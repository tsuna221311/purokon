"""pdf_export.py — 型紙のSVG/PDF出力（A4分割印刷対応）。

型紙PDF出力(ワンクリック)→A4分割印刷(家庭用プリンタ)→貼り合わせ(ガイドに
沿って)→裁断→縫製、という一連の流れの入口部分を実装する。

出力するのは2種類:
  1. render_layout_svg  : 生地全体を1枚で見るためのプレビューSVG（画面表示用）
  2. render_a4_pdf       : 実寸1:1でA4に分割したPDF（家庭用プリンタで印刷し、
                           貼り合わせて実物の型紙にする）
"""

from __future__ import annotations
import base64
import math
from dataclasses import dataclass
import os
import zipfile

import svgwrite
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm as CM
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError
from reportlab.pdfgen import canvas as rl_canvas

from .dxf_export import render_dxf
from .nesting import NestingResult, NestedPart

Point = tuple[float, float]

#: round57: 用紙。round53から「A3に対応していない」と限界に書き続けていた
#: (用紙寸法が73か所に直書きされていたため)。コンビニのA3はA4と同じ単価で
#: 面積は2倍なので、対応すると枚数と貼り合わせの手間がほぼ半分になる。
#:
#: **1:1の実寸を崩さないことがすべて**なので、寸法は1か所にまとめ、
#: 描画側はここから読む。A4を選んだときの出力がround56と1ページも
#: 変わらないことを、全ページの画像を突き合わせて確かめてある
#: (tests/test_round57_paper.py)。
@dataclass(frozen=True)
class Paper:
    name: str
    width_cm: float
    height_cm: float
    margin_cm: float = 1.0

    @property
    def usable_w_cm(self) -> float:
        return self.width_cm - 2 * self.margin_cm

    @property
    def usable_h_cm(self) -> float:
        return self.height_cm - 2 * self.margin_cm

    @property
    def pagesize(self) -> tuple[float, float]:
        return (self.width_cm * CM, self.height_cm * CM)


A4_PAPER = Paper("A4", 21.0, 29.7)
A3_PAPER = Paper("A3", 29.7, 42.0)
#: 画面・APIから選べる用紙(キーは小文字)。
PAPERS: dict[str, Paper] = {"a4": A4_PAPER, "a3": A3_PAPER}
DEFAULT_PAPER = A4_PAPER


def get_paper(name: str | None) -> Paper:
    """用紙名から`Paper`を返す。知らない名前は**黙って既定に落とさない**。"""
    if name is None or not str(name).strip():
        return DEFAULT_PAPER
    key = str(name).strip().lower()
    if key not in PAPERS:
        raise ValueError(
            f"用紙は{'・'.join(sorted(k.upper() for k in PAPERS))}のいずれかを"
            f"指定してください: {name!r}")
    return PAPERS[key]


A4_WIDTH_CM = 21.0
A4_HEIGHT_CM = 29.7
A4_MARGIN_CM = 1.0
A4_USABLE_W_CM = A4_WIDTH_CM - 2 * A4_MARGIN_CM
A4_USABLE_H_CM = A4_HEIGHT_CM - 2 * A4_MARGIN_CM

# A4分割PDF上のページ情報・パーツ名ラベルに使う日本語対応フォント。
#
# reportlabの組み込み標準フォント(Helvetica等)は日本語グリフを持たない。
# 以前はページ情報テキストに「枚」という文字をHelveticaのままdrawStringして
# いたため、実際に生成したPDFをレンダリングして確認すると豆腐(■)として
# 表示される実バグがあった。また、画面プレビュー(SVG)には表示される
# 「左脚/右脚/前/後」等のパーツ識別ラベルが、実際に印刷して裁断に使う
# A4分割PDF側には一切描かれていない機能不足もあった(貼り合わせた後、
# どの裁断線がどのパーツか分からなくなる)。
#
# この2点を修正するため、ASCII+ひらがな+カタカナ+必要な漢字だけに絞った
# 軽量サブセットフォント(engine/assets/pattern_label_ja_subset.ttf、
# IPAゴシックからの派生。ライセンスは同ディレクトリの
# PATTERN_LABEL_FONT_LICENSE.txt、再構築手順はscripts/build_pattern_label_font.py
# を参照)を同梱・登録している。フォントファイルが万一読めない場合でも
# クラッシュはさせず、Helveticaへフォールバックする(この場合、日本語部分は
# 文字化けするがPDF自体は生成できる)。
_JP_FONT_NAME = "PatternForgeJP"

#: round30: 基準線(バスト線・ウエスト線・ヒップ線・中心線・BP)の色。
#: 縫い線(#666)・裁断線(黒)・合印(赤)・布目線(青)のどれとも見分けが
#: つく色で、かつ「縫う線ではない」と一目で分かるよう薄くしてある。
REFERENCE_LINE_COLOR = "#8a7fb8"
REFERENCE_LINE_RGB = (0.54, 0.50, 0.72)
_JP_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "pattern_label_ja_subset.ttf")


def _register_jp_font() -> str:
    try:
        pdfmetrics.registerFont(TTFont(_JP_FONT_NAME, _JP_FONT_PATH))
        return _JP_FONT_NAME
    except (TTFError, OSError):  # pragma: no cover - フォント資産が欠けた環境向けの保険
        return "Helvetica"


_LABEL_FONT = _register_jp_font()

#: 貼り合わせ図で、枡の番号(R1-C1)に使う帯の高さ(pt)。round60で追加。
#: 番号はこの帯に白地を敷いてから描き、パーツの名前はこの帯を避ける。
#: 2か所(番号を描く側・名前を逃がす側)から読むので、値は1つにしておく
#: ——別々に書くと、片方だけ変えたときに名前がまた分断される。
_TILE_NUMBER_BAND_PT = 9.5

#: 貼り合わせ図に描くパーツ名の、いちばん大きい文字の大きさ(pt)。
#: 名前を番号の帯から逃がす計算にも使うので、1か所にまとめてある。
_MAP_LABEL_MAX_PT = 7.0


#: round54: 生地の名前によく使う漢字を、フォントに必ず収録させるための一覧。
#:
#: 生地の名前は利用者が自由に入力するので、原理的には全部は収録できない
#: (上の`unprintable_characters`のdocstring参照)。それでも、実際に
#: 打ち込まれる語はかなり狭い——色と素材の名前である。ところが実測すると、
#: **いちばんよく使う色が軒並み落ちていた**:
#:
#:     「紺サテン」  → 紺が落ちて「サテン」
#:     「金ラメ」    → 金が落ちて「ラメ」
#:     「エナメル黒」→ 黒が落ちて「エナメル」
#:
#: この一覧は文字列リテラルなので、`scripts/build_pattern_label_font.py`が
#: そのまま拾ってサブセットに入れる(PRINTED_MODULESにpdf_exportが
#: 入っている)。数十字ぶんでフォントは数KB太るだけである。
COMMON_FABRIC_NAME_CHARS = (
    "黒白赤青紺緑黄紫茶灰金銀桃橙藍朱紅"      # 色
    "濃淡明暗深"                              # 色の程度
    "綿麻絹毛革布地糸"                        # 素材
    "光沢艶厚薄硬柔"                          # 質感
    "上下内外左右前後表裏"                    # 部位・向き
    "本体差色替別共用予備"                    # 使い分け
)


def unprintable_characters(text: str) -> list[str]:
    """`text`のうち、型紙に印刷できない(サブセットフォントに無い)文字を返す。

    【なぜ要るか — round36で見つけた実害】埋め込みフォントは
    ASCII+かな+必要な漢字だけのサブセットで、収録外の文字は豆腐(□)ですら
    なく**何も描かれずに黙って消える**。固定文言なら
    `scripts/build_pattern_label_font.py`が集めて収録するので防げるが、
    **利用者が付けたカスタムパーツの名前は防げない**——何と入力されるか
    分からないし、全漢字を収録するとフォントが10MB超になる。

    実測: カスタムパーツに「薔薇の装甲」と名前を付けると、薔・薇・装・甲が
    すべて収録外のため、型紙には**「の」とだけ印刷される**。警告は
    どこにも出ず、利用者は「の」と書かれた布を裁つことになる。

    直しようがあるのは「黙って落とす」ところだけである。印刷できない文字を
    数え上げて呼び出し側へ返し、生成する前に利用者へ伝える。
    """
    if _LABEL_FONT == "Helvetica":     # フォントが読めない環境では判定しない
        return []
    try:
        from reportlab.pdfbase.pdfmetrics import getFont
        char_to_glyph = getFont(_LABEL_FONT).face.charToGlyph
    except Exception:                  # pragma: no cover - 保険
        return []
    return list(dict.fromkeys(ch for ch in text
                               if not ch.isspace() and ord(ch) not in char_to_glyph))

# パーツ識別ラベルの標準の文字サイズ(pt)と、パーツ幅に収めるために縮小する
# ときの下限(round11で追加)。下限より小さくしないのは、これ以上小さいと
# 印刷しても実際には読めず、「小さすぎて読めない文字」と「はみ出した文字」の
# どちらもラベルとして役に立たないため。下限でも収まらない場合は末尾を
# 省略記号に置き換えて詰める。
#: PDFに描画する固定文言の一覧(round11で追加)。
#:
#: 【この一覧が必要な理由】埋め込みフォントはASCII+かな+必要な漢字だけの
#: サブセット(scripts/build_pattern_label_font.py)であり、収録されていない
#: 文字をreportlabに渡すと、豆腐(□)ですらなく「何も描かれずに黙って消える」。
#: 実際、round11で全体図ページを追加した際に、追加した漢字の一部を
#: REQUIRED_KANJIへ入れ忘れ、生成PDFを画像化して初めて「記号の凡例」が
#: 「の」とだけ表示されていることに気付いた(文字が消えても例外も警告も
#: 出ないため、テストでも目視でも気付きにくい)。
#:
#: そこで、描画する固定文言をこの一覧に集約し、
#:   - scripts/build_pattern_label_font.py がここから必要な文字を集めて
#:     サブセットフォントを生成する
#:   - tests/test_pdf_export.py が「一覧の全文字がフォントに収録されている」
#:     ことを検証する
#: という形にして、文言を足したのにフォントを更新し忘れる事故を、目視では
#: なくテストで検出できるようにした。
#: (パーツ名など利用者入力を含む動的な文字列は対象外。これらはASCII+かなの
#:  範囲を前提とする従来通りの扱い。)
PDF_STATIC_TEXTS: tuple[str, ...] = (
    # 警告ページ
    "▲ 警告: 型紙が不完全です",
    "▲ 警告: 型紙に含まれていないパーツ: ",
    "採寸値を見直してください。",
    # 全体図・凡例ページ
    "貼り合わせ図と記号の凡例",
    "生地幅 ",
    "使用長 ",
    "全",
    "枚 (",
    "行 x ",
    "列)",
    "cm",
    "貼り合わせ図 (実物大ではありません)",
    "記号の凡例",
    "実線 = 裁断線",
    "この線で布を裁つ",
    "破線 = 縫い線",
    "裁断線の内側 ",
    "短い線 = 合印",
    "縫い合わせる位置の目印",
    "矢印の線 = 布目線",
    "布の縦地に平行に置く",
    "裾は ",
    "印刷は「実物大」「倍率100%」で行ってください。",
    "用紙に合わせて拡大縮小すると寸法が変わります。",
    "各ページの四隅の + 印を重ねて貼り合わせます。",
    # タイルページ
    "PatternForge  R",
    "-C",
    " / ",
    "x",
    "枚",
    "  (この面に型紙なし)",
    # round60: 型紙ページの隅の縫い代表示。英語から日本語にした。
    "縫い代 ",
    "（裾 ",
    "）",
    "(90度回転・布目確認)",
    # round33: 縫製手順ページ(engine/assembly.py の文言はそこから集める)
    "縫う順番",
    "標準的な手順です。裏地を付ける場合など、他の順番になることもあります。",
    "使うパーツ: ",
    # round33: 印刷倍率の確認(検定スクエア)
    "印刷倍率の確認",
    "この四角の1辺を定規で測ってください。5.0cm なら正しい倍率です。",
    "違っていたら、印刷設定を「実物大」「倍率100%」にして印刷し直してください。",
    # round31: 裁ち方の指示(engine/cutting.py)
    "表地1枚 わ裁ち不要 接着芯あり",
    "わ裁ち",
    # ラベルの省略記号
    "…",
)

