"""bodice_fit.py — 身頃を「区間ごとに違う倍率」で採寸に合わせる(round14で追加)。

【なぜ必要か】
round13までの身頃は、X方向(幅)を**バスト比で一律に**拡大縮小していた
(`engine/scaling.py`の`compute_scale_factors`)。輪郭全体に同じ倍率を掛けるので、
脇線・肩先・首の付け根がすべて同じ比で外側へ動く。その結果:

  * 利用者が入力した**肩幅がまったく使われない**。肩幅はバスト比で決まる。
  * 首の開きもバスト比そのままに広がる。

実測(標準M基準・前身頃で計測):

  体型(バスト/肩幅)      入力肩幅   型紙の肩幅   誤差
  76 / 35 (細身)          35.0      33.9      -1.1cm
  100 / 38 (バスト大)      38.0      44.6      +6.6cm
  112 / 39 (バスト特大)    39.0      49.9     +10.9cm
  78 / 41 (胸小・肩広)     41.0      34.8      -6.2cm
  105 / 36 (グラマー)      36.0      46.8     +10.8cm

肩幅が+10.8cmということは、肩の縫い目が左右それぞれ5.4cm腕側へずれるという
ことで、袖ぐりの位置ごと落ちる。首幅も13.7cm→17.4cmに広がり、首ぐりが
浮く。いずれも「実際に縫って着てみて初めて分かる」類の破綻である。

【対処】X方向を1つの倍率ではなく、**基準点の間ごとに違う倍率をもつ
区分線形写像**にする。基準点はテンプレートSVGの`data-fit-x`属性に
役割つきで書いてある(`scripts/generate_templates.py`の`_bodice_anchors`):

  side     … 脇線。バスト比で動く(=従来通り。胴回りはバストで決まる)
  shoulder … 肩先。**入力された肩幅**で決まる
  neck     … 首の付け根。文化式の前ネック幅(バスト/24+3.4)で決まる
  cf       … 中心前(中心後)。左右対称の中心
  cut      … 前開きパネルの裁ち割り線。中心前からの距離(見返し幅)は一定

基準点を engine 側の定数ではなくテンプレート自身に持たせているのは、
テンプレートの寸法を変えたときに基準点だけ古いまま残る「二重管理のずれ」を
構造的に防ぐため(このプロジェクトでは過去にフォントのサブセットで同じ
失敗をしている。`engine/pdf_export.py`の`PDF_STATIC_TEXTS`参照)。

【この方式の限界(正直な注記)】
区分線形写像は、基準点そのものは狙った位置へ正確に運ぶが、区間の内部に
ある**ベジエ曲線の制御点**は、その制御点が乗っている区間の倍率で動く。
袖ぐり曲線の肩先側の制御点は、えぐれ量のぶんだけ肩線側の区間へはみ出して
いるため(`_armhole_d`参照)、肩幅を大きく動かすと袖ぐりのカーブの張り方が
わずかに変わる。実測した影響は後述の`ARMHOLE_CURVE_NOTE`にまとめてある。
"""

from __future__ import annotations

#: `neck_half_cm`の基準となる標準バスト。engine.measurements.STANDARD_M と
#: 同じ値だが、循環importを避けるためここでは数値で持ち、
#: tests/test_bodice_fit.py で STANDARD_M.bust と一致することを確認している。
_STANDARD_BUST_CM = 83.0

#: 首幅(中心から片側)を求める式の係数。文化式婦人原型の前ネック幅
#: 「B/24 + 3.4」をそのまま使う。バスト83cmで6.858cmになる。
#: この式は`scripts/generate_templates.py`の`BODICE_NECK_HALF`が
#: **この関数を呼んで**標準値を決めているので、二重管理にはならない。
NECK_HALF_DIVISOR = 24.0
NECK_HALF_CONST = 3.4


def neck_half_cm(bust_cm: float) -> float:
    """バストから首幅(中心から片側)を求める(文化式の前ネック幅)。"""
    return bust_cm / NECK_HALF_DIVISOR + NECK_HALF_CONST


