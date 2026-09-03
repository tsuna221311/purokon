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
_JP_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "pattern_label_ja_subset.ttf")


def _register_jp_font() -> str:
    try:
        pdfmetrics.registerFont(TTFont(_JP_FONT_NAME, _JP_FONT_PATH))
        return _JP_FONT_NAME
    except (TTFError, OSError):  # pragma: no cover - フォント資産が欠けた環境向けの保険
        return "Helvetica"


_LABEL_FONT = _register_jp_font()

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
    "seam allowance: ",
    " (hem: ",
    ")",
    "(90度回転・布目確認)",
    # ラベルの省略記号
    "…",
)

_PART_LABEL_FONT_SIZE = 9
_PART_LABEL_MIN_FONT_SIZE = 5
_PART_LABEL_ELLIPSIS = "…"


def _fit_label_to_width(text: str, max_width_pt: float) -> tuple[str, float]:
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
    size = _PART_LABEL_FONT_SIZE
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
#: 警告帯の高さ(cm)。実際に全テンプレート×採寸(1200通り)を最も極端な
#: 採寸範囲で総当たりして確認したところ、現状のテンプレート・MIN_SCALE/
#: MAX_SCALEの範囲ではunplacedが発生するケースは存在しない(確認済み・
#: 問題無し)。ただし以前はunplacedが発生した場合でもSVG/PDFはresult.placed
#: しか描画しないため、配置できなかったパーツが出力から完全に無言で消える
#: (=画面の統計欄の数値以外、生地を裁ってから気づくまで実害に気付く手段が
#: 無い)作りだった。到達不能であることを確認済みとはいえ、将来テンプレート
#: やスケール範囲を変更した場合に備え、実際に発生したら出力ファイル自体にも
#: 目立つ警告を残すよう防御的に修正した。
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

def _to_page_xy(local_x: float, local_y: float) -> tuple[float, float]:
    """タイル内ローカル座標(cm, 上原点でY下方向)を、PDFページ座標(pt, 下原点でY上方向)に変換。"""
    px = (A4_MARGIN_CM + local_x) * CM
    py = (A4_HEIGHT_CM - A4_MARGIN_CM - local_y) * CM
    return (px, py)


def _draw_overview_page(c, result: NestingResult, rows: int, cols: int,
                         seam_allowance_cm: float,
                         hem_seam_allowance_cm: float | None) -> None:
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
    margin = A4_MARGIN_CM
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 15)
    c.drawString(margin * CM, (A4_HEIGHT_CM - margin - 0.5) * CM, "貼り合わせ図と記号の凡例")

    c.setFont(_LABEL_FONT, 9)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(margin * CM, (A4_HEIGHT_CM - margin - 1.2) * CM,
                 f"生地幅 {result.fabric_width_cm:.0f}cm / 使用長 {result.used_length_cm:.0f}cm"
                 f" / 全{rows * cols}枚 ({rows}行 x {cols}列)")

    # --- 上: 貼り合わせ図(縮小) ------------------------------------------
    # 生地は「幅150cm×長さ87cm」のように横長になることが多く、縮小図を
    # ページの左半分に収めると図が小さくなりすぎる。ページ幅いっぱいを
    # 使って描き、凡例はその下に置く。
    map_top_cm = margin + 2.2
    map_left_cm = margin
    map_w_cm = A4_USABLE_W_CM
    # 図は縦にページの半分程度までとし、残りを凡例に充てる。
    map_h_cm = (A4_HEIGHT_CM - map_top_cm - margin) * 0.55
    sheet_w_cm = cols * A4_USABLE_W_CM
    sheet_h_cm = rows * A4_USABLE_H_CM
    scale = min(map_w_cm / sheet_w_cm, map_h_cm / sheet_h_cm) if sheet_w_cm and sheet_h_cm else 1.0

    def _map_xy(x_cm: float, y_cm: float) -> tuple[float, float]:
        """生地座標(cm, 上原点)を、縮小図のPDFページ座標(pt)に変換する。"""
        return ((map_left_cm + x_cm * scale) * CM,
                (A4_HEIGHT_CM - map_top_cm - y_cm * scale) * CM)

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(_LABEL_FONT, 10)
    c.drawString(map_left_cm * CM, (A4_HEIGHT_CM - map_top_cm + 0.35) * CM,
                 "貼り合わせ図 (実物大ではありません)")

    # 生地全体の外枠
    x0, y0 = _map_xy(0, 0)
    x1, y1 = _map_xy(result.fabric_width_cm, max(result.used_length_cm, 0.1))
    c.setStrokeColorRGB(0.45, 0.45, 0.45)
    c.setLineWidth(0.8)
    c.rect(x0, y1, x1 - x0, y0 - y1, stroke=1, fill=0)

    # タイルの区切りと行列番号
    c.setFont(_LABEL_FONT, 6)
    for row in range(rows):
        for col in range(cols):
            tx0, ty0 = _map_xy(col * A4_USABLE_W_CM, row * A4_USABLE_H_CM)
            tx1, ty1 = _map_xy((col + 1) * A4_USABLE_W_CM, (row + 1) * A4_USABLE_H_CM)
            c.setDash(2, 2)
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.rect(tx0, ty1, tx1 - tx0, ty0 - ty1, stroke=1, fill=0)
            c.setDash()
            c.setFillColorRGB(0.55, 0.55, 0.55)
            c.drawString(tx0 + 2, ty0 - 8, f"R{row + 1}-C{col + 1}")

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
        lx, ly = _map_xy((min_x + max_x) / 2, (min_y + max_y) / 2)
        label = placed.part.display_name
        # 縮小図では実寸よりさらに幅が狭くなるため、実寸ページと同じ
        # 収まり調整(_fit_label_to_width)を縮小後の幅に対して行う。
        text, size = _fit_label_to_width(label, (max_x - min_x) * scale * CM)
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont(_LABEL_FONT, max(4.0, min(size, 7.0)))
        c.drawCentredString(lx, ly, text)

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
    c.drawString(legend_left_cm * CM, (A4_HEIGHT_CM - legend_top_cm + 0.35) * CM, "記号の凡例")

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
        sy = (A4_HEIGHT_CM - y_cm) * CM

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
    c.drawString(notes_left_cm * CM, (A4_HEIGHT_CM - legend_top_cm + 0.35) * CM, "印刷と貼り合わせ")
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.setFont(_LABEL_FONT, 8)
    for i, line in enumerate([
        "印刷は「実物大」「倍率100%」で行ってください。",
        "用紙に合わせて拡大縮小すると寸法が変わります。",
        "各ページの四隅の + 印を重ねて貼り合わせます。",
    ]):
        c.drawString(notes_left_cm * CM, (A4_HEIGHT_CM - legend_top_cm - 0.5 - i * 0.5) * CM, line)

    c.showPage()


