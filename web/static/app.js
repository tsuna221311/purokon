// app.js — PatternForge フロントエンド。フォーム送信とAPI結果の表示だけを担う
// 薄いレイヤー。ロジックはすべてサーバ側(engine/)にある。

// round6で追加: サーバ側にCSRFトークン検証(app.pyの`_csrf_protect`)を
// 導入したことに伴い、フロント側でもトークンを送信する必要がある箇所に対応。
// #generate-formはCSRFトークンをhidden inputとして持っているため
// new FormData(form)で自動的に含まれるが、/api/profiles はJSで手動組み立て
// したFormDataを使っているため、ここで明示的に付与する必要がある。
// トークン自体は各ページの<head>相当(_nav.html)に埋め込まれた
// <meta name="csrf-token">から読み取る。
function _csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

const form = document.getElementById("generate-form");
const illustrationSection = document.getElementById("illustration-section");
const manualSection = document.getElementById("manual-section");
const formError = document.getElementById("form-error");

const placeholder = document.getElementById("result-placeholder");
const loading = document.getElementById("result-loading");
const content = document.getElementById("result-content");
const multiSizeContent = document.getElementById("multi-size-result-content");
const resultPanel = document.getElementById("result-panel");
const submitButton = form ? form.querySelector('button[type="submit"]') : null;
const submitButtonLabel = submitButton ? submitButton.textContent : "";

// 衣装カタログは50件ある。ネイティブselectを残してキーボード操作とフォーム送信
// の互換性を保ちつつ、検索・ジャンル絞り込み・おすすめボタンを上に重ねる。
// サーバー側の値を複製せず、optionのvalue/表示名だけからUIの分類を作る。
const costumeProjectSelect = document.getElementById("costume-project");
const costumeProjectSection = document.getElementById("costume-project-section");
const costumeProjectSearch = document.getElementById("costume-project-search");
const costumeProjectCategory = document.getElementById("costume-project-category");
const costumeProjectSummary = document.getElementById("costume-project-selection-summary");
const referenceModeButton = document.getElementById("switch-to-reference-mode");
const CURATED_PROJECT_KEYS = new Set([
  "endministrator_female", "endministrator_male", "perlica", "chen_qianyu",
  "hatsune_miku_classic", "yor_forger_thorn_princess",
]);

function projectCategoryFor(key, label) {
  const text = `${key} ${label}`.toLowerCase();
  if (CURATED_PROJECT_KEYS.has(key)) return "curated";
  if (text.includes("endministrator") || text.includes("perlica") || text.includes("chen_qianyu")) return "endfield";
  if (text.includes("miku") || text.includes("hololive")) return "music";
  if (text.includes("genshin") || text.includes("hsr") || text.includes("ff7") || text.includes("pokemon")) return "game";
  return "anime";
}

function syncCostumeProjectPicker() {
  if (!costumeProjectSelect) return;
  const query = (costumeProjectSearch?.value || "").trim().toLocaleLowerCase("ja-JP");
  const category = costumeProjectCategory?.value || "all";
  let shown = 0;
  for (const option of costumeProjectSelect.options) {
    if (!option.value) continue;
    const matchesQuery = !query || `${option.text} ${option.value}`.toLocaleLowerCase("ja-JP").includes(query);
    const matchesCategory = category === "all" || projectCategoryFor(option.value, option.text) === category;
    option.hidden = !(matchesQuery && matchesCategory);
    if (!option.hidden) shown += 1;
  }
  const count = document.getElementById("costume-project-count");
  if (count) count.textContent = `${shown}件`;
}

function syncCostumeProjectSummary() {
  if (!costumeProjectSelect || !costumeProjectSummary) return;
  const option = costumeProjectSelect.selectedOptions[0];
  const key = option?.value || "";
  costumeProjectSummary.classList.remove("is-curated", "is-catalog");
  if (!key) {
    costumeProjectSummary.textContent = "未選択です。資料画像から作る場合は、上の「資料画像を使う」を選んでください。";
    return;
  }
  if (CURATED_PROJECT_KEYS.has(key)) {
    costumeProjectSummary.textContent = `「${option.text}」を選択中です。市販セットの構成を照合した個別設計済みプリセットとして、裏地・装飾布・制作チェック項目をセットします。`;
    costumeProjectSummary.classList.add("is-curated");
  } else {
    costumeProjectSummary.textContent = `「${option.text}」を選択中です。型紙エンジンで生成確認済みの検証ベースです。固有の装飾・印刷・立体小物は、生成後の別工程リストで確認してください。`;
    costumeProjectSummary.classList.add("is-catalog");
  }
}

if (costumeProjectSearch) costumeProjectSearch.addEventListener("input", syncCostumeProjectPicker);
if (costumeProjectCategory) costumeProjectCategory.addEventListener("change", syncCostumeProjectPicker);
if (costumeProjectSelect) costumeProjectSelect.addEventListener("change", syncCostumeProjectSummary);
syncCostumeProjectPicker();
syncCostumeProjectSummary();

// round32で直した実バグ: 「型紙を生成する」ボタンはフォームのいちばん下
// (実測でページ先頭から約2300px)にあり、結果パネルは画面のいちばん上に
// 出る。押しても**画面上は何も変わらない**ため、壊れたと思ってもう一度
// 押すと、無料枠(1日3回)を2回使ってしまう。実際にブラウザで操作して
// 発見した。押した瞬間に結果パネルへスクロールし、ボタンを押せなくして
// 「生成中…」に変える。
/**
 * 生成の進み具合を、画面を見ていない人へ伝える(round44)。
 *
 * 【なぜ要るか】この画面は、押したあとに起きることが**全部JSで差し込まれる**。
 * 実測(Playwrightで全ページを調べた結果)、`aria-live` を持つ要素は
 * **1つも無かった**。スクリーンリーダーで使うと、「型紙を生成する」を押しても
 * 生成が始まったことも、終わったことも、失敗したことも読み上げられない——
 * 無言のまま数十秒が過ぎる。WCAG 2.1 SC 4.1.3(Status Messages)。
 *
 * 同じ文字列を続けて入れても読み上げられないブラウザがあるので、
 * 一度空にしてから入れ直す。
 */
function announce(message) {
  const region = document.getElementById("result-status");
  if (!region) return;
  region.textContent = "";
  window.setTimeout(() => { region.textContent = message; }, 30);
}

/* -- 通信の失敗を、日本語の文にして返す (round45) ---------------------------
 *
 * 【round44まで何が起きていたか】この画面のfetchは3か所とも
 *
 *     const data = await response.json();
 *     if (!response.ok || !data.ok) throw new Error(data.error || "…日本語…");
 *
 * と書いてあった。`response.json()` が **ifより先に走る** ので、応答が
 * JSONでなければそこで例外になり、せっかく用意した日本語の文言は
 * **一度も表示されない**。実際にPlaywrightで確かめた画面の文字:
 *
 *     通信が切れたとき      → 「Failed to fetch」
 *     502(HTMLが返る)      → 「Unexpected token '<', "<html><bod"... is not valid JSON」
 *
 * 家庭で服を縫う人に向けた日本語の製品で、失敗したときにだけ英語の
 * パーサのメッセージが出ていた。**日本語の文言が用意してあったのに、
 * それが出る経路が無かった**のが不具合である。
 *
 * ここでは応答を1か所で解く。JSONでなければHTTPの状態から日本語の文を作り、
 * 生の本文は画面に出さない(サーバーの内部事情が漏れるのを防ぐため)。
 */
/* [失敗の文言:ここから] — この印から下は、DOMに触らない純粋な関数だけを置く。
   tests/test_round45_failures.py が、この区間を切り出してNodeで実際に
   走らせ、返ってくる文言を確かめる(文字列を探すだけの検査では、条件を
   `if (false)` に書き換えても通ってしまい、回帰を捕まえられなかった)。 */
const NETWORK_ERROR_MESSAGE =
  "サーバーに接続できませんでした。通信の状態を確かめて、もう一度お試しください。";

function _httpErrorMessage(status, fallback) {
  if (status === 429) return "利用の上限に達しました。";
  if (status === 413) return "送信したデータが大きすぎます。画像の枚数やサイズを減らしてください。";
  if (status >= 500) return `${fallback}（サーバー側の一時的な不具合の可能性があります。HTTP ${status}）`;
  return `${fallback}（HTTP ${status}）`;
}

/** fetchの応答をJSONとして解く。JSONでない応答も日本語の例外にして投げる。 */
async function readJsonOrThrow(response, fallback) {
  let data = null;
  try {
    data = await response.json();
  } catch (parseError) {
    // 502のHTML、空の本文、プロキシのエラーページなど。
    // 生の本文は出さず、状態から文を作る。
    throw new Error(_httpErrorMessage(response.status, fallback));
  }
  if (!response.ok || !data || data.ok === false) {
    const message = (data && data.error) || _httpErrorMessage(response.status, fallback);
    const err = new Error(message);
    if (data && data.upgrade_url) err.upgradeUrl = data.upgrade_url;
    throw err;
  }
  return data;
}

/** fetch自体が投げた例外(通信断・中断)を、日本語の文にする。 */
function describeFetchFailure(err, fallback) {
  if (err && err.name === "AbortError") return err.message || fallback;
  // fetchはネットワーク障害で TypeError("Failed to fetch") を投げる。
  // 画面に出せる日本語を持っていないので、ここで差し替える。
  if (err instanceof TypeError) return NETWORK_ERROR_MESSAGE;
  return (err && err.message) || fallback;
}
/* [失敗の文言:ここまで] */

/* -- 応答が返ってこないときに、操作を取り戻せるようにする (round45) ---------
 *
 * 【round44まで何が起きていたか】fetchに時間の上限が無かった。応答が
 * 返ってこないと(サーバーが詰まる、プロキシが接続を掴んだまま等)、
 * 送信ボタンは「生成中です…」のまま **永久に押せない**。実測で60秒待っても
 * disabled=true のままだった。利用者にできるのは再読み込みだけで、
 * それをすると **入力した採寸値が全部消える**。
 *
 * 【この秒数の根拠】手動モードの生成にかかる実測時間(サーバー側、3回ずつ):
 *
 *     既定              0.44s      裏地つき        0.92s
 *     子ども(身長110)    0.44s      複数サイズ5     0.50s
 *     大柄 B130/H150    0.40s      プロジェクタ     0.48s
 *
 * いちばん遅い経路でも **1秒未満**である。一方イラストモードは外部APIを
 * 呼ぶので、待ち時間は通信と相手側次第になる(そちらはサーバー側で
 * engine/part_classifier.py に上限を置いた)。
 *
 * ここの120秒は**計測値ではなく方針**である。「1秒で終わるはずの処理を
 * 2分待ってまだ返らないなら、待ち続けるより操作を返した方がよい」という
 * 判断で決めた。中断しても入力欄は触っていないので、採寸値は残る。
 */
const GENERATE_TIMEOUT_MS = 120000;
const GENERATE_TIMEOUT_MESSAGE =
  "時間内に応答がありませんでした（2分）。入力した値はそのままです。"
  + "もう一度「型紙を生成する」を押してお試しください。";

function startGenerateTimeout() {
  // AbortSignal.timeout() は古いブラウザに無いので、AbortControllerで組む。
  if (typeof AbortController !== "function") {
    return { signal: undefined, clear: () => {} };
  }
  const controller = new AbortController();
  const id = window.setTimeout(() => {
    // 中断の理由を日本語で持たせる(既定のDOMExceptionは英語のため)。
    controller.abort(new DOMException(GENERATE_TIMEOUT_MESSAGE, "AbortError"));
  }, GENERATE_TIMEOUT_MS);
  return { signal: controller.signal, clear: () => window.clearTimeout(id) };
}

/** 押したあとにフォーカスが迷子にならないよう、行き先へ移す (round47)。
 *
 * 【round46まで何が起きていたか】キーボードで「型紙を生成する」をEnterで
 * 押すと、その瞬間に **フォーカスが <body> へ落ちていた**。
 * `beginGenerating()` がボタンを disabled にするからで、
 * フォーカスを持った要素を無効にすると、ブラウザはフォーカスを
 * 文書へ戻す。実測: 押す前 BUTTON → 150ms後 BODY → 完了後も BODY。
 *
 * マウスでは気づかないが、キーボードだけで使うと現在地が消える。
 * スクリーンリーダーでは読み上げの起点が文書の先頭に戻るので、
 * 出来上がった型紙にたどり着くまで、ヘッダーからやり直すことになる。
 *
 * `preventScroll: true` にするのは、直後に `scrollResultIntoView()` が
 * 位置を決めるため。ここでブラウザに勝手に寄せられると二重に動く。
 */
function moveFocusTo(element) {
  if (!element || typeof element.focus !== "function") return;
  try {
    element.focus({ preventScroll: true });
  } catch (e) {
    element.focus();
  }
}

function beginGenerating() {
  // フォーカスを先に逃がしてから無効にする(順番が逆だと、無効にした
  // 瞬間にブラウザが <body> へ落としてしまう)。
  const heading = document.getElementById("result-heading");
  if (submitButton && document.activeElement === submitButton) {
    moveFocusTo(heading);
  }
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "生成中です…";
  }
  announce("型紙を生成しています。しばらくお待ちください。");
  // round34: 結果パネルは広い画面で position:sticky + 自前のスクロールに
  // なった。前回の結果を見て下までスクロールした状態で再生成すると、
  // パネルの中は下にスクロールしたままで、新しい結果の先頭
  // (「用意する生地」)が見えない。中身を先頭へ戻す。
  if (resultPanel) resultPanel.scrollTop = 0;
  scrollResultIntoView();
}

/** 結果(または生成中の表示)が見える位置まで画面を動かす。 */
function scrollResultIntoView() {
  if (resultPanel) {
    // 動きが苦手な人の設定(prefers-reduced-motion)を尊重する。
    const smooth = !window.matchMedia
      || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // round34: 結果パネルは広い画面で position:sticky になった。
    // sticky で貼り付いている要素に scrollIntoView を使うと、**すでに
    // 画面内にある**と判断されて何も起きず、下までスクロールした状態の
    // まま結果の先頭(「用意する生地」)が親の終端で切れて見えない。
    // 貼り付かない親(.layout)の位置を基準にスクロールする。
    //
    // round46: ただし **これは2段組のときだけ正しい**。
    // 狭い画面(768px以下)では .layout は1段組になり、その先頭は
    // 結果パネルではなく**フォームの先頭**である。実際に測ったところ:
    //
    //   390px幅で、ボタン(y=3681)まで下げて「型紙を生成する」を押すと、
    //   1.5秒後には scrollY=117 ——**画面のほぼ最上部**まで戻され、
    //   出来上がった結果は 4190px 下にあって**まったく見えない**。
    //
    // 押したのに何も起きていないように見える、といういちばん困る形だった。
    // 貼り付いているときだけ親を基準にし、そうでなければ結果パネル自身
    // (=1段組では結果の先頭)へ寄せる。
    const sticky = window.getComputedStyle(resultPanel).position === "sticky";
    const anchor = (sticky && resultPanel.parentElement) || resultPanel;
    const top = anchor.getBoundingClientRect().top + window.scrollY - 16;
    window.scrollTo({ top: Math.max(0, top), behavior: smooth ? "smooth" : "auto" });
  }
}

function endGenerating() {
  if (submitButton) {
    submitButton.disabled = false;
    submitButton.textContent = submitButtonLabel;
  }
}

const illustrationFileInput = illustrationSection.querySelector('input[name="illustration"]');
// round34: 袖の形は<select>からサムネイルのラジオになった。値の読み取りと
// 変更の監視だけが必要なので、「選ばれている袖の形」を返す小さな関数と、
// 「変わったら呼ぶ」の登録に置き換える(選び方のUIが変わっても、ここから
// 先の判定は同じままにするため)。
const sleeveStyleInputs = manualSection.querySelectorAll('input[name="sleeve_style"]');

function selectedSleeveStyle() {
  const checked = manualSection.querySelector('input[name="sleeve_style"]:checked');
  return checked ? checked.value : "";
}
const includeCuffsInput = document.getElementById("include-cuffs-input");
const multiSizeSection = document.getElementById("multi-size-section");
// round10で追加: カスタムパーツ(自由形状パーツ)セクションは、現状バックエンド
// (app.pyの`/api/generate`)がイラストモード・サイズ展開モードとの併用に
// 未対応(明確なエラーを返す設計、README参照)のため、手動モードでのみ表示する。
const customPanelSection = document.getElementById("custom-panel-section");

// round25で追加: ゆとりを「数値で指定する」を選んだときだけ入力欄を出す。
// 隠している間は入力欄を無効化して送信データに含めない(disabledな要素は
// FormDataに入らないので、隠したまま古い値が送られる事故を防げる)。
const fitSelect = document.getElementById("fit");
const blockSelect = document.getElementById("block");
const customEaseFields = document.getElementById("custom-ease-fields");
// round30: 「伸びる生地」を選んだときだけ、伸縮率の入力欄を出す。
// 隠している入力は disabled にして送信データから外す（そうしないと、
// 選んでいない方式の入力値が一緒に送られてしまう）。
const stretchFields = document.getElementById("stretch-fields");
const stretchHint = document.getElementById("stretch-hint");

