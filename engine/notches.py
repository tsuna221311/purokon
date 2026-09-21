"""notches.py — 合印(ノッチ)を「実際に縫い合わせる辺の上」に、相手と対応する
位置で打つ(round16で追加)。

【round15までの問題】
合印は、パーツごとに決めた**自分自身の周長比**(0.0と0.5など)で打っていた
(`engine/seam.py`の`DEFAULT_NOTCH_FRACTIONS`)。相手パーツとの関係を一切
見ていないので、縫い合わせる2枚の合印が別々の場所に来る。合印は
「2枚を突き合わせるための印」なので、対応していなければ意味がない。

実測(標準M・ラウンドネック・タイトスカート):

  パーツ            合印1            合印2
  前身頃            左肩先           右脇線の、裾から1.2cm上
  後身頃            左肩先           **裾の上**(脇線ですらない)
  袖                袖山カーブ上     袖口の反対側
  ウエストバンド    左上の角         **右下の角**(下端は縫い付けない辺)
  衿                上端             **下端**(標準カラーは下端が縫い付け辺)

前身頃の2つ目は右脇線、後身頃の2つ目は裾。この2枚の脇線を縫い合わせるとき、
合印はまったく別の場所にある。さらに周長比なので、ダーツが入ったり体型が
変わるたびに位置が動き、前後のずれ方も変わる。

【この モジュールの方針】
「縫い合わせる相手の実際の長さに合わせる」という、round7(ウエストバンド/
カフス)・round14(袖山)・round15(衿)で繰り返し使ってきた考え方を、合印にも
適用する。すなわち:

  * 合印は必ず「実際に縫い合わされる辺」の上に置く(裾や自由端には置かない)。
  * 位置は、その辺の**共通の基準点からの距離**で決める。両方のパーツが
    同じ規則で決めるので、必ず対応する。

対応させる組み合わせ:
  脇線     前身頃 ⇔ 後ろ身頃 … 脇の下からの距離の比で対応(round14で前後の
                                 脇線長が一致するようになったので比で足りる)
  袖ぐり   身頃 ⇔ 袖山       … 脇の下(袖山の端)からの弧長で対応。前後を
                                 取り違えないよう、後ろ側は合印2本にする
                                 (洋裁の定石)
  ウエスト スカート/パンツ ⇔ ウエストバンド … バンドの縫い付け辺の上に、
                                 各パーツの継ぎ目が来る位置
  袖口     袖 ⇔ カフス       … 同上
  首ぐり   身頃 ⇔ 衿         … 衿の縫い付け辺の上に、肩の継ぎ目が来る位置
"""

from __future__ import annotations

from math import hypot

from .compatibility import (
    _closed_points, _COORD_TOL, _is_side_seam_edge, _MIN_VERTICAL_RUN_CM,
    _sum_length_at_x, first_side_seam_index, seam_edge_path, side_seam_edges,
)

Point = tuple[float, float]

#: 脇線の合印を、脇の下から脇線長の何割の位置に打つか。
#: 0.5は概ねウエスト位置にあたり、前後を合わせるときに最も効く場所。
SIDE_SEAM_NOTCH_RATIO = 0.5

#: 袖ぐり/袖山の合印を、脇の下(袖山の端)から弧長の何割の位置に打つか。
#: 実務では「前は肩寄りに1本、後ろは2本」で前後を区別する。ここでも
#: 同じ比率を身頃側と袖側の両方で使うので、必ず突き合う。
ARMHOLE_NOTCH_RATIO = 0.45

#: 後ろ側の合印を2本にするときの、2本目のずらし量(cm)。
#: 実際の型紙でも数mm〜1cm程度離した2本で「後ろ」を表す。
BACK_DOUBLE_NOTCH_GAP_CM = 0.8

#: 合印の切り込みの長さ(cm)。engine/seam.pyのnotch_marksと同じ既定値。
NOTCH_LENGTH_CM = 0.5


