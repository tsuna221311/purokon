import os
import zipfile

import pytest

from engine.measurements import (
    Measurements,
    STANDARD_SIZE_GRADE_CM,
    STANDARD_SIZE_ORDER,
    STANDARD_SIZE_STEPS,
    detect_dart_count_inconsistencies,
    graded_measurements,
    grading_relative_change_notes,
    validate_custom_grade_cm,
)
from engine.pipeline import PatternForgePipeline, build_garment_spec

BASE = Measurements(bust=84, waist=68, hip=92, height=160, sleeve_length=54, shoulder_width=37)


# --- engine.measurements.graded_measurements ---------------------------------


def test_graded_measurements_for_m_returns_the_base_unchanged():
    graded = graded_measurements(BASE, "M")
    assert graded == BASE


def test_graded_measurements_l_is_larger_than_base_by_the_documented_grade():
    graded = graded_measurements(BASE, "L")
    assert graded.bust == BASE.bust + STANDARD_SIZE_GRADE_CM["bust"]
    assert graded.waist == BASE.waist + STANDARD_SIZE_GRADE_CM["waist"]
    assert graded.hip == BASE.hip + STANDARD_SIZE_GRADE_CM["hip"]
    assert graded.shoulder_width == BASE.shoulder_width + STANDARD_SIZE_GRADE_CM["shoulder_width"]
    assert graded.sleeve_length == BASE.sleeve_length + STANDARD_SIZE_GRADE_CM["sleeve_length"]
    assert graded.height == BASE.height  # 身長は号数で変えない設計


def test_graded_measurements_s_is_smaller_than_base_by_the_documented_grade():
    graded = graded_measurements(BASE, "S")
    assert graded.bust == BASE.bust - STANDARD_SIZE_GRADE_CM["bust"]
    assert graded.waist == BASE.waist - STANDARD_SIZE_GRADE_CM["waist"]
    assert graded.hip == BASE.hip - STANDARD_SIZE_GRADE_CM["hip"]


def test_graded_measurements_sizes_are_monotonically_increasing():
    # XS < S < M < L < XL の順で、各部位が単調に大きくなる(身長を除く)はず。
    graded_by_size = {size: graded_measurements(BASE, size) for size in STANDARD_SIZE_ORDER}
    ordered = [graded_by_size[size] for size in STANDARD_SIZE_ORDER]
    for field in ("bust", "waist", "hip", "sleeve_length", "shoulder_width"):
        values = [getattr(m, field) for m in ordered]
        assert values == sorted(values)
        assert len(set(values)) == len(values)  # 全サイズで値が異なる(重複しない)


def test_graded_measurements_rejects_unknown_size():
    with pytest.raises(ValueError):
        graded_measurements(BASE, "XXL")


def test_graded_measurements_can_raise_when_grading_pushes_out_of_valid_range():
    # 極端に大きい基準値からさらにXLへ4段階分グレーディングすると、
    # Measurements自体の入力検証(_VALID_RANGES)に引っかかりうる。
    # これは「グレーディングルールのバグ」ではなく、Measurements側の
    # 正直な現実的範囲チェックがそのまま働いている、という正しい挙動。
    near_max_bust = Measurements(bust=155.0, waist=68, hip=92, height=160,
                                  sleeve_length=54, shoulder_width=37)
    with pytest.raises(ValueError):
        graded_measurements(near_max_bust, "XL")  # bust=155+8=163 > 160(上限)


def test_standard_size_steps_cover_exactly_the_documented_five_sizes():
    assert set(STANDARD_SIZE_STEPS) == {"XS", "S", "M", "L", "XL"}
    assert STANDARD_SIZE_STEPS["M"] == 0
    assert tuple(sorted(STANDARD_SIZE_STEPS, key=STANDARD_SIZE_STEPS.get)) == STANDARD_SIZE_ORDER


# --- engine.pipeline.PatternForgePipeline.generate_multi_size ----------------


