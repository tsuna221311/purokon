import pytest

from engine.nesting import nest_parts, best_fabric_width
from engine.seam import finalize_part
from engine.svgpath import parse_path
from engine import nesting as nesting_module


def _rect_part(name, w, h):
    segments = parse_path(f"M 0 0 L {w} 0 L {w} {h} L 0 {h} Z")
    return finalize_part(name, "", segments, seam_allowance_cm=0.5)


def test_all_parts_get_placed_when_bin_is_big_enough():
    parts = [_rect_part("a", 20, 30), _rect_part("b", 15, 40), _rect_part("c", 10, 10)]
    result = nest_parts(parts, fabric_width_cm=150.0)
    assert result.unplaced == []
    assert len(result.placed) == 3
    assert result.used_length_cm > 0
    assert 0.0 <= result.waste_ratio < 1.0


def test_placed_parts_do_not_overlap_bounding_boxes():
    parts = [_rect_part("a", 20, 30), _rect_part("b", 15, 40), _rect_part("c", 10, 10),
             _rect_part("d", 25, 25)]
    result = nest_parts(parts, fabric_width_cm=60.0)

    def overlaps(b1, b2):
        return not (b1[2] <= b2[0] or b2[2] <= b1[0] or b1[3] <= b2[1] or b2[3] <= b1[1])

    boxes = [p.bbox() for p in result.placed]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not overlaps(boxes[i], boxes[j])


def test_best_fabric_width_picks_lower_waste():
    parts = [_rect_part("a", 100, 20), _rect_part("b", 100, 20)]
    result = best_fabric_width(parts, candidates=(110.0, 150.0))
    assert result.fabric_width_cm in (110.0, 150.0)
    assert result.unplaced == []


def test_shipped_templates_are_not_exactly_square_bounding_boxes():
    # rotated判定は rect.width と元の(幅+隙間)を1e-3cmの誤差で比較する推定
    # であり、これがすり抜けるのは width_cm と height_cm が実質的に完全に
    # 一致する場合だけ（差が2cmもあれば回転後は明確にwidthの値が変わるので
    # 正しく検出できる。実際 sleeve は width≈21cm/height≈23cmで見た目には
    # 「正方形に近い」が、この2cmの差は1e-3の許容誤差より遥かに大きいため
    # 検出は機能する）。将来、幅と高さがほぼ完全一致するテンプレートが
    # 追加されないかを検出する回帰テスト。
    from engine.measurements import STANDARD_M
    from engine.pipeline import PatternForgePipeline
    from engine.scaling import scale_template

    pipeline = PatternForgePipeline()
    exactly_square = []
    for part_type, variation in pipeline.template_db.available():
        segments = pipeline.template_db.get(part_type, variation)
        scaled = scale_template(part_type, variation, segments, STANDARD_M)
        part = _rect_part_from_segments(part_type, variation, scaled.segments)
        if part.width_cm and part.height_cm and abs(part.width_cm - part.height_cm) < 0.01:
            exactly_square.append((part_type, variation, part.width_cm, part.height_cm))
    assert exactly_square == [], (
        f"幅と高さがほぼ完全一致する型紙が見つかった(回転検出の既知の限界に該当): {exactly_square}"
    )


def _rect_part_from_segments(part_type, variation, segments):
    from engine.seam import finalize_part
    return finalize_part(part_type, variation, segments, seam_allowance_cm=0.5)


# ---------------------------------------------------------------------------
# 圧縮パス(_compact_placement, 本格的な不定形ネスティングの代替)のテスト
# ---------------------------------------------------------------------------

def _shapely_polygon(cut_line):
    from shapely.geometry import Polygon
    pts = cut_line[:-1] if cut_line and cut_line[0] == cut_line[-1] else cut_line
    return Polygon(pts)


def _assert_no_real_overlap(placed):
    """bboxではなく実ポリゴン(縫い代込みの裁断線)同士が重なっていないことを
    確認する。180度反転で詰め直した後は、bboxが重ならないだけでは不十分。"""
    polys = [_shapely_polygon(p.placed_cut_line()) for p in placed]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            overlap = polys[i].buffer(-1e-6).intersection(polys[j].buffer(-1e-6))
            assert overlap.area < 1e-6, f"parts {i} and {j} overlap by {overlap.area}cm^2"