/**
 * ゆとりの選択肢の表示を、選ばれている原型に合わせて書き換える(round42)。
 *
 * 【なぜ要るか】round41まで「標準（身頃 バスト+8.0cm）」と**絶対値**を
 * 書いていた。round42で原型ごとに標準ゆとりが変わった(子ども原型は
 * バスト/4=バスト60で15cm)ので、この表示は子どもを選ぶと**嘘になる**。
 *
 * 数字をJS側で計算し直すことはしない(エンジンの式を2か所に持つと必ず
 * 食い違う)。原型が持っている式の文字列(data-ease-text)と、プリセットの
 * 標準からの増減(data-fit-delta)を並べて出すだけにしてある。
 * 実際に使われた値は、生成後に「この型紙の作り方」へ数字で出る。
 */
function syncFitLabels() {
  if (!fitSelect || !blockSelect) return;
  const block = blockSelect.selectedOptions[0];
  const easeText = block ? block.dataset.easeText : "";
  const isDefaultAbsolute = easeText && !easeText.includes("/");
  fitSelect.querySelectorAll("option[data-fit-label]").forEach((option) => {
    const label = option.dataset.fitLabel;
    if (isDefaultAbsolute) {
      // 定数の原型(大人)は、これまでどおり絶対値で書ける。
      option.textContent = `${label}（身頃 バスト+${option.dataset.fitAbs}cm）`;
      return;
    }
    const delta = Number(option.dataset.fitDelta);
    const shift = delta === 0
      ? "そのまま"
      : `${delta > 0 ? "+" : "−"}${Math.abs(delta)}cm`;
    option.textContent = `${label}（身頃 ${easeText} ${shift}）`;
  });
}

function syncCustomEaseFields() {
  if (!fitSelect || !customEaseFields) return;
  const useCustom = fitSelect.value === "custom";
  customEaseFields.classList.toggle("hidden", !useCustom);
  customEaseFields.querySelectorAll("input").forEach((input) => {
    input.disabled = !useCustom;
  });
  const useStretch = fitSelect.value === "stretch";
  if (stretchFields) {
    stretchFields.classList.toggle("hidden", !useStretch);
    stretchFields.querySelectorAll("input").forEach((input) => {
      input.disabled = !useStretch;
    });
  }
  if (stretchHint) stretchHint.classList.toggle("hidden", !useStretch);
}
if (fitSelect) {
  fitSelect.addEventListener("change", syncCustomEaseFields);
  syncCustomEaseFields();
}
if (blockSelect) {
  blockSelect.addEventListener("change", syncFitLabels);
  syncFitLabels();
}

// チェックボックスと「バリエーション選択」を1組にした4項目(パンツ/衿/
// カフス/ウエストバンド)。チェックが入っていない間はselectを無効化して
// 送信データに含めない（ブラウザはdisabledなフォーム要素をFormDataに
// 含めないため、include_*=falseのままstyleだけ送られる事故を防げる）。
const OPTION_WITH_STYLE_IDS = [
  ["include-pants-input", "field-pants-style"],
  ["include-collar-input", "field-collar-style"],
  ["include-cuffs-input", "field-cuffs-style"],
  ["include-waistband-input", "field-waistband-style"],
];

function syncOptionStyleSelects() {
  OPTION_WITH_STYLE_IDS.forEach(([checkboxId, selectId]) => {
    const checkbox = document.getElementById(checkboxId);
    const select = document.getElementById(selectId);
    if (!checkbox || !select) return;
    select.disabled = !checkbox.checked;
  });
}

OPTION_WITH_STYLE_IDS.forEach(([checkboxId]) => {
  const checkbox = document.getElementById(checkboxId);
  if (checkbox) checkbox.addEventListener("change", syncOptionStyleSelects);
});
syncOptionStyleSelects();

function setMode(mode) {
  const isIllustration = mode === "illustration";
  const isMultiSize = mode === "multi_size";
  const isManual = mode === "manual";
  illustrationSection.classList.toggle("hidden", !isIllustration);
  // 「③ パーツ構成」(ネックライン・袖等の選択)は、手動モードだけでなく
  // サイズ展開モードでも同じ構成を使う(サイズ展開は「同じデザインを複数
  // サイズ分まとめて作る」機能なので、パーツ構成の選び方自体は変わらない)。
  manualSection.classList.toggle("hidden", isIllustration);
  multiSizeSection.classList.toggle("hidden", !isMultiSize);
  // 衣装プリセットは採寸を使う手動生成専用。イラスト／サイズ展開では入力欄を
  // 隠して送信対象から外すことで、選択だけ残ってサーバーに400を返される
  // 「見えない矛盾」を防ぐ。手動へ戻れば選択はそのまま復元される。
  if (costumeProjectSection) costumeProjectSection.classList.toggle("hidden", !isManual);
  [costumeProjectSelect, costumeProjectSearch, costumeProjectCategory]
    .filter(Boolean)
    .forEach((input) => { input.disabled = !isManual; });
  // round10で追加: カスタムパーツは手動モードのみ対応(上のコメント参照)。
  if (customPanelSection) {
    customPanelSection.classList.toggle("hidden", !isManual);
  }
  // round49はここで裏地の節をサイズ展開モードだけ隠していた。サーバの
  // generate_multi_size が lining を受け取らず、チェックしても黙って
  // 無視されていたためで、「押せるのに効かない」を無くす回避だった。
  // round58でサーバ側に渡るようにしたので、隠す理由が無くなった
  // (裏地付きの衣装をS/M/Lでまとめて作れる)。
  // 隠していた頃の「隠すときはチェックを外す」も、もう要らない。
  // イラストモードなのに画像を選ばず送信すると、サーバはエラーを返すが
  // (app.py側で明確な400エラーに修正済み)、ブラウザの標準フォーム検証で
  // 送信前に気付けるようにしておく方が体験として良い。
  illustrationFileInput.required = isIllustration;
  // イラストモードでは「③ パーツ構成」の見出しごと非表示になるため、
  // 直後の見出しが固定の番号のままだと表示中の見出しの並びと食い違って
  // 見える(実際に画面を見て確認して壊れて見えた不具合の再発防止)。
  syncStepNumbers();
}

//: 任意セクションの番号(①②③…)。
const CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮";

/**
 * 任意セクションの見出し番号を、**いま画面に出ている順**で振り直す(round41)。
 *
 * 【round40まで何が壊れていたか】番号はモードごとに手書きの三項演算子で
 * 決めていた("⑤"か"④"か)。round40で「⑥ 着てみて合わなかったら」を
 * 割り込ませたとき、HTML側の縫い代を⑦へ書き換えたのに、このJS側は
 * "⑥"のままだった。初回表示はHTMLの⑦が出るので気付かないが、
 * **モードを切り替えて手動に戻すと**JSが上書きして、⑥が2つ並ぶ。
 * round41で裏地(⑦)を足せば3つ目のずれになる。
 *
 * 番号を手で管理するのをやめる。DOMの順に、表示されている任意セクションを
 * 数えて振り直す——セクションを足しても、この関数もHTMLの初期値も
 * 直さなくてよい(初期値はJSが上書きするまでの一瞬しか見えない)。
 */
function syncStepNumbers() {
  // 常に出ている固定の見出しは「① 入力モード」「② 採寸値」の2つ。
  // 「③ パーツ構成」(manualSection)はイラストモードで消える。
  let n = 2;
  if (manualSection && !manualSection.classList.contains("hidden")) n += 1;
  form.querySelectorAll(".optional-step").forEach((el) => {
    const section = el.closest("details");
    if (section && section.classList.contains("hidden")) return;
    n += 1;
    el.textContent = CIRCLED_NUMBERS[n - 1] || String(n);
  });
}

// 袖を「なし（ノースリーブ）」にした場合、カフスは追加できない
// (engine/pipeline.py の build_garment_spec が明確なエラーを返すように
// 修正済みだが、そもそも矛盾した組み合わせを選べないようにする方が親切)。
function syncCuffsAvailability() {
  const hasSleeve = selectedSleeveStyle() !== "";
  includeCuffsInput.disabled = !hasSleeve;
  if (!hasSleeve) {
    includeCuffsInput.checked = false;
  }
  // includeCuffsInput.checked をJSから直接変更した場合は"change"イベントが
  // 発火しないため、カフスのバリエーション選択(select)の有効/無効が
  // 追随しない。ここで明示的に同期させる。
  syncOptionStyleSelects();
}

form.querySelectorAll('input[name="mode"]').forEach((el) => {
  el.addEventListener("change", (e) => setMode(e.target.value));
});
if (referenceModeButton) {
  referenceModeButton.addEventListener("click", () => {
    const illustrationMode = form.querySelector('input[name="mode"][value="illustration"]');
    if (!illustrationMode) return;
    illustrationMode.checked = true;
    setMode("illustration");
    illustrationSection.scrollIntoView({ behavior: "smooth", block: "start" });
    illustrationFileInput.focus({ preventScroll: true });
  });
}
setMode(form.querySelector('input[name="mode"]:checked')?.value || "manual");

for (const input of sleeveStyleInputs) {
  input.addEventListener("change", syncCuffsAvailability);
}
syncCuffsAvailability();

function showError(message, upgradeUrl) {
  formError.textContent = message;
  if (upgradeUrl) {
    formError.appendChild(document.createTextNode(" "));
    const link = document.createElement("a");
    link.href = upgradeUrl;
    link.textContent = "料金ページを見る";
    formError.appendChild(link);
  }
  formError.classList.remove("hidden");
}

function clearError() {
  formError.classList.add("hidden");
  formError.textContent = "";
}

function formatPercent(ratio) {
  return `${Math.round(ratio * 1000) / 10}%`;
}

// td/spanの内容はサーバ側で固定の許可リスト(part_type/variation等)に検証
// 済みだが、将来自由入力欄が増えたときに無自覚なXSSにならないよう、
// innerHTMLへの文字列埋め込みではなく createElement + textContent で
// DOMを組み立てる（テンプレートリテラルによるHTML注入を避ける）。
// round9で追加: AIパーツ判定ログ表がpart_type/variationの内部識別子
// (例: "round_neck")をそのまま日本語UIに表示していた実バグの修正。
// ラベル辞書はindex.html側の#classification-sectionのdata-*属性(サーバー
// 側labels.pyをJSON化したもの)から読む。CSPのscript-src 'self'により
// インラインscriptでは値を渡せないため、非実行属性であるdata-*経由にした
// (labels.pyのモジュールdocstring参照)。要素/属性が無い場合や不正なJSONの
// 場合も例外にせず、素通し(識別子そのまま表示)にフォールバックする。
function _parseLabelDict(datasetValue) {
  if (!datasetValue) return {};
  try {
    return JSON.parse(datasetValue) || {};
  } catch (e) {
    return {};
  }
}

const _classificationSectionEl = document.getElementById("classification-section");
const VARIATION_LABELS_JA = _parseLabelDict(_classificationSectionEl && _classificationSectionEl.dataset.variationLabels);
const PART_TYPE_LABELS_JA = _parseLabelDict(_classificationSectionEl && _classificationSectionEl.dataset.partTypeLabels);

function _variationLabel(variation) {
  if (!variation) return "—";
  return Object.prototype.hasOwnProperty.call(VARIATION_LABELS_JA, variation)
    ? VARIATION_LABELS_JA[variation]
    : variation;
}

function _partTypeLabel(partType) {
  if (!partType) return "—";
  return Object.prototype.hasOwnProperty.call(PART_TYPE_LABELS_JA, partType)
    ? PART_TYPE_LABELS_JA[partType]
    : partType;
}

function _cell(text) {
  const td = document.createElement("td");
  td.className = "p-2";
  td.textContent = text;
  return td;
}

function renderClassificationLog(rows) {
  const section = document.getElementById("classification-section");
  const tbody = document.getElementById("classification-tbody");
  tbody.innerHTML = "";
  if (!rows || rows.length === 0) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.className = "border-t border-stone-100";
    const isMock = row.mode === "mock";

    const modeCell = document.createElement("td");
    modeCell.className = "p-2";
    const pill = document.createElement("span");
    pill.className = `mode-pill ${isMock ? "mock" : "claude"}`;
    pill.textContent = isMock ? "簡易判定(モック)" : "Claude API";
    modeCell.appendChild(pill);

    tr.appendChild(_cell(_partTypeLabel(row.part_type)));
    tr.appendChild(_cell(_variationLabel(row.variation)));
    tr.appendChild(_cell(row.confidence));
    tr.appendChild(modeCell);
    tbody.appendChild(tr);
  }
}

function renderPartsList(parts) {
  const list = document.getElementById("parts-chip-list");
  list.innerHTML = "";
  for (const part of parts || []) {
    const chip = document.createElement("div");
    chip.className = "part-chip";

    const name = document.createElement("span");
    name.className = "part-chip-name";
    name.textContent = part.display_name;

    const size = document.createElement("span");
    size.className = "part-chip-size";
    size.textContent = `${part.width_cm} × ${part.height_cm} cm`;

    chip.appendChild(name);
    chip.appendChild(size);
    // round32: 裁ち方の指示(表地/枚数/わ裁ち/接着芯)。型紙そのものにも
    // 印字しているが、裁つ前に一覧で見えると「接着芯が要るパーツはどれか」
    // をまとめて確認できる。
    if (part.cutting_note) {
      const note = document.createElement("span");
      note.className = "part-chip-note";
      note.textContent = part.cutting_note;
      chip.appendChild(note);
    }
    list.appendChild(chip);
  }
}

// round34: 「布を何m買えばいいか」を先頭に出す。
//
// round33までの結果画面の先頭は パーツ数/布ロス率/使用生地丈/生地幅/
// 処理時間/配置不能パーツ という6つの数値タイルで、**処理時間のような
// エンジン側の指標**が、買い物に必要な「幅○cmの生地を△m」と同じ大きさで
// 並んでいた。作る人がいちばん最初に知りたいのは、店で何を頼むかである。
//
// 端数は必ず切り上げる。10cm単位に丸めた上で切り上げるのは、生地が
// 10cm単位で売られることが多いため。足りない方向へ丸めてはいけない
// (足りなければ作れない。多い分は残るだけ)。
const FABRIC_ROUND_UP_CM = 10;

function renderPdfSheetCount(data) {
  // round53: A4分割PDFが何枚になるかを、ダウンロードする前に出す。
  //
  // コンビニで印刷する人にはこれがそのまま値段(1枚あたり数十円)と
  // 待ち時間になり、家のプリンタなら「紙が足りるか」の判断になる。
  // 枚数はサーバがPDFを作るのと同じ関数から出した数字をそのまま使う
  // (画面側で割り算し直すと、白紙を省いたぶんずれる)。
  const hint = document.getElementById("pdf-sheet-hint");
  if (!hint) return;
  const sheets = Number(data.pdf_sheet_count);
  if (!Number.isFinite(sheets) || sheets <= 0) {
    hint.textContent = "";
    return;
  }
  // round57: 用紙(A4/A3)を選べるようになったので、どちらの枚数かを書く。
  const paper = data.paper || "A4";
  hint.textContent = `${paper}分割PDFは、実寸の型紙が${sheets}枚と、`
    + "貼り合わせ図・買い物メモ・縫う順番のページが付きます"
    + "（型紙の載らない面は省いてあります）。";
}

// round65: ダーツが「どのパーツに」入ったかを、実際のパーツから書く。
//
// round64まで、この文はHTMLに手書きしてあった——
//   「身頃のウエスト/脇ダーツ、タイトスカートのウエストダーツなど」
// 14通りで実測すると、この文が出る11通りのうち10通りで、挙げたパーツに
// ダーツは1本も入っていなかった(標準体型ではタイトスカートにも入らない。
// パンツに8本入っても文はパンツに触れない)。ダーツはV字の切り込みなので、
// 「どこを探すか」を間違えると裁つ前の確認そのものが空振りする。
//
// 縫う順番(engine/assembly.py)は最初から dart_count から作っていた。
// 画面も同じ出どころ(data.darts_by_part)から作る。
function renderDartNote(data) {
  const box = document.getElementById("dart-note");
  const list = document.getElementById("dart-note-list");
  if (!box || !list) return;
  const byPart = Array.isArray(data.darts_by_part) ? data.darts_by_part : [];
  const total = Number(data.darts_applied) || 0;
  box.classList.toggle("hidden", total === 0 || byPart.length === 0);
  document.getElementById("dart-count").textContent = total;
  list.innerHTML = "";
  for (const row of byPart) {
    const li = document.createElement("li");
    li.textContent = `${row.name} — ${row.dart_count}本`;
    list.appendChild(li);
  }
}

function renderFabricNeed(data) {
  const widthEl = document.getElementById("need-width");
  const lengthEl = document.getElementById("need-length");
  const subEl = document.getElementById("need-sub");
  if (!widthEl || !lengthEl) return;

  const usedCm = Number(data.used_length_cm) || 0;
  const buyCm = Math.ceil(usedCm / FABRIC_ROUND_UP_CM) * FABRIC_ROUND_UP_CM;
  widthEl.textContent = data.fabric_width_cm;
  lengthEl.textContent = (buyCm / 100).toFixed(1);

  const parts = [`型紙が実際に使うのは ${usedCm}cm で、`
                  + `生地が${FABRIC_ROUND_UP_CM}cm単位で売られることを見込んで`
                  + `${buyCm}cm に切り上げています。`];
  if (data.rotation_used) {
    parts.push("一部のパーツを90度回転して詰めた配置です。");
  }
  // round35: 分割が起きたことを、この一番上の箱でも触れておく。
  //
  // 【なぜここか】分割の詳しい説明は下の「この型紙の作り方」に出るが、
  // 1440pxで実際に開いて確かめたところ、その箱はプレビュー画像より下に
  // あり、結果パネル(sticky・overflow:auto)の中をスクロールしないと
  // 見えなかった。分割は**裁つ枚数が変わる**話なので、生地の必要量を
  // 読んでいるこの場所で先に一言触れて、下を見に行く動機を作る。
  const splitCounts = data.split_panels || {};
  const splitTypes = Object.keys(splitCounts);
  if (splitTypes.length > 0) {
    const maxPanels = Math.max(...splitTypes.map((k) => splitCounts[k]));
    parts.push(`生地幅に収まらないパーツがあるため、${maxPanels}枚に分けて裁つ型紙に`
                + "なっています(縫い合わせ方は下の「この型紙の作り方」に書いています)。");
  }
  parts.push("地直し(水通し)で縮む生地は、その分を足して購入してください。");
  subEl.textContent = parts.join("");
}