def test_generate_multi_size_produces_one_result_per_requested_size(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M", "L"])

    assert multi.sizes == ["S", "M", "L"]
    assert set(multi.results.keys()) == {"S", "M", "L"}
    for size, result in multi.results.items():
        assert result.nesting.unplaced == []
        assert result.measurements == graded_measurements(BASE, size)
        # 各サイズは完全に独立したjob_idを持つ(=単体でも/download/<job_id>/<fmt>で取れる)
        assert result.job_id
    job_ids = [r.job_id for r in multi.results.values()]
    assert len(set(job_ids)) == 3  # 3サイズとも別々のjob_id


def test_generate_multi_size_writes_a_zip_containing_every_size_and_format(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M", "L"])

    assert os.path.isfile(multi.zip_path)
    with zipfile.ZipFile(multi.zip_path) as zf:
        names = set(zf.namelist())
    for size in ("S", "M", "L"):
        for ext in ("svg", "pdf", "dxf"):
            assert f"{size}/{size}.{ext}" in names


def test_generate_multi_size_rejects_empty_size_list(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    with pytest.raises(ValueError):
        pipeline.generate_multi_size(spec, BASE, [])


def test_generate_multi_size_rejects_unknown_size_name(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    with pytest.raises(ValueError):
        pipeline.generate_multi_size(spec, BASE, ["M", "XXL"])


def test_generate_multi_size_summary_includes_every_size_and_base_measurements(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M"])
    summary = multi.summary()

    assert summary["bundle_job_id"] == multi.bundle_job_id
    assert summary["sizes"] == ["S", "M"]
    assert summary["base_measurements"] == BASE.as_dict()
    assert set(summary["results"].keys()) == {"S", "M"}
    assert summary["results"]["S"]["job_id"] == multi.results["S"].job_id


def test_generate_multi_size_single_size_still_works(tmp_path):
    # 単一サイズだけの「一括生成」も禁止しない(利用者がとりあえず1サイズだけ
    # まとめてダウンロードしたい場合もあるため)。
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    multi = pipeline.generate_multi_size(spec, BASE, ["M"])
    assert multi.sizes == ["M"]
    assert multi.results["M"].measurements == BASE


# --- engine.measurements.detect_dart_count_inconsistencies (round6) ---------


def test_detect_dart_count_inconsistencies_flags_a_valley():
    # Lサイズだけダーツ本数が両隣より少ない(谷)、実際に観測されたパターン。
    counts = {"XS": 6, "S": 6, "M": 6, "L": 0, "XL": 2}
    messages = detect_dart_count_inconsistencies(counts)
    assert len(messages) == 1
    assert "L" in messages[0]


def test_detect_dart_count_inconsistencies_flags_a_peak():
    counts = {"XS": 0, "S": 4, "M": 0, "L": 0, "XL": 0}
    messages = detect_dart_count_inconsistencies(counts)
    assert len(messages) == 1
    assert "S" in messages[0]


def test_detect_dart_count_inconsistencies_silent_for_monotonic_sequence():
    counts = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}
    assert detect_dart_count_inconsistencies(counts) == []


def test_detect_dart_count_inconsistencies_silent_for_flat_sequence():
    counts = {"XS": 2, "S": 2, "M": 2, "L": 2, "XL": 2}
    assert detect_dart_count_inconsistencies(counts) == []


def test_detect_dart_count_inconsistencies_needs_at_least_three_sizes():
    assert detect_dart_count_inconsistencies({"S": 0, "M": 4}) == []
    assert detect_dart_count_inconsistencies({}) == []


def test_detect_dart_count_inconsistencies_ignores_dict_key_order():
    # 辞書の挿入順ではなく、STANDARD_SIZE_ORDERの順序で谷/山を判定する。
    counts = {"L": 0, "XS": 6, "XL": 2, "S": 6, "M": 6}
    messages = detect_dart_count_inconsistencies(counts)
    assert len(messages) == 1
    assert "L" in messages[0]


def test_generate_multi_size_result_exposes_size_consistency_warnings(tmp_path):
    # 実際に不整合が起きることを確認済みの体型(本モジュールdocstring参照)。
    base = Measurements(bust=70, waist=50, hip=70, height=160, sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None, skirt_style="tight")
    multi = pipeline.generate_multi_size(spec, base, list(STANDARD_SIZE_ORDER))
    warnings = multi.size_consistency_warnings()
    assert isinstance(warnings, list)
    summary = multi.summary()
    assert summary["size_consistency_warnings"] == warnings


def test_generate_multi_size_no_consistency_warnings_for_plain_monotonic_case(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    multi = pipeline.generate_multi_size(spec, BASE, list(STANDARD_SIZE_ORDER))
    assert multi.size_consistency_warnings() == []


# --- engine.measurements.grading_relative_change_notes (round6) ------------


def test_grading_relative_change_notes_fires_for_a_small_boned_base():
    # ウエスト45cmの小柄な体型では、XSの-8cmが-17.8%という大きな相対変化になる。
    small = Measurements(bust=60, waist=45, hip=65, height=160, sleeve_length=54, shoulder_width=37)
    notes = grading_relative_change_notes(small, ["XS", "M", "XL"])
    assert any("XS" in n and "ウエスト" in n for n in notes)
    assert any("XL" in n and "ウエスト" in n for n in notes)


def test_grading_relative_change_notes_silent_for_a_large_boned_base():
    # バスト120cmの体型では、同じ8cmの変化が相対的に小さい(6〜8%程度)。
    large = Measurements(bust=120, waist=100, hip=125, height=160, sleeve_length=54, shoulder_width=37)
    notes = grading_relative_change_notes(large, ["XS", "XL"])
    assert notes == []


def test_grading_relative_change_notes_ignores_m_and_unrequested_sizes():
    base = Measurements(bust=60, waist=45, hip=65, height=160, sleeve_length=54, shoulder_width=37)
    notes = grading_relative_change_notes(base, ["M"])
    assert notes == []


def test_grading_relative_change_notes_deduplicates_per_size_and_field():
    base = Measurements(bust=60, waist=45, hip=65, height=160, sleeve_length=54, shoulder_width=37)
    notes = grading_relative_change_notes(base, ["XS"])
    waist_notes = [n for n in notes if "ウエスト" in n]
    assert len(waist_notes) == 1


def test_generate_multi_size_exposes_grading_precision_notes(tmp_path):
    # waist=50なら、XSの-8cmで42cm(有効範囲40〜150cm内)に収まりつつ、
    # 相対変化率-16.0%で閾値(15%)を超える。
    small = Measurements(bust=65, waist=50, hip=70, height=160, sleeve_length=54, shoulder_width=37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    multi = pipeline.generate_multi_size(spec, small, list(STANDARD_SIZE_ORDER))
    notes = multi.grading_precision_notes()
    assert notes
    assert multi.summary()["grading_precision_notes"] == notes


# --- round7: カスタムグレーディングルール対応 -------------------------------
#
# round6の調査で「本物のグレーディングルールはブランド・アイテムごとの
# ノウハウであり、根拠のある既定値の改善は見送った」という結論だったため、
# round7では代わりに、自社の実際のルールを知っている利用者がそれを
# そのまま入力できるようにした(engine.measurements.validate_custom_grade_cm/
# graded_measurements(grade_cm=...)参照)。

def test_validate_custom_grade_cm_accepts_partial_override():
    validated = validate_custom_grade_cm({"bust": 5.0, "waist": 3.0})
    assert validated == {"bust": 5.0, "waist": 3.0}


def test_validate_custom_grade_cm_rejects_unknown_field():
    with pytest.raises(ValueError):
        validate_custom_grade_cm({"neck": 2.0})


def test_validate_custom_grade_cm_rejects_out_of_range_value():
    # 刻み幅(号数1段階あたりの増減量)の欄に、採寸値そのもの(例: 83cm)を
    # 誤って入力してしまうような単位違いを弾く。
    with pytest.raises(ValueError):
        validate_custom_grade_cm({"bust": 83.0})


def test_validate_custom_grade_cm_rejects_non_numeric_value():
    with pytest.raises(TypeError):
        validate_custom_grade_cm({"bust": "5.0"})


def test_validate_custom_grade_cm_rejects_bool_value():
    # bool は int のサブクラスなので、isinstance(value, (int, float)) だけでは
    # Trueが5.0のように扱われてすり抜けてしまう。明示的に除外する。
    with pytest.raises(TypeError):
        validate_custom_grade_cm({"bust": True})


def test_graded_measurements_with_custom_grade_cm_overrides_only_specified_fields():
    custom = validate_custom_grade_cm({"bust": 6.0})
    graded = graded_measurements(BASE, "L", grade_cm=custom)
    assert graded.bust == BASE.bust + 6.0  # 上書きした項目
    # 指定しなかった項目は既定値のまま。
    assert graded.waist == BASE.waist + STANDARD_SIZE_GRADE_CM["waist"]
    assert graded.hip == BASE.hip + STANDARD_SIZE_GRADE_CM["hip"]


def test_graded_measurements_without_custom_grade_cm_matches_default_behavior():
    assert graded_measurements(BASE, "L", grade_cm=None) == graded_measurements(BASE, "L")
    assert graded_measurements(BASE, "L", grade_cm={}) == graded_measurements(BASE, "L")


def test_grading_relative_change_notes_reflects_custom_grade_cm():
    # 既定のwaist刻み(4.0cm)ではbase.waist=68の変化率が閾値未満だが、
    # カスタムで20cmに設定すると閾値(15%)を超えて開示されるはず。
    without_custom = grading_relative_change_notes(BASE, ["L"])
    assert not any("ウエスト" in n for n in without_custom)

    custom = validate_custom_grade_cm({"waist": 20.0})
    with_custom = grading_relative_change_notes(BASE, ["L"], grade_cm=custom)
    assert any("ウエスト" in n for n in with_custom)


def test_generate_multi_size_with_custom_grade_cm_uses_it_for_every_size(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    custom = {"bust": 6.0, "waist": 5.0, "hip": 5.0}

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M", "L"], custom_grade_cm=custom)

    assert multi.custom_grade_cm == custom
    for size in ("S", "M", "L"):
        expected = graded_measurements(BASE, size, grade_cm=custom)
        assert multi.results[size].measurements == expected
    # Lサイズのbustは、既定の4.0cmではなくカスタムの6.0cm分だけ増えているはず。
    assert multi.results["L"].measurements.bust == BASE.bust + 6.0


def test_generate_multi_size_custom_grade_cm_summary_reports_effective_grade(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    custom = {"bust": 6.0}

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M", "L"], custom_grade_cm=custom)
    summary = multi.summary()

    assert summary["custom_grade_cm_applied"] is True
    assert summary["grade_cm_used"]["bust"] == 6.0
    # 上書きしなかった項目は既定値のまま報告される。
    assert summary["grade_cm_used"]["waist"] == STANDARD_SIZE_GRADE_CM["waist"]


def test_generate_multi_size_without_custom_grade_cm_reports_all_defaults(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")

    multi = pipeline.generate_multi_size(spec, BASE, ["S", "M", "L"])
    summary = multi.summary()

    assert summary["custom_grade_cm_applied"] is False
    assert summary["grade_cm_used"] == STANDARD_SIZE_GRADE_CM


def test_generate_multi_size_rejects_invalid_custom_grade_cm(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare")
    with pytest.raises(ValueError):
        pipeline.generate_multi_size(spec, BASE, ["S", "M"], custom_grade_cm={"bust": 999.0})
