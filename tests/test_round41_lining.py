"""round41: 裏地の型紙(engine/lining.py)。

【round40まで何が足りなかったか】この製品は表地の型紙しか出さなかった。
裏地を付ける服——ジャケット・コート・スカート——を作ろうとすると、
利用者は裏地の型紙を自分で引くことになる。しかも`engine/assembly.py`は
「裏地の付け方はこのエンジンが情報を持っていない」と明記していたので、
縫う順番にも一言も出ていなかった。

【このテストが見張っていること】
裏地について**資料が数字で書いていること**だけが型紙に載り、それが
そのとおりの寸法になっていること:

  * 裾の縫い代が表地ちょうど2.0cm少ないこと(うさこの洋裁工房)
  * 後ろ身頃の裏だけ、背中心がちょうど2.0cm広がっていること
    (かたやまゆうこ/MAISON DE AS の「きせ1cm＝布2cm」)
  * 出来上がり線(縫い線)がそれ以外の場所で1mmも動いていないこと
  * 衿・カフス・ウエストバンドには裏地を引かないこと

そして**資料に無いことは載っていない**ことも見張る(肩・袖ぐり・脇の
ゆとりを勝手に足していないこと)。ここが崩れると、根拠のない寸法が
黙って型紙に入る。
"""

import pytest

from shapely.geometry import Polygon

from engine.lining import (CB_PLEAT_DEPTH_CM, CB_PLEAT_FABRIC_CM,
                            CB_PLEAT_PART_TYPES, LINED_PART_TYPES,
                            LINING_HEM_REDUCTION_CM, build_lining_parts,
                            lining_hem_allowance_cm, lining_kind, lining_notes,
                            lining_part, reference_lining_length_cm,
                            spread_at_center, yardage_reference_note)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

STANDARD = Measurements(84, 68, 92, 160, 54, 37)
#: 縫い線どうしの比較なので、0.005cm(50ミクロン)まで一致を求める。
#: 裁断線はshapelyのバッファの円弧近似で数十ミクロン動くため、
#: 裁断線を比べるテストだけは別の許容を使う。
TOL = 0.005


@pytest.fixture(scope="module")
def lined(tmp_path_factory):
    pipeline = PatternForgePipeline(
        output_dir=str(tmp_path_factory.mktemp("lining")))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare", include_collar=True,
                              include_cuffs=True)
    return pipeline.generate_from_selection(
        spec, STANDARD, hem_seam_allowance_cm=3.0, lining=True,
        skip_export=True)


def _by_type(parts):
    out = {}
    for part in parts:
        out.setdefault(part.part_type, []).append(part)
    return out


def _width(points):
    xs = [p[0] for p in points]
    return max(xs) - min(xs)


def _height(points):
    ys = [p[1] for p in points]
    return max(ys) - min(ys)


# --- 裾の縫い代: うさこの洋裁工房の実例をそのまま再現する ------------------

@pytest.mark.parametrize("outer_cm, expected_cm", [
    # 記事が挙げている3つの実例そのもの。
    (4.0, 2.0),
    (3.0, 1.0),
    (2.0, 0.0),
    # 2cmを下回る表地。負の縫い代は存在しないので0で止まる。
    (1.0, 0.0),
    (0.0, 0.0),
])
def test_lining_hem_allowance_reproduces_the_worked_examples_in_the_source(
        outer_cm, expected_cm):
    assert lining_hem_allowance_cm(outer_cm) == pytest.approx(expected_cm)


def test_the_hem_reduction_is_the_two_centimetres_the_source_states():
    assert LINING_HEM_REDUCTION_CM == 2.0


def test_every_lining_piece_is_exactly_two_centimetres_shorter_at_the_hem(lined):
    """裾の縫い代が2cm減った分だけ、裁断線の丈が2cm縮んでいること。

    「だいたい短い」では意味が無い。裏地が表から見えるかどうかは、
    この2cmがそのとおり出ているかで決まる。
    """
    outer = _by_type(lined.finalized_parts)
    for part in lined.lining_parts:
        counterpart = outer[part.part_type][0]
        delta = _height(part.cut_line) - _height(counterpart.cut_line)
        assert delta == pytest.approx(-LINING_HEM_REDUCTION_CM, abs=0.01), (
            f"{part.part_type}: 裾が{-delta:.3f}cmしか短くなっていない")