// round38: 買い物メモ。
//
// 【なぜ幅ごとに並べるか】round37まで画面には「幅150cm の生地を 2.6m」と
// **エンジンが選んだ1つの幅だけ**が出ていた。他の幅の必要量は内部で
// 計算しているのに捨てていたので、近所の店に110cm幅しか置いていない人は
// 自分で換算するしかなかった。実測すると幅と必要丈は比例しない
// (パーツが横に2枚並ぶかどうかで段が変わる)ので、換算のしようもない。
// round39: 手持ちの生地で足りるかの判定。
//
// 【なぜ「足りません」だけで終わらせないか】round38で幅ごとの必要量は
// 出るようになったが、足りないと分かったあとが行き止まりだった。何をどれだけ
// 変えれば入るのかは、利用者が構成をいじって何度も生成し直すしかない。
// ここに出す提案は**推定ではなく**、実際にその丈で型紙を作り直して
// ネスティングし、入ることを確かめた結果である(engine/stash.py)。
// round70: 状態の色は、CSSのトークン(--warn-fg など)を持つクラスで付ける。
//
// round69まで、ここは `el.style.color = "#92400e"` のように**16進を直接**
// 書いていた。画面の地色がOSの設定で暗くなると、その文字色だけが明るい
// 画面向けのまま取り残される(実測: 暗い画面で濃い茶色の文字が濃い地に
// 乗り、読めなかった)。クラスにすると、地・枠・文字の3色がいつも揃う。
const NOTE_TONES = ["note-info", "note-warn", "note-danger",
                    "note-success", "note-plan"];

function setNoteTone(el, tone) {
  if (!el) return;
  for (const name of NOTE_TONES) el.classList.remove(name);
  if (tone) el.classList.add("note-" + tone);
}

function renderStashVerdict(data) {
  const box = document.getElementById("stash-verdict");
  if (!box) return;
  const verdict = data.stash_verdict;
  if (!verdict) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");

  const headline = document.getElementById("stash-headline");
  const detail = document.getElementById("stash-detail");
  const list = document.getElementById("stash-suggestions");
  list.innerHTML = "";

  const have = `幅${verdict.have_width_cm}cm × ${verdict.have_length_cm}cm`;

  // round55: 生地を分けているときは、**生地ごとに**答える。
  //
  // 手持ちの端切れは1種類の生地なので、全パーツ合計の長さで答えると
  // 「白い身頃＋紺のスカート」の紺だけを持っている人に
  // 「117cm足りません」と言ってしまう(紺のぶんは124cmで、実際には
  // 130cmの手持ちに収まっていた)。持っている生地を使わせ損ねる。
  const byFabric = data.stash_verdicts_by_fabric;
  if (byFabric && byFabric.length > 1) {
    const anyShort = byFabric.some((v) => !v.fits);
    setNoteTone(box, anyShort ? "warn" : "success");
    // round57: 生地ごとに違う寸法を入れられるようになったので、
    // 見出しに1つの寸法を書くと嘘になる。寸法は各行に書く。
    const sizes = new Set(byFabric.map((v) => `${v.have_width_cm}x${v.have_length_cm}`));
    headline.textContent = anyShort
      ? "手持ちの生地で足りない生地があります"
      : "✓ 手持ちの生地は、どの生地のぶんにも足ります";
    detail.textContent = sizes.size > 1
      ? "生地ごとに、入力した手持ちの寸法で見ています。"
      : `手持ちの1枚（${have}）は1種類の生地なので、生地ごとに見ています。`;
    for (const item of byFabric) {
      const li = document.createElement("li");
      const own = `幅${item.have_width_cm}cm×${item.have_length_cm}cm`;
      li.textContent = item.fits
        ? `${item.fabric_name}（${own}）: 要${item.needed_length_cm}cm → 足ります（${item.leftover_cm}cm余り）`
        : (item.all_parts_fit
            // round59: 買い足す量は10cm単位で言う(裁断台で頼める数字)。
            ? `${item.fabric_name}（${own}）: 要${item.needed_length_cm}cm → あと${item.buy_more_cm}cm要ります`
            : `${item.fabric_name}（${own}）: 幅が足りません（長さの問題ではありません）`);
      list.appendChild(li);
    }
    return;
  }

  if (verdict.fits) {
    setNoteTone(box, "success");
    headline.textContent = `✓ 手持ちの生地（${have}）で作れます`;
    // round59: **どの幅で測ったか**を書く。すぐ下の「用意する生地」の箱は
    // 推奨幅(例: 140cm)で測った別の数字を出しているので、幅を書かないと
    // 2つの数字が矛盾して見える(実測: 手持ち110cmで248.8cm / 推奨140cmで
    // 181.6cm が同じ画面に並んでいた)。
    detail.textContent =
      `幅${verdict.have_width_cm}cmで裁つと${verdict.needed_length_cm}cm要るので、`
      + `${verdict.leftover_cm}cm余ります。`;
    return;
  }

  setNoteTone(box, "warn");
  headline.textContent = `手持ちの生地（${have}）では足りません`;
  if (!verdict.all_parts_fit) {
    // 幅が足りない場合は不足cmを出さない。長さの話ではないので、
    // 数字を出すと「その分足せば作れる」と読めてしまう。
    detail.textContent = (verdict.notes || [])[0] || "";
    return;
  }
  // round59: 幅を書き、不足は**店で頼める量**(10cm単位)で出す。
  // 「98.8cm足りません」は裁断台では使えない数字だった。
  // 端数(98.8cm)も残す——切り上げた100cmだけだと、なぜ100なのか分からない。
  detail.textContent =
    `幅${verdict.have_width_cm}cmで裁つと${verdict.needed_length_cm}cm要るので、`
    + `あと${verdict.buy_more_cm}cm要ります`
    + `（不足${verdict.shortfall_cm}cmを、切り売りの10cm単位に`
    + `切り上げた値です）。`;

  // round59: 注記(「手持ちに収める道は無かった」)を先に、逃げ道を後に置く。
  // 逆だと、提案を読んだあとで「収まりませんでした」が来て、
  // 提案が否定されたように読める。事情 → 選べる道、の順にする。
  for (const note of verdict.notes || []) {
    const li = document.createElement("li");
    li.textContent = note;
    list.appendChild(li);
  }
  for (const suggestion of verdict.suggestions || []) {
    const li = document.createElement("li");
    li.style.marginBottom = "4px";
    const label = document.createElement("strong");
    label.textContent = suggestion.label;
    li.appendChild(label);
    li.appendChild(document.createTextNode(" — " + suggestion.detail));
    list.appendChild(li);
  }
}

/**
 * round41: 裏地の型紙。表地とは**別の生地**なので、必要量もダウンロードも
 * 表地とは別の箱に出す(足し合わせると買う単位にならない)。
 *
 * 裏地を付けずに生成した場合、`data.lining`はnullで、この箱ごと隠れる。
 */

// round57: 手持ち生地の欄を、⑨で入力した生地の名前ごとに出す。
//
// round55で判定は生地ごとになったが、寸法は1枚ぶんしか受け取れなかった。
// 「白を2m、紺を1m持っている」というふつうの状態が入れられず、
// 同じ1枚の寸法を全部の生地に当てて答えていた。
function refreshStashPerFabricRows() {
  const box = document.getElementById("stash-per-fabric");
  const rows = document.getElementById("stash-per-fabric-rows");
  if (!box || !rows || !form) return;
  const names = [];
  for (const input of form.querySelectorAll('input[name^="fabric_"]')) {
    const value = (input.value || "").trim();
    if (value && !names.includes(value)) names.push(value);
  }
  // 既定の生地(名前を書かなかったパーツの行き先)も対象にする。
  const defaultName = box.dataset.defaultFabric || "表地";
  if (names.length && !names.includes(defaultName)) names.unshift(defaultName);

  box.classList.toggle("hidden", names.length < 2);
  const previous = new Map();
  for (const row of rows.querySelectorAll("[data-fabric-row]")) {
    previous.set(row.dataset.fabricRow, [
      row.querySelector('[name="stash_fabric_width_cm"]').value,
      row.querySelector('[name="stash_fabric_length_cm"]').value,
    ]);
  }
  rows.textContent = "";
  if (names.length < 2) return;
  for (const name of names) {
    const row = document.createElement("div");
    row.className = "grid-measurements";
    row.dataset.fabricRow = name;
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "stash_fabric_name";
    hidden.value = name;
    row.appendChild(hidden);
    const kept = previous.get(name) || ["", ""];
    const fields = [
      ["stash_fabric_width_cm", `${name} の幅 (cm)`, "例: 110", kept[0]],
      ["stash_fabric_length_cm", `${name} の長さ (cm)`, "例: 130", kept[1]],
    ];
    for (const [fieldName, labelText, placeholder, value] of fields) {
      const field = document.createElement("div");
      field.className = "field";
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("input");
      input.type = "number";
      input.step = "1";
      input.name = fieldName;
      input.placeholder = placeholder;
      // 画面のラベルと**同じ文言**で読み上げ名も付ける(round47の約束)。
      // 違う文言にすると、見えている名前と読み上げがずれる
      // (WCAG 2.5.3 Label in Name)。
      input.setAttribute("aria-label", labelText);
      input.value = value;
      const id = `field-${fieldName}-${encodeURIComponent(name)}`;
      input.id = id;
      label.htmlFor = id;
      field.append(label, input);
      row.appendChild(field);
    }
    rows.appendChild(row);
  }
}

if (form) {
  for (const input of form.querySelectorAll('input[name^="fabric_"]')) {
    input.addEventListener("input", refreshStashPerFabricRows);
    input.addEventListener("change", refreshStashPerFabricRows);
  }
  refreshStashPerFabricRows();
}

function renderFabricGroups(data) {
  // round54: 生地を分けたときは、生地ごとに1ブロックずつ出す。
  //
  // 上のダウンロード行(#download-pdf など)は**1種類目の生地**のものなので、
  // 2種類以上に分かれたときにそのまま出しておくと、どの生地の型紙なのかが
  // 分からないまま押すことになる。分かれたときは隠して、こちらに寄せる。
  const box = document.getElementById("fabric-groups-box");
  const list = document.getElementById("fabric-group-list");
  const mainRow = document.querySelector(".download-row");
  if (!box || !list) return;

  const groups = data.fabric_groups;
  box.classList.toggle("hidden", !groups || groups.length < 2);
  if (mainRow) mainRow.classList.toggle("hidden", Boolean(groups && groups.length >= 2));
  const sheetHint = document.getElementById("pdf-sheet-hint");
  if (sheetHint && groups && groups.length >= 2) sheetHint.textContent = "";
  list.textContent = "";
  if (!groups || groups.length < 2) return;

  document.getElementById("fabric-group-count").textContent = String(groups.length);
  // round57: 生地ごとの章を1本にまとめたPDF。コンビニで印刷する人は、
  // 2色なら2ファイル送ることになっていた(round54の積み残し)。
  const combined = data.download && data.download.all_fabrics_pdf;
  if (combined) {
    const row = document.createElement("div");
    row.className = "download-row";
    row.style.margin = "0 0 10px";
    const anchor = document.createElement("a");
    anchor.href = combined;
    anchor.className = "btn-solid";
    anchor.textContent = "全部の生地をまとめた1本のPDF";
    row.appendChild(anchor);
    const note = document.createElement("p");
    note.className = "hint";
    note.style.margin = "4px 0 0";
    note.textContent = "生地ごとの章に分かれた1つのファイルです"
      + "（コンビニで1回の印刷で済ませたい場合はこちら）。";
    list.appendChild(row);
    list.appendChild(note);
  }
  for (const group of groups) {
    const block = document.createElement("div");
    block.className = "field-box";
    block.style.margin = "0 0 10px";

    const title = document.createElement("p");
    title.className = "hint";
    title.style.cssText = "margin:0 0 4px; font-weight:600;";
    title.textContent = `${group.name}（${group.part_labels.join("・")}）`;
    block.appendChild(title);

    const need = document.createElement("p");
    need.className = "hint";
    need.style.margin = "0 0 8px";
    const buyCm = Math.ceil((Number(group.used_length_cm) || 0) / FABRIC_ROUND_UP_CM)
                  * FABRIC_ROUND_UP_CM;
    need.textContent =
      `幅${group.fabric_width_cm}cm の生地を ${(buyCm / 100).toFixed(1)}m`
      + `（実際に使うのは ${group.used_length_cm}cm）／`
      + `A4分割PDFは実寸の型紙が${group.pdf_sheet_count}枚`;
    block.appendChild(need);

    const row = document.createElement("div");
    row.className = "download-row";
    row.style.margin = "0";
    // 1種類目のファイルは接頭辞なし、2種類目以降は fabric2_ ... と付く
    // (サーバ側の `_DOWNLOAD_FORMATS` と対応。engine側が output_files に
    //  同じ鍵で入れている)。
    const prefix = group.index === 0 ? "" : `fabric${group.index + 1}_`;
    const links = [
      [`${prefix}pdf`, "A4分割PDF", "btn-solid"],
      [`${prefix}svg`, "SVGを開く", "btn-outline"],
      [`${prefix}dxf`, "DXF", "btn-outline"],
      [`${prefix}projector`, "プロジェクター投影用PDF", "btn-outline"],
    ];
    for (const [key, label, cls] of links) {
      const href = data.download && data.download[key];
      if (!href) continue;   // 出ていない形式のリンクは作らない(押して404にしない)
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.className = cls;
      anchor.textContent = `${group.name}の${label}`;
      if (key.endsWith("svg")) anchor.target = "_blank";
      row.appendChild(anchor);
    }
    block.appendChild(row);
    list.appendChild(block);
  }
}

function renderLining(data) {
  const box = document.getElementById("lining-box");
  if (!box) return;
  const lining = data.lining;
  box.classList.toggle("hidden", !lining);
  if (!lining) return;

  document.getElementById("lining-part-count").textContent = lining.part_count;
  const need = document.getElementById("lining-need");
  if (lining.used_length_cm != null && lining.fabric_width_cm != null) {
    need.textContent =
      `幅${lining.fabric_width_cm}cm の裏地を ${(lining.used_length_cm / 100).toFixed(2)}m`
      + `（実際に並べ直した実測。表地の必要量とは別に買ってください）`;
  } else {
    need.textContent = "";
  }

  const cacheBust = `?t=${Date.now()}`;
  const links = {
    "download-lining-pdf": data.download && data.download.lining_pdf,
    "download-lining-svg": data.download && data.download.lining_svg,
    "download-lining-dxf": data.download && data.download.lining_dxf,
    "download-lining-projector": data.download && data.download.lining_projector,
  };
  for (const [id, href] of Object.entries(links)) {
    const el = document.getElementById(id);
    if (!el) continue;
    // 応答に無いリンクは隠す——押せるのに404になる方が分かりにくい。
    el.classList.toggle("hidden", !href);
    if (href) el.href = href + cacheBust;
  }

  const list = document.getElementById("lining-notes");
  list.innerHTML = "";
  for (const note of lining.notes || []) {
    const li = document.createElement("li");
    li.textContent = note;
    list.appendChild(li);
  }
}

/**
 * 生地幅ごとの見積もりの表を組み立てる(round38の中身をround41で関数に出した)。
 *
 * 表地と裏地で**まったく同じ形の表**を出すため。裏地は表地とは別の生地
 * なので、行を混ぜずに表ごと分ける(混ぜると、どの行を足せば買う量になるのか
 * 読めなくなる)。
 */
function fillWidthTable(table, widths, recommendedWidthCm) {
  table.innerHTML = "";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["生地幅", "買う長さ", "実際に使う長さ", "布ロス率"]) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = document.createElement("tbody");
  for (const width of widths) {
    const tr = document.createElement("tr");
    const recommended = width.width_cm === recommendedWidthCm;
    if (recommended) tr.className = "is-recommended";

    const nameCell = document.createElement("td");
    nameCell.textContent = `幅${width.width_cm}cm`;
    if (recommended) {
      const badge = document.createElement("span");
      badge.className = "shopping-badge";
      // 狭い画面では表が横に伸びすぎるので、文言を短くする。
      // (表自体はスクロールできる入れ物に入れてあるが、短い方が読みやすい。)
      badge.textContent = window.innerWidth < 480 ? "← 最短" : "← いちばん短く済みます";
      nameCell.appendChild(badge);
    }
    tr.appendChild(nameCell);

    const buyCell = document.createElement("td");
    if (width.all_parts_fit) {
      buyCell.textContent = `${(width.buy_length_cm / 100).toFixed(1)}m`;
    } else {
      // 収まらない幅は長さを出さない。出すと「その長さを買えば作れる」と
      // 読めてしまうが、実際にはその幅では作れない。
      buyCell.textContent = "この幅では収まりません";
      buyCell.className = "shopping-nofit";
    }
    tr.appendChild(buyCell);

    const usedCell = document.createElement("td");
    usedCell.textContent = width.all_parts_fit ? `${width.used_length_cm}cm` : "—";
    tr.appendChild(usedCell);

    const wasteCell = document.createElement("td");
    wasteCell.textContent = width.all_parts_fit ? formatPercent(width.waste_ratio) : "—";
    tr.appendChild(wasteCell);

    body.appendChild(tr);
  }
  table.appendChild(body);
}

