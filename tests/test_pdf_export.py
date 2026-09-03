import os

import pytest

import re

from engine import pdf_export
from engine.pdf_export import (
    _clip_segment_to_rect,
    clip_polygon_to_rect,
    export_pattern,
    render_a4_pdf,
    render_layout_svg,
)
from engine.nesting import nest_parts
from engine.pipeline import PAIR_LABELS
from engine.seam import finalize_part
from engine.svgpath import parse_path


def test_clip_polygon_to_rect_cuts_a_square_in_half():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    clipped = clip_polygon_to_rect(square, xmin=0, ymin=0, xmax=5, ymax=10)
    xs = [p[0] for p in clipped]
    assert max(xs) == 5.0
    assert min(xs) == 0.0


def test_clip_polygon_outside_rect_returns_empty():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    clipped = clip_polygon_to_rect(square, xmin=100, ymin=100, xmax=200, ymax=200)
    assert clipped == []


def test_export_pattern_writes_svg_and_pdf(tmp_path):
    # round5でDXF(engine/dxf_export.py)を追加した際、export_pattern()の
    # 戻り値がsvg/pdfの2キーからsvg/pdf/dxfの3キーに変わったため、この
    # テストもdxfの存在を併せて確認するよう更新した。
    segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    part = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    outputs = export_pattern(result, str(tmp_path), basename="job")

    assert os.path.getsize(outputs["svg"]) > 0
    assert os.path.getsize(outputs["pdf"]) > 0
    assert os.path.getsize(outputs["dxf"]) > 0
    assert outputs["svg"].endswith("job.svg")
    assert outputs["pdf"].endswith("job.pdf")
    assert outputs["dxf"].endswith("job.dxf")


def test_unplaced_parts_do_not_silently_vanish_from_svg_or_pdf(tmp_path):
    """配置できなかったパーツ(unplaced)が、以前はSVG/PDFのどちらからも
    完全に無言で消えていた問題の回帰テスト。

    実際に全テンプレート×採寸(有効な採寸値の最も極端な範囲を含む1200通り)
    を総当たりして確認したところ、現状のテンプレート・MIN_SCALE/MAX_SCALEの
    範囲ではunplacedが発生するケースは存在しない(=製品としては到達不能)。
    ただし`nesting.py`はunplacedを検出できる作りになっている一方、
    `render_layout_svg`/`render_a4_pdf`は`result.placed`しか描画しないため、
    到達した場合は配置できなかったパーツが出力から完全に消え、画面上も
    他の統計と同じ見た目の数値表示のみだった。ここでは生地幅より明らかに
    幅の広いパーツを直接`nest_parts()`に渡すことで、到達不能な状態を
    直接作り出し、実際に生成したSVG/PDFの両方に警告として残ることを確認する。
    """
    import pypdf

    wide_segments = parse_path("M 0 0 L 500 0 L 500 30 L 0 30 Z")  # 生地幅より明らかに広い
    normal_segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    wide_part = finalize_part("skirt", "flare", wide_segments, seam_allowance_cm=1.0)
    normal_part = finalize_part("front_bodice", "round_neck", normal_segments, seam_allowance_cm=1.0)

    result = nest_parts([normal_part, wide_part], fabric_width_cm=110.0)
    assert len(result.unplaced) == 1  # 前提: 実際にunplacedが発生していること
    assert result.unplaced[0].part_type == "skirt"

    outputs = export_pattern(result, str(tmp_path), basename="job")

    svg_content = open(outputs["svg"], encoding="utf-8").read()
    assert "型紙に含まれていない" in svg_content
    assert "skirt" in svg_content

    reader = pypdf.PdfReader(outputs["pdf"])
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "型紙が不完全です" in full_text
    assert "skirt" in full_text


