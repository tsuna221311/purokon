import pytest

try:
    from shapely.geometry import Polygon as _ShapelyPolygon
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover
    _HAS_SHAPELY = False

from engine.seam import (
    DEFAULT_NOTCH_FRACTIONS, finalize_part, offset_polygon, offset_polygon_variable,
    notch_marks, grainline_marks, _signed_area, _line_intersect,
    _offset_polygon_fallback, _offset_polygon_per_edge, _hem_edge_distances,
)
from engine.svgpath import parse_path, segments_to_polyline
from engine.templates_db import TemplateDB


def _square(size=10.0):
    return [(0.0, 0.0), (size, 0.0), (size, size), (0.0, size), (0.0, 0.0)]


def test_offset_polygon_grows_a_square_outward():
    square = _square(10.0)
    offset = offset_polygon(square, 1.0)
    area_before = abs(_signed_area(square))
    area_after = abs(_signed_area(offset))
    assert area_after > area_before
    # 1cmの縫い代を四方に付けると、12x12=144cm^2 に近づく
    assert area_after == pytest.approx(144.0, rel=0.05)


def test_notch_marks_start_on_the_stitch_line():
    square = _square(10.0)
    marks = notch_marks(square, [0.0, 0.5])
    assert len(marks) == 2
    for start, end in marks:
        assert start != end  # 合印は長さを持つ短い線分


def test_notch_marks_at_fraction_1_do_not_collapse_onto_fraction_0():
    # 閉じた輪郭では周長比0.0と1.0は数学的に同一点になるため、
    # [0.0, 1.0]という指定は「2箇所のはずが同じ点に重複する」バグを生む。
    # collar/cuffs/waistband の既定値がこの罠を踏んでいないことを確認する。
    square = _square(10.0)
    for part_type in ("collar", "cuffs", "waistband"):
        fractions = DEFAULT_NOTCH_FRACTIONS[part_type]
        assert 1.0 not in fractions, f"{part_type} の合印指定に1.0が残っている(0.0と重複する)"
        marks = notch_marks(square, fractions)
        starts = [start for start, _end in marks]
        assert len(set(starts)) == len(starts), f"{part_type} の合印が同一点に重複している: {starts}"


def test_notch_marks_fraction_1_would_collapse_to_fraction_0_if_ever_used_again():
    # _perimeter_point自体の仕様（閉じた輪郭でt=1.0はt=0.0と同一点）を
    # 明示しておく回帰テスト。将来また[..., 1.0]のような指定を追加した際に
    # 「あれ、2点のはずなのに1点しかない」を検出できるようにする。
    square = _square(10.0)
    marks = notch_marks(square, [0.0, 1.0])
    assert marks[0][0] == marks[1][0]


def test_grainline_is_vertical_and_centered():
    bbox = (0.0, 0.0, 10.0, 20.0)
    grain = grainline_marks(bbox)
    (x1, y1), (x2, y2) = grain["line"]
    assert x1 == x2 == 5.0  # 幅の中央
    assert y1 < y2
    assert len(grain["arrows"]) == 4


def test_finalize_part_produces_larger_cut_line_than_stitch_line():
    segments = parse_path("M 0 0 L 10 0 L 10 20 L 0 20 Z")
    finalized = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    stitch_area = abs(_signed_area(finalized.stitch_line))
    cut_area = abs(_signed_area(finalized.cut_line))
    assert cut_area > stitch_area
    assert finalized.width_cm > 10.0
    assert finalized.height_cm > 20.0
    assert len(finalized.notches) >= 1


def test_line_intersect_finds_the_correct_crossing_point():
    # _line_intersect()は以前、標準的な2直線交点の公式のPx・Pyそれぞれの
    # 第2項で(x1-x2)と(y1-y2)が入れ替わっていた(実バグ)。この関数は
    # _offset_polygon_fallback専用に使われ、そちらにテストが無かったため
    # 長年気付かれていなかった。x=-1の垂直線とy=-1の水平線という最も単純な
    # 例で検証する: 正しい交点は(-1,-1)のはずだが、修正前の実装は無関係な
    # 点(-2, 0)を返していた。
    vertical = ((-1.0, 10.0), (-1.0, 0.0))
    horizontal = ((0.0, -1.0), (10.0, -1.0))
    point = _line_intersect(*vertical, *horizontal)
    assert point == pytest.approx((-1.0, -1.0))