# --- 出来上がり線: 背中心のきせ以外はまったく動かさない --------------------

def test_the_lining_finished_line_is_identical_except_at_the_centre_back(lined):
    """縫い線は、背中心のきせを入れるパーツ以外では1mmも動かない。

    資料は「ゆとりを入れる」と書くが、肩・袖ぐり・脇で何cm足すのかを
    数字で書いた資料が見つからなかった。だから足さない——このテストは
    「あとから思いつきでゆとりを足す」ことを防ぐための歯止めである。
    足すなら、まず出典を持ってくること。
    """
    outer = _by_type(lined.finalized_parts)
    checked = 0
    for part in lined.lining_parts:
        if part.part_type in CB_PLEAT_PART_TYPES:
            continue
        counterpart = outer[part.part_type][0]
        assert part.stitch_line == counterpart.stitch_line, (
            f"{part.part_type}: 縫い線が変わっている")
        checked += 1
    assert checked >= 3, "比較したパーツが少なすぎる(構成を確認)"


def test_the_back_bodice_lining_is_wider_by_exactly_the_pleat_fabric(lined):
    """後ろ身頃の裏だけ、背中心がちょうど2.0cm広い。

    深さ1cmの折り山は布を2cm食う(かたやまゆうこ「1cmのきせ分、布の長さで
    いうと2cm」)。たたむと表地と同じ幅に戻るので、広がりは**ちょうど**
    2cmでなければならない——多ければ裏地が余り、少なければつっぱる。
    """
    outer = _by_type(lined.finalized_parts)
    back = next(p for p in lined.lining_parts
                if p.part_type in CB_PLEAT_PART_TYPES)
    counterpart = outer[back.part_type][0]
    delta = _width(back.stitch_line) - _width(counterpart.stitch_line)
    assert delta == pytest.approx(CB_PLEAT_FABRIC_CM, abs=TOL)
    assert CB_PLEAT_FABRIC_CM == pytest.approx(CB_PLEAT_DEPTH_CM * 2)
    # 丈は変わらない(きせは横に広げるだけ)。裾の縫い代の分だけは縮む。
    assert _height(back.stitch_line) == pytest.approx(
        _height(counterpart.stitch_line), abs=TOL)


def test_the_added_centre_back_area_is_a_clean_two_centimetre_strip(lined):
    """広げた分の面積が「2cm × 背中心の長さ」ちょうどであること。

    幅だけ見ていると、輪郭が斜めにずれても2.0cmに見えることがある。
    面積で見れば、切り開いた隙間が縦にまっすぐな帯になっているかが分かる。
    """
    outer = _by_type(lined.finalized_parts)
    back = next(p for p in lined.lining_parts
                if p.part_type in CB_PLEAT_PART_TYPES)
    counterpart = outer[back.part_type][0]
    lining_poly = Polygon(back.stitch_line)
    outer_poly = Polygon(counterpart.stitch_line)
    assert lining_poly.is_valid, "きせを入れた輪郭が自己交差している"
    added = lining_poly.area - outer_poly.area
    cb_length = added / CB_PLEAT_FABRIC_CM
    # 背中心の長さは、襟ぐりの底から裾まで。身頃の丈より短く、その6割以上。
    height = _height(counterpart.stitch_line)
    assert 0.6 * height < cb_length < height


def test_the_lining_notches_sit_where_the_outer_notches_do(lined):
    """合印が表地とまったく同じ位置にあること。

    裏地は表地と同じ縫い目を縫うので、合印がずれていたら合わせる目印に
    ならない。`finalize_part`は合印を打ち直すが、`notch_points`
    (engine/notches.pyが決めた実座標)を渡せない呼び出しでは**周長比**へ
    フォールバックする(round16の設計)。裏地を周長比で打ち直すと、表地が
    実座標で打った位置と別の場所に出る——だから打ち直さず引き継ぐ。

    背中心を広げた後ろ身頃だけは、合印も載っている側へ一緒に動く
    (ちょうど±1cm。ひだをたたむと表地と重なる)。
    """
    outer = _by_type(lined.finalized_parts)
    for part in lined.lining_parts:
        counterpart = outer[part.part_type][0]
        assert len(part.notches) == len(counterpart.notches), part.part_type
        if part.part_type in CB_PLEAT_PART_TYPES:
            shifts = {round(a[0] - c[0], 6)
                      for (a, _), (c, _) in zip(part.notches, counterpart.notches)}
            assert shifts <= {-1.0, 1.0}, f"{part.part_type}: ずれ={shifts}"
            assert all(a[1] == c[1]
                       for (a, _), (c, _) in zip(part.notches, counterpart.notches))
        else:
            assert part.notches == counterpart.notches, part.part_type