_PART_LABEL_FONT_SIZE = 9
_PART_LABEL_MIN_FONT_SIZE = 5
_PART_LABEL_ELLIPSIS = "…"
#: round31: 裁ち方の指示は、パーツ名より一段小さく書く(パーツ名の方が
#: 「どの裁断線がどのパーツか」を伝える主役なので、大きさで区別する)。
_CUTTING_NOTE_FONT_SIZE = 7


def _label_span_cm(points: list[tuple[float, float]], y_cm: float,
                    center_x_cm: float) -> float | None:
    """パーツの輪郭の、高さ`y_cm`における**実際の幅**(cm)を返す。

    【round46で見つけた実バグ】round11はラベルを「外接矩形の幅」に収めて
    いたが、文字が描かれるのはパーツの**中央の高さ**である。袖や身頃は
    上下が広く中ほどがすぼまるので、その高さの実幅は外接矩形より狭い。
    貼り合わせ図(縮小図)で実測したところ、裏地付きの前身頃で**2.5pt**、
    後身頃で2.1pt、ラベルが裁断線の外へ出ていた(≒0.9mm)。
    大きくはないが、round11が立てた「ラベルは裁断線を越えない」という
    約束はここで破れていた。

    走査線と輪郭の交点を取り、**中央x を含む区間**の幅を返す。
    min〜max ではなく区間にするのは、その高さで輪郭が2つに割れている形
    (深い切り込みのあるパーツ)で、間の空白まで幅に数えないため。
    交点が取れない場合は None(呼び出し側は外接矩形にそのまま従う)。
    """
    crossings: list[float] = []
    n = len(points)
    if n < 3:
        return None
    for i in range(n):
        (x0, y0), (x1, y1) = points[i], points[(i + 1) % n]
        if y0 == y1:
            continue
        if (y0 - y_cm) * (y1 - y_cm) <= 0:
            crossings.append(x0 + (y_cm - y0) / (y1 - y0) * (x1 - x0))
    if len(crossings) < 2:
        return None
    crossings.sort()
    for i in range(0, len(crossings) - 1, 2):
        left, right = crossings[i], crossings[i + 1]
        if left <= center_x_cm <= right:
            return right - left
    # 中央xがどの区間にも入らない(数値誤差・特殊な形)ときは、
    # いちばん広い区間を使う。外接矩形より狭いので、安全側に倒れる。
    widths = [crossings[i + 1] - crossings[i]
              for i in range(0, len(crossings) - 1, 2)]
    return max(widths) if widths else None


def _fit_label_to_width(text: str, max_width_pt: float,
                         base_size: float = _PART_LABEL_FONT_SIZE) -> tuple[str, float]:
    """パーツ識別ラベルを、指定幅(pt)に収まる (表示文字列, 文字サイズ) にする。

    【round11で修正した実バグ】以前はパーツの幅を一切見ずに常に9ptで
    `drawCentredString`していたため、パーツの実幅よりラベルが長い場合に
    文字が裁断線の外へはみ出していた。標準パーツ(身頃・袖等)は十分に幅が
    あるため露見しなかったが、round9で追加した自由形状パーツ(custom_panel)は
    幅2cmまで許容され、しかもラベルに利用者が付けた任意の名前が入るため
    容易に起こる。実測では、幅5.0cmのパーツに対し
    `custom_panel(肩ひも(左右共通・裏地付き))`のラベルが6.35cm必要で、
    左右に約0.7cmずつはみ出していた。貼り合わせた型紙の上では、はみ出した
    文字が隣のパーツに重なり「どの裁断線がどのパーツか」が却って分から
    なくなるため、ラベルの目的そのものを損なう。

    まず文字サイズを下限(_PART_LABEL_MIN_FONT_SIZE)まで段階的に縮小し、
    それでも収まらなければ末尾を省略記号に置き換えて詰める。
    幅が取れない(極端に細いパーツ)場合でも、最低1文字+省略記号は返す。
    """
    size = base_size
    while size > _PART_LABEL_MIN_FONT_SIZE:
        if pdfmetrics.stringWidth(text, _LABEL_FONT, size) <= max_width_pt:
            return text, size
        size -= 0.5

    # 下限サイズでも収まらない場合は文字数を削る。
    if pdfmetrics.stringWidth(text, _LABEL_FONT, size) <= max_width_pt:
        return text, size
    for cut in range(len(text) - 1, 0, -1):
        candidate = text[:cut] + _PART_LABEL_ELLIPSIS
        if pdfmetrics.stringWidth(candidate, _LABEL_FONT, size) <= max_width_pt:
            return candidate, size
    return text[:1] + _PART_LABEL_ELLIPSIS, size


