"""round14で追加した「身頃を区間ごとに違う倍率で採寸に合わせる」機構の検証。

ここで守りたいのは主に次の3点:
  1. 入力された肩幅が、実際に型紙の肩幅になること(round13までは無視されていた)。
  2. 首の開きがバスト比そのままではなく、ネック幅の式で決まること。
  3. その仕組みが「静かに使われなくなる」経路を塞ぐこと
     (テンプレートが基準点を持たない/パイプラインが渡さない、の両方)。
"""

import math
from types import SimpleNamespace

import pytest
import shapely.geometry as sg

from engine.bodice_fit import (
    ARMHOLE_CURVE_MAX_ERROR_RATIO,
    MIN_ARMHOLE_WIDTH_CM,
    MIN_SHOULDER_RUN_CM,
    BodiceFitError,
    _STANDARD_BUST_CM,
    build_x_map,
    effective_shoulder_width_cm,
    map_x,
    neck_half_cm,
    parse_fit_anchors,
    remap_segments_x,
)
from engine.measurements import Measurements, STANDARD_M
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.scaling import (
    FIT_ANCHOR_PART_TYPES, bodice_fit_clamp_warning, compute_scale_factors, scale_template,
)
from engine.svgpath import bounding_box, parse_path, segments_to_polyline
from engine.templates_db import TemplateDB

DB = TemplateDB()

#: 現実的な体型の代表例(バスト, ウエスト, ヒップ, 身長, 袖丈, 肩幅)。
BODIES = [
    ("標準M", Measurements(83, 66, 91, 158, 52, 37)),
    ("細身・小柄", Measurements(76, 60, 86, 152, 49, 35)),
    ("バスト大", Measurements(100, 80, 104, 160, 53, 38)),
    ("バスト特大", Measurements(112, 95, 115, 163, 54, 39)),
    ("胸小・肩広", Measurements(78, 64, 88, 168, 55, 41)),
    ("グラマー", Measurements(105, 72, 100, 158, 52, 36)),
]


def _fitted(part_type: str, variation: str, measurements: Measurements):
    segments = DB.get(part_type, variation)
    assert segments is not None, f"{part_type}/{variation}"
    return scale_template(part_type, variation, segments, measurements,
                           fit_anchors=DB.get_fit_anchors(part_type, variation))


def _points(scaled):
    return segments_to_polyline(scaled.segments, curve_steps=120)


def _shoulder_span_cm(scaled) -> float:
    """型紙上の肩幅(左右の肩先の水平距離)を測る。

    `_bodice_path`(scripts/generate_templates.py)の規約で輪郭の先頭点が
    左肩先なので、その点と同じyにある点の左右端の距離が肩幅になる。
    """
    points = _points(scaled)
    _sx, sy = points[0]
    xs = [x for x, y in points if abs(y - sy) < 1e-6]
    assert len(xs) >= 2
    return max(xs) - min(xs)


def _neck_width_cm(scaled) -> float:
    """首の付け根の幅(左右の首の付け根の水平距離)を測る。"""
    points = _points(scaled)
    top = min(y for _x, y in points)
    xs = [x for x, y in points if abs(y - top) < 1e-6]
    assert len(xs) >= 2
    return max(xs) - min(xs)


# --- 基準点のパース -------------------------------------------------------

def test_parse_fit_anchors_sorts_by_x_and_keeps_roles():
    anchors = parse_fit_anchors("side:45.5 cf:22.75 shoulder:4.25")
    assert anchors == [("shoulder", 4.25), ("cf", 22.75), ("side", 45.5)]


def test_parse_fit_anchors_returns_empty_for_missing_attribute():
    assert parse_fit_anchors(None) == []
    assert parse_fit_anchors("") == []


@pytest.mark.parametrize("text", ["side", "unknown:1.0", "side:abc"])
def test_parse_fit_anchors_rejects_broken_input(text):
    """壊れた指定を静かに無視しないこと。

    無視すると「基準点が無い」と判断して従来の一律スケーリングへ落ち、
    肩幅が使われない不具合が黙って復活する(それが最も避けたい失敗)。
    """
    with pytest.raises(BodiceFitError):
        parse_fit_anchors(text)


# --- テンプレート側の担保 -------------------------------------------------