def test_the_lining_cut_line_stays_a_valid_simple_polygon(lined):
    """裁断線が有効な単純多角形であること(自己交差した型紙は裁てない)。"""
    for part in lined.lining_parts:
        assert Polygon(part.cut_line).is_valid, f"{part.part_type}の裁断線が無効"


# --- どのパーツに裏地を引くか ---------------------------------------------

def test_interfaced_parts_do_not_get_a_lining(lined):
    """衿・カフス・ウエストバンドには裏地を引かない。

    これらは「裏地を付ける」部位ではなく、接着芯を貼って表布で二重にする
    部位である(engine/cutting.pyのneeds_interfacingが芯地側で面倒を見る)。
    裏地の型紙まで出すと、要らない紙が増えるだけでなく、裏地の必要量にも
    その分が入って**多く買わされる**。
    """
    lining_types = {p.part_type for p in lined.lining_parts}
    assert "collar" not in lining_types
    assert "cuffs" not in lining_types
    # 生成した表地側には確かに衿とカフスがある(=テストが空振りしていない)。
    outer_types = {p.part_type for p in lined.finalized_parts}
    assert {"collar", "cuffs"} <= outer_types


def test_every_lined_part_type_produces_exactly_one_lining_piece(lined):
    outer_lined = [p for p in lined.finalized_parts
                   if p.part_type in LINED_PART_TYPES]
    assert len(lined.lining_parts) == len(outer_lined)
    for part in lined.lining_parts:
        assert part.label_suffix.endswith("裏"), part.label_suffix


def test_a_part_type_with_no_lining_returns_none():
    class _Fake:
        part_type = "collar"
        variation = "stand"
        stitch_line = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        seam_allowance_cm = 1.0
    assert lining_part(_Fake()) is None


def test_build_lining_parts_on_an_empty_list_is_empty():
    assert build_lining_parts([]) == []


# --- 切り開いて広げる操作そのもの ------------------------------------------

def test_spread_at_centre_widens_a_rectangle_by_exactly_twice_the_half():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    out = spread_at_center(square, 5.0, 1.0)
    assert _width(out) == pytest.approx(12.0)
    assert _height(out) == pytest.approx(10.0)
    assert Polygon(out).area == pytest.approx(120.0)


def test_spread_at_centre_splits_edges_that_cross_the_line():
    """中心線をまたぐ斜めの辺は、交点で切ってから左右に離される。

    三角形の頂点(5, 10)は中心線の**上**にあるので、2点に割れて
    上辺が水平な2cmの隙間になる。切らずに片側へ寄せると、この隙間が
    斜めになり、たたんだときに折り山が中心からずれる。
    """
    triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0), (0.0, 0.0)]
    out = spread_at_center(triangle, 5.0, 1.0)
    poly = Polygon(out)
    assert poly.is_valid
    assert _width(out) == pytest.approx(12.0)
    # 元の面積(50) + 高さ10・幅2の帯(20)
    assert poly.area == pytest.approx(70.0, abs=1e-6)
    tops = sorted(p[0] for p in out if p[1] == pytest.approx(10.0))
    assert tops == pytest.approx([4.0, 6.0])


def test_spread_at_centre_does_nothing_for_a_zero_width():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    assert spread_at_center(square, 5.0, 0.0) == square


# --- 必要量の目安(旭化成) --------------------------------------------------

def test_the_reference_formulas_reproduce_the_source_arithmetic():
    # パンツ総裏: (パンツ丈×2)+10cm
    assert reference_lining_length_cm("pants", length_cm=95) == (200, 200)
    # ジャケット総裏: (着丈×2)+(袖丈×2)+20cm
    assert reference_lining_length_cm(
        "jacket", length_cm=60, sleeve_cm=55) == (250, 250)
    # スカート: (スカート丈+10)×2〜3、幅が広い型は×3〜4 → 下限2・上限4
    assert reference_lining_length_cm("skirt", length_cm=60) == (140, 280)


