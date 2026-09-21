"""princess.py — 身頃を切り替え線(プリンセスライン)で分割する(round30で追加)。

【なぜ必要か】
round26以降、この型紙エンジンが「正直な限界」として毎回書いてきた項目が
2つある:

  * ウエストを絞りきれない体型がある。ダーツで摘める量には上限があり、
    ウエストとバストの差が極端な体型では残ってしまう(round29の実測で
    バスト83/ウエスト50/ヒップ100の場合に2.9cm)。
  * 胸ぐせダーツが脇線に収まりきらない体型がある(round29の実測で
    バスト140の場合に2cm)。

どちらの注記にも「切り替え(プリンセスライン)のあるデザインの方が適して
います」と書いてきた。実際の型紙でもそこが定石だからである。round30で
その切り替え線そのものを作れるようにした。

【切り替え線が効く理由】
ダーツは「1枚の布の中で摘む」ので、摘める量は布のつながり方に縛られる。
切り替え線は**布を切り分けてから縫い直す**ので、その縛りが無い。
ウエストで細くしたいだけ細くでき、しかも上はバストの丸みへ、下はヒップの
丸みへ、1本の線で連続して沿わせられる。

【作り方(このモジュールが行う操作)】
1. ダーツを入れない身頃を作る(呼び出し側が`dartless=True`で作る)。
2. 袖ぐりの途中の点Aから、BP(バストポイント)を通り、ウエスト、裾まで
   降りる線を引く。
3. その線を、ウエストで「摘みたい量」だけ左右に開いた**2本**にする。
   前中心側の1本が中央パーツの縁、脇側の1本が脇パーツの縁になる。
4. 輪郭をその2本で切り分け、中央パーツと脇パーツの2枚にする。

縫うと2本の縁が重なるので、ウエストでは開いた分だけ細くなり、BPと裾では
元の幅のままになる——ダーツとまったく同じ効果が、縫い目として得られる。

【正直な限界】
* **袖ぐりから上には立体を足していない。** 実際の製図では、胸ぐせダーツを
  袖ぐりへ回してから切り替え線を引くこともある(その場合、袖ぐりは回した
  分だけ長くなる)。ここでは袖ぐりの長さを変えず、胸の丸みはすべて
  「BPを通る縫い目の曲がり」で作っている。つまり得られる胸の立体は、
  ウエストで開いた量に応じた分だけで、新文化式の胸ぐせダーツ角
  (B/4−2.5度)を再現するものではない。足りない場合は開示する。
* **BPの上下で縁の長さがそろっていない。** 中央側と脇側の縁は、BPを
  中心にわずかに長さが違う(実測で最大0.6cm)。実物の型紙では長い方を
  いせ込むか、線を引き直して合わせる。ここでは差を実測して開示する。
* **後ろ身頃の切り替え線の頂点は、肩甲骨の位置ではなくバストラインの
  高さに置いている。** 肩甲骨の高さを決める採寸項目を持っていないため。
"""

from __future__ import annotations

from math import hypot

from .bodice_fit import bust_point_from_cf_cm
from .darts import DART_OFFSET_RATIO
from .measurements import Measurements
from .part_specs import fit_ease
from .svgpath import segments_to_polyline

Point = tuple[float, float]

#: 切り替え線を分割できるパーツ種。前開きの片側パネル
#: (front_bodice_zip_panel)は左右非対称で中心前が輪郭の縁にあるため対象外。
PRINCESS_PART_TYPES = ("front_bodice", "back_bodice")

#: 分割後のパーツ種の名前。`part_type`はラベルにそのまま出るので、
#: 「中央」「脇」が分かる名前にしてある。
PRINCESS_PANEL_TYPES: dict[str, tuple[str, str]] = {
    "front_bodice": ("front_bodice_center", "front_bodice_side"),
    "back_bodice": ("back_bodice_center", "back_bodice_side"),
}

#: 切り替え線が袖ぐりから始まる位置。脇の下から袖ぐりの弧長の何割か。
#:
#: 実物の型紙では「袖ぐりの下から1/3ほど上がったあたり」から引くことが
#: 多い。合印(`engine/notches.py`の`ARMHOLE_NOTCH_RATIO`=0.45)と同じ位置に
#: すると、袖を合わせる印と切り替えの縫い目が重なって紛らわしいので、
#: 少し下にずらしてある。
PRINCESS_ARMHOLE_FROM_UNDERARM = 0.35

