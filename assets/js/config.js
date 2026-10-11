/**
 * お問い合わせフォームの送信設定
 * ------------------------------------------------------------
 * formEndpoint に送信先を設定すると、フォームが実際に送信されます。
 * 空のままだと「デモ表示」となり、送信は行われません。
 *
 *   ■ Formspree を使う場合（サーバー不要）
 *     formEndpoint: "https://formspree.io/f/xxxxxxxx"
 *
 *   ■ PHP が動くレンタルサーバーを使う場合（同梱の contact.php）
 *     formEndpoint: "contact.php"
 *     ※ 送信先メールアドレスは contact.php 冒頭で設定します。
 *
 * 詳しくは README.md の「お問い合わせフォームの設定」を参照してください。
 */
window.RDS_CONFIG = {
  formEndpoint: "",

  // 送信エラー時に案内するメールアドレス（任意。空なら表示しません）
  fallbackEmail: ""
};