def _build_embedded_jp_font_face_css() -> str | None:
    """SVGプレビュー用に、PDFと同じ日本語サブセットフォントをdata URIとして
    埋め込む@font-face CSSを組み立てる。失敗したら None を返す(呼び出し側で
    フォント埋め込み無し=従来のシステムフォント指定のみにフォールバックする)。

    実際にcairosvgで生成済みのSVGプレビューをPNGへレンダリングして目視確認
    した際に見つかった実バグの修正: 以前はテキスト要素の`font-family`に
    'Noto Sans JP'等の名前を指定するだけで、実際のフォントデータは一切
    埋め込んでいなかった。ブラウザ側にこれらの名前のCJK対応フォントが
    インストールされていない環境(このリポジトリの検証で使ったサンドボックスの
    ような、日本語フォントが入っていないLinux環境等)では、パーツ識別ラベルの
    漢字部分がそのまま文字化け(豆腐/□)して表示され、「布目確認」の指示すら
    読めなくなってしまう。A4分割PDF側は既に専用フォント(_JP_FONT_PATH)を
    ファイルに埋め込むことで解決済みだったが、画面プレビュー用のSVGだけは
    この対策が漏れていた。同じサブセットフォントをbase64のdata URIとして
    SVGの<defs>内に@font-faceで埋め込み、閲覧側の環境に依存せず表示できる
    ようにする(フォント名は末尾にシステムフォントの候補も残しておき、
    埋め込みフォントに無い文字が将来増えた場合の保険とする)。
    """
    try:
        with open(_JP_FONT_PATH, "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:  # pragma: no cover - フォント資産が欠けた環境向けの保険
        return None
    return (
        f"@font-face {{ font-family: '{_JP_FONT_NAME}'; "
        f"src: url(data:font/ttf;base64,{font_b64}) format('truetype'); }}"
    )


_EMBEDDED_JP_FONT_FACE_CSS = _build_embedded_jp_font_face_css()

# SVGプレビューのテキストに使うfont-family。埋め込みフォント(_JP_FONT_NAME)を
# 最優先にし、そこに無い文字(将来ラベル文言を増やした場合の保険)のみ
# ブラウザ側のシステムフォントにフォールバックする。
_SVG_LABEL_FONT_FAMILY = (
    f"'{_JP_FONT_NAME}','Noto Sans JP','Noto Sans CJK JP','Hiragino Sans',sans-serif"
)


# ---------------------------------------------------------------------------
# プレビューSVG（生地全体を1枚で表示）
# ---------------------------------------------------------------------------

#: unplaced(配置できなかったパーツ)がある場合に、SVG/PDF冒頭へ挿入する
#: 警告帯の高さ(cm)。以前はunplacedが発生した場合でもSVG/PDFはresult.placed
#: しか描画しないため、配置できなかったパーツが出力から完全に無言で消える
#: (=画面の統計欄の数値以外、生地を裁ってから気づくまで実害に気付く手段が
#: 無い)作りだった。round11でこの警告帯を足した。
#:
#: 【round35で訂正】round11当時ここには「総当たりで確認したところunplacedは
#: 発生しない(=到達不能)」と書いていたが、round9で追加したサーキュラー
#: スカートは幅がヒップにほぼ比例するため、**その時点で既に到達可能に
#: なっていた**(実測でヒップ143cm以上、110通り中70通りでスカートが消えていた)。
#: 「一度総当たりしたから安全」という書き方が、後から入った機能で崩れる
#: ことに気付けなかった。round35で`engine/panel_split.py`を足し、分けられる
#: パーツは分けて収めるようにしたが、それでも
#:   - 分けても細くなりすぎる/MAX_PANELSを超える極端な幅
#:   - 身頃・衿など、そもそも分けてはいけない種類のパーツ
#: では今も発生しうる。**この警告帯は到達可能な経路である**。
UNPLACED_BANNER_HEIGHT_CM = 2.5


def render_layout_svg(result: NestingResult, output_path: str) -> str:
    """ネスティング結果を、生地全体が見える1枚のSVGに書き出す。"""
    width_cm = result.fabric_width_cm
    height_cm = max(result.used_length_cm, 1.0)
    banner_height_cm = UNPLACED_BANNER_HEIGHT_CM if result.unplaced else 0.0
    total_height_cm = height_cm + banner_height_cm
    dwg = svgwrite.Drawing(output_path, size=(f"{width_cm}cm", f"{total_height_cm}cm"),
                           viewBox=f"0 0 {width_cm} {total_height_cm}")
    if _EMBEDDED_JP_FONT_FACE_CSS:
        dwg.embed_stylesheet(_EMBEDDED_JP_FONT_FACE_CSS)

    # 生地レイアウト本体は、警告帯がある場合はその下にずらして描く。
    content = dwg.g(transform=f"translate(0,{banner_height_cm})") if banner_height_cm else dwg
    content.add(dwg.rect(insert=(0, 0), size=(width_cm, height_cm),
                          fill="#f5f0e8", stroke="#999", stroke_width=0.05))

    for i, placed in enumerate(result.placed):
        cut = placed.placed_cut_line()
        stitch = placed.placed_stitch_line()
        content.add(dwg.polygon(points=cut, fill="white", stroke="black",
                                 stroke_width=0.08, fill_opacity=0.9))
        content.add(dwg.polyline(points=stitch + [stitch[0]], fill="none",
                                  stroke="#666", stroke_width=0.05,
                                  stroke_dasharray="0.3,0.2"))
        for a, b in placed.placed_notches():
            content.add(dwg.line(start=a, end=b, stroke="red", stroke_width=0.08))
        # round27: パーツ内部の縫い線(ウエストのダイヤモンドダーツ等)。
        # 輪郭ではないので、裁断線と紛れないよう縫い線と同じ破線で描く。
        for line in placed.placed_internal_lines():
            content.add(dwg.polyline(points=line, fill="none", stroke="#666",
                                      stroke_width=0.05, stroke_dasharray="0.3,0.2"))
        # round30: 基準線(バスト線・ウエスト線・ヒップ線・中心線・BP)。
        # 縫う線ではないので、縫い線ともはっきり違う細い線・薄い色にする
        # (JIS L 0110 表2-40「内部線」・表1-2「中心線」・表1-12「BP」)。
        for label, line in placed.placed_reference_lines():
            if len(line) < 2:
                continue
            content.add(dwg.polyline(points=line, fill="none",
                                      stroke=REFERENCE_LINE_COLOR,
                                      stroke_width=0.035,
                                      stroke_dasharray="0.8,0.25,0.12,0.25"))
            if label:
                lx, ly = line[0]
                content.add(dwg.text(label, insert=(lx + 0.2, ly - 0.25),
                                      font_size="0.55",
                                      fill=REFERENCE_LINE_COLOR))
        grain = placed.placed_grainline()
        gx1, gy1 = grain["line"][0]
        gx2, gy2 = grain["line"][1]
        content.add(dwg.line(start=(gx1, gy1), end=(gx2, gy2), stroke="blue", stroke_width=0.06))
        for a, b in grain["arrows"]:
            content.add(dwg.line(start=a, end=b, stroke="blue", stroke_width=0.06))
        min_x, min_y, max_x, max_y = placed.bbox()
        label = placed.part.display_name
        if placed.rotated:
            # A4分割PDF側(render_a4_pdf)の同じ意味の注記と全く同じ文言に揃える。
            # 以前はここだけ「↻90°(要:布目確認)」という別の文言を使っており、
            # (1) PDFとSVGで同じ部材の注記が違う表現になる、(2) "↻"(U+21BB)・
            # "°"(U+00B0)・"要"(U+8981)が上記の埋め込みサブセットフォントには
            # 含まれておらず(test_jp_label_font_contains_every_character_the_pdf_actually_draws
            # が保証しているのはPDF側で実際に使う文字だけだったため)、フォントを
            # 埋め込んでもこの3文字だけ文字化けする、という2つの問題があった。
            label += "(90度回転・布目確認)"
        content.add(dwg.text(label, insert=((min_x + max_x) / 2, (min_y + max_y) / 2),
                              text_anchor="middle", font_size="0.9", fill="#333",
                              style=f"font-family:{_SVG_LABEL_FONT_FAMILY}"))
        # round31: 裁ち方の指示。PDF側とまったく同じ文言を使う
        # (同じ部材の注記がPDFとSVGで違う表現になると、どちらが正しいのか
        #  読み手に分からなくなる。round11の「布目確認」で実際に起きた)。
        content.add(dwg.text(placed.part.cutting_note,
                              insert=((min_x + max_x) / 2, (min_y + max_y) / 2 + 1.1),
                              text_anchor="middle", font_size="0.7", fill="#555",
                              style=f"font-family:{_SVG_LABEL_FONT_FAMILY}"))

    if banner_height_cm:
        dwg.add(content)  # 平行移動した生地レイアウト本体を、警告帯の下に追加する
        dwg.add(dwg.rect(insert=(0, 0), size=(width_cm, banner_height_cm),
                          fill="#fee2e2", stroke="#dc2626", stroke_width=0.05))
        names = "・".join(p.display_name for p in result.unplaced)
        # 文言はrender_a4_pdf側の警告ページと揃える(埋め込みサブセットフォント
        # に実際に収録されている文字だけで組み立てる。REQUIRED_KANJIのコメント
        # 参照)。
        dwg.add(dwg.text(
            f"▲ 警告: 型紙に含まれていないパーツ: {names}",
            insert=(0.3, banner_height_cm / 2 + 0.3),
            font_size="0.9", fill="#991b1b",
            style=f"font-family:{_SVG_LABEL_FONT_FAMILY}",
        ))

    dwg.save()
    return output_path


# ---------------------------------------------------------------------------
# Sutherland-Hodgman による矩形クリッピング（A4タイルへの分割用）
# ---------------------------------------------------------------------------

def _lerp_at_x(a: Point, b: Point, x: float) -> Point:
    ax, ay = a; bx, by = b
    t = 0.0 if bx == ax else (x - ax) / (bx - ax)
    return (x, ay + t * (by - ay))


def _lerp_at_y(a: Point, b: Point, y: float) -> Point:
    ax, ay = a; bx, by = b
    t = 0.0 if by == ay else (y - ay) / (by - ay)
    return (ax + t * (bx - ax), y)


def clip_polygon_to_rect(points: list[Point], xmin: float, ymin: float,
                          xmax: float, ymax: float) -> list[Point]:
    """閉じた多角形を矩形[xmin,xmax]x[ymin,ymax]でクリップする(Sutherland-Hodgman)。"""

    def clip_edge(poly: list[Point], inside, intersect) -> list[Point]:
        if not poly:
            return []
        out: list[Point] = []
        n = len(poly)
        for i in range(n):
            cur, prev = poly[i], poly[i - 1]
            cur_in, prev_in = inside(cur), inside(prev)
            if cur_in:
                if not prev_in:
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif prev_in:
                out.append(intersect(prev, cur))
        return out

    poly = points[:-1] if points and points[0] == points[-1] else list(points)
    poly = clip_edge(poly, lambda p: p[0] >= xmin, lambda a, b: _lerp_at_x(a, b, xmin))
    poly = clip_edge(poly, lambda p: p[0] <= xmax, lambda a, b: _lerp_at_x(a, b, xmax))
    poly = clip_edge(poly, lambda p: p[1] >= ymin, lambda a, b: _lerp_at_y(a, b, ymin))
    poly = clip_edge(poly, lambda p: p[1] <= ymax, lambda a, b: _lerp_at_y(a, b, ymax))
    if poly:
        poly = poly + [poly[0]]
    return poly


def _segment_in_tile(a: Point, b: Point, xmin: float, ymin: float,
                      xmax: float, ymax: float) -> bool:
    """合印などの短い線分は、中点がタイル内にあれば描画する簡易判定で十分。

    合印(notch)は裁断線上の一点を指す長さ数mm程度の短い印であり、実際の
    A4タイル1枚(27.7cm)よりずっと短いため、中点がどのタイルに属するかで
    「そのタイルに描くかどうか」を判定しても、実質的に描き漏れは起きない。
    """
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return xmin <= mx <= xmax and ymin <= my <= ymax


def _clip_segment_to_rect(a: Point, b: Point, xmin: float, ymin: float,
                           xmax: float, ymax: float) -> tuple[Point, Point] | None:
    """線分を矩形[xmin,xmax]x[ymin,ymax]でクリップする(Liang-Barsky)。

    交差しない場合はNoneを返す。布目線(grainline)の描画で使う実バグの
    修正のために追加した(下のrender_a4_pdf内のコメント参照)。合印と違い、
    布目線はパーツの縦幅いっぱいに伸びる長い線であり、A4タイル1枚の高さ
    (27.7cm)を優に超えることが多い(例: パンツの脚パーツは高さ100cm超)。
    以前は`_segment_in_tile`と同じ「線分全体の中点がこのタイルに入って
    いるかどうか」だけで判定し、入っていれば"元の(タイルでクリップして
    いない)線分"をそのまま描いていた。これは、線分の長さがタイル1枚分より
    十分短い合印には問題無いが、布目線のような長い線分では、線分全体の
    中点が属するタイル1枚にしか描かれず、実際にその線分が視覚的に通過する
    他のタイル(複数枚に渡ることが多い)には一切描かれない、という実バグに
    なっていた。実際に生成したPDFの各ページのcontent streamを検査して、
    高さ72cmの縦長パーツ(A4タイル6枚分に相当)で、布目線の色(青
    "0 0 .8 RG")が全6ページ中1ページにしか出現しないことを確認して発見した。
    貼り合わせて使う大きなパーツほど、布目(生地の縦地)を確認する手段が
    ほとんど無くなってしまう、実用上重要な不具合だった。
    """
    x0, y0 = a
    x1, y1 = b
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return None
            if r < t1:
                t1 = r
    if t0 > t1:
        return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


# ---------------------------------------------------------------------------
# A4分割PDF（実寸1:1）
# ---------------------------------------------------------------------------

def _to_page_xy(local_x: float, local_y: float, paper: Paper = DEFAULT_PAPER) -> tuple[float, float]:
    """タイル内ローカル座標(cm, 上原点でY下方向)を、PDFページ座標(pt, 下原点でY上方向)に変換。"""
    px = (paper.margin_cm + local_x) * CM
    py = (paper.height_cm - paper.margin_cm - local_y) * CM
    return (px, py)


#: 印刷倍率を確かめるための正方形の1辺(cm)。round33で追加。
#:
#: 【なぜ「倍率100%で印刷してください」という文だけでは足りないか】
#: この型紙は「実寸1:1で印刷して、そのまま裁断に使える」ことを中心的な
#: 主張にしている。ところがPDF側にあったのはその**お願いの文だけ**で、
#: 実際にそうなったかを**確かめる手段が無かった**。家庭用プリンタの既定は
#: 多くが「用紙に合わせる」で、A4原稿をA4に印刷しても数%縮む機種がある。
#: 縮んだことに気づくのは布を裁ったあと——やり直しの費用がいちばん高い
#: 段階である。市販のPDF型紙には必ずこの四角が入っている。
#:
#: 5cmにしたのは、A4の余白に収まり、かつ一般的な定規(15cm/30cm)で
#: 端から測りやすい長さだから。1cmでは印刷誤差を読み取れない
#: (2%の縮みは0.02cm=目視不能)が、5cmなら0.1cm=2%として見分けられる。
SCALE_CHECK_SQUARE_CM = 5.0


def _draw_scale_check_square(c, left_cm: float, top_cm: float, paper: Paper = DEFAULT_PAPER) -> None:
    """印刷倍率を確かめるための、1辺`SCALE_CHECK_SQUARE_CM`の正方形を描く。

    使う人は、印刷した紙の上でこの四角の1辺を定規で測る。5.0cmでなければ
    プリンタの倍率設定が「実物大/100%」になっていないので、型紙全体が
    その割合でずれている。
    """
    side = SCALE_CHECK_SQUARE_CM
    x0 = left_cm * CM
    y0 = (paper.height_cm - top_cm - side) * CM

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 9)
    c.drawString(x0, (paper.height_cm - top_cm + 0.25) * CM, "印刷倍率の確認")

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1.0)
    c.setDash()
    c.rect(x0, y0, side * CM, side * CM, stroke=1, fill=0)

    # 1cmごとの目盛り(下辺と左辺)。定規が手元に無くても、目盛りの数で
    # おおよその狂いに気づける。
    c.setLineWidth(0.4)
    c.setStrokeColorRGB(0.55, 0.55, 0.55)
    for i in range(1, int(side)):
        c.line(x0 + i * CM, y0, x0 + i * CM, y0 + 0.25 * CM)
        c.line(x0, y0 + i * CM, x0 + 0.25 * CM, y0 + i * CM)

    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.setFont(_LABEL_FONT, 7.5)
    c.drawString(x0, y0 - 0.45 * CM,
                 f"この四角の1辺を定規で測ってください。{side:.0f}.0cm なら正しい倍率です。")
    c.drawString(x0, y0 - 0.85 * CM,
                 "違っていたら、印刷設定を「実物大」「倍率100%」にして印刷し直してください。")


def printed_tile_cells(result: NestingResult, include_empty_tiles: bool = False,
                        paper: Paper = DEFAULT_PAPER
                        ) -> tuple[int, int, list[tuple[int, int]]]:
    """A4分割PDFが実際に印刷する面を数える(行数, 列数, 面の一覧)。

    面の一覧は0始まりの`(行, 列)`。型紙が1本も載らない面は含まない
    (round53。それまでは白紙のまま1ページ割り当てていた)。

    **画面に出す枚数もここから取る**。PDFを作る側と画面側で別々に
    数えると、「30枚と書いてあるのに28枚しか出ない」ことが起きる。
    """
    cols = max(1, math.ceil(result.fabric_width_cm / paper.usable_w_cm))
    rows = max(1, math.ceil(result.used_length_cm / paper.usable_h_cm)) if result.used_length_cm else 1
    if include_empty_tiles:
        # round57: 「格子をそろえて全面ほしい」人向け。round53で白紙を
        # 省くようにしたとき、選ぶ余地を作っていなかった。
        return rows, cols, [(r, c) for r in range(rows) for c in range(cols)]
    cells = [
        (row, col)
        for row in range(rows) for col in range(cols)
        if _tile_has_content(result, col * paper.usable_w_cm, row * paper.usable_h_cm,
                              (col + 1) * paper.usable_w_cm, (row + 1) * paper.usable_h_cm)
    ]
    if not cells:
        # 【round56で直した、round53の取りこぼし】
        # 1面も型紙が載らないとき、`render_a4_pdf`は0ページのPDFを作らない
        # ために**格子をそのまま全面出す**。ところがこの関数は0を返して
        # いたので、画面には「型紙が0枚」と出るのに、開くと6ページある、
        # という食い違いになっていた。
        # 実測: マント(幅173cm)がどの生地幅にも収まらなかったとき、
        #       画面「0枚」/ PDFの型紙の面 6枚。
        # 数えるのはPDFを作る側と同じ結論でなければ意味がない。
        return rows, cols, [(row, col) for row in range(rows) for col in range(cols)]
    return rows, cols, cells


def _tile_has_content(result: NestingResult, tile_x0: float, tile_y0: float,
                       tile_x1: float, tile_y1: float) -> bool:
    """この面(A4 1枚ぶんの範囲)に、型紙の線が1本でも載るか。

    判定はタイルを描く側とまったく同じ`clip_polygon_to_rect`で行う——
    別々の式で判定すると、「載っていると思って白紙を出す」か「載って
    いるのに出さない」のどちらかが必ず起きる。後者は**型紙が欠ける**ので、
    紙が1枚無駄になるより桁違いに悪い。

    パーツが面より大きく、面を完全に覆う場合(大きなスカートの内側など)も、
    Sutherland-Hodgmanの切り取りは面の矩形そのものを返して3点以上になる
    ため、ここでTrueになる。

    裁断線だけを見ればよい。縫い線・内部線・基準線・合印・布目線・名前は
    すべて裁断線の**内側**にあるので、それらが載る面には必ず裁断線も載る。
    この前提は`test_round53_printing.py`の
    `test_the_stitch_line_never_escapes_the_cut_line`が体型と縫い代幅を
    振って確かめている(縫い代0でも裁断線と縫い線は一致するだけで、
    外には出ない)。
    """
    for placed in result.placed:
        cut = clip_polygon_to_rect(placed.placed_cut_line(),
                                    tile_x0, tile_y0, tile_x1, tile_y1)
        if len(cut) >= 3:
            return True
    return False


