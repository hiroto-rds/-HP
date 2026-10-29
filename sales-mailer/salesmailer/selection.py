"""送信対象の絞り込み。"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

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


def normalize_url(url: str) -> str:
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()


class Selector:
    def __init__(self, cfg: dict, log: list[dict]):
        self.f = cfg["filter"]
        self.excludes = [(name, normalize_name(name)) for name in load_exclude_names()]
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
        judgement = lead.get("judgement")
        if f["allowed_judgements"] and judgement not in f["allowed_judgements"]:
            return f"対象判定が「{judgement or '空欄'}」"
        if f["required_list_state"] and lead.get("list_state") != f["required_list_state"]:
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
        if any(host == d or host.endswith("." + d) for d in self.f["skip_form_domains"]):
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
        out, seen = [], set()
        for lead in sorted(leads, key=lambda l: -l.score):
            if self.skip_reason(lead):
                continue
            if self.f["form_only_when_no_email"] and self.email_for(lead):
                continue
            url = self.form_for(lead)
            key = normalize_url(url)
            if not url or key in self.done_targets or key in seen or lead.lead_id in seen:
                continue
            seen.update({key, lead.lead_id})
            out.append((lead, url))
        return out