#: 切り替え線の頂点(BP)より上で、縫い目が中心側へ寄る量の上限(cm)。
#: これを超えて寄せると、中央パーツの袖ぐり側が細くなりすぎる。
PRINCESS_MAX_UPPER_SHIFT_CM = 6.0

#: 分割後のパーツがこれより細くなる場合は、分割しない(縫えない幅になる)。
MIN_PANEL_WIDTH_CM = 4.0

#: 切り替え線を折れ線で近似するときの、縦方向の刻み(cm)。
PRINCESS_CURVE_STEP_CM = 0.5


class PrincessError(ValueError):
    """切り替え線を引けない形状。呼び出し側で安全側に倒すために使う。"""


def _closed(points: list[Point]) -> list[Point]:
    if points and points[0] == points[-1]:
        return list(points)
    return list(points) + [points[0]] if points else []


def _catmull_x_at(controls: list[Point], y: float) -> float:
    """(y, x) の制御点列を通る、なめらかな x(y) を評価する。

    制御点の間はエルミート補間(端の傾きは片側差分、内側は中央差分)で
    つなぐ。制御点そのものは必ず通るので、「BPを通る」「ウエストで
    指定した位置を通る」という要件が保たれる。
    """
    ys = [c[0] for c in controls]
    xs = [c[1] for c in controls]
    if y <= ys[0]:
        return xs[0]
    if y >= ys[-1]:
        return xs[-1]
    # 各制御点での傾き dx/dy。
    slopes: list[float] = []
    for i in range(len(controls)):
        if i == 0:
            slopes.append((xs[1] - xs[0]) / (ys[1] - ys[0]))
        elif i == len(controls) - 1:
            slopes.append((xs[-1] - xs[-2]) / (ys[-1] - ys[-2]))
        else:
            slopes.append((xs[i + 1] - xs[i - 1]) / (ys[i + 1] - ys[i - 1]))
    for i in range(len(controls) - 1):
        y0, y1 = ys[i], ys[i + 1]
        if not (y0 <= y <= y1):
            continue
        h = y1 - y0
        t = (y - y0) / h
        t2, t3 = t * t, t * t * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        return (h00 * xs[i] + h10 * h * slopes[i]
                + h01 * xs[i + 1] + h11 * h * slopes[i + 1])
    return xs[-1]


def _sample_edge(controls: list[Point]) -> list[Point]:
    """制御点列から、縫い目の折れ線(上から下へ)を作る。

    刻みの位置に加えて、**制御点の高さそのもの**を必ず標本に含める。
    含めないと、BPやウエストの高さが2つの標本の間に落ち、その高さでの
    幅が「線形補間した値」になって狙いよりわずかに広くなる(実測で
    バスト140の体型のウエスト周が1.4cm広くなっていた)。
    """
    top, bottom = controls[0][0], controls[-1][0]
    steps = max(2, int((bottom - top) / PRINCESS_CURVE_STEP_CM) + 1)
    ys = {top + (bottom - top) * k / steps for k in range(steps + 1)}
    ys.update(c[0] for c in controls)
    out = [(_catmull_x_at(controls, y), y) for y in sorted(ys)]
    out[0] = (controls[0][1], controls[0][0])
    out[-1] = (controls[-1][1], controls[-1][0])
    return out


def _edge_length(points: list[Point]) -> float:
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _crossing_index(points: list[Point], y: float, start: int, stop: int,
                     left: bool) -> int | None:
    """points[start:stop] のうち、高さ`y`を跨ぐ辺の番号を返す。"""
    for i in range(start, min(stop, len(points) - 1)):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        if (y1 - y) * (y2 - y) <= 0 and abs(y2 - y1) > 1e-9:
            return i
    return None


def _armhole_start_point(points: list[Point], side_seam_index: int,
                          left: bool) -> tuple[Point, int]:
    """袖ぐりの上で、切り替え線が始まる点とその直前の辺の番号を返す。"""
    path = points[:side_seam_index + 1] if left else points[side_seam_index:]
    if len(path) < 2:
        raise PrincessError("袖ぐりの点列が短すぎます")
    total = _edge_length(path)
    if total <= 0:
        raise PrincessError("袖ぐりの長さが0です")
    # 脇の下からの弧長。左は末尾が脇の下、右は先頭が脇の下。
    target = total * PRINCESS_ARMHOLE_FROM_UNDERARM
    walk = list(reversed(path)) if left else path
    acc = 0.0
    for i, (a, b) in enumerate(zip(walk, walk[1:])):
        seg = hypot(b[0] - a[0], b[1] - a[1])
        if acc + seg >= target:
            t = (target - acc) / seg if seg else 0.0
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if left:
                index = side_seam_index - i - 1
            else:
                index = side_seam_index + i
            return point, max(0, index)
        acc += seg
    raise PrincessError("袖ぐりの上に開始点を置けません")


