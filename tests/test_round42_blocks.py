"""round42: 原型(ブロック)を選べるようにした(engine/blocks.py)。

【round41まで何が壊れていたか】このエンジンの身頃は、はじめから最後まで
**新文化式の婦人原型**の式で組まれていた。背幅 B/8+7.4、胸幅 B/8+6.2、
前ネック幅 B/24+3.4、胸ぐせ (B/4−2.5)°。それでいて採寸欄は身長120cmから
受け付けたので、**子どもの寸法を入れると、子どもの体に成人女子の原型を
当てた型紙**が、一言の断りもなく出ていた。

【このテストが見張っていること】
  1. 子ども原型で引いた型紙が、出典の式**そのとおりの寸法**になること
     (背幅・胸幅・袖ぐり深さ・ゆとり・胸ぐせ角度)。
  2. 大人(既定)の型紙が**1mmも変わっていない**こと。原型を足したことで
     既存の利用者の型紙が動いたら、それは改善ではなく破壊である。
  3. 子どもの参考寸法12段階のどれを入れても、身に覚えのないクランプ警告が
     出ず、丈が体に比例すること(round41までは10/12段階で丈が頭打ちだった)。
  4. 資料に無いこと(男性原型)は入っていないと、はっきり言うこと。
"""

import pytest

from shapely.geometry import Polygon

from engine.blocks import (ADULT_FEMALE, BLOCKS, CHILD, DEFAULT_BLOCK_KEY,
                            Formula, MENS_BLOCK_ABSENT_NOTE, block_notes,
                            get_block)
from engine.bodice_fit import (armhole_depth_cm, back_width_cm, chest_width_cm,
                                neck_half_cm)
from engine.darts import bust_dart_angle_deg
from engine.measurements import Measurements, STANDARD_M, _VALID_RANGES
from engine.part_specs import MAX_SCALE
from engine.pipeline import (PatternForgePipeline, _closed_points_from_segments,
                              _x_span_at_y, build_garment_spec)

#: MAISON DE AS「採寸の仕方【男性・女性・子供】」の子どもの参考寸法。
#: https://maisondeas.com/taking-measurements/
#: (身長, バスト, ウエスト, ヒップ, 肩幅, 袖丈)
KIDS_REFERENCE_SIZES = [
    (80, 50, 48, 50, 24, 24),
    (90, 52, 49, 52, 26, 24),
    (95, 53, 50, 55, 27, 25),
    (102, 54, 51, 57, 28, 26),
    (108, 56, 52, 59, 29, 27),
    (114, 58, 53, 61, 30, 28),
    (120, 60, 54, 63, 31, 30),
    (126, 62, 55, 66, 32, 32),
    (131, 64, 56, 70, 33, 34),
    (137, 66, 58, 72, 34, 36),
    (143, 69, 60, 75, 35, 38),
    (150, 72, 61, 78, 36, 40),
]

ADULT = Measurements(84, 68, 92, 160, 54, 37)
#: 製図の式との比較なので、0.005cm(50ミクロン)まで一致を求める。
TOL = 0.005


def _kid(height, bust, waist, hip, shoulder, sleeve):
    return Measurements(bust=bust, waist=waist, hip=hip, height=height,
                        sleeve_length=sleeve, shoulder_width=shoulder)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("blocks")))


def _generate(pipeline, measurements, block_key=None, **kwargs):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style=None)
    return pipeline.generate_from_selection(
        spec, measurements, skip_export=True, block_key=block_key, **kwargs)


# --- 式そのもの ------------------------------------------------------------