def test_every_bodice_template_has_fit_anchors():
    """全身頃テンプレートが基準点を持つこと。

    1枚でも欠けると、そのバリエーションだけ静かに旧挙動(肩幅を無視)へ
    戻る。テンプレート追加時にここで気付けるようにしておく。
    """
    missing = [
        (part, variation)
        for (part, variation) in DB.available()
        if part in FIT_ANCHOR_PART_TYPES and not DB.get_fit_anchors(part, variation)
    ]
    assert missing == []


def test_bodice_templates_are_left_right_symmetric():
    """身頃の輪郭が中心前について左右対称であること。

    round14で見つけた不具合の回帰テスト。ボートネックだけ、肩線の終点が
    BODICE_NECK_HALF基準・首ぐり曲線の終点が1.75倍基準と食い違っていて、
    左の首の付け根がx=10.75、右がx=29.61という非対称な身頃になっていた
    (肩線の水平長が左6.5cm・右11.6cm)。着ると首ぐりが4cm横へずれる。
    """
    for (part, variation) in sorted(DB.available()):
        if part not in ("front_bodice", "back_bodice"):
            continue
        points = segments_to_polyline(DB.get(part, variation), curve_steps=120)
        min_x, _min_y, max_x, _max_y = bounding_box(DB.get(part, variation))
        cf = (min_x + max_x) / 2.0
        top = min(y for _x, y in points)
        xs = sorted(x for x, y in points if abs(y - top) < 1e-6)
        assert len(xs) >= 2, (part, variation)
        left, right = xs[0], xs[-1]
        assert abs((cf - left) - (right - cf)) < 0.01, (part, variation, left, right, cf)


def test_template_neck_half_matches_the_shared_formula():
    """テンプレートの首幅が engine 側の式と一致すること(二重管理の検出)。

    `scripts/generate_templates.py`は`engine.bodice_fit.neck_half_cm`を
    呼んで標準の首幅を決めている。片方だけ書き換えたら気付けるように、
    実際に生成済みのSVGの基準点から逆算して確認する。
    """
    anchors = DB.get_fit_anchors("front_bodice", "round_neck")
    cf = next(x for role, x in anchors if role == "cf")
    neck = [x for role, x in anchors if role == "neck"]
    measured = min(abs(x - cf) for x in neck)
    assert measured == pytest.approx(neck_half_cm(_STANDARD_BUST_CM), abs=0.001)


def test_standard_bust_constant_matches_measurements_module():
    assert _STANDARD_BUST_CM == STANDARD_M.bust


# --- 写像そのもの ---------------------------------------------------------

def test_map_is_identity_at_standard_measurements():
    """標準Mでは写像が恒等になること(=既存の型紙が1mmも変わらない)。"""
    for (part, variation) in sorted(DB.available()):
        if part not in FIT_ANCHOR_PART_TYPES:
            continue
        anchors = DB.get_fit_anchors(part, variation)
        rx, _ry = compute_scale_factors(STANDARD_M, part)
        knots = build_x_map(anchors, STANDARD_M.bust, STANDARD_M.shoulder_width, rx)
        for src, dst in knots:
            assert dst == pytest.approx(src, abs=0.005), (part, variation, src, dst)


def test_map_x_extrapolates_beyond_the_outermost_knots():
    """節点の外側も直線的に延長されること。

    袖ぐり曲線の制御点は脇線より外側(x<0)に出ることがあり、そこで写像が
    止まると輪郭が壊れる。
    """
    knots = [(0.0, 0.0), (10.0, 20.0)]
    assert map_x(-5.0, knots) == pytest.approx(-10.0)
    assert map_x(15.0, knots) == pytest.approx(30.0)


def test_build_x_map_rejects_incomplete_anchors():
    with pytest.raises(BodiceFitError):
        build_x_map([("side", 0.0), ("side", 45.5)], 83.0, 37.0, 1.0)


