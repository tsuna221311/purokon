"""round31: 型紙に「何を何枚、どう裁つか」を書く。

round30まで、型紙に書いてあったのはパーツ名・布目線・縫い代幅だけだった。
JIS L 0110の表示記号が前提にしている「そのまま裁断に使える型紙」には、
生地の種類・裁断枚数・わ裁ちの有無・接着芯の指示が要る。

実際に布を無駄にするのは次の2つ:
  * この型紙の身頃は左右つながった**全幅**で出る。日本の市販型紙に多い
    「半身+わ裁ち」のつもりで中心を布のわに合わせると、倍幅で裁ち上がる。
  * 衿・カフス・見返し・ウエストバンドに接着芯を貼り忘れると、衿が立たず
    カフスがよれる(出典: DRCOS「接着芯の縫い代処理」)。
"""

import pytest

from engine.cutting import (
    FABRIC_LABEL, INTERFACED_PART_TYPES, cutting_note, needs_interfacing,
)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.svgpath import parse_path
from engine.seam import finalize_part


def test_the_note_states_fabric_count_and_fold():
    assert cutting_note("front_bodice") == f"{FABRIC_LABEL}1枚 わ裁ち不要"
    assert cutting_note("sleeve", 2) == f"{FABRIC_LABEL}2枚 わ裁ち不要"
    assert cutting_note("front_bodice", 1, cut_on_fold=True) \
        == f"{FABRIC_LABEL}1枚 わ裁ち"


@pytest.mark.parametrize("part_type", sorted(INTERFACED_PART_TYPES))
def test_the_interfaced_parts_say_so(part_type):
    """衿・カフス・見返し・ウエストバンドに接着芯の指示が出ること。"""
    assert needs_interfacing(part_type)
    assert "接着芯あり" in cutting_note(part_type)


@pytest.mark.parametrize("part_type", ["front_bodice", "back_bodice", "sleeve",
                                        "skirt", "front_pants", "back_pants"])
def test_the_other_parts_do_not(part_type):
    """身頃・袖・スカート・パンツには接着芯を指示しないこと。

    「どこにでも書いてある」指示は読み飛ばされるので、貼る所だけに書く。
    """
    assert not needs_interfacing(part_type)
    assert "接着芯" not in cutting_note(part_type)


def test_a_zero_or_negative_count_still_reads_as_one():
    """枚数が壊れた値でも「0枚裁つ」とは書かないこと。"""
    assert cutting_note("sleeve", 0) == f"{FABRIC_LABEL}1枚 わ裁ち不要"


def test_the_finalized_part_carries_the_note():
    part = finalize_part("collar", "", parse_path("M 0 0 L 10 0 L 10 4 L 0 4 Z"),
                         seam_allowance_cm=1.0)
    assert "接着芯あり" in part.cutting_note
    assert part.cut_quantity == 1 and part.cut_on_fold is False


def test_every_generated_part_gets_a_note(tmp_path):
    """実際に生成した全パーツが、空でない裁ち方の指示を持つこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare", include_collar=True,
                              include_cuffs=True, include_waistband=True)
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37))
    seen = set()
    for part in result.finalized_parts:
        note = part.cutting_note
        assert note and "枚" in note and "わ裁ち" in note, part.part_type
        seen.add(part.part_type)
    # 接着芯が要るパーツが実際に含まれていて、指示が出ていること。
    interfaced = [p for p in result.finalized_parts if needs_interfacing(p.part_type)]
    assert interfaced, sorted(seen)
    assert all("接着芯あり" in p.cutting_note for p in interfaced)


def test_the_note_reaches_the_printed_pattern(tmp_path):
    """指示が、実際に印刷するPDFの文字として埋め込まれていること。

    (画面のプレビューにだけ出て紙に出ない、では裁断の役に立たない。)
    """
    pypdf = pytest.importorskip("pypdf")
    from engine import pdf_export
    if pdf_export._LABEL_FONT == "Helvetica":
        pytest.skip("この環境では日本語フォントが読み込めていない")

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, Measurements(83, 66, 91, 158, 52, 37))
    path = result.output_files.get("pdf")
    assert path, sorted(result.output_files)
    text = "".join(page.extract_text() or ""
                   for page in pypdf.PdfReader(path).pages)
    assert "わ裁ち不要" in text