def test_the_child_formulas_are_the_ones_the_source_writes():
    """出典が数字で書いている式を、そのまま持っていること。

    出典: MAISON DE AS「【原型製図】子供原型作り(新文化)」
      「背幅（バスト寸法÷5+1.2）」「胸幅（バスト寸法÷5）」
      「前襟ぐり幅（◎-0.2）」(◎=背幅÷2 なので B/10+0.4)
      「Fを基点に8°とり」
      「バスト寸法÷2にゆとり分バスト寸法÷8」(半身にB/8 → 総回りB/4)
      「背丈(身長÷4)」「A点から背丈÷2+1(ゆとり)」(→ 袖ぐり深さ 身長/8+1)
    """
    assert CHILD.back_width == Formula(5.0, 1.2)
    assert CHILD.chest_width == Formula(5.0, 0.0)
    assert CHILD.neck_half == Formula(10.0, 0.4)
    assert CHILD.bust_dart_angle == Formula(None, 8.0)
    assert CHILD.standard_ease == Formula(4.0, 0.0)
    assert CHILD.armhole_depth == Formula(8.0, 1.0, base="height")
    # 前ネック幅は「背幅の半分 − 0.2」と同じ値になること(式の書き換えが
    # 出典の手順とずれていないことの確認)。
    for bust in (50.0, 60.0, 72.0):
        assert CHILD.neck_half.value(bust) == pytest.approx(
            CHILD.back_width.value(bust) / 2.0 - 0.2)


def test_the_adult_formulas_did_not_move():
    """成人女子の式が1つも変わっていないこと。"""
    assert ADULT_FEMALE.back_width == Formula(8.0, 7.4)
    assert ADULT_FEMALE.chest_width == Formula(8.0, 6.2)
    assert ADULT_FEMALE.neck_half == Formula(24.0, 3.4)
    assert ADULT_FEMALE.bust_dart_angle == Formula(4.0, -2.5)
    assert ADULT_FEMALE.ease_cm(83.0) == pytest.approx(8.0)
    assert ADULT_FEMALE.armhole_depth is None
    assert DEFAULT_BLOCK_KEY == ADULT_FEMALE.key


def test_the_helper_functions_default_to_the_adult_block():
    """`block`を渡さない呼び出しは、round41までとまったく同じ値を返す。"""
    for bust in (60.0, 83.0, 110.0):
        assert back_width_cm(bust) == pytest.approx(bust / 8.0 + 7.4)
        assert chest_width_cm(bust) == pytest.approx(bust / 8.0 + 6.2)
        assert neck_half_cm(bust) == pytest.approx(bust / 24.0 + 3.4)
        assert bust_dart_angle_deg(bust) == pytest.approx(max(0.0, bust / 4 - 2.5))


def test_the_child_block_changes_those_same_functions():
    for bust in (50.0, 60.0, 72.0):
        assert back_width_cm(bust, CHILD) == pytest.approx(bust / 5.0 + 1.2)
        assert chest_width_cm(bust, CHILD) == pytest.approx(bust / 5.0)
        assert neck_half_cm(bust, CHILD) == pytest.approx(bust / 10.0 + 0.4)
        assert bust_dart_angle_deg(bust, CHILD) == 8.0


def test_the_child_armhole_depth_needs_the_height_and_says_so():
    """身長から決まる式なのに身長が渡されなければ、黙って別の値を返さない。"""
    assert armhole_depth_cm(23.5, 60.0, 0.75, CHILD, 120.0) == pytest.approx(16.0)
    with pytest.raises(ValueError, match="身長"):
        armhole_depth_cm(23.5, 60.0, 0.75, CHILD)
    # 大人はテンプレートからの増分方式のまま(身長は要らない)。
    assert armhole_depth_cm(23.5, 83.0, 1.0) == pytest.approx(23.5)


def test_an_unknown_block_is_an_error_not_a_silent_fallback():
    """知らない原型キーは黙って既定に落とさない。

    落とすと「子どもを選んだのに大人の型紙が出た」を、利用者が
    出来上がりを見るまで気づけない。
    """
    assert get_block(None) is ADULT_FEMALE
    assert get_block("") is ADULT_FEMALE
    assert get_block("child") is CHILD
    with pytest.raises(ValueError, match="原型は"):
        get_block("adult_male")


def test_a_formula_with_a_zero_divisor_is_rejected():
    with pytest.raises(ValueError):
        Formula(0.0, 1.0)
    with pytest.raises(ValueError):
        Formula(2.0, 1.0, base="waist")