function renderShoppingList(data) {
  const box = document.getElementById("shopping-list");
  if (!box) return;
  const memo = data.shopping_list;
  if (!memo || !Array.isArray(memo.widths) || memo.widths.length === 0) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");

  fillWidthTable(document.getElementById("shopping-width-table"),
                 memo.widths, memo.recommended_width_cm);

  // round41: 裏地(別の生地)。付けていない生成では表ごと隠す。
  const liningWrap = document.getElementById("shopping-lining-wrap");
  const liningWidths = Array.isArray(memo.lining_widths) ? memo.lining_widths : [];
  if (liningWrap) {
    liningWrap.classList.toggle("hidden", liningWidths.length === 0);
    if (liningWidths.length > 0) {
      fillWidthTable(document.getElementById("shopping-lining-table"),
                     liningWidths, memo.lining_recommended_width_cm);
    }
  }

  const interfacing = document.getElementById("shopping-interfacing");
  if (memo.interfacing_length_cm > 0) {
    interfacing.textContent =
      `接着芯: 幅${memo.interfacing_width_cm}cm を ${memo.interfacing_length_cm}cm`
      + "（接着芯が要るパーツだけを、芯地の幅で並べ直して測った長さです）";
    interfacing.classList.remove("hidden");
  } else {
    interfacing.textContent = "接着芯: この構成では要りません";
  }

  // round68: ファスナー。数字は engine/fabric.py が持っている値をそのまま
  // 出す(丸め直さない。同じ数字が2つの丸めで出ると、どちらが正かが
  // 分からなくなる——round61と同じ形)。
  const zipper = document.getElementById("shopping-zipper");
  if (zipper) {
    const opening = Number(memo.front_opening_cm);
    if (Number.isFinite(opening) && opening > 0) {
      zipper.textContent =
        `ファスナー: 前中心の開き ${opening.toFixed(1)}cm`
        + "（これ以上の長さのものを選びます。下の注記に、長さの数え方と"
        + "詰め方を出典付きで書いてあります）";
      zipper.classList.remove("hidden");
    } else {
      zipper.textContent = "";
      zipper.classList.add("hidden");
    }
  }

  const notes = document.getElementById("shopping-notes");
  notes.innerHTML = "";
  for (const message of memo.notes || []) {
    const li = document.createElement("li");
    li.textContent = message;
    notes.appendChild(li);
  }

  const suggestions = document.getElementById("shopping-suggestions");
  suggestions.innerHTML = "";
  if ((memo.suggestions || []).length > 0) {
    const heading = document.createElement("p");
    heading.className = "hint hint-info";
    heading.style.cssText = "margin:0 0 6px; font-weight:600;";
    heading.textContent = "向いている生地";
    suggestions.appendChild(heading);
    for (const item of memo.suggestions) {
      const p = document.createElement("p");
      p.className = "shopping-suggestion";
      const name = document.createElement("span");
      name.className = "shopping-part";
      name.textContent = `${item.part_label}: `;
      p.appendChild(name);
      p.appendChild(document.createTextNode(item.text));
      // 出典は必ず添える。どこから来た助言なのかが分からないと、
      // 利用者は自分で確かめようがない。
      const source = document.createElement("span");
      source.className = "shopping-source";
      source.appendChild(document.createTextNode(" 出典: "));
      const link = document.createElement("a");
      link.href = item.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = item.source_name;
      source.appendChild(link);
      p.appendChild(source);
      suggestions.appendChild(p);
    }
  }
}

function renderAssemblySteps(steps) {
  const box = document.getElementById("assembly-steps");
  const list = document.getElementById("assembly-steps-list");
  const count = document.getElementById("assembly-step-count");
  if (!box || !list) return;
  const items = Array.isArray(steps) ? steps : [];
  box.classList.toggle("hidden", items.length === 0);
  count.textContent = items.length;
  list.innerHTML = "";
  for (const step of items) {
    const li = document.createElement("li");
    li.className = "assembly-step";

    const title = document.createElement("div");
    title.className = "assembly-step-title";
    title.textContent = step.title;
    li.appendChild(title);

    const detail = document.createElement("div");
    detail.className = "assembly-step-detail";
    detail.textContent = step.detail;
    li.appendChild(detail);

    if (Array.isArray(step.parts) && step.parts.length) {
      const parts = document.createElement("div");
      parts.className = "assembly-step-parts";
      parts.textContent = `使うパーツ: ${step.parts.join("・")}`;
      li.appendChild(parts);
    }
    list.appendChild(li);
  }
}

/**
 * サイズ展開の1サイズぶんのダウンロードリンクを組み立てる(round58)。
 *
 * 【round57まで何が起きていたか】ここは SVG/PDF/DXF の**3本が直書き**
 * されていた。裏地を引けば`lining_pdf`が、生地を分ければ
 * `fabric2_pdf`・`all_fabrics_pdf`が、プロジェクター投影用は
 * `projector`が、それぞれサーバから返っているのに、画面には出ない。
 * 実測(S/M・裏地あり・生地2種類): サイズごとに13本のリンクが返って
 * いて、押せるのは3本だった。残りはZIPを展開するか、URLを当てるしか
 * 手が無い——**生地を分ける機能はround55からサイズ展開で動いていた**
 * ので、その間ずっと2色目の型紙は画面から取れなかった。
 *
 * 返ってきた鍵だけからリンクを作る(無い形式は作らない=押して404にしない)。
 */
function downloadLinksForSize(result) {
  const download = result.download || {};
  const links = [];
  const add = (key, label, cls, newTab) => {
    if (download[key]) links.push([label, download[key], cls, Boolean(newTab)]);
  };
  const groups = Array.isArray(result.fabric_groups) ? result.fabric_groups : [];
  const split = groups.length >= 2;

  // 生地を分けていないときは、これまでと同じ並びのまま。
  if (!split) {
    add("pdf", "PDF", "btn-outline");
    add("svg", "SVGを開く", "btn-outline", true);
    add("dxf", "DXF", "btn-outline");
    add("projector", "プロジェクター投影用PDF", "btn-outline");
  } else {
    add("all_fabrics_pdf", "全部の生地をまとめた1本のPDF", "btn-solid");
    for (const group of groups) {
      const prefix = group.index === 0 ? "" : `fabric${group.index + 1}_`;
      add(`${prefix}pdf`, `${group.name}のPDF`, "btn-outline");
      add(`${prefix}svg`, `${group.name}のSVG`, "btn-outline", true);
      add(`${prefix}dxf`, `${group.name}のDXF`, "btn-outline");
      add(`${prefix}projector`, `${group.name}の投影用PDF`, "btn-outline");
    }
  }
  // 裏地は表地とは別の生地なので、いつでも別立てにする(round41と同じ扱い)。
  add("lining_pdf", "裏地のPDF", "btn-outline");
  add("lining_svg", "裏地のSVG", "btn-outline", true);
  add("lining_dxf", "裏地のDXF", "btn-outline");
  add("lining_projector", "裏地の投影用PDF", "btn-outline");
  return links;
}

// round69: 全サイズを合わせた「何枚刷るか・何を買うか」。
//
// サイズ展開を使うのは、同じ衣装を何人ぶんか作る人である。round68まで
// 画面に出ていたのはサイズごとのパーツ数・布ロス率・生地丈だけで、
// **全部で何枚刷るのか**(実測: S/M/Lで143枚)も、**合わせて生地を
// 何m買うのか**も、接着芯もファスナーもどこにも出ていなかった。
//
// 数字はエンジン(MultiSizeResult.totals)が出したものをそのまま並べる。
// ここで足し算し直さない。
function renderMultiSizeTotals(totals) {
  const box = document.getElementById("multi-size-totals");
  const list = document.getElementById("multi-size-totals-list");
  const caveat = document.getElementById("multi-size-totals-caveat");
  if (!box || !list || !caveat) return;
  list.innerHTML = "";
  if (!totals || !totals.size_count) {
    box.classList.add("hidden");
    return;
  }
  const lines = [];
  const width = totals.fabric_recommended_width_cm;
  const length = totals.fabric_recommended_length_cm;
  if (width && length) {
    lines.push(`表地: 幅${width}cm を ${(length / 100).toFixed(1)}m`
               + `（${totals.size_count}サイズ合わせて）`);
  } else if (totals.no_width_fits_every_size) {
    // 足りない数字を出すより、出せないと言う。
    lines.push("表地: 全サイズが収まる生地幅がありませんでした"
               + "（下のサイズごとの欄と、各サイズのPDFの買い物メモを"
               + "見てください）。");
  }
  if (totals.interfacing_length_cm > 0) {
    lines.push(`接着芯: 幅${totals.interfacing_width_cm}cm を `
               + `${totals.interfacing_length_cm}cm`);
  }
  const zippers = Array.isArray(totals.zippers) ? totals.zippers : [];
  if (zippers.length > 0) {
    const each = zippers
      .map((z) => `${z.size} ${Number(z.opening_cm).toFixed(1)}cm`)
      .join(" / ");
    lines.push(`ファスナー: ${zippers.length}本（開き寸法は ${each}）`);
  }
  if (totals.pdf_sheet_count > 0) {
    lines.push(`印刷: ${totals.paper || "A4"}で ${totals.pdf_sheet_count}枚`
               + "（実寸の型紙のページ。貼り合わせ図などは別に付きます）");
  }
  for (const text of lines) {
    const li = document.createElement("li");
    li.className = "hint";
    li.textContent = text;
    list.appendChild(li);
  }
  // 足し算の前提を隠さない。サイズをまたいだ詰め合わせはしていない。
  caveat.textContent =
    "生地の長さは、サイズごとに別々に裁つ前提で足した値です"
    + "（1枚の布に全サイズを詰め合わせ直した値ではありません）。"
    + "幅は、合計がいちばん短くなるものを選んでいます"
    + "（サイズごとのおすすめ幅とは違うことがあります）。";
  box.classList.toggle("hidden", lines.length === 0);
}


function renderMultiSizeResults(data) {
  const cacheBust = `?t=${Date.now()}`;
  document.getElementById("download-zip").href = data.download.zip + cacheBust;

  const sizes = data.sizes || [];
  document.getElementById("multi-size-summary").textContent =
    `${sizes.join("・")} の ${sizes.length}サイズ分を生成しました。`;

  // round7で追加。カスタムグレーディングルールを使った場合、既定値と
  // 黙って違う結果になっていることに気づけるよう明示する。
  const customGradeNote = document.getElementById("custom-grade-note");
  if (data.custom_grade_cm_applied) {
    const grade = data.grade_cm_used || {};
    const labels = {
      bust: "バスト", waist: "ウエスト", hip: "ヒップ",
      height: "身長", sleeve_length: "袖丈", shoulder_width: "肩幅",
    };
    const parts = Object.keys(labels).map((key) => `${labels[key]}${grade[key]}cm`);
    customGradeNote.textContent = `カスタムグレーディングルールを使用しました(${parts.join("・")})。`;
    customGradeNote.classList.remove("hidden");
  } else {
    customGradeNote.classList.add("hidden");
  }

  const sizeConsistencyWarnings = Array.isArray(data.size_consistency_warnings) ? data.size_consistency_warnings : [];
  const sizeConsistencyBox = document.getElementById("size-consistency-warning");
  const sizeConsistencyList = document.getElementById("size-consistency-warning-list");
  sizeConsistencyBox.classList.toggle("hidden", sizeConsistencyWarnings.length === 0);
  sizeConsistencyList.innerHTML = "";
  for (const message of sizeConsistencyWarnings) {
    const li = document.createElement("li");
    li.textContent = message;
    sizeConsistencyList.appendChild(li);
  }

  // round49: 「このモードではやらなかったこと」を出す。
  // サイズ展開で裏地をチェックしていた場合が該当する(以前は黙って無視)。
  const multiNotes = Array.isArray(data.design_notes) ? data.design_notes : [];
  const multiNoteBox = document.getElementById("multi-size-note");
  const multiNoteList = document.getElementById("multi-size-note-list");
  if (multiNoteBox && multiNoteList) {
    multiNoteList.innerHTML = "";
    for (const message of multiNotes) {
      const li = document.createElement("li");
      li.textContent = message;
      multiNoteList.appendChild(li);
    }
    multiNoteBox.classList.toggle("hidden", multiNotes.length === 0);
  }

  const gradingPrecisionNotes = Array.isArray(data.grading_precision_notes) ? data.grading_precision_notes : [];
  const gradingPrecisionBox = document.getElementById("grading-precision-note");
  const gradingPrecisionList = document.getElementById("grading-precision-note-list");
  gradingPrecisionBox.classList.toggle("hidden", gradingPrecisionNotes.length === 0);
  gradingPrecisionList.innerHTML = "";
  for (const message of gradingPrecisionNotes) {
    const li = document.createElement("li");
    li.textContent = message;
    gradingPrecisionList.appendChild(li);
  }

  renderMultiSizeTotals(data.totals);

  const list = document.getElementById("multi-size-list");
  list.innerHTML = "";
  for (const size of sizes) {
    const result = (data.results || {})[size];
    if (!result) continue;

    const box = document.createElement("div");
    box.className = "field-box";

    const heading = document.createElement("h3");
    heading.style.margin = "0 0 6px";
    heading.textContent = `サイズ ${size}`;
    box.appendChild(heading);

    const stats = document.createElement("p");
    stats.className = "hint";
    stats.style.margin = "0 0 8px";
    const buyCm = Math.ceil((Number(result.used_length_cm) || 0) / FABRIC_ROUND_UP_CM)
                  * FABRIC_ROUND_UP_CM;
    // round69: 印刷枚数を足した。コンビニで刷る人にはそのまま代金と
    // 待ち時間になる数字で、単一サイズの画面ではround53から出している
    // のに、**サイズ展開だけ出ていなかった**(3サイズで実測143枚)。
    const sheets = Number(result.pdf_sheet_count);
    const sheetText = Number.isFinite(sheets) && sheets > 0
      ? ` / ${result.paper || "A4"}で${sheets}枚` : "";
    stats.textContent =
      `パーツ数 ${result.part_count} / 布ロス率 ${formatPercent(result.waste_ratio)} / ` +
      `幅${result.fabric_width_cm}cm の生地を ${(buyCm / 100).toFixed(1)}m` + sheetText;
    box.appendChild(stats);

    // round36: サイズごとの警告・注記を、単一サイズと同じ強さで出す。
    //
    // 【何が起きていたか】ここは`result.summary()`をそのまま受け取っており、
    // 採寸クランプ警告・未配置警告・分割の開示は**全部届いていた**。
    // それなのに描いていたのはパーツ数と布ロス率だけで、残りを捨てていた。
    // 実測(バスト100/ウエスト90/ヒップ138、M・L・XL)では、XLだけ
    //   - ヒップ146cmが変形可能範囲を超え、145.6cm相当に丸められている
    //   - スカートが生地幅に収まらず2枚に分割されている
    // という状態だったが、画面には「パーツ数 6」(M・Lは4)としか出ず、
    // なぜ増えたのかも、型紙が採寸どおりでないことも分からなかった。
    // 単一サイズなら赤い箱で強調している内容である。サイズ展開は
    // **大きいサイズほどこれらに当たりやすい**ので、ここで落とすのが一番痛い。
    const noteGroups = [
      ["measurement_warnings", "⚠ 縫う前に確認してください", "danger"],
      ["unplaced_warnings", "⚠ 型紙が不完全です", "danger"],
      ["design_notes", "この型紙の作り方", "info"],
    ];
    for (const [key, heading, tone] of noteGroups) {
      const messages = Array.isArray(result[key]) ? result[key] : [];
      if (messages.length === 0) continue;
      const note = document.createElement("div");
      note.className = "field-box";
      setNoteTone(note, tone);
      note.style.margin = "0 0 8px";
      const title = document.createElement("p");
      title.className = "hint note-title";
      title.textContent = heading;
      note.appendChild(title);
      const ul = document.createElement("ul");
      for (const message of messages) {
        const li = document.createElement("li");
        li.className = "hint";
        li.textContent = message;
        ul.appendChild(li);
      }
      note.appendChild(ul);
      box.appendChild(note);
    }

    const compatWarnings = Array.isArray(result.compatibility_warnings) ? result.compatibility_warnings : [];
    if (compatWarnings.length > 0) {
      const compatNote = document.createElement("p");
      compatNote.className = "hint hint-warn";
      compatNote.style.margin = "0 0 8px";
      compatNote.textContent = "⚠ " + compatWarnings.map((w) => w.message).join(" ");
      box.appendChild(compatNote);
    }

    // round58: 手持ちの生地で足りるかを、サイズごとに1行で出す。
    //
    // 【round57まで何が起きていたか】手持ちの欄はどのモードでも出ている
    // のに、判定していたのは手動モードだけだった。サイズ展開では
    // `stash_verdict` が null で返り、画面にも何も出ない——入れた値が
    // どこへ行ったのか分からないまま消えていた。
    // S/M/Lを1枚の端切れから取れるかは、まさにここで知りたいことである。
    const stash = result.stash_verdict;
    if (stash) {
      const byFabric = Array.isArray(result.stash_verdicts_by_fabric)
        ? result.stash_verdicts_by_fabric : [];
      const line = document.createElement("p");
      line.className = "hint";
      line.style.margin = "0 0 8px";
      if (byFabric.length > 1) {
        const short = byFabric.filter((v) => !v.fits);
        line.className = "hint " + (short.length ? "hint-warn" : "hint-success");
        line.textContent = short.length
          ? "手持ちの生地: " + short.map((v) => `${v.fabric_name}があと${v.buy_more_cm}cm要ります`).join("／")
          : "✓ 手持ちの生地は、どの生地のぶんにも足ります";
      } else if (stash.fits) {
        line.className = "hint hint-success";
        line.textContent =
          `✓ 手持ちの生地（幅${stash.have_width_cm}cm×${stash.have_length_cm}cm）で作れます`
          + `（要${stash.needed_length_cm}cm・${stash.leftover_cm}cm余り）`;
      } else {
        line.className = "hint hint-warn";
        line.textContent = stash.all_parts_fit
          ? `手持ちの生地（幅${stash.have_width_cm}cm×${stash.have_length_cm}cm）では`
            + `あと${stash.buy_more_cm}cm要ります（幅${stash.have_width_cm}cmで裁つと`
            + `${stash.needed_length_cm}cm）`
          : `手持ちの生地は幅が足りません（長さの問題ではありません）`;
      }
      box.appendChild(line);
    }

    const row = document.createElement("div");
    row.className = "download-row";
    const links = downloadLinksForSize(result);
    for (const [label, href, cls, openInNewTab] of links) {
      const a = document.createElement("a");
      a.href = href + cacheBust;
      a.className = cls;
      a.textContent = label;
      if (openInNewTab) a.target = "_blank";
      row.appendChild(a);
    }
    box.appendChild(row);
    list.appendChild(box);
  }
}