def _outward_normal(points: list[Point], index: int) -> Point:
    """輪郭上のindex番目の辺の外向き法線。"""
    pts = _closed_points(points)
    p1 = pts[index]
    p2 = pts[(index + 1) % (len(pts) - 1)]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = hypot(dx, dy) or 1e-9
    nx, ny = dy / length, -dx / length
    cx = sum(p[0] for p in pts[:-1]) / (len(pts) - 1)
    cy = sum(p[1] for p in pts[:-1]) / (len(pts) - 1)
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    if nx * (mx - cx) + ny * (my - cy) < 0:
        nx, ny = -nx, -ny
    return (nx, ny)


def _mark(point: Point, normal: Point, length_cm: float = NOTCH_LENGTH_CM):
    return (point, (point[0] + normal[0] * length_cm, point[1] + normal[1] * length_cm))


# --- 脇線 -------------------------------------------------------------------

def side_seam_notch_points(stitch_line: list[Point],
                            ratio: float = SIDE_SEAM_NOTCH_RATIO,
                            underarm_y: float | None = None,
                            distance_cm: float | None = None) -> list[Point]:
    """縦の脇線それぞれの上に、脇の下から `ratio` の位置の点を返す。

    脇線は「x座標が輪郭の左端/右端に一致する、縦向きの辺」として探す
    (`engine/compatibility.py`の`side_seam_length`と同じ考え方)。

    距離は**縫い閉じた後の脇線に沿って**測る。前身頃には脇ダーツが入り、
    脇線がダーツの口のぶんだけ2本に分かれている。単純に「上端から下端まで
    の何割」で測ると、その口の幅ぶん前身頃だけ位置がずれる(実測: バスト
    100cmの体型で前y=42.12・後y=41.27と0.85cmずれた)。ダーツを縫い閉じれば
    口は消えるので、縦の辺の長さの合計に対する割合で測れば前後が一致する。
    """
    pts = _closed_points(stitch_line)
    if len(pts) < 4:
        return []

    # round26: 脇線は厳密な垂直ではなくなった(裾をヒップに合わせて開かせる
    # ため)。「x座標が左端/右端に一致する縦の辺」という探し方はできないので、
    # `engine/compatibility.py`の`_is_side_seam_edge`と同じ判定に揃える
    # (判定を2か所に書くと、片方だけ直して静かに食い違う)。
    # round28: 辺ごとではなく「走り」でまとめる(`side_seam_runs`)。ダーツの口が
    # 脇線の上端近くへ移ったことで、口より上の断片が単独では短すぎて捨てられ、
    # 合印が下へずれるようになったため。
    runs: dict[str, list[tuple[Point, Point]]] = {"left": [], "right": []}
    # round31: 脇の下の高さが分かるなら渡す。後ろ身頃の袖ぐりは
    # ほぼ直線なので、形だけでは脇線と区別できない
    # (engine/compatibility.pyの`side_seam_edges`のdocstring参照)。
    for _i, side, a, b in side_seam_edges(pts, underarm_y=underarm_y):
        runs[side].append((a, b) if a[1] <= b[1] else (b, a))

    out: list[Point] = []
    for side in ("left", "right"):
        edges = sorted(runs[side], key=lambda e: e[0][1])
        if not edges:
            continue
        total = sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in edges)
        if total <= 0:
            continue
        # round71: 相手と同じ**距離**を渡されたら、比率ではなくそれを使う。
        #
        # 【なぜ必要になったか】比率で測ると、前後の脇線長がわずかでも
        # 違えば合印がずれる。round70まで前後はぴったり同じ長さだったので
        # 比率で足りていたが、round71でダーツをたたみ出しした結果、
        # 前身頃の脇線(紙の上の長さ)が0.15cmほど変わった。0.5倍すると
        # 0.075cm——**合印の位置が前後で食い違う**(実測 17.219 対 17.271)。
        #
        # これはround16がこのモジュールを作ったときの方針そのもの——
        # 「位置は共通の基準点からの**距離**で決める」——に戻すだけである。
        # 袖ぐりの合印(`armhole_notch_distance_cm`)は最初からそうしている。
        target = total * ratio if distance_cm is None else distance_cm
        if target >= total:
            continue
        acc = 0.0
        for a, b in edges:
            length = hypot(b[0] - a[0], b[1] - a[1])
            if acc + length >= target:
                t = (target - acc) / length if length else 0.0
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            acc += length
        else:  # pragma: no cover - ratio<=1なら到達しない
            out.append(edges[-1][1])
    return out