def test_formula_text_reads_like_the_source():
    assert ADULT_FEMALE.back_width.text() == "B/8 + 7.4"
    assert CHILD.chest_width.text() == "B/5"
    assert CHILD.bust_dart_angle.text() == "8"
    assert CHILD.armhole_depth.text() == "身長/8 + 1"


# --- 型紙が式のとおりに出ること ---------------------------------------------

@pytest.mark.parametrize("height,bust,waist,hip,shoulder,sleeve",
                         [(102, 54, 51, 57, 28, 26), (120, 60, 54, 63, 31, 30),
                          (150, 72, 61, 78, 36, 40)])
def test_the_child_pattern_lands_exactly_on_the_block_formulas(
        pipeline, height, bust, waist, hip, shoulder, sleeve):
    """背幅・胸幅・袖ぐり深さ・半身幅が、式の値ちょうどになること。

    「だいたい近い」では意味がない。式のとおりに引けていなければ、
    それは出典の原型ではなく、このエンジンが勝手に作った別の何かである。
    """
    result = _generate(pipeline, _kid(height, bust, waist, hip, shoulder, sleeve),
                        block_key="child")
    front = next(s for s in result.scaled_parts if s.part_type == "front_bodice")
    back = next(s for s in result.scaled_parts if s.part_type == "back_bodice")

    assert back.chest_width_cm_actual == pytest.approx(
        CHILD.back_width.value(bust), abs=TOL)
    assert front.chest_width_cm_actual == pytest.approx(
        CHILD.chest_width.value(bust), abs=TOL)

    points = _closed_points_from_segments(front.segments)
    neck_y = min(p[1] for p in points)
    depth = front.bust_line_y_cm - neck_y
    assert depth == pytest.approx(CHILD.armhole_depth.value(bust, height), abs=TOL)

    span = _x_span_at_y(points, front.bust_line_y_cm)
    half = (span[1] - span[0]) / 2.0
    # 出来上がり胴回り = バスト + ゆとり。前身頃はその半分の幅で、
    # 中心から脇まではさらにその半分。
    assert half == pytest.approx((bust + CHILD.ease_cm(bust)) / 4.0, abs=TOL)


def test_the_child_bodice_is_roomier_than_the_adult_block_would_make_it(pipeline):
    """同じ子どもの寸法で、原型を変えると幅が実際に変わること。

    実測(身長120・バスト60): 大人の式ではゆとり8cm、子ども原型では
    バスト/4 = 15cm。総回りで7cmの差になる。
    """
    kid = _kid(120, 60, 54, 63, 31, 30)
    adult_run = _generate(pipeline, kid)
    child_run = _generate(pipeline, kid, block_key="child")

    def _half(result):
        front = next(s for s in result.scaled_parts if s.part_type == "front_bodice")
        span = _x_span_at_y(_closed_points_from_segments(front.segments),
                             front.bust_line_y_cm)
        return (span[1] - span[0]) / 2.0

    assert _half(adult_run) == pytest.approx((60 + 8.0) / 4.0, abs=TOL)
    assert _half(child_run) == pytest.approx((60 + 15.0) / 4.0, abs=TOL)
    assert _half(child_run) - _half(adult_run) == pytest.approx(7.0 / 4.0, abs=TOL)


def test_the_child_block_does_not_draw_a_bust_point(pipeline):
    """子どもの型紙にBP(バストポイント)を描かない。

    出典の製図にBPは出てこない。6歳児の型紙にバストポイントの十字が
    印刷されるのは、単に間違っている。
    """
    kid = _kid(120, 60, 54, 63, 31, 30)
    child_run = _generate(pipeline, kid, block_key="child")
    adult_run = _generate(pipeline, kid)

    def _labels(result):
        front = next(p for p in result.finalized_parts
                     if p.part_type == "front_bodice")
        return [label for label, _pts in front.reference_lines]

    assert "BP" not in _labels(child_run)
    # 大人では今までどおり描く(テストが空振りしていないことの確認)。
    assert "BP" in _labels(adult_run)


