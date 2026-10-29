"""設定ファイル（config.toml）の読み込み。"""
from __future__ import annotations

import re
import shutil
import sys
import unicodedata
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 以前
    import tomli as tomllib

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.toml"
EXAMPLE_PATH = BASE_DIR / "config.example.toml"
EXCLUDE_PATH = BASE_DIR / "exclude.txt"

PLACEHOLDER = "（要記入）"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        shutil.copy(EXAMPLE_PATH, CONFIG_PATH)
        sys.exit(
            f"設定ファイルを作成しました: {CONFIG_PATH}\n"
            "「（要記入）」の部分を書き換えてから、もう一度実行してください。"
        )
    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)
    if PLACEHOLDER in cfg["sheet"]["spreadsheet_id"]:
        sys.exit("config.toml の [sheet] spreadsheet_id を記入してください。")
    return cfg


def resolve_path(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else BASE_DIR / p


def missing_sender_fields(cfg: dict) -> list[str]:
    """送信者情報のうち、まだ「（要記入）」のままの項目名を返す。"""
    return [k for k, v in cfg["sender"].items() if PLACEHOLDER in str(v)]


def normalize_name(text: str) -> str:
    """会社名の比較用に、全角・半角、大文字・小文字、空白・記号の違いをそろえる。"""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s'’‘`´・.,，、。]", "", text)


def load_exclude_names() -> list[str]:
    """exclude.txt（送らない会社のリスト）を読む。"""
    if not EXCLUDE_PATH.exists():
        return []
    lines = EXCLUDE_PATH.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
