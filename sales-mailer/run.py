"""営業メール・お問い合わせフォーム送信ツール

使い方（詳しくは README.md）:
  python3 run.py check                 送信対象の件数を確認する
  python3 run.py preview [-n 3]        送信するメールの文面を確認する（送信しない）
  python3 run.py test-mail 自分のアドレス  1通だけ自分宛てにテスト送信する
  python3 run.py mail [--limit 10]     メールを送信する（1日の上限まで）
  python3 run.py form [--limit 10]     フォームを半自動で入力する（送信ボタンは自分で押す）
  どのコマンドも --pref 宮崎 福岡（または --pref 九州）で都道府県ごとに絞り込めます
"""
from __future__ import annotations

import argparse
import random
import sys
import time

from salesmailer.config import load_config, missing_sender_fields
from salesmailer.selection import Selector, expand_prefectures, in_prefectures, is_search_url
from salesmailer.sheet import SheetClient
from salesmailer.template import TemplateError, load_template, render_message


def connect(cfg, args=None):
    print("スプレッドシートを読み込んでいます…")
    sheet = SheetClient(cfg)
    leads = sheet.load_leads()
    selector = Selector(cfg, sheet.load_log())
    words = getattr(args, "pref", None)
    if words:
        wanted = expand_prefectures(words)
        leads = [l for l in leads if in_prefectures(l.prefecture, wanted)]
        print(f"都道府県で絞り込み: {'・'.join(wanted)}（{len(leads)} 件）")
        if not leads:
            sys.exit("指定した都道府県の会社がありません。都道府県名を確認してください。")
    return sheet, leads, selector


def require_sender(cfg):
    missing = missing_sender_fields(cfg)
    if missing:
        sys.exit("config.toml の [sender] に「（要記入）」が残っています: " + ", ".join(missing))


def render_all(cfg, section, candidates):
    """送信前に全件の文面を作ってみて、差し込みミスがあれば送信を始めない。"""
    try:
        template = load_template(cfg[section]["template"])
        return [(lead, target, *render_message(template, lead, cfg["sender"])) for lead, target in candidates]
    except TemplateError as e:
        sys.exit(f"文面テンプレートの問題: {e}")


def confirm(question: str) -> bool:
    return input(f"{question} (y/N) > ").strip().lower() in ("y", "yes")


# ---------------- コマンド ----------------

def cmd_check(cfg, args):
    _, leads, selector = connect(cfg, args)
    mails = selector.email_candidates(leads)
    forms = selector.form_candidates(leads)
    print(f"\n読み込んだ会社: {len(leads)} 件（タブ: {', '.join(cfg['sheet']['tabs'])}）")
    print(f"メール送信の対象: {len(mails)} 件（今日の送信済み {selector.sent_today('メール')} / 上限 {cfg['mail']['daily_limit']}）")
    print(f"フォーム送信の対象: {len(forms)} 件（今日の送信済み {selector.sent_today('フォーム')} / 上限 {cfg['form']['daily_limit']}）")
    counts: dict = {}
    for i, items in enumerate((mails, forms)):
        for lead, _ in items:
            counts.setdefault(lead.prefecture or "（空欄）", [0, 0])[i] += 1
    if counts:
        print("\n▼ 都道府県ごとの送信対象")
        for pref, (m, f) in sorted(counts.items(), key=lambda kv: -sum(kv[1])):
            print(f"  {pref}　メール {m} 件 / フォーム {f} 件")
    if args.pref:
        print("\n▼ 会社ごとの状況（メール / フォーム）")
        for lead, mail, form in selector.explain(leads):
            if mail == form:
                print(f"  {lead.label()}\n      送らない：{mail}")
            else:
                print(f"  {lead.label()}\n      メール：{mail}\n      フォーム：{form}")
    if selector.excludes and not args.pref:
        print("\n▼ 送らない会社リスト（exclude.txt）で除外")
        for name, _ in selector.excludes:
            hits = [l for l in leads if selector.excluded_by(l) == name]
            if hits:
                for l in hits:
                    print(f"  {name} → {l.label()}（{l.tab}）")
            else:
                print(f"  ⚠ {name} → 一致する会社が見つかりません（店名の表記を確認してください）")
    for title, items in (("メール", mails), ("フォーム", forms)):
        if items:
            print(f"\n▼ {title}（先頭10件）")
            for lead, target in items[:10]:
                print(f"  {lead.score:>4}点  {lead.label()}  {'（Googleでお店のサイトを探す）' if is_search_url(target) else target}")
    missing = missing_sender_fields(cfg)
    if missing:
        print("\n⚠ config.toml の [sender] に「（要記入）」が残っています: " + ", ".join(missing))