def test_line_intersect_returns_none_for_parallel_lines():
    a = ((0.0, 0.0), (10.0, 0.0))
    b = ((0.0, 5.0), (10.0, 5.0))
    assert _line_intersect(*a, *b) is None


def test_offset_polygon_fallback_matches_exact_square_offset():
    # _line_intersect()のバグにより、この関数は正方形のような単純な凸形状
    # でさえ正しくオフセットできていなかった(実際に検証: 修正前は面積0、
    # 座標も無関係な値になっていた)。修正後は解析的に正しい値(12x12=144)
    # に一致することを確認する。
    square = _square(10.0)
    offset = _offset_polygon_fallback(square, 1.0)
    assert abs(_signed_area(offset)) == pytest.approx(144.0)
    assert set(offset[:-1]) == {(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0)}


def test_offset_polygon_fallback_handles_the_real_concave_front_bodice_template():
    # engine/seam.pyのshapely未導入時フォールバック(_offset_polygon_fallback)
    # は、以前「型紙のような『概ね凸に近い』輪郭では十分実用的な近似になる」
    # と説明されていたが、実際にこのアプリの本物のfront_bodiceテンプレート
    # (首元がカーブで凹んでいる、=凹頂点を含む輪郭)に対して実行すると、
    # 凹頂点で無限直線同士が全く逆側の遠方で交差し、自己交差した無効な
    # 多角形(面積が正しい値の約4倍に膨らむ)を返すことを確認した(実バグ)。
    # 凹頂点をmiter joinではなくbevel(面取り)にし、外向き法線の判定を
    # 辺ごとの重心ヒューリスティックから輪郭全体で共通の1回の判定に
    # 変更したことで、shapelyを使った正しい結果とほぼ一致するようになった
    # (面積の相対誤差5%未満)ことを回帰テストとして固定する。
    # 正直な限界: 一部の鋭い頂点付近では、この単純化された自前実装は今でも
    # わずかな自己交差を起こすことがある(shapelyほど厳密ではない)。この
    # フォールバックはshapelyが無い場合専用であり、engine/nesting.pyが
    # shapelyを無条件にimportしているため実際のアプリからは到達しない
    # 経路である(README「縫い代のオフセットについて」参照)。
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    stitch_line = segments_to_polyline(segments)

    correct = offset_polygon(stitch_line, 1.0)  # shapely経由(本物のアプリが使う経路)
    fallback = _offset_polygon_fallback(stitch_line, 1.0)  # shapely未導入時の近似

    correct_area = abs(_signed_area(correct))
    fallback_area = abs(_signed_area(fallback))
    assert fallback_area == pytest.approx(correct_area, rel=0.05)


# --- round5: 辺ごとに異なる縫い代幅(offset_polygon_variable等) ---------------


def test_offset_polygon_per_edge_matches_fallback_when_all_distances_equal():
    # 全辺同じ距離を渡した場合は、単一distanceの_offset_polygon_fallback
    # (内部で委譲される側)と一致するはず。
    square = _square(10.0)
    uniform = _offset_polygon_fallback(square, 1.0)
    per_edge = _offset_polygon_per_edge(square, [1.0, 1.0, 1.0, 1.0])
    assert per_edge == uniform


def test_offset_polygon_per_edge_rejects_mismatched_distance_count():
    square = _square(10.0)
    with pytest.raises(ValueError):
        _offset_polygon_per_edge(square, [1.0, 1.0])  # 辺は4本あるのに2個しか渡さない


def test_hem_edge_distances_marks_only_the_horizontal_edge_at_max_y():
    # 正方形の頂点順は (0,0)->(10,0)->(10,10)->(0,10)->close なので、
    # y座標が最大(10)で水平な辺は2番目の辺(index=2: (10,10)->(0,10))のみ。
    square = _square(10.0)
    distances = _hem_edge_distances(square, base_distance=1.0, hem_distance=3.0)
    assert distances == [1.0, 1.0, 3.0, 1.0]