def test_compaction_never_increases_waste_or_used_length():
    from engine.measurements import STANDARD_M
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline()
    specs = [
        build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare"),
        build_garment_spec(neckline="v_neck", sleeve_style="curve", skirt_style="tight",
                            include_collar=True, include_cuffs=True, include_waistband=True),
        build_garment_spec(neckline="turtle_neck", sleeve_style=None, skirt_style=None,
                            include_pants=True),
    ]
    for spec in specs:
        original_compact = nesting_module._compact_placement
        try:
            # round38: `_compact_placement`に allow_flip(一方方向の生地では
            # 180度反転を使わない)が増えたので、差し替え側も受け取る。
            nesting_module._compact_placement = (
                lambda result, seam_gap_cm, allow_flip=True: result)
            # round48: skip_export=True を付けた。このテストは配置の指標
            # (布ロス率・使用長・枚数)しか見ていないのに、SVG/PDF/DXFを
            # 既定の出力先 `generated/`——**リポジトリの中**——へ書いていた。
            # 6回分で6.4MBが作業ツリーに残り、.gitignore されているので
            # 気づかないまま溜まり続けていた(round48で実測)。
            before = pipeline.generate_from_selection(spec, STANDARD_M,
                                                      skip_export=True)
        finally:
            nesting_module._compact_placement = original_compact
        after = pipeline.generate_from_selection(spec, STANDARD_M,
                                                 skip_export=True)

        assert after.nesting.waste_ratio <= before.nesting.waste_ratio + 1e-6
        assert after.nesting.used_length_cm <= before.nesting.used_length_cm + 1e-6
        assert len(after.nesting.placed) == len(before.nesting.placed)
        assert after.nesting.unplaced == before.nesting.unplaced
        _assert_no_real_overlap(after.nesting.placed)


def test_compaction_can_flip_a_part_180_degrees_to_interlock():
    """180度反転の仕組みそのものが健在であること。ただし**得はしていない**。

    台形のパーツ2枚を横に並べるとき、片方を180度反転させると実ポリゴンが
    より深く噛み合う——外接矩形どうしを隣接させるだけでは再現できない挙動で、
    round11で入れた機能である。

    【round12でケースを取り直した】以前はフレアスカート2枚・生地幅150cmで
    固定していたが、round12でスカートの寸法を実寸に作り直した結果、
    フレアスカートは裾80cmと大きくなり、150cm幅には2枚横に並ばず縦積みに
    なるため反転が不要になった。横に2枚並ぶタイトスカートに差し替えた。

    【round38で分かったこと】この「見せ場」のケースで、反転あり/なしを
    実際に測ってみた:

        反転あり: 丈62.0cm ロス34.0% (1枚反転)
        反転なし: 丈62.0cm ロス34.0%

    **まったく同じだった。** 反転は起きているが、配置の見た目が変わるだけで
    生地は1mmも節約していない。171通りの実測でも平均+0.032cm・最大+0.60cm
    しか差が無く、この機能は「効いているように見えて、ほぼ何も生んでいない」。

    一方で反転は、起毛・別珍・コーデュロイでは毛の向きを逆にし、片方向
    プリントでは絵柄を逆さまにする。そこでround38から、反転は
    「非方向性の生地」を選んだときだけ使うようにした(既定では反転しない)。

    このテストは、仕組みが壊れていないことを`_compact_placement`を直接
    呼んで確かめる。`nest_parts(allow_rotation=True)`経由では、rectpackが
    先に90度回転を選び、圧縮パスは回転済みパーツを対象外にするため、
    反転が起きない——**機能を確かめたいのに経路の都合で確かめられない**ので、
    ここは仕組みを直接呼ぶ。
    """
    from itertools import product

    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template
    from engine.measurements import STANDARD_M
    from engine.nesting import (
        _pack_once, _compact_placement, _best_of,
        _PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES, DEFAULT_SEAM_GAP_CM,
    )

    db = TemplateDB()
    segments = db.get("skirt", "tight")
    scaled = scale_template("skirt", "tight", segments, STANDARD_M)
    front = finalize_part("skirt", "tight", scaled.segments, label_suffix="前")
    back = finalize_part("skirt", "tight", scaled.segments, label_suffix="後")

    candidates = [
        _pack_once([front, back], 150.0, DEFAULT_SEAM_GAP_CM, False, pa, sa)
        for pa, sa in product(_PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES)
    ]
    best = _best_of(candidates, key=lambda r: r.waste_ratio)

    flipped = _compact_placement(best, DEFAULT_SEAM_GAP_CM, allow_flip=True)
    assert flipped.unplaced == []
    assert any(p.flipped for p in flipped.placed), "反転の仕組みが動いていない"
    _assert_no_real_overlap(flipped.placed)

    not_flipped = _compact_placement(best, DEFAULT_SEAM_GAP_CM, allow_flip=False)
    assert not any(p.flipped for p in not_flipped.placed)
    _assert_no_real_overlap(not_flipped.placed)

    # 得はしていない、という実測を固定する。ここが将来変わったら
    # (反転が本当に生地を節約するようになったら)、既定を見直す価値がある。
    assert flipped.used_length_cm == pytest.approx(not_flipped.used_length_cm)

    # 既定(布目安全モード)では反転しないこと
    safe = nest_parts([front, back], fabric_width_cm=150.0)
    assert not any(p.flipped for p in safe.placed)