def _draw_overview_page(c, result: NestingResult, rows: int, cols: int,
                         seam_allowance_cm: float,
                         hem_seam_allowance_cm: float | None,
                         printed_cells: set | None = None,
                         fabric_name: str | None = None,
                         paper: Paper = DEFAULT_PAPER) -> None:
    """A4分割PDFの先頭に「全体図 + 記号の凡例」の1枚を描く(round11で追加)。

    それまでのPDFは、いきなり実寸1:1のタイルページが並ぶ構成だった。この
    構成には、実際に印刷して使う側から見て2つの不便があった:

      1. 何枚を、どの並びで貼り合わせるのかが、全ページを見比べるまで
         分からない。各タイルの隅には`R{行}-C{列} / {行}x{列}枚`という
         目印を入れていたが、これは「今どこにいるか」しか伝えず、全体像
         (どのパーツがどのあたりに来るか)は分からない。
      2. 線種・記号(実線=裁断線、破線=縫い線、短い線分=合印、長い矢印線=
         布目線)の意味がPDF内のどこにも書かれておらず、READMEを読んだ人
         にしか伝わらない。印刷した紙だけが手元にある状況では解読できない。

    このページは、その2点を印刷物の中で完結させるためのもの。左側に
    生地全体を縮小した貼り合わせ図(タイルの区切りと行列番号、パーツの
    配置と名前)を、右側に記号の凡例を描く。実寸ではないことを明示する
    ため、図の見出しに「実物大ではありません」と添える。
    """
    margin = paper.margin_cm
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 15)
    # round54: 生地が2種類以上あるときは、**見出しそのもの**を生地の名前に
    # する。同じ見た目のPDFが何本も手元に来るので、開いた瞬間に
    # どちらの生地の型紙かが分からないと選べない。
    c.drawString(margin * CM, (paper.height_cm - margin - 0.5) * CM,
                 f"「{fabric_name}」から裁つ型紙" if fabric_name
                 else "貼り合わせ図と記号の凡例")

    c.setFont(_LABEL_FONT, 9)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    # round53: 「全48枚」と書きながら、そのうち7枚は白紙だった。
    # 実際に印刷される枚数を書く(白紙は出さなくなったため)。
    sheets = rows * cols if printed_cells is None else len(printed_cells)
    empty = rows * cols - sheets
    summary = (f"生地幅 {result.fabric_width_cm:.0f}cm / 使用長 {result.used_length_cm:.0f}cm"
               f" / 全{sheets}枚 ({rows}行 x {cols}列)")
    if empty > 0:
        # 記号(※など)はサブセットフォントに入っていないと**黙って消える**
        # ので、既に印刷実績のある文字だけで書く(round11・round38の事故)。
        summary += f" / 型紙の載らない{empty}枚は省いています"
    c.drawString(margin * CM, (paper.height_cm - margin - 1.2) * CM, summary)

    # --- 上: 貼り合わせ図(縮小) ------------------------------------------
    # 生地は「幅150cm×長さ87cm」のように横長になることが多く、縮小図を
    # ページの左半分に収めると図が小さくなりすぎる。ページ幅いっぱいを
    # 使って描き、凡例はその下に置く。
    map_top_cm = margin + 2.2
    map_left_cm = margin
    map_w_cm = paper.usable_w_cm
    # 図は縦にページの半分程度までとし、残りを凡例に充てる。
    map_h_cm = (paper.height_cm - map_top_cm - margin) * 0.55
    sheet_w_cm = cols * paper.usable_w_cm
    sheet_h_cm = rows * paper.usable_h_cm
    scale = min(map_w_cm / sheet_w_cm, map_h_cm / sheet_h_cm) if sheet_w_cm and sheet_h_cm else 1.0

    def _map_xy(x_cm: float, y_cm: float) -> tuple[float, float]:
        """生地座標(cm, 上原点)を、縮小図のPDFページ座標(pt)に変換する。"""
        return ((map_left_cm + x_cm * scale) * CM,
                (paper.height_cm - map_top_cm - y_cm * scale) * CM)

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 10)
    c.drawString(map_left_cm * CM, (paper.height_cm - map_top_cm + 0.35) * CM,
                 "貼り合わせ図 (実物大ではありません)")

    # 生地全体の外枠
    x0, y0 = _map_xy(0, 0)
    x1, y1 = _map_xy(result.fabric_width_cm, max(result.used_length_cm, 0.1))
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.8)
    c.rect(x0, y1, x1 - x0, y0 - y1, stroke=1, fill=0)

    # パーツの輪郭(裁断線)と名前
    for placed in result.placed:
        cut = placed.placed_cut_line()
        if len(cut) < 3:
            continue
        path = c.beginPath()
        first = _map_xy(cut[0][0], cut[0][1])
        path.moveTo(*first)
        for x_cm, y_cm in cut[1:]:
            path.lineTo(*_map_xy(x_cm, y_cm))
        path.close()
        c.setStrokeColorRGB(0.15, 0.15, 0.15)
        c.setFillColorRGB(0.90, 0.93, 0.97)
        c.setLineWidth(0.5)
        c.drawPath(path, stroke=1, fill=1)

        min_x, min_y, max_x, max_y = placed.bbox()
        cx_cm, cy_cm = (min_x + max_x) / 2, (min_y + max_y) / 2
        # round60: 枡の番号は各枡の左上に描く(下記)。パーツの名前が
        # ちょうどその高さに来ると、名前が番号の白地で分断される
        # (実測: 「スカート（フレア） 前」が「カート」「レア）」に割れた)。
        # 名前を番号の帯の下へ逃がす。パーツの真ん中付近で数mm動かすだけ
        # なので、どのパーツの名前かは変わらない。
        #
        # 逃がす量は「番号の帯」＋「名前そのものの高さ」である。
        # 【一度間違えた】帯のぶんだけ下げれば足りると思って書いたが、
        # `drawCentredString`が置くのは**文字の下端(ベースライン)**なので、
        # 文字は そこから上へ伸びて帯に食い込む。実際に刷って見たら
        # 名前はまだ分断されたままだった。文字の高さぶんも足す
        # (実際に使う大きさは下で決まるが、上限の`_MAP_LABEL_MAX_PT`で
        #  見ておけば、どの大きさになっても食い込まない)。
        clearance_pt = _TILE_NUMBER_BAND_PT + _MAP_LABEL_MAX_PT
        band_cm = clearance_pt / (scale * CM) if scale > 0 else 0.0
        row_top_cm = math.floor(cy_cm / paper.usable_h_cm) * paper.usable_h_cm
        if cy_cm - row_top_cm < band_cm:
            shifted = row_top_cm + band_cm
            # パーツからはみ出してまで逃がさない(はみ出すと、どのパーツの
            # 名前か分からなくなる)。入らないときは動かさない。
            if shifted <= max_y:
                cy_cm = shifted
        lx, ly = _map_xy(cx_cm, cy_cm)
        label = placed.part.display_name
        # 縮小図では実寸よりさらに幅が狭くなるため、実寸ページと同じ
        # 収まり調整(_fit_label_to_width)を縮小後の幅に対して行う。
        # round46: 外接矩形ではなく、**文字を描く高さでの実幅**に合わせる
        # (`_label_span_cm`のdocstringに実測値と経緯)。
        usable_cm = _label_span_cm(cut, cy_cm, cx_cm)
        if usable_cm is None:
            usable_cm = max_x - min_x
        text, size = _fit_label_to_width(label, usable_cm * scale * CM)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont(_LABEL_FONT, max(4.0, min(size, _MAP_LABEL_MAX_PT)))
        c.drawCentredString(lx, ly, text)

    # --- タイルの区切りと行列番号は、パーツの**上**に描く(round60) ---
    #
    # 【round59まで何が起きていたか】ここはパーツより前に描いていた。
    # パーツは薄い水色で**塗りつぶして**描かれるので、その上に来る番号と
    # 区切り線は塗りに消される。実測(バスト88・フレアスカート、49枚):
    #
    #     印刷する面 49枚 のうち、番号が読めない面 33枚（67%）
    #
    # しかも消えるのは**型紙が載っている紙**の番号ばかりで、読めるのは
    # 余白だけの紙だった。貼り合わせ図は「どの紙がどこに来るか」の索引
    # なのに、いちばん位置を間違えてはいけない紙の番号が見えない。
    # 区切り線も同じで、1枚のパーツが何枚の紙にまたがるのかが読めなかった。
    #
    # 索引は図の上に重ねる。番号は白地を敷いてから描く——水色の塗りや
    # 黒い裁断線の上に直に置くと、今度は文字が線に紛れる。
    # 白地の高さは`_TILE_NUMBER_BAND_PT`。パーツの名前はこの帯を避ける
    # (上のパーツ名の描画を参照)。
    c.setFont(_LABEL_FONT, 6)
    for row in range(rows):
        for col in range(cols):
            tx0, ty0 = _map_xy(col * paper.usable_w_cm, row * paper.usable_h_cm)
            tx1, ty1 = _map_xy((col + 1) * paper.usable_w_cm, (row + 1) * paper.usable_h_cm)
            c.setDash(2, 2)
            c.setStrokeColorRGB(0.55, 0.55, 0.55)
            c.setLineWidth(0.4)
            c.rect(tx0, ty1, tx1 - tx0, ty0 - ty1, stroke=1, fill=0)
            c.setDash()
            c.setLineWidth(0.8)
            # round53: 印刷しない面には番号を書かない。
            # 貼り合わせ図は「どの紙がどこに来るか」の索引なので、手元に
            # 来ない紙の番号が載っていると「印刷に失敗したのでは」と
            # 探させることになる。枡そのものは残す(型紙が無い場所だと
            # 分かる方が、図が歯抜けになるより読みやすい)。
            if printed_cells is not None and (row, col) not in printed_cells:
                continue
            number = f"R{row + 1}-C{col + 1}"
            text_w = c.stringWidth(number, _LABEL_FONT, 6)
            c.setFillColorRGB(1, 1, 1)
            c.rect(tx0 + 1, ty0 - _TILE_NUMBER_BAND_PT + 1.5,
                   text_w + 2, _TILE_NUMBER_BAND_PT - 1.5, stroke=0, fill=1)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.drawString(tx0 + 2, ty0 - 8, number)

    # --- 下: 記号の凡例 ----------------------------------------------------
    # 縮小図が実際に占めた高さの分だけ下げてから凡例を描く(横長の生地では
    # 図が薄くなるため、固定位置にすると無駄な空白ができる)。
    # タイルの区切りは生地の実長より下まで伸びる(最終行の余りの部分)。
    # 凡例の位置は、生地の外枠ではなくタイル区切りまで含めた実際の描画範囲を
    # 基準に決める(そうしないと区切り線が凡例の文字に重なる)。
    used_map_h_cm = min(map_h_cm, max(sheet_h_cm, result.used_length_cm, 0.1) * scale)
    legend_left_cm = map_left_cm
    legend_top_cm = map_top_cm + used_map_h_cm + 1.4
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 10)
    c.drawString(legend_left_cm * CM, (paper.height_cm - legend_top_cm + 0.35) * CM, "記号の凡例")

    sample_w_cm = 1.6
    line_gap_cm = 1.25
    entries = [
        ("cut", "実線 = 裁断線", "この線で布を裁つ"),
        ("stitch", "破線 = 縫い線", f"裁断線の内側 {seam_allowance_cm}cm"),
        ("notch", "短い線 = 合印", "縫い合わせる位置の目印"),
        ("grain", "矢印の線 = 布目線", "布の縦地に平行に置く"),
    ]
    if hem_seam_allowance_cm is not None and hem_seam_allowance_cm != seam_allowance_cm:
        entries[1] = ("stitch", "破線 = 縫い線",
                      f"裁断線の内側 {seam_allowance_cm}cm (裾は {hem_seam_allowance_cm}cm)")

    for i, (kind, title, note) in enumerate(entries):
        y_cm = legend_top_cm + 0.6 + i * line_gap_cm
        sx0 = legend_left_cm * CM
        sx1 = (legend_left_cm + sample_w_cm) * CM
        sy = (paper.height_cm - y_cm) * CM

        if kind == "cut":
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(1.0)
            c.line(sx0, sy, sx1, sy)
        elif kind == "stitch":
            c.setStrokeColorRGB(0.55, 0.55, 0.55)
            c.setLineWidth(0.7)
            c.setDash(2, 2)
            c.line(sx0, sy, sx1, sy)
            c.setDash()
        elif kind == "notch":
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(1.0)
            mid = (sx0 + sx1) / 2
            c.line(sx0, sy, sx1, sy)
            c.setStrokeColorRGB(0.8, 0.1, 0.1)
            c.line(mid, sy - 4, mid, sy + 4)
        else:  # grain
            c.setStrokeColorRGB(0, 0, 0.8)
            c.setLineWidth(0.8)
            c.line(sx0, sy, sx1, sy)
            for tip_x, dx in ((sx0, 4), (sx1, -4)):
                c.line(tip_x, sy, tip_x + dx, sy + 3)
                c.line(tip_x, sy, tip_x + dx, sy - 3)

        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, 9)
        c.drawString(sx1 + 0.3 * CM, sy - 3, title)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont(_LABEL_FONT, 7.5)
        c.drawString(sx1 + 0.3 * CM, sy - 12, note)

    # 印刷時の注意(実寸で印刷しないと型紙として使えないため)。凡例の右隣に
    # 置いて、縦方向を使いすぎないようにする。
    notes_left_cm = legend_left_cm + 9.0
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 10)
    c.drawString(notes_left_cm * CM, (paper.height_cm - legend_top_cm + 0.35) * CM, "印刷と貼り合わせ")
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.setFont(_LABEL_FONT, 8)
    for i, line in enumerate([
        "印刷は「実物大」「倍率100%」で行ってください。",
        "用紙に合わせて拡大縮小すると寸法が変わります。",
        "各ページの四隅の + 印を重ねて貼り合わせます。",
    ]):
        c.drawString(notes_left_cm * CM, (paper.height_cm - legend_top_cm - 0.5 - i * 0.5) * CM, line)

    _draw_scale_check_square(c, notes_left_cm, legend_top_cm + 2.4, paper)

    c.showPage()