def test_an_unknown_kind_returns_none_instead_of_a_made_up_number():
    assert reference_lining_length_cm("cape", length_cm=100) is None
    # ワンピースの式は背丈を要求する。このエンジンは背丈を採寸していないので
    # 実装しない(着丈で代用すると、式の意味が変わる)。
    assert reference_lining_length_cm("dress", length_cm=100) is None


def test_a_top_and_bottom_combination_has_no_formula_to_apply(lined):
    """身頃+スカートには当てはめる式が無いので、目安を出さない。

    元の資料のワンピース式は背丈を使う。身頃のパーツ丈は**着丈**であって
    背丈ではないので、代入すると別の数字になる。当てられない式は当てない。
    """
    assert lining_kind(lined.lining_parts) is None
    assert yardage_reference_note(lined.lining_parts, 180.0, 140.0) is None


def test_the_reference_note_explains_why_the_measured_length_is_shorter(
        tmp_path):
    """身頃+袖では目安を出す。実測の方が短い理由まで書いてあること。

    実測(バスト84・裾3cm)では、旭化成式264cmに対しこのエンジンは
    幅110cmで122cm——ちょうど半分になる。概算式が前後の身頃を縦に
    並べる前提だからで、理由を書かずに数字だけ並べると
    「どちらかが間違っている」と読めてしまう。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, STANDARD, hem_seam_allowance_cm=3.0, lining=True,
        skip_export=True)
    assert lining_kind(result.lining_parts) == "jacket"
    note = next(n for n in result.lining_notes if "概算" in n)
    assert "実測" in note and "横に並べている" in note
    assert "asahi-kasei" in note


def test_the_note_warns_when_the_measured_length_exceeds_the_rule_of_thumb(
        lined):
    """実測が目安を上回るときだけ「目安で買うと足りない」と言う。

    この向きの食い違いは、目安を信じて買った人が布を足りなくする。
    逆向き(実測の方が短い)は損をしないので、警告にしない。
    """
    # 身頃+袖だけ取り出して「ジャケット」の式が当たる構成にする
    # (スカートが混ざると当てはめる式が無くなる)。
    parts = [p for p in lined.lining_parts
             if p.part_type.endswith("bodice") or p.part_type == "sleeve"]
    assert lining_kind(parts) == "jacket"
    huge = yardage_reference_note(parts, 10_000.0, 110.0)
    assert huge is not None and "足りません" in huge
    small = yardage_reference_note(parts, 1.0, 110.0)
    assert small is not None and "足りません" not in small


# --- 注記: 入れた数字と、入れなかったもの ----------------------------------

def test_the_notes_name_the_source_for_every_number_they_state(lined):
    notes = " ".join(lined.lining_notes)
    assert "yousai.net" in notes, "裾の2cmの出典が無い"
    assert "ameblo.jp/katagami-sewing" in notes, "きせの1cmの出典が無い"
    assert "maisondeas.com" in notes, "きせのもう一方の出典が無い"


def test_the_notes_disclose_what_was_deliberately_left_out(lined):
    """入れなかったもの(肩・袖ぐり・脇のゆとり)を明記していること。

    「入れていない」と書かなければ、利用者は入っていると思って縫う。
    黙って落とすのは、間違った数字を入れるのと同じくらい悪い。
    """
    notes = " ".join(lined.lining_notes)
    assert "肩・袖ぐり・脇のゆとりは足していません" in notes


def test_the_notes_disclose_the_competing_convention(lined):
    """採らなかった流儀(裏地の丈そのものを2cm短くする)を残していること。"""
    notes = " ".join(lined.lining_notes)
    assert "うさこ式" in notes and "かたやまゆうこ" in notes


def test_no_notes_when_there_is_no_lining():
    assert lining_notes([], 3.0) == []


# --- パイプライン全体 ------------------------------------------------------

def test_the_lining_is_laid_out_on_its_own_fabric(lined):
    """裏地は表地とは別に並べる。同じ生地に混ぜて数えていないこと。

    裏地は別の生地なので、表地のネスティングに混ぜると
    「幅150cmを3.5m買えば全部できる」という**作れない案内**になる。
    """
    assert lined.lining_nesting is not None
    assert lined.lining_nesting is not lined.nesting
    outer_ids = {id(p) for p in lined.nesting.placed}
    assert not (outer_ids & {id(p) for p in lined.lining_nesting.placed})
    assert len(lined.lining_nesting.placed) == len(lined.lining_parts)
    assert not lined.lining_nesting.unplaced


def test_the_shopping_list_keeps_the_lining_on_its_own_row(lined):
    memo = lined.shopping_list.as_dict()
    assert memo["lining_widths"], "裏地の必要量が買い物メモに出ていない"
    assert memo["lining_recommended_width_cm"] is not None
    widths = {w["width_cm"] for w in memo["lining_widths"]}
    assert widths == {w["width_cm"] for w in memo["widths"]}
    note = " ".join(memo["notes"])
    assert "足し合わせないでください" in note


def test_generating_without_the_lining_option_changes_nothing(tmp_path):
    """裏地を付けない生成は、round40までとまったく同じ結果になること。

    既定を変えていないことの確認。裏地のコードが表地の型紙に触れていたら
    ここで落ちる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    plain = pipeline.generate_from_selection(spec, STANDARD, skip_export=True)
    with_lining = pipeline.generate_from_selection(
        spec, STANDARD, lining=True, skip_export=True)
    assert plain.lining_parts == []
    assert plain.lining_nesting is None
    assert plain.lining_notes == []
    assert plain.summary()["lining"] is None
    for a, b in zip(plain.finalized_parts, with_lining.finalized_parts):
        assert a.cut_line == b.cut_line
        assert a.stitch_line == b.stitch_line
    assert plain.nesting.used_length_cm == pytest.approx(
        with_lining.nesting.used_length_cm)