def test_compaction_skips_gracefully_for_many_parts():
    # 圧縮対象パーツ数の上限(_COMPACTION_MAX_PARTS)を超える場合は、
    # 素のbbox配置をそのまま返す(処理時間の暴走防止)。壊れずに動くことだけ確認。
    parts = [_rect_part(f"p{i}", 10, 10) for i in range(nesting_module._COMPACTION_MAX_PARTS + 2)]
    result = nest_parts(parts, fabric_width_cm=150.0)
    assert len(result.placed) + len(result.unplaced) == len(parts)


# --- round5「ネスティングの改善」: 反復+複数処理順への拡張 -------------------


def test_position_order_and_largest_area_first_order_are_both_valid_permutations():
    placed_parts = [
        _rect_part(f"p{i}", w, h)
        for i, (w, h) in enumerate([(10, 10), (30, 5), (5, 30), (15, 15)])
    ]
    # NestedPartでラップして座標を与える(値自体は順序判定に関係無い)。
    from engine.nesting import NestedPart
    placed = [NestedPart(part=p, x=float(i), y=float(i), rotated=False) for i, p in enumerate(placed_parts)]

    for order_fn in (nesting_module._position_order, nesting_module._largest_area_first_order):
        order = order_fn(placed)
        assert sorted(order) == list(range(len(placed)))  # 全indexをちょうど1回ずつ含む置換である


def test_largest_area_first_order_actually_sorts_by_area_descending():
    from engine.nesting import NestedPart
    small = _rect_part("small", 5, 5)     # 25cm^2
    large = _rect_part("large", 20, 20)   # 400cm^2
    medium = _rect_part("medium", 10, 10)  # 100cm^2
    placed = [
        NestedPart(part=small, x=0.0, y=0.0, rotated=False),
        NestedPart(part=large, x=0.0, y=0.0, rotated=False),
        NestedPart(part=medium, x=0.0, y=0.0, rotated=False),
    ]
    order = nesting_module._largest_area_first_order(placed)
    assert order == [1, 2, 0]  # large(index1) > medium(index2) > small(index0)


def test_compact_repeatedly_never_regresses_versus_a_single_pass():
    # `_compact_repeatedly`は`_compact_once`をfail-safeなまま繰り返すだけ
    # なので、1回のパスより悪化することは無いはず。
    from engine.nesting import (
        _pack_once, _compact_once, _compact_repeatedly, _position_order,
        _PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES, _best_of,
    )
    from itertools import product

    parts = [_rect_part(f"p{i}", w, h) for i, (w, h) in
              enumerate([(20, 30), (15, 40), (25, 10), (10, 50), (30, 20), (12, 35)])]
    candidates = [
        _pack_once(parts, 110.0, 0.3, False, algo, sort)
        for algo, sort in product(_PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES)
    ]
    best = _best_of(candidates, key=lambda r: r.waste_ratio)

    single = _compact_once(best, 0.3)
    repeated = _compact_repeatedly(best, 0.3, _position_order)

    assert repeated.waste_ratio <= single.waste_ratio + 1e-9
    assert repeated.used_length_cm <= single.used_length_cm + 1e-9