#: 縫製手順ページの本文の折り返し幅(1行あたりの全角文字数の目安)。
#: A4の使用幅18cmに9ptで全角を並べると約29字入るので、余白を見て28字。
_ASSEMBLY_WRAP_CHARS = 28


def _wrap_ja(text: str, width: int) -> list[str]:
    """日本語の本文を、指定した文字数で折り返す。

    日本語には単語区切りが無いので単純に文字数で折るが、行頭に来ると
    読みにくい約物(。、)」など)だけは前の行へぶら下げる(禁則処理の
    いちばん基本的な部分)。
    """
    forbidden_at_start = "。、）」』】〉》!?,.:;・ー"
    lines: list[str] = []
    current = ""
    for ch in text:
        can_break = (len(current) >= width and ch not in forbidden_at_start
                     # 半角の英数(「2.0cm」「BP」など)の途中では折らない。
                     # 実測: 「約2.0cm縮めます」が「約2.0c / m縮めます」に
                     # 割れて、印刷した紙の上で読めなかった。
                     and not (ch.isascii() and ch.isalnum()
                              and current and current[-1].isascii()
                              and (current[-1].isalnum() or current[-1] == ".")))
        if can_break:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines


def _draw_assembly_pages(c, steps: list, paper: Paper = DEFAULT_PAPER) -> None:
    """縫製手順のページを描く(round33で追加)。

    【なぜ画面だけでは足りないか】縫うときに見ているのは布と紙であって
    ブラウザではない。型紙を印刷して机に広げた状態で手順が手元に無いと、
    結局どこかに書き写すことになる。A4分割PDFの中に入れておけば、
    型紙と手順が必ず一緒に届く。

    内容そのものは`engine/assembly.py`が組み立てる(このエンジンが実際に
    知っている数字——ダーツ本数・縫い代・いせ込み量——を埋め込んだもの)。
    ここはその描画だけを担う。
    """
    if not steps:
        return
    margin = paper.margin_cm
    y_cm = margin + 0.5

    def _new_page() -> float:
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, 15)
        c.drawString(margin * CM, (paper.height_cm - margin - 0.5) * CM, "縫う順番")
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont(_LABEL_FONT, 8)
        c.drawString(margin * CM, (paper.height_cm - margin - 1.1) * CM,
                     "標準的な手順です。裏地を付ける場合など、他の順番になることもあります。")
        return margin + 1.9

    y_cm = _new_page()
    for step in steps:
        body = _wrap_ja(step.detail, _ASSEMBLY_WRAP_CHARS)
        parts_line = ("使うパーツ: " + "・".join(step.parts)) if step.parts else ""
        parts_lines = _wrap_ja(parts_line, _ASSEMBLY_WRAP_CHARS + 4) if parts_line else []
        needed = 0.75 + len(body) * 0.42 + len(parts_lines) * 0.42 + 0.35
        if y_cm + needed > paper.height_cm - margin:
            c.showPage()
            y_cm = _new_page()

        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, 11)
        c.drawString(margin * CM, (paper.height_cm - y_cm) * CM,
                     f"{step.number}. {step.title}")
        y_cm += 0.68

        c.setFillColorRGB(0.25, 0.25, 0.25)
        c.setFont(_LABEL_FONT, 9)
        for line in body:
            c.drawString((margin + 0.5) * CM, (paper.height_cm - y_cm) * CM, line)
            y_cm += 0.42

        if parts_lines:
            c.setFillColorRGB(0.45, 0.45, 0.45)
            c.setFont(_LABEL_FONT, 8)
            for line in parts_lines:
                c.drawString((margin + 0.5) * CM, (paper.height_cm - y_cm) * CM, line)
                y_cm += 0.42
        y_cm += 0.35

    c.showPage()


def _draw_shopping_page(c, memo, paper: Paper = DEFAULT_PAPER) -> None:
    """買い物メモのページを描く(round38で追加)。

    【なぜ紙に入れるか】このページを見るのは**生地屋の店先**である。
    画面だけに出しても、店で見返すには結局どこかに書き写すことになる。
    型紙と一緒に必ず届くよう、実寸タイルの前に入れる。

    内容は`engine/fabric.py`が組み立てる。ここは描画だけを担う。
    """
    if memo is None or not getattr(memo, "widths", None):
        return
    margin = paper.margin_cm
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 15)
    c.drawString(margin * CM, (paper.height_cm - margin - 0.5) * CM, "買い物メモ")
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.setFont(_LABEL_FONT, 8)
    c.drawString(margin * CM, (paper.height_cm - margin - 1.1) * CM,
                 "この型紙を裁つのに必要な量です。店でこのページを見せられます。")
    y_cm = margin + 2.0

    # --- 生地幅ごとの表 ---
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 11)
    c.drawString(margin * CM, (paper.height_cm - y_cm) * CM, "表地")
    y_cm += 0.7

    col_x = [margin + 0.5, margin + 4.0, margin + 8.0, margin + 12.0]
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont(_LABEL_FONT, 8)
    for x_cm, label in zip(col_x, ("生地幅", "買う長さ", "実際に使う長さ", "布ロス率")):
        c.drawString(x_cm * CM, (paper.height_cm - y_cm) * CM, label)
    y_cm += 0.5

    for width in memo.widths:
        recommended = width.width_cm == memo.recommended_width_cm
        if recommended:
            c.setFillColorRGB(0.23, 0.29, 0.56)
            c.setFont(_LABEL_FONT, 10)
        else:
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.setFont(_LABEL_FONT, 9)
        cells = [f"{width.width_cm:.0f}cm"]
        if width.all_parts_fit:
            cells += [f"{width.buy_length_cm}cm",
                       f"{width.used_length_cm:.0f}cm",
                       f"{width.waste_ratio * 100:.0f}%"]
        else:
            # 収まらない幅に長さを書くと「その長さで作れる」と読めてしまう。
            cells += ["この幅では収まりません", "", ""]
        for x_cm, text in zip(col_x, cells):
            c.drawString(x_cm * CM, (paper.height_cm - y_cm) * CM, text)
        if recommended:
            c.setFont(_LABEL_FONT, 8)
            # 表の右端のすぐ隣に置く。離すと、どの行に掛かる印なのか
            # 分からなくなる(実際に描いて確かめた)。
            c.drawString((margin + 14.6) * CM, (paper.height_cm - y_cm) * CM, "いちばん短い")
        y_cm += 0.55
    y_cm += 0.5

    # --- 接着芯 ---
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 11)
    c.drawString(margin * CM, (paper.height_cm - y_cm) * CM, "接着芯")
    y_cm += 0.65
    c.setFillColorRGB(0.25, 0.25, 0.25)
    c.setFont(_LABEL_FONT, 9)
    if memo.interfacing_length_cm > 0:
        line = (f"幅{memo.interfacing_width_cm:.0f}cm を "
                f"{memo.interfacing_length_cm}cm")
    else:
        line = "この構成では要りません"
    c.drawString((margin + 0.5) * CM, (paper.height_cm - y_cm) * CM, line)
    y_cm += 0.8

    # --- ファスナー(round68) ---
    # 縫う順番は「前開きファスナーを付ける」と言うのに、round67まで
    # この紙にファスナーは一度も出てこなかった。生地屋でこのページを
    # 見て買う人は、生地と接着芯だけ買って帰ることになる。
    # 長さの選び方・詰め方は注記(engine/fabric.pyのfront_opening_note)に
    # 出典付きで入っているので、ここは数字だけを見出しの下に置く。
    if getattr(memo, "front_opening_cm", None):
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, 11)
        c.drawString(margin * CM, (paper.height_cm - y_cm) * CM, "ファスナー")
        y_cm += 0.65
        c.setFillColorRGB(0.25, 0.25, 0.25)
        c.setFont(_LABEL_FONT, 9)
        c.drawString((margin + 0.5) * CM, (paper.height_cm - y_cm) * CM,
                     f"前中心の開き {memo.front_opening_cm:.1f}cm"
                     "（これ以上の長さのものを選びます）")
        y_cm += 0.8

    # --- 注記 ---
    for note in memo.notes:
        lines = _wrap_ja(note, _ASSEMBLY_WRAP_CHARS + 12)
        if y_cm + len(lines) * 0.42 + 0.4 > paper.height_cm - margin:
            break      # 1ページに収まらない分は画面側で読める
        c.setFillColorRGB(0.25, 0.25, 0.25)
        c.setFont(_LABEL_FONT, 8.5)
        for line in lines:
            c.drawString((margin + 0.3) * CM, (paper.height_cm - y_cm) * CM, line)
            y_cm += 0.42
        y_cm += 0.25

    # --- 向いている生地 ---
    if memo.suggestions and y_cm + 1.5 < paper.height_cm - margin:
        y_cm += 0.3
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, 11)
        c.drawString(margin * CM, (paper.height_cm - y_cm) * CM, "向いている生地")
        y_cm += 0.65
        for item in memo.suggestions:
            lines = _wrap_ja(f"{item.part_label}: {item.text}",
                              _ASSEMBLY_WRAP_CHARS + 12)
            # 出典は必ず添える。どこから来た助言なのかが分からないと、
            # 利用者は自分で確かめようがない。URLはASCIIなので折り返さない。
            if y_cm + (len(lines) + 1) * 0.42 + 0.3 > paper.height_cm - margin:
                break
            c.setFillColorRGB(0.25, 0.25, 0.25)
            c.setFont(_LABEL_FONT, 8.5)
            for line in lines:
                c.drawString((margin + 0.3) * CM, (paper.height_cm - y_cm) * CM, line)
                y_cm += 0.42
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.setFont(_LABEL_FONT, 7)
            c.drawString((margin + 0.6) * CM, (paper.height_cm - y_cm) * CM,
                         f"出典: {item.source_url}")
            y_cm += 0.55

    c.showPage()


