import pytest
from PIL import Image, ImageDraw

from engine.measurements import Measurements
from engine.part_classifier import ClassificationResult, PartClassifier
from engine.pipeline import PatternForgePipeline, build_garment_spec

STANDARD = Measurements(bust=84, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)


def _illustration_test_image():
    image = Image.new("RGB", (400, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(150, 50), (250, 50), (260, 300), (300, 300), (300, 340),
                  (100, 340), (100, 300), (140, 300)], fill="black")
    draw.rectangle([100, 340, 300, 780], fill="black")
    return image


def test_build_garment_spec_defaults():
    spec = build_garment_spec()
    part_types = {p.part_type for p in spec.parts}
    assert "front_bodice" in part_types
    assert "back_bodice" in part_types
    assert "sleeve" in part_types
    assert "skirt" in part_types


def test_build_garment_spec_rejects_turtleneck_zip_combo():
    with pytest.raises(ValueError):
        build_garment_spec(neckline="turtle_neck", front_zip=True)


@pytest.mark.parametrize("neckline", ["square_neck", "boat_neck", "sweetheart"])
def test_build_garment_spec_allows_zip_for_newly_added_necklines(neckline):
    # round9より前開きファスナー対応ネックラインをround_neck/v_neckの2種から
    # turtle_neckを除く5種へ拡大した(engine/pipeline.py
    # ZIP_COMPATIBLE_NECKLINESのコメント参照)。以前はこれら3種を
    # front_zip=Trueと組み合わせるとValueErrorになる仕様だった
    # (test_build_garment_spec_rejects_zip_for_new_necklinesという名前の
    # テストとしてround7時点では存在したが、round9でこのテストに置き換えた)。
    spec = build_garment_spec(neckline=neckline, front_zip=True)
    front = next(p for p in spec.parts if p.part_type == "front_bodice_zip_panel")
    assert front.variation == neckline
    assert front.quantity == 2
    back = next(p for p in spec.parts if p.part_type == "back_bodice")
    assert back.variation == f"{neckline}_zip"


@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "turtle_neck", "square_neck",
                                       "boat_neck", "sweetheart"])
def test_generate_from_selection_supports_every_neckline(tmp_path, neckline):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline=neckline, sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    assert len(result.finalized_parts) == 2  # front_bodice + back_bodice


def test_build_garment_spec_allows_zip_for_v_neck():
    spec = build_garment_spec(neckline="v_neck", front_zip=True)
    # round5よりfront_zip=Trueの前身頃はfront_bodice_zip_panel(中心前で
    # 分割した2枚構成)になる。variationはneckline自体(「_zip」接尾辞は
    # part_type名の方に表れるので付かない)。back_bodiceの方は従来通り
    # "v_neck_zip"のまま。
    front = next(p for p in spec.parts if p.part_type == "front_bodice_zip_panel")
    assert front.variation == "v_neck"
    assert front.quantity == 2
    back = next(p for p in spec.parts if p.part_type == "back_bodice")
    assert back.variation == "v_neck_zip"


@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart"])
def test_generate_from_selection_with_front_zip_produces_two_front_panels(tmp_path, neckline):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline=neckline, sleeve_style=None, skirt_style=None,
                               front_zip=True)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    zip_panels = [p for p in result.finalized_parts if p.part_type == "front_bodice_zip_panel"]
    assert len(zip_panels) == 2
    labels = {p.label_suffix for p in zip_panels}
    assert labels == {"左", "右"}
    # 通常のfront_bodiceはもう使われていないはず。
    assert not any(p.part_type == "front_bodice" for p in result.finalized_parts)


