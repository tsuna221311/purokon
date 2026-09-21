"""round39: 手持ちの生地で足りるかの判定と、プロジェクター投影用の出力。

【何が足りなかったか】round38の買い物メモで「幅ごとに何m要るか」は出せる
ようになった。だが実際によくあるのは**これから買う**話ではなく、
「押し入れに幅110cmの生地が1.8mある。これで作れる?」である。表を見て
引き算すれば足りるかは分かるが、**足りないと分かったあとが行き止まり**だった。

出力の側も、A4に分割して何十枚も貼り合わせる前提だった。プロジェクターで
布に直接投影して裁つやり方には、別の形のPDFが要る。
"""

import functools

import pytest

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.stash import (MIN_SKIRT_LENGTH_CM, MIN_STASH_LENGTH_CM,
                           evaluate_stash)

STANDARD = Measurements(84, 68, 92, 160, 54, 37)


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    pipeline = PatternForgePipeline(
        output_dir=str(tmp_path_factory.mktemp("stash")))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, STANDARD)
    return pipeline, spec, result


# --- 判定 ---------------------------------------------------------------------

def test_enough_fabric_is_reported_with_the_leftover(setup):
    """足りる場合は、余る量まで出すこと。

    「足ります」だけだと、はぎれが出るのか、ぎりぎりなのかが分からない。
    """
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=400)
    assert verdict.fits
    assert verdict.leftover_cm == pytest.approx(400 - verdict.needed_length_cm)
    assert verdict.shortfall_cm == 0
    assert verdict.suggestions == []


def test_not_enough_fabric_says_how_much_is_missing(setup):
    """足りない場合は、何cm足りないかを出すこと。"""
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=200)
    assert not verdict.fits
    assert verdict.shortfall_cm == pytest.approx(verdict.needed_length_cm - 200)


def test_a_suggestion_is_verified_by_actually_rebuilding_the_pattern(setup):
    """「丈を詰めれば入る」という提案が、実際に入ることを確かめた値であること。

    ここがこの機能の肝である。「たぶん5cm詰めれば入る」で外すと、
    利用者は生地を裁ってから足りないことに気づく。提案どおりに作り直して、
    本当に手持ちに収まるかを検算する。
    """
    pipeline, spec, result = setup
    have_length = 200
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=have_length)
    shortening = [s for s in verdict.suggestions if s.kind == "skirt_length"]
    assert shortening, [s.kind for s in verdict.suggestions]

    # 提案文から「何cmにすれば入る」と言っているかを取り出して、その丈で
    # 作り直し、本当に収まるか確かめる。
    import re
    match = re.search(r"(\d+)cmから(\d+)cmにすると", shortening[0].detail)
    assert match, shortening[0].detail
    proposed = float(match.group(2))
    rebuilt = pipeline.generate_from_selection(
        spec, STANDARD, fabric_width_candidates=(110.0,),
        design_length_overrides={"skirt": proposed}, skip_export=True)
    assert rebuilt.nesting.used_length_cm <= have_length, (
        f"提案どおり{proposed}cmにしても{rebuilt.nesting.used_length_cm:.1f}cm要る")
    assert not rebuilt.nesting.unplaced


def test_when_only_a_combination_fits_it_is_offered(setup):
    """単独では収まらないが組み合わせれば収まる場合に、それを出すこと。

    【最初これを落としていた】「回転を許す」と「丈を詰める」を別々にしか
    試しておらず、実測(標準M・幅110cm・手持ち180cm)では
        そのまま247cm / 回転あり237cm / スカート30cm 187cm
        回転 + スカート30cm **171cm** ← これだけが収まる
    単独では1つも収まらないので「収まりません」と答えていた。
    **入る道があるのに無いと言う**のがいちばん悪い。
    """
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=180)
    assert not verdict.fits
    combined = [s for s in verdict.suggestions if s.kind.startswith("rotation_and_")]
    assert combined, [s.kind for s in verdict.suggestions]
    assert "両方あわせる" in combined[0].detail


def test_impossible_cases_get_no_invented_suggestion(setup):
    """どうやっても入らない場合に、提案をひねり出さないこと。

    「詰めれば入る」という嘘の方が、「入りません」より有害である。

    【round59で変わったこと】手持ちを使い切る提案(回転・丈詰め)は、
    ここでは1つも出ない——それは変わらない。変わったのは、
    **買う話は言えるようになった**ことである。「幅140cmの生地なら
    190cmで足ります」は推測ではなく、その幅で実際に並べ直して測った値で、
    ひねり出した逃げ道ではない。手持ちで入る道が無いことを言ったうえで、
    次にすること(買う)の数字を渡す。
    """
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=60)
    assert not verdict.fits
    # 手持ちを使い切る提案は1つも無い。
    assert [s for s in verdict.suggestions if s.kind != "wider_fabric"] == []
    # 収まらなかったことは必ず言う。
    assert verdict.notes and "収まりませんでした" in verdict.notes[0]
    # 足りない量も必ずどこかで言う(round59で、買う提案が出るときは
    # 同じ数字を3回書かないよう、注記から提案側へ寄せた)。
    shown = " ".join(verdict.notes + [s.detail for s in verdict.suggestions])
    assert f"{verdict.buy_more_cm}cm" in shown, shown


