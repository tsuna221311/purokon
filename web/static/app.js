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

const illustrationFileInput = illustrationSection.querySelector('input[name="illustration"]');
const sleeveStyleSelect = manualSection.querySelector('select[name="sleeve_style"]');
const includeCuffsInput = document.getElementById("include-cuffs-input");
const fabricStepNumber = document.getElementById("fabric-step-number");
const seamStepNumber = document.getElementById("seam-step-number");
const multiSizeSection = document.getElementById("multi-size-section");
// round10で追加: カスタムパーツ(自由形状パーツ)セクションは、現状バックエンド
// (app.pyの`/api/generate`)がイラストモード・サイズ展開モードとの併用に
// 未対応(明確なエラーを返す設計、README参照)のため、手動モードでのみ表示する。
const customPanelSection = document.getElementById("custom-panel-section");

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
  // round10で追加: カスタムパーツは手動モードのみ対応(上のコメント参照)。
  if (customPanelSection) {
    customPanelSection.classList.toggle("hidden", !isManual);
  }
  // イラストモードなのに画像を選ばず送信すると、サーバはエラーを返すが
  // (app.py側で明確な400エラーに修正済み)、ブラウザの標準フォーム検証で
  // 送信前に気付けるようにしておく方が体験として良い。
  illustrationFileInput.required = isIllustration;
  // イラストモードでは「③ パーツ構成」の見出しごと非表示になるため、
  // 直後の見出しが固定の番号のままだと表示中の見出しの並びと食い違って
  // 見える(実際に画面を見て確認して壊れて見えた不具合の再発防止)。
  // 手動モードだけ「④ カスタムパーツ」が割り込むため、その分1つずつ
  // 後ろにずれる。
  if (fabricStepNumber) {
    fabricStepNumber.textContent = isIllustration ? "③" : (isManual ? "⑤" : "④");
  }
  if (seamStepNumber) {
    seamStepNumber.textContent = isIllustration ? "④" : (isManual ? "⑥" : "⑤");
  }
}

// 袖を「なし（ノースリーブ）」にした場合、カフスは追加できない
// (engine/pipeline.py の build_garment_spec が明確なエラーを返すように
// 修正済みだが、そもそも矛盾した組み合わせを選べないようにする方が親切)。
function syncCuffsAvailability() {
  const hasSleeve = sleeveStyleSelect.value !== "";
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

sleeveStyleSelect.addEventListener("change", syncCuffsAvailability);
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
    list.appendChild(chip);
  }
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
    stats.textContent =
      `パーツ数 ${result.part_count} / 布ロス率 ${formatPercent(result.waste_ratio)} / ` +
      `使用生地丈 ${result.used_length_cm}cm`;
    box.appendChild(stats);

    const compatWarnings = Array.isArray(result.compatibility_warnings) ? result.compatibility_warnings : [];
    if (compatWarnings.length > 0) {
      const compatNote = document.createElement("p");
      compatNote.className = "hint";
      compatNote.style.margin = "0 0 8px";
      compatNote.style.color = "#92400e";
      compatNote.textContent = "⚠ " + compatWarnings.map((w) => w.message).join(" ");
      box.appendChild(compatNote);
    }

    const row = document.createElement("div");
    row.className = "download-row";
    const links = [
      ["SVGを開く", result.download.svg, "btn-outline", true],
      ["PDF", result.download.pdf, "btn-outline", false],
      ["DXF", result.download.dxf, "btn-outline", false],
    ];
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
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `輪郭の抽出に失敗しました (HTTP ${response.status})`);
    }
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
    setPanelStatus(panel, err.message || "輪郭の抽出に失敗しました。", true);
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
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-outline";
  removeBtn.textContent = "このパーツを削除";
  header.append(labelInput, quantityLabel, mirrorLabel, removeBtn);
  card.appendChild(header);

  const traceRow = document.createElement("div");
  traceRow.className = "custom-panel-trace-row";
  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
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
  referenceCmField.appendChild(referenceCmInput);
  calibBox.appendChild(referenceCmField);

  const measurementFieldBox = document.createElement("div");
  measurementFieldBox.className = "custom-panel-calib-measurement-field hidden";
  const measurementSelect = document.createElement("select");
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
    + " 頂点はドラッグで移動、ダブルクリックで個別に削除できます。";
  card.appendChild(status);

  customPanelListEl.appendChild(card);

  const panel = {
    id, card, canvas, ctx: canvas.getContext("2d"),
    img: null, points: [], refA: null, refB: null, mode: "add", dragging: null,
    els: {
      labelInput, quantityInput, mirrorInput, fileInput, autoTraceBtn,
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
  loading.classList.remove("hidden");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      body: new FormData(form),
    });
    const data = await response.json();

    if (!response.ok || !data.ok) {
      const err = new Error(data.error || `サーバーエラー (HTTP ${response.status})`);
      err.upgradeUrl = data.upgrade_url;
      throw err;
    }

    if (data.mode === "multi_size") {
      renderMultiSizeResults(data);
      updateUsageNote(data.usage);
      content.classList.add("hidden");
      multiSizeContent.classList.remove("hidden");
      loading.classList.add("hidden");
      return;
    }
    multiSizeContent.classList.add("hidden");

    document.getElementById("stat-parts").textContent = data.part_count;
    document.getElementById("stat-waste").textContent = formatPercent(data.waste_ratio);
    document.getElementById("stat-length").textContent = data.used_length_cm;
    document.getElementById("stat-width").textContent = data.fabric_width_cm;
    document.getElementById("stat-time").textContent = data.elapsed_seconds;
    document.getElementById("stat-unplaced").textContent = data.unplaced_count;

    const cacheBust = `?t=${Date.now()}`;
    document.getElementById("preview-img").src = data.download.svg + cacheBust;
    document.getElementById("download-svg").href = data.download.svg;
    document.getElementById("download-pdf").href = data.download.pdf;
    document.getElementById("download-dxf").href = data.download.dxf;

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

    const usedAi = Array.isArray(data.classification_log) && data.classification_log.length > 0;
    const aiBadge = document.getElementById("ai-badge");
    aiBadge.textContent = usedAi ? "AI使用" : "ルールベースのみ";
    aiBadge.classList.toggle("ai-badge-active", usedAi);
    aiBadge.classList.toggle("ai-badge-inactive", !usedAi);

    const dartsApplied = data.darts_applied || 0;
    document.getElementById("dart-note").classList.toggle("hidden", dartsApplied === 0);
    document.getElementById("dart-count").textContent = dartsApplied;

    renderCompareBars(data.used_length_cm, data.naive_used_length_cm || data.used_length_cm);
    renderPartsList(data.parts);
    renderClassificationLog(data.classification_log);
    updateUsageNote(data.usage);

    loading.classList.add("hidden");
    content.classList.remove("hidden");
  } catch (err) {
    loading.classList.add("hidden");
    placeholder.classList.remove("hidden");
    showError(err.message || "型紙の生成に失敗しました。", err.upgradeUrl);
  }
});

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
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.error || `保存に失敗しました (HTTP ${response.status})`);
      }
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
      profileSaveMessage.textContent = err.message || "保存に失敗しました。";
      profileSaveMessage.classList.add("error-text");
    }
  });
}