def test_the_child_bust_dart_is_smaller_than_the_adult_one(pipeline):
    """胸ぐせダーツの角が8°になり、大人の式(12.5°)より小さいこと。"""
    kid = _kid(120, 60, 54, 63, 31, 30)
    assert bust_dart_angle_deg(60, CHILD) == 8.0
    assert bust_dart_angle_deg(60, ADULT_FEMALE) == pytest.approx(12.5)
    child_run = _generate(pipeline, kid, block_key="child")
    front = next(s for s in child_run.scaled_parts
                 if s.part_type == "front_bodice")
    # 角が小さいぶん、ダーツを閉じたときの裾の下がり量も小さい。
    adult_front = next(s for s in _generate(pipeline, kid).scaled_parts
                       if s.part_type == "front_bodice")
    assert front.bust_dart_shift_cm < adult_front.bust_dart_shift_cm


# --- 参考寸法12段階を全部通す ----------------------------------------------

@pytest.mark.parametrize("size", KIDS_REFERENCE_SIZES,
                         ids=[f"h{s[0]}" for s in KIDS_REFERENCE_SIZES])
def test_every_reference_child_size_generates_without_phantom_clamp_warnings(
        pipeline, size):
    """子どもの参考寸法のどれを入れても、身に覚えのない警告が出ないこと。

    round41までは、身長120cm未満は**入力の時点でエラー**、120cm以上でも
    テンプレートの縮小限界(標準Mの0.7倍=110.6cm)に当たり、12段階のうち
    10段階で「◯cm相当として生成しました」というクランプ警告が出ていた。
    """
    result = _generate(pipeline, _kid(*size), block_key="child")
    clamps = [w for w in result.measurement_warnings if "変形可能範囲" in w]
    assert clamps == [], f"身長{size[0]}: {clamps}"
    assert result.compatibility_warnings() == []
    for part in result.finalized_parts:
        assert Polygon(part.cut_line).is_valid, part.identifier


def test_the_child_bodice_length_actually_follows_the_height(pipeline):
    """丈が身長に比例して伸びること(頭打ちにならないこと)。

    round41までは身長80〜108cmの子の身頃丈が**全部44.1cm**、
    身長80〜131cmの袖丈が**全部38.4cm**で出ていた(実測)。
    倍率の下限が成人女子だけを見た0.7で止まっていたためである。
    """
    lengths = []
    sleeves = []
    for size in KIDS_REFERENCE_SIZES:
        result = _generate(pipeline, _kid(*size), block_key="child")
        lengths.append(next(p.height_cm for p in result.finalized_parts
                            if p.part_type == "front_bodice"))
        sleeves.append(next(p.height_cm for p in result.finalized_parts
                            if p.part_type == "sleeve"))
    # 身長順に単調増加(同じ丈が並ばない)。
    assert all(b > a for a, b in zip(lengths, lengths[1:])), lengths
    assert len(set(round(v, 1) for v in sleeves)) >= 8, sleeves
    # いちばん小さい子といちばん大きい子で、丈が身長比なりに開いていること。
    assert lengths[-1] / lengths[0] == pytest.approx(150 / 80, rel=0.05)


def test_the_child_min_scale_covers_the_whole_valid_measurement_range():
    """原型の縮小下限が、入力を許している範囲を全部通せること。

    `_VALID_RANGES`の下限を動かしたのに`min_scale`を直し忘れると、
    「入力は通るのに黙ってクランプされる」型紙が出る。round42で
    `MIN_SCALE_BAND`が実際にその形で古くなっていた(帯状パーツが
    子どものカフスを約2倍の長さでクランプしていた)。
    """
    needed = []
    for name in ("height", "hip", "sleeve_length", "shoulder_width", "waist"):
        lo, _hi = _VALID_RANGES[name]
        needed.append(lo / getattr(STANDARD_M, name))
    assert CHILD.min_scale is not None
    assert CHILD.min_scale <= min(needed), (
        f"子ども原型のmin_scale={CHILD.min_scale}では、"
        f"入力可能な最小値(必要倍率{min(needed):.3f})が通らない")