# --- 区間がつぶれないための最小幅 -------------------------------------------
#
# 肩先を入力どおりに置くと、バストと肩幅の組み合わせによっては区間が
# つぶれる(あるいは順序が入れ替わる)ことがある。例えばバスト60cm・肩幅45cm
# なら、半身の幅は(60+8)/4=17cmしか無いのに肩先は中心から22.5cmの位置に
# 来てしまい、脇線より外側になる。
#
# 下限値を決めるにあたり、まず「どこまで詰めると輪郭が壊れるか」を実測した
# (袖ぐり幅を6.0cmから0.1cm刻みで0.2cmまで詰め、前身頃・後身頃・Vネック・
# ボートネック・前開きパネルのそれぞれで、shapelyによる自己交差判定と
# 縫い代1cmのオフセットが成立するかを確認した)。結果は**どこでも壊れな
# かった**。袖ぐり曲線の制御点も同じ区間の倍率で一緒に詰まるため、カーブは
# 平たくなるだけで折り返さない(袖ぐり片側の弧長は幅6.0cmで20.17cm、
# 0.2cmでも18.59cmと連続的に変化するだけだった)。
#
# つまりここの下限は「幾何が壊れないための値」ではなく、
# **区分線形写像の単調性(順序)を保つためのガード**である。そのため
# 現実的な体型では絶対に効かない小さな値にしてある。効いた場合は
# `bodice_fit_clamp_warnings`が利用者に開示する(黙って別の寸法にしない)。
# 再現手順は tests/test_bodice_fit.py の
# `test_narrow_armhole_stays_a_valid_polygon` に残してある。
#: 脇線から肩先までの水平距離の下限(=袖ぐりの幅)。
MIN_ARMHOLE_WIDTH_CM = 0.5
#: 肩先から首の付け根までの水平距離の下限(=肩線の水平方向の長さ)。
MIN_SHOULDER_RUN_CM = 1.0

#: 上の「正直な注記」で触れた、袖ぐり曲線の制御点による誤差の実測値。
#: README と tests/test_bodice_fit.py から参照する。
#:
#: 【測り方】新しい肩先・脇線・袖ぐり深さに対して、えぐれ量(scoop=2.5cm)を
#: テンプレートと同じままにして袖ぐり曲線を引き直したものを「正解」とし、
#: 区分線形写像の結果と比べた(前身頃・片側の袖ぐり弧長):
#:
#:   体型(バスト/肩幅)   写像後    引き直し    差
#:   83 / 37 (標準)     19.493   19.493   +0.000 (±0.00%)
#:   76 / 35            18.449   18.619   -0.170 (-0.92%)
#:   100 / 38           21.788   21.233   +0.556 (+2.62%)
#:   112 / 39           23.829   22.950   +0.879 (+3.83%)
#:   78 / 41            19.740   20.040   -0.300 (-1.50%)
#:   105 / 36           22.980   22.239   +0.741 (+3.33%)
#:   140 / 30 (極端)    30.751   29.637   +1.114 (+3.76%)
#:   60 / 50  (極端)    18.629   19.130   -0.501 (-2.62%)
#:
#: 標準Mでは写像が恒等になるため誤差0で、離れるほど最大約4%(片側で約1cm)
#: ずれる。袖は「実測した袖ぐりの長さ」に合わせて作る
#: (engine/scaling.pyのscale_sleeve_to_cap_length)ので袖付けは常に成立し、
#: 残るのは「袖ぐりが理想より数%ゆるい/きつい」という程度の差である。
#: 直すには輪郭を「肩線・袖ぐり・脇線」の意味単位に分解して曲線ごとに
#: 引き直す仕組みが必要で、今回は踏み込んでいない。
ARMHOLE_CURVE_MAX_ERROR_RATIO = 0.04
ARMHOLE_CURVE_NOTE = (
    "区分線形写像では袖ぐり曲線の制御点が肩線側の区間の倍率で動くため、"
    "袖ぐりの曲線長が理想の引き直しより最大約4%(片側で約1cm)ずれる"
    "(標準Mでは誤差0)。袖はこの実測値に合わせて作るため袖付けは成立する。"
)


class BodiceFitError(ValueError):
    """基準点の指定が壊れている場合に投げる。"""