def test_front_zip_panel_gets_one_bust_dart_per_panel_on_the_outer_edge_only(tmp_path):
    # round6でfront_bodice_zip_panelにも脇ダーツ(バストダーツ)を適用できる
    # ようにした(engine/darts.py「前開きファスナー×脇ダーツの併用対応」参照)。
    # 左右それぞれのパネルの外側の脇線に1本ずつ入る。
    #
    # round11でこのpart_typeにウエストダーツも入るようになったため、
    # dart_countは「脇ダーツ+ウエストダーツ」の合計になる。このテストの本来の
    # 意図(脇ダーツはパネル1枚につき1本、外側の脇線だけに入る)を保つため、
    # バスト比とウエスト比を揃えてウエストダーツが発火しない採寸を使い、
    # 脇ダーツだけを単独で確認する。ウエストダーツ側の挙動は
    # tests/test_darts.pyの round11 節で個別に確認している。
    from engine.measurements import STANDARD_M

    proportional_waist = 110 / STANDARD_M.bust * STANDARD_M.waist
    hourglass = Measurements(bust=110, waist=proportional_waist, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None,
                               front_zip=True)
    result = pipeline.generate_from_selection(spec, hourglass)

    front_parts = [p for p in result.finalized_parts if p.part_type == "front_bodice_zip_panel"]
    assert len(front_parts) == 2
    for p in front_parts:
        assert p.dart_count == 1  # パネル1枚あたり脇ダーツ1本(外側の脇線のみ)


def test_front_zip_panel_gets_both_bust_and_waist_darts_for_an_hourglass(tmp_path):
    """round11の回帰テスト: くびれの強い体型では、前開きパネルにも
    脇ダーツとウエストダーツの両方が入る(round10までウエストダーツは
    このpart_typeに一切入らなかった)。
    """
    hourglass = Measurements(bust=110, waist=60, hip=92, height=160,
                              sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None,
                               front_zip=True)
    result = pipeline.generate_from_selection(spec, hourglass)

    front_parts = [p for p in result.finalized_parts if p.part_type == "front_bodice_zip_panel"]
    assert len(front_parts) == 2
    for p in front_parts:
        # 脇ダーツ1本 + ウエストダーツ1本以上
        assert p.dart_count >= 2

    back_darts = sum(p.dart_count for p in result.finalized_parts
                      if p.part_type == "back_bodice")
    assert back_darts > 0


def test_front_zip_panel_gets_no_dart_when_bust_is_not_excessive(tmp_path):
    standard = Measurements(bust=84, waist=68, hip=92, height=160,
                             sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None,
                               front_zip=True)
    result = pipeline.generate_from_selection(spec, standard)

    front_darts = sum(p.dart_count for p in result.finalized_parts
                       if p.part_type == "front_bodice_zip_panel")
    assert front_darts == 0


@pytest.mark.parametrize("neckline", ["round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart"])
def test_front_bodice_zip_panel_is_valid_across_full_measurement_range(neckline):
    shapely = pytest.importorskip("shapely.geometry")
    Polygon = shapely.Polygon

    from engine.measurements import _VALID_RANGES
    from engine.scaling import scale_template
    from engine.templates_db import TemplateDB
    from engine.svgpath import segments_to_polyline

    db = TemplateDB()
    segments = db.get("front_bodice_zip_panel", neckline)
    bust_lo, bust_hi = _VALID_RANGES["bust"]
    height_lo, height_hi = _VALID_RANGES["height"]

    checked = 0
    bust = bust_lo
    while bust <= bust_hi:
        height = height_lo
        while height <= height_hi:
            m = Measurements(bust=bust, waist=68, hip=92, height=height,
                              sleeve_length=54, shoulder_width=37)
            scaled = scale_template("front_bodice_zip_panel", neckline, segments, m)
            checked += 1
            poly_points = segments_to_polyline(scaled.segments)
            closed = poly_points[:-1] if poly_points[0] == poly_points[-1] else poly_points
            assert Polygon(closed).is_valid, f"invalid polygon at bust={bust}, height={height}"
            height += 25
        bust += 25
    assert checked > 0