def test_svg_and_pdf_have_no_unplaced_warning_when_everything_is_placed(tmp_path):
    # 通常の(全パーツが配置できる)ケースでは、警告帯/警告ページが
    # 一切追加されないことも確認する(誤検知が無いこと)。
    segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    part = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    assert result.unplaced == []

    outputs = export_pattern(result, str(tmp_path), basename="job2")
    svg_content = open(outputs["svg"], encoding="utf-8").read()
    assert "型紙に含まれていない" not in svg_content

    import pypdf
    reader = pypdf.PdfReader(outputs["pdf"])
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "型紙が不完全です" not in full_text
    # 警告ページが追加されていないなら、1ページ目が最初のタイル(R1-C1)の
    # はず(警告ページが挿入されると1ページ目がそちらになってしまう)。
    assert "R1-C1" in reader.pages[0].extract_text()


def test_jp_label_font_actually_registered_not_falling_back_to_helvetica():
    # このテスト環境(engine/assets/pattern_label_ja_subset.ttf が読み込める)
    # では、Helveticaへの静かなフォールバックが起きていないことを保証する。
    # フォールバックしたままだと、下のテストが検出しようとしている「枚」等の
    # 文字化けバグに実質的には気付けなくなってしまう。
    assert pdf_export._LABEL_FONT != "Helvetica"


def test_jp_label_font_contains_every_character_the_pdf_actually_draws():
    # 実バグの再発防止テスト: A4分割PDF出力(render_a4_pdf)は、ページ情報の
    # 「枚」という文字や、パーツ左右/前後を示す漢字ラベル(PAIR_LABELS)、
    # ダーツ注記、回転注記を日本語対応フォント(_LABEL_FONT)で描画している。
    # このフォントは全漢字を含むフルセットではなく、実際に使う文字だけを
    # 抜き出したサブセット(scripts/build_pattern_label_font.py参照)なので、
    # 新しく日本語の文字を使うラベルを追加したのにフォント側の更新を忘れると、
    # その文字だけが無言で欠落する(以前「布目確認」の「布」「目」を追加した
    # 際に実際に発生させてしまった不具合)。ここでは、実際にコード中で
    # 生成されうる文字列を全て集めて、フォントの文字コード→グリフ対応表
    # (charToGlyph)に全て含まれていることを検証する。
    if pdf_export._LABEL_FONT == "Helvetica":
        import pytest
        pytest.skip("このテスト環境では日本語フォントが読み込めていないため対象外")

    from reportlab.pdfbase.pdfmetrics import getFont
    face = getFont(pdf_export._LABEL_FONT).face

    required_text = "".join(
        label for labels in PAIR_LABELS.values() for label in labels
    )
    required_text += "PatternForge  R1-C1 / 5x8枚  (この面に型紙なし)"
    required_text += "(90度回転・布目確認)"
    required_text += "[ダーツ2本]"
    required_text += "seam allowance: 1.0cm"

    missing = sorted({ch for ch in required_text if ord(ch) not in face.charToGlyph})
    assert not missing, f"フォントに存在しない文字: {missing}"


