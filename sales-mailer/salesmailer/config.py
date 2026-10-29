"""設定ファイル（config.toml）の読み込み。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 以前
    import tomli as tomllib

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.toml"
EXAMPLE_PATH = BASE_DIR / "config.example.toml"

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