def test_remap_preserves_vertical_and_horizontal_segments():
    """脇線(縦)と裾(横)が、変形後も縦・横のままであること。

    `engine/darts.py`と`engine/compatibility.py`は「脇線はちょうど2本の
    長い縦のL」「裾は最もyが大きい横のL」という前提で位置を探すため、
    この性質が崩れると縫い代・ダーツ・整合性チェックが一斉に壊れる。
    """
    for name, m in BODIES:
        # ダーツ挿入前の、写像そのものの結果を見る(脇ダーツが入ると脇線は
        # 意図的に複数の辺へ分割されるため、ここでは変形だけを対象にする)。
        anchors = DB.get_fit_anchors("front_bodice", "round_neck")
        rx, ry = compute_scale_factors(m, "front_bodice")
        knots = build_x_map(anchors, m.bust, m.shoulder_width, rx)
        segments = remap_segments_x(DB.get("front_bodice", "round_neck"), knots, ry)
        vertical_xs, horizontal_ys = set(), set()
        cur = (0.0, 0.0)
        for cmd, nums in segments:
            if cmd in ("M", "L"):
                nxt = (nums[0], nums[1])
                if cmd == "L" and abs(nxt[0] - cur[0]) < 1e-9 and abs(nxt[1] - cur[1]) > 5.0:
                    vertical_xs.add(round(nxt[0], 6))
                if cmd == "L" and abs(nxt[1] - cur[1]) < 1e-9 and abs(nxt[0] - cur[0]) > 5.0:
                    horizontal_ys.add(round(nxt[1], 6))
                cur = nxt
            elif cmd == "C":
                cur = (nums[4], nums[5])
        assert len(vertical_xs) == 2, (name, vertical_xs)
        assert len(horizontal_ys) == 1, (name, horizontal_ys)


# --- 本題: 採寸が型紙に反映されること -------------------------------------

@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_pattern_shoulder_width_equals_the_entered_shoulder_width(name, measurements):
    """入力した肩幅が、そのまま型紙の肩幅になること。

    round13までの実測値(バスト比で一律に伸縮していたため):
      76/35 → 33.9cm(-1.1)、100/38 → 44.6cm(+6.6)、112/39 → 49.9cm(+10.9)、
      78/41 → 34.8cm(-6.2)、105/36 → 46.8cm(+10.8)
    肩幅が10cm広い型紙は、肩の縫い目が左右5cmずつ腕側へずれる。
    """
    for part in ("front_bodice", "back_bodice"):
        scaled = _fitted(part, "round_neck", measurements)
        assert _shoulder_span_cm(scaled) == pytest.approx(
            measurements.shoulder_width, abs=0.05), (name, part)


