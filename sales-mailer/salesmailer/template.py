"""文面テンプレートの読み込みと差し込み。

テンプレートの {店名} {宛名} {送信者氏名} などを会社ごとの値に置き換える。
スプレッドシートの見出し名（例: {都道府県} {重点エリア}）もそのまま使える。
"""
from __future__ import annotations

import re

from .config import normalize_name, resolve_path
from .sheet import Lead

PLACEHOLDER_RE = re.compile(r"\{([^{}\n]+)\}")
# 「株式会社山儀（サイト表示: 株式会社ヤマギ）」「〇〇（法人格未確認）」のような調査メモの括弧書き
NOTE_RE = re.compile(r"[（(][^（）()]*(?:[:：]|未確認|確認中|要確認|不明|推定|表示|調査)[^（）()]*[）)]")
PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")


class TemplateError(Exception):
    pass


def clean_name(text: str) -> str:
    """店名から調査メモの括弧書きを取り除く（「アオキ（AOKI）」のような読みの括弧は残す）。"""
    return NOTE_RE.sub("", text or "").strip()


def clean_company(text: str) -> str:
    """会社名（公開運営主体）は、括弧書きをすべて取り除く。"""
    return PAREN_RE.sub("", text or "").strip()


def addressee(company: str, shop: str) -> str:
    """宛先の会社名・店名。同じ名前（会社名が店名に含まれる場合も）なら1つだけにする。"""
    if not company or normalize_name(company) in normalize_name(shop):
        return shop
    if not shop or normalize_name(shop) in normalize_name(company):
        return company
    return f"{company}\n{shop}"


def load_template(path: str) -> tuple[str, str]:
    """「件名: ...」の行と「---」の行のあとに本文、という形式のファイルを読む。"""
    text = resolve_path(path).read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n")
    if not sep or not head.strip().startswith("件名:"):
        raise TemplateError(f"{path} の1行目は「件名: 〜」、2行目は「---」にしてください。")
    return head.strip()[len("件名:"):].strip(), body.strip() + "\n"


def build_context(lead: Lead, sender: dict) -> dict:
    shop = clean_name(lead.shop_name)
    company = clean_company(lead.get("company"))
    ctx = dict(lead.values)
    ctx.update({
        "店名": shop,
        "会社名": company or shop,
        "宛先名": addressee(company, shop),
        "宛名": addressee(company, shop) + " ご担当者様",
        "送信者会社名": sender["company"],
        "送信者姓": sender["last_name"],
        "送信者名": sender["first_name"],
        "送信者氏名": f"{sender['last_name']} {sender['first_name']}",
        "送信者氏名カナ": f"{sender['last_name_kana']} {sender['first_name_kana']}",
        "送信者メール": sender["email"],
        "送信者電話": sender["phone"],
        "送信者郵便番号": sender["zip"],
        "送信者住所": sender["address"],
        "送信者URL": sender.get("url", ""),
    })
    return ctx


def render(text: str, ctx: dict) -> str:
    unknown = sorted({m for m in PLACEHOLDER_RE.findall(text) if m not in ctx})
    if unknown:
        raise TemplateError("テンプレートに使えない差し込み項目があります: " + "、".join("{" + u + "}" for u in unknown))
    return PLACEHOLDER_RE.sub(lambda m: str(ctx[m.group(1)]).strip(), text)


def render_message(template: tuple[str, str], lead: Lead, sender: dict) -> tuple[str, str]:
    ctx = build_context(lead, sender)
    subject, body = template
    return render(subject, ctx), render(body, ctx)