function updateUsageNote(usage) {
  if (!usage) return;
  const el = document.getElementById("usage-note-text");
  if (!el) return;
  const planLabel = usage.plan === "pro" ? "Pro" : usage.plan === "free" ? "Free会員" : "未ログイン";
  const limitLabel = usage.daily_limit === null || usage.daily_limit === undefined ? "無制限" : usage.daily_limit;
  el.textContent = `${usage.used_today} / ${limitLabel}（${planLabel}）`;
}

function renderCompareBars(usedLength, naiveLength) {
  const maxLength = Math.max(usedLength, naiveLength, 0.01);
  document.getElementById("bar-naive").style.width = `${(naiveLength / maxLength) * 100}%`;
  document.getElementById("bar-actual").style.width = `${(usedLength / maxLength) * 100}%`;
  document.getElementById("compare-naive-value").textContent = `${naiveLength} cm`;
  document.getElementById("compare-actual-value").textContent = `${usedLength} cm`;
}

// ---------------------------------------------------------------------------
// round10で追加: カスタムパーツ(自由形状パーツ)の輪郭トレースUI。
//
// 「アニメ画像からのコスプレ生成やラフイラストからの舞台衣装など定型的な
// デザインがないものも型紙生成できるようにしてほしい」という要望に対応する
// engine/custom_panel.py・app.pyの/api/custom-panel/trace・/api/generateの
// custom_panels_json処理と対になるフロントエンド。1つの<canvas>に、
// (a) アップロード画像を自動抽出した輪郭の下敷きとして表示し、
// (b) クリックで頂点を追加、既存の頂点/参照点はドラッグで調整、
// という2つの入力方法を組み合わせられるようにしている
// (round10のAskUserQuestion「自動抽出＋手動調整の両方」の回答に対応)。
// ---------------------------------------------------------------------------

const CUSTOM_PANEL_MEASUREMENT_FIELDS = [
  ["bust", "バスト"], ["waist", "ウエスト"], ["hip", "ヒップ"],
  ["height", "身長"], ["sleeve_length", "袖丈"], ["shoulder_width", "肩幅"],
];
// 画像を読み込んだ際、キャンバスの内部描画バッファ(=座標系)の最大辺(px)。
// 校正(calibrate_points_to_cm)は参照線1本の実寸を基準にした一様スケーリング
// のため、この値を変えても最終的なcm換算結果には影響しない
// (見た目の解像度・操作のしやすさ・処理コストのトレードオフのみに影響する)。
const CUSTOM_PANEL_MAX_CANVAS_DIMENSION = 640;
// 画像未読込(手動トレースのみ)の場合の既定キャンバスサイズ。
const CUSTOM_PANEL_DEFAULT_CANVAS_SIZE = 480;
// 既存の頂点・参照点をクリック/タップした際に「ドラッグ開始」とみなす
// 当たり判定半径(表示px。キャンバスの表示縮小率に応じて内部座標系の値に変換する)。
const CUSTOM_PANEL_POINT_HIT_RADIUS = 10;
// engine/custom_panel.pyのMAX_CUSTOM_PANELS_PER_REQUESTと合わせた目安値。
// 実際の上限判定はサーバー側(app.py `_parse_custom_panels`)で行われるため、
// これはUI上で早期に気づかせるための目安に過ぎない。
const CUSTOM_PANEL_MAX_PANELS_CLIENT = 12;
// engine/custom_panel.py の MIN/MAX_CUSTOM_PANEL_DIMENSION_CM と対の値。
// 送信前に画面側で寸法を表示・判定するためだけに使う(実際の検証はサーバー側)。
const CUSTOM_PANEL_MIN_DIMENSION_CM = 2.0;
const CUSTOM_PANEL_MAX_DIMENSION_CM = 300.0;
// engine/custom_panel.py の MIN_REFERENCE_PIXEL_DISTANCE と対の値。
const CUSTOM_PANEL_MIN_REFERENCE_PIXEL_DISTANCE = 2.0;

// 縫い代と採寸値は、カスタムパーツの実寸予告(裁断寸法・採寸基準の校正)にも
// 効くため、これらを変更したときも予告表示を更新する(round11)。
function wireCustomPanelSizeDependencies() {
  const ids = ["field-seam-allowance"].concat(
    CUSTOM_PANEL_MEASUREMENT_FIELDS.map(([f]) => `field-${f}`));
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", () => customPanels.forEach(updateCustomPanelSizePreview));
  });
}

const customPanelListEl = document.getElementById("custom-panel-list");
const addCustomPanelBtn = document.getElementById("add-custom-panel-btn");
const customPanelsJsonInput = document.getElementById("custom-panels-json-input");

let customPanelIdCounter = 0;
/** @type {Array<object>} 各要素は1つのカスタムパーツカードの状態。 */
const customPanels = [];

function _toolButton(text) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn-outline custom-panel-tool-btn";
  b.textContent = text;
  return b;
}

function setPanelStatus(panel, message, isError) {
  panel.els.status.textContent = message;
  panel.els.status.classList.toggle("error-text", !!isError);
}

function syncAddCustomPanelButton() {
  if (!addCustomPanelBtn) return;
  const atLimit = customPanels.length >= CUSTOM_PANEL_MAX_PANELS_CLIENT;
  addCustomPanelBtn.disabled = atLimit;
  addCustomPanelBtn.textContent = atLimit
    ? `カスタムパーツを追加（1リクエストあたり上限${CUSTOM_PANEL_MAX_PANELS_CLIENT}個に達しました）`
    : "＋ カスタムパーツを追加";
}

// panel.points/refA/refBはすべて「キャンバスの内部描画バッファ」座標系
// (canvas.width/heightのピクセル)で保持する。画像読み込み時はその画像の
// 表示スケールに合わせてこの座標系ごと決め直す(handleAutoTrace参照)ため、
// 1つのパーツの中では常に単一の座標系に統一されている。
function redrawPanel(panel) {
  const ctx = panel.ctx;
  const w = panel.canvas.width;
  const h = panel.canvas.height;
  ctx.clearRect(0, 0, w, h);

  if (panel.img) {
    ctx.drawImage(panel.img, 0, 0, w, h);
  } else {
    ctx.fillStyle = "#faf9f6";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#e7e2d9";
    ctx.lineWidth = 1;
    const grid = 40;
    for (let x = 0; x <= w; x += grid) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    for (let y = 0; y <= h; y += grid) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
  }

  if (panel.points.length > 0) {
    ctx.beginPath();
    panel.points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p[0], p[1]);
      else ctx.lineTo(p[0], p[1]);
    });
    if (panel.points.length >= 3) ctx.closePath();
    ctx.strokeStyle = "#1e293b";
    ctx.lineWidth = 2;
    ctx.stroke();
    if (panel.points.length >= 3) {
      ctx.fillStyle = "rgba(30,41,59,0.15)";
      ctx.fill();
    }
    panel.points.forEach((p, i) => {
      ctx.beginPath();
      ctx.arc(p[0], p[1], 6, 0, Math.PI * 2);
      ctx.fillStyle = "#1e293b";
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(i + 1), p[0], p[1]);
    });
  }

  const drawRefHandle = (pt, color, label) => {
    ctx.beginPath();
    ctx.arc(pt[0], pt[1], 7, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#fff";
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, pt[0], pt[1]);
  };
  if (panel.refA && panel.refB) {
    ctx.beginPath();
    ctx.setLineDash([6, 4]);
    ctx.moveTo(panel.refA[0], panel.refA[1]);
    ctx.lineTo(panel.refB[0], panel.refB[1]);
    ctx.strokeStyle = "#16a34a";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.setLineDash([]);
  }
  if (panel.refA) drawRefHandle(panel.refA, "#dc2626", "A");
  if (panel.refB) drawRefHandle(panel.refB, "#2563eb", "B");
}

function canvasPointFromEvent(panel, evt) {
  const rect = panel.canvas.getBoundingClientRect();
  const scaleX = panel.canvas.width / rect.width;
  const scaleY = panel.canvas.height / rect.height;
  const x = (evt.clientX - rect.left) * scaleX;
  const y = (evt.clientY - rect.top) * scaleY;
  return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
}

function findNearestHandle(panel, pt) {
  const rect = panel.canvas.getBoundingClientRect();
  const scale = panel.canvas.width / rect.width;
  const radius = CUSTOM_PANEL_POINT_HIT_RADIUS * scale;
  let best = null;
  let bestDist = radius;
  panel.points.forEach((p, i) => {
    const d = Math.hypot(p[0] - pt[0], p[1] - pt[1]);
    if (d <= bestDist) { bestDist = d; best = { kind: "point", index: i }; }
  });
  if (panel.refA) {
    const d = Math.hypot(panel.refA[0] - pt[0], panel.refA[1] - pt[1]);
    if (d <= bestDist) { bestDist = d; best = { kind: "refA" }; }
  }
  if (panel.refB) {
    const d = Math.hypot(panel.refB[0] - pt[0], panel.refB[1] - pt[1]);
    if (d <= bestDist) { bestDist = d; best = { kind: "refB" }; }
  }
  return best;
}

// 校正後の実寸(cm)を、送信前に画面側で計算する。
//
// engine/custom_panel.py の calibrate_points_to_cm と同じ計算
// (参照線の実寸 ÷ 参照線のピクセル長 を全点に一様に掛ける)をそのまま
// 再現している。サーバー側が唯一の正であることは変わらないが、
// 「送信して初めて『小さすぎます/大きすぎます』と怒られる」「意図した
// 寸法になっているか裁つまで分からない」という状態を避けるための予告表示。
// 計算できない場合(点や参照線が未指定など)は理由付きで null を返す。
function computeCustomPanelSizeCm(panel) {
  if (!panel.refA || !panel.refB) return { error: "参照点A・Bを指定すると実寸を表示します" };
  if (panel.points.length < 3) return { error: "頂点を3つ以上置くと実寸を表示します" };

  const refPx = Math.hypot(panel.refB[0] - panel.refA[0], panel.refB[1] - panel.refA[1]);
  if (refPx < CUSTOM_PANEL_MIN_REFERENCE_PIXEL_DISTANCE) {
    return { error: "参照点A・Bが近すぎます" };
  }

  let referenceCm;
  if (panel.els.measurementRadio.checked) {
    const field = panel.els.measurementSelect.value;
    const input = document.getElementById(`field-${field}`);
    referenceCm = input ? parseFloat(input.value) : NaN;
    if (!isFinite(referenceCm) || referenceCm <= 0) {
      return { error: "採寸値が未入力のため実寸を計算できません" };
    }
  } else {
    referenceCm = parseFloat(panel.els.referenceCmInput.value);
    if (!isFinite(referenceCm) || referenceCm <= 0) {
      return { error: "基準寸法(cm)を入力すると実寸を表示します" };
    }
  }

  const scale = referenceCm / refPx;
  const xs = panel.points.map((p) => p[0]);
  const ys = panel.points.map((p) => p[1]);
  const width = (Math.max(...xs) - Math.min(...xs)) * scale;
  const height = (Math.max(...ys) - Math.min(...ys)) * scale;
  return { width, height };
}

function updateCustomPanelSizePreview(panel) {
  const el = panel.els.sizePreview;
  if (!el) return;
  const size = computeCustomPanelSizeCm(panel);
  if (size.error) {
    el.textContent = size.error;
    el.classList.remove("error-text");
    el.classList.add("is-muted");
    return;
  }
  const { width, height } = size;
  el.classList.remove("is-muted");
  // 生成結果の一覧に出る寸法は「裁断線(縫い代込み)」の外寸なので、ここでも
  // 両方を並べて示す。片方だけ出すと、この予告(縫い線=仕上がり寸法)と
  // 結果表示(裁断線)が食い違って見え、実際に検証中に混乱の元になった。
  const seamInput = document.getElementById("field-seam-allowance");
  const seamCm = seamInput && seamInput.value !== "" ? parseFloat(seamInput.value) : 1.0;
  const seam = isFinite(seamCm) && seamCm >= 0 ? seamCm : 1.0;
  const cutW = width + seam * 2;
  const cutH = height + seam * 2;
  const dims = `仕上がり寸法(縫い線) 幅 ${width.toFixed(1)}cm × 高さ ${height.toFixed(1)}cm`
    + ` / 裁断寸法(縫い代${seam}cm込み) 幅 ${cutW.toFixed(1)}cm × 高さ ${cutH.toFixed(1)}cm`;
  // サーバー側と同じ判定条件で、送信前に警告しておく。
  if (width < CUSTOM_PANEL_MIN_DIMENSION_CM && height < CUSTOM_PANEL_MIN_DIMENSION_CM) {
    el.textContent = `${dims}（小さすぎます。基準寸法か輪郭を見直してください）`;
    el.classList.add("error-text");
  } else if (width > CUSTOM_PANEL_MAX_DIMENSION_CM || height > CUSTOM_PANEL_MAX_DIMENSION_CM) {
    el.textContent = `${dims}（大きすぎます。上限は${CUSTOM_PANEL_MAX_DIMENSION_CM}cmです）`;
    el.classList.add("error-text");
  } else {
    el.textContent = dims;
    el.classList.remove("error-text");
  }
}

function updateCustomPanelsJson() {
  if (!customPanelsJsonInput) return;
  const payload = customPanels.map((panel) => {
    const entry = {
      label: panel.els.labelInput.value.trim(),
      points: panel.points,
      ref_point_a: panel.refA,
      ref_point_b: panel.refB,
      quantity: parseInt(panel.els.quantityInput.value, 10) || 1,
      mirror: panel.els.mirrorInput.checked,
      // round57: 収まらないときに分けてよいか(既定は分けない)。
      allow_split: panel.els.splitInput.checked,
    };
    if (panel.els.measurementRadio.checked) {
      entry.measurement_field = panel.els.measurementSelect.value;
    } else {
      entry.reference_cm = parseFloat(panel.els.referenceCmInput.value);
    }
    return entry;
  });
  customPanelsJsonInput.value = JSON.stringify(payload);
  customPanels.forEach(updateCustomPanelSizePreview);
}

async function handleAutoTrace(panel) {
  const file = panel.els.fileInput.files && panel.els.fileInput.files[0];
  if (!file) {
    setPanelStatus(panel, "先に画像ファイルを選択してください。", true);
    return;
  }
  setPanelStatus(panel, "画像から輪郭を抽出しています…");
  const body = new FormData();
  body.append("csrf_token", _csrfToken());
  body.append("image", file);
  try {
    const response = await fetch("/api/custom-panel/trace", { method: "POST", body });
    const data = await readJsonOrThrow(response, "輪郭の抽出に失敗しました。");
    // 実際にPlaywrightでブラウザを起動して確認して見つかった不具合の修正:
    // 以前はURL.createObjectURL(file)で生成した blob: URLを<img>のsrcに
    // 使っていたが、このアプリのCSP(app.pyの_set_security_headers参照)は
    // `img-src 'self' data:` のみを許可しており blob: は含まれないため、
    // ブラウザにブロックされて画像が一切表示されない実バグがあった
    // (コンソールにCSP違反エラーが出るのみで、画面上はimg.onerrorが呼ばれ
    // 「画像の読み込みに失敗しました」とだけ表示される分かりにくい状態)。
    // blob:をCSPで新たに許可する代わりに、data: URL(既に許可済み)を
    // 使うFileReaderに切り替えて解消する。
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // サーバーが返す輪郭点(data.points)は、アップロードした画像の元の
        // 解像度(ピクセル)基準。キャンバスの内部バッファは処理コスト・
        // 操作のしやすさのため上限(CUSTOM_PANEL_MAX_CANVAS_DIMENSION)まで
        // 縮小するため、輪郭点も同じ比率で縮小してキャンバス座標系に揃える
        // (校正は一様スケーリングのため、この縮小自体は最終結果に影響しない)。
        const naturalMax = Math.max(img.naturalWidth, img.naturalHeight) || 1;
        const scale = Math.min(1, CUSTOM_PANEL_MAX_CANVAS_DIMENSION / naturalMax);
        panel.canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
        panel.canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
        panel.img = img;
        panel.points = (data.points || []).map(([x, y]) => [x * scale, y * scale]);
        panel.refA = null;
        panel.refB = null;
        redrawPanel(panel);
        updateCustomPanelsJson();
        setPanelStatus(
          panel,
          `輪郭を自動抽出しました（頂点${panel.points.length}個）。ドラッグで位置を調整できます。` +
          "続けて「参照点Aを指定」「参照点Bを指定」で校正用の2点をクリックし、基準寸法を入力してください。",
        );
      };
      img.onerror = () => setPanelStatus(panel, "画像の読み込みに失敗しました。", true);
      img.src = reader.result;
    };
    reader.onerror = () => setPanelStatus(panel, "画像の読み込みに失敗しました。", true);
    reader.readAsDataURL(file);
  } catch (err) {
    setPanelStatus(panel, describeFetchFailure(err, "輪郭の抽出に失敗しました。"), true);
  }
}