def parse_fit_anchors(text: str | None) -> list[tuple[str, float]]:
    """`data-fit-x`属性("role:x role:x ...")を [(role, x), ...] にする。

    x の昇順で返す。役割名が未知、または数値でない場合は例外にする
    (静かに無視すると「基準点が無いので従来通り一律スケーリング」に
    落ちてしまい、直したはずの不具合が黙って復活するため)。
    """
    if not text:
        return []
    anchors: list[tuple[str, float]] = []
    for token in text.split():
        role, sep, value = token.partition(":")
        if not sep:
            raise BodiceFitError(f"data-fit-xの書式が不正です: {token!r}")
        if role not in ("side", "shoulder", "neck", "cf", "cut"):
            raise BodiceFitError(f"data-fit-xに未知の役割があります: {role!r}")
        try:
            anchors.append((role, float(value)))
        except ValueError as exc:
            raise BodiceFitError(f"data-fit-xの座標が数値ではありません: {token!r}") from exc
    anchors.sort(key=lambda a: a[1])
    return anchors


def _clamped_half_widths(half_width_dst: float, shoulder_half: float, neck_half: float,
                          src_proportions: tuple[float, float]) -> tuple[float, float]:
    """中心からの距離(肩先・首の付け根)を、区間がつぶれない範囲へ収める。

    half_width_dst は変形後の「中心から脇線まで」の距離。
    src_proportions は、テンプレート自身の (肩先, 首の付け根) が
    「中心から脇線まで」の何割の位置にあるかで、最後の手段で使う。
    返り値は (肩先, 首の付け根) の中心からの距離。
    """
    # 1. 肩先は脇線より内側に MIN_ARMHOLE_WIDTH_CM 以上入っていること。
    shoulder_half = min(shoulder_half, half_width_dst - MIN_ARMHOLE_WIDTH_CM)
    # 2. 首の付け根は肩先より内側に MIN_SHOULDER_RUN_CM 以上入っていること。
    neck_half = min(neck_half, shoulder_half - MIN_SHOULDER_RUN_CM)
    # 3. 1と2の両立が不可能なほど半身が狭い場合は、順序だけは必ず保てるよう
    #    テンプレート自身の比率で配分する(=round13までと同じ一律スケーリング)。
    if neck_half <= 0.0 or shoulder_half <= 0.0:
        shoulder_ratio, neck_ratio = src_proportions
        shoulder_half = half_width_dst * shoulder_ratio
        neck_half = half_width_dst * neck_ratio
    return shoulder_half, neck_half


def build_x_map(anchors: list[tuple[str, float]], bust_cm: float,
                 shoulder_width_cm: float, bust_scale: float) -> list[tuple[float, float]]:
    """基準点から、X方向の区分線形写像の節点 [(変形前x, 変形後x), ...] を作る。

    bust_scale は「脇線を動かす倍率」(=バスト比。クランプ済みの値を渡す)。
    テンプレートは中心前(cf)について左右対称に作られているので、
    変形後の位置は「cf からの符号つき距離」で決める。
    """
    if not anchors:
        return []
    cf_src = next((x for role, x in anchors if role == "cf"), None)
    if cf_src is None:
        raise BodiceFitError("data-fit-xに中心前(cf)がありません。")

    cf_dst = cf_src * bust_scale

    # 脇線(side)は最も外側の基準点。半身の幅(中心→脇線)を変形後の値で求める。
    side_offsets = [abs(x - cf_src) for role, x in anchors if role == "side"]
    if not side_offsets:
        raise BodiceFitError("data-fit-xに脇線(side)がありません。")
    half_width_dst = max(side_offsets) * bust_scale

    shoulder_offsets = [abs(x - cf_src) for role, x in anchors if role == "shoulder"]
    neck_offsets = [abs(x - cf_src) for role, x in anchors if role == "neck"]
    if not shoulder_offsets or not neck_offsets:
        raise BodiceFitError("data-fit-xに肩先(shoulder)または首の付け根(neck)がありません。")

    # 肩先: 入力された肩幅の半分をそのまま使う。
    shoulder_half = shoulder_width_cm / 2.0
    # 首の付け根: テンプレートが設計上どれだけ首を開いているか(ボートネックは
    # 標準の1.75倍)という「デザインの比」を保ったまま、標準の首幅だけを
    # 採寸由来の値へ差し替える。
    neck_half_std = neck_half_cm(_STANDARD_BUST_CM)
    design_ratio = neck_offsets[0] / neck_half_std
    neck_half = neck_half_cm(bust_cm) * design_ratio

    half_width_src = max(side_offsets)
    shoulder_half, neck_half = _clamped_half_widths(
        half_width_dst, shoulder_half, neck_half,
        (shoulder_offsets[0] / half_width_src, neck_offsets[0] / half_width_src))

    dst_by_role = {
        "cf": 0.0,
        "side": half_width_dst,
        "shoulder": shoulder_half,
        "neck": neck_half,
    }

    knots: list[tuple[float, float]] = []
    for role, x_src in anchors:
        offset_src = x_src - cf_src
        sign = 1.0 if offset_src >= 0 else -1.0
        if role == "cut":
            # 見返し幅は体型によらず一定。cfからの距離をそのまま保つ。
            offset_dst = offset_src
        else:
            offset_dst = sign * dst_by_role[role]
        knots.append((x_src, cf_dst + offset_dst))

    knots.sort(key=lambda k: k[0])
    # 変形後も順序(単調性)が保たれていることを確認する。ここが崩れると
    # 輪郭が折り返して自己交差した型紙になる。
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if not (x1 > x0 and y1 > y0):
            raise BodiceFitError(
                f"体型合わせの基準点が単調になりません({x0}->{y0}, {x1}->{y1})。"
            )
    return knots