def test_a_narrow_fabric_is_not_blamed_on_length(setup):
    """幅が足りない場合に、丈を詰める提案をしないこと。

    幅が足りないのは長さの問題ではないので、丈を詰めても解決しない。
    そこで「何cm足りません」と数字を出すと、その分足せば作れると読める。
    """
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=40, have_length_cm=1000)
    assert not verdict.fits
    assert not verdict.all_parts_fit
    assert verdict.suggestions == []
    assert any("幅が足りていない" in n for n in verdict.notes), verdict.notes


def test_a_shortening_suggestion_never_goes_below_the_floor(setup):
    """短くしすぎる提案をしないこと(スカートが下着より短くなる等)。"""
    pipeline, spec, result = setup
    verdict = pipeline.evaluate_stash_for(
        result, spec, STANDARD, have_width_cm=110, have_length_cm=200)
    import re
    for suggestion in verdict.suggestions:
        match = re.search(r"から(\d+)cmにすると", suggestion.detail)
        if match and suggestion.kind.endswith("skirt_length"):
            assert float(match.group(1)) >= MIN_SKIRT_LENGTH_CM


def test_a_silly_stash_length_is_refused(setup):
    """入力ミスとしか思えない長さを弾くこと。"""
    pipeline, spec, result = setup
    with pytest.raises(ValueError):
        pipeline.evaluate_stash_for(result, spec, STANDARD,
                                     have_width_cm=110,
                                     have_length_cm=MIN_STASH_LENGTH_CM - 1)


def test_probing_does_not_write_files(setup, tmp_path):
    """判定のための作り直しが、ファイルを書き出さないこと。

    途中経過のSVG/PDF/DXFは誰も見ない。書き出すと時間もディスクも無駄になる
    (実測: 3.93秒 → 1.72秒)。
    """
    import glob
    import os

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, STANDARD)
    before = len(glob.glob(os.path.join(str(tmp_path), "*")))
    pipeline.evaluate_stash_for(result, spec, STANDARD,
                                 have_width_cm=110, have_length_cm=180)
    assert len(glob.glob(os.path.join(str(tmp_path), "*"))) == before


# --- プロジェクター投影用の出力 -----------------------------------------------

def test_the_projector_pdf_is_one_page_at_true_size(setup):
    """1枚もので、実寸(生地の寸法+余白)であること。

    投影するのに分割は意味が無い。貼り合わせの手間を消すのが目的である。
    """
    import pypdf

    from engine.pdf_export import PROJECTOR_PADDING_CM

    _pipeline, _spec, result = setup
    reader = pypdf.PdfReader(result.output_files["projector"])
    assert len(reader.pages) == 1

    box = reader.pages[0].mediabox
    width_cm = float(box.width) / 72 * 2.54
    height_cm = float(box.height) / 72 * 2.54
    assert width_cm == pytest.approx(
        result.nesting.fabric_width_cm + 2 * PROJECTOR_PADDING_CM, abs=0.2)
    assert height_cm == pytest.approx(
        result.nesting.used_length_cm + 2 * PROJECTOR_PADDING_CM, abs=0.2)


def test_the_projector_pdf_tells_you_to_calibrate_first(setup):
    """較正の指示が、投影される像の中に入っていること。

    投影してからでないと合わせられないので、紙の外に書いても意味が無い。
    """
    import pypdf

    from engine.pdf_export import PROJECTOR_GRID_CM

    _pipeline, _spec, result = setup
    text = pypdf.PdfReader(result.output_files["projector"]).pages[0].extract_text()
    assert "格子" in text
    assert f"{PROJECTOR_GRID_CM:.0f}cm" in text
    # 文字が落ちていないこと(サブセットフォントの収録漏れ)
    assert "\x00" not in text


def test_the_projector_lines_are_thick_enough_to_see(setup):
    """線が、投影して追える太さであること。

    出典: Craftstorming「Tips for using pdf sewing patterns on a projector」
    「線の太さは約3ポイント必要」。印刷用の細い線(0.5pt前後)のままでは、
    投影すると細くて追えない。
    """
    from engine.pdf_export import (PROJECTOR_CUT_LINE_WIDTH_PT,
                                   PROJECTOR_STITCH_LINE_WIDTH_PT)

    assert PROJECTOR_CUT_LINE_WIDTH_PT >= 3.0
    assert PROJECTOR_STITCH_LINE_WIDTH_PT >= 1.0
    # 裁断線の方が太いこと(どちらで裁つのかが見て分かる)
    assert PROJECTOR_CUT_LINE_WIDTH_PT > PROJECTOR_STITCH_LINE_WIDTH_PT


def test_the_a4_pdf_is_unchanged_by_the_projector_output(setup):
    """プロジェクター用を足したことで、A4分割PDFが変わっていないこと。"""
    import pypdf

    _pipeline, _spec, result = setup
    a4 = pypdf.PdfReader(result.output_files["pdf"])
    first = a4.pages[0].mediabox
    assert float(first.width) / 72 * 2.54 == pytest.approx(21.0, abs=0.1)
    assert float(first.height) / 72 * 2.54 == pytest.approx(29.7, abs=0.1)
