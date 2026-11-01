"""設定ファイル（config.toml / config.mfarm.toml など）の読み込み。"""
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
DEFAULT_CONFIG = "config.toml"
EXAMPLE_PATH = BASE_DIR / "config.example.toml"
DEFAULT_EXCLUDE = "exclude.txt"

PLACEHOLDER = "（要記入）"

EXCLUDE_HEADER = """# 送らない会社のリスト（1行に1社）
# 店名・会社名にこの言葉が含まれる会社には、メールもフォームも送りません。
# 全角・半角、大文字・小文字、空白の違いは区別しません。
"""


def config_path(name: str | None) -> Path:
    """--config の指定から設定ファイルの場所を決める。

    指定なし → config.toml / 「mfarm」→ config.mfarm.toml / 「config.mfarm.toml」→ そのまま
    """
    if not name:
        name = DEFAULT_CONFIG
    elif not name.endswith(".toml"):
        name = f"config.{name}.toml"
    return resolve_path(name)


def example_for(path: Path) -> Path:
    """config.mfarm.toml の見本は config.mfarm.example.toml（なければ config.example.toml）。"""
    candidate = path.with_name(path.stem + ".example.toml")
    return candidate if candidate.exists() else EXAMPLE_PATH


def load_config(name: str | None = None) -> dict:
    path = config_path(name)
    if not path.exists():
        example = example_for(path)
        if name and example == EXAMPLE_PATH and path.name != DEFAULT_CONFIG:
            sys.exit(
                f"設定ファイル {path.name} が見つかりません。\n"
                "--config の後ろの名前を確認してください（例: --config mfarm）。"
            )
        shutil.copy(example, path)
        sys.exit(
            f"設定ファイルを作成しました: {path}\n"
            "「（要記入）」の部分を書き換えてから、もう一度実行してください。"
        )
    with path.open("rb") as f:
        try:
            cfg = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"{path.name} の書き方に誤りがあります（\" の閉じ忘れなど）: {e}")
    cfg["_file"] = path.name
    if PLACEHOLDER in cfg["sheet"]["spreadsheet_id"]:
        sys.exit(f"{path.name} の [sheet] spreadsheet_id を記入してください。")
    cfg["sheet"]["spreadsheet_id"] = spreadsheet_id(cfg["sheet"]["spreadsheet_id"])
    if any(PLACEHOLDER in t for t in cfg["sheet"]["tabs"]):
        sys.exit(f"{path.name} の [sheet] tabs に、読み込むタブ（シート）の名前を記入してください。")
    return cfg


def spreadsheet_id(text: str) -> str:
    """URL がまるごと貼られていても、/d/【ここ】/ の部分だけを取り出す。"""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    return m.group(1) if m else text.strip()


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


def exclude_path(cfg: dict) -> Path:
    return resolve_path(cfg["sheet"].get("exclude_file") or DEFAULT_EXCLUDE)


def load_exclude_names(cfg: dict) -> list[str]:
    """送らない会社のリスト（exclude.txt など）を読む。ファイルがなければ空のリストを作る。"""
    path = exclude_path(cfg)
    if not path.exists():
        path.write_text(EXCLUDE_HEADER, encoding="utf-8")
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
