"""お問い合わせフォームへの自動入力（送信ボタンは人が押す）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import normalize_name

# 各入力欄の「見出し」に当たる文字列を集める（label, placeholder, name, 表の見出しなど）
DESCRIBE_JS = r"""
el => {
  const parts = [];
  const add = s => { if (s && String(s).trim()) parts.push(String(s).trim()); };
  if (el.labels) for (const l of el.labels) add(l.innerText);
  const lb = el.getAttribute('aria-labelledby');
  if (lb) lb.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) add(n.innerText); });
  add(el.getAttribute('aria-label'));
  add(el.placeholder);
  add(el.name);
  add(el.id);
  const tr = el.closest('tr');
  if (tr) { const th = tr.querySelector('th'); if (th) add(th.innerText); }
  const dd = el.closest('dd');
  if (dd && dd.previousElementSibling && dd.previousElementSibling.tagName === 'DT') add(dd.previousElementSibling.innerText);
  let p = el.parentElement;
  for (let i = 0; i < 3 && p; i++, p = p.parentElement) {
    const t = (p.innerText || '').trim();
    if (t) { if (t.length < 60) add(t); break; }
  }
  const st = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  return {
    text: parts.join(' | '),
    tag: el.tagName.toLowerCase(),
    type: (el.getAttribute('type') || '').toLowerCase(),
    visible: st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0,
    disabled: el.disabled || el.readOnly,
    value: el.type === 'checkbox' ? '' : (el.value || ''),
    checked: !!el.checked,
    maxlength: el.maxLength > 0 ? el.maxLength : 0,
    form: el.form ? Array.from(document.forms).indexOf(el.form) : -1,
  };
}
"""

SKIP_TYPES = {"hidden", "submit", "button", "image", "file", "reset", "password", "radio", "search",
              "date", "time", "number", "range", "color"}

# 上から順に判定する（「会社名」を「名前」より先に判定する、など順番が大事）
RULES = [
    ("email_confirm", r"(mail|メール).*(確認|confirm|再入力|もう一度|again|conf)|(確認|confirm|再入力|もう一度).*(mail|メール)"),
    ("email", r"mail|メール"),
    ("kana", r"ふりがな|フリガナ|カナ|かな|kana|furigana|ruby|yomi"),
    ("zip", r"郵便|〒|zip|postal|postcode"),
    ("phone", r"電話|tel|phone|携帯|fax"),
    ("company", r"会社|企業|法人|貴社|御社|団体|組織|社名|店名|店舗名|屋号|company|corp|organization"),
    ("department", r"部署|役職|department|position"),
    ("url", r"url|ホームページ|website|web\s?サイト"),
    ("address", r"住所|所在地|都道府県|市区町村|番地|address|addr|pref|city"),
    ("subject", r"件名|題名|タイトル|subject"),
    ("message", r"内容|本文|お問い?合わ?せ|問合|ご質問|ご用件|ご要望|詳細|メッセージ|message|inquiry|comment|body|content"),
    ("name", r"名前|氏名|担当|姓|名|name"),
]
AGREE_RE = re.compile(r"同意|プライバシー|個人情報|privacy|agree|承諾|規約")
FAX_RE = re.compile(r"fax", re.I)
NO_HYPHEN_RE = re.compile(r"ハイフン(なし|無し|不要|を?除|を?入れず)|数字のみ")
# 入力欄が複数見つかっても、最初の1つにだけ入れる項目
SINGLE_KEYS = {"company", "address", "url", "subject", "message"}

REFUSAL_RE = re.compile(
    r"(営業|セールス|売り込み|勧誘|広告)[^。\n]{0,30}"
    r"(お断り|ご遠慮|禁止|控え|受け付けて(い)?ません|お受けして(い)?ません|対応(いた)?しかね|返信(いた)?しません|お答えできません)"
)
CAPTCHA_RE = re.compile(r"recaptcha|hcaptcha|turnstile|captcha", re.I)

LABELS = {
    "company": "会社名", "name": "お名前", "kana": "フリガナ", "email": "メール", "email_confirm": "メール(確認)",
    "phone": "電話", "zip": "郵便番号", "address": "住所", "url": "URL", "subject": "件名",
    "message": "お問い合わせ内容", "agree": "同意チェック",
}


@dataclass
class FillResult:
    filled: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def classify(info: dict) -> str | None:
    if info["disabled"]:
        return None
    tag, typ, text = info["tag"], info["type"], info["text"].lower()
    if tag == "select":
        return None
    if typ == "checkbox":
        return "agree" if AGREE_RE.search(text) else None
    if not info["visible"]:  # 見えない入力欄はスパム対策の罠のことがあるので触らない
        return None
    if typ in SKIP_TYPES:
        return None
    if typ == "email":
        return "email_confirm" if re.search(RULES[0][1], text) else "email"
    if typ == "tel":
        return None if FAX_RE.search(text) else "phone"
    for key, pattern in RULES:
        if re.search(pattern, text):
            if key == "phone" and FAX_RE.search(text):
                return None
            if key == "message" and tag != "textarea" and not re.search(r"件名|subject", text):
                # 1行の入力欄に「お問い合わせ種別」などが付いているだけのことが多い
                continue
            return None if key == "department" else key
    if tag == "textarea":
        return "message"
    return None


def to_hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def build_values(sender: dict, subject: str, message: str) -> dict:
    return {
        "company": sender["company"],
        "name": f"{sender['last_name']} {sender['first_name']}",
        "name_parts": [sender["last_name"], sender["first_name"]],
        "kana": f"{sender['last_name_kana']} {sender['first_name_kana']}",
        "kana_parts": [sender["last_name_kana"], sender["first_name_kana"]],
        "email": sender["email"],
        "email_confirm": sender["email"],
        "phone": sender["phone"],
        "phone_parts": sender["phone"].split("-"),
        "zip": sender["zip"],
        "zip_parts": sender["zip"].replace("〒", "").split("-"),
        "address": sender["address"],
        "url": sender.get("url", ""),
        "subject": subject,
        "message": message,
    }


# 店名のうち、どのお店にも付く言葉（ページに店名があるかの確認では無視する）
GENERIC_WORDS = [
    "株式会社", "有限会社", "合同会社", "(株)", "(有)", "バイクショップ", "bikeshop", "モーターサイクル",
    "motorcycles", "motorcycle", "モータース", "motors", "オートバイ", "バイク", "bike", "サイクル", "cycle",
    "ショップ", "shop", "オート", "auto", "本店", "店",
]


def name_keys(names: list[str]) -> list[str]:
    """店名から、ページ内を探すときの手がかりになる言葉を取り出す。"""
    keys = []
    for name in names:
        name = re.sub(r"[（(][^（）()]*[）)]", " ", name or "")
        for token in re.split(r"[\s　【】「」/／]+", name):
            key = normalize_name(token)
            for word in GENERIC_WORDS:
                key = key.replace(normalize_name(word), "")
            if len(key) >= 2:
                keys.append(key)
    return keys


def page_warnings(page, names: list[str] | None = None) -> list[str]:
    warnings = []
    try:
        body = page.inner_text("body", timeout=5000)
    except Exception:
        body = ""
    keys = name_keys(names or [])
    if keys and body:
        text = normalize_name(body + (page.title() or ""))
        if not any(k in text for k in keys):
            warnings.append(f"このページに店名「{names[0]}」が見当たりません。別のお店のページかもしれません（g で検索できます）。")
    m = REFUSAL_RE.search(body)
    if m:
        warnings.append(f"営業お断りの記載があります：「{m.group(0)}」")
    if any(CAPTCHA_RE.search(f.url or "") for f in page.frames):
        warnings.append("画像認証（reCAPTCHA など）があります。必要ならブラウザで操作してください。")
    return warnings


def fill_page(page, values: dict) -> FillResult:
    result = FillResult()
    # ページ内の <form> ごとに入力欄を分類し、問い合わせフォームらしいもの（本文欄があり項目が多い）だけに入れる
    forms: dict[tuple, dict[str, list]] = {}
    for fi, frame in enumerate(page.frames):
        try:
            handles = frame.query_selector_all("input, textarea, select")
        except Exception:
            continue
        for h in handles:
            try:
                info = h.evaluate(DESCRIBE_JS)
            except Exception:
                continue
            key = classify(info)
            if key:
                forms.setdefault((fi, info["form"]), {}).setdefault(key, []).append((h, info))
    if not forms:
        return result
    groups = max(forms.values(), key=lambda g: (10 if "message" in g else 0) + len(g))

    # 1つの項目が複数の入力欄に分かれている場合（姓・名、電話番号3分割など）は順に分けて入れる
    plans = []
    for key, items in groups.items():
        if key == "agree":
            plans += [(h, info, True, key) for h, info in items]
            continue
        if key in SINGLE_KEYS and len(items) > 1:
            if key == "address":
                result.warnings.append("住所欄が複数に分かれています。ブラウザで分け直してください。")
            items = items[:1]
        parts = values.get(f"{key}_parts")
        if key in ("name", "kana", "phone", "zip") and parts and len(items) == len(parts) > 1:
            plans += [(h, info, part, key) for (h, info), part in zip(items, parts)]
        elif key in ("name", "kana", "phone", "zip") and len(items) > 1:
            plans.append((items[0][0], items[0][1], values[key], key))
        else:
            plans += [(h, info, values[key], key) for h, info in items]

    for h, info, value, key in plans:
        try:
            if value is True:
                if not info["checked"]:
                    h.check(force=True, timeout=3000)
            elif not value:
                continue
            elif not info["value"].strip():  # すでに入力済みの欄はそのままにする
                if key == "kana" and re.search(r"ふりがな|ひらがな", info["text"]):
                    value = to_hiragana(value)
                if key in ("phone", "zip") and NO_HYPHEN_RE.search(info["text"]):
                    value = value.replace("-", "")
                if info["maxlength"] and len(value) > info["maxlength"]:
                    result.warnings.append(
                        f"{LABELS[key]}は{info['maxlength']}文字までの欄です（文面は{len(value)}文字）。短くしてください。"
                    )
                h.fill(value, timeout=5000)
            if LABELS[key] not in result.filled:
                result.filled.append(LABELS[key])
        except Exception as e:
            result.warnings.append(f"{LABELS[key]}を入力できませんでした（{type(e).__name__}）")
    return result
