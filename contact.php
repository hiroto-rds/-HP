<?php
/**
 * Rデザインスタジオ 営業支援サイト — お問い合わせフォーム送信処理
 * ------------------------------------------------------------
 * PHP が動作するレンタルサーバー（エックスサーバー、さくら、ロリポップ等）で使用します。
 * 使い方：
 *   1. 下の「設定」を書き換える
 *   2. assets/js/config.js の formEndpoint を "contact.php" にする
 *   3. サイト一式をサーバーにアップロードする
 */

/* ===================== 設定 ===================== */

// 問い合わせを受け取るメールアドレス
const MAIL_TO = 'info@r-design.studio.jp';

// 送信元（From）アドレス。迷惑メール判定を避けるため、サイトと同じドメインのアドレスを使用
// 受信用と同じアドレスにしておくと、自動返信への返信や配信エラーも info@ に届きます
const MAIL_FROM = 'info@r-design.studio.jp';
const MAIL_FROM_NAME = 'Rデザインスタジオ 営業支援サイト';

// 送信者へ自動返信メールを送るか
const SEND_AUTO_REPLY = true;

// 受け付けるドメイン（空配列なら制限なし）。公開URLが決まったら設定してください
// 例：['https://r-design.studio.jp', 'https://www.r-design.studio.jp']
const ALLOWED_ORIGINS = [];

// 同じ送信元からの連続送信を制限する秒数
const RATE_LIMIT_SECONDS = 60;

/* ================================================ */

mb_language('uni'); // UTF-8 で送信（ISO-2022-JP で文字化けしやすい記号にも対応）
mb_internal_encoding('UTF-8');
header('Content-Type: application/json; charset=UTF-8');
header('X-Content-Type-Options: nosniff');

function respond(int $status, bool $ok, string $message = ''): void
{
    http_response_code($status);
    echo json_encode(['ok' => $ok, 'message' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    respond(405, false, 'Method Not Allowed');
}

// 送信元ドメインの確認
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if (ALLOWED_ORIGINS && !in_array($origin, ALLOWED_ORIGINS, true)) {
    respond(403, false, '許可されていない送信元です。');
}

// ボット対策（非表示項目に入力があれば、成功したように見せて何もしない）
if (!empty($_POST['_gotcha'])) {
    respond(200, true);
}

/** 入力値を取得し、制御文字を除去して長さを制限する */
function field(string $key, int $max, bool $multiline = false): string
{
    $v = isset($_POST[$key]) && is_string($_POST[$key]) ? $_POST[$key] : '';
    $v = str_replace(["\r\n", "\r"], "\n", $v);
    $v = $multiline
        ? preg_replace('/[^\P{C}\n\t]/u', '', $v)
        : preg_replace('/\p{C}/u', '', $v);
    $v = trim((string) $v);
    return mb_substr($v, 0, $max);
}

$company  = field('company', 100);
$name     = field('name', 60);
$email    = field('email', 254);
$tel      = field('tel', 20);
$topics   = field('topics', 300);
$meeting  = field('meeting', 30);
$business = field('business', 200);
$message  = field('message', 3000, true);
$consent  = field('consent', 20);

// 入力チェック
$errors = [];
if ($company === '')  $errors[] = '会社名・屋号';
if ($name === '')     $errors[] = 'お名前';
if ($email === '' || !filter_var($email, FILTER_VALIDATE_EMAIL)) $errors[] = 'メールアドレス';
if ($tel !== '' && !preg_match('/^[0-9０-９+\-−ー() ]{8,20}$/u', $tel)) $errors[] = '電話番号';
if ($topics === '')   $errors[] = 'ご相談内容';
if ($business === '') $errors[] = '事業内容・商材';
if ($message === '')  $errors[] = '現在の課題・ご相談内容';
if ($consent === '')  $errors[] = '個人情報の取り扱いへの同意';

if ($errors) {
    respond(422, false, '入力内容をご確認ください：' . implode('、', $errors));
}

// 連続送信の制限
$ip = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
$lockFile = sys_get_temp_dir() . '/rds_contact_' . hash('sha256', $ip);
if (is_file($lockFile) && (time() - (int) @filemtime($lockFile)) < RATE_LIMIT_SECONDS) {
    respond(429, false, '短時間に連続して送信されました。しばらくしてから再度お試しください。');
}

// 管理者宛メール
$now = date('Y-m-d H:i');
$body = <<<TXT
営業支援サイトからお問い合わせがありました。

────────────────────
■ 会社名・屋号
{$company}

■ お名前
{$name}

■ メールアドレス
{$email}

■ 電話番号
{$tel}

■ ご相談内容
{$topics}

■ ご希望の打ち合わせ方法
{$meeting}

■ 事業内容・商材
{$business}

■ 現在の課題・ご相談内容
{$message}
────────────────────
送信日時：{$now}
送信元IP：{$ip}
TXT;

$fromHeader = 'From: ' . mb_encode_mimeheader(MAIL_FROM_NAME) . ' <' . MAIL_FROM . '>';
$subject = '【営業支援サイト】' . $company . ' 様よりご相談';
$headers = $fromHeader . "\r\n" . 'Reply-To: ' . $email;

$sent = mb_send_mail(MAIL_TO, $subject, $body, $headers, '-f' . MAIL_FROM);
if (!$sent) {
    respond(500, false, 'メールの送信に失敗しました。');
}

@touch($lockFile);

// 自動返信メール
// （第三者のアドレスへ任意の文章を送る踏み台にされないよう、自由記述欄は本文に含めません）
if (SEND_AUTO_REPLY) {
    $replyBody = <<<TXT
{$company}
{$name} 様

このたびは Rデザインスタジオ 営業支援へお問い合わせいただき、ありがとうございます。
以下の内容でお問い合わせを受け付けました。
内容を確認のうえ、担当よりご連絡いたします。

■ ご相談内容：{$topics}

※ このメールは自動でお送りしています。
※ お心当たりのない場合は、お手数ですが本メールを破棄してください。

Rデザインスタジオ 営業支援
TXT;
    mb_send_mail($email, '【Rデザインスタジオ】お問い合わせを受け付けました', $replyBody, $fromHeader, '-f' . MAIL_FROM);
}

respond(200, true);
