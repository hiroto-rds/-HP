"""Mac の「メール」アプリ経由での送信（AppleScript を osascript で実行）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("send_mail.applescript")


class MailError(Exception):
    pass


def send_mail(to: str, subject: str, body: str, sender: str = "") -> None:
    if sys.platform != "darwin":
        raise MailError("メール送信は Mac でのみ実行できます。")
    try:
        subprocess.run(
            ["osascript", str(SCRIPT), to, subject, body, sender],
            check=True, capture_output=True, text=True, timeout=120,
        )
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or "").strip()
        if "-1743" in msg or "not allowed" in msg.lower():
            msg += "\n→ システム設定 > プライバシーとセキュリティ > オートメーション で、ターミナルに「メール」の操作を許可してください。"
        raise MailError(msg or "メールアプリでの送信に失敗しました。")
    except subprocess.TimeoutExpired:
        raise MailError("メールアプリが応答しませんでした。")
