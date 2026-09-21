"""seam.py — 縫い代・合印・布目線の生成。

縫い代(1〜1.5cm)・縫い線・合印・布目線を内包したSVG/PDFを出力し、
A4分割印刷→貼り合わせだけで型紙として使用できるようにする実装。

各パーツについて:
  - stitch_line : 縫い線（テンプレート本来の輪郭。ミシンで縫う位置）
  - cut_line    : 縫い代を外側に加えた裁断線（stitch_line を offset した結果）
  - notches     : 合印（重ね合わせの目印。裁断線から縫い線に向かう短い切り込み）
  - grainline   : 布目線（生地の縦地方向を示す矢印つきの線）

多角形オフセットは shapely があれば shapely.buffer を使い、無ければ
「各辺を法線方向にずらして再交差させる」自前実装にフォールバックする。
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field

from .svgpath import segments_to_polyline

try:
    from shapely.geometry import Polygon as _ShapelyPolygon
    from shapely.ops import unary_union as _shapely_unary_union
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover - shapely未導入環境向けフォールバック
    _HAS_SHAPELY = False

Point = tuple[float, float]
Segment = tuple[Point, Point]

DEFAULT_SEAM_ALLOWANCE_CM = 1.0


@dataclass
class FinalizedPart:
    part_type: str
    variation: str
    stitch_line: list[Point]
    cut_line: list[Point]
    notches: list[Segment]
    grainline: dict
    seam_allowance_cm: float
    # 「前/後」「左/右」など、同じテンプレートを複数枚使うときにどちらの
    # ピースかを区別するラベル（印刷される型紙にもそのまま表示する）。
    # 実際の縫製では前後・左右で形が同一でも必ずラベルを振って区別するため、
    # 形状が同じであっても空文字のままにしない。
    label_suffix: str = ""
    # engine.darts.apply_waist_dart() が実際に追加したウエストダーツの本数
    # (両半身合計)。0ならダーツ無し(線形スケーリングのみ)。
    dart_count: int = 0
    # round15で追加: 帯状パーツ(衿・カフス・ウエストバンド)の「相手に
    # 縫い付けられる辺」("top"/"bottom"、宣言が無ければ"")。
    # テンプレートSVGのdata-seam-edge属性が出どころで、
    # engine/compatibility.pyのseam_edge_lengthが長さを測るのに使う。
    seam_edge: str = ""
    #: round27で追加: パーツ**内部**の縫い線(閉じた点列のリスト)。
    #:
    #: ウエストのダーツ(両端が尖ったダイヤモンドダーツ)のように、輪郭を
    #: 切り欠かずに内側で摘む縫い線を表す。輪郭(cut_line/stitch_line)には
    #: 現れないので、縫い合わせ長さのチェックには影響しない。
    internal_lines: list[list[Point]] = field(default_factory=list)
    #: round30で追加: JIS L 0110「衣料パターンの表示記号」の**内部線**(表2-40)
    #: と**中心線**(表1-2)、**バストポイント**(表1-12)。
    #:
    #: (ラベル, 点列) の並び。縫う線ではなく、「この線がバストの高さ」
    #: 「ここが中心前」という**製図上の基準**を示すための線で、実物の型紙
    #: では細い線で描かれる。補正するとき(丈を詰める・ダーツを移す)に
    #: どこを基準にすればよいかが型紙だけで分かるようになる。
    reference_lines: list[tuple[str, list[Point]]] = field(default_factory=list)
    #: round31: この型紙1枚から裁つ枚数。パイプラインは同じ形を複数枚使う
    #: 場合それぞれ別のパーツとして並べるので、通常は1になる。
    cut_quantity: int = 1
    #: round31: 中心を布のわ(輪)に合わせて裁つパーツか。このエンジンの
    #: 身頃は左右つながった全幅で出るので、今はどれもFalse。
    cut_on_fold: bool = False
    #: round76: ドロップショルダーで下げたあとの脇の下の高さ(cm)。
    #: Noneなら基準線のバスト線(BL)を脇の下として扱う(round75までと同じ)。
    #: `engine/compatibility.py`の`underarm_y_of`が読む。
    underarm_y_cm: float | None = None
    bbox: tuple[float, float, float, float] = field(init=False)

    def __post_init__(self) -> None:
        xs = [p[0] for p in self.cut_line]
        ys = [p[1] for p in self.cut_line]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    @property
    def width_cm(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height_cm(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def display_name(self) -> str:
        """型紙に印字する日本語のパーツ名(round32)。

        round31まではここが内部識別子(`front_bodice(round_neck)`)のままで、
        **印刷して裁断に使う紙の上にそれが書かれていた**。機械向けの
        識別子が要る場所では`identifier`を使う(文字列はround31までと同一)。
        """
        from .part_names import part_display_name
        return part_display_name(self.part_type, self.variation,
                                  self.label_suffix, self.dart_count)

    @property
    def name_without_dart_count(self) -> str:
        """ダーツ本数の後置きを付けない、そのままのパーツ名(round65)。

        「どのパーツにダーツが入ったか」を文で言うときに使う。
        `display_name`をそのまま並べると
        「前身頃（ラウンドネック） [ダーツ4本] 4本」と重なる。
        名前の組み立ては`display_name`と同じ関数を使う(二重に書かない)。
        """
        from .part_names import part_display_name
        return part_display_name(self.part_type, self.variation,
                                  self.label_suffix)

    @property
    def identifier(self) -> str:
        """機械向けの識別子。round31までの`display_name`とまったく同じ文字列。"""
        from .part_names import part_identifier
        return part_identifier(self.part_type, self.variation,
                                self.label_suffix, self.dart_count)

    @property
    def cutting_note(self) -> str:
        """裁ち方の指示(生地・枚数・わ裁ち・接着芯)。engine/cutting.py参照。"""
        from .cutting import cutting_note
        return cutting_note(self.part_type, self.cut_quantity, self.cut_on_fold)


def _signed_area(points: list[Point]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _line_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> Point | None:
    """2直線(無限延長)の交点。平行な場合は None。

    標準的な2直線交点の公式(Wikipedia "Line-line intersection"の
    2点表現版)は
        Px = [(x1y2-y1x2)(x3-x4) - (x1-x2)(x3y4-y3x4)] / D
        Py = [(x1y2-y1x2)(y3-y4) - (y1-y2)(x3y4-y3x4)] / D
        D  = (x1-x2)(y3-y4) - (y1-y2)(x3-x4)
    だが、以前の実装はPx・Pyそれぞれの第2項で (x1-x2) と (y1-y2) が
    入れ替わっていた（誤って py の項に (x1-x2) を、px の項に (y1-y2) を
    使っていた）。この関数は`_offset_polygon_fallback`（shapelyが無い場合の
    縫い代オフセット、miter join）専用に使われているが、そちら側にテストが
    無かったため長年気付かれていなかった。実際に「x=-1の垂直線」と
    「y=-1の水平線」という単純な例で検証したところ、正しい交点は(-1,-1)の
    はずが、修正前の実装は(-2,0)という全く無関係な点を返すことを確認した。
    """
    x1, y1 = a1; x2, y2 = a2
    x3, y3 = b1; x4, y4 = b2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return (px, py)


def _cross(o: Point, a: Point, b: Point) -> float:
    """ベクトル(o->a)と(o->b)の外積のz成分。頂点が凸/凹どちらかの判定に使う。"""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _offset_polygon_fallback(points: list[Point], distance: float) -> list[Point]:
    """shapelyが無い環境向け: 全辺を同じdistanceでオフセットする。

    round5で辺ごとに異なる幅を指定できる`_offset_polygon_per_edge`を
    追加した際、こちらは「全辺同じ幅」という特殊ケースとして、内部で
    そちらに委譲するよう書き換えた（アルゴリズム自体は変更していない）。
    """
    pts = points[:-1] if points and points[0] == points[-1] else list(points)
    n = len(pts)
    if n < 3:
        return list(points)
    return _offset_polygon_per_edge(points, [distance] * n)


def _offset_polygon_per_edge(points: list[Point], edge_distances: list[float]) -> list[Point]:
    """各辺を外向き法線方向に、辺ごとに指定した距離だけずらして
    隣り合う辺同士を再交差させる、古典的なポリゴンオフセット手法。

    edge_distances[i] は pts[i]->pts[i+1] (最後はpts[n-1]->pts[0]) の
    辺のオフセット幅(cm)。全辺同じ値を渡せば`_offset_polygon_fallback`と
    同じ結果になる。round5で「縫い代を辺ごとに設定可能に」する機能
    (`offset_polygon_variable`)のために、単一distanceだった旧実装を
    一般化した。

    以前は凸頂点・凹頂点を区別せず、隣接するオフセット辺を常に無限直線として
    交差させていた（miter joinのみ）。これは輪郭がどこも凸である場合は
    問題ないが、実際にこのアプリの本物の`front_bodice`テンプレート
    （首元がカーブで凹んでいる、i.e. 凹頂点を含む輪郭）に対して実行すると、
    凹頂点で2本の無限直線がオフセット方向とは逆側の遠方で交差してしまい、
    出力が自己交差した無効な多角形になることを実際に確認した
    （`shapely.geometry.Polygon(...).is_valid`で検証: 修正前は`False`、
    面積も正しい値の約4倍(7410cm^2 vs 正しい1892cm^2)に膨らんでいた）。
    docstringが述べる「型紙のような『概ね凸に近い』輪郭」という前提自体が、
    このアプリの実テンプレートに当てはまっていなかった。

    修正: 各頂点が凸か凹かを`_cross`の符号（輪郭全体の向きと比較）で判定し、
    凹頂点だけは無限直線の交差(miter)をやめて、隣接する2本のオフセット辺の
    端点をそのまま繋ぐ(bevel、面取り)方式にする。凹頂点でbevelにすると
    僅かに面取りされた分だけ縫い代が小さくなるが、自己交差するよりは
    はるかに安全（縫い代が全くゼロになるわけではなく、実用上問題ない程度の
    近似）。凸頂点は従来通りmiter joinを使う。
    """
    pts = points[:-1] if points and points[0] == points[-1] else list(points)
    n = len(pts)
    if n < 3:
        return list(points)
    if len(edge_distances) != n:
        raise ValueError(
            f"edge_distancesの長さ({len(edge_distances)})が辺の本数({n})と一致しません。"
        )

    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n

    # 輪郭全体の向き（CW/CCW）。個々の頂点の凸/凹判定の基準に使う。
    orientation_sign = 1.0 if _signed_area(pts) >= 0 else -1.0

    # 「外向き」の判定方法について: 以前は辺ごとに「その辺の中点から
    # 図形全体の重心へ向かうベクトルと反対側」を外向きとみなす、辺単位の
    # 重心ヒューリスティックを使っていた。これは凸多角形では機能するが、
    # front_bodiceの首元カーブのような凹んだ領域の近くでは、辺の中点から
    # 見て全体の重心が「直感的な外側」とは反対方向にあることがあり、
    # 実際にそのカーブ付近の辺だけ法線が逆向き(内向き)に誤判定され、
    # オフセット後の輪郭がその部分だけ内側に折れ込んで自己交差する
    # ことを確認した。閉じた単純多角形は全体として一定の向き
    # (CW/CCWのどちらか一方)で頂点が並んでいるため、外向き法線の
    # 「どちらに90度回転させるか」は輪郭全体で共通の1つの選択のはずで、
    # 辺ごとに判定し直す必要は無い。そこで、向き判定は先頭の辺だけで
    # 一度行い（重心ヒューリスティックは孤立した1辺に対してであれば
    # 凹凸の影響を受けず信頼できる）、以降は全ての辺に同じ回転方向を
    # 適用するようにした。
    p1_0, p2_0 = pts[0], pts[1 % n]
    dx0, dy0 = p2_0[0] - p1_0[0], p2_0[1] - p1_0[1]
    len0 = math.hypot(dx0, dy0) or 1e-9
    nx0, ny0 = dy0 / len0, -dx0 / len0
    mx0, my0 = (p1_0[0] + p2_0[0]) / 2, (p1_0[1] + p2_0[1]) / 2
    flip_all = (nx0 * (mx0 - cx) + ny0 * (my0 - cy)) < 0

    offset_edges: list[Segment] = []
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy) or 1e-9
        nx, ny = dy / length, -dx / length
        if flip_all:
            nx, ny = -nx, -ny
        d = edge_distances[i]
        offset_edges.append(((p1[0] + nx * d, p1[1] + ny * d),
                              (p2[0] + nx * d, p2[1] + ny * d)))

    new_pts: list[Point] = []
    for i in range(n):
        prev_idx, next_idx = (i - 1) % n, (i + 1) % n
        cross = _cross(pts[prev_idx], pts[i], pts[next_idx])
        is_reflex = (cross * orientation_sign) < 0
        a1, a2 = offset_edges[prev_idx]
        b1, b2 = offset_edges[i]
        if is_reflex:
            new_pts.append(a2)
            new_pts.append(b1)
        else:
            pt = _line_intersect(a1, a2, b1, b2)
            new_pts.append(pt if pt is not None else b1)
    new_pts.append(new_pts[0])
    return new_pts


def offset_polygon(points: list[Point], distance: float) -> list[Point]:
    """輪郭を外側に distance(cm) だけオフセットする（縫い代の裁断線を作る）。"""
    if _HAS_SHAPELY:
        pts = points[:-1] if points and points[0] == points[-1] else points
        if len(pts) < 3:
            return list(points)
        poly = _ShapelyPolygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        buffered = poly.buffer(distance, join_style=1, quad_segs=8)  # round join
        if buffered.is_empty:
            return _offset_polygon_fallback(points, distance)
        coords = list(buffered.exterior.coords)
        return coords
    return _offset_polygon_fallback(points, distance)


# 裾(hem)とみなす辺の判定に使う許容誤差(cm)。浮動小数点演算の丸め誤差
# 吸収のためだけの小さな値で、実際の裾の幅とは無関係。
_HEM_Y_TOLERANCE_CM = 1e-6


def _hem_edge_distances(points: list[Point], base_distance: float,
                         hem_distance: float) -> list[float]:
    """輪郭の各辺について、「裾(hem)」とみなす辺だけhem_distanceを、それ
    以外はbase_distanceを割り当てた、辺の本数と同じ長さのリストを返す。

    「裾」の判定は、`darts.py`が既にウエストダーツの挿入位置を探すために
    使っている考え方(y座標が最大の水平な直線を裾とみなす)を、ここでは
    セグメント単位ではなく閉多角形の"辺"単位に一般化したもの。front_bodice/
    back_bodiceの裾、skirtの裾、front_pants/back_pantsの裾(=足首の
    開き口)、sleeveの袖口など、多くのパーツで「y座標が最大の辺=実際の
    折り返しが入る縁」に対応するため、パーツ種ごとの特別扱いをせずに
    汎用的に扱える。ウエストダーツを追加した後は、裾の一部がダーツの
    V字切り込みで分割されるため、裾のうちダーツの脚(斜めの辺)部分は
    「水平ではない」という理由でhemと判定されず、通常の縫い代幅になる
    （裾全体が一律にhem幅になるとは限らない、という正直な限界がある）。
    collar/cuffs/waistbandのような帯状パーツにも同じ判定を機械的に
    適用しており、「片方の長辺がたまたまy最大」というだけの理由で
    hem幅が付くことがある（実務上、縫い代が広すぎて困ることはない）。
    """
    pts = points[:-1] if points and points[0] == points[-1] else list(points)
    n = len(pts)
    if n < 3:
        return [base_distance] * n
    max_y = max(p[1] for p in pts)
    distances = []
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        is_horizontal = abs(p1[1] - p2[1]) < _HEM_Y_TOLERANCE_CM
        is_at_max_y = (abs(p1[1] - max_y) < _HEM_Y_TOLERANCE_CM
                       and abs(p2[1] - max_y) < _HEM_Y_TOLERANCE_CM)
        distances.append(hem_distance if (is_horizontal and is_at_max_y) else base_distance)
    return distances


def _outward_flip(pts: list[Point], cx: float, cy: float) -> bool:
    """輪郭全体で共通の「外向き法線をどちらに90度回転させるか」を判定する。

    `_offset_polygon_per_edge`と同じ理由(辺ごとに重心ヒューリスティックを
    やり直すと凹んだ領域の近くで誤判定することがある)で、先頭の辺だけで
    一度判定し、以降は全ての辺・計算に同じ結果を使い回す。
    """
    n = len(pts)
    p1, p2 = pts[0], pts[1 % n]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy) or 1e-9
    nx, ny = dy / length, -dx / length
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    return (nx * (mx - cx) + ny * (my - cy)) < 0


def _offset_polygon_variable_shapely(points: list[Point], base_distance: float,
                                      hem_distance: float) -> list[Point]:
    """shapelyが使える場合の「辺ごとに異なる幅」オフセット。

    `_offset_polygon_per_edge`(miter/bevel の手計算方式)をそのまま
    「辺ごとの幅」に一般化して使うと、front_bodiceの首元カーブのような
    凹頂点を含む本物のテンプレートに対して、裾(hem)の幅を標準の縫い代
    幅からわずかに変えただけで自己交差する(shapely `Polygon(...).is_valid`
    が`False`になる)ことを実際に確認した。以前は同種の凹頂点バグが
    `_offset_polygon_fallback`にもあったが、そちらはshapelyが使える環境
    (=実際のアプリ)からは到達しない経路だったため実害が無かった。
    しかしround5で追加したこの関数は、shapelyが使える環境でも
    hem_distance != base_distanceの場合に必ず`_offset_polygon_per_edge`を
    経由する設計だったため、この既知のバグが実際のアプリ上でも
    front_bodiceのような凹んだ輪郭に対して再現してしまう(=既存の
    「不要になったはずの」制限が新機能によって再び実害を持つ)ことが
    分かった。

    対策として、shapelyが使える場合はこの手計算方式を使わず、
    以下の頑健な合成アプローチに変更した:
      1. まず全辺base_distanceで`offset_polygon`と同じ一様buffer(shapelyの
         round join、自己交差の心配が無い)を作る。
      2. 「裾」と判定された辺だけ、元の頂点から外向きにhem_distance分
         張り出した帯状の四角形を作り、辺の両端を接線方向に少し延長した
         上で(隣接する辺の丸まった角にもきちんと重なるようにするため)、
         hem_distance > base_distanceならunion(張り出しを追加)、
         hem_distance < base_distanceならdifference(その分だけ削る)する。
    union/differenceはshapelyの頑健な多角形演算なので、辺単位の手計算
    交差処理と違って自己交差した無効な多角形を生む余地が無い。
    唯一の近似は、裾の辺の両端(隣の辺との境目)付近が完全な角
    (miter)ではなく、延長した四角形の端がそのまま境界になる点だが、
    実用上の縫い代線としては十分な精度で、何より必ず有効な単純多角形に
    なることを優先した。
    """
    pts = points[:-1] if points and points[0] == points[-1] else list(points)
    n = len(pts)
    base_poly = _ShapelyPolygon(pts)
    if not base_poly.is_valid:
        base_poly = base_poly.buffer(0)
    result = base_poly.buffer(base_distance, join_style=1, quad_segs=8)

    edge_distances = _hem_edge_distances(points, base_distance, hem_distance)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    flip_all = _outward_flip(pts, cx, cy)

    # 接線方向に延長する余白。base_distance分の丸い角の外側まで確実に
    # 重なる最小限の量として base_distance そのもの(+丸め誤差吸収の
    # 小さな定数)を使う。値を大きくしすぎると自己交差は防げるが、裾の
    # 両端(隣接する辺との継ぎ目)で縫い代がわずかに外側へ膨らむ副作用が
    # 大きくなる(union/differenceでその余白ぶんも境界に含まれるため)。
    # 実際に本アプリの全パーツ種×代表的なバリエーション×縫い代0.3〜8cmの
    # 組み合わせで検証し、この値(1.0倍)で全て有効な単純多角形になる
    # ことを確認した上で、この副作用が最小になる値として選んでいる。
    margin = base_distance * 1.0 + 0.05
    far = base_distance * 1.0 + 0.5  # difference側で削り取る範囲の上限

    for i in range(n):
        d = edge_distances[i]
        if d == base_distance:
            continue
        p1, p2 = pts[i], pts[(i + 1) % n]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / length, dy / length
        nx, ny = uy, -ux
        if flip_all:
            nx, ny = -nx, -ny
        e1 = (p1[0] - ux * margin, p1[1] - uy * margin)
        e2 = (p2[0] + ux * margin, p2[1] + uy * margin)
        if d > base_distance:
            quad = _ShapelyPolygon([
                e1, e2,
                (e2[0] + nx * d, e2[1] + ny * d),
                (e1[0] + nx * d, e1[1] + ny * d),
            ])
            result = _shapely_unary_union([result, quad])
        else:
            sliver = _ShapelyPolygon([
                (e1[0] + nx * d, e1[1] + ny * d), (e2[0] + nx * d, e2[1] + ny * d),
                (e2[0] + nx * far, e2[1] + ny * far), (e1[0] + nx * far, e1[1] + ny * far),
            ])
            result = result.difference(sliver)

    if result.geom_type == "MultiPolygon":  # pragma: no cover - 理論上のみ、実テンプレートでは未発生
        result = max(result.geoms, key=lambda g: g.area)
    if not result.is_valid:  # pragma: no cover - 上記の演算はいずれも頑健なはずの保険
        result = result.buffer(0)
    return list(result.exterior.coords)


def offset_polygon_variable(points: list[Point], base_distance: float,
                             hem_distance: float | None = None) -> list[Point]:
    """縫い代を辺ごとに変えたい場合のオフセット。裾(hem)だけ別の幅を
    指定できる(round5「縫い代を辺ごとに設定可能に」)。

    hem_distanceがNone、またはbase_distanceと等しい場合は、従来通り
    `offset_polygon`(shapelyの一様buffer、利用可能な場合)にそのまま
    委譲する。異なる場合、shapelyが使える環境では
    `_offset_polygon_variable_shapely`(union/differenceベースの頑健な
    合成、そちらのdocstring参照)を使う。shapelyが無い環境だけ、
    `_offset_polygon_per_edge`(miter/bevel joinの手計算方式。凹頂点を
    含む輪郭では稀に自己交差することがある、`_offset_polygon_fallback`と
    同種の既知の限界がある)にフォールバックする。
    """
    if hem_distance is None or hem_distance == base_distance:
        return offset_polygon(points, base_distance)
    if _HAS_SHAPELY:
        return _offset_polygon_variable_shapely(points, base_distance, hem_distance)
    edge_distances = _hem_edge_distances(points, base_distance, hem_distance)
    return _offset_polygon_per_edge(points, edge_distances)


def _perimeter_point(points: list[Point], t: float) -> tuple[Point, Point]:
    """輪郭上の周長比 t(0..1) の点と、そこでの外向き法線を返す。"""
    pts = points[:-1] if points and points[0] == points[-1] else list(points)
    n = len(pts)
    lengths = []
    total = 0.0
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        lengths.append(d)
        total += d
    target = (t % 1.0) * total
    acc = 0.0
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    for i in range(n):
        if acc + lengths[i] >= target or i == n - 1:
            p1, p2 = pts[i], pts[(i + 1) % n]
            local_t = (target - acc) / lengths[i] if lengths[i] else 0.0
            point = (p1[0] + (p2[0] - p1[0]) * local_t, p1[1] + (p2[1] - p1[1]) * local_t)
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            length = math.hypot(dx, dy) or 1e-9
            nx, ny = dy / length, -dx / length
            if nx * (point[0] - cx) + ny * (point[1] - cy) < 0:
                nx, ny = -nx, -ny
            return point, (nx, ny)
        acc += lengths[i]
    return pts[0], (0.0, -1.0)


def notch_marks(stitch_line: list[Point], fractions: list[float],
                length_cm: float = 0.5) -> list[Segment]:
    """合印。輪郭上の指定位置(周長比0..1)から外向きに短い切り込み線を作る。"""
    marks = []
    for t in fractions:
        point, (nx, ny) = _perimeter_point(stitch_line, t)
        outer = (point[0] + nx * length_cm, point[1] + ny * length_cm)
        marks.append((point, outer))
    return marks


def grainline_marks(bbox: tuple[float, float, float, float],
                     margin_ratio: float = 0.08) -> dict:
    """布目線。パーツ中央に縦方向の矢印つき線を1本引く。"""
    min_x, min_y, max_x, max_y = bbox
    cx = (min_x + max_x) / 2.0
    h = max_y - min_y
    top = min_y + h * margin_ratio
    bottom = max_y - h * margin_ratio
    arrow = max(0.4, min(1.5, h * 0.03))
    return {
        "line": ((cx, top), (cx, bottom)),
        "arrows": [
            ((cx - arrow, top + arrow), (cx, top)),
            ((cx + arrow, top + arrow), (cx, top)),
            ((cx - arrow, bottom - arrow), (cx, bottom)),
            ((cx + arrow, bottom - arrow), (cx, bottom)),
        ],
    }


# パーツ種ごとの標準的な合印位置（輪郭の周長比、テンプレート作成時の頂点順に依存）。
# 肩点・脇の合わせ位置など、隣接パーツと縫い合わせる際の目印を最低1〜2箇所置く。
#
# 注意: stitch_line は必ず閉じた輪郭（多角形）なので、周長比 0.0 と 1.0 は
# 数学的に同一点になる（`_perimeter_point` は `t % 1.0` で位置を求めるため）。
# 以前は collar/cuffs/waistband に [0.0, 1.0] を指定していたため、2箇所の
# 合印のはずが同一点に重複して打たれ、実質「片端にしか合印が無い」状態
# だった。他のパーツ（front_bodice等）と同様、周長の半分(0.5)を使って
# 輪郭上の別の点を指すようにする。
DEFAULT_NOTCH_FRACTIONS: dict[str, list[float]] = {
    "front_bodice": [0.0, 0.5],
    "front_bodice_zip_panel": [0.0, 0.5],
    "back_bodice": [0.0, 0.5],
    "sleeve": [0.25, 0.75],
    "skirt": [0.0],
    "front_pants": [0.0, 0.5],
    "back_pants": [0.0, 0.5],
    "collar": [0.0, 0.5],
    "cuffs": [0.0, 0.5],
    "hood": [0.0, 0.5],
    "waistband": [0.0, 0.5],
}


def finalize_part(part_type: str, variation: str, segments: list,
                   seam_allowance_cm: float = DEFAULT_SEAM_ALLOWANCE_CM,
                   hem_seam_allowance_cm: float | None = None,
                   label_suffix: str = "",
                   extra_notch_fractions: list[float] | None = None,
                   dart_count: int = 0,
                   seam_edge: str = "",
                   notch_points: list[Point] | None = None,
                   internal_lines: list[list[Point]] | None = None,
                   reference_lines: list[tuple[str, list[Point]]] | None = None,
                   underarm_y_cm: float | None = None,
                   ) -> FinalizedPart:
    """変形済みセグメントから、縫い線・裁断線・合印・布目線を含む最終パーツを作る。

    Args:
        label_suffix: 「前」「後」「左」「右」など、同じテンプレートを複数枚
            使う際にどちらのピースかを示すラベル。
        hem_seam_allowance_cm: round5で追加した「裾だけ別の縫い代幅にする」
            オプション。Noneなら従来通りseam_allowance_cmで全辺一律
            （裾の折り返し分として、通常の縫い代より広めの値を指定する
            使い方を想定。裾の判定方法は`offset_polygon_variable`/
            `_hem_edge_distances`のdocstring参照）。
        extra_notch_fractions: パーツ種の既定の合印に加えて打つ、追加の合印
            位置（周長比0..1）。後ろスカートのウエストダーツ位置など、
            前後で異なる仕立て上の目印を表現するために使う。
        dart_count: engine.darts.apply_waist_dart() が既にsegmentsに追加した
            ウエストダーツの本数。segments自体にはダーツの輪郭(V字の切り込み)
            が既に反映済みなので、ここでは表示用のメタデータとして渡すだけで、
            ジオメトリを追加で変形するわけではない。
    """
    return finalize_from_stitch_line(
        part_type, variation, segments_to_polyline(segments),
        seam_allowance_cm=seam_allowance_cm,
        hem_seam_allowance_cm=hem_seam_allowance_cm,
        label_suffix=label_suffix,
        extra_notch_fractions=extra_notch_fractions,
        dart_count=dart_count, seam_edge=seam_edge,
        notch_points=notch_points, internal_lines=internal_lines,
        reference_lines=reference_lines, underarm_y_cm=underarm_y_cm)


def finalize_from_stitch_line(part_type: str, variation: str,
                               stitch_line: list[Point],
                               seam_allowance_cm: float = DEFAULT_SEAM_ALLOWANCE_CM,
                               hem_seam_allowance_cm: float | None = None,
                               label_suffix: str = "",
                               extra_notch_fractions: list[float] | None = None,
                               dart_count: int = 0,
                               seam_edge: str = "",
                               notch_points: list[Point] | None = None,
                               internal_lines: list[list[Point]] | None = None,
                               reference_lines: list[tuple[str, list[Point]]] | None = None,
                               underarm_y_cm: float | None = None,
                               ) -> FinalizedPart:
    """`finalize_part`の本体。縫い線が**点列として既にある**場合の入口。

    round41で`finalize_part`から切り出した。裏地のパーツ(engine/lining.py)は
    「表地とまったく同じ縫い線を、縫い代だけ変えてもう一度確定させる」ため、
    ベジエのセグメントではなく既に確定した`stitch_line`から作る必要がある。
    セグメントを持たない分岐を`finalize_part`側に足すより、共通処理をこちらへ
    出して`finalize_part`を薄い包みにするほうが分岐が増えない。
    """
    cut_line = offset_polygon_variable(stitch_line, seam_allowance_cm, hem_seam_allowance_cm)
    # round16: `notch_points`(実際に縫い合わせる辺の上の座標)が与えられた
    # 場合はそれを使う。与えられない場合だけ、round15までの「自分自身の
    # 周長比」による既定位置へフォールバックする。周長比の合印は相手パーツ
    # との対応が無く、裾や自由端にも落ちるため、engine/notches.py が位置を
    # 決められるパーツでは必ずそちらを使う(理由はそのモジュール参照)。
    if notch_points:
        from .notches import notch_marks_at
        notches = notch_marks_at(stitch_line, notch_points)
        if extra_notch_fractions:
            notches = notches + notch_marks(stitch_line, list(extra_notch_fractions))
    else:
        fractions = list(DEFAULT_NOTCH_FRACTIONS.get(part_type, [0.0]))
        if extra_notch_fractions:
            fractions.extend(extra_notch_fractions)
        notches = notch_marks(stitch_line, fractions)
    xs = [p[0] for p in cut_line]
    ys = [p[1] for p in cut_line]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    grain = grainline_marks(bbox)
    return FinalizedPart(
        part_type=part_type,
        variation=variation,
        stitch_line=stitch_line,
        cut_line=cut_line,
        notches=notches,
        grainline=grain,
        seam_allowance_cm=seam_allowance_cm,
        label_suffix=label_suffix,
        dart_count=dart_count,
        seam_edge=seam_edge,
        internal_lines=list(internal_lines or []),
        reference_lines=list(reference_lines or []),
        underarm_y_cm=underarm_y_cm,
    )
