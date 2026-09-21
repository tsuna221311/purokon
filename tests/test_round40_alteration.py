"""round40: 着てみて合わなかったときに、型紙を直す(engine/alteration.py)。

【round39まで何が足りなかったか】この製品は**型紙を出すところで終わって
いた**。実際に縫って、肩が窮屈だった・ウエストがきつかった——そのとき
利用者にできるのは、採寸値を変えて全部やり直すことだけだった。

【症状を当てない】「なで肩ですか?」と聞いてこちらで補正量を決めるやり方は
採っていない。どれくらいなで肩なのかは分かりようがないからである。
利用者が実物で測った余り/不足をcmで受け取る——数字の出どころが実測になる。

このテストが見張っているのは、**入れた数字がそのとおりに型紙へ効くこと**。
「だいたい効いている」では意味が無い。1.0cm入れたら1.0cm動く。
"""

import pytest

from engine.alteration import (ALTERATION_KEYS, ALTERATION_KINDS,
                                LARGE_ALTERATION_CM, MAX_ALTERATION_CM,
                                SIDE_SEAM_SHARE, validate)
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, _closed_points_from_segments,
                              _x_span_at_y, build_garment_spec)
from engine.svgpath import segments_to_polyline

STANDARD = Measurements(84, 68, 92, 160, 54, 37)
#: 変形・ダーツを通したあとの実測なので、0.05cm(0.5mm)まで一致を求める。
TOL = 0.05


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("alter")))


def _front(pipeline, alterations=None):
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        spec, STANDARD, alterations=alterations, skip_export=True)
    scaled = next(s for s in result.scaled_parts if s.part_type == "front_bodice")
    return scaled, result


def _width_at(scaled, y):
    span = _x_span_at_y(_closed_points_from_segments(scaled.segments), y)
    return None if span is None else span[1] - span[0]


def _shoulder_y_at_anchor(scaled):
    """肩の基準点のxで、肩線の高さを測る。

    出来上がった輪郭の「いちばん外側の点」を追うと、肩幅の補正で点そのものが
    動くので比べられない。基準点のxで測れば、同じ場所を比べられる。
    """
    shoulder_x = max(x for role, x in scaled.fit_anchors_scaled
                      if role == "shoulder")
    points = segments_to_polyline(scaled.segments, curve_steps=400)
    limit = scaled.bust_line_y_cm * 0.7
    near = [y for x, y in points if abs(x - shoulder_x) < 0.05 and y < limit]
    return max(near) if near else None


# --- 入れた数字がそのとおり効くこと -------------------------------------------

@pytest.mark.parametrize("amount", [4.0, -4.0, 2.0])
def test_the_waist_moves_by_exactly_a_quarter_per_side_seam(pipeline, amount):
    """ウエストの補正が、脇1本あたり一周ぶんの1/4だけ動くこと。

    出典: MAISON DE AS「不足分の1/4を外側に出し、脇線を引き直す」。
    前身頃・後ろ身頃それぞれに脇が1本ずつ、左右で合計4本あるので1/4。
    前身頃1枚には脇が2本(左右)あるから、パネルの幅は 2×(1/4) = 半分動く。

    【ここで2回踏んだ落とし穴】
    1つめ: 基準点のxで重みを配っていたが、身頃はウエストで絞ってあるので
    **脇線は基準点より内側にある**。満額が届かず、-4cmの指定で-1.49cmしか
    動かなかった。中心からの距離を「その高さの半幅」で正規化して直した。
    2つめ: それでも0.75倍のままだった。原因は基準点のyで、身頃は胸ぐせ
    ダーツの分だけ下へずれるため、**基準点のウエスト38.48cmに対し実際の
    ウエスト線は43.51cm**だった。5cmずれた位置を「ウエスト」として重みを
    配っていた。`ScaledPart.waist_y_cm`(変形もダーツも通したあとの値)を
    使って直した。
    """
    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"waist_width": amount})
    before = _width_at(base, base.waist_y_cm)
    after = _width_at(altered, altered.waist_y_cm)
    expected = amount * SIDE_SEAM_SHARE * 2      # 左右2本ぶん
    assert after - before == pytest.approx(expected, abs=TOL)


def test_the_bust_moves_and_the_waist_does_not(pipeline):
    """胸の補正が胸に効き、ウエストへ漏れないこと。

    高さごとの重みが混ざっていると、片方を直したつもりでもう片方が動く。
    """
    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"bust_width": 4.0})
    assert (_width_at(altered, altered.bust_line_y_cm)
            - _width_at(base, base.bust_line_y_cm)) == pytest.approx(2.0, abs=TOL)
    assert (_width_at(altered, altered.waist_y_cm)
            - _width_at(base, base.waist_y_cm)) == pytest.approx(0.0, abs=TOL)


def test_the_hip_does_not_leak_into_the_waist(pipeline):
    """ヒップの補正がウエストへ漏れないこと。

    直す前は、ヒップを4cm広げるとウエストまで0.5cm広がっていた。
    """
    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"hip_width": 4.0})
    assert (_width_at(altered, altered.waist_y_cm)
            - _width_at(base, base.waist_y_cm)) == pytest.approx(0.0, abs=TOL)