function wireCustomPanelEvents(panel) {
  const { els, canvas } = panel;

  els.labelInput.addEventListener("input", updateCustomPanelsJson);
  els.quantityInput.addEventListener("input", updateCustomPanelsJson);
  els.mirrorInput.addEventListener("change", updateCustomPanelsJson);
  els.referenceCmInput.addEventListener("input", updateCustomPanelsJson);
  els.measurementSelect.addEventListener("change", updateCustomPanelsJson);

  els.manualRadio.addEventListener("change", () => {
    els.referenceCmField.classList.toggle("hidden", !els.manualRadio.checked);
    els.measurementFieldBox.classList.toggle("hidden", els.manualRadio.checked);
    updateCustomPanelsJson();
  });
  els.measurementRadio.addEventListener("change", () => {
    els.referenceCmField.classList.toggle("hidden", els.measurementRadio.checked);
    els.measurementFieldBox.classList.toggle("hidden", !els.measurementRadio.checked);
    updateCustomPanelsJson();
  });

  function setToolMode(mode) {
    panel.mode = mode;
    [els.addModeBtn, els.refABtn, els.refBBtn].forEach((b) => b.classList.remove("is-active"));
    if (mode === "add") els.addModeBtn.classList.add("is-active");
    if (mode === "refA") els.refABtn.classList.add("is-active");
    if (mode === "refB") els.refBBtn.classList.add("is-active");
  }
  els.addModeBtn.addEventListener("click", () => setToolMode("add"));
  els.refABtn.addEventListener("click", () => setToolMode("refA"));
  els.refBBtn.addEventListener("click", () => setToolMode("refB"));
  setToolMode("add");

  els.undoBtn.addEventListener("click", () => {
    panel.points.pop();
    redrawPanel(panel);
    updateCustomPanelsJson();
  });
  els.clearBtn.addEventListener("click", () => {
    panel.points = [];
    redrawPanel(panel);
    updateCustomPanelsJson();
  });
  els.removeBtn.addEventListener("click", () => {
    const idx = customPanels.indexOf(panel);
    if (idx >= 0) customPanels.splice(idx, 1);
    panel.card.remove();
    syncAddCustomPanelButton();
    updateCustomPanelsJson();
  });
  els.autoTraceBtn.addEventListener("click", () => handleAutoTrace(panel));

  canvas.addEventListener("pointerdown", (e) => {
    const pt = canvasPointFromEvent(panel, e);

    // 【round11で修正したUI上の不具合】以前は既存の頂点/参照点の当たり判定を
    // 常に最優先していたため、「参照点Aを指定」ボタンを押した直後でも、
    // 置きたい場所にたまたま頂点があると参照点が置かれず、代わりにその頂点の
    // ドラッグが始まっていた(利用者から見ると、ボタンを押したのに何も
    // 起きないまま輪郭が動く)。参照線は輪郭の角に合わせて引きたいことが
    // 多く、実際に画像から自動抽出した輪郭では頂点が密なため、かなりの
    // 確率でこれを踏む。明示的に参照点モードを選んでいる間は、そのモードの
    // 操作を優先する。
    if (panel.mode === "refA" || panel.mode === "refB") {
      if (panel.mode === "refA") panel.refA = pt;
      else panel.refB = pt;
      setToolMode("add");
      redrawPanel(panel);
      updateCustomPanelsJson();
      return;
    }

    const handle = findNearestHandle(panel, pt);
    if (handle) {
      panel.dragging = handle;
      canvas.setPointerCapture(e.pointerId);
      return;
    }
    panel.points.push(pt);
    redrawPanel(panel);
    updateCustomPanelsJson();
  });
  // 頂点の個別削除(round11で追加)。それまでは「最後の点を取り消す」しか
  // 手段が無く、途中の1点だけを直したい場合に、その点以降を全部消して
  // 引き直す必要があった(自動抽出した輪郭は点数が多いので特に手戻りが
  // 大きい)。ダブルクリック/ダブルタップした頂点だけを取り除く。
  // 参照点A・Bは輪郭の頂点ではないので対象にしない。
  canvas.addEventListener("dblclick", (e) => {
    e.preventDefault();
    const pt = canvasPointFromEvent(panel, e);
    const handle = findNearestHandle(panel, pt);
    if (!handle || handle.kind !== "point") return;
    // 3点未満になると輪郭として成立しないため、その場合は消さずに知らせる。
    if (panel.points.length <= 3) {
      setPanelStatus(panel, "輪郭には3点以上必要です。これ以上は削除できません。", true);
      return;
    }
    panel.points.splice(handle.index, 1);
    panel.dragging = null;
    setPanelStatus(panel, `頂点を1つ削除しました(残り${panel.points.length}点)。`, false);
    redrawPanel(panel);
    updateCustomPanelsJson();
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!panel.dragging) return;
    const pt = canvasPointFromEvent(panel, e);
    if (panel.dragging.kind === "point") panel.points[panel.dragging.index] = pt;
    else if (panel.dragging.kind === "refA") panel.refA = pt;
    else if (panel.dragging.kind === "refB") panel.refB = pt;
    redrawPanel(panel);
    // ドラッグ中も実寸表示だけは追従させる(参照線を動かしている最中に
    // 寸法が固まったままだと、狙った寸法へ合わせにくいため)。
    updateCustomPanelSizePreview(panel);
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((evtName) => {
    canvas.addEventListener(evtName, () => {
      if (panel.dragging) {
        panel.dragging = null;
        updateCustomPanelsJson();
      }
    });
  });
}

function createCustomPanel() {
  if (customPanels.length >= CUSTOM_PANEL_MAX_PANELS_CLIENT) return null;
  const id = ++customPanelIdCounter;

  const card = document.createElement("div");
  card.className = "custom-panel-card field-box";

  const header = document.createElement("div");
  header.className = "custom-panel-card-header";
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.placeholder = "パーツ名（例: マント、肩当て）";
  labelInput.maxLength = 40;
  // round37: 支援技術に読まれる名前を付ける。
  //
  // 【なぜplaceholderでは足りないか】placeholderは**名前ではない**。
  // 読み上げソフトによっては読まれず、読まれる場合でも1文字入力した
  // 時点で消えるので、「今どの欄にいるのか」を確かめ直せない。
  // 実測(round37): Tabで辿ったところ、カスタムパーツの中の3つの欄
  // (パーツ名・画像ファイル・参照線の実寸)が**名前を持たない**まま
  // 到達でき、読み上げても何の欄か分からない状態だった。
  labelInput.setAttribute("aria-label", "カスタムパーツの名前");
  const quantityLabel = document.createElement("label");
  quantityLabel.appendChild(document.createTextNode("枚数 "));
  const quantityInput = document.createElement("input");
  quantityInput.type = "number";
  quantityInput.min = "1";
  quantityInput.max = "8";
  quantityInput.value = "1";
  quantityInput.style.width = "4em";
  quantityLabel.appendChild(quantityInput);
  const mirrorLabel = document.createElement("label");
  const mirrorInput = document.createElement("input");
  mirrorInput.type = "checkbox";
  mirrorLabel.appendChild(mirrorInput);
  mirrorLabel.appendChild(document.createTextNode(" 左右反転パーツも作る"));
  // round57: 生地幅に収まらないときに分けてよいか。
  // マントは中心で縫い合わせるのがふつうだが、EVAフォームの装甲に
  // 縫い目を入れるのは別の話なので、**作る人が決める**。
  const splitLabel = document.createElement("label");
  const splitInput = document.createElement("input");
  splitInput.type = "checkbox";
  splitLabel.appendChild(splitInput);
  splitLabel.appendChild(document.createTextNode(" 収まらないときは分割する"));
  splitLabel.title = "生地幅に収まらない場合、縦に分けて縫い合わせる型紙にします"
    + "（マントなど、そこに縫い目が入ってよいパーツ向け）。";
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-outline";
  removeBtn.textContent = "このパーツを削除";
  header.append(labelInput, quantityLabel, mirrorLabel, splitLabel, removeBtn);
  card.appendChild(header);

  const traceRow = document.createElement("div");
  traceRow.className = "custom-panel-trace-row";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.setAttribute("aria-label", "輪郭を読み取る画像ファイル");
  const autoTraceBtn = document.createElement("button");
  autoTraceBtn.type = "button";
  autoTraceBtn.className = "btn-outline";
  autoTraceBtn.textContent = "画像から輪郭を自動抽出";
  traceRow.append(fileInput, autoTraceBtn);
  card.appendChild(traceRow);

  const canvasWrap = document.createElement("div");
  canvasWrap.className = "custom-panel-canvas-wrap";
  const canvas = document.createElement("canvas");
  canvas.className = "custom-panel-canvas";
  canvas.width = CUSTOM_PANEL_DEFAULT_CANVAS_SIZE;
  canvas.height = CUSTOM_PANEL_DEFAULT_CANVAS_SIZE;
  // round37: このキャンバスは、Tabで到達できず、名前も役割も持っていなかった。
  //
  // 【正直に書くと】輪郭をクリックで描く操作そのものは、キーボードだけでは
  // できない。矢印キーで頂点を置く仕組みを作ることはできるが、いまは無い。
  // ただし**同じ輪郭を得る別の道はある**——画像を選んで「画像から輪郭を
  // 自動抽出」を押す経路は、ファイル選択もボタンも普通にTabで辿れる。
  // 道があるのに、それが道だと画面のどこにも書いていなかったのが問題である。
  // ここでは (a) キャンバスに名前と役割を与えて読み上げに乗せ、
  // (b) 下の説明文で代わりの経路を案内する。
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label",
    "カスタムパーツの輪郭を描く領域です。マウスやタッチでの操作が必要です。"
    + "キーボードだけで操作する場合は、上の「画像から輪郭を自動抽出」を"
    + "使うと同じ輪郭が得られます。");
  canvasWrap.appendChild(canvas);
  card.appendChild(canvasWrap);

  const tools = document.createElement("div");
  tools.className = "custom-panel-tools checkbox-row";
  const addModeBtn = _toolButton("頂点を追加/ドラッグで調整");
  const refABtn = _toolButton("参照点Aを指定");
  const refBBtn = _toolButton("参照点Bを指定");
  const undoBtn = _toolButton("最後の頂点を削除");
  const clearBtn = _toolButton("輪郭をクリア");
  tools.append(addModeBtn, refABtn, refBBtn, undoBtn, clearBtn);
  card.appendChild(tools);

  const calibBox = document.createElement("div");
  calibBox.className = "custom-panel-calibration";
  const calibRow = document.createElement("div");
  calibRow.className = "checkbox-row";
  const manualRadioLabel = document.createElement("label");
  const manualRadio = document.createElement("input");
  manualRadio.type = "radio";
  manualRadio.name = `custom-panel-calib-${id}`;
  manualRadio.checked = true;
  manualRadioLabel.append(manualRadio, document.createTextNode(" 参照線の実寸(cm)を直接入力"));
  const measurementRadioLabel = document.createElement("label");
  const measurementRadio = document.createElement("input");
  measurementRadio.type = "radio";
  measurementRadio.name = `custom-panel-calib-${id}`;
  measurementRadioLabel.append(measurementRadio, document.createTextNode(" 既存の採寸値を流用"));
  calibRow.append(manualRadioLabel, measurementRadioLabel);
  calibBox.appendChild(calibRow);

  const referenceCmField = document.createElement("div");
  referenceCmField.className = "custom-panel-calib-manual-field";
  const referenceCmInput = document.createElement("input");
  referenceCmInput.type = "number";
  referenceCmInput.step = "0.1";
  referenceCmInput.placeholder = "参照点A〜B間の実寸(cm)。例: 40";
  referenceCmInput.setAttribute("aria-label", "参照点A〜B間の実寸(cm)");
  referenceCmField.appendChild(referenceCmInput);
  calibBox.appendChild(referenceCmField);

  const measurementFieldBox = document.createElement("div");
  measurementFieldBox.className = "custom-panel-calib-measurement-field hidden";
  const measurementSelect = document.createElement("select");
  // round47: この1つだけ読み上げ用の名前が無かった。名前の無い<select>は、
  // ブラウザが**選択肢の文字を全部つなげたもの**を名前として読む——実測で
  // 「バストウエストヒップ身長袖丈肩幅 コンボボックス」と読み上げられていた。
  // すぐ上の referenceCmInput には aria-label が付いているので、
  // ここだけ抜けていた(round44で静的な画面の同種6件は直したが、
  // この欄は押して初めて作られるので、その調査に入っていなかった)。
  measurementSelect.setAttribute("aria-label", "流用する採寸値");
  CUSTOM_PANEL_MEASUREMENT_FIELDS.forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    measurementSelect.appendChild(opt);
  });
  measurementFieldBox.appendChild(measurementSelect);
  calibBox.appendChild(measurementFieldBox);
  card.appendChild(calibBox);

  // 校正後の実寸(cm)の予告表示(round11で追加)。送信して初めて寸法エラーに
  // 気づく状態を避けるため、頂点・参照点・基準寸法のどれを操作しても
  // その場で更新される(updateCustomPanelsJson経由)。
  const sizePreview = document.createElement("p");
  sizePreview.className = "hint custom-panel-size-preview is-muted";
  sizePreview.textContent = "参照点A・Bを指定すると実寸を表示します";
  card.appendChild(sizePreview);

  const status = document.createElement("p");
  status.className = "hint custom-panel-status";
  status.textContent = "輪郭の頂点を3つ以上追加(クリック)し、参照点A・Bと基準寸法を指定してください。"
    + " 頂点はドラッグで移動、ダブルクリックで個別に削除できます。"
    // round37: キーボードだけで操作する人への案内。輪郭を描く操作自体は
    // マウス/タッチが要るが、画像から自動抽出する経路なら同じ輪郭が得られ、
    // そちらはファイル選択もボタンも普通にTabで辿れる。道はあったのに、
    // 画面のどこにも書いていなかった。
    + " マウスやタッチが使えない場合は、上の「画像から輪郭を自動抽出」から"
    + "輪郭の写真・画像を読み込ませると、同じ輪郭が作れます。";
  card.appendChild(status);

  customPanelListEl.appendChild(card);

  const panel = {
    id, card, canvas, ctx: canvas.getContext("2d"),
    img: null, points: [], refA: null, refB: null, mode: "add", dragging: null,
    els: {
      labelInput, quantityInput, mirrorInput, splitInput, fileInput, autoTraceBtn,
      addModeBtn, refABtn, refBBtn, undoBtn, clearBtn, removeBtn,
      manualRadio, measurementRadio, referenceCmInput, referenceCmField,
      measurementSelect, measurementFieldBox, status, sizePreview,
    },
  };
  customPanels.push(panel);
  redrawPanel(panel);
  wireCustomPanelEvents(panel);
  syncAddCustomPanelButton();
  updateCustomPanelsJson();
  return panel;
}

if (addCustomPanelBtn) {
  addCustomPanelBtn.addEventListener("click", () => createCustomPanel());
}
wireCustomPanelSizeDependencies();