def test_render_a4_pdf_draws_part_label_and_correct_manai_character(tmp_path):
    # 実際に生成したPDFをpdftoppmで画像化して目視確認して見つかった2つの
    # 不具合の再現テスト:
    #   1. SVGプレビューには表示されるパーツ識別ラベル(左脚/右脚等)が、
    #      実際に印刷して裁断に使うA4分割PDF側には一切描かれていなかった。
    #   2. ページ情報に使われている「枚」の文字が、日本語グリフを持たない
    #      Helveticaで描画されていたため、実際のPDFでは豆腐(■)になっていた。
    # pypdfのテキスト抽出(extract_text)で、両方が実際に文字として埋め込まれて
    # いることを確認する(ベクター図形のcontent stream解析には既知の癖が
    # あるため、テキストオブジェクトの抽出で検証する)。
    import pypdf

    segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    part = finalize_part("sleeve", "curve", segments, seam_allowance_cm=1.0,
                          label_suffix=PAIR_LABELS["sleeve"][0])
    result = nest_parts([part], fabric_width_cm=110.0)
    pdf_path = str(tmp_path / "job.pdf")
    render_a4_pdf(result, pdf_path)

    reader = pypdf.PdfReader(pdf_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    assert "枚" in full_text
    assert PAIR_LABELS["sleeve"][0] in full_text  # "左"
    assert "sleeve" in full_text


def test_a4_pdf_page_is_actually_physical_a4_size_for_1to1_printing(tmp_path):
    # 「実寸1:1」(等倍で印刷してそのまま裁断に使える)という製品としての
    # 中心的な主張を、実際に生成したPDFのページサイズから直接検証する。
    # pypdfでmediabox(pt単位)を取得し、reportlab.lib.units.cmで実際にcmへ
    # 変換した上で、標準A4(21.0cm x 29.7cm)に一致することを確認する。
    # これがずれていると、印刷時にプリンタ側の「用紙に合わせて縮小」等の
    # 設定次第で型紙が縮小され、実際の身体サイズと合わない紙が出てくる
    # (=製品の前提が崩れる)ため、A4サイズそのものを固定の回帰テストとして
    # 明示的に守る。
    import pypdf
    from reportlab.lib.units import cm as CM_PT_PER_CM

    segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    part = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    pdf_path = str(tmp_path / "job.pdf")
    render_a4_pdf(result, pdf_path)

    reader = pypdf.PdfReader(pdf_path)
    page = reader.pages[0]
    width_cm = float(page.mediabox.width) / CM_PT_PER_CM
    height_cm = float(page.mediabox.height) / CM_PT_PER_CM

    assert width_cm == pytest.approx(pdf_export.A4_WIDTH_CM, abs=0.001)
    assert height_cm == pytest.approx(pdf_export.A4_HEIGHT_CM, abs=0.001)

    # ページ内の「型紙を実際に印刷できる範囲」(=四辺の余白1cmを除いた領域)の
    # 大きさも、実際に描画に使っている定数と食い違っていないことを保証する。
    assert pdf_export.A4_USABLE_W_CM == pytest.approx(19.0, abs=0.0001)
    assert pdf_export.A4_USABLE_H_CM == pytest.approx(27.7, abs=0.0001)


def test_svg_preview_embeds_jp_subset_font_for_environment_independent_rendering(tmp_path):
    # 実際に生成したSVGプレビューをcairosvg(requirements-dev.txtに任意の目視
    # 確認用ツールとして declare済み)でPNG化して目視確認したところ、パーツ
    # ラベルの漢字部分が文字化け(豆腐)することがあった。原因を実際のChromium
    # (Playwrightで実機相当のレンダリングを確認)と突き合わせて調べたところ、
    # 実際のブラウザではfont-familyに指定した'Noto Sans CJK JP'等がシステム
    # フォントとして解決されて正しく表示される一方、cairosvgは
    # CSSの@font-face自体を一切解釈しない(cairosvg/text.pyがcairoの
    # select_font_faceにfont-family文字列を渡すだけで、埋め込みフォント
    # データやコンマ区切りのフォールバック順を見ていない)ため、閲覧側の
    # システムフォント資産だけに依存する状態だった。これはA4分割PDF側で
    # すでに解決済み(専用サブセットフォントをPDFファイル自体に埋め込むこと
    # で、閲覧側の環境に依存しないようにした)問題と全く同じ種類のリスクが、
    # SVGプレビュー側にだけ残っていたということ。同じサブセットフォント
    # (engine/assets/pattern_label_ja_subset.ttf)をbase64のdata URIとして
    # SVG自体に@font-faceで埋め込むことで、PDFと同様に閲覧環境の
    # フォント資産に依存しないようにした。ここでは、実際に生成したSVGの中に
    # @font-face宣言と、ディスク上のフォントファイルと完全に一致するbase64
    # データが埋め込まれていることを検証する
    # (cairosvg自体は@font-faceを解釈できないため、この回帰テストの検証には
    # 使わない。実際の見た目の検証はChromium等の実ブラウザで行うべきもので、
    # ここではSVGの中身が正しく組み立てられているかを保証する)。
    segments = parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z")
    part = finalize_part("sleeve", "curve", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    svg_path = str(tmp_path / "job.svg")
    render_layout_svg(result, svg_path)

    with open(svg_path, encoding="utf-8") as f:
        svg_text = f.read()

    assert "@font-face" in svg_text
    assert pdf_export._JP_FONT_NAME in svg_text

    import base64
    import re

    match = re.search(r"base64,([A-Za-z0-9+/=]+)\)", svg_text)
    assert match, "SVGに@font-faceのdata URIが見つからない"
    embedded_bytes = base64.b64decode(match.group(1))
    with open(pdf_export._JP_FONT_PATH, "rb") as f:
        disk_bytes = f.read()
    assert embedded_bytes == disk_bytes


def test_svg_preview_rotation_note_matches_pdf_wording_and_font_coverage(tmp_path):
    # SVGプレビュー(画面表示用)とA4分割PDF(印刷用)は同じ「90度回転して
    # 配置されたパーツ」という情報を注記するが、以前はそれぞれ別の文言
    # ("↻90°(要:布目確認)" 対 "(90度回転・布目確認)")を使っていた。
    # 表現の不統一に加え、SVG側の文言だけが使っていた"↻"(U+21BB)・
    # "°"(U+00B0)・"要"(U+8981)は、PDFの文字化け再発防止テスト
    # (test_jp_label_font_contains_every_character_the_pdf_actually_draws)
    # が実際に検証している「フォントに実在する文字」の対象に含まれておらず、
    # 案の定サブセットフォントには存在しなかった(実際にreportlabの
    # charToGlyphで確認済み)。SVG側もPDFと同じ、フォント収録済みの文言に
    # 統一した。ここでは実際に生成したSVGの中身で両者が一致すること、かつ
    # その文言の全文字がサブセットフォントに実在することを検証する。
    from reportlab.pdfbase.pdfmetrics import getFont

    # 横長(42cm x 12cm、縫い代込み)のパーツを、それより狭い生地幅に
    # allow_rotation=Trueで配置させ、確実に90度回転配置を発生させる。
    segments = parse_path("M 0 0 L 40 0 L 40 10 L 0 10 Z")
    part = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=15.0, allow_rotation=True)
    assert any(p.rotated for p in result.placed), "テスト条件的に回転配置が発生していない"

    svg_path = str(tmp_path / "job.svg")
    render_layout_svg(result, svg_path)
    with open(svg_path, encoding="utf-8") as f:
        svg_text = f.read()

    rotation_note = "(90度回転・布目確認)"
    assert rotation_note in svg_text
    assert "↻" not in svg_text and "要" not in svg_text

    if pdf_export._LABEL_FONT == "Helvetica":
        pytest.skip("このテスト環境では日本語フォントが読み込めていないため対象外")
    face = getFont(pdf_export._LABEL_FONT).face
    missing = sorted({ch for ch in rotation_note if ord(ch) not in face.charToGlyph})
    assert not missing, f"フォントに存在しない文字: {missing}"


def test_clip_segment_to_rect_returns_intersecting_portion_only():
    # 縦に長い線分(y=-10〜110)を、矩形y=[0,30]でクリップすると、
    # 交差する区間(y=0〜30)だけが返る。
    clipped = _clip_segment_to_rect((5.0, -10.0), (5.0, 110.0), xmin=0, ymin=0, xmax=10, ymax=30)
    assert clipped is not None
    (x0, y0), (x1, y1) = clipped
    assert x0 == pytest.approx(5.0) and x1 == pytest.approx(5.0)
    assert {round(y0, 6), round(y1, 6)} == {0.0, 30.0}


def test_clip_segment_to_rect_returns_none_when_fully_outside():
    clipped = _clip_segment_to_rect((100.0, 100.0), (200.0, 200.0), xmin=0, ymin=0, xmax=10, ymax=10)
    assert clipped is None


def _stroke_color_ops(content_bytes: bytes) -> list[tuple[float, float, float]]:
    """PDFページのcontent streamから、ストローク色設定(`r g b RG`)を全て抜き出す。"""
    ops = []
    for m in re.finditer(rb"([\-0-9.]+) ([\-0-9.]+) ([\-0-9.]+) RG", content_bytes):
        ops.append(tuple(float(v) for v in m.groups()))
    return ops


def test_grainline_is_drawn_on_every_a4_tile_it_actually_passes_through(tmp_path):
    # 実際に生成したA4分割PDFの各ページのcontent streamを検査して見つけた
    # 実バグの修正(再発防止テスト): 布目線(grainline)は合印と違ってパーツの
    # 縦幅いっぱいに伸びる長い線分で、A4タイル1枚の高さ(27.7cm)を超える
    # ことが多い(例: パンツの脚パーツ、丈の長いスカート等)。以前は
    # 「線分全体の中点がこのタイルに入っているか」だけで判定し、入っていれば
    # 元の(クリップしていない)線分をそのまま描画していたため、線分全体の
    # 中点が属するタイル1枚にしか布目線が描かれず、実際にその布目線が
    # 視覚的に通過している他のタイルには全く描かれていなかった。
    # ここでは、高さ72cm(A4タイル1枚の高さの3倍近い)の縦長パーツを実際に
    # A4分割PDFに書き出し、パーツが縦方向に3段のタイルへ分割される
    # レイアウトで、布目線の色(青、setStrokeColorRGB(0, 0, 0.8))を示す
    # `RG`オペレータが、複数ページ(=複数タイル)に渡って実際に出現する
    # ことを検証する。修正前はこれが常に1ページだけだった。
    import pypdf

    segments = parse_path("M 0 0 L 20 0 L 20 70 L 0 70 Z")
    part = finalize_part("pants", "straight", segments, seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=25.0)

    pdf_path = str(tmp_path / "tall.pdf")
    render_a4_pdf(result, pdf_path)

    reader = pypdf.PdfReader(pdf_path)
    assert len(reader.pages) > 3, "テスト条件的にA4タイルが複数段に渡っていない"

    pages_with_grainline = 0
    for page in reader.pages:
        data = page.get_contents().get_data()
        has_blue_stroke = any(
            abs(r) < 0.01 and abs(g) < 0.01 and abs(b - 0.8) < 0.01
            for r, g, b in _stroke_color_ops(data)
        )
        if has_blue_stroke:
            pages_with_grainline += 1

    # パーツは縦に3段のタイルへ分割されるはずなので、布目線もその3段全てに
    # 現れるべき(=1ページだけに限定されていた不具合が再発していないことの
    # 直接的な証拠)。
    assert pages_with_grainline >= 3, (
        f"布目線が描かれたページ数={pages_with_grainline}"
        "(3段に渡るはずなのに1ページ等に限定されていないか確認)"
    )


# --- round11: 細いパーツでのラベル文字はみ出し対策 ------------------------

def test_fit_label_keeps_the_default_size_when_it_already_fits():
    from engine.pdf_export import _fit_label_to_width, _PART_LABEL_FONT_SIZE, CM

    text, size = _fit_label_to_width("front_bodice(round_neck)", 32.0 * CM)
    assert text == "front_bodice(round_neck)"
    assert size == _PART_LABEL_FONT_SIZE


def test_fit_label_shrinks_the_font_for_a_narrow_part():
    from reportlab.pdfbase import pdfmetrics
    from engine.pdf_export import _fit_label_to_width, _LABEL_FONT, _PART_LABEL_FONT_SIZE, CM

    # round11で実測した実バグのケース: 幅5.0cmのパーツに対し、9ptでは
    # 6.35cm必要ではみ出していた。
    label = "custom_panel(肩ひも(左右共通・裏地付き))"
    assert pdfmetrics.stringWidth(label, _LABEL_FONT, _PART_LABEL_FONT_SIZE) > 5.0 * CM

    text, size = _fit_label_to_width(label, 5.0 * CM)
    assert size < _PART_LABEL_FONT_SIZE
    assert text == label  # 縮小だけで収まるので文字は削らない
    assert pdfmetrics.stringWidth(text, _LABEL_FONT, size) <= 5.0 * CM


def test_fit_label_truncates_with_an_ellipsis_when_shrinking_is_not_enough():
    from reportlab.pdfbase import pdfmetrics
    from engine.pdf_export import (
        _fit_label_to_width, _LABEL_FONT, _PART_LABEL_MIN_FONT_SIZE, _PART_LABEL_ELLIPSIS, CM,
    )

    label = "custom_panel(とても長い名前をつけた特殊なパーツ名称)"
    text, size = _fit_label_to_width(label, 2.0 * CM)
    assert size >= _PART_LABEL_MIN_FONT_SIZE  # 読めない大きさまでは縮めない
    assert text.endswith(_PART_LABEL_ELLIPSIS)
    assert pdfmetrics.stringWidth(text, _LABEL_FONT, size) <= 2.0 * CM


def test_fit_label_never_returns_an_empty_string_for_an_extremely_narrow_part():
    from engine.pdf_export import _fit_label_to_width, CM

    text, size = _fit_label_to_width("custom_panel(あ)", 0.1 * CM)
    assert text  # 何も描かないより、切り詰めてでも何か描く
    assert size > 0


def test_every_part_label_fits_inside_its_own_width_in_a_real_pdf(tmp_path):
    """実際に生成した型紙の全パーツで、ラベルがパーツ幅に収まることを確認する
    (細いカスタムパーツを含む構成で、はみ出しが再発しないことの回帰テスト)。
    """
    from reportlab.pdfbase import pdfmetrics
    from engine.pdf_export import _fit_label_to_width, _LABEL_FONT, CM
    from engine.custom_panel import calibrate_points_to_cm
    from engine.measurements import STANDARD_M
    from engine.pipeline import (
        GarmentSpec, PatternForgePipeline, build_custom_panel_requests,
    )

    points_cm = calibrate_points_to_cm([(0, 0), (30, 0), (30, 400), (0, 400)],
                                        (0, 0), (30, 0), 3.0)
    requests = build_custom_panel_requests(label="肩ひも(左右共通・裏地付き)",
                                            points_cm=points_cm, quantity=1)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(GarmentSpec(parts=requests), STANDARD_M)

    checked = 0
    for placed in result.nesting.placed:
        label = placed.part.display_name
        if placed.rotated:
            label += "(90度回転・布目確認)"
        min_x, _, max_x, _ = placed.bbox()
        width_pt = (max_x - min_x) * CM
        text, size = _fit_label_to_width(label, width_pt)
        assert pdfmetrics.stringWidth(text, _LABEL_FONT, size) <= width_pt + 1e-6
        checked += 1
    assert checked > 0


# --- round11: 全体図 + 記号の凡例ページ ------------------------------------

def _pdf_page_count(path):
    import pypdf
    return len(pypdf.PdfReader(path).pages)


def _render_sample_pdf(tmp_path, **spec_kwargs):
    from engine.measurements import STANDARD_M
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(**spec_kwargs)
    result = pipeline.generate_from_selection(spec, STANDARD_M)
    pdf_path = [str(p) for p in tmp_path.iterdir() if str(p).endswith(".pdf")][0]
    return pdf_path, result.nesting


def test_every_static_pdf_text_character_exists_in_the_embedded_font():
    """round11で実際に踏んだ事故の再発防止テスト。

    埋め込みフォントはサブセットのため、収録されていない文字をreportlabに
    渡すと豆腐(□)ですらなく「黙って消える」。全体図ページを追加した際に
    追加漢字の登録漏れがあり、「記号の凡例」が「の」とだけ描かれていた。
    例外も警告も出ないため、PDFを画像化して目視するまで気付けなかった。

    描画する固定文言は engine/pdf_export.py の PDF_STATIC_TEXTS に集約して
    あるので、その全文字がフォントに収録されていることをここで検証する。
    (文言を足してフォントを再生成し忘れると、このテストが落ちる。)
    """
    from fontTools.ttLib import TTFont
    from engine.pdf_export import PDF_STATIC_TEXTS, _JP_FONT_PATH, _LABEL_FONT, _JP_FONT_NAME

    if _LABEL_FONT != _JP_FONT_NAME:
        pytest.skip("サブセットフォントを読み込めない環境")

    cmap = set(TTFont(_JP_FONT_PATH).getBestCmap())
    missing = sorted({ch for ch in "".join(PDF_STATIC_TEXTS)
                       if ord(ch) > 0x7F and ord(ch) not in cmap})
    assert missing == [], (
        f"フォント未収録の文字があります: {''.join(missing)} / "
        "`python3 scripts/build_pattern_label_font.py` を実行してください"
    )


def test_pdf_starts_with_an_overview_page_showing_the_assembly_map_and_legend(tmp_path):
    import pypdf

    pdf_path, result = _render_sample_pdf(
        tmp_path, neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    assert result.placed

    text = pypdf.PdfReader(pdf_path).pages[0].extract_text()
    # 見出しと凡例の主要項目が、欠落せずそのまま入っていること
    for expected in ("貼り合わせ図と記号の凡例", "記号の凡例", "実線 = 裁断線",
                      "破線 = 縫い線", "短い線 = 合印", "矢印の線 = 布目線",
                      "実物大ではありません"):
        assert expected in text, f"{expected!r} が全体図ページに見当たらない"

    # 生地幅・枚数などの全体情報も載っていること
    assert f"{result.fabric_width_cm:.0f}cm" in text


def test_overview_page_lists_every_placed_part_name(tmp_path):
    import pypdf

    pdf_path, result = _render_sample_pdf(
        tmp_path, neckline="round_neck", sleeve_style="straight", skirt_style="flare",
        include_collar=True, include_cuffs=True, include_waistband=True)
    text = pypdf.PdfReader(pdf_path).pages[0].extract_text()
    for placed in result.placed:
        # 縮小図では幅に応じて省略されることがあるため、先頭数文字で確認する。
        head = placed.part.display_name[:6]
        assert head in text, f"{placed.part.display_name} が全体図に見当たらない"


def test_overview_page_adds_exactly_one_page(tmp_path):
    """全体図ページが1枚だけ増えること(タイル枚数は変わらないこと)。"""
    import math
    from engine.pdf_export import A4_USABLE_W_CM, A4_USABLE_H_CM

    pdf_path, result = _render_sample_pdf(
        tmp_path, neckline="round_neck", sleeve_style=None, skirt_style=None)
    cols = max(1, math.ceil(result.fabric_width_cm / A4_USABLE_W_CM))
    rows = max(1, math.ceil(result.used_length_cm / A4_USABLE_H_CM)) if result.used_length_cm else 1
    assert _pdf_page_count(pdf_path) == rows * cols + 1


def test_overview_page_is_skipped_when_nothing_could_be_placed(tmp_path):
    """配置できたパーツが1つも無い場合は、描くものが無いので全体図を出さない。"""
    from engine.nesting import NestingResult
    from engine.pdf_export import render_a4_pdf

    import math
    from engine.pdf_export import A4_USABLE_W_CM

    empty = NestingResult(placed=[], unplaced=[], fabric_width_cm=110.0,
                           used_length_cm=0.0, waste_ratio=0.0)
    out = str(tmp_path / "empty.pdf")
    render_a4_pdf(empty, out)
    # 全体図ページは付かず、タイルページ(1行×必要列数)だけになる。
    expected_tiles = max(1, math.ceil(110.0 / A4_USABLE_W_CM))
    assert _pdf_page_count(out) == expected_tiles