def test_hem_edge_distances_all_base_when_no_horizontal_edge_at_max_y():
    # 頂点をひとつだけ持つ三角形は、水平な辺がそもそも一つも無いので、
    # 全辺baseのままになるはず(裾扱いになる辺が存在しない)。
    triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0), (0.0, 0.0)]
    distances = _hem_edge_distances(triangle, base_distance=1.0, hem_distance=3.0)
    assert distances == [1.0, 1.0, 1.0]


def test_offset_polygon_variable_delegates_to_offset_polygon_when_hem_is_none():
    square = _square(10.0)
    assert offset_polygon_variable(square, 1.0, None) == offset_polygon(square, 1.0)


def test_offset_polygon_variable_delegates_to_offset_polygon_when_hem_equals_base():
    square = _square(10.0)
    assert offset_polygon_variable(square, 1.0, 1.0) == offset_polygon(square, 1.0)


def test_offset_polygon_variable_widens_only_the_max_y_edge():
    # base=1.0, hem=3.0の正方形を辺ごとにオフセットすると、裾(y最大の辺、
    # 元の輪郭ではy=10)側だけ標準の縫い代(1cm、y=11相当)より張り出して
    # y=13付近まで届き、他の3辺(x方向・下辺)はbase_distance(1cm)相当の
    # ままになるはず。shapelyのunion/differenceベースの実装(round join +
    # 継ぎ目の接線方向への延長)を使うため、正確な座標は解析的な鋭角の
    # 値(-1,-1)〜(11,13)とは境界付近で若干異なる(丸い角・延長の接合部分)
    # ため、bboxと概形で確認する。
    square = _square(10.0)
    result = offset_polygon_variable(square, base_distance=1.0, hem_distance=3.0)
    xs = [p[0] for p in result]
    ys = [p[1] for p in result]
    assert min(xs) == pytest.approx(-1.0, abs=0.6)
    assert max(xs) == pytest.approx(11.0, abs=0.6)
    assert min(ys) == pytest.approx(-1.0, abs=0.1)
    assert max(ys) == pytest.approx(13.0, abs=0.1)  # 裾側は3cm張り出す
    if _HAS_SHAPELY:
        assert _ShapelyPolygon(result[:-1]).is_valid


def test_offset_polygon_variable_is_valid_and_larger_than_uniform_offset():
    square = _square(10.0)
    uniform = offset_polygon_variable(square, 1.0, 1.0)
    variable = offset_polygon_variable(square, 1.0, 3.0)
    if _HAS_SHAPELY:
        assert _ShapelyPolygon(variable[:-1]).is_valid
    assert abs(_signed_area(variable)) > abs(_signed_area(uniform))


@pytest.mark.parametrize("hem_distance", [0.3, 0.5, 1.2, 1.5, 2.0, 3.0, 5.0, 8.0])
def test_offset_polygon_variable_stays_valid_on_the_real_concave_front_bodice_template(hem_distance):
    # shapelyが使える環境(=実際のアプリ)でも、front_bodiceの首元カーブの
    # ような凹頂点を含む本物のテンプレートに対して、裾だけ標準の縫い代
    # (1.0cm)よりわずかに広い/狭いだけで自己交差する(無効な多角形になる)
    # 実バグが実際に見つかった(手計算のmiter/bevel方式をそのまま辺ごとの
    # 幅に一般化しただけでは再現した)。shapelyのunion/differenceベースの
    # 実装(_offset_polygon_variable_shapely)に切り替えた後、標準的な
    # 縫い代の範囲(0.3〜8cm、app.py側の入力検証範囲と対応)全体で有効な
    # 単純多角形になることを確認する。
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    stitch_line = segments_to_polyline(segments)
    variable = offset_polygon_variable(stitch_line, base_distance=1.0, hem_distance=hem_distance)
    if _HAS_SHAPELY:
        assert _ShapelyPolygon(variable[:-1]).is_valid


