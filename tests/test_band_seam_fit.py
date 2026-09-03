"""round15: 帯状パーツを「実際に縫い付けられる辺」で測り、衿を首ぐりに合わせる。

守りたいのは3点:
  1. 帯(衿・カフス・ウエストバンド)の長さを、外接矩形ではなく縫い付け辺で測ること。
  2. 衿の長さが、実際に縫い付ける首ぐりの長さと一致すること。
  3. 測れない組み合わせ(タートルネック+衿、前開きパネル)で、黙って
     おかしなものを出さないこと。
"""

import pytest

from engine.compatibility import (
    COLLAR_EASE_CM,
    CUFFS_EASE_CM,
    WAISTBAND_CLOSURE_EASE_CM,
    band_length,
    check_seam_compatibility,
    hem_or_wrist_opening_length,
    neckline_length,
    seam_edge_length,
    waist_opening_length,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.scaling import scale_band_to_seam_length
from engine.seam import finalize_part
from engine.svgpath import segments_to_polyline
from engine.templates_db import TemplateDB

DB = TemplateDB()
BAND_PART_TYPES = ("collar", "cuffs", "waistband")

BODIES = [
    ("標準M", STANDARD_M),
    ("細身", Measurements(76, 60, 86, 152, 49, 35)),
    ("バスト大", Measurements(100, 80, 104, 160, 53, 38)),
    ("バスト特大", Measurements(112, 95, 115, 163, 54, 39)),
]

#: 標準Mサイズのテンプレートでの (外接矩形の幅, 縫い付け辺の長さ)。
#: round14までは左の値が「帯の長さ」として使われていた。実測して固定し、
#: テンプレートを描き変えたときに気付けるようにしておく。
EXPECTED_BAND_LENGTHS = {
    ("collar", ""): (40.0, 40.0),
    ("collar", "shirt_collar"): (40.0, 32.0),
    ("collar", "bow_collar"): (44.0, 32.0),
    ("collar", "peter_pan_collar"): (40.0, 36.0),
    ("collar", "ruffle_collar"): (40.0, 40.0),
    ("collar", "convertible_collar"): (40.0, 28.0),
    ("cuffs", ""): (20.0, 20.0),
    ("cuffs", "wide"): (20.0, 20.0),
    ("cuffs", "ruffle"): (20.0, 20.0),
    ("cuffs", "button_tab"): (24.0, 20.0),
    ("waistband", ""): (70.0, 70.0),
    ("waistband", "wide"): (70.0, 70.0),
    ("waistband", "elastic"): (70.0, 70.0),
    ("waistband", "contour"): (70.0, 70.1),
}


def _band(part_type: str, variation: str, segments=None):
    segments = segments if segments is not None else DB.get(part_type, variation)
    return finalize_part(part_type, variation, segments,
                          seam_edge=DB.get_seam_edge(part_type, variation))


# --- 縫い付け辺の宣言と計測 -------------------------------------------------

def test_every_band_template_declares_its_seam_edge():
    """全ての帯状パーツが「どちらの辺を縫い付けるか」を宣言していること。

    宣言が無いと`seam_edge_length`が外接矩形へフォールバックし、
    round14までの誤った測り方へ静かに戻ってしまう。
    """
    missing = [(p, v) for (p, v) in DB.available()
               if p in BAND_PART_TYPES and DB.get_seam_edge(p, v) not in ("top", "bottom")]
    assert missing == []


@pytest.mark.parametrize("key,expected", sorted(EXPECTED_BAND_LENGTHS.items()))
def test_seam_edge_length_differs_from_the_bounding_box(key, expected):
    """縫い付け辺の実測値が、記録した値と一致すること。

    襟先やボタンタブは左右へ張り出すので、外接矩形の幅は縫い付け辺より
    長くなる。round14まではこの差を無視していたため、例えば
    convertible_collarは目標より30%短い辺で仕上がっていた。
    """
    part_type, variation = key
    expected_bbox, expected_seam = expected
    band = _band(part_type, variation)
    assert band_length(band) == pytest.approx(expected_bbox, abs=0.05)
    assert seam_edge_length(band) == pytest.approx(expected_seam, abs=0.05)


def test_seam_edge_length_falls_back_to_the_bounding_box_without_a_declaration():
    """宣言が無いパーツでは従来通り外接矩形の幅を返すこと。"""
    band = finalize_part("collar", "", DB.get("collar", ""))  # seam_edge未指定
    assert seam_edge_length(band) == pytest.approx(band_length(band))


def test_curved_seam_edge_is_measured_as_an_arc():
    """辺そのものが曲線のパーツ(コンターウエストバンド)で、弧長を返すこと。

    水平な辺が見つからないので、左右の端点を結ぶ輪郭の弧を測る経路に入る。
    曲線なので外接矩形の幅よりわずかに長くなる。
    """
    band = _band("waistband", "contour")
    assert seam_edge_length(band) > band_length(band)
    assert seam_edge_length(band) == pytest.approx(70.1, abs=0.1)


# --- 帯を縫い付け辺の長さに合わせる ---------------------------------------

@pytest.mark.parametrize("part_type,variation", sorted(EXPECTED_BAND_LENGTHS))
def test_scaling_a_band_hits_the_target_on_the_seam_edge(part_type, variation):
    """目標長さが、外接矩形ではなく縫い付け辺に対して達成されること。"""
    target = 55.0
    scaled = scale_band_to_seam_length(part_type, variation, DB.get(part_type, variation),
                                        target, seam_edge=DB.get_seam_edge(part_type, variation))
    band = _band(part_type, variation, scaled.segments)
    assert seam_edge_length(band) == pytest.approx(target, abs=0.05), (part_type, variation)


def test_button_tab_cuff_was_the_worst_offender():
    """round14までの測り方だと、ボタンタブ付きカフスが16.7%短くなったこと。

    改善の大きさを記録として固定しておく(外接矩形24cmに対し縫い付け辺は
    20cmなので、外接矩形を目標に合わせると縫い付け辺は目標の20/24になる)。
    """
    target = 24.0
    old_style_rx = target / band_length(_band("cuffs", "button_tab"))
    from engine.svgpath import scale_segments
    old = _band("cuffs", "button_tab",
                scale_segments(DB.get("cuffs", "button_tab"), old_style_rx, 1.0))
    assert seam_edge_length(old) == pytest.approx(target * 20.0 / 24.0, abs=0.05)

    new = _band("cuffs", "button_tab",
                scale_band_to_seam_length("cuffs", "button_tab", DB.get("cuffs", "button_tab"),
                                           target, seam_edge="top").segments)
    assert seam_edge_length(new) == pytest.approx(target, abs=0.05)


# --- 首ぐりの計測 -----------------------------------------------------------

#: 標準Mサイズのテンプレートでの首ぐりの長さ(前身頃, 後ろ身頃)。実測して固定する。
#: 前+後の合計が、そのまま衿の縫い付け辺の目標長さになる。
EXPECTED_NECKLINE_LENGTHS = {
    "round_neck": (22.37, 15.12),
    "v_neck": (30.75, 17.58),
    "square_neck": (25.23, 18.72),
    "boat_neck": (24.96, 24.63),
    "sweetheart": (26.75, 17.43),
}


@pytest.mark.parametrize("variation", sorted(EXPECTED_NECKLINE_LENGTHS))
def test_neckline_length_is_measured_per_shape(variation):
    """首ぐりの長さがネックライン形状ごとに正しく変わること。

    round14まではこの計測自体が無く、衿はどの形状でも同じ長さ(バスト比で
    決まる40cm前後)だった。前+後の合計は、ラウンド37.5cmからボート49.6cmまで
    12cm以上ひらく。
    """
    expected_front, expected_back = EXPECTED_NECKLINE_LENGTHS[variation]
    front = finalize_part("front_bodice", variation, DB.get("front_bodice", variation))
    back = finalize_part("back_bodice", variation, DB.get("back_bodice", variation))
    assert neckline_length(front) == pytest.approx(expected_front, abs=0.1), variation
    assert neckline_length(back) == pytest.approx(expected_back, abs=0.1), variation


def test_neckline_lengths_differ_enough_to_matter():
    """ネックライン形状による差が、衿を作り直すに値する大きさであること。

    「どの形状でも同じ長さの衿でよかったのでは」という疑いを排除するため、
    最短(ラウンド)と最長(ボート)の差を明示的に確認する。
    """
    totals = {v: sum(EXPECTED_NECKLINE_LENGTHS[v]) for v in EXPECTED_NECKLINE_LENGTHS}
    assert max(totals.values()) - min(totals.values()) > 10.0, totals


def test_neckline_length_is_none_where_it_cannot_be_measured():
    """測れないパーツではNoneを返し、当てずっぽうの値を返さないこと。"""
    turtle = finalize_part("front_bodice", "turtle_neck", DB.get("front_bodice", "turtle_neck"))
    assert neckline_length(turtle) is None
    zip_panel = finalize_part("front_bodice_zip_panel", "round_neck",
                               DB.get("front_bodice_zip_panel", "round_neck"))
    assert neckline_length(zip_panel) is None
    skirt = finalize_part("skirt", "tight", DB.get("skirt", "tight"))
    assert neckline_length(skirt) is None


# --- 衿を首ぐりに合わせる ---------------------------------------------------

@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "boat_neck",
                                       "square_neck", "sweetheart"])