def _draw_fabric_section(c, result: NestingResult,
                          seam_allowance_cm: float,
                          hem_seam_allowance_cm: float | None,
                          assembly_steps: list | None,
                          shopping_list,
                          fabric_name: str | None,
                          include_empty_tiles: bool,
                          paper: Paper) -> None:
    """1つの生地ぶんを、渡されたキャンバスへ描く(round57で切り出した)。

    round56まで、この中身は`render_a4_pdf`に直接書かれていた。生地を
    分けたときに**生地の数だけ別のPDF**ができるのは、そのためである
    (コンビニで2色なら2ファイル送ることになる)。1つのキャンバスへ
    続けて描けるように切り出して、`render_combined_pdf`が生地ごとの章を
    1本にまとめられるようにした。

    **切り出しただけで、描く内容は1行も変えていない。** A4・1種類の
    生地での出力が、round56と1ページも変わらないことを全ページの画像で
    確かめてある(tests/test_round57_paper.py)。
    """
    rows, cols, printed_cells = printed_tile_cells(
        result, include_empty_tiles=include_empty_tiles, paper=paper)

    skipped_tiles: list[tuple[int, int]] = []
    # round56: 出す面は`printed_tile_cells`が返した一覧**そのもの**にする。
    #
    # round53では、数える側(printed_tile_cells)と出す側(ここ)が別々に
    # `_tile_has_content`を呼んでいた。同じ式なので普段は一致するが、
    # 「1面も載らないときは0ページにしないために全面出す」という逃げ道が
    # 出す側にだけあったため、**画面は0枚・PDFは6枚**という食い違いが
    # 残っていた(実測: どの生地幅にも収まらないマント)。
    # 一覧を共有すれば、食い違いようがない。
    cells_to_print = set(printed_cells)

    # 実寸タイルの前に、全体図と記号の凡例のページを1枚置く(round11で追加。
    # `_draw_overview_page`のdocstring参照)。配置できたパーツが1つも無い
    # 場合は縮小図に描くものが無いため省く。
    if result.placed:
        _draw_overview_page(c, result, rows, cols, seam_allowance_cm, hem_seam_allowance_cm,
                            printed_cells=set(printed_cells), fabric_name=fabric_name,
                            paper=paper)
        # round38: 買い物メモ。見るのは生地屋の店先なので、紙に要る。
        _draw_shopping_page(c, shopping_list, paper)
        # round33: 縫う順番。型紙と一緒に必ず届くよう、実寸タイルの前に置く。
        _draw_assembly_pages(c, assembly_steps or [], paper)

    if result.unplaced:
        # 配置できなかったパーツがある場合、貼り合わせ用のタイルページより
        # 前に警告専用の1枚を挿入する。SVGプレビュー(render_layout_svg)側の
        # 警告帯と同じ理由で、実際に印刷して使うこのPDF自体にも記録を残す
        # (UNPLACED_BANNER_HEIGHT_CMのコメント参照。round34まで「到達不能」と
        # 書いていたが実際には到達可能だった。round35で分割を入れた今も、
        # 分けられない種類・分けても収まらない幅では発生する)。
        # 文言は、埋め込みサブセットフォント(_LABEL_FONT)に実際に収録されて
        # いる文字だけで組み立てる(REQUIRED_KANJIのコメント参照。この警告
        # 自体が上のコメントで説明した「新しい漢字を使うラベルを追加した場合」
        # の実例で、含/不/完/全/配/置/採/寸/見/直の10字を追加した)。
        c.setFillColorRGB(0.8, 0.09, 0.09)
        c.setFont(_LABEL_FONT, 14)
        # 【round11で気付いた既存の不具合】ここは以前 "⚠ 型紙が不完全です" と
        # 描いていたが、⚠(U+26A0)は元フォント(IPAゴシック)自体に収録が無く、
        # サブセットにも入らないため、実際のPDFでは警告記号だけが黙って
        # 消えていた(全体図ページを追加した際にPDFを画像化して発見)。
        # フォントに実在する▲と文字で同じ意味を表すよう改めた。
        c.drawString(1.5 * CM, (paper.height_cm - 3) * CM, "▲ 警告: 型紙が不完全です")
        c.setFont(_LABEL_FONT, 10)
        names = "・".join(p.display_name for p in result.unplaced)
        text_lines = [
            f"型紙に含まれていないパーツ: {names}",
            "採寸値を見直してください。",
        ]
        for i, line in enumerate(text_lines):
            c.drawString(1.5 * CM, (paper.height_cm - 4 - i * 0.7) * CM, line)
        c.showPage()

    for row in range(rows):
        for col in range(cols):
            tile_x0, tile_x1 = col * paper.usable_w_cm, (col + 1) * paper.usable_w_cm
            tile_y0, tile_y1 = row * paper.usable_h_cm, (row + 1) * paper.usable_h_cm

            # round53: 型紙が1本も載らない面は、印刷しない。
            #
            # 生地は長方形だが型紙は長方形ではないので、隅のほうには必ず
            # 何も載らない面ができる。それでも1ページ割り当てて出していた
            # (「(この面に型紙なし)」と書いてはあった)。実測: 身長160cmの
            # ワンピース1着で **48面中7面(15%)が白紙**。家庭用プリンタなら
            # 紙とインク、コンビニなら1枚20円がそのまま無駄になり、
            # 貼り合わせるときも白紙を1枚ずつ除ける手間がかかる。
            # 面の名前は`R行-C列`で位置そのものなので、抜けても
            # 貼り合わせ順は分からなくならない。
            if (row, col) not in cells_to_print:
                skipped_tiles.append((row + 1, col + 1))
                continue

            # 印刷可能領域の枠（この線に沿って隣接ページと貼り合わせる）
            x0, y0 = _to_page_xy(0, 0, paper)
            x1, y1 = _to_page_xy(paper.usable_w_cm, paper.usable_h_cm, paper)
            c.setDash(3, 2)
            c.setStrokeColorRGB(0.6, 0.6, 0.6)
            c.rect(x0, y1, x1 - x0, y0 - y1, stroke=1, fill=0)
            c.setDash()

            # 四隅の位置合わせマーク(+)
            c.setStrokeColorRGB(0.2, 0.2, 0.2)
            for cx, cy in [(0, 0), (paper.usable_w_cm, 0), (0, paper.usable_h_cm),
                           (paper.usable_w_cm, paper.usable_h_cm)]:
                px, py = _to_page_xy(cx, cy, paper)
                c.line(px - 4, py, px + 4, py)
                c.line(px, py - 4, px, py + 4)

            any_content = False
            for placed in result.placed:
                cut = clip_polygon_to_rect(placed.placed_cut_line(), tile_x0, tile_y0, tile_x1, tile_y1)
                stitch = clip_polygon_to_rect(placed.placed_stitch_line(), tile_x0, tile_y0, tile_x1, tile_y1)

                if len(cut) >= 3:
                    any_content = True
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0, paper) for px, py in cut]
                    path = c.beginPath()
                    path.moveTo(*pts[0])
                    for pt in pts[1:]:
                        path.lineTo(*pt)
                    path.close()
                    c.setStrokeColorRGB(0, 0, 0)
                    c.setLineWidth(1.0)
                    c.drawPath(path, stroke=1, fill=0)

                if len(stitch) >= 3:
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0, paper) for px, py in stitch]
                    c.setDash(2, 2)
                    c.setStrokeColorRGB(0.4, 0.4, 0.4)
                    c.setLineWidth(0.6)
                    path = c.beginPath()
                    path.moveTo(*pts[0])
                    for pt in pts[1:]:
                        path.lineTo(*pt)
                    path.close()
                    c.drawPath(path, stroke=1, fill=0)
                    c.setDash()

                # round27: パーツ内部の縫い線(ウエストのダイヤモンドダーツ等)。
                for line in placed.placed_internal_lines():
                    if len(line) < 3:
                        continue
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0, paper) for px, py in line]
                    c.setDash(2, 2)
                    c.setStrokeColorRGB(0.4, 0.4, 0.4)
                    c.setLineWidth(0.6)
                    path = c.beginPath()
                    path.moveTo(*pts[0])
                    for pt in pts[1:]:
                        path.lineTo(*pt)
                    path.close()
                    c.drawPath(path, stroke=1, fill=0)
                    c.setDash()

                # round30: 基準線(バスト線・ウエスト線・ヒップ線・中心線・BP)。
                for label, line in placed.placed_reference_lines():
                    if len(line) < 2:
                        continue
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0, paper) for px, py in line]
                    c.setDash([6, 2, 1, 2], 0)
                    c.setStrokeColorRGB(*REFERENCE_LINE_RGB)
                    c.setLineWidth(0.4)
                    path = c.beginPath()
                    path.moveTo(*pts[0])
                    for pt in pts[1:]:
                        path.lineTo(*pt)
                    c.drawPath(path, stroke=1, fill=0)
                    c.setDash()
                    if label:
                        c.setFillColorRGB(*REFERENCE_LINE_RGB)
                        c.setFont(_LABEL_FONT, 5)
                        c.drawString(pts[0][0] + 2, pts[0][1] + 2, label)

                for a, b in placed.placed_notches():
                    if _segment_in_tile(a, b, tile_x0, tile_y0, tile_x1, tile_y1):
                        pa = _to_page_xy(a[0] - tile_x0, a[1] - tile_y0, paper)
                        pb = _to_page_xy(b[0] - tile_x0, b[1] - tile_y0, paper)
                        c.setStrokeColorRGB(0.8, 0, 0)
                        c.setLineWidth(1.2)
                        c.line(*pa, *pb)

                # パーツ識別ラベル(SVGプレビューには元々あったが、実際に印刷
                # する側には無かった機能不足の修正: 貼り合わせ後に「どの裁断
                # 線がどのパーツか」が分かるよう、パーツの中心点が含まれる
                # タイルに1回だけ描く。中心点がちょうどタイル境界に乗る場合は
                # 隣接タイルどちらにも描かれず抜け漏れることがあるため、
                # ちょうど境界上ならこのタイル側([x0,x1)半開区間)に含める。
                min_x, min_y, max_x, max_y = placed.bbox()
                cx_pt, cy_pt = (min_x + max_x) / 2, (min_y + max_y) / 2
                if (tile_x0 <= cx_pt < tile_x1 or (col == cols - 1 and cx_pt == tile_x1)) and \
                   (tile_y0 <= cy_pt < tile_y1 or (row == rows - 1 and cy_pt == tile_y1)):
                    label_text = placed.part.display_name
                    if placed.rotated:
                        label_text += "(90度回転・布目確認)"
                    lx, ly = _to_page_xy(cx_pt - tile_x0, cy_pt - tile_y0, paper)
                    c.setFillColorRGB(0.2, 0.2, 0.2)
                    # パーツの実幅に収まるよう文字サイズを調整する(細いパーツで
                    # ラベルが裁断線からはみ出し、隣のパーツに重なるのを防ぐ。
                    # `_fit_label_to_width`のdocstringに実測値と経緯を記載)。
                    # round46: 外接矩形ではなく、**文字を描く高さでの実幅**に
                    # 合わせる(`_label_span_cm`のdocstringに実測値と経緯)。
                    usable_cm = _label_span_cm(placed.placed_cut_line(),
                                               cy_pt, cx_pt)
                    if usable_cm is None:
                        usable_cm = max_x - min_x
                    fitted_text, fitted_size = _fit_label_to_width(
                        label_text, usable_cm * CM)
                    c.setFont(_LABEL_FONT, fitted_size)
                    c.drawCentredString(lx, ly, fitted_text)
                    # round31: 裁ち方の指示(生地・枚数・わ裁ち・接着芯)を
                    # パーツ名の下の行に書く。パーツ名と別々に幅へ収めるので、
                    # こちらが長くてもパーツ名が削られない。
                    note_text, note_size = _fit_label_to_width(
                        placed.part.cutting_note, usable_cm * CM,
                        base_size=_CUTTING_NOTE_FONT_SIZE)
                    c.setFont(_LABEL_FONT, note_size)
                    c.drawCentredString(lx, ly - fitted_size * 1.15, note_text)

                # 布目線(grainline)は、合印と違ってパーツの縦幅いっぱいに伸びる
                # 長い線分で、A4タイル1枚の高さを超えることが多い。以前は
                # (合印と同じ)"線分全体の中点がこのタイルに入っているか"だけで
                # 判定し、入っていれば元の(タイルでクリップしていない)線分を
                # そのまま描いていたため、線分全体の中点が属するタイル1枚にしか
                # 描かれず、実際にその布目線が通過している他のタイル(複数枚に
                # 渡ることが多い)には一切描かれていない実バグがあった
                # (_clip_segment_to_rectの docstring 参照。実際に高さ72cmの
                # パーツで検証し、6ページ中1ページにしか描かれないことを確認
                # 済み)。Liang-Barsky法で線分をこのタイルの範囲にクリップし、
                # 交差する分だけ(=このページに実際に収まる区間だけ)描くように
                # 修正した。これにより、布目線が通過する全ページに、その
                # ページ内に収まる長さの線が描かれるようになる。
                grain = placed.placed_grainline()
                gl = grain["line"]
                clipped_grain = _clip_segment_to_rect(gl[0], gl[1], tile_x0, tile_y0, tile_x1, tile_y1)
                if clipped_grain:
                    ga, gb = clipped_grain
                    pa = _to_page_xy(ga[0] - tile_x0, ga[1] - tile_y0, paper)
                    pb = _to_page_xy(gb[0] - tile_x0, gb[1] - tile_y0, paper)
                    c.setStrokeColorRGB(0, 0, 0.8)
                    c.setLineWidth(0.8)
                    c.line(*pa, *pb)
                for a, b in grain["arrows"]:
                    clipped_arrow = _clip_segment_to_rect(a, b, tile_x0, tile_y0, tile_x1, tile_y1)
                    if clipped_arrow:
                        aa, ab = clipped_arrow
                        pa = _to_page_xy(aa[0] - tile_x0, aa[1] - tile_y0, paper)
                        pb = _to_page_xy(ab[0] - tile_x0, ab[1] - tile_y0, paper)
                        c.setStrokeColorRGB(0, 0, 0.8)
                        c.setLineWidth(0.8)
                        c.line(*pa, *pb)

            # ページ情報（貼り合わせ順の目印）
            #
            # 以前はここをHelveticaで描画していたため、「枚」の文字だけが
            # 豆腐(■)になっていた実バグがあった(Helveticaは日本語グリフを
            # 持たない)。日本語対応の_LABEL_FONTに変更して修正。
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.setFont(_LABEL_FONT, 8)
            # round54: 生地が2種類以上あるときは、どの生地の紙かを毎ページに
            # 書く。50枚の紙が2つの山に分かれるので、1枚混ざるだけで
            # 「白い生地にスカートの型紙を載せて裁つ」事故になる。
            label = (f"PatternForge  {fabric_name}  R{row + 1}-C{col + 1} / {rows}x{cols}枚"
                     if fabric_name else
                     f"PatternForge  R{row + 1}-C{col + 1} / {rows}x{cols}枚")
            if not any_content:
                label += "  (この面に型紙なし)"
            c.drawString(0.3 * CM, (paper.height_cm - 0.6) * CM, label)
            # round60: ここだけ英語だった。他のページは表紙も凡例も縫う順番も
            # 全部日本語で、同じことを凡例では「裁断線の内側 1.0cm」と
            # 書いている。型紙を1枚ずつ手に取る人が読むのは**この隅**なので、
            # 凡例と同じ言い方にそろえる。
            if hem_seam_allowance_cm is not None and hem_seam_allowance_cm != seam_allowance_cm:
                allowance_label = (f"縫い代 {seam_allowance_cm}cm"
                                    f"（裾 {hem_seam_allowance_cm}cm）")
            else:
                allowance_label = f"縫い代 {seam_allowance_cm}cm"
            c.drawString(0.3 * CM, 0.4 * CM, allowance_label)

            c.showPage()