def test_band_parts_are_not_clamped_for_children_either():
    """帯状パーツのクランプ範囲も、入力を許している範囲を全部通すこと。"""
    from engine.part_specs import MIN_SCALE_BAND, MAX_SCALE_BAND
    for name in ("bust", "sleeve_length", "waist"):
        lo, hi = _VALID_RANGES[name]
        standard = getattr(STANDARD_M, name)
        assert MIN_SCALE_BAND <= lo / standard, name
        assert MAX_SCALE_BAND >= hi / standard, name


# --- 大人の型紙が変わっていないこと ------------------------------------------

def test_the_default_block_produces_the_round41_pattern_unchanged(pipeline):
    """既定(原型を選ばない)で生成した型紙が、大人の原型と完全一致すること。"""
    plain = _generate(pipeline, ADULT)
    explicit = _generate(pipeline, ADULT, block_key="adult_female")
    for a, b in zip(plain.finalized_parts, explicit.finalized_parts):
        assert a.cut_line == b.cut_line
        assert a.stitch_line == b.stitch_line
        assert a.notches == b.notches
    assert plain.design_notes == explicit.design_notes


def test_the_fit_presets_still_mean_the_same_centimetres_for_adults(pipeline):
    """ゆとりの選択が、大人では round41までとまったく同じcmで効くこと。

    round42でゆとりを「原型の標準ゆとりからの増減」に変えた。成人女子の
    標準ゆとりは8.0cmなので、ぴったり4.0/標準8.0/ゆったり14.0は
    そのままの値でなければならない。
    """
    from engine.scaling import bodice_ease_for
    for fit, expected in (("fitted", 4.0), ("standard", 8.0), ("relaxed", 14.0)):
        assert bodice_ease_for(ADULT, fit) == pytest.approx(expected)
    # 子どもは標準がバスト/4なので、そこからの増減になる。
    kid = _kid(120, 60, 54, 63, 31, 30)
    assert bodice_ease_for(kid, "standard", CHILD) == pytest.approx(15.0)
    assert bodice_ease_for(kid, "fitted", CHILD) == pytest.approx(11.0)
    assert bodice_ease_for(kid, "relaxed", CHILD) == pytest.approx(21.0)


# --- 開示 ------------------------------------------------------------------

def test_choosing_the_child_block_discloses_the_formulas_and_the_source(pipeline):
    result = _generate(pipeline, _kid(120, 60, 54, 63, 31, 30), block_key="child")
    notes = " ".join(result.design_notes)
    assert "原型「子ども」で引きました" in notes
    assert "B/5 + 1.2" in notes and "B/5" in notes
    assert "maisondeas.com/kids-pattern-block-new-bunka" in notes
    assert "BP(バストポイント)の印を型紙に描きません" in notes


def test_the_default_block_says_nothing_extra(pipeline):
    """既定で生成したときは原型の説明を出さない(毎回同じ文が並ぶだけ)。"""
    result = _generate(pipeline, ADULT)
    assert not any("原型「" in n for n in result.design_notes)
    assert block_notes(ADULT_FEMALE, 84.0, 160.0) == []


def test_a_height_outside_the_block_range_is_flagged_but_still_generated(pipeline):
    """原型の想定身長から外れたら警告を出す。ただし生成は止めない。

    境目の体型は実在する(身長150cmの大人、身長155cmの中学生)。
    入力を拒むのではなく、選び直せるように伝える。
    """
    tall_kid = _kid(160, 78, 64, 84, 38, 46)
    result = _generate(pipeline, tall_kid, block_key="child")
    # 警告は青い注記ではなく赤い警告の側に出す(round32で分けた区別)。
    warnings = " ".join(result.measurement_warnings)
    assert "身長80〜150cm向けの原型です" in warnings and "大きすぎる" in warnings
    assert result.finalized_parts  # 生成そのものは止まっていない

    small_adult = _kid(100, 53, 50, 55, 25, 26)
    adult_run = _generate(pipeline, small_adult)
    # 既定(大人)でも範囲外の警告は出す。round42で最初に書いたときは
    # `block_notes`の早期returnに巻き込まれ、**この場合だけ出なかった**
    # ——身長100cmの子に大人の原型を当てたときこそ要る警告なのに。
    assert not any("原型「" in n for n in adult_run.design_notes)
    adult_warnings = " ".join(adult_run.measurement_warnings)
    assert "身長140〜190cm向けの原型です" in adult_warnings
    assert "小さすぎる" in adult_warnings