def test_collar_matches_the_neckline_it_is_sewn_to(tmp_path, name, measurements, neckline):
    """衿の縫い付け辺が、身頃の首ぐり(前+後)と一致すること。

    round14までは衿をバスト比で拡大縮小していたため、実測(標準M)で
      ラウンド 首ぐり37.6cm vs 衿40.0cm
      Vネック   首ぐり48.3cm vs 衿40.0cm(8.3cm不足)
      ボート    首ぐり49.6cm vs 衿40.0cm(9.6cm不足)
    となり、Vネックやボートでは物理的に縫い付けられなかった。さらに
    shirt_collar等では縫い付け辺が32cmしかないので、差はもっと大きかった。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for style in ("", "shirt_collar", "convertible_collar", "peter_pan_collar"):
        spec = build_garment_spec(neckline=neckline, sleeve_style=None, skirt_style=None,
                                   include_collar=True, collar_style=style)
        result = pipeline.generate_from_selection(spec, measurements)
        bodices = [p for p in result.finalized_parts
                   if p.part_type in ("front_bodice", "back_bodice")]
        collars = [p for p in result.finalized_parts if p.part_type == "collar"]
        assert collars
        neck_total = sum(neckline_length(p) for p in bodices)
        collar_total = sum(seam_edge_length(p) for p in collars)
        assert collar_total == pytest.approx(neck_total + COLLAR_EASE_CM, abs=0.1), (
            name, neckline, style)
        assert "neckline_collar" not in {w.kind for w in result.compatibility_warnings()}


def test_neckline_collar_warning_fires_for_a_genuine_mismatch():
    """衿が首ぐりに合っていなければ、チェッカーが検出すること。

    上のテストで警告が出なくなったのが、検査の無効化ではなく寸法の改善で
    あることを示すため、あえて合っていない衿を作って確認する。
    """
    from engine.svgpath import scale_segments

    front = finalize_part("front_bodice", "round_neck", DB.get("front_bodice", "round_neck"))
    back = finalize_part("back_bodice", "round_neck", DB.get("back_bodice", "round_neck"))
    collar = _band("collar", "", scale_segments(DB.get("collar", ""), 0.5, 1.0))
    kinds = {w.kind for w in check_seam_compatibility([front, back, collar])}
    assert "neckline_collar" in kinds


def test_turtle_neck_with_a_separate_collar_is_rejected():
    """タートルネック+衿は、黙って使えない衿を出さずにエラーにすること。

    タートルネックは首ぐりそのものが台襟なので、衿を縫い付ける線が型紙上に
    存在しない。round14まではこの組み合わせでも生成でき、台襟とは無関係な
    長さの衿が1枚混ざっていた。
    """
    with pytest.raises(ValueError, match="タートルネック"):
        build_garment_spec(neckline="turtle_neck", sleeve_style=None, skirt_style=None,
                            include_collar=True, collar_style="")


def test_front_zip_collar_falls_back_without_crashing(tmp_path):
    """前開き+衿では首ぐりを測れないので、従来通りの採寸比へフォールバックし、
    例外にもならないこと(測れないことは正直な限界として残す)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None,
                               front_zip=True, include_collar=True, collar_style="")
    result = pipeline.generate_from_selection(spec, STANDARD_M)
    collars = [p for p in result.finalized_parts if p.part_type == "collar"]
    assert len(collars) == 1
    assert seam_edge_length(collars[0]) > 0