def _insert(points: list[Point], index: int, point: Point) -> list[Point]:
    """points[index] と points[index+1] の間に点を差し込んだ列を返す。"""
    return points[:index + 1] + [point] + points[index + 1:]


def princess_intake_cm(half_width_at_waist_cm: float, waist_cm: float,
                        waist_ease_cm: float) -> float:
    """切り替え線1本がウエストで摘む量(cm)。

    身頃の半身がウエストで余っている量そのもの。ダーツと違って上限を
    設けない——切り替え線は布を切り分けるので、ダーツのような
    「1枚の中で摘める量」の制約が無い。
    """
    target = (waist_cm + waist_ease_cm) / 4.0
    return max(0.0, half_width_at_waist_cm - target)


def split_bodice(part_type: str, scaled, measurements: Measurements,
                  fit=None) -> tuple[list, list, dict] | None:
    """身頃を切り替え線で「中央パーツ」と「脇パーツ」に分ける。

    Returns:
        (中央パーツのsegments, 脇パーツのsegments, 実測値の辞書)。
        引けない形状ならNone(呼び出し側は分割せずそのまま出す)。

    実測値の辞書には、開示に使う量を入れる:
        waist_intake_cm … 切り替え線1本がウエストで摘む量
        edge_gap_cm     … 中央側と脇側の縁の長さの差(いせ込む量)
    """
    if part_type not in PRINCESS_PART_TYPES:
        return None
    if scaled.waist_y_cm is None or scaled.bust_line_y_cm is None:
        return None

    points = _closed(segments_to_polyline(scaled.segments, curve_steps=200))
    if len(points) < 8:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    center_x = (min(xs) + max(xs)) / 2.0
    hem_y = max(ys)
    waist_y = scaled.waist_y_cm
    if not (min(ys) < waist_y < hem_y):
        return None

    from .compatibility import _x_range_at_y, first_side_seam_index

    side_index = first_side_seam_index(points)
    if side_index is None:
        return None
    span = _x_range_at_y(points, waist_y)
    if span is None:
        return None
    half_width = (span[1] - span[0]) / 2.0
    intake = princess_intake_cm(half_width, measurements.waist,
                                 fit_ease(fit).waist_cm)
    if intake <= 0.2:
        return None

    # 切り替え線の頂点。前身頃はBP、後ろ身頃はバストラインの高さの
    # 「ダーツを置く位置」(ダーツと同じ場所を通す)。
    if part_type == "front_bodice":
        apex_offset = bust_point_from_cf_cm(measurements.bust,
                                             measurements.bust_point_spacing)
        apex_y = scaled.bust_point_y_cm or scaled.bust_line_y_cm
    else:
        apex_offset = half_width * DART_OFFSET_RATIO
        apex_y = scaled.bust_line_y_cm
    apex_y = min(max(apex_y, min(ys) + 1.0), waist_y - 2.0)

    # 裾では2本が合流する(裾の幅=ヒップの幅を変えない)。
    hem_span = _x_range_at_y(points, hem_y - 0.01)
    if hem_span is None:
        return None
    hem_half = (hem_span[1] - hem_span[0]) / 2.0
    hem_offset = min(apex_offset, hem_half - MIN_PANEL_WIDTH_CM)
    if hem_offset <= 0:
        return None

    try:
        panels = _build_panels(points, side_index, center_x, apex_offset, apex_y,
                                waist_y, hem_y, hem_offset, intake)
    except PrincessError:
        return None
    if panels is None:
        return None
    center_segments, side_segments, stats = panels
    stats["waist_intake_cm"] = intake
    return center_segments, side_segments, stats


def _hem_insert_index(points: list[Point], hem_y: float, x: float) -> int | None:
    """裾の水平な辺のうち、xを含むものの番号。

    輪郭は「左肩→左袖ぐり→左脇線→**裾(左から右へ)**→右脇線→右袖ぐり→
    襟ぐり」の順に並ぶ(`scripts/generate_templates.py`の`_bodice_path`)。
    裾の辺は両端のyが裾の高さに一致する。
    """
    tol = 1e-6
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        if abs(y1 - hem_y) > tol or abs(y2 - hem_y) > tol:
            continue
        if min(x1, x2) - tol <= x <= max(x1, x2) + tol:
            return i
    return None