# --- 袖ぐり と 袖山 ---------------------------------------------------------

def _walk_length(points: list[Point], upto: int) -> float:
    return sum(hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points[:upto], points[1:upto + 1]))


def _point_at_arc(points: list[Point], distance: float) -> Point | None:
    """点列に沿って先頭から`distance`だけ進んだ位置の点。"""
    acc = 0.0
    for a, b in zip(points, points[1:]):
        seg = hypot(b[0] - a[0], b[1] - a[1])
        if acc + seg >= distance:
            t = (distance - acc) / seg if seg else 0.0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += seg
    return points[-1] if points else None


def _left_armhole_path(stitch_line: list[Point],
                        underarm_y: float | None = None) -> list[Point]:
    """輪郭の先頭(左肩先)から、左の脇の下までの点列を返す。

    `engine/compatibility.py`の`armhole_length`とまったく同じ走査規則
    (最初に現れる脇線の辺で打ち切る)を使う。長さを測る関数と合印を置く
    関数が別々の規則を持つとずれるため、判定そのものを共有している
    (round26で`_is_side_seam_edge`に集約した)。
    """
    pts = _closed_points(stitch_line)
    stop = first_side_seam_index(pts, underarm_y=underarm_y)
    if stop is None:
        return []
    return pts[:stop + 1]


def side_seam_notch_distance_cm(stitch_line: list[Point],
                                 ratio: float = SIDE_SEAM_NOTCH_RATIO,
                                 underarm_y: float | None = None) -> float:
    """脇線で、脇の下から合印までの弧長(cm)。相手パーツへ渡す値(round71)。

    ダーツの無い側(後ろ身頃・後ろパンツ)で測って、前後の両方に同じ値を
    使う。`armhole_notch_distance_cm`とまったく同じ考え方である。
    """
    pts = _closed_points(stitch_line)
    if len(pts) < 4:
        return 0.0
    runs: dict[str, list[float]] = {"left": [], "right": []}
    for _i, side, a, b in side_seam_edges(pts, underarm_y=underarm_y):
        runs[side].append(hypot(b[0] - a[0], b[1] - a[1]))
    totals = [sum(v) for v in runs.values() if v]
    if not totals:
        return 0.0
    return min(totals) * ratio


def armhole_notch_points(stitch_line: list[Point], is_back: bool,
                          ratio: float = ARMHOLE_NOTCH_RATIO,
                          underarm_y: float | None = None) -> list[Point]:
    """身頃の左右の袖ぐりに、脇の下から弧長比`ratio`の位置の合印を返す。

    後ろ身頃(is_back=True)は合印を2本にする。袖を裏返しに付けてしまうのを
    防ぐための、洋裁の定石(前は1本・後ろは2本)をそのまま実装している。
    身頃は中心前について左右対称なので、左の袖ぐりで求めた点を中心で
    鏡映して右側の合印にする。
    """
    path = _left_armhole_path(stitch_line, underarm_y)
    if len(path) < 2:
        return []
    total = _walk_length(path, len(path) - 1)
    if total <= 0:
        return []
    distances = [total * (1.0 - ratio)]
    if is_back:
        distances.append(max(0.0, distances[0] - BACK_DOUBLE_NOTCH_GAP_CM))

    xs = [p[0] for p in _closed_points(stitch_line)]
    center_x = (min(xs) + max(xs)) / 2.0
    out: list[Point] = []
    for d in distances:
        point = _point_at_arc(path, d)
        if point is None:
            continue
        out.append(point)
        out.append((2.0 * center_x - point[0], point[1]))
    return out


