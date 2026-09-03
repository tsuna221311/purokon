/**
 * password_toggle.js — パスワード入力欄に「表示/隠す」トグルボタンを付与する。
 *
 * 実際にログイン・サインアップ・パスワード再設定の画面を動かして確認した
 * 実際のUX上の問題への対応: このアプリのサインアップ・パスワード再設定画面
 * には確認用(2回目入力)のパスワード欄が無く、かつ入力内容を目視確認する
 * 手段(表示切り替え)も無かった。つまり利用者は自分が打った文字列を一度も
 * 見ないまま送信することになり、タイプミスに気付けず、直後のログインで
 * 「自分が設定したはずのパスワードでログインできない」という分かりにくい
 * 詰みに陥りやすい(特に確認用入力欄が無いこのアプリでは、確認欄との
 * 不一致チェックというセーフティネットも効かないため影響が大きい)。
 *
 * サーバー側の値・検証ロジックには一切手を入れず、`type="password"`と
 * `type="text"`を切り替えるだけの純粋な表示上のトグルなので、セキュリティ
 * 上の影響は無い(送信される値は変わらない)。CSP(script-src 'self')の
 * 都合上、インラインscriptではなくこの外部ファイルとして実装している。
 */
(function () {
  function attachToggle(input) {
    if (input.dataset.toggleAttached) return;
    input.dataset.toggleAttached = "1";

    var wrapper = document.createElement("div");
    wrapper.className = "password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "password-toggle-btn";
    btn.textContent = "表示";
    btn.setAttribute("aria-label", "パスワードを表示");
    btn.addEventListener("click", function () {
      var willShow = input.type === "password";
      input.type = willShow ? "text" : "password";
      btn.textContent = willShow ? "隠す" : "表示";
      btn.setAttribute("aria-label", willShow ? "パスワードを隠す" : "パスワードを表示");
    });
    wrapper.appendChild(btn);
  }

  function init() {
    document.querySelectorAll('input[type="password"]').forEach(attachToggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