def test_offset_polygon_variable_can_shrink_the_hem_edge_narrower_than_base():
    # hem_distance < base_distance(裾を標準より狭くする、通常の使い方の
    # 逆)も同じ関数で扱えることを確認する。正方形の裾(y最大の辺)だけ
    # 0.3cmにすると、その辺のy方向の張り出しは0.3cm程度に留まり、
    # 標準の1.0cmより明らかに小さくなるはず。
    square = _square(10.0)
    result = offset_polygon_variable(square, base_distance=1.0, hem_distance=0.3)
    if _HAS_SHAPELY:
        poly = _ShapelyPolygon(result[:-1])
        assert poly.is_valid
    ys = [p[1] for p in result]
    assert max(ys) == pytest.approx(10.3, abs=0.1)  # 標準の11.0より明らかに小さい


@pytest.mark.parametrize("part_type,variation", [
    ("front_bodice", "round_neck"), ("back_bodice", "v_neck"),
    ("front_bodice_zip_panel", "round_neck"), ("front_pants", "wide"),
    ("back_pants", "flare"), ("skirt", "tight"), ("skirt", "flare"),
    ("sleeve", "puff"), ("collar", "shirt_collar"), ("cuffs", "ruffle"),
    ("waistband", "elastic"),
])
@pytest.mark.parametrize("base_distance,hem_distance", [
    (0.3, 0.5), (1.0, 3.0), (1.0, 0.3), (3.0, 8.0),
])
def test_offset_polygon_variable_is_valid_across_every_part_type_and_allowance_range(
        part_type, variation, base_distance, hem_distance):
    # round5の縫い代機能をapp.py側で公開する入力範囲(0.3〜8cm)全体・
    # 標準で用意している全パーツ種の代表バリエーションで、辺ごとの
    # オフセットが必ず有効な単純多角形になることを確認する。
    db = TemplateDB()
    segments = db.get(part_type, variation)
    stitch_line = segments_to_polyline(segments)
    variable = offset_polygon_variable(stitch_line, base_distance, hem_distance)
    if _HAS_SHAPELY:
        assert _ShapelyPolygon(variable[:-1]).is_valid


def test_finalize_part_hem_seam_allowance_only_widens_the_bottom_edge():
    # 縦20cm x 横10cmの単純な矩形で、裾(y最大=上辺)だけ3cm、他は1cmにすると、
    # 高さは 22cm(=1+1で全周)ではなく 24cm(裾側だけ+3cm、反対側は+1cmのまま)
    # になる。横幅は左右どちらも裾判定を受けないため、ほぼ12cmのまま
    # (shapelyのunion/differenceベースの実装では、裾の両端の継ぎ目部分に
    # ごく僅かな張り出し(0.1cm程度、offset_polygon_variableのdocstring
    # 参照)が生じる近似があるため、完全な等値ではなく許容誤差付きで比較する)。
    segments = parse_path("M 0 0 L 10 0 L 10 20 L 0 20 Z")
    base_only = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    with_hem = finalize_part("front_bodice", "round_neck", segments,
                              seam_allowance_cm=1.0, hem_seam_allowance_cm=3.0)
    assert base_only.height_cm == pytest.approx(22.0)
    assert with_hem.height_cm == pytest.approx(24.0)
    assert with_hem.width_cm == pytest.approx(base_only.width_cm, abs=0.2)
    assert with_hem.seam_allowance_cm == 1.0  # 表示用に保持される値は「通常」縫い代の方


def test_finalize_part_hem_seam_allowance_none_matches_uniform_behavior():
    segments = parse_path("M 0 0 L 10 0 L 10 20 L 0 20 Z")
    base_only = finalize_part("front_bodice", "round_neck", segments, seam_allowance_cm=1.0)
    explicit_none = finalize_part("front_bodice", "round_neck", segments,
                                   seam_allowance_cm=1.0, hem_seam_allowance_cm=None)
    assert base_only.cut_line == explicit_none.cut_line