@pytest.mark.parametrize("name,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_neck_width_follows_the_neck_formula_not_the_bust_ratio(name, measurements):
    """首の開きがネック幅の式で決まること(バスト比の一律拡大ではない)。

    バスト112cmの体型では、round13までは首幅が13.7×112/83=18.5cmまで
    広がっていた。首まわりはバストほど大きくならないので首ぐりが浮く。
    """
    scaled = _fitted("front_bodice", "round_neck", measurements)
    expected = neck_half_cm(measurements.bust) * 2.0
    assert _neck_width_cm(scaled) == pytest.approx(expected, abs=0.05), name


def test_boat_neck_keeps_its_design_ratio_after_fitting():
    """デザイン上の首の開き(ボートネックは標準の1.75倍)が保たれること。

    採寸に合わせて首幅を決め直すときに、バリエーションごとの意図
    (ボートは広く開ける)を落としてしまわないことの確認。
    """
    for name, m in BODIES:
        boat = _neck_width_cm(_fitted("front_bodice", "boat_neck", m))
        rnd = _neck_width_cm(_fitted("front_bodice", "round_neck", m))
        assert boat / rnd == pytest.approx(1.75, abs=0.01), name


def test_body_girth_still_follows_bust():
    """胴回り(前+後)が引き続きバスト比で決まること。

    肩幅を独立させた副作用で胴回りがずれていないことの確認。
    テンプレートの幅(標準Mの91cm=バスト83+ゆとり8)をバスト比で伸縮する
    という round13 までの挙動をそのまま保つ。つまりゆとりの8cmも比例して
    伸縮する(バスト76なら7.3cm、バスト112なら10.8cm)。これは round14 で
    変えていない既存の設計で、ここではその不変性だけを確認する。
    """
    for name, m in BODIES:
        front = _fitted("front_bodice", "round_neck", m)
        back = _fitted("back_bodice", "round_neck", m)
        rx, _ry = compute_scale_factors(m, "front_bodice")
        expected = (STANDARD_M.bust + 8.0) * rx
        girth = front.width_cm + back.width_cm
        assert girth == pytest.approx(expected, abs=0.6), (name, girth, expected)


def test_zip_panel_keeps_a_constant_facing_width():
    """前開きパネルの見返し幅(4cm)が体型によらず一定であること。

    見返しはファスナーを付けるための固定幅なので、体型で伸縮させると
    ファスナーが収まらない。
    """
    widths = []
    for name, m in BODIES:
        anchors = DB.get_fit_anchors("front_bodice_zip_panel", "round_neck")
        rx, _ry = compute_scale_factors(m, "front_bodice_zip_panel")
        knots = build_x_map(anchors, m.bust, m.shoulder_width, rx)
        by_role = dict(zip([role for role, _x in sorted(anchors, key=lambda a: a[1])],
                            [dst for _src, dst in knots]))
        widths.append(by_role["cf"] - by_role["cut"])
    assert all(w == pytest.approx(4.0, abs=0.01) for w in widths), widths


# --- 極端な入力への振る舞いと、その開示 -----------------------------------

def test_shoulder_is_clamped_and_disclosed_for_impossible_bodies():
    """肩幅を反映できない極端な入力では、クランプした事実を開示すること。

    バスト60cm・肩幅48cmでは、身頃の半身の幅(=(60+8)/4=17cm)より肩先が
    外側に来てしまい、そのまま置くと輪郭が折り返す。黙って別の寸法を
    出さず、実際に使った値を利用者へ伝える。
    """
    m = Measurements(60, 55, 70, 150, 45, 48)
    anchors = DB.get_fit_anchors("front_bodice", "round_neck")
    note = bodice_fit_clamp_warning(anchors, m)
    assert note is not None
    assert "肩幅=48cm" in note
    scaled = _fitted("front_bodice", "round_neck", m)
    assert _shoulder_span_cm(scaled) < m.shoulder_width


def test_no_clamp_warning_for_realistic_bodies():
    """現実的な体型では開示すべきことが無い(=常に出る警告になっていない)。"""
    anchors = DB.get_fit_anchors("front_bodice", "round_neck")
    for name, m in BODIES:
        assert bodice_fit_clamp_warning(anchors, m) is None, name


def test_narrow_armhole_stays_a_valid_polygon():
    """袖ぐり幅を詰めても輪郭が自己交差しないこと(下限値の根拠の再現)。

    MIN_ARMHOLE_WIDTH_CM/MIN_SHOULDER_RUN_CM を決めるとき、袖ぐり幅を
    6.0cmから0.1cm刻みで0.2cmまで詰めながら、shapelyの自己交差判定と
    縫い代1cmのオフセットが成立するかを実測した。結果はどこでも壊れず、
    「幾何の限界」ではなく「単調性のガード」として小さな値を選んだ
    (engine/bodice_fit.pyのコメント参照)。その実測を再現する。
    """
    half = 22.75
    for part, variation in (("front_bodice", "round_neck"), ("back_bodice", "round_neck"),
                             ("front_bodice", "boat_neck"),
                             ("front_bodice_zip_panel", "round_neck")):
        anchors = DB.get_fit_anchors(part, variation)
        cf_src = next(x for role, x in anchors if role == "cf")
        width = 6.0
        while width >= 0.2:
            shoulder_half = half - width
            neck_half = min(6.858, shoulder_half - MIN_SHOULDER_RUN_CM)
            dst = {"cf": 0.0, "side": half, "shoulder": shoulder_half, "neck": neck_half}
            knots = []
            for role, x_src in anchors:
                off = x_src - cf_src
                sign = 1.0 if off >= 0 else -1.0
                knots.append((x_src, cf_src + (off if role == "cut" else sign * dst[role])))
            knots.sort()
            segments = remap_segments_x(DB.get(part, variation), knots, 1.0)
            points = segments_to_polyline(segments, curve_steps=64)
            ring = points[:-1] if points[0] == points[-1] else points
            poly = sg.Polygon(ring)
            assert poly.is_valid, (part, variation, width)
            grown = poly.buffer(1.0, join_style=2)
            assert not grown.is_empty and grown.geom_type == "Polygon", (part, variation, width)
            width = round(width - 0.1, 2)
    assert MIN_ARMHOLE_WIDTH_CM <= 1.0 and MIN_SHOULDER_RUN_CM <= 1.5


def test_armhole_curve_error_stays_within_the_documented_bound():
    """袖ぐり曲線の制御点による誤差が、文書化した上限(4%)に収まること。

    区分線形写像は制御点を「その制御点が乗っている区間の倍率」で動かす。
    袖ぐり曲線の肩先側の制御点はえぐれ量のぶん肩線側の区間へはみ出して
    いるため、理想の引き直しと数%ずれる(ARMHOLE_CURVE_NOTE参照)。
    ここではその上限を固定して、将来悪化したら気付けるようにする。
    """
    scoop, ah_depth, drop = 2.5, 23.5, 5.30

    def exact(shoulder_half, half_width, ry):
        sl = half_width - shoulder_half
        sy, ey = drop * ry, ah_depth * ry
        dy = ey - sy
        d = (f"M {sl} {sy} C {sl + scoop * 1.05} {sy + dy * 0.40},"
             f" {scoop * 1.25} {sy + dy * 0.75}, 0 {ey}")
        pts = segments_to_polyline(parse_path(d), curve_steps=64)
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))

    from engine.compatibility import armhole_length
    anchors = DB.get_fit_anchors("front_bodice", "round_neck")
    extremes = BODIES + [
        ("極端140/30", Measurements(140, 100, 110, 160, 54, 30)),
        ("極端60/50", Measurements(60, 55, 80, 160, 54, 50)),
    ]
    for name, m in extremes:
        scaled = _fitted("front_bodice", "round_neck", m)
        got = armhole_length(SimpleNamespace(
            part_type="front_bodice",
            stitch_line=segments_to_polyline(scaled.segments, curve_steps=64))) / 2.0
        rx, ry = compute_scale_factors(m, "front_bodice")
        knots = build_x_map(anchors, m.bust, m.shoulder_width, rx)
        half_width = 22.75 * rx
        shoulder_half = effective_shoulder_width_cm(
            anchors, m.bust, m.shoulder_width, rx) / 2.0
        want = exact(shoulder_half, half_width, ry)
        assert abs(got - want) / want <= ARMHOLE_CURVE_MAX_ERROR_RATIO, (name, got, want)