// フォーム送信前の入力チェック。手動モード以外では常に空配列に戻す
// (バックエンドはイラスト/サイズ展開モードでcustom_panels_jsonが空でない
// 場合、明確なエラーを返す設計のため、モードを切り替えたのに前に入力した
// カスタムパーツが残っていて誤送信される事故を防ぐ)。エラーがあれば
// メッセージを、無ければnullを返す。
function validateCustomPanelsBeforeSubmit() {
  const modeInput = form.querySelector('input[name="mode"]:checked');
  const isManual = modeInput && modeInput.value === "manual";
  if (!isManual || customPanels.length === 0) {
    if (customPanelsJsonInput) customPanelsJsonInput.value = "[]";
    return null;
  }
  for (const panel of customPanels) {
    const label = panel.els.labelInput.value.trim();
    if (!label) return "カスタムパーツの名前(ラベル)を入力してください。";
    if (panel.points.length < 3) return `カスタムパーツ「${label}」: 輪郭の頂点を3つ以上指定してください。`;
    if (!panel.refA || !panel.refB) {
      return `カスタムパーツ「${label}」: 校正用の参照点A・Bを両方指定してください。`;
    }
    if (panel.els.manualRadio.checked) {
      const cm = parseFloat(panel.els.referenceCmInput.value);
      if (!(cm > 0)) return `カスタムパーツ「${label}」: 参照点A〜B間の実寸(cm)を入力してください。`;
    }
  }
  updateCustomPanelsJson();
  return null;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const customPanelError = validateCustomPanelsBeforeSubmit();
  if (customPanelError) {
    showError(customPanelError);
    return;
  }

  placeholder.classList.add("hidden");
  content.classList.add("hidden");
  multiSizeContent.classList.add("hidden");
  loading.classList.remove("hidden");
  beginGenerating();

  const timer = startGenerateTimeout();
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      body: new FormData(form),
      signal: timer.signal,
    });
    const data = await readJsonOrThrow(response, "型紙の生成に失敗しました。");

    if (data.mode === "multi_size") {
      renderMultiSizeResults(data);
      updateUsageNote(data.usage);
      content.classList.add("hidden");
      multiSizeContent.classList.remove("hidden");
      loading.classList.add("hidden");
      // round46: 1段組(768px以下)でも結果まで画面を動かす。
      scrollResultIntoView();
      // round46: 「右のパネル」は2段組のときだけの話で、スマホでは
      // 結果はフォームの**下**に出る。画面の作りに依らない言い方にする。
      announce(`${Object.keys(data.results || {}).length}サイズ分の型紙ができました。`
               + "「生成結果」に一覧が出ています。");
      endGenerating();
      return;
    }
    multiSizeContent.classList.add("hidden");

    document.getElementById("stat-parts").textContent = data.part_count;
    document.getElementById("stat-waste").textContent = formatPercent(data.waste_ratio);
    document.getElementById("stat-length").textContent = data.used_length_cm;
    document.getElementById("stat-width").textContent = data.fabric_width_cm;
    renderFabricNeed(data);
    renderShoppingList(data);
    renderStashVerdict(data);
    renderLining(data);
    document.getElementById("stat-time").textContent = data.elapsed_seconds;
    document.getElementById("stat-unplaced").textContent = data.unplaced_count;
    renderPdfSheetCount(data);
    renderFabricGroups(data);

    const cacheBust = `?t=${Date.now()}`;
    document.getElementById("preview-img").src = data.download.svg + cacheBust;
    document.getElementById("download-svg").href = data.download.svg;
    document.getElementById("download-pdf").href = data.download.pdf;
    document.getElementById("download-dxf").href = data.download.dxf;
    // round39: プロジェクター投影用。応答に無い場合(古いジョブの再生成など)は
    // リンクを隠す——押せるのに404になる方が分かりにくい。
    const projectorLink = document.getElementById("download-projector");
    if (projectorLink) {
      const href = data.download.projector;
      projectorLink.classList.toggle("hidden", !href);
      if (href) projectorLink.href = href + cacheBust;
    }

    document.getElementById("rotation-warning").classList.toggle("hidden", !data.rotation_used);

    const unplacedWarnings = Array.isArray(data.unplaced_warnings) ? data.unplaced_warnings : [];
    const unplacedWarningBox = document.getElementById("unplaced-warning");
    const unplacedWarningList = document.getElementById("unplaced-warning-list");
    unplacedWarningBox.classList.toggle("hidden", unplacedWarnings.length === 0);
    unplacedWarningList.innerHTML = "";
    for (const message of unplacedWarnings) {
      const li = document.createElement("li");
      li.textContent = message;
      unplacedWarningList.appendChild(li);
    }

    const measurementWarnings = Array.isArray(data.measurement_warnings) ? data.measurement_warnings : [];
    const clampWarningBox = document.getElementById("measurement-clamp-warning");
    const clampWarningList = document.getElementById("measurement-clamp-warning-list");
    clampWarningBox.classList.toggle("hidden", measurementWarnings.length === 0);
    clampWarningList.innerHTML = "";
    for (const message of measurementWarnings) {
      const li = document.createElement("li");
      li.textContent = message;
      clampWarningList.appendChild(li);
    }

    // round33: 縫う順番。PDFにも同じ内容が入っているが、裁つ前に画面で
    // 全体を見通せるようにする。
    renderAssemblySteps(data.assembly_steps);

    // round32: 警告ではない「こう作りました」の説明。
    const designNotes = Array.isArray(data.design_notes) ? data.design_notes : [];
    const designNoteBox = document.getElementById("design-note");
    const designNoteList = document.getElementById("design-note-list");
    designNoteBox.classList.toggle("hidden", designNotes.length === 0);
    designNoteList.innerHTML = "";
    for (const message of designNotes) {
      const li = document.createElement("li");
      li.textContent = message;
      designNoteList.appendChild(li);
    }

    const costumeProject = data.costume_project;
    const costumeProjectBox = document.getElementById("costume-project-result");
    costumeProjectBox.classList.toggle("hidden", !costumeProject);
    if (costumeProject) {
      document.getElementById("costume-project-name").textContent = costumeProject.label || "衣装プロジェクト";
      const fillList = (id, values) => {
        const list = document.getElementById(id);
        list.innerHTML = "";
        for (const value of values || []) {
          const li = document.createElement("li");
          li.textContent = value;
          list.appendChild(li);
        }
      };
      fillList("costume-project-benchmark", costumeProject.commercial_benchmark);
      fillList("costume-project-patterns", costumeProject.patternable_components);
      fillList("costume-project-separate", costumeProject.separate_components);
      fillList("costume-project-materials", costumeProject.material_plan);
      fillList("costume-project-construction", costumeProject.construction_plan);
      fillList("costume-project-limitations", costumeProject.limitations);
    }

    const referenceReview = data.reference_review;
    const referenceReviewBox = document.getElementById("reference-review-result");
    referenceReviewBox.classList.toggle("hidden", !referenceReview);
    if (referenceReview) {
      document.getElementById("reference-review-summary").textContent = referenceReview.summary || "";
      const fillReviewList = (id, values) => {
        const list = document.getElementById(id);
        list.innerHTML = "";
        for (const value of values || []) {
          const li = document.createElement("li");
          li.textContent = value;
          list.appendChild(li);
        }
      };
      fillReviewList("reference-review-detected", referenceReview.detected);
      fillReviewList("reference-review-missing", referenceReview.missing);
    }

    const compatibilityWarnings = Array.isArray(data.compatibility_warnings) ? data.compatibility_warnings : [];
    const compatibilityWarningBox = document.getElementById("compatibility-warning");
    const compatibilityWarningList = document.getElementById("compatibility-warning-list");
    compatibilityWarningBox.classList.toggle("hidden", compatibilityWarnings.length === 0);
    compatibilityWarningList.innerHTML = "";
    for (const warning of compatibilityWarnings) {
      const li = document.createElement("li");
      li.textContent = warning.message;
      compatibilityWarningList.appendChild(li);
    }

    document.getElementById("ai-contribution-note").textContent = data.ai_contribution || "";

    // round50: 「AI使用」かどうかは、サーバが返す `ai_engine` で決める。
    //
    // 【round49まで何が起きていたか】`classification_log.length > 0` だけで
    // 判定していたため、ANTHROPIC_API_KEY が無い環境——つまり案内文が
    // 「未設定の場合は簡易判定（モック）で動作します」と書いている、
    // まさにその状態——でも緑の「AI使用」が出ていた。AIは一度も
    // 呼ばれていない。engine側の `ai_contribution_note()` は
    // 「簡易判定(モック)」と正しく書き分けていたので、
    // **目立つバッジだけが実態と食い違っていた**。
    const aiEngine = data.ai_engine
      || (Array.isArray(data.classification_log) && data.classification_log.length > 0
          ? "claude" : "none");
    const usedRealAi = aiEngine === "claude";
    const aiBadge = document.getElementById("ai-badge");
    aiBadge.textContent = {
      claude: "AI使用",
      mock: "簡易判定（モック）",
      none: "ルールベースのみ",
    }[aiEngine] || "ルールベースのみ";
    // モックはAIではないので、AI用の強調はしない。
    aiBadge.classList.toggle("ai-badge-active", usedRealAi);
    aiBadge.classList.toggle("ai-badge-inactive", !usedRealAi);

    renderDartNote(data);

    renderCompareBars(data.used_length_cm, data.naive_used_length_cm || data.used_length_cm);
    renderPartsList(data.parts);
    renderClassificationLog(data.classification_log);
    updateUsageNote(data.usage);

    loading.classList.add("hidden");
    content.classList.remove("hidden");
    // 結果を差し込んだ後にも先頭へ戻す(高さが変わると位置がずれるため)。
    if (resultPanel) resultPanel.scrollTop = 0;
    // round46: パネルの中を先頭へ戻すだけでは、1段組(768px以下)では
    // 何も起きない——そこではパネル自身がスクロールしないからである。
    // 押してから返るまでの間にフォームの高さが変わる(採寸の指摘が
    // 後から出る等)ので、**結果が入った後にもう一度**位置を取り直す。
    scrollResultIntoView();
    // 読み上げる数字は「何を買えばいいか」——この画面でいちばん先に
    // 知りたいことを先に言う。警告があればその件数も添える。
    {
      // 【round66で直した実バグ】ここは採寸の指摘と配置不能だけを数えて
      // いて、**画面でいちばん大きい⚠**——「パーツ間の縫い合わせ長さに、
      // 無視できない差があります」——を数えていなかった。実測で、画面に
      // ⚠が3件出ているのに読み上げは「注意が1件あります」と言っていた。
      // 数え落としていた2件は「そのままでは縫えません」という、
      // いちばん先に知りたい種類の注意である。
      const warnings = (data.measurement_warnings || []).length
                        + (data.unplaced_warnings || []).length
                        + (data.compatibility_warnings || []).length;
      announce(`型紙ができました。パーツ${data.part_count}枚、`
               + `幅${data.fabric_width_cm}cmの生地を`
               + `${(data.used_length_cm / 100).toFixed(1)}メートル使います。`
               + (warnings ? `確認してほしい注意が${warnings}件あります。` : ""));
    }
    endGenerating();
  } catch (err) {
    loading.classList.add("hidden");
    placeholder.classList.remove("hidden");
    endGenerating();
    const message = describeFetchFailure(err, "型紙の生成に失敗しました。");
    showError(message, err.upgradeUrl);
    // round44で読み上げ領域を置いたが、**失敗したときだけ何も言わなかった**。
    // 生成が失敗しても「型紙を生成しています。しばらくお待ちください。」が
    // 残ったままで、スクリーンリーダーではいつまでも作業中に聞こえていた。
    announce(`型紙を作れませんでした。${message}`);
    // エラーはフォームのいちばん下(送信ボタンの直下)に出るので、
    // 結果パネルへスクロールしたままだと読めない。エラー側へ戻す。
    if (formError && typeof formError.scrollIntoView === "function") {
      formError.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    // round47: 失敗したときも、フォーカスは <body> に落ちたままだった。
    // キーボードだけで使うと、何が起きたか読める場所へ自力で戻れない。
    // もう一度押せるように、送信ボタンへ返す(エラー文はその直上にあり、
    // role="alert" で読み上げられる)。
    if (submitButton) moveFocusTo(submitButton);
  } finally {
    timer.clear();
  }
});

// -- 同時に選べない組み合わせを、押す前に止める (round67) -------------------
//
// 前開きファスナーと切り替え線(プリンセスライン)は同時に指定できない
// (engine/pipeline.py の build_garment_spec がはっきり断る。前開きの
// パネルは左右非対称で、切り替え線の分割がその形を前提にしていないため)。
//
// round66まで画面は両方押せてしまい、**「型紙を生成する」を押してから**
// エラーで戻されていた。説明文の中に一行書いてはあったが、round32の
// 折りたたみで隠れることがあるうえ、押せてしまうことに変わりはない。
// 片方を選んだ時点で、もう片方をその場で押せなくして理由を出す。
const optFrontZip = document.getElementById("opt-front-zip");
const optPrincess = document.getElementById("opt-princess-line");
const zipPrincessConflict = document.getElementById("zip-princess-conflict");

function syncZipPrincessConflict() {
  if (!optFrontZip || !optPrincess || !zipPrincessConflict) return;
  const blockedByZip = optFrontZip.checked;
  const blockedByPrincess = optPrincess.checked;
  optPrincess.disabled = blockedByZip;
  optFrontZip.disabled = blockedByPrincess;
  const chosen = blockedByZip ? "前開きファスナー"
                : blockedByPrincess ? "切り替え線（プリンセスライン）" : "";
  const blocked = blockedByZip ? "切り替え線（プリンセスライン）"
                : blockedByPrincess ? "前開きファスナー" : "";
  if (!chosen) {
    zipPrincessConflict.textContent = "";
    zipPrincessConflict.classList.add("hidden");
    optPrincess.removeAttribute("aria-describedby");
    optFrontZip.removeAttribute("aria-describedby");
    return;
  }
  zipPrincessConflict.textContent =
    `「${chosen}」を選んでいる間は、「${blocked}」は選べません`
    + "（前開きのパネルは左右非対称で、切り替え線の分割がその形に対応して"
    + `いないためです）。「${blocked}」を使いたい場合は、`
    + `「${chosen}」のチェックを外してください。`;
  zipPrincessConflict.classList.remove("hidden");
  // 押せない方に、押せない理由を結び付ける(読み上げで理由が分かるように)。
  const blockedInput = blockedByZip ? optPrincess : optFrontZip;
  blockedInput.setAttribute("aria-describedby", "zip-princess-conflict");
}

if (optFrontZip && optPrincess) {
  optFrontZip.addEventListener("change", syncZipPrincessConflict);
  optPrincess.addEventListener("change", syncZipPrincessConflict);
  syncZipPrincessConflict();
}

// -- 採寸図: 入力中の項目を図の上で光らせる (round34) -------------------------
//
// 生成前の右パネルは、1440px幅で画面のほぼ半分を占める空白だった。
// 採寸ミスがこのサービスの最大の失敗要因なので、そこに「どこを測るか」の
// 図を置き、入力欄にフォーカスが入った項目を強調する。
// 測り方の文は engine/measure_guide.py から data-*属性で受け取る
// (CSPで inline script が使えないため。round9のラベル辞書と同じ方式)。
const measureFigure = document.getElementById("measure-figure");

// 「広い画面か」の境目。図の置き場所(placeMeasureFigure)と、
// 採寸欄のすぐ下に測り方を出すか(round64)の両方がこの1つを見る。
const wideScreen = window.matchMedia("(min-width: 1000px)");

// -- round64: 狭い画面では、測り方を採寸欄のすぐ下にも出す --------------------
//
// 【実測】390x844で6つの必須採寸欄のどれにフォーカスしても、採寸図の
// 見えている高さは0px、説明(measure-caption)も0pxだった。図は390px幅で
// 523px あり、説明はさらにその下にある。ソフトキーボードを出した状態
// (390x508)では肩幅でも0pxで、**測りながら読むことができない**。
// 1440x900では図が712px見えているので、これは狭い画面だけの問題である。
//
// 文は engine/measure_guide.py が唯一の出どころのまま。ここは図と同じ
// guides を使って、同じ文を別の場所にも描くだけ(文を書き足さない)。
const inlineGuideBox = document.getElementById("measure-inline-guide");
const inlineGuideTitle = document.getElementById("measure-inline-guide-title");
const inlineGuideHow = document.getElementById("measure-inline-guide-how");
const inlineGuideCaution = document.getElementById("measure-inline-guide-caution");

// どの欄に出すかは、HTMLの並び(.grid-measurements の中)から取る。
// 一覧をJSにもう1つ持つと、欄を足したときに片方だけ古くなる。
// 任意項目(二の腕・乳間・乳下がり)は欄の直下に既に説明文があるので、
// ここで二重に出さない。
function inlineGuideFields() {
  const grid = document.querySelector(".grid-measurements");
  if (!grid) return [];
  return [...grid.querySelectorAll("input[name]")].map((input) => input.name);
}

let inlineGuideDescribed = null;   // いまaria-describedbyを付けている欄

function showInlineGuide(field, guide) {
  if (!inlineGuideBox || !guide) return;
  // 広い画面では図の説明が見えている(実測712px)ので、二重に出さない。
  // CSSでも隠しているが、隠れた要素をaria-describedbyで指さないために
  // ここでも見る。
  if (wideScreen.matches) return;
  inlineGuideTitle.textContent = `${guide.label}の測り方`;
  inlineGuideHow.textContent = guide.how;
  inlineGuideCaution.textContent = guide.caution || "";
  inlineGuideCaution.classList.toggle("hidden", !guide.caution);
  inlineGuideBox.classList.remove("hidden");
  // 読み上げでは、欄の説明として読まれるのが自然(aria-live だと
  // 欄を移るたびに割り込んで読み上げる)。前の欄からは外す。
  if (inlineGuideDescribed) {
    inlineGuideDescribed.removeAttribute("aria-describedby");
  }
  const input = document.getElementById(`field-${field}`);
  if (input) {
    input.setAttribute("aria-describedby", "measure-inline-guide");
    inlineGuideDescribed = input;
  }
}