def test_the_lining_gets_its_own_output_files(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD, lining=True)
    for key in ("lining_svg", "lining_pdf", "lining_dxf", "lining_projector"):
        assert key in result.output_files, key
        path = result.output_files[key]
        assert path.endswith(("_lining.svg", "_lining.pdf", "_lining.dxf",
                              "_lining_projector.pdf"))
        assert (tmp_path / path.rsplit("/", 1)[-1]).stat().st_size > 0
    # 表地のファイルと別物であること(上書きしていない)。
    assert result.output_files["pdf"] != result.output_files["lining_pdf"]


def test_the_summary_exposes_the_lining_for_the_screen(lined):
    payload = lined.summary()["lining"]
    assert payload["part_count"] == len(lined.lining_parts)
    assert payload["used_length_cm"] == pytest.approx(
        round(lined.lining_nesting.used_length_cm, 1))
    assert payload["unplaced_count"] == 0
    assert all("裏" in p["display_name"] for p in payload["parts"])


# --- 縫う順番 --------------------------------------------------------------

def test_the_assembly_steps_gain_the_lining_work(lined):
    titles = [s.title for s in lined.assembly_steps()]
    assert "裏地の背中心にきせをたたむ" in titles
    assert "裏地を組み立てる" in titles
    assert "裏地を身頃に合わせる" in titles
    # きせは裏地を組み立てる前。たたんでから縫わないと幅が合わない。
    assert titles.index("裏地の背中心にきせをたたむ") < titles.index("裏地を組み立てる")
    # 合わせるのは最後。
    assert titles.index("裏地を組み立てる") < titles.index("裏地を身頃に合わせる")


def test_the_hem_step_states_both_hem_allowances(lined):
    step = next(s for s in lined.assembly_steps() if s.title == "裾を始末する")
    assert "3cm" in step.detail, "表地の裾の縫い代が書かれていない"
    assert "1cm" in step.detail, "裏地の裾の縫い代が書かれていない"
    assert "yousai.net" not in step.detail  # 手順書にはURLではなく出典名を書く
    assert "うさこの洋裁工房" in step.detail


def test_the_final_step_says_what_the_engine_does_not_know(lined):
    """「どう合わせるか」を知らないことを、知らないと書いていること。

    袋状に縫うか見返しを付けるかは型紙からは決まらない。もっともらしい
    手順を書けば、それは根拠のない指示になる。
    """
    step = next(s for s in lined.assembly_steps()
                if s.title == "裏地を身頃に合わせる")
    assert "書けません" in step.detail


def test_no_lining_steps_appear_without_a_lining(tmp_path):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(spec, STANDARD, skip_export=True)
    titles = " ".join(s.title for s in result.assembly_steps())
    assert "裏地" not in titles