# --- 既存の帯チェックが縫い付け辺で行われること -----------------------------

def test_waistband_and_cuffs_still_match_their_partners(tmp_path):
    """ウエストバンド/カフスも、縫い付け辺の長さで相手と一致すること。

    測り方を外接矩形から縫い付け辺へ変えたので、生成側・検査側の双方が
    同じ辺を見ていることを確認する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for name, m in BODIES:
        for wb, cf in (("", ""), ("contour", "button_tab"), ("elastic", "ruffle")):
            spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                       skirt_style="tight", include_waistband=True,
                                       waistband_style=wb, include_cuffs=True, cuffs_style=cf)
            result = pipeline.generate_from_selection(spec, m)
            skirts = [p for p in result.finalized_parts if p.part_type == "skirt"]
            bands = [p for p in result.finalized_parts if p.part_type == "waistband"]
            sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
            cuffs = [p for p in result.finalized_parts if p.part_type == "cuffs"]
            waist_total = sum(waist_opening_length(p) for p in skirts)
            assert sum(seam_edge_length(p) for p in bands) == pytest.approx(
                waist_total + WAISTBAND_CLOSURE_EASE_CM, abs=0.1), (name, wb)
            wrist = hem_or_wrist_opening_length(sleeves[0])
            for cuff in cuffs:
                assert seam_edge_length(cuff) == pytest.approx(
                    wrist + CUFFS_EASE_CM, abs=0.1), (name, cf)
            kinds = {w.kind for w in result.compatibility_warnings()}
            assert "waist_opening_skirt" not in kinds
            assert "wrist_opening" not in kinds