function setupMeasureFigure() {
  if (!measureFigure) return;
  let guides = {};
  try {
    guides = JSON.parse(measureFigure.dataset.measureGuides || "{}");
  } catch (err) {
    return;   // 図は補助なので、壊れていても操作を妨げない。
  }
  const groups = measureFigure.querySelectorAll("[data-measure]");
  const titleEl = document.getElementById("measure-caption-title");
  const howEl = document.getElementById("measure-caption-how");
  const cautionEl = document.getElementById("measure-caption-caution");
  const DEFAULT_TITLE = titleEl.textContent;
  const DEFAULT_HOW = howEl.textContent;

  function highlight(field) {
    for (const group of groups) {
      group.classList.toggle("is-active", group.dataset.measure === field);
    }
    const guide = guides[field];
    if (!guide) {
      titleEl.textContent = DEFAULT_TITLE;
      howEl.textContent = DEFAULT_HOW;
      cautionEl.classList.add("hidden");
      return;
    }
    titleEl.textContent = `${guide.label}の測り方`;
    howEl.textContent = guide.how;
    cautionEl.textContent = guide.caution || "";
    cautionEl.classList.toggle("hidden", !guide.caution);
  }

  const inlineFields = new Set(inlineGuideFields());
  for (const field of Object.keys(guides)) {
    const input = document.getElementById(`field-${field}`);
    if (!input) continue;
    input.addEventListener("focus", () => {
      highlight(field);
      // round64: 狭い画面では、同じ文を欄のすぐ下にも出す。
      if (inlineFields.has(field)) showInlineGuide(field, guides[field]);
    });
    // blurで消さない: 入力欄を離れて図を見比べたい場面の方が多く、
    // 触るたびに説明が消えると読み終わる前に無くなる。
  }
  // 図の線をクリックしても、その項目へ移動できるようにする。
  for (const group of groups) {
    group.addEventListener("click", () => {
      const input = document.getElementById(`field-${group.dataset.measure}`);
      if (input) { input.focus(); input.select?.(); }
    });
  }
}

setupMeasureFigure();

// round34: 狭い画面では、採寸図を採寸欄のすぐ下へ移す。
// 図は右のパネル(生成結果)の中に置いてあるが、1列に積まれるスマホでは
// フォーム全体の下に来てしまい、実測で採寸欄から2500px離れていた。
// 測りながら見る図がそこにあっても意味がない。
const measureFigureSlot = document.getElementById("measure-figure-slot");
const measureFigureHome = measureFigure ? measureFigure.parentElement : null;
// wideScreen は上(setupMeasureFigure の手前)で作っている。round64で
// 「狭い画面か」を見る場所が2つになったので、境目の値は1か所に置く。

function placeMeasureFigure() {
  if (!measureFigure || !measureFigureSlot || !measureFigureHome) return;
  const target = wideScreen.matches ? measureFigureHome : measureFigureSlot;
  if (measureFigure.parentElement !== target) target.appendChild(measureFigure);
}

// round64: 広い画面に変わったら、欄の下の測り方を片付ける。CSSで見えなく
// なるだけだと、aria-describedby が隠れた要素を指したまま残る。
function onScreenWidthChanged() {
  placeMeasureFigure();
  if (wideScreen.matches && inlineGuideBox) {
    inlineGuideBox.classList.add("hidden");
    if (inlineGuideDescribed) {
      inlineGuideDescribed.removeAttribute("aria-describedby");
      inlineGuideDescribed = null;
    }
  }
}

placeMeasureFigure();
// 画面を回した・ウィンドウ幅を変えた場合にも追随する。
if (wideScreen.addEventListener) {
  wideScreen.addEventListener("change", onScreenWidthChanged);
} else if (wideScreen.addListener) {
  wideScreen.addListener(onScreenWidthChanged);   // 古いSafari向け
}

// -- 採寸値の「たぶん測り間違い」を、生成する前に出す (round33) ---------------
//
// 採寸ミスはこのサービスがうまくいかない最大の原因なのに、round32までは
// 指摘が**生成したあと**にしか出ていなかった。1日の生成回数を1回使い、
// PDFを開いて初めて「肩幅の採寸を確かめてください」と言われる。
// 入力欄を離れた時点でサーバに聞き、その場で出す(生成回数は消費しない)。
const measurementHintBox = document.getElementById("measurement-hints");
const measurementHintList = document.getElementById("measurement-hints-list");
const HINT_FIELDS = ["bust", "waist", "hip", "height", "sleeve_length", "shoulder_width"];
let measurementHintToken = 0;

async function refreshMeasurementHints() {
  if (!measurementHintBox || !form) return;
  const body = new FormData();
  body.append("csrf_token", _csrfToken());
  let complete = true;
  for (const field of HINT_FIELDS) {
    const input = document.getElementById(`field-${field}`);
    const value = input ? input.value.trim() : "";
    if (!value) complete = false;
    body.append(field, value);
  }
  // 入力途中(空欄あり)では何も言わない。打っている最中に赤や黄が出ると、
  // 「まだ入れていないだけ」を間違いだと言われているように読める。
  if (!complete) {
    measurementHintBox.classList.add("hidden");
    return;
  }
  const token = ++measurementHintToken;
  try {
    const response = await fetch("/api/measurements/check", { method: "POST", body });
    if (!response.ok) return;
    const data = await response.json();
    // 連打された場合、古い応答で新しい表示を上書きしない。
    if (token !== measurementHintToken) return;
    const hints = Array.isArray(data.hints) ? data.hints : [];
    // round47: 中身を入れてから見せる。逆順(先に見せてから足す)だと、
    // 空の読み上げ領域が現れた直後に中身が入ることになり、
    // 読み上げの取りこぼしが起きうる。
    measurementHintList.innerHTML = "";
    for (const hint of hints) {
      const li = document.createElement("li");
      li.textContent = hint.message;
      measurementHintList.appendChild(li);
    }
    measurementHintBox.classList.toggle("hidden", hints.length === 0);
  } catch (err) {
    // 指摘は補助なので、取れなくても操作を妨げない(黙って何も出さない)。
  }
}

for (const field of HINT_FIELDS) {
  const input = document.getElementById(`field-${field}`);
  if (input) input.addEventListener("change", refreshMeasurementHints);
}

// -- 長い説明文をたたむ (round32) --------------------------------------------
//
// 実測: フォーム全体の高さ2971pxのうち、説明文(p.hint)が1254px——**42%**を
// 占めていた。そのため「型紙を生成する」ボタンがページ先頭から約2300px下に
// あり、初めて開いた人は延々スクロールしてようやくボタンに着く。
// 説明は消さず(この型紙の作りは説明が要る)、最初の一文だけ見せて残りを
// たたむ。何が書いてあるかは一文目で分かるので、必要な人だけ開けばよい。
//
// 注意: 「⚠」で始まる注意書きはたたまない。読まずに進むと困る種類の
//       情報で、たたむことは開示をやめることに近い。
const HINT_COLLAPSE_MIN_HEIGHT_PX = 48;   // 約3行以上のものだけ対象にする

function rawSentenceLength(hint, normalizedStop) {
  // 見出しにした一文が、**原文(空白を潰す前)**では何文字ぶんかを返す。
  //
  // 一文目を探すときは `replace(/\s+/g, " ")` で正規化した文字列を使って
  // いるが、DOMの文字数はそれとずれる(テンプレートの改行・字下げが
  // そのまま入っているため)。正規化後の位置で原文を切ると、途中で
  // 切れた文が残る。原文側の「。」を数え直して位置を合わせる。
  const raw = hint.textContent || "";
  const index = raw.indexOf("。");
  return index >= 0 ? index + 1 : normalizedStop + 1;
}

function keepLeadingCharacters(root, count) {
  // `root`の先頭`count`文字ぶんだけを残す(要素の入れ子は保つ)。
  // 見出しにする一文にも<strong>が入っていることがあるため。
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let remaining = count;
  const doomed = [];
  let node;
  while ((node = walker.nextNode())) {
    if (remaining <= 0) {
      doomed.push(node);
    } else if (node.data.length > remaining) {
      node.data = node.data.slice(0, remaining);
      remaining = 0;
    } else {
      remaining -= node.data.length;
    }
  }
  for (const text of doomed) text.remove();
  for (const element of [...root.querySelectorAll("*")]) {
    if (!element.textContent.trim() && !element.querySelector("img")) element.remove();
  }
  // 見出しは1行に収めるので、途中の改行・字下げを1つの空白に潰す。
  const inner = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let text;
  while ((text = inner.nextNode())) text.data = text.data.replace(/\s+/g, " ");
}

function removeLeadingCharacters(root, count) {
  // `root`の先頭から`count`文字ぶんのテキストを、要素の入れ子を保ったまま
  // 取り除く。`textContent`で作り直すのと違い、<strong>等が残る。
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let remaining = count;
  const emptied = [];
  let node;
  while (remaining > 0 && (node = walker.nextNode())) {
    if (node.data.length <= remaining) {
      remaining -= node.data.length;
      emptied.push(node);
    } else {
      node.data = node.data.slice(remaining);
      remaining = 0;
    }
  }
  for (const text of emptied) text.remove();
  // 一文目の中だけにあった<strong>等は、中身が無くなって残骸になる。
  for (const element of [...root.querySelectorAll("*")]) {
    if (!element.textContent.trim() && !element.querySelector("img, br")) {
      element.remove();
    }
  }
  // 先頭に残った空白・改行を落とす(「。」の直後から始めるため)。
  const first = document.createTreeWalker(root, NodeFilter.SHOW_TEXT).nextNode();
  if (first) first.data = first.data.replace(/^\s+/, "");
}

function collapseLongHints() {
  if (!form) return;
  for (const hint of [...form.querySelectorAll("p.hint")]) {
    const text = (hint.textContent || "").replace(/\s+/g, " ").trim();
    if (!text || text.startsWith("⚠")) continue;
    if (hint.getBoundingClientRect().height < HINT_COLLAPSE_MIN_HEIGHT_PX) continue;
    if (hint.querySelector("a, input, select, button")) continue;  // 操作できる物は触らない

    // 一文目(「。」まで)を見出しにする。句点が無ければ先頭40文字。
    const stop = text.indexOf("。");
    const head = stop > 0 && stop < text.length - 1 ? text.slice(0, stop + 1) : text.slice(0, 40) + "…";
    const rest = stop > 0 && stop < text.length - 1 ? text.slice(stop + 1).trim() : text;
    if (!rest) continue;

    const details = document.createElement("details");
    details.className = "hint hint-collapsible";
    const summary = document.createElement("summary");
    // 見出しにも強調が入っていることがある(「出来上がりの長さです」など)。
    // 句点で切れる場合だけ元のマークアップから作り、そうでない場合
    // (先頭40文字+「…」)は文字列から作る。
    const cut = stop > 0 && stop < text.length - 1 ? rawSentenceLength(hint, stop) : 0;
    if (cut > 0) {
      const headNodes = hint.cloneNode(true);
      keepLeadingCharacters(headNodes, cut);
      while (headNodes.firstChild) summary.appendChild(headNodes.firstChild);
    } else {
      summary.textContent = head;
    }
    const body = document.createElement("p");
    body.className = "hint hint-collapsible-body";
    // 【round52で直した実害】ここは以前 `body.textContent = rest` と書いて
    // いたため、たたんだ説明文から**強調(<strong>)が消えていた**。
    // 実測: 画面の強調17か所のうち7か所が失われ、その中には
    // 「縫い代は足していません」「出来上がりの長さ」——つまり
    // **読み違えると寸法を間違える箇所**が含まれていた。否定文の強調が
    // 消えるのが特に悪く、「足しています」と読み飛ばしても気づけない。
    // 元のマークアップごと残し、見出しにした一文目だけを取り除く。
    const restNodes = hint.cloneNode(true);
    if (stop > 0 && stop < text.length - 1) {
      removeLeadingCharacters(restNodes, rawSentenceLength(hint, stop));
    }
    while (restNodes.firstChild) body.appendChild(restNodes.firstChild);
    details.appendChild(summary);
    details.appendChild(body);
    hint.replaceWith(details);
  }
}

collapseLongHints();
// イラスト/サイズ展開モードへ切り替えると隠れていた説明文が現れるので、
// そのときにもたたみ直す(表示された直後は高さが測れるようになっている)。
for (const input of form ? form.querySelectorAll('input[name="mode"]') : []) {
  input.addEventListener("change", () => window.setTimeout(collapseLongHints, 0));
}
if (fitSelect) fitSelect.addEventListener("change", () => window.setTimeout(collapseLongHints, 0));

// -- 採寸プロフィール（ログイン時のみ表示。複数顧客・家族分の採寸値を
//    名前付きで保存・呼び出しできるようにする） -----------------------

const profileSelect = document.getElementById("profile-select");
const profileNameInput = document.getElementById("profile-name-input");
const profileSaveBtn = document.getElementById("profile-save-btn");
const profileSaveMessage = document.getElementById("profile-save-message");

const MEASUREMENT_FIELDS = ["bust", "waist", "hip", "height", "sleeve_length", "shoulder_width"];

if (profileSelect) {
  profileSelect.addEventListener("change", () => {
    const option = profileSelect.selectedOptions[0];
    if (!option || !option.value) return;
    for (const field of MEASUREMENT_FIELDS) {
      const input = document.getElementById(`field-${field}`);
      if (input && option.dataset[field] !== undefined) {
        input.value = option.dataset[field];
        // round47: `value` を代入するだけでは、ブラウザは change を投げない。
        // そのため**保存したプロフィールを読み込んだときだけ、採寸値の
        // 指摘(round33)が一度も走らなかった**。実測:
        //
        //   ウエスト95・ヒップ70 を手で打つ → 「ヒップがウエストより細く
        //     なっています。…履く動作が成り立ちません」が出る
        //   同じ値をプロフィールから読み込む → **何も出ない**
        //
        // 採寸ミスはこのサービスの最大の失敗要因(round33)で、しかも
        // プロフィールは「前に測った値をそのまま使う」機能だから、
        // 間違いが入ったまま何度も使われる経路である。
        // 個別に呼ぶのではなくイベントを投げるのは、この欄を見ている
        // 処理が今後増えても勝手に動くようにするため。
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  });
}

if (profileSaveBtn) {
  profileSaveBtn.addEventListener("click", async () => {
    profileSaveMessage.textContent = "";
    profileSaveMessage.classList.remove("error-text");
    const name = profileNameInput.value.trim();
    if (!name) {
      profileSaveMessage.textContent = "プロフィール名を入力してください。";
      profileSaveMessage.classList.add("error-text");
      return;
    }

    const body = new FormData();
    body.append("csrf_token", _csrfToken());
    body.append("name", name);
    for (const field of MEASUREMENT_FIELDS) {
      const input = document.getElementById(`field-${field}`);
      body.append(field, input ? input.value : "");
    }

    try {
      const response = await fetch("/api/profiles", { method: "POST", body });
      const data = await readJsonOrThrow(response, "保存に失敗しました。");
      if (profileSelect) {
        const option = document.createElement("option");
        option.value = data.profile.id;
        option.textContent = data.profile.name;
        for (const field of MEASUREMENT_FIELDS) {
          option.dataset[field] = data.profile[field];
        }
        profileSelect.appendChild(option);
        profileSelect.value = String(data.profile.id);
        // 最初の1件を保存したときは、プロフィール選択欄自体が
        // (保存前は0件だったため)非表示のままなので、ここで表示する。
        const selectField = document.getElementById("profile-select-field");
        if (selectField) selectField.classList.remove("hidden");
      }
      profileNameInput.value = "";
      profileSaveMessage.textContent = `「${data.profile.name}」として保存しました。`;
    } catch (err) {
      profileSaveMessage.textContent = describeFetchFailure(err, "保存に失敗しました。");
      profileSaveMessage.classList.add("error-text");
    }
  });
}

/* -- 結果パネルに「まだ下がある」ことを見せる (round48) -----------------------
 *
 * 【round47まで何が起きていたか】1440×950 で生成すると、結果パネルは
 *
 *     見えている高さ 918px / 中身の高さ 1836px / **隠れている分 918px**
 *
 * ——ちょうど半分が画面の外にあった。隠れている側には、縫う順番・
 * パーツ一覧・買い物メモ・注意書きが全部入っている。
 * それでいてスクロールバーは重ねて描かれる種類なので、触るまで現れない。
 * 「PDFを落として終わり」と思われて、その先が読まれないまま終わる。
 *
 * CSSの `scrollbar-color` だけでは足りない——重ねて描く環境(macOSや、
 * この製品を検証しているheadless Chromium)では、指定しても**何も描かれない**。
 * 実測でも、指定後にスクロールバーの列を読むと全画素が #ffffff のままだった。
 * そこで「実際にあふれているか」をJSで見て、そのときだけ下端に合図を出す。
 *
 * 合図は見た目だけのもので、操作の邪魔をしない(pointer-events: none)。
 * 下まで読んだら消える。あふれていなければ最初から出ない。
 */
function updateResultPanelOverflowHint() {
  if (!resultPanel) return;
  const slack = resultPanel.scrollHeight - resultPanel.clientHeight;
  // 8px は、小数の丸めで1〜2pxだけ余る場合に合図を出さないための余裕。
  const overflowing = slack > 8;
  const atBottom = resultPanel.scrollTop >= slack - 8;
  resultPanel.classList.toggle("has-more-below", overflowing && !atBottom);
}

if (resultPanel) {
  resultPanel.addEventListener("scroll", updateResultPanelOverflowHint,
                               { passive: true });
  window.addEventListener("resize", updateResultPanelOverflowHint);
  if (typeof ResizeObserver === "function") {
    // 結果が差し込まれて高さが変わったときにも見直す。
    new ResizeObserver(updateResultPanelOverflowHint).observe(resultPanel);
  }
  updateResultPanelOverflowHint();
}