@pytest.mark.parametrize("sleeve_style", ["straight", "curve", "puff", "bell", "cap", "three_quarter"])
def test_generate_from_selection_supports_every_sleeve_style(tmp_path, sleeve_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=sleeve_style, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    sleeve_parts = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert len(sleeve_parts) == 2


@pytest.mark.parametrize("skirt_style", ["flare", "tight", "pleated", "wrap", "mermaid", "circle"])
def test_generate_from_selection_supports_every_skirt_style(tmp_path, skirt_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=skirt_style)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    skirt_parts = [p for p in result.finalized_parts if p.part_type == "skirt"]
    assert len(skirt_parts) == 2


def test_only_tight_skirt_gets_a_waist_dart_for_pear_shaped_measurements(tmp_path):
    # ヒップに対してウエストが標準より細い体型(いわゆる「洋なし型」)。
    # skirt(tight)にはウエストダーツが入るが、意図的にウエストで摘まない
    # デザインのflare/pleated/wrapには入らないはず。
    pear = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for skirt_style, expect_dart in [("tight", True), ("flare", False),
                                      ("pleated", False), ("wrap", False),
                                      ("mermaid", True), ("circle", False)]:
        spec = build_garment_spec(sleeve_style=None, skirt_style=skirt_style)
        result = pipeline.generate_from_selection(spec, pear)
        skirt_parts = [p for p in result.finalized_parts if p.part_type == "skirt"]
        total_darts = sum(p.dart_count for p in skirt_parts)
        if expect_dart:
            assert total_darts > 0, f"{skirt_style}にウエストダーツが入っていない"
        else:
            assert total_darts == 0, f"{skirt_style}にウエストダーツが入るべきではない"


def test_every_pants_style_gets_a_waist_dart_for_pear_shaped_measurements(tmp_path):
    # スカートと異なり、パンツには「意図的にウエストで摘まないデザイン」は
    # 無いという設計判断のもと、全パンツバリエーションが対象になっている。
    pear = Measurements(bust=84, waist=60, hip=105, height=160, sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for pants_style in ["", "wide", "tapered", "shorts", "flare", "cropped"]:
        spec = build_garment_spec(sleeve_style=None, skirt_style=None,
                                   include_pants=True, pants_style=pants_style)
        result = pipeline.generate_from_selection(spec, pear)
        pants_parts = [p for p in result.finalized_parts
                       if p.part_type in ("front_pants", "back_pants")]
        total_darts = sum(p.dart_count for p in pants_parts)
        assert total_darts > 0, f"pants({pants_style!r})にウエストダーツが入っていない"


@pytest.mark.parametrize("collar_style", ["", "shirt_collar", "peter_pan_collar", "bow_collar",
                                           "ruffle_collar", "convertible_collar"])
def test_generate_from_selection_supports_every_collar_style(tmp_path, collar_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=None,
                               include_collar=True, collar_style=collar_style)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []


def test_build_garment_spec_rejects_unknown_collar_style():
    with pytest.raises(ValueError):
        build_garment_spec(include_collar=True, collar_style="not-a-real-style")


@pytest.mark.parametrize("cuffs_style", ["", "wide", "ruffle", "button_tab"])
def test_generate_from_selection_supports_every_cuffs_style(tmp_path, cuffs_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style="straight", skirt_style=None,
                               include_cuffs=True, cuffs_style=cuffs_style)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []


def test_build_garment_spec_rejects_unknown_cuffs_style():
    with pytest.raises(ValueError):
        build_garment_spec(sleeve_style="straight", include_cuffs=True, cuffs_style="not-a-real-style")


@pytest.mark.parametrize("pants_style", ["", "wide", "tapered", "shorts", "flare", "cropped"])
def test_generate_from_selection_supports_every_pants_style(tmp_path, pants_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=None,
                               include_pants=True, pants_style=pants_style)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []
    # round5でpantsはfront_pants/back_pantsに分離した。それぞれ左右の脚で
    # 2枚ずつ、計4枚になる。
    front_pants_parts = [p for p in result.finalized_parts if p.part_type == "front_pants"]
    back_pants_parts = [p for p in result.finalized_parts if p.part_type == "back_pants"]
    assert len(front_pants_parts) == 2
    assert len(back_pants_parts) == 2


def test_build_garment_spec_rejects_unknown_pants_style():
    with pytest.raises(ValueError):
        build_garment_spec(include_pants=True, pants_style="not-a-real-style")


@pytest.mark.parametrize("waistband_style", ["", "wide", "elastic", "contour"])
def test_generate_from_selection_supports_every_waistband_style(tmp_path, waistband_style):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(sleeve_style=None, skirt_style=None,
                               include_waistband=True, waistband_style=waistband_style)
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.nesting.unplaced == []


def test_build_garment_spec_rejects_unknown_waistband_style():
    with pytest.raises(ValueError):
        build_garment_spec(include_waistband=True, waistband_style="not-a-real-style")


def test_build_garment_spec_rejects_cuffs_without_sleeve():
    # 以前はsleeve_style=Noneのときcuffsチェックが黙って無視されており、
    # 利用者が「カフスを含める」を選んでも型紙に反映されない不具合があった。
    with pytest.raises(ValueError):
        build_garment_spec(sleeve_style=None, include_cuffs=True)


def test_build_garment_spec_allows_cuffs_with_sleeve():
    spec = build_garment_spec(sleeve_style="straight", include_cuffs=True)
    part_types = [p.part_type for p in spec.parts]
    assert "cuffs" in part_types


def test_generate_from_selection_end_to_end(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="v_neck", sleeve_style="curve", skirt_style="tight",
                               include_collar=True, include_cuffs=True, include_waistband=True)
    result = pipeline.generate_from_selection(spec, STANDARD)

    assert result.nesting.unplaced == []
    assert len(result.finalized_parts) == spec.total_pieces()
    assert result.output_files["pdf"].endswith(".pdf")
    assert result.output_files["svg"].endswith(".svg")


def test_generate_from_illustration_mock_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    image = _illustration_test_image()

    result = pipeline.generate_from_illustration(image, STANDARD)

    assert len(result.classification_log) > 0
    assert all(c.raw.get("mode") == "mock" for c in result.classification_log)
    assert result.nesting.unplaced == []


def test_generate_from_illustration_produces_front_and_back_skirt(tmp_path, monkeypatch):
    # 以前は"lower_body"領域がpart_type="skirt"のquantity=1として登録されて
    # おり、後ろスカートが生成されないまま「型紙が完成した」ことになっていた
    # (skirtはPAIR_LABELSで前/後の2枚セットが前提)。手動モードのbuild_garment_spec
    # と同様に、イラストモードでもskirtが2枚(前+後)生成されることを確認する。
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    image = _illustration_test_image()

    result = pipeline.generate_from_illustration(image, STANDARD)

    skirt_parts = [p for p in result.finalized_parts if p.part_type == "skirt"]
    assert len(skirt_parts) == 2, "skirtは前後2枚生成されるはず"
    labels = {p.label_suffix for p in skirt_parts}
    assert labels == {"前", "後"}


class _ConflictingVariationClassifier(PartClassifier):
    """左右の袖領域に、意図的に異なるvariationを返すダミー分類器。

    本物のClaude API判定は左右の袖を独立に見て判定するため、画像品質等の
    理由で異なるバリエーションを返す可能性がある。そのケースで
    「straight×2 + curve×2 = 4枚」のような余分な型紙が出ないことを確認する。
    """

    def classify(self, image, region_label: str = "") -> ClassificationResult:
        if region_label == "torso":
            return ClassificationResult(part_type="front_bodice", variation="round_neck", confidence=0.9)
        if region_label == "left_sleeve":
            return ClassificationResult(part_type="sleeve", variation="straight", confidence=0.9)
        if region_label == "right_sleeve":
            # 右袖だけ違うバリエーションと誤判定したケースを模擬する。
            return ClassificationResult(part_type="sleeve", variation="curve", confidence=0.9)
        return ClassificationResult(part_type="", variation="", confidence=0.0)


def test_summary_has_no_measurement_warnings_for_standard_measurements(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    result = pipeline.generate_from_selection(spec, STANDARD)
    assert result.summary()["measurement_warnings"] == []


def test_summary_warns_and_actually_reveals_the_silent_clamp_bug(tmp_path):
    """実際にHTTP経由で`/api/generate`にbust=160cmとbust=132.8cmを送って
    比較し、生成される型紙が完全に同一になってしまうことを確認した実バグの
    回帰テスト。

    以前はこの食い違いについて`summary()`が一切触れておらず、利用者は
    自分の入力したbust=160cmがそのまま使われたと誤解しうる状態だった。
    修正後は`measurement_warnings`にその旨の注記が入るようになった一方、
    テンプレートの変形限界(MIN_SCALE〜MAX_SCALE)自体は変えていないため、
    bust=160cmとbust=132.8cmの実際の型紙(width_cm)は今も同一になる
    ——これは意図した仕様(正確な型紙が作れない入力を弾く/警告する)であり、
    「警告さえ出せば良い」という誤った修正(実は型紙自体は直っていない)に
    後退しないよう、両方をこのテストで明示的に確認する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")

    m_requested = Measurements(bust=160, waist=68, hip=92, height=160,
                                sleeve_length=54, shoulder_width=37)
    m_effective = Measurements(bust=83 * 1.6, waist=68, hip=92, height=160,
                                sleeve_length=54, shoulder_width=37)

    result_requested = pipeline.generate_from_selection(spec, m_requested)
    result_effective = pipeline.generate_from_selection(spec, m_effective)

    # 警告が出ていること(利用者への開示)。
    summary_requested = result_requested.summary()
    assert any("バスト" in w for w in summary_requested["measurement_warnings"])
    assert result_effective.summary()["measurement_warnings"] == []  # 132.8cmはクランプ範囲の境界内

    # 実際の型紙の寸法が今も同一であること(=これは正しい挙動。テンプレート
    # 自体を160cm相当に対応させたわけではなく、正直に開示しているだけ)。
    front_requested = next(p for p in result_requested.finalized_parts if p.part_type == "front_bodice")
    front_effective = next(p for p in result_effective.finalized_parts if p.part_type == "front_bodice")
    assert front_requested.width_cm == pytest.approx(front_effective.width_cm)


def test_summary_naive_baseline_is_never_better_than_actual_nesting(tmp_path):
    # naive_used_length_cm は「詰めずに縦積みしただけ」の参考値なので、
    # 実際のネスティング結果(used_length_cm)以上になるはず
    # (詰め合わせによって短くなる、もしくは同じになる)。
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="v_neck", sleeve_style="curve", skirt_style="tight",
                               include_collar=True, include_cuffs=True, include_waistband=True)
    result = pipeline.generate_from_selection(spec, STANDARD)
    summary = result.summary()

    assert summary["naive_used_length_cm"] >= summary["used_length_cm"] - 1e-6
    assert summary["naive_waste_ratio"] >= summary["waste_ratio"] - 1e-6


def test_summary_parts_list_matches_finalized_parts(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    result = pipeline.generate_from_selection(spec, STANDARD)
    summary = result.summary()

    assert len(summary["parts"]) == len(result.finalized_parts)
    for entry, part in zip(summary["parts"], result.finalized_parts):
        assert entry["display_name"] == part.display_name
        assert entry["width_cm"] == round(part.width_cm, 1)
        assert entry["height_cm"] == round(part.height_cm, 1)


def test_conflicting_sleeve_variations_do_not_produce_four_sleeves(tmp_path, monkeypatch):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    image = _illustration_test_image()

    import engine.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "get_default_classifier", lambda: _ConflictingVariationClassifier())
    result = pipeline.generate_from_illustration(image, STANDARD)

    sleeve_count = sum(1 for p in result.finalized_parts if p.part_type == "sleeve")
    assert sleeve_count == 2, (
        "左右で違うvariationが判定されても、袖は2枚(1対)にまとまるべき: "
        f"got {sleeve_count}"
    )


# --- round5: 縫い代を辺ごとに設定可能に(hem_seam_allowance_cm) -----------------


def test_generate_from_selection_default_seam_allowance_is_uniform(tmp_path):
    # hem_seam_allowance_cmを指定しなければ、従来通り全パーツ・全辺
    # 1.0cm(DEFAULT_SEAM_ALLOWANCE_CM)一律のはず。
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD)

    assert result.seam_allowance_cm == 1.0
    assert result.hem_seam_allowance_cm is None
    summary = result.summary()
    assert summary["seam_allowance_cm"] == 1.0
    assert summary["hem_seam_allowance_cm"] is None


def test_generate_from_selection_hem_seam_allowance_actually_widens_the_hem(tmp_path):
    # round5の目玉機能: hem_seam_allowance_cmを指定すると、実際に各パーツの
    # 裾側だけcut_line(裁断線)が広がること(=見た目のダミーパラメータでは
    # なく実際にジオメトリへ反映されること)を、パイプライン経由で確認する。
    # front_bodiceは「裾(y最大)」が実際に衣服の裾に対応するパーツなので、
    # これを比較対象に使う。
    pipeline_uniform = PatternForgePipeline(output_dir=str(tmp_path / "uniform"))
    pipeline_hem = PatternForgePipeline(output_dir=str(tmp_path / "hem"))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)

    uniform = pipeline_uniform.generate_from_selection(spec, STANDARD, seam_allowance_cm=1.0)
    hemmed = pipeline_hem.generate_from_selection(
        spec, STANDARD, seam_allowance_cm=1.0, hem_seam_allowance_cm=3.0,
    )

    uniform_front = next(p for p in uniform.finalized_parts if p.part_type == "front_bodice")
    hemmed_front = next(p for p in hemmed.finalized_parts if p.part_type == "front_bodice")
    assert hemmed_front.height_cm > uniform_front.height_cm

    assert hemmed.seam_allowance_cm == 1.0
    assert hemmed.hem_seam_allowance_cm == 3.0
    assert hemmed.summary()["hem_seam_allowance_cm"] == 3.0
    # 全パーツについて、cut_lineが有効な(自己交差しない)単純多角形のままであること。
    for part in hemmed.finalized_parts:
        assert _is_simple_polygon(part.cut_line)


def test_generate_from_selection_per_call_seam_allowance_overrides_instance_default(tmp_path):
    # インスタンス生成時の既定値(seam_allowance_cm)を変えずに、1回の呼び出し
    # だけ違う縫い代を使えること(engine/pipeline.pyのeffective_seam_cm/
    # effective_hem_cmの解決ロジック)を確認する。
    pipeline = PatternForgePipeline(output_dir=str(tmp_path), seam_allowance_cm=1.0)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style=None)

    default_result = pipeline.generate_from_selection(spec, STANDARD)
    overridden_result = pipeline.generate_from_selection(spec, STANDARD, seam_allowance_cm=2.0)

    assert default_result.seam_allowance_cm == 1.0
    assert overridden_result.seam_allowance_cm == 2.0
    assert pipeline.seam_allowance_cm == 1.0  # インスタンス既定値自体は変わらない


def _is_simple_polygon(points) -> bool:
    try:
        from shapely.geometry import Polygon
    except Exception:  # pragma: no cover - shapely未導入環境では検証をスキップ
        return True
    pts = points[:-1] if points and points[0] == points[-1] else points
    return Polygon(pts).is_valid