def test_iterative_and_multi_order_compaction_rarely_beats_a_single_pass():
    """正直な実測の回帰テスト（`_compact_placement`のdocstring参照）。

    このテストの目的は「劇的に改善する」ことを証明するのではなく、
    round5で追加した反復+複数処理順の拡張が、単発の圧縮パスに対して
    (a) 絶対に悪化しないこと、(b) 実際に何らかの改善が見つかる場合でも
    ごくわずか(1ポイント未満)であることの両方を、実際の標準M寸テンプレート
    を使って固定することにある。「改善が無い」という結果自体も、この
    拡張の効果を過大に謳わないための正直な記録として重要な回帰対象。
    """
    from engine.measurements import STANDARD_M
    from engine.pipeline import build_garment_spec
    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template
    from engine.nesting import (
        _pack_once, _compact_once, _compact_placement,
        _PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES, _best_of,
    )
    from itertools import product

    db = TemplateDB()

    def _build_parts(spec):
        built = []
        for req in spec.parts:
            segs = db.get(req.part_type, req.variation)
            scaled = scale_template(req.part_type, req.variation, segs, STANDARD_M)
            for _ in range(max(1, req.quantity)):
                built.append(finalize_part(req.part_type, req.variation, scaled.segments,
                                            dart_count=scaled.dart_count))
        return built

    specs = [
        build_garment_spec(neckline="round_neck", sleeve_style="straight", skirt_style="flare"),
        build_garment_spec(neckline="v_neck", sleeve_style="curve", skirt_style="tight",
                            include_collar=True, include_cuffs=True, include_waistband=True),
        build_garment_spec(neckline="turtle_neck", sleeve_style=None, skirt_style=None,
                            include_pants=True),
    ]

    for spec in specs:
        parts = _build_parts(spec)
        for width in (110.0, 150.0):
            candidates = [
                _pack_once(parts, width, 0.3, False, algo, sort)
                for algo, sort in product(_PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES)
            ]
            best = _best_of(candidates, key=lambda r: r.waste_ratio)
            single = _compact_once(best, 0.3)
            new = _compact_placement(best, 0.3)

            # (a) 絶対に悪化しない
            assert new.waste_ratio <= single.waste_ratio + 1e-9
            # (b) 改善するとしても1ポイント未満(誇張した効果を主張しない)
            assert single.waste_ratio - new.waste_ratio < 0.01


def test_round6_expanded_sort_candidates_fix_a_previously_badly_packed_case():
    """round6の回帰テスト: 前開きファスナー+袖の組み合わせで、round5までの
    並べ替え候補(SORT_AREA/SORT_PERI)だけでは本来1段に収まるはずの配置を
    見つけられず、不要な2段構成で布ロス率が約0.60まで悪化していた実例
    (engine/nesting.pyの`_SORT_ALGO_CANDIDATES`docstring参照)。

    round6でSORT_DIFF/SORT_SSIDE/SORT_LSIDE/SORT_RATIO/SORT_NONEを追加した
    結果、同じ構成で布ロス率が0.25未満まで改善することを固定する。
    """
    from engine.measurements import STANDARD_M
    from engine.pipeline import build_garment_spec
    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template
    from engine.nesting import best_fabric_width, DEFAULT_FABRIC_WIDTHS_CM

    db = TemplateDB()
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                               skirt_style=None, front_zip=True)
    parts = []
    for req in spec.parts:
        segs = db.get(req.part_type, req.variation)
        scaled = scale_template(req.part_type, req.variation, segs, STANDARD_M)
        for _ in range(max(1, req.quantity)):
            parts.append(finalize_part(req.part_type, req.variation, scaled.segments,
                                        dart_count=scaled.dart_count))

    result = best_fabric_width(parts, candidates=DEFAULT_FABRIC_WIDTHS_CM)
    assert result.unplaced == []
    assert result.waste_ratio < 0.25


