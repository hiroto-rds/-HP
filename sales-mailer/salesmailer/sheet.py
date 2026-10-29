"""Google スプレッドシートの読み書き。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from .config import resolve_path

# OAuth でログインしたあとの許可情報を保存するファイル（credentials フォルダ内）
TOKEN_FILE = "token.json"

LOG_HEADER =["日時", "方法", "結果", "リードID", "店名", "宛先", "タブ", "メモ"]

# この結果が記録された会社には、次回以降は送らない（「エラー」だけは再挑戦する）
FINAL_RESULTS = {"送信済み", "スキップ", "営業お断り", "フォームなし"}


@dataclass
class Lead:
    tab: str
    row: int  # スプレッドシート上の行番号（1始まり）
    values: dict = field(repr=False)
    cols: dict = field(repr=False)  # [columns] の設定

    def get(self, key: str) -> str:
        """[columns] のキー名（shop_name など）で値を取り出す。"""
        return self.values.get(self.cols.get(key, ""), "").strip()

    @property
    def lead_id(self) -> str:
        return self.get("lead_id") or f"{self.tab}!{self.row}"

    @property
    def shop_name(self) -> str:
        return self.get("shop_name")

    @property
    def score(self) -> int:
        try:
            return int(float(self.get("score")))
        except ValueError:
            return -1

    def label(self) -> str:
        pref = self.values.get("都道府県", "")
        return f"{self.shop_name}（{pref}）" if pref else self.shop_name


class SheetClient:
    def __init__(self, cfg: dict):
        import gspread

        self._gspread = gspread
        self.cfg = cfg
        self.cols = cfg["columns"]
        gc, hint = self._authorize(gspread, resolve_path(cfg["sheet"]["credentials_file"]))
        try:
            self.book = gc.open_by_key(cfg["sheet"]["spreadsheet_id"])
        except (gspread.exceptions.SpreadsheetNotFound, gspread.exceptions.APIError) as e:
            raise SystemExit(f"スプレッドシートを開けませんでした。\n{hint}\n（詳細: {e}）")
        self._log_ws = None

    @staticmethod
    def _authorize(gspread, cred):
        """credentials フォルダの JSON の種類に合わせて、Google にログインする。

        - OAuth クライアント（デスクトップアプリ）: 初回だけブラウザで自分の Google アカウントにログイン
        - サービスアカウントの鍵: そのまま接続
        """
        if not cred.exists():
            found = [p for p in cred.parent.glob("*.json") if p.name != TOKEN_FILE]
            if len(found) != 1:
                raise SystemExit(
                    f"Google の認証ファイルが見つかりません: {cred}\n"
                    "README の「Google スプレッドシートとの接続」の手順で作成してください。"
                )
            cred = found[0]
        info = json.loads(cred.read_text(encoding="utf-8"))
        if info.get("type") == "service_account":
            return gspread.service_account(filename=str(cred)), (
                f"サービスアカウント（{info.get('client_email', '')}）に"
                "スプレッドシートを「編集者」として共有してあるか確認してください。"
            )
        if "installed" in info or "web" in info:
            token = cred.parent / TOKEN_FILE
            if not token.exists():
                print("ブラウザが開くので、スプレッドシートを編集できる Google アカウントでログインし、「許可」を押してください。")
            gc = gspread.oauth(
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
                credentials_filename=str(cred),
                authorized_user_filename=str(token),
            )
            return gc, "ログインした Google アカウントで、このスプレッドシートを編集できるか確認してください。"
        raise SystemExit(f"{cred.name} は Google の認証ファイルではないようです。")

    # ---------- 読み込み ----------

    def load_leads(self) -> list[Lead]:
        leads = []
        for tab in self.cfg["sheet"]["tabs"]:
            try:
                ws = self.book.worksheet(tab)
            except self._gspread.exceptions.WorksheetNotFound:
                print(f"⚠ タブ「{tab}」が見つからないため読み飛ばします。")
                continue
            rows = ws.get_all_values()
            if not rows:
                continue
            header = [h.strip() for h in rows[0]]
            for i, row in enumerate(rows[1:], start=2):
                values = {}
                for h, v in zip(header, row):
                    if h and h not in values:
                        values[h] = v
                if not any(v.strip() for v in values.values()):
                    continue
                leads.append(Lead(tab=tab, row=i, values=values, cols=self.cols))
        return leads

    def log_ws(self):
        if self._log_ws is None:
            name = self.cfg["sheet"]["log_tab"]
            try:
                self._log_ws = self.book.worksheet(name)
            except self._gspread.exceptions.WorksheetNotFound:
                self._log_ws = self.book.add_worksheet(title=name, rows=1000, cols=len(LOG_HEADER))
                self._log_ws.append_row(LOG_HEADER, value_input_option="RAW")
        return self._log_ws

    def load_log(self) -> list[dict]:
        rows = self.log_ws().get_all_values()
        if not rows:
            return []
        header = rows[0]
        return [dict(zip(header, r)) for r in rows[1:]]

    # ---------- 書き込み ----------

    def record(self, lead: Lead, method: str, result: str, target: str, memo: str = "") -> dict:
        """送信ログに1行追加し、送信済みならリストの「アプローチ回数」「最終コンタクト」も更新する。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = [now, method, result, lead.lead_id, lead.shop_name, target, lead.tab, memo]
        self.log_ws().append_row(entry, value_input_option="RAW")
        if result == "送信済み":
            self._mark_contacted(lead, method, now[:10])
        return dict(zip(LOG_HEADER, entry))

    def _mark_contacted(self, lead: Lead, method: str, date: str) -> None:
        ws = self.book.worksheet(lead.tab)
        header = [h.strip() for h in ws.row_values(1)]
        row = self._locate_row(ws, header, lead)
        if row is None:
            print(f"  ⚠ 「{lead.tab}」で {lead.lead_id} の行が見つからず、最終コンタクトを更新できませんでした。")
            return
        current = ws.row_values(row)
        updates = []
        count_col = self._col(header, "approach_count")
        if count_col:
            old = current[count_col - 1] if len(current) >= count_col else ""
            try:
                count = int(float(old)) + 1
            except ValueError:
                count = 1
            updates.append((count_col, count))
        last_col = self._col(header, "last_contact")
        if last_col:
            updates.append((last_col, f"{date} {method}"))
        if updates:
            a1 = self._gspread.utils.rowcol_to_a1
            ws.batch_update(
                [{"range": a1(row, c), "values": [[v]]} for c, v in updates],
                value_input_option="RAW",
            )

    def _col(self, header: list[str], key: str) -> int | None:
        name = self.cols.get(key, "")
        return header.index(name) + 1 if name in header else None

    def _locate_row(self, ws, header: list[str], lead: Lead) -> int | None:
        """読み込み後に行の並べ替え・挿入があっても正しい行に書くため、リードIDで行を探し直す。"""
        id_col = self._col(header, "lead_id")
        if id_col is None or not lead.get("lead_id"):
            return lead.row
        ids = ws.col_values(id_col)
        for i, v in enumerate(ids, start=1):
            if v.strip() == lead.get("lead_id"):
                return i
        return None