def cmd_preview(cfg, args):
    _, leads, selector = connect(cfg, args)
    messages = render_all(cfg, "mail", selector.email_candidates(leads)[: args.n])
    if not messages:
        print("メール送信の対象がありません。")
    for lead, email, subject, body in messages:
        print("=" * 60)
        print(f"宛先: {email}（{lead.label()}）\n件名: {subject}\n" + "-" * 60 + f"\n{body}")


def cmd_test_mail(cfg, args):
    from salesmailer.mac_mail import MailError, send_mail

    require_sender(cfg)
    _, leads, selector = connect(cfg)
    messages = render_all(cfg, "mail", selector.email_candidates(leads)[:1])
    if not messages:
        sys.exit("文面の見本にする会社がありません。")
    lead, _, subject, body = messages[0]
    try:
        send_mail(args.address, f"[テスト] {subject}", body, cfg["sender"]["email"])
    except MailError as e:
        sys.exit(f"送信に失敗しました: {e}")
    print(f"{args.address} に「{lead.shop_name}」宛ての文面でテスト送信しました。届いたメールを確認してください。")


def cmd_mail(cfg, args):
    from salesmailer.mac_mail import MailError, send_mail

    require_sender(cfg)
    sheet, leads, selector = connect(cfg, args)
    remaining = cfg["mail"]["daily_limit"] - selector.sent_today("メール")
    if args.limit is not None:
        remaining = min(remaining, args.limit)
    if remaining <= 0:
        sys.exit("今日の送信上限に達しています。また明日実行してください。")
    messages = render_all(cfg, "mail", selector.email_candidates(leads)[:remaining])
    if not messages:
        sys.exit("メール送信の対象がありません。")

    low, high = cfg["mail"]["interval_seconds"]
    print(f"\n次の {len(messages)} 件にメールを送信します（1通ごとに {low}〜{high} 秒あけます）。")
    for lead, email, _, _ in messages:
        print(f"  {lead.label()}  {email}")
    if not args.yes and not confirm("送信を始めますか？"):
        return

    errors_in_row = 0
    for i, (lead, email, subject, body) in enumerate(messages, start=1):
        try:
            send_mail(email, subject, body, cfg["sender"]["email"])
        except MailError as e:
            print(f"[{i}/{len(messages)}] ✗ {lead.label()} {email}: {e}")
            sheet.record(lead, "メール", "エラー", email, str(e)[:200])
            errors_in_row += 1
            if errors_in_row >= 3:
                sys.exit("3回続けて失敗したため停止しました。メールアプリの状態を確認してください。")
            continue
        errors_in_row = 0
        sheet.record(lead, "メール", "送信済み", email)
        print(f"[{i}/{len(messages)}] ✓ {lead.label()} {email}")
        if i < len(messages):
            wait = random.randint(low, high)
            print(f"  次の送信まで {wait} 秒待ちます…（中断は Ctrl+C）")
            time.sleep(wait)
    print("\n完了しました。送信結果はスプレッドシートの送信ログタブに記録しています。")


FORM_HELP = "Enter=送信した  s=スキップ  n=営業お断り（今後送らない）  r=今のページに入力し直す  g=Googleで探す  q=終了"