def test_sort_algo_candidates_include_more_than_the_round5_baseline():
    """`_SORT_ALGO_CANDIDATES`が、round5時点のSORT_AREA/SORT_PERIの2種類だけ
    に戻っていないことを確認する回帰テスト(意図しない縮退防止)。
    """
    from rectpack import SORT_AREA, SORT_PERI

    assert len(nesting_module._SORT_ALGO_CANDIDATES) > 2
    assert SORT_AREA in nesting_module._SORT_ALGO_CANDIDATES
    assert SORT_PERI in nesting_module._SORT_ALGO_CANDIDATES


def test_round7_expanded_pack_candidates_fix_a_previously_badly_packed_case():
    """round7の回帰テスト(3回目のネスティング再調査)。

    round6までの詰め込み候補(pack_algo)は3種類だけで、組み合わせによっては
    布ロス率が下がりきらない実例があった。round7で MaxRectsBl・MaxRectsBaf・
    SkylineMwfl の3種類を追加してこれを解消した。

    【round12でテストの書き方を2度変えた】当初は「布ロス率 < 0.21」という
    絶対値のしきい値で固定していたが、これはテンプレートの寸法に依存する値で、
    寸法を作り直すたびに(改良自体は有効なままなのに)落ちた。次に特定の1構成
    での比較に変えたが、これも寸法変更で「その構成では差が出ない」状態になり
    再び落ちた。テストの意図は「追加した候補が実際に効いていること」なので、
    複数の構成を走査して『どれかで改善し、どこでも悪化しない』を確認する形に
    改めた。これならテンプレートの寸法が変わっても意図を保てる。
    """
    import itertools

    from engine.measurements import Measurements, STANDARD_M
    from engine.pipeline import build_garment_spec
    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template
    from engine.nesting import _pack_once, _best_of, _SORT_ALGO_CANDIDATES, DEFAULT_SEAM_GAP_CM
    from rectpack import GuillotineBssfSas, GuillotineBafSas, MaxRectsBssf
    from itertools import product

    round6_algos = (GuillotineBssfSas, GuillotineBafSas, MaxRectsBssf)
    db = TemplateDB()
    bodies = (STANDARD_M,
              Measurements(bust=100, waist=80, hip=100, height=165,
                            sleeve_length=55, shoulder_width=40))

    def _build(spec, m):
        parts = []
        for req in spec.parts:
            segs = db.get(req.part_type, req.variation)
            scaled = scale_template(req.part_type, req.variation, segs, m)
            for _ in range(max(1, req.quantity)):
                parts.append(finalize_part(req.part_type, req.variation, scaled.segments,
                                            dart_count=scaled.dart_count))
        return parts

    def _best_with(parts, algos, width):
        candidates = [
            _pack_once(parts, width, DEFAULT_SEAM_GAP_CM, False, algo, sort)
            for algo, sort in product(algos, _SORT_ALGO_CANDIDATES)
        ]
        return _best_of(candidates, key=lambda r: r.waste_ratio)

    improved_cases = 0
    for m, sleeve, skirt, pants in itertools.product(
            bodies, (None, "straight", "puff"), (None, "flare", "tight"), (False, True)):
        spec = build_garment_spec(neckline="round_neck", sleeve_style=sleeve,
                                   skirt_style=skirt, include_pants=pants)
        parts = _build(spec, m)
        for width in (110.0, 140.0, 150.0):
            old = _best_with(parts, round6_algos, width)
            new = _best_with(parts, nesting_module._PACK_ALGO_CANDIDATES, width)
            # 候補を増やして悪化することは原理的に無い(_best_ofの設計)。
            assert new.waste_ratio <= old.waste_ratio + 1e-9
            if old.waste_ratio - new.waste_ratio > 1e-6:
                improved_cases += 1
    assert improved_cases > 0, "round7で追加した候補が、どの構成でも効いていない"