def render_combined_pdf(sections: list, output_path: str,
                         seam_allowance_cm: float = 1.0,
                         hem_seam_allowance_cm: float | None = None,
                         assembly_steps: list | None = None,
                         include_empty_tiles: bool = False,
                         paper: Paper = DEFAULT_PAPER) -> str:
    """生地ごとの章を、**1本のPDF**にまとめて書き出す(round57で追加)。

    round54で生地を分けられるようにしたとき、生地の数だけ別のファイルに
    していた。コンビニで印刷する人は、2色なら2ファイルを送ることになる
    ——1回の印刷で済ませたいのに、手間が生地の数だけ増える。

    `sections`は`(生地の名前, NestingResult, 買い物メモ)`の並び。
    章の順番は渡された順(＝画面に出る順)にする。各章の頭には、
    これまでと同じ「貼り合わせ図・買い物メモ・縫う順番」が入り、
    表紙の見出しと全ページの隅に生地の名前が入る(round54)ので、
    1本になっても**どの紙がどの生地か**は紙の上で分かる。

    縫う順番は全章に同じものを入れる。1着の服なので、片方の章にだけ
    工程が無いと、そちらの紙を見た人は作り方が分からなくなる。
    """
    c = rl_canvas.Canvas(output_path, pagesize=paper.pagesize)
    for fabric_name, result, shopping_list in sections:
        _draw_fabric_section(c, result, seam_allowance_cm, hem_seam_allowance_cm,
                              assembly_steps, shopping_list, fabric_name,
                              include_empty_tiles, paper)
    c.save()
    return output_path


def render_a4_pdf(result: NestingResult, output_path: str,
                   seam_allowance_cm: float = 1.0,
                   hem_seam_allowance_cm: float | None = None,
                   assembly_steps: list | None = None,
                   shopping_list=None,
                   fabric_name: str | None = None,
                   include_empty_tiles: bool = False,
                   paper: Paper = DEFAULT_PAPER) -> str:
    """ネスティング結果を、実寸1:1のA4(またはA3)分割PDFに書き出す。"""
    c = rl_canvas.Canvas(output_path, pagesize=paper.pagesize)
    _draw_fabric_section(c, result, seam_allowance_cm, hem_seam_allowance_cm,
                          assembly_steps, shopping_list, fabric_name,
                          include_empty_tiles, paper)
    c.save()
    return output_path


# ---------------------------------------------------------------------------
# プロジェクター裁断向けの出力(round39で追加)
# ---------------------------------------------------------------------------

#: プロジェクター投影用PDFの余白(cm)。
#: 出典: Craftstorming「Tips for using pdf sewing patterns on a projector」
#: https://www.craftstorming.com/2020/05/tips-for-using-pdf-sewing-patterns-on-a-projector
#: 「各辺に最低2.5cm以上のパディング」。
PROJECTOR_PADDING_CM = 2.5

#: 較正用グリッドの間隔(cm)。同出典が「10cm grid」を挙げている。
#: 投影した像の上に定規を当て、この間隔が10cmになるよう投影距離・ズームを
#: 合わせる。1本の四角より、格子の方が像の歪み(台形補正の残り)に気付ける。
PROJECTOR_GRID_CM = 10.0

#: 裁断線の太さ(pt)。同出典は「線の太さは約3ポイント必要」としている。
#: 紙に印刷する線(0.5pt前後)のままでは、投影すると細くて追えない。
PROJECTOR_CUT_LINE_WIDTH_PT = 3.0

#: 縫い線の太さ(pt)。裁断線より細くするが、印刷用よりは太い。
PROJECTOR_STITCH_LINE_WIDTH_PT = 1.5

#: パーツ名の文字サイズ(pt)。投影して離れた位置から読むので大きくする。
PROJECTOR_LABEL_FONT_SIZE = 22

#: 「1マス=10cm」の目盛りを、何cmおきに置くか(round62で追加)。
#:
#: 【なぜ要るか】較正の指示は左上隅に1行あるだけだった。ところがこの紙は
#: 実寸なので、ワンピース1着で**145.0 × 186.6cm**になる。プロジェクターは
#: ふつう布の一部(60〜90cm四方)を映して、少しずつずらしながら裁つので、
#: 左上から始めなかった人は**その一文を一度も見ない**。格子が何cmか
#: 分からなければ較正できないし、5cmだと思い込めば倍の大きさで裁つ。
#:
#: 投影する窓がこの間隔以上なら、どこを映しても必ず1つは目盛りが入る
#: (間隔Sの格子点は、幅S以上のどの区間にも1つ以上ある)。
#: 40cmにしてあるのは、上記Craftstormingの記事が挙げる投影範囲
#: (60〜90cm四方)より確実に小さくするため。
PROJECTOR_SCALE_LABEL_EVERY_CM = 40.0

#: その目盛りの文字サイズ(pt)。定規を当てる距離で読むので、パーツ名ほど
#: 大きくはしない(22pt)。
PROJECTOR_SCALE_LABEL_FONT_SIZE = 15

#: 目盛りの色。白地に対するコントラスト比5.14:1(実測)。
#: 格子の線(1.46:1)では読めず、較正の見出しの色(8.21:1)では裁断線と競る。
PROJECTOR_SCALE_LABEL_RGB = (0.35, 0.42, 0.65)


def render_projector_pdf(result: NestingResult, output_path: str,
                          seam_allowance_cm: float = 1.0) -> str:
    """プロジェクターで布に投影して裁つための、実寸1枚もののPDFを書き出す。

    【なぜA4分割とは別に要るか】家庭でPDFの型紙を使うとき、A4に分割して
    印刷し、何十枚も貼り合わせるのが従来のやり方である。これをプロジェクターで
    布に直接投影して裁つやり方が広まっている——貼り合わせの手間がまるごと
    消え、紙もテープも要らない。ただし投影用のPDFには、印刷用とは違う条件が要る。

    Craftstormingの記事(上の定数のコメント参照)が挙げている条件のうち、
    このエンジンが満たせるものを満たす:

      * **1枚もの**にする(分割しない)。投影するのに分割は意味が無い。
      * **較正用の10cmグリッド**を入れる。投影した像に定規を当てて、
        格子が10cmになるよう合わせてから裁つ。
      * **線を太くする**(裁断線3pt)。印刷用の細い線は投影すると追えない。
      * **パーツ名を大きく**する。離れた位置から読むため。
      * **各辺に2.5cmの余白**を取る。

    満たせないものは、満たせないと書いておく:

      * **レイヤー(サイズごとの表示切り替え)は入れていない。** 記事は
        「プロジェクター用ファイルには必須」としているが、この型紙は
        1回の生成につき1サイズなので、切り替える対象がそもそも無い
        (サイズ展開はサイズごとに別のPDFになる)。複数サイズを1枚に
        重ねて出す機能は無い。
      * **縫い線は破線のまま**にした。記事は「実線が望ましい」とするが、
        それは線が1種類の場合の話で、ここでは裁断線と縫い線を見分ける
        必要がある。両方実線にすると、どちらで裁つのか分からなくなる。
    """
    width_cm = result.fabric_width_cm + 2 * PROJECTOR_PADDING_CM
    height_cm = max(result.used_length_cm, 1.0) + 2 * PROJECTOR_PADDING_CM
    c = rl_canvas.Canvas(output_path, pagesize=(width_cm * CM, height_cm * CM))

    def _xy(x_cm: float, y_cm: float) -> tuple[float, float]:
        """生地座標(cm・上原点)をPDF座標(pt・下原点)へ。実寸1:1。"""
        return ((PROJECTOR_PADDING_CM + x_cm) * CM,
                (height_cm - PROJECTOR_PADDING_CM - y_cm) * CM)

    # --- 較正用グリッド(いちばん下に敷く) ---
    c.setStrokeColorRGB(0.80, 0.84, 0.92)
    c.setLineWidth(0.7)
    x = 0.0
    while x <= result.fabric_width_cm + 1e-6:
        x0, y0 = _xy(x, 0)
        _x1, y1 = _xy(x, max(result.used_length_cm, 1.0))
        c.line(x0, y0, x0, y1)
        x += PROJECTOR_GRID_CM
    y = 0.0
    while y <= max(result.used_length_cm, 1.0) + 1e-6:
        x0, y0 = _xy(0, y)
        x1, _y1 = _xy(result.fabric_width_cm, y)
        c.line(x0, y0, x1, y0)
        y += PROJECTOR_GRID_CM

    # 較正の指示。投影してからでないと合わせられないので、必ず像の中に置く。
    c.setFillColorRGB(0.23, 0.29, 0.56)
    c.setFont(_LABEL_FONT, 13)
    c.drawString(_xy(0.2, -0.9)[0], _xy(0.2, -0.9)[1],
                 f"投影したら、まず格子1マスが{PROJECTOR_GRID_CM:.0f}cmになるよう合わせてください")

    # --- 格子の目盛り(round62) ---
    #
    # 【round61まで何が起きていたか】上の1行が、格子の大きさを述べる
    # **紙の中で唯一の場所**だった。実寸の紙は145.0 × 186.6cmもあるのに、
    # その一文は左上隅(2.7, 1.2cm)に4.6mmの高さで1つあるだけである。
    # プロジェクターは布の一部を映してずらしながら使うので、左上から
    # 始めなかった人はこの文を一度も見ない——格子が何cmか分からないまま、
    # 何を基準に合わせればいいのか分からない紙になっていた。
    #
    # 目盛りは格子と一緒に、**パーツより先に**描く。round60とは逆だが、
    # 理由は同じ「消えて困る方を上にする」である——ここで消えて困るのは
    # 裁断線の方で、目盛りは較正のときに1つ読めれば足りる。
    # 色は「格子の仲間に見えるが、読める」ところを取る。白地に対する
    # コントラスト比を実測して選んだ: 格子の線 1.46:1（読めない)、
    # 最初に置いた(0.45,0.52,0.70) 3.68:1、これ 5.14:1、較正の見出し
    # 8.21:1（目立ちすぎて裁断線と競る）。布の色は選べないので、
    # 白地で4.5:1を下回らない濃さにしておく。
    c.setFillColorRGB(*PROJECTOR_SCALE_LABEL_RGB)
    c.setFont(_LABEL_FONT, PROJECTOR_SCALE_LABEL_FONT_SIZE)
    scale_text = f"1マス{PROJECTOR_GRID_CM:.0f}cm"
    step = PROJECTOR_SCALE_LABEL_EVERY_CM
    label_y = 0.0
    while label_y <= max(result.used_length_cm, 1.0) + 1e-6:
        label_x = 0.0
        while label_x <= result.fabric_width_cm + 1e-6:
            lx, ly = _xy(label_x + 0.4, label_y + 1.2)
            c.drawString(lx, ly, scale_text)
            label_x += step
        label_y += step

    # --- 生地の外枠 ---
    c.setStrokeColorRGB(0.55, 0.55, 0.55)
    c.setLineWidth(1.0)
    fx0, fy0 = _xy(0, 0)
    fx1, fy1 = _xy(result.fabric_width_cm, max(result.used_length_cm, 1.0))
    c.rect(fx0, fy1, fx1 - fx0, fy0 - fy1, stroke=1, fill=0)

    # --- パーツ ---
    for placed in result.placed:
        stitch = placed.placed_stitch_line()
        if len(stitch) >= 3:
            c.setStrokeColorRGB(0.42, 0.42, 0.42)
            c.setLineWidth(PROJECTOR_STITCH_LINE_WIDTH_PT)
            c.setDash(6, 4)
            path = c.beginPath()
            path.moveTo(*_xy(stitch[0][0], stitch[0][1]))
            for px, py in stitch[1:]:
                path.lineTo(*_xy(px, py))
            path.close()
            c.drawPath(path, stroke=1, fill=0)
            c.setDash()

        cut = placed.placed_cut_line()
        if len(cut) >= 3:
            c.setStrokeColorRGB(0.05, 0.05, 0.05)
            c.setLineWidth(PROJECTOR_CUT_LINE_WIDTH_PT)
            path = c.beginPath()
            path.moveTo(*_xy(cut[0][0], cut[0][1]))
            for px, py in cut[1:]:
                path.lineTo(*_xy(px, py))
            path.close()
            c.drawPath(path, stroke=1, fill=0)

        for line in placed.placed_internal_lines():
            if len(line) < 2:
                continue
            c.setStrokeColorRGB(0.05, 0.05, 0.05)
            c.setLineWidth(PROJECTOR_STITCH_LINE_WIDTH_PT)
            path = c.beginPath()
            path.moveTo(*_xy(line[0][0], line[0][1]))
            for px, py in line[1:]:
                path.lineTo(*_xy(px, py))
            c.drawPath(path, stroke=1, fill=0)

        for notch in placed.placed_notches():
            if len(notch) < 2:
                continue
            c.setStrokeColorRGB(0.80, 0.09, 0.09)
            c.setLineWidth(PROJECTOR_STITCH_LINE_WIDTH_PT)
            c.line(*_xy(notch[0][0], notch[0][1]), *_xy(notch[1][0], notch[1][1]))

        # 布目線は {"line": (始点, 終点), "arrows": [(a, b), ...]} という形。
        grain = placed.placed_grainline()
        if grain and grain.get("line"):
            c.setStrokeColorRGB(0.15, 0.35, 0.85)
            c.setLineWidth(PROJECTOR_STITCH_LINE_WIDTH_PT)
            (gx0, gy0), (gx1, gy1) = grain["line"]
            c.line(*_xy(gx0, gy0), *_xy(gx1, gy1))
            for (ax0, ay0), (ax1, ay1) in grain.get("arrows", []):
                c.line(*_xy(ax0, ay0), *_xy(ax1, ay1))

        # パーツ名(大きく)
        x0_cm, y0_cm, x1_cm, y1_cm = placed.bbox()
        label = placed.part.display_name
        cx = (x0_cm + x1_cm) / 2.0
        cy = (y0_cm + y1_cm) / 2.0
        text, size = _fit_label_to_width(
            label, (x1_cm - x0_cm) * CM, base_size=PROJECTOR_LABEL_FONT_SIZE)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(_LABEL_FONT, size)
        px, py = _xy(cx, cy)
        c.drawCentredString(px, py, text)

    c.showPage()
    c.save()
    return output_path