def cmd_form(cfg, args):
    from playwright.sync_api import sync_playwright

    from salesmailer.form_filler import build_values, fill_page, page_warnings
    from salesmailer.selection import search_url

    require_sender(cfg)
    sheet, leads, selector = connect(cfg, args)
    remaining = cfg["form"]["daily_limit"] - selector.sent_today("フォーム")
    if args.limit is not None:
        remaining = min(remaining, args.limit)
    if remaining <= 0:
        sys.exit("今日のフォーム送信の上限に達しています。")
    messages = render_all(cfg, "form", selector.form_candidates(leads))
    if not messages:
        sys.exit("フォーム送信の対象がありません。")
    print(f"\nフォーム送信の対象は {len(messages)} 件です（今日はあと {remaining} 件まで）。")
    print("ブラウザが開いたら、入力内容を確認して自分で送信ボタンを押してください。")
    print("送信したらブラウザは閉じずに、ターミナルに戻ってキーを押してください。")
    print(f"操作: {FORM_HELP}\n")

    sent = 0
    with sync_playwright() as p:
        channel = cfg["form"].get("browser_channel") or None
        browser = page = None

        def live_page():
            """ブラウザのウィンドウやタブが閉じられていたら、開き直す。"""
            nonlocal browser, page
            if browser is None or not browser.is_connected():
                browser = p.chromium.launch(headless=False, channel=channel)
                page = None
            if page is None or page.is_closed():
                page = browser.new_page(viewport={"width": 1200, "height": 900})
            return page

        def open_url(url):
            page = live_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            return page

        for i, (lead, url, subject, body) in enumerate(messages, start=1):
            if sent >= remaining:
                print("今日の上限に達したので終了します。")
                break
            print("=" * 60)
            print(f"[{i}/{len(messages)}] {lead.label()}  {'（公式サイトの登録なし → Googleで検索）' if is_search_url(url) else url}")
            values = build_values(cfg["sender"], subject, body)
            try:
                try:
                    page = open_url(url)
                except Exception:
                    page = open_url(url)  # 閉じられたウィンドウを開き直して、もう一度だけ試す
            except Exception as e:
                print(f"  ✗ ページを開けませんでした（{type(e).__name__}）")
                sheet.record(lead, "フォーム", "エラー", url, "ページを開けない")
                continue

            while True:
                if page.is_closed():
                    print("  ⚠ ブラウザが閉じられていたので開き直しました。")
                    page = open_url(url)
                if is_search_url(page.url):
                    print("  Googleでお店を検索しました。お店の公式サイトを開き、問い合わせページを表示してから r を押してください。")
                    print("  見つからない場合や、問い合わせフォームがない場合は s を押してください。")
                else:
                    for w in page_warnings(page, [lead.shop_name, lead.get("company")]):
                        print(f"  ⚠ {w}")
                    result = fill_page(page, values)
                    if result.filled:
                        print("  入力した項目: " + "、".join(result.filled))
                    else:
                        print("  ⚠ 入力欄が見つかりません。ブラウザで問い合わせページを開いてから r を押してください。")
                    for w in result.warnings:
                        print(f"  ⚠ {w}")
                    print("  ※ 選択肢・チェックボックス・未入力の欄は、ブラウザで直接入力してください。")
                answer = input(f"  {FORM_HELP}\n  > ").strip().lower()
                if answer == "g":
                    try:
                        page = live_page()
                        page.goto(search_url(lead), wait_until="domcontentloaded", timeout=30000)
                    except Exception as e:
                        print(f"  ✗ Google検索を開けませんでした（{type(e).__name__}）")
                    continue
                if answer == "" and not page.is_closed() and is_search_url(page.url):
                    print("  まだGoogle検索のページです。問い合わせページを開いて r、見つからなければ s を押してください。")
                    continue
                if answer != "r":
                    break

            if answer == "q":
                print("終了します。")
                break
            if answer == "s":
                sheet.record(lead, "フォーム", "スキップ", url)
                print("  → スキップとして記録しました")
            elif answer == "n":
                sheet.record(lead, "フォーム", "営業お断り", url)
                print("  → 営業お断りとして記録しました（今後は送りません）")
            else:
                sheet.record(lead, "フォーム", "送信済み", page.url)
                sent += 1
                print("  → 送信済みとして記録しました")
        if browser is not None and browser.is_connected():
            browser.close()
    print(f"\n今回フォームで送信した件数: {sent} 件")


def main():
    parser = argparse.ArgumentParser(description="スプレッドシートの会社リストに営業メール・フォームを送るツール")
    sub = parser.add_subparsers(dest="command", required=True)
    pref_help = "都道府県・地方で絞り込む（例: --pref 宮崎 福岡 / --pref 九州）"
    p = sub.add_parser("check", help="送信対象の件数を確認する")
    p.add_argument("--pref", nargs="+", help=pref_help)
    p = sub.add_parser("preview", help="メール文面を確認する（送信しない）")
    p.add_argument("-n", type=int, default=3, help="表示する件数")
    p.add_argument("--pref", nargs="+", help=pref_help)
    p = sub.add_parser("test-mail", help="自分宛てにテスト送信する")
    p.add_argument("address", help="テストメールの宛先（自分のアドレス）")
    p = sub.add_parser("mail", help="メールを送信する")
    p.add_argument("--limit", type=int, help="今回送る件数の上限")
    p.add_argument("--yes", action="store_true", help="確認を省略して送信を始める")
    p.add_argument("--pref", nargs="+", help=pref_help)
    p = sub.add_parser("form", help="フォームを半自動で入力する")
    p.add_argument("--limit", type=int, help="今回送る件数の上限")
    p.add_argument("--pref", nargs="+", help=pref_help)
    args = parser.parse_args()

    cfg = load_config()
    commands = {"check": cmd_check, "preview": cmd_preview, "test-mail": cmd_test_mail, "mail": cmd_mail, "form": cmd_form}
    try:
        commands[args.command](cfg, args)
    except KeyboardInterrupt:
        print("\n中断しました。ここまでの送信結果は送信ログに記録済みです。")


if __name__ == "__main__":
    main()
