"""ドロップショルダー(肩先を肩線の延長上へ出す)の製図(round76)。

【round75までの状態】このエンジンの身頃の肩先は、常に「入力された肩幅の
半分」の位置にある(`engine/bodice_fit.py`)。つまり**セットインスリーブ
以外の肩の形が引けない**。コスプレ衣装でよく使う、肩先が腕の上まで
落ちたコート・パーカ・ブルゾンの形は、この型紙では作れなかった。

ここでやることは2つだけである。

  1. 身頃 … 肩先を**肩線の延長上**へ`drop_cm`出し、袖ぐりをその分だけ
            引き直す(`apply_drop_shoulder`)。
  2. 袖   … 袖山を低くする(`cap_height_scale`)。袖ぐりが長くなった分を
            袖山の高さで受けると、袖が不自然に高く細くなるため。

【袖山の高さの根拠】東レACS「No.019 ドロップショルダーの作図」は

    「袖山の高さはアームホール寸法の30%以下が望ましい」
    「袖山Aはアームホールの25%…に設定」

と書いている。上限(30%)と作例(25%)の両方が出典にある数字なので、
**作例の25%を採り、30%を超えないことを不変条件として持つ**。

【いせ込み】同「第十六章 ドロップショルダージャケットのパターンと
デジタルトワル チェック」は

    「ドロップショルダー袖にするため、袖山線のいせ量を減らし
      全体で15mm前後とする」

と書いている。`DROP_SLEEVE_CAP_EASE_CM`がその15mmである。

【この資料から出せなかったもの(正直な限界)】

  * **袖ぐりを何cm下げるか。** ドロップショルダーでは袖ぐりの底も
    下げるが、調べた資料(東レACS No.019/第十六章、yuca先生、
    ド素人シャツ、ユリトワ)はどれも「下げる」とは書いても
    **cmを書いていない**。そこで下げ幅そのものではなく、
    「**袖ぐりの長さをドロップ前と同じに保つ**」という条件を
    こちらで決め、それを満たす下げ幅を解いている
    (`apply_drop_shoulder`)。出典から採った数字ではない。
  * **ドロップ量と袖山の関係式。** 出典にあるのは作例1つ(25%)だけで、
    「7cm出したら袖山を何cmにする」という式は無い。ドロップを大きく
    しても袖山の比は25%のままである。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .svgpath import segments_to_polyline


@dataclass(frozen=True)
class DropShoulderResult:
    """ドロップショルダーを当てた結果。"""
    #: 引き直した輪郭。
    segments: list
    #: 下げたあとの脇の下の高さ(cm)。袖ぐりをどこで打ち切るかの判定に使う。
    underarm_y_cm: float
    #: 脇の下を下げた量(cm)。
    armhole_drop_cm: float

#: ドロップショルダーの袖山の高さ ÷ 袖ぐり(片腕)。
#: 東レACS No.019「袖山Aはアームホールの25%」。
DROP_CAP_HEIGHT_RATIO = 0.25

#: 袖山の高さの上限 ÷ 袖ぐり(片腕)。
#: 東レACS No.019「袖山の高さはアームホール寸法の30%以下が望ましい」。
CAP_HEIGHT_MAX_RATIO = 0.30

#: ドロップショルダーの袖のいせ込み量(cm)。
#: 東レACS 第十六章「いせ量を減らし全体で15mm前後とする」。
DROP_SLEEVE_CAP_EASE_CM = 1.5

#: 肩先を出せる上限(cm)。肩幅の半分(=肩先から中心までの距離)を超えて
#: 出すと、肩線の延長が身頃の反対側へ届いてしまい輪郭が成立しない。
#: 比で持つのは、子ども用の小さい身頃でも同じ意味になるため。
MAX_DROP_RATIO_OF_HALF_SHOULDER = 1.0

#: ドロップショルダーを当てるパーツ種。肩先と袖ぐりを持つ身頃だけ。
#: 前開きのパネル(front_bodice_zip_panel)も対象に入る——基準点
#: (data-fit-x)に肩先・首の付け根・脇があるので、同じ手順で引ける。
DROP_SHOULDER_PART_TYPES = frozenset({
    "front_bodice", "back_bodice", "front_bodice_zip_panel",
})

#: 座標の一致判定の許容(cm)。
_TOL = 0.05


def too_large_drop_reason(drop_cm: float, shoulder_width_cm: float) -> str | None:
    """このドロップ量が引けない場合、その理由を返す(引けるならNone)。"""
    if drop_cm <= 0:
        return None
    limit = shoulder_width_cm / 2.0 * MAX_DROP_RATIO_OF_HALF_SHOULDER
    if drop_cm > limit:
        return (f"肩先を{drop_cm:g}cm出すと、肩線の延長が身頃の中心を越えます"
                f"(肩幅{shoulder_width_cm:g}cmでは{limit:.1f}cmまで)")
    return None


def cap_height_scale(armhole_per_arm_cm: float,
                     template_cap_height_cm: float) -> float | None:
    """ドロップショルダーの袖山の高さの倍率(テンプレート比)。

    高さそのものは`袖ぐり(片腕) × DROP_CAP_HEIGHT_RATIO`。テンプレートの
    袖山の高さで割って倍率にする。測れない場合はNone(呼び出し側は
    round75までと同じ扱いに落ちる)。
    """
    if armhole_per_arm_cm <= 0 or template_cap_height_cm <= 0:
        return None
    return armhole_per_arm_cm * DROP_CAP_HEIGHT_RATIO / template_cap_height_cm


def _closed(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """末尾がZで先頭に戻った重複点と、**隣り合う重複点**を落とす。

    隣り合う重複を落とすのは、脇の下が二重の点になっているため。
    身頃の輪郭は「袖ぐりの終点(0, 23.417)」と「脇線の始点(-0.0, 23.417)」を
    別の点として持っている(前者はベジエの終点、後者はLの始点)。片方だけを
    下げると、輪郭が脇の下でいったん下がってすぐ上へ戻る**ジグザグ**に
    なり、そこが脇線と読まれて袖ぐりが41.75cm→102.27cmになった(実測)。
    """
    out: list[tuple[float, float]] = []
    for point in points:
        if out and math.dist(out[-1], point) <= _TOL:
            continue
        out.append(point)
    if len(out) >= 2 and math.dist(out[0], out[-1]) <= _TOL:
        out.pop()
    return out


def _nearest_index(points: list[tuple[float, float]], target_x: float,
                   max_y: float) -> int | None:
    """`max_y`より上にある頂点のうち、xが`target_x`に最も近いものの番号。

    同じxの頂点が複数ある(袖ぐりのカーブは肩先と同じxを2回通る)場合は、
    **上にある方**を採る。肩先は袖ぐりのいちばん上の点である。
    """
    best = None
    for i, (x, y) in enumerate(points):
        if y > max_y + _TOL:
            continue
        key = (round(abs(x - target_x), 3), round(y, 3))
        if best is None or key < best[0]:
            best = (key, i)
    return None if best is None else best[1]


def _armhole_run(points: list[tuple[float, float]], si: int, ui: int,
                 underarm_y: float) -> list[int] | None:
    """肩先`si`から脇の下`ui`までの、袖ぐり側の頂点番号の並び。

    閉じた輪郭なので si→ui の経路は2通りある。袖ぐり側は**全部の点が
    脇の下より上**にあり、もう一方は必ず裾を通る(=脇の下より下)ので、
    その条件で選べる。どちらも条件を満たさなければNone。
    """
    n = len(points)
    for step in (1, -1):
        run = [si]
        i = si
        while i != ui and len(run) <= n:
            i = (i + step) % n
            run.append(i)
        if i != ui:
            continue
        if all(points[k][1] <= underarm_y + _TOL for k in run):
            return run
    return None


#: 脇の下を下げられる上限(cm)。ここまで探しても袖ぐりの長さが戻らなければ
#: 引けないものとして扱う(黙って短い袖ぐりを出さない)。
MAX_ARMHOLE_DROP_CM = 20.0


def _run_length(shape: list[tuple[float, float]], weights: list[float],
                dx: float, dy: float, armhole_drop: float) -> float:
    moved = [(x + dx * w, y + dy * w + armhole_drop * (1.0 - w))
             for (x, y), w in zip(shape, weights)]
    return sum(math.dist(a, b) for a, b in zip(moved, moved[1:]))


def _solve_armhole_drop(shape: list[tuple[float, float]], weights: list[float],
                        dx: float, dy: float, target_cm: float) -> float | None:
    """袖ぐりの長さが`target_cm`に戻る、脇の下の下げ幅を求める。

    下げ幅に対して袖ぐりの長さは単調に増えるので二分探索でよい。
    上限(`MAX_ARMHOLE_DROP_CM`)まで探しても届かなければNone。
    """
    if _run_length(shape, weights, dx, dy, MAX_ARMHOLE_DROP_CM) < target_cm:
        return None
    lo, hi = 0.0, MAX_ARMHOLE_DROP_CM
    if _run_length(shape, weights, dx, dy, lo) >= target_cm:
        return 0.0
    while hi - lo > 1e-4:
        mid = (lo + hi) / 2.0
        if _run_length(shape, weights, dx, dy, mid) < target_cm:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def apply_drop_shoulder(segments: list, fit_anchors_scaled: list,
                        fit_anchors_y_scaled: list, drop_cm: float
                        ) -> "DropShoulderResult | None":
    """身頃の輪郭に、`drop_cm`のドロップショルダーを当てる。

    当てられない形(基準点が足りない・袖ぐりを取り出せない)ではNoneを
    返す——黙って別の形を出さない。

    【やっていること】

      1. 肩先を、**肩線(首の付け根→肩先)の延長上**へ`drop_cm`動かす。
         肩の傾きを変えずに伸ばすので、肩の線は1本の直線のまま
         つながる(折れない)。
      2. 脇の下を、真下へ`ARMHOLE_DROP`だけ下げる。
      3. 袖ぐりの途中の点は、1と2を袖ぐりに沿った距離で線形に混ぜて
         動かす(肩先では1が100%、脇の下では2が100%)。

    【なぜ2が要るか(実測)】1だけをやると、肩先は外へ出ると同時に
    **下がる**(肩線は水平ではないため)。すると肩先と脇の下が近づき、
    袖ぐりは逆に**短くなる**。実測(バスト82・肩幅37・ドロップ5cm):

        前身頃の袖ぐり  41.75cm → 37.43cm(-4.3cm)
        後ろ身頃の袖ぐり 41.34cm → 37.53cm(-3.8cm)

    袖ぐりが4cm縮むと腕が上がらない。資料が「袖ぐりを下げる」と書いて
    いるのはこのためである。ただしどの資料も**下げ幅のcmを書いていない**
    ので、こちらで不変条件を決める:

        **袖ぐりの長さを、ドロップ前と同じに保つ。**

    この条件を満たす下げ幅を二分探索で求める(`_solve_armhole_drop`)。
    出典から採った数字ではなく、このプログラムが決めた条件である。

    座標は**変形後(cm)**のものを受け取る。基準点も変形後の値
    (`ScaledPart.fit_anchors_scaled`/`fit_anchors_y_scaled`)を使う。
    """
    if drop_cm <= 0:
        return None
    shoulders = [x for role, x in fit_anchors_scaled if role == "shoulder"]
    necks = [x for role, x in fit_anchors_scaled if role == "neck"]
    underarm = [y for role, y in fit_anchors_y_scaled if role == "underarm"]
    sides = [x for role, x in fit_anchors_scaled if role == "side"]
    if not shoulders or not necks or not underarm or not sides:
        return None
    underarm_y = underarm[0]

    points = _closed(segments_to_polyline(segments))
    if len(points) < 4:
        return None

    moved = list(points)
    drops: list[float] = []
    for shoulder_x in shoulders:
        neck_x = min(necks, key=lambda x: abs(x - shoulder_x))
        side_x = min(sides, key=lambda x: abs(x - shoulder_x))
        si = _nearest_index(points, shoulder_x, underarm_y)
        ni = _nearest_index(points, neck_x, underarm_y)
        ui = _nearest_index(points, side_x, underarm_y)
        if si is None or ni is None or ui is None or si in (ni, ui):
            return None
        sx, sy = points[si]
        nx, ny = points[ni]
        length = math.hypot(sx - nx, sy - ny)
        if length <= _TOL:
            return None
        dx = (sx - nx) / length * drop_cm
        dy = (sy - ny) / length * drop_cm

        run = _armhole_run(points, si, ui, underarm_y)
        if run is None or len(run) < 2:
            return None
        # 肩先から各点までの、袖ぐりに沿った距離。
        along = [0.0]
        for a, b in zip(run, run[1:]):
            along.append(along[-1] + math.dist(points[a], points[b]))
        total = along[-1]
        if total <= _TOL:
            return None
        weights = [1.0 - v / total for v in along]
        shape = [points[k] for k in run]
        armhole_drop = _solve_armhole_drop(shape, weights, dx, dy, total)
        if armhole_drop is None:
            return None
        drops.append(armhole_drop)
        for k, idx in enumerate(run):
            w = weights[k]
            x, y = moved[idx]
            moved[idx] = (x + dx * w, y + dy * w + armhole_drop * (1.0 - w))

    out: list = [("M", [moved[0][0], moved[0][1]])]
    out.extend(("L", [x, y]) for x, y in moved[1:])
    out.append(("Z", []))
    # 脇の下の高さは1枚につき1つしか持てないので、左右のうち**浅い方**を
    # 採る。深い方を採ると、浅い側の脇線の上端が「脇の下より上」と判定
    # されて脇線から外れる(`engine/compatibility.py`の`side_seam_edges`)。
    #
    # ただし**実測では左右の下げ幅は一致する**。袖ぐりは脇の下より上に
    # しかなく、そこは左右対称だからである(胸ぐせダーツで非対称になるのは
    # 脇の下より下)。つまりこの`min`は安全側に倒しているだけで、
    # **`max`に変えても落ちるテストを作れなかった**。左右で違う下げ幅に
    # なる組み合わせを見つけたら、ここを見張るテストを足すこと。
    armhole_drop = min(drops)
    return DropShoulderResult(segments=out,
                              underarm_y_cm=underarm_y + armhole_drop,
                              armhole_drop_cm=armhole_drop)


def drop_shoulder_notes(drop_cm: float, armhole_per_arm_cm: float | None,
                        cap_height_cm: float | None,
                        upper_arm_ignored: bool = False) -> list[str]:
    """利用者へ出す説明(型紙に載る注記)。"""
    notes = [
        f"ドロップショルダー: 肩先を肩線の延長上へ{drop_cm:g}cm出しました。"
        f"袖丈はその{drop_cm:g}cmを引いた寸法で引いています。",
    ]
    if armhole_per_arm_cm and cap_height_cm:
        ratio = cap_height_cm / armhole_per_arm_cm * 100.0
        notes.append(
            f"袖山の高さは{cap_height_cm:.1f}cm(袖ぐり{armhole_per_arm_cm:.1f}cmの"
            f"{ratio:.0f}%)です。東レACS「袖山の高さはアームホール寸法の30%以下が"
            f"望ましい」に従い、作例の{DROP_CAP_HEIGHT_RATIO * 100:.0f}%を"
            "採りました。")
    notes.append(
        f"袖山のいせ込みは{DROP_SLEEVE_CAP_EASE_CM:g}cmにしています"
        "(東レACS「いせ量を減らし全体で15mm前後とする」)。")
    notes.append(
        "脇の下は、袖ぐりの長さがドロップ前と変わらないところまで下げて"
        "います。調べた資料はどれも「袖ぐりを下げる」とは書いていますが、"
        "下げ幅のcmを書いていないため、下げ幅そのものではなく"
        "「袖ぐりの長さを保つ」という条件で決めています。")
    if upper_arm_ignored:
        notes.append(
            "二の腕まわりを測っていただいていますが、ドロップショルダーでは"
            "袖幅をそこから決めていません。袖山を低くした分、袖幅は"
            "袖ぐりに合わせて広がります。")
    return notes