# --- 画面とAPIの経路(round41) ----------------------------------------------

def _form(**extra):
    form = {"mode": "manual", "bust": "84", "waist": "68", "hip": "92",
            "height": "160", "sleeve_length": "54", "shoulder_width": "37",
            "neckline": "round_neck", "sleeve_style": "straight",
            "skirt_style": "", "custom_panels_json": "[]"}
    form.update(extra)
    return form


def test_the_lining_downloads_are_offered_and_actually_serve_a_file(client):
    """裏地のダウンロードが、押したら実際に落ちてくること。

    round40まで`/download/<job>/<fmt>`の許可リストとファイル名の対応が
    2か所に分かれていた。片方だけ増やすと「許可されているのにファイル名が
    合わず404」になるので、実際に取りに行って確かめる。
    """
    response = client.post("/api/generate", data=_form(lining="1"))
    assert response.status_code == 200
    payload = response.get_json()
    links = payload["download"]
    for fmt in ("lining_svg", "lining_pdf", "lining_dxf", "lining_projector"):
        assert fmt in links, fmt
        got = client.get(links[fmt])
        assert got.status_code == 200, f"{fmt} が落ちてこない"
        assert len(got.data) > 0
    assert payload["lining"]["part_count"] > 0


def test_no_lining_links_are_offered_when_there_is_no_lining(client):
    """裏地を付けていない生成では、裏地のリンクを出さない。

    出すと「押したら404」になる。round40までリンクの一覧は呼び出し側に
    べた書きだったので、こういう出し分けができなかった。
    """
    payload = client.post("/api/generate", data=_form()).get_json()
    assert payload["lining"] is None
    assert not any(k.startswith("lining_") for k in payload["download"])


def test_an_unknown_download_format_is_still_rejected(client):
    assert client.get("/download/0123456789ab/lining_exe").status_code == 400


def test_the_v1_api_actually_applies_the_options_it_reads(client):
    """`/api/v1/generate`が、読み取った指定を実際に型紙へ渡していること。

    【round40まで何が壊れていたか】この関数のdocstringは「リクエストボディは
    `/api/generate`と同じフォームフィールドを受け付ける」と約束しているのに、
    `one_way_fabric` / `shrink_percent` / `pattern_repeat_cm` / `alterations` /
    手持ちの生地の判定を**1つも`generate_from_selection`へ渡していなかった**。

    読み取り側の`_parse_*`は書いてあるので、不正な値なら400が返る。
    つまりAPI利用者から見ると「指定は受理されたのに効かない」——
    エラーが返るぶん、**効いていると誤解しやすい**。

    ここでは、効いていれば必ず結果に現れる4つを見る:
    一方方向の生地の注記、縮み分、柄合わせの上乗せ、補正の記録、そして
    round41で足した裏地。
    """
    import re as _re
    from tests.test_app import _extract_issued_api_key, _signup, _valid_form

    _signup(client, email="v1options@example.com")
    created = client.post("/account/api-keys", data={"name": "opt"},
                          follow_redirects=True)
    key = _extract_issued_api_key(created.get_data(as_text=True))

    form = dict(_valid_form())
    form.pop("mode", None)
    form.update({
        "one_way_fabric": "1",
        "shrink_percent": "2",
        "pattern_repeat_cm": "12",
        "alter_waist_width": "-2",
        "lining": "1",
        "stash_width_cm": "110",
        "stash_length_cm": "500",
    })
    payload = client.post("/api/v1/generate", data=form,
                          headers={"Authorization": f"Bearer {key}"}).get_json()
    assert payload["ok"] is True

    notes = " ".join(payload["shopping_list"]["notes"])
    assert "一方方向の生地" in notes, "one_way_fabric が渡っていない"
    assert "収縮率2%" in notes, "shrink_percent が渡っていない"
    assert payload["shopping_list"]["pattern_repeat_extra_cm"] > 0, \
        "pattern_repeat_cm が渡っていない"
    assert any("ウエスト" in n for n in payload["design_notes"]), \
        "alterations が渡っていない"
    assert payload["lining"] is not None, "lining が渡っていない"
    assert payload["stash_verdict"] is not None, "手持ちの生地の判定が走っていない"
    assert _re.match(r"^[0-9a-f]{6,32}$", payload["job_id"])