def export_pattern(result: NestingResult, output_dir: str, basename: str = "pattern",
                    seam_allowance_cm: float = 1.0,
                    hem_seam_allowance_cm: float | None = None,
                    assembly_steps: list | None = None,
                    shopping_list=None,
                    fabric_name: str | None = None,
                    include_empty_tiles: bool = False,
                    paper: Paper = DEFAULT_PAPER) -> dict[str, str]:
    """SVGプレビュー・A4分割PDF・DXF(round5で追加)の3種を出力し、パスを返す。

    DXFはA4分割PDFと違い、家庭用プリンタでの印刷・貼り合わせを前提とせず、
    業務用の自動裁断機やCADソフトに実寸1:1でそのまま読み込むための形式
    (詳細はengine/dxf_export.pyのモジュールdocstring参照)。SVG/PDFと違い
    縫い代幅(seam_allowance_cm/hem_seam_allowance_cm)を文字として書き込む
    フッターは無い点に注意(DXF側は既にcut_line自体にその縫い代が反映済み
    のジオメトリとして出力されるため、数値表記は必須ではない判断)。
    """
    os.makedirs(output_dir, exist_ok=True)
    svg_path = os.path.join(output_dir, f"{basename}.svg")
    pdf_path = os.path.join(output_dir, f"{basename}.pdf")
    dxf_path = os.path.join(output_dir, f"{basename}.dxf")
    render_layout_svg(result, svg_path)
    render_a4_pdf(result, pdf_path, seam_allowance_cm=seam_allowance_cm,
                  hem_seam_allowance_cm=hem_seam_allowance_cm,
                  assembly_steps=assembly_steps,
                  shopping_list=shopping_list,
                  fabric_name=fabric_name,
                  include_empty_tiles=include_empty_tiles,
                  paper=paper)
    render_dxf(result, dxf_path)
    # round39: プロジェクター投影用(実寸1枚もの)。A4分割PDFとは別物なので
    # 別ファイルにする(投影する人は貼り合わせないし、印刷する人は
    # 巨大な1ページを開いても困る)。
    projector_path = os.path.join(output_dir, f"{basename}_projector.pdf")
    render_projector_pdf(result, projector_path, seam_allowance_cm=seam_allowance_cm)
    return {"svg": svg_path, "pdf": pdf_path, "dxf": dxf_path,
            "projector": projector_path}


#: ZIPに入れるときの、ファイル名に足す接尾辞 (round49)。
#: 拡張子が同じ形式どうしを区別するためのもの。ここに無い形式は
#: `_<形式名>` を自動で足す(そのうえで衝突を検査する)。
#: 単体ダウンロードのファイル名 (`{job}_projector.pdf` など) と揃えてある。
_BUNDLE_NAME_SUFFIX = {
    "svg": "",
    "pdf": "",
    "dxf": "",
    "projector": "_projector",
    # round55: 生地を分けたときの2種類目以降(engine/fabric_groups.py)。
    # 接尾辞を書いておかないと `_fabric2_pdf` のような読みにくい名前になる
    # (衝突はround49の検査が止めるが、名前は直らない)。
    **{f"fabric{index}_{fmt}": f"_fabric{index}{suffix}"
       for index in range(2, 7)
       for fmt, suffix in (("svg", ""), ("pdf", ""), ("dxf", ""),
                            ("projector", "_projector"))},
    # round58: round57が足した「生地ぜんぶを1本にしたPDF」。ここに
    # 書き忘れていたので、下の`.get(fmt, f'_{fmt}')`という保険が働き、
    # ZIPの中身が **S/S_all_fabrics_pdf.pdf** になっていた
    # (拡張子の前に内部のキー名がそのまま出ている)。実測で確認済み。
    "all_fabrics_pdf": "_all_fabrics",
    # round58: 裏地(round41)。round49がZIPの名前表を作ったとき、裏地は
    # サイズ展開に渡っていなかったので**ZIPに入ることが無く**、
    # 書き忘れても誰も困らなかった。サイズ展開でも裏地を引けるように
    # した以上、ここに名前が要る(書かないと `S/S_lining_svg.svg` になる)。
    **{f"lining_{fmt}": f"_lining{suffix}"
       for fmt, suffix in (("svg", ""), ("pdf", ""), ("dxf", ""),
                            ("projector", "_projector"))},
}


def export_multi_size_bundle(per_size_outputs: dict[str, dict[str, str]],
                              output_dir: str, basename: str) -> str:
    """複数サイズ分の`export_pattern()`出力(サイズ名 -> {"svg":path,...})を、
    1つのZIPファイルにまとめる(round5「複数サイズの一括生成」で追加)。

    ZIP内は`{サイズ名}/{サイズ名}.{svg|pdf|dxf}`、プロジェクター投影用だけ
    `{サイズ名}/{サイズ名}_projector.pdf`という構成にする(例: `L/L.pdf`、
    `L/L_projector.pdf`)。単体ダウンロードのファイル名と同じ付け方である。
    各サイズは既に個別のジョブとして`output_dir`に実ファイルが存在している
    前提で、それをそのまま参照コピーする（＝サイズごとの単体ダウンロード
    リンクと、このZIPの中身は同じファイルの二重提供になる。正直な設計上の
    トレードオフとして、まとめてダウンロードしたい人にはZIPを、1サイズだけ
    確認したい人には個別リンクを、の両方を提供することを優先し、ディスク
    使用量が多少増えることは許容している）。

    【round49で見つけた実バグ】以前はZIP内の名前を**拡張子だけ**から
    `f"{size}/{size}{ext}"` と組み立てていた。round39でプロジェクター投影用
    (これも`.pdf`)が`export_pattern()`の戻り値に増えたため、1サイズにつき
    `L/L.pdf`が**2件**書かれ、名前が衝突していた。実測(S/M/Lの3サイズ):

        L/L.pdf   153,663バイト … A4分割PDF(印刷して貼り合わせる本命)
        L/L.pdf    23,201バイト … プロジェクター投影用(145×196cmの1ページ)

    ZIPは同名を2件持てるので書き込み自体は通り、Pythonも
    `UserWarning: Duplicate name` を出すだけだった。しかし**展開すると
    後から書いた方が上書きする**ので、利用者の手元に残るのは投影用だけに
    なり、家庭用プリンタで刷るためのA4分割PDFが消えていた。
    実際に展開して、残ったのが23,201バイトの方であることを確認した。
    """
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, f"{basename}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for size, outputs in per_size_outputs.items():
            used: dict[str, str] = {}
            for fmt, path in outputs.items():
                if not os.path.isfile(path):
                    continue  # pragma: no cover - 通常は起こらない防御的分岐
                ext = os.path.splitext(path)[1]
                # round58: ここは `.get(fmt, f'_{fmt}')` という保険だった。
                # 名前が衝突しない限り黙って通るので、round57が足した
                # `all_fabrics_pdf` が **S/S_all_fabrics_pdf.pdf** という
                # 内部のキー名そのままのファイル名でZIPに入っていた。
                # 「衝突は止めるが、変な名前は通す」では見つからない。
                # 登録されていない形式は、名前を作らずに止める。
                if fmt not in _BUNDLE_NAME_SUFFIX:
                    raise ValueError(
                        f"ZIPに入れる名前が決まっていない形式です: {fmt}。"
                        "engine/pdf_export.py の _BUNDLE_NAME_SUFFIX に"
                        "その形式の接尾辞を足してください。")
                arcname = f"{size}/{size}{_BUNDLE_NAME_SUFFIX[fmt]}{ext}"
                if arcname in used:
                    # 名前が衝突したら黙って上書きさせない。形式が増えたときに
                    # 気づけるよう、はっきり止める(round49はこれが無くて、
                    # 「同名2件」が3ラウンド分そのまま配られていた)。
                    raise ValueError(
                        f"ZIP内の名前が衝突しています: {arcname} "
                        f"({used[arcname]} と {fmt})。"
                        "engine/pdf_export.py の _BUNDLE_NAME_SUFFIX に"
                        "その形式の接尾辞を足してください。")
                used[arcname] = fmt
                zf.write(path, arcname=arcname)
    return zip_path