@pytest.mark.parametrize("amount", [1.0, -1.0, 0.5])
def test_the_shoulder_slope_moves_the_shoulder_line_by_the_amount(pipeline, amount):
    """肩の傾きの補正が、肩先で指定どおり動くこと。

    【落とし穴】最初は首の付け根から脇の下へ一律に薄めていた。肩先は
    その途中(首の付け根から8.1cm、脇の下は23.9cm)にあるので、
    **肩先の時点で既に66%まで薄まっていた**——1.0cm下げたつもりが
    0.62cmしか下がらない。肩先までは満額を保つよう直した。
    """
    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"shoulder_slope": amount})
    before = _shoulder_y_at_anchor(base)
    after = _shoulder_y_at_anchor(altered)
    assert before is not None and after is not None
    assert after - before == pytest.approx(amount, abs=TOL)


@pytest.mark.parametrize("amount", [1.0, -1.0])
def test_the_shoulder_width_moves_the_tip_by_the_amount(pipeline, amount):
    """肩幅の補正が、肩先で指定どおり動くこと。

    出典: ここのの衣装製作日記「型紙補正！肩幅を広げる方法」——肩先を
    伸ばし、元の肩の角度を保ち、脇で元の線に戻す。
    """
    def _tip_x(scaled):
        points = segments_to_polyline(scaled.segments, curve_steps=400)
        limit = scaled.bust_line_y_cm * 0.6
        return max(x for x, y in points if y < limit)

    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"shoulder_width": amount})
    assert _tip_x(altered) - _tip_x(base) == pytest.approx(amount, abs=TOL)


def test_the_side_seam_returns_to_the_original_line_below_the_armhole(pipeline):
    """肩幅の補正が、脇の下より下へ及ばないこと。

    出典の「脇でもとの線に戻るよう線をひきます」がここにあたる。
    及んでしまうと、身幅まで一緒に変わる。
    """
    base, _ = _front(pipeline)
    altered, _ = _front(pipeline, {"shoulder_width": 1.0})
    assert (_width_at(altered, altered.bust_line_y_cm)
            - _width_at(base, base.bust_line_y_cm)) == pytest.approx(0.0, abs=TOL)
    assert (_width_at(altered, altered.waist_y_cm)
            - _width_at(base, base.waist_y_cm)) == pytest.approx(0.0, abs=TOL)


def test_no_alteration_changes_nothing(pipeline):
    """補正を入れなければ、型紙が1mmも変わらないこと。"""
    base, _ = _front(pipeline)
    same, _ = _front(pipeline, {})
    assert base.segments == same.segments


def test_two_alterations_combine(pipeline):
    """2つ同時に入れても、それぞれが独立に効くこと。"""
    base, _ = _front(pipeline)
    both, _ = _front(pipeline, {"bust_width": 2.0, "waist_width": -2.0})
    assert (_width_at(both, both.bust_line_y_cm)
            - _width_at(base, base.bust_line_y_cm)) == pytest.approx(1.0, abs=TOL)
    assert (_width_at(both, both.waist_y_cm)
            - _width_at(base, base.waist_y_cm)) == pytest.approx(-1.0, abs=TOL)


# --- 開示と検算 ---------------------------------------------------------------

def test_what_was_altered_is_disclosed(pipeline):
    """何をどれだけ直したかを、黙らずに伝えること。

    どの数字がどこに効いたのかが分からないと、次に合わなかったときに
    また同じ迷い方をする。
    """
    _scaled, result = _front(pipeline, {"waist_width": -0.5})
    notes = [n for n in result.design_notes if "補正しました" in n]
    assert notes, result.design_notes
    assert "ウエスト" in notes[0] and "0.5cm" in notes[0]


def test_a_large_alteration_is_flagged(pipeline):
    """勧められる範囲を超える補正は、そう伝えること。

    出典: MAISON DE AS「体型補正は0.5〜0.8cm程度まで」。それを超える場合は
    幅と丈の併用が必要とされている。適用は止めない——止めると利用者は
    何もできなくなる——が、縫い合わせの相手と合わなくなることは必ず言う。
    """
    _scaled, result = _front(pipeline, {"waist_width": 3.0})
    warned = [n for n in result.design_notes if "超えています" in n]
    assert warned, result.design_notes
    assert f"{LARGE_ALTERATION_CM:g}cm" in warned[0]

    _scaled2, small = _front(pipeline, {"waist_width": LARGE_ALTERATION_CM - 0.1})
    assert not [n for n in small.design_notes if "超えています" in n]


def test_out_of_range_is_refused_not_silently_clamped():
    """範囲外は黙って丸めず、エラーにすること。

    勝手に丸めると、利用者は自分の入れた数字が使われたと思い込む。
    """
    with pytest.raises(ValueError, match="まで"):
        validate({"waist_width": MAX_ALTERATION_CM + 0.1})
    with pytest.raises(ValueError, match="知らない補正"):
        validate({"banana": 1.0})
    # 0は「補正しない」と同じ扱いにする(項目だけ残さない)
    assert validate({"waist_width": 0.0}) == {}


def test_every_kind_explains_how_to_measure_and_cites_a_source():
    """全ての項目に、測り方と正負の意味と出典があること。

    測り方が曖昧だと、入力された数字の意味が人によって揺れる。
    そうなると「1.0cm入れたら1.0cm動く」という保証に意味が無くなる。
    """
    assert len(ALTERATION_KINDS) == len(ALTERATION_KEYS)
    for kind in ALTERATION_KINDS:
        assert kind.how_to_measure.strip()
        assert kind.positive_means.strip()
        assert kind.negative_means.strip()
        assert kind.source_url.startswith("https://"), kind