# --- パイプラインが実際にこの仕組みを通っていること -----------------------

def test_pipeline_actually_passes_fit_anchors(tmp_path):
    """パイプライン経由で生成した身頃の肩幅が入力どおりであること。

    `scale_template`は基準点が渡されなければ旧挙動へフォールバックする
    ので、「実装したが呼び出し側で渡し忘れている」状態を検出する。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    m = Measurements(105, 72, 100, 158, 52, 36)
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style=None)
    result = pipeline.generate_from_selection(spec, m)
    fronts = [p for p in result.scaled_parts if p.part_type == "front_bodice"]
    assert fronts
    assert _shoulder_span_cm(fronts[0]) == pytest.approx(m.shoulder_width, abs=0.05)


def test_pipeline_fits_the_sleeve_cap_to_the_measured_armhole(tmp_path):
    """袖山の長さが「袖ぐり+いせ込み(+ギャザー)」に一致すること。

    round14で袖の幅を袖ぐりに合わせるようにした本体の確認
    (engine/scaling.pyのscale_sleeve_to_cap_length)。
    """
    from engine.compatibility import (
        SLEEVE_CAP_DESIGN_GATHER_CM, SLEEVE_CAP_EASE_CM, armhole_length, sleeve_cap_length,
    )
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for name, m in BODIES:
        for style in ("straight", "puff", "bell"):
            spec = build_garment_spec(neckline="round_neck", sleeve_style=style, skirt_style=None)
            result = pipeline.generate_from_selection(spec, m)
            fronts = [p for p in result.finalized_parts if p.part_type == "front_bodice"]
            backs = [p for p in result.finalized_parts if p.part_type == "back_bodice"]
            sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
            per_arm = (sum(armhole_length(p) for p in fronts)
                       + sum(armhole_length(p) for p in backs)) / 2.0
            target = (per_arm + SLEEVE_CAP_EASE_CM
                      + SLEEVE_CAP_DESIGN_GATHER_CM.get(style, 0.0))
            for sleeve in sleeves:
                assert sleeve_cap_length(sleeve) == pytest.approx(target, abs=0.1), (name, style)


def test_sleeve_falls_back_to_measurement_scaling_without_a_bodice(tmp_path):
    """身頃を含まない構成では、袖が従来通り採寸比で作られること。

    袖だけの生成でも例外にならず型紙が出ること(フォールバック経路)。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    from engine.pipeline import GarmentSpec, PartRequest
    spec = GarmentSpec(parts=[PartRequest("sleeve", "straight", 2)])
    result = pipeline.generate_from_selection(spec, STANDARD_M)
    sleeves = [p for p in result.scaled_parts if p.part_type == "sleeve"]
    assert len(sleeves) == 2
    assert all(s.width_cm > 0 for s in sleeves)
