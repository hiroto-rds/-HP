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


def account_addresses() -> list[str]:
    """「メール」アプリに登録されているアカウントのメールアドレスの一覧（小文字）。"""
    import re

    if sys.platform != "darwin":
        raise MailError("メール送信は Mac でのみ実行できます。")
    try:
        r = subprocess.run(
            ["osascript", "-e", 'tell application "Mail" to get email addresses of every account'],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        raise MailError((e.stderr or "").strip() or "メールアプリのアカウントを確認できませんでした。")
    except subprocess.TimeoutExpired:
        raise MailError("メールアプリが応答しませんでした。")
    return list(dict.fromkeys(a.lower() for a in re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", r.stdout)))


def check_sender(sender: str) -> None:
    """送信者アドレスが「メール」アプリに登録されているか確認する（別の会社のアドレスで送るのを防ぐ）。"""
    if not sender:
        raise MailError("送信者のメールアドレス（[sender] email）が空です。")
    addresses = account_addresses()
    if sender.lower() not in addresses:
        raise MailError(
            f"{sender} は Mac の「メール」アプリに登録されていません。\n"
            "メールアプリの「設定」→「アカウント」に、このアドレスのアカウントを追加してください。\n"
            f"（登録されているアドレス: {', '.join(addresses) or 'なし'}）"
        )