def test_pack_algo_candidates_include_more_than_the_round6_baseline():
    """`_PACK_ALGO_CANDIDATES`が、round6時点の3種類だけに戻っていないことを
    確認する回帰テスト(意図しない縮退防止)。
    """
    from rectpack import (
        GuillotineBssfSas, GuillotineBafSas, MaxRectsBssf,
        MaxRectsBl, MaxRectsBaf, SkylineMwfl,
    )

    assert len(nesting_module._PACK_ALGO_CANDIDATES) > 3
    for algo in (GuillotineBssfSas, GuillotineBafSas, MaxRectsBssf,
                 MaxRectsBl, MaxRectsBaf, SkylineMwfl):
        assert algo in nesting_module._PACK_ALGO_CANDIDATES


# --- round11: 生地幅候補への140cm追加 --------------------------------------

def test_default_fabric_widths_include_140cm():
    """round11で追加した140cm候補が既定のまま残っていることの回帰テスト
    (意図しない縮退防止。DEFAULT_FABRIC_WIDTHS_CMのdocstring参照)。
    """
    from engine.nesting import DEFAULT_FABRIC_WIDTHS_CM

    assert 110.0 in DEFAULT_FABRIC_WIDTHS_CM
    assert 140.0 in DEFAULT_FABRIC_WIDTHS_CM
    assert 150.0 in DEFAULT_FABRIC_WIDTHS_CM


def test_140cm_fabric_width_strictly_beats_110_and_150_for_a_mid_width_case():
    """140cm候補が、110/150だけでは損をするケースで実際に良い結果を選べる
    ことを確認する(絵に描いた改善ではなく実測)。

    幅68cmのパーツを2枚横並びにすると合計約136.3cm(隙間込み)になり、
    110cm幅には収まらず2段組みになって丈が倍近く必要になる一方、150cm幅
    には収まるが13.6cm分の余白が生地幅方向に無駄になる。140cm幅ならほぼ
    ぴったり収まり、150cm幅より無駄が大幅に少なくなるはず。
    """
    parts = [_rect_part("a", 68, 100), _rect_part("b", 68, 100)]

    result_110 = nest_parts(parts, fabric_width_cm=110.0)
    result_140 = nest_parts(parts, fabric_width_cm=140.0)
    result_150 = nest_parts(parts, fabric_width_cm=150.0)
    assert result_110.unplaced == result_140.unplaced == result_150.unplaced == []

    # 140cmは150cmより明確に布ロス率が低い(生地幅方向の無駄が少ないため)。
    assert result_140.waste_ratio < result_150.waste_ratio - 0.02
    # 110cmは横に並べきれず2段組みになるため、140cmより明確に悪い。
    assert result_140.waste_ratio < result_110.waste_ratio - 0.1

    best = best_fabric_width(parts, candidates=(110.0, 140.0, 150.0))
    assert best.fabric_width_cm == 140.0
    # 従来通り110/150の2択しか試さなければ、この改善は見つからない。
    best_without_140 = best_fabric_width(parts, candidates=(110.0, 150.0))
    assert best.waste_ratio < best_without_140.waste_ratio - 0.02


def test_adding_a_fabric_width_candidate_never_makes_the_result_worse():
    """候補を増やしても悪化しないこと(`_best_of`の設計上の保証)を、実際の
    衣装スペックで確認する。round11で140cmを追加する前に、この性質を
    72通りの組み合わせで実測して確認した際の代表ケースを固定する。
    """
    from engine.measurements import STANDARD_M
    from engine.pipeline import build_garment_spec
    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template

    db = TemplateDB()
    for kwargs in (
        dict(neckline="round_neck", sleeve_style="bell", skirt_style="tight"),
        dict(neckline="v_neck", sleeve_style="straight", skirt_style="flare"),
        dict(neckline="round_neck", sleeve_style=None, skirt_style=None, include_pants=True),
    ):
        spec = build_garment_spec(**kwargs)
        parts = []
        for req in spec.parts:
            segs = db.get(req.part_type, req.variation)
            scaled = scale_template(req.part_type, req.variation, segs, STANDARD_M)
            for _ in range(max(1, req.quantity)):
                parts.append(finalize_part(req.part_type, req.variation, scaled.segments,
                                            dart_count=scaled.dart_count))
        old = best_fabric_width(parts, candidates=(110.0, 150.0))
        new = best_fabric_width(parts, candidates=(110.0, 140.0, 150.0))
        assert new.waste_ratio <= old.waste_ratio + 1e-9, kwargs