def sleeve_cap_notch_points(stitch_line: list[Point], armhole_distance_cm: float,
                             back_gap_cm: float = BACK_DOUBLE_NOTCH_GAP_CM) -> list[Point]:
    """袖山カーブの両端から、それぞれ`armhole_distance_cm`の位置に合印を返す。

    身頃側の合印は「脇の下から弧長で何cm」の位置にある。袖側も袖山の端
    (=脇の下に来る点)から同じ距離に打てば、縫うときに必ず突き合う。

    袖山は袖ぐりより「いせ込み」のぶんだけ長い(round14で袖幅を袖ぐりに
    合わせるようにしたので、その差は常にいせ込み(`sleeve_cap_ease_cm`)+デザイン分)。
    両端から同じ距離を測ると、余った差はすべて**合印より上、肩寄りの区間**
    に集まる。実際の縫製でもいせ込みは肩寄りに配分し脇の下には入れないので、
    この置き方はその配分をそのまま型紙上に表現していることになる
    (round14のREADMEに「いせ込みの配分までは指定していない」と書いた
    限界の、少なくとも一部はこれで解消する)。

    片側は合印1本(前)、もう片側は2本(後ろ)にして前後を区別する。
    """
    pts = _closed_points(stitch_line)
    if len(pts) < 3 or armhole_distance_cm <= 0:
        return []
    y0 = pts[0][1]
    cap: list[Point] = [pts[0]]
    for point in pts[1:]:
        cap.append(point)
        if abs(point[1] - y0) <= _COORD_TOL:
            break
    if len(cap) < 3:
        return []
    total = _walk_length(cap, len(cap) - 1)
    if armhole_distance_cm >= total:
        return []

    out: list[Point] = []
    front = _point_at_arc(cap, armhole_distance_cm)
    if front is not None:
        out.append(front)
    reverse = list(reversed(cap))
    for d in (armhole_distance_cm, max(0.0, armhole_distance_cm - back_gap_cm)):
        point = _point_at_arc(reverse, d)
        if point is not None:
            out.append(point)
    return out


def armhole_notch_distance_cm(stitch_line: list[Point],
                               ratio: float = ARMHOLE_NOTCH_RATIO,
                               underarm_y: float | None = None) -> float:
    """身頃の袖ぐりで、脇の下から合印までの弧長(cm)。袖側へ渡す値。"""
    path = _left_armhole_path(stitch_line, underarm_y)
    if len(path) < 2:
        return 0.0
    return _walk_length(path, len(path) - 1) * ratio


# --- 帯状パーツ(ウエストバンド/カフス/衿)の縫い付け辺 -----------------------

def seam_edge_points_at(stitch_line: list[Point], seam_edge: str,
                         distances_cm: list[float]) -> list[Point]:
    """帯の縫い付け辺の上で、片端から指定した距離の点を返す。

    `engine/compatibility.py`の`seam_edge_length`が測るのと同じ辺を辿る。
    距離は辺の始点(x最小側)からの弧長で指定する。相手パーツの継ぎ目の
    位置(例: スカート前身頃のウエスト開き長)をそのまま渡せば、その継ぎ目が
    バンドのどこに来るかを示す合印になる。
    """
    path = seam_edge_path(_closed_points(stitch_line), seam_edge)
    if len(path) < 2:
        return []
    cumulative = [0.0]
    for a, b in zip(path, path[1:]):
        cumulative.append(cumulative[-1] + hypot(b[0] - a[0], b[1] - a[1]))
    total = cumulative[-1]
    out: list[Point] = []
    for d in distances_cm:
        if d <= 0 or d >= total:
            continue
        for i in range(len(path) - 1):
            if cumulative[i] <= d <= cumulative[i + 1]:
                span = cumulative[i + 1] - cumulative[i]
                t = (d - cumulative[i]) / span if span else 0.0
                a, b = path[i], path[i + 1]
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
    return out


def notch_marks_at(stitch_line: list[Point], points: list[Point],
                    length_cm: float = NOTCH_LENGTH_CM):
    """指定した座標に、外向きの切り込みとして合印を作る。

    法線は「その点がいちばん近い辺」のものを使う。`engine/seam.py`の
    `notch_marks`(周長比で指定する版)と同じ形式のセグメントを返すので、
    PDF/SVG/DXFの描画側は変更不要。
    """
    pts = _closed_points(stitch_line)
    marks = []
    for point in points:
        best_i, best_d = 0, float("inf")
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            d = _distance_to_segment(point, a, b)
            if d < best_d:
                best_i, best_d = i, d
        marks.append(_mark(point, _outward_normal(stitch_line, best_i), length_cm))
    return marks


def _distance_to_segment(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom <= 0:
        return hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
    proj = (a[0] + dx * t, a[1] + dy * t)
    return hypot(p[0] - proj[0], p[1] - proj[1])