def _build_panels(points: list[Point], side_index: int, center_x: float,
                   apex_offset: float, apex_y: float, waist_y: float,
                   hem_y: float, hem_offset: float, intake: float):
    """左右の袖ぐりから裾までを2本の縫い目で切り分ける。

    輪郭の並び順(左肩→左袖ぐり→左脇線→裾→右脇線→右袖ぐり→襟ぐり)に
    依拠する。順序が想定と違えば`PrincessError`にして、呼び出し側が
    分割せずそのまま出せるようにする。
    """
    a_left, a_left_index = _armhole_start_point(points, side_index, left=True)
    if a_left[1] >= apex_y - 1.0:
        raise PrincessError("切り替え線の開始点がBPより下になります")

    apex_x = center_x - apex_offset
    hem_x = center_x - hem_offset
    half = intake / 2.0

    # 左の縫い目。上端(袖ぐり)で1点、BPで合流、ウエストで開き、裾で合流。
    center_controls = [(a_left[1], a_left[0]), (apex_y, apex_x),
                        (waist_y, apex_x + half), (hem_y, hem_x)]
    side_controls = [(a_left[1], a_left[0]), (apex_y, apex_x),
                      (waist_y, apex_x - half), (hem_y, hem_x)]
    center_edge = _sample_edge(center_controls)      # 上→下
    side_edge = _sample_edge(side_controls)          # 上→下

    def _mirror(seq: list[Point]) -> list[Point]:
        return [(2 * center_x - x, y) for x, y in seq]

    a_right = (2 * center_x - a_left[0], a_left[1])
    hem_right_x = 2 * center_x - hem_x

    # 右の袖ぐりの上で、開始点を差し込む辺を探す。輪郭の右半分(裾より後)を
    # 高さで走査する。
    hem_left_index = _hem_insert_index(points, hem_y, hem_x)
    hem_right_index = _hem_insert_index(points, hem_y, hem_right_x)
    if hem_left_index is None or hem_right_index is None:
        raise PrincessError("裾の上に着地点を置けません")
    a_right_index = _crossing_index(points, a_left[1], hem_right_index + 1,
                                     len(points) - 1, left=False)
    if a_right_index is None:
        raise PrincessError("右の袖ぐりに開始点を置けません")
    if not (a_left_index < hem_left_index <= hem_right_index < a_right_index):
        raise PrincessError("輪郭の並び順が想定と違います")

    # 番号がずれないよう、後ろから差し込む。
    work = _insert(points, a_right_index, a_right)
    work = _insert(work, hem_right_index, (hem_right_x, hem_y))
    work = _insert(work, hem_left_index, (hem_x, hem_y))
    work = _insert(work, a_left_index, a_left)
    a_left_at = a_left_index + 1
    hem_left_at = hem_left_index + 2
    hem_right_at = hem_right_index + 3
    a_right_at = a_right_index + 4

    # 脇パーツ(左): 袖ぐり下部 → 脇線 → 裾 → 縫い目を上って戻る。
    side_panel = work[a_left_at:hem_left_at + 1] + list(reversed(side_edge))

    # 中央パーツ: 裾を左から右へ → 右の縫い目を上る → 右袖ぐり・襟ぐり・
    # 左袖ぐり → 左の縫い目を下る。
    center_panel = (
        work[hem_left_at:hem_right_at + 1]
        + list(reversed(_mirror(center_edge)))
        + work[a_right_at:len(work) - 1]
        + work[:a_left_at + 1]
        + center_edge
    )

    center_panel = _dedupe(center_panel)
    side_panel = _dedupe(side_panel)
    if len(center_panel) < 4 or len(side_panel) < 4:
        raise PrincessError("分割後の輪郭が短すぎます")

    stats = {"edge_gap_cm": abs(_edge_length(center_edge) - _edge_length(side_edge))}
    return _to_segments(center_panel), _to_segments(side_panel), stats


def _dedupe(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        if not out or hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) > 1 and hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def _to_segments(points: list[Point]) -> list:
    segments = [("M", [points[0][0], points[0][1]])]
    segments += [("L", [x, y]) for x, y in points[1:]]
    segments.append(("Z", []))
    return segments
