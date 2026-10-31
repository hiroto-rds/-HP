"""送信対象の絞り込み。"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote, urlparse

from .config import load_exclude_names, normalize_name
from .sheet import FINAL_RESULTS, Lead

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s、，,）)]+")


def extract_email(text: str) -> str:
    m = EMAIL_RE.search(text or "")
    return m.group(0) if m else ""


def extract_url(text: str) -> str:
    m = URL_RE.search(text or "")
    return m.group(0) if m else ""


REGIONS = {
    "北海道": ["北海道"],
    "東北": ["青森", "岩手", "宮城", "秋田", "山形", "福島"],
    "関東": ["茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川"],
    "中部": ["新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜", "静岡", "愛知"],
    "近畿": ["三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山"],
    "関西": ["三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山"],
    "中国": ["鳥取", "島根", "岡山", "広島", "山口"],
    "四国": ["徳島", "香川", "愛媛", "高知"],
    "九州": ["福岡", "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島"],
    "沖縄": ["沖縄"],
}


def expand_prefectures(words: list[str]) -> list[str]:
    """「宮崎」「福岡県」「九州」のような指定を、都道府県名の頭の部分のリストにする。"""
    out = []
    for word in words:
        for w in word.replace("、", ",").replace("，", ",").split(","):
            w = w.strip()
            if w.endswith("地方"):
                w = w[:-2]
            if not w:
                continue
            if w in REGIONS:
                out += REGIONS[w]
            elif w != "北海道" and w[-1] in "都道府県":
                out.append(w[:-1])
            else:
                out.append(w)
    return out


def in_prefectures(pref: str, wanted: list[str]) -> bool:
    return any(pref.startswith(w) for w in wanted)


# お店の公式フォームではない、ポータルサイト・SNS など（設定ファイルの skip_form_domains に加えて使わない）
PORTAL_DOMAINS = [
    "goobike.com", "bikebros.co.jp", "webike.net", "hondago-bikerental.jp", "rental819.com",
    "instagram.com", "facebook.com", "x.com", "twitter.com", "line.me", "google.com",
]


def is_search_url(url: str) -> bool:
    """Google のページか（検索結果のほか、同意画面・ロボット確認画面などに転送された場合も含む）。"""
    host = urlparse(url or "").netloc.lower()
    return host.startswith(("google.", "www.google.", "consent.google.")) or ".google." in host


def search_url(lead: Lead) -> str:
    """お店の公式サイトを探すための Google 検索の URL（店名＋都道府県・市区町村）。"""
    shop = re.sub(r"[（(][^（）()]*[）)]", "", lead.shop_name).strip() or lead.shop_name
    area = lead.prefecture + lead.values.get("市区町村", "").strip()
    return "https://www.google.com/search?q=" + quote(f"{shop} {area}".strip())


def normalize_url(url: str) -> str:
    if is_search_url(url):
        return url.lower()
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


class Selector:
    def __init__(self, cfg: dict, log: list[dict]):
        self.f = cfg["filter"]
        self.excludes = [(name, normalize_name(name)) for name in load_exclude_names(cfg)]
        self.search_when_no_form = cfg.get("form", {}).get("search_when_no_form", False)
        self.done_ids = set()
        self.done_targets = set()
        for e in log:
            if e.get("結果") in FINAL_RESULTS:
                self.done_ids.add(e.get("リードID", ""))
                target = e.get("宛先", "")
                self.done_targets.add(target.lower() if "@" in target else normalize_url(target))
        self.log = log

    def sent_today(self, method: str) -> int:
        today = date.today().isoformat()
        return sum(
            1 for e in self.log
            if e.get("日時", "").startswith(today) and e.get("方法") == method and e.get("結果") == "送信済み"
        )

    def skip_reason(self, lead: Lead) -> str | None:
        """送ってはいけない理由があれば返す（メール・フォーム共通の条件）。"""
        f = self.f
        if lead.lead_id in self.done_ids:
            return "送信ログに記録済み"
        name = self.excluded_by(lead)
        if name:
            return f"送らない会社リスト（{name}）"
        # 「対象判定」「リスト状態」の列がないスプレッドシート（タブ）では、この条件は使わない
        judgement = lead.get("judgement")
        if f["allowed_judgements"] and lead.has("judgement") and judgement not in f["allowed_judgements"]:
            return f"対象判定が「{judgement or '空欄'}」"
        if f["required_list_state"] and lead.has("list_state") and lead.get("list_state") != f["required_list_state"]:
            return "リスト状態が対象外"
        status = lead.get("business_status")
        if any(k in status for k in f["skip_business_status_keywords"]):
            return f"営業状態が「{status}」"
        remarks = lead.get("remarks")
        if any(k in remarks for k in f["skip_remarks_keywords"]):
            return "備考に送信不可の記載あり"
        if f["skip_already_contacted"]:
            count = lead.get("approach_count")
            if (count and count not in ("0", "0.0")) or lead.get("last_contact"):
                return "連絡済み（アプローチ回数・最終コンタクトあり）"
        return None

    def excluded_by(self, lead: Lead) -> str | None:
        """exclude.txt のどの名前に当てはまるか。"""
        target = normalize_name(lead.shop_name + " " + lead.get("company"))
        for name, norm in self.excludes:
            if norm and norm in target:
                return name
        return None

    def email_for(self, lead: Lead) -> str:
        """メール送信に使えるアドレス。使えなければ空文字。"""
        email = extract_email(lead.get("email"))
        if not email:
            return ""
        adoption_col = lead.cols.get("email_adoption", "")
        if adoption_col in lead.values and lead.values[adoption_col].strip() not in self.f["allowed_email_adoption"]:
            return ""
        return email

    def form_for(self, lead: Lead) -> str:
        url = extract_url(lead.get("form_url"))
        if not url:
            return ""
        host = urlparse(url).netloc.lower()
        if any(host == d or host.endswith("." + d) for d in PORTAL_DOMAINS + self.f["skip_form_domains"]):
            return ""
        return url

    def email_candidates(self, leads: list[Lead]) -> list[tuple[Lead, str]]:
        out, seen = [], set()
        for lead in sorted(leads, key=lambda l: -l.score):
            if self.skip_reason(lead):
                continue
            email = self.email_for(lead)
            key = email.lower()
            if not email or key in self.done_targets or key in seen or lead.lead_id in seen:
                continue
            seen.update({key, lead.lead_id})
            out.append((lead, email))
        return out

    def form_candidates(self, leads: list[Lead]) -> list[tuple[Lead, str]]:
        """フォームで送る会社。公式フォームの URL がない会社は、Google 検索で探す（search_when_no_form）。"""
        out, seen = [], set()
        for lead in sorted(leads, key=lambda l: -l.score):
            if self.skip_reason(lead):
                continue
            if self.f["form_only_when_no_email"] and self.email_for(lead):
                continue
            url = self.form_for(lead) or (search_url(lead) if self.search_when_no_form else "")
            key = normalize_url(url)
            if not url or key in self.done_targets or key in seen or lead.lead_id in seen:
                continue
            seen.update({key, lead.lead_id})
            out.append((lead, url))
        return sorted(out, key=lambda c: is_search_url(c[1]))  # 公式フォームがある会社を先に

    def explain(self, leads: list[Lead]) -> list[tuple[Lead, str, str]]:
        """会社ごとに、メール・フォームそれぞれ送れるか（送れない理由）を返す。"""
        mail_ok = {id(l): t for l, t in self.email_candidates(leads)}
        form_ok = {id(l): t for l, t in self.form_candidates(leads)}
        out = []
        for lead in sorted(leads, key=lambda l: -l.score):
            reason = self.skip_reason(lead)
            if reason:
                out.append((lead, reason, reason))
                continue
            if id(lead) in mail_ok:
                mail = "○ " + mail_ok[id(lead)]
            elif not extract_email(lead.get("email")):
                mail = "メールアドレスなし"
            elif not self.email_for(lead):
                mail = f"メール採用判定が「{lead.get('email_adoption') or '空欄'}」"
            else:
                mail = "同じアドレスに送信済み・送信予定"
            if id(lead) in form_ok:
                form = "○ Googleでお店のサイトを探す" if is_search_url(form_ok[id(lead)]) else "○ " + form_ok[id(lead)]
            elif self.f["form_only_when_no_email"] and self.email_for(lead):
                form = "メールで送るため対象外"
            elif not extract_url(lead.get("form_url")):
                form = "フォームURLなし"
            elif not self.form_for(lead):
                form = "ポータルサイト等のため使わない"
            else:
                form = "同じフォームに送信済み・送信予定"
            out.append((lead, mail, form))
        return out