def test_the_absence_of_a_mens_block_is_stated_not_hidden():
    """男性原型が無いことを、無いと書いてあること。

    黙って無いままにすると、利用者は探し続ける。何が足りないのか
    (式が数字で書かれた出典)まで書いてあれば、持っている人が持ってこられる。
    """
    assert "男性の原型はまだありません" in MENS_BLOCK_ABSENT_NOTE
    assert "出典" in MENS_BLOCK_ABSENT_NOTE
    assert set(BLOCKS) == {"adult_female", "child"}


# --- 画面とAPI --------------------------------------------------------------

def test_the_form_offers_every_block_with_its_source(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="block"' in body
    for block in BLOCKS.values():
        assert f'value="{block.key}"' in body
        assert block.source_url in body
    assert "男性の原型はまだありません" in body


def _form(**extra):
    form = {"mode": "manual", "bust": "60", "waist": "54", "hip": "63",
            "height": "120", "sleeve_length": "30", "shoulder_width": "31",
            "neckline": "round_neck", "sleeve_style": "straight",
            "skirt_style": "", "custom_panels_json": "[]"}
    form.update(extra)
    return form


def test_the_api_applies_the_selected_block(client):
    payload = client.post("/api/generate", data=_form(block="child")).get_json()
    assert payload["ok"] is True
    assert any("原型「子ども」" in n for n in payload["design_notes"])
    plain = client.post("/api/generate", data=_form()).get_json()
    assert not any("原型「" in n for n in plain["design_notes"])


def test_an_unknown_block_is_a_400_not_a_silent_adult_pattern(client):
    response = client.post("/api/generate", data=_form(block="adult_male"))
    assert response.status_code == 400
    assert "原型は" in response.get_json()["error"]


def test_children_can_actually_be_entered_now(client):
    """round41まで入力の時点で弾かれていた1歳児が、通ること。"""
    response = client.post("/api/generate", data=_form(
        block="child", height="80", bust="50", waist="48", hip="50",
        shoulder_width="24", sleeve_length="24"))
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["part_count"] > 0


def test_the_fit_labels_do_not_hardcode_the_adult_ease(client):
    """ゆとりの選択肢が、原型に合わせて書き換えられる作りになっていること。

    round41までは「標準（身頃 バスト+8.0cm）」と絶対値を書いていた。
    子ども原型の標準ゆとりはバスト/4(バスト60で15cm)なので、この表示は
    子どもを選ぶと**嘘になる**。app.jsがdata-*から書き換える前提を、
    テンプレート側の目印が消えていないことで保証する。

    数字をJS側で計算し直すことはしていない(エンジンの式を2か所に持つと
    必ず食い違う)。原型が持つ式の文字列と、標準からの増減を並べるだけ。
    """
    import pathlib
    import app as app_module

    body = client.get("/").get_data(as_text=True)
    assert 'data-fit-delta="0.0"' in body or 'data-fit-delta="0"' in body
    assert 'data-ease-text="B/4"' in body      # 子ども
    assert 'data-ease-text="8"' in body        # 大人(定数)
    js = (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(
        encoding="utf-8")
    assert "syncFitLabels" in js
    # 式の係数をJSに書き写していないこと(二重管理の再発防止)。
    assert "/ 4" not in js.split("function syncFitLabels")[1].split("}")[0]