def render_a4_pdf(result: NestingResult, output_path: str,
                   seam_allowance_cm: float = 1.0,
                   hem_seam_allowance_cm: float | None = None) -> str:
    """ネスティング結果を、実寸1:1のA4分割PDFに書き出す。

    各ページに縫い線・裁断線(縫い代込み)・合印・布目線を描き、ページ境界を
    合わせて貼り合わせれば元の生地レイアウトを再現できる。
    """
    cols = max(1, math.ceil(result.fabric_width_cm / A4_USABLE_W_CM))
    rows = max(1, math.ceil(result.used_length_cm / A4_USABLE_H_CM)) if result.used_length_cm else 1

    c = rl_canvas.Canvas(output_path, pagesize=A4)

    # 実寸タイルの前に、全体図と記号の凡例のページを1枚置く(round11で追加。
    # `_draw_overview_page`のdocstring参照)。配置できたパーツが1つも無い
    # 場合は縮小図に描くものが無いため省く。
    if result.placed:
        _draw_overview_page(c, result, rows, cols, seam_allowance_cm, hem_seam_allowance_cm)

    if result.unplaced:
        # 配置できなかったパーツがある場合、貼り合わせ用のタイルページより
        # 前に警告専用の1枚を挿入する。SVGプレビュー(render_layout_svg)側の
        # 警告帯と同じ理由で、実際に印刷して使うこのPDF自体にも記録を残す
        # (UNPLACED_BANNER_HEIGHT_CMのコメント参照。到達不能であることは
        # 確認済みだが、発生した場合に無言でパーツが消えるのを防ぐ防御的な
        # 対応)。
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
        c.drawString(1.5 * CM, (A4_HEIGHT_CM - 3) * CM, "▲ 警告: 型紙が不完全です")
        c.setFont(_LABEL_FONT, 10)
        names = "・".join(p.display_name for p in result.unplaced)
        text_lines = [
            f"型紙に含まれていないパーツ: {names}",
            "採寸値を見直してください。",
        ]
        for i, line in enumerate(text_lines):
            c.drawString(1.5 * CM, (A4_HEIGHT_CM - 4 - i * 0.7) * CM, line)
        c.showPage()

    for row in range(rows):
        for col in range(cols):
            tile_x0, tile_x1 = col * A4_USABLE_W_CM, (col + 1) * A4_USABLE_W_CM
            tile_y0, tile_y1 = row * A4_USABLE_H_CM, (row + 1) * A4_USABLE_H_CM

            # 印刷可能領域の枠（この線に沿って隣接ページと貼り合わせる）
            x0, y0 = _to_page_xy(0, 0)
            x1, y1 = _to_page_xy(A4_USABLE_W_CM, A4_USABLE_H_CM)
            c.setDash(3, 2)
            c.setStrokeColorRGB(0.6, 0.6, 0.6)
            c.rect(x0, y1, x1 - x0, y0 - y1, stroke=1, fill=0)
            c.setDash()

            # 四隅の位置合わせマーク(+)
            c.setStrokeColorRGB(0.2, 0.2, 0.2)
            for cx, cy in [(0, 0), (A4_USABLE_W_CM, 0), (0, A4_USABLE_H_CM),
                           (A4_USABLE_W_CM, A4_USABLE_H_CM)]:
                px, py = _to_page_xy(cx, cy)
                c.line(px - 4, py, px + 4, py)
                c.line(px, py - 4, px, py + 4)

            any_content = False
            for placed in result.placed:
                cut = clip_polygon_to_rect(placed.placed_cut_line(), tile_x0, tile_y0, tile_x1, tile_y1)
                stitch = clip_polygon_to_rect(placed.placed_stitch_line(), tile_x0, tile_y0, tile_x1, tile_y1)

                if len(cut) >= 3:
                    any_content = True
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0) for px, py in cut]
                    path = c.beginPath()
                    path.moveTo(*pts[0])
                    for pt in pts[1:]:
                        path.lineTo(*pt)
                    path.close()
                    c.setStrokeColorRGB(0, 0, 0)
                    c.setLineWidth(1.0)
                    c.drawPath(path, stroke=1, fill=0)

                if len(stitch) >= 3:
                    pts = [_to_page_xy(px - tile_x0, py - tile_y0) for px, py in stitch]
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

                for a, b in placed.placed_notches():
                    if _segment_in_tile(a, b, tile_x0, tile_y0, tile_x1, tile_y1):
                        pa = _to_page_xy(a[0] - tile_x0, a[1] - tile_y0)
                        pb = _to_page_xy(b[0] - tile_x0, b[1] - tile_y0)
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
                    lx, ly = _to_page_xy(cx_pt - tile_x0, cy_pt - tile_y0)
                    c.setFillColorRGB(0.2, 0.2, 0.2)
                    # パーツの実幅に収まるよう文字サイズを調整する(細いパーツで
                    # ラベルが裁断線からはみ出し、隣のパーツに重なるのを防ぐ。
                    # `_fit_label_to_width`のdocstringに実測値と経緯を記載)。
                    fitted_text, fitted_size = _fit_label_to_width(
                        label_text, (max_x - min_x) * CM)
                    c.setFont(_LABEL_FONT, fitted_size)
                    c.drawCentredString(lx, ly, fitted_text)

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
                    pa = _to_page_xy(ga[0] - tile_x0, ga[1] - tile_y0)
                    pb = _to_page_xy(gb[0] - tile_x0, gb[1] - tile_y0)
                    c.setStrokeColorRGB(0, 0, 0.8)
                    c.setLineWidth(0.8)
                    c.line(*pa, *pb)
                for a, b in grain["arrows"]:
                    clipped_arrow = _clip_segment_to_rect(a, b, tile_x0, tile_y0, tile_x1, tile_y1)
                    if clipped_arrow:
                        aa, ab = clipped_arrow
                        pa = _to_page_xy(aa[0] - tile_x0, aa[1] - tile_y0)
                        pb = _to_page_xy(ab[0] - tile_x0, ab[1] - tile_y0)
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
            label = f"PatternForge  R{row + 1}-C{col + 1} / {rows}x{cols}枚"
            if not any_content:
                label += "  (この面に型紙なし)"
            c.drawString(0.3 * CM, (A4_HEIGHT_CM - 0.6) * CM, label)
            if hem_seam_allowance_cm is not None and hem_seam_allowance_cm != seam_allowance_cm:
                allowance_label = f"seam allowance: {seam_allowance_cm}cm (hem: {hem_seam_allowance_cm}cm)"
            else:
                allowance_label = f"seam allowance: {seam_allowance_cm}cm"
            c.drawString(0.3 * CM, 0.4 * CM, allowance_label)

            c.showPage()

    c.save()
    return output_path