# --- round11: 圧縮対象を「圧縮前に同点だった候補」まで広げた改良 -------------

def _old_style_single_best_compaction(parts, fabric_width_cm, allow_rotation=False):
    """round10までの実装(圧縮前1位の候補1件だけを圧縮する版)を再現する
    ヘルパー。round11の新実装との比較用。

    【round38】180度反転の使用条件が`allow_rotation`に連動するようになった
    ので、参照側も同じ条件で回す。ここが食い違うと、比べたいのは
    「圧縮を何件に適用するか」なのに、反転の有無の差を見てしまう。
    """
    from itertools import product
    from engine.nesting import (
        _pack_once, _compact_placement, _best_of,
        _PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES, DEFAULT_SEAM_GAP_CM,
    )

    candidates = [
        _pack_once(parts, fabric_width_cm, DEFAULT_SEAM_GAP_CM, allow_rotation,
                    pack_algo, sort_algo)
        for pack_algo, sort_algo in product(_PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES)
    ]
    best = _best_of(candidates, key=lambda r: r.waste_ratio)
    return _compact_placement(best, DEFAULT_SEAM_GAP_CM,
                               allow_flip=allow_rotation)


def _build_finalized_parts(measurements=None, **spec_kwargs):
    from engine.measurements import STANDARD_M
    from engine.pipeline import build_garment_spec
    from engine.templates_db import TemplateDB
    from engine.scaling import scale_template

    m = measurements or STANDARD_M
    db = TemplateDB()
    spec = build_garment_spec(**spec_kwargs)
    parts = []
    for req in spec.parts:
        segs = db.get(req.part_type, req.variation)
        scaled = scale_template(req.part_type, req.variation, segs, m)
        for _ in range(max(1, req.quantity)):
            parts.append(finalize_part(req.part_type, req.variation, scaled.segments,
                                        dart_count=scaled.dart_count))
    return parts


@pytest.mark.parametrize("spec_kwargs,fabric_width", [
    (dict(neckline="v_neck", sleeve_style="cap", skirt_style="flare"), 140.0),
    (dict(neckline="round_neck", sleeve_style="straight", skirt_style=None), 110.0),
    (dict(neckline="turtle_neck", sleeve_style="bell", skirt_style="pleated"), 110.0),
    (dict(neckline="round_neck", sleeve_style=None, skirt_style="tight", include_pants=True), 150.0),
])
def test_nest_parts_matches_the_single_best_compaction_reference(spec_kwargs, fabric_width):
    """`nest_parts`の結果が、「圧縮前の最良候補1件だけを圧縮する」という
    参照実装と一致すること(round12で同点候補の圧縮を撤回した後の仕様)。
    """
    parts = _build_finalized_parts(**spec_kwargs)
    reference = _old_style_single_best_compaction(parts, fabric_width)
    actual = nest_parts(parts, fabric_width_cm=fabric_width)
    assert actual.waste_ratio == pytest.approx(reference.waste_ratio)


def test_compaction_applies_to_the_single_best_candidate_only():
    """round12で撤回した改良が、意図せず元に戻っていないことの記録テスト。

    round11では「圧縮前の成績が同点の候補もまとめて圧縮する」改良を入れて
    いたが、round12でテンプレートの寸法を正した結果、効果が最大0.43ポイント・
    中央値0.17ポイントまで落ちる一方でネスティングの処理時間は約2倍のまま
    であることが分かり撤回した(経緯はengine/nesting.pyのモジュール
    docstring【round12での撤回】参照)。

    実装が「圧縮前の最良候補1件だけを圧縮する」に戻っていることを、
    参照実装と結果が完全一致することで確認する。
    """
    parts = _build_finalized_parts(neckline="boat_neck", sleeve_style="puff",
                                    skirt_style="wrap", include_pants=True)
    for fabric_width in (110.0, 140.0, 150.0):
        reference = _old_style_single_best_compaction(parts, fabric_width)
        actual = nest_parts(parts, fabric_width_cm=fabric_width)
        assert actual.waste_ratio == pytest.approx(reference.waste_ratio), fabric_width