def effective_shoulder_width_cm(anchors: list[tuple[str, float]], bust_cm: float,
                                 shoulder_width_cm: float, bust_scale: float) -> float | None:
    """実際に型紙へ反映される肩幅(cm)を返す。基準点が無ければ None。

    `build_x_map`と同じ手順で肩先の位置を求めるが、返すのは肩幅そのもの
    (=中心からの距離×2)。入力どおりに置けない極端な体型でクランプが
    効いたかどうかを、利用者へ開示するために使う
    (`engine/scaling.py`の`bodice_fit_clamp_warnings`)。
    """
    if not anchors:
        return None
    knots = build_x_map(anchors, bust_cm, shoulder_width_cm, bust_scale)
    cf_src = next(x for role, x in anchors if role == "cf")
    cf_dst = cf_src * bust_scale
    shoulder_dsts = [dst for (src, dst), (role, _x) in zip(knots, sorted(anchors, key=lambda a: a[1]))
                     if role == "shoulder"]
    if not shoulder_dsts:
        return None
    return max(abs(d - cf_dst) for d in shoulder_dsts) * 2.0


def map_x(x: float, knots: list[tuple[float, float]]) -> float:
    """区分線形写像で1つのx座標を変換する。

    節点の外側は、いちばん端の区間の傾きをそのまま延長する
    (袖ぐり曲線の制御点のように、脇線より外へはみ出す制御点があるため)。
    """
    if not knots:
        return x
    if len(knots) == 1:
        return x - knots[0][0] + knots[0][1]
    if x <= knots[0][0]:
        (x0, y0), (x1, y1) = knots[0], knots[1]
    elif x >= knots[-1][0]:
        (x0, y0), (x1, y1) = knots[-2], knots[-1]
    else:
        lo = 0
        for i in range(len(knots) - 1):
            if knots[i][0] <= x <= knots[i + 1][0]:
                lo = i
                break
        (x0, y0), (x1, y1) = knots[lo], knots[lo + 1]
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def remap_segments_x(segments: list[tuple[str, list[float]]],
                      knots: list[tuple[float, float]],
                      ry: float) -> list[tuple[str, list[float]]]:
    """X は区分線形写像で、Y は一律 ry 倍で変形する。

    `engine.svgpath.scale_segments`のX方向だけを差し替えたもの。
    ベジエの制御点も同じ写像を通す(上の「限界」の注記を参照)。
    """
    out: list[tuple[str, list[float]]] = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "H":
            out.append(("H", [map_x(nums[0], knots)]))
        elif cmd == "V":
            out.append(("V", [nums[0] * ry]))
        else:
            vals = [map_x(v, knots) if k % 2 == 0 else v * ry
                    for k, v in enumerate(nums)]
            out.append((cmd, vals))
    return out