def export_pattern(result: NestingResult, output_dir: str, basename: str = "pattern",
                    seam_allowance_cm: float = 1.0,
                    hem_seam_allowance_cm: float | None = None) -> dict[str, str]:
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
                  hem_seam_allowance_cm=hem_seam_allowance_cm)
    render_dxf(result, dxf_path)
    return {"svg": svg_path, "pdf": pdf_path, "dxf": dxf_path}


def export_multi_size_bundle(per_size_outputs: dict[str, dict[str, str]],
                              output_dir: str, basename: str) -> str:
    """複数サイズ分の`export_pattern()`出力(サイズ名 -> {"svg":path,...})を、
    1つのZIPファイルにまとめる(round5「複数サイズの一括生成」で追加)。

    ZIP内は`{サイズ名}/{サイズ名}.{svg|pdf|dxf}`という構成にする
    (例: `L/L.pdf`)。各サイズは既に個別のジョブとして`output_dir`に
    実ファイルが存在している前提で、それをそのまま参照コピーする
    （＝サイズごとの単体ダウンロードリンクと、このZIPの中身は同じ
    ファイルの二重提供になる。正直な設計上のトレードオフとして、
    まとめてダウンロードしたい人にはZIPを、1サイズだけ確認したい人には
    個別リンクを、の両方を提供することを優先し、ディスク使用量が
    多少増えることは許容している）。
    """
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, f"{basename}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for size, outputs in per_size_outputs.items():
            for fmt, path in outputs.items():
                if not os.path.isfile(path):
                    continue  # pragma: no cover - 通常は起こらない防御的分岐
                ext = os.path.splitext(path)[1]
                zf.write(path, arcname=f"{size}/{size}{ext}")
    return zip_path
