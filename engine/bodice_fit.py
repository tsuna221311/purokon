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

from .blocks import ADULT_FEMALE, Block

#: `neck_half_cm`の基準となる標準バスト。engine.measurements.STANDARD_M と
#: 同じ値だが、循環importを避けるためここでは数値で持ち、
#: tests/test_bodice_fit.py で STANDARD_M.bust と一致することを確認している。
_STANDARD_BUST_CM = 83.0
#: 同じく標準ヒップ(round25で股上の式に使う)。
_STANDARD_HIP_CM = 91.0

#: 首幅(中心から片側)を求める式の係数。文化式婦人原型の前ネック幅
#: 「B/24 + 3.4」をそのまま使う。バスト83cmで6.858cmになる。
#: この式は`scripts/generate_templates.py`の`BODICE_NECK_HALF`が
#: **この関数を呼んで**標準値を決めているので、二重管理にはならない。
#:
#: 【round42】数値そのものは`engine/blocks.py`の`ADULT_FEMALE`が持つように
#: なった(原型ごとに式が違うため)。ここの定数はその値を読み出しているだけで、
#: 二重管理にはならない。既存の名前を残してあるのは、
#: `scripts/generate_templates.py`とテストが参照しているため。
NECK_HALF_DIVISOR = ADULT_FEMALE.neck_half.divisor
NECK_HALF_CONST = ADULT_FEMALE.neck_half.const


def neck_half_cm(bust_cm: float, block: Block = ADULT_FEMALE) -> float:
    """バストから首幅(中心から片側)を求める(文化式の前ネック幅)。

    block: round42。どの原型の式で引くか(`engine/blocks.py`)。
        既定は成人女子で、round41までとまったく同じ値になる。
    """
    return block.neck_half.value(bust_cm)


#: 前の襟ぐりの深さが、前ネック幅よりどれだけ深いか(cm)。新文化式の
#: 「前襟ぐり深さ = 前襟ぐり幅 + 0.5」から(round29)。
#: 乳下がり(前中央で**首の付け根**からBPまで)を型紙の座標へ置き直すのに要る。
FRONT_NECK_DEPTH_EXTRA_CM = 0.5


def front_neck_depth_cm(bust_cm: float, block: Block = ADULT_FEMALE) -> float:
    """肩の高さの線から、前中央の首の付け根までの深さ(cm)。"""
    return neck_half_cm(bust_cm, block) + FRONT_NECK_DEPTH_EXTRA_CM


#: 身頃の着用ゆとり(cm)。出来上がりの胴回り = バスト + この値。
#:
#: 布帛の身頃で一般的な範囲の値で、テンプレートの設計値そのもの
#: (`scripts/generate_templates.py`の`BODICE_W`がこの値を使って
#: (83+8)/2=45.5cm という1枚の幅を決めている。あちらはここをimportする)。
#:
#: 【round23で「一定」にした】round22まで、身頃の幅はバスト比で一律に
#: 拡大縮小していた。テンプレート(バスト83+ゆとり8)ごと引き伸ばすので、
#: **ゆとりまでバストに比例して増減していた**。実測(出来上がり胴回り):
#:
#:   バスト  出来上がり  ゆとり
#:     60      65.8      5.8   ← 布帛の身頃としてはきつい
#:     83      91.0      8.0
#:    110     120.6     10.6
#:    130     142.5     12.5   ← ぶかぶか
#:
#: ゆとりは「そのデザインをどれだけゆったり着るか」という設計上の量であって、
#: 体の大きさに比例して増えるものではない(実際のグレーディングでも、
#: サイズを変えてもゆとりは一定に保つ)。同じ考え方は下半身パーツで既に
#: 採用されていて(`engine/part_specs.py`の`lower_garment_x_scale`は
#: ウエスト+2cm・ヒップ+4cmという**一定の**ゆとりで倍率を決めている)、
#: 身頃だけが取り残されていた。
BODICE_EASE_CM = 8.0


def bodice_x_scale(bust_cm: float, ease_cm: float = BODICE_EASE_CM) -> float:
    """身頃の幅方向の倍率。ゆとりを一定に保つ(round23。round24でゆとりを可変に)。

    テンプレートの半身幅は (83 + 8) / 4 = 22.75cm なので、この倍率を掛けると
    半身幅は (bust + ease) / 4 になり、前後2枚の合計が bust + ease になる。
    分母のゆとりが常にテンプレートの設計値(8cm)なのはそのためで、
    `ease_cm`はあくまで**出来上がりに欲しいゆとり**である。
    """
    return ((bust_cm + ease_cm)
            / (_STANDARD_BUST_CM + BODICE_EASE_CM))


def bodice_bust_cm_for_scale(scale: float, ease_cm: float = BODICE_EASE_CM) -> float:
    """`bodice_x_scale`の逆。ある倍率に相当するバスト(cm)を返す。

    クランプの境界を利用者へ説明するのに使う(倍率の決め方と、それを
    説明する文言を同じ式から作るため。別々に書くと、変形の限界と
    注記に書かれた数値がずれる)。
    """
    return scale * (_STANDARD_BUST_CM + BODICE_EASE_CM) - ease_cm


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


#: `data-fit-x`に書ける役割名。
FIT_X_ROLES = ("side", "shoulder", "neck", "cf", "cut")
#: 身頃の`data-fit-y`が持つ役割名(round23)。
BODICE_FIT_Y_ROLES = ("neck", "underarm", "waist", "hem")
#: 袖の`data-fit-y`が持つ役割名(round24)。
SLEEVE_FIT_Y_ROLES = ("cap", "underarm", "hem")
#: パンツの`data-fit-y`が持つ役割名(round25)。
PANTS_FIT_Y_ROLES = ("waist", "crotch", "hem")
#: `data-fit-y`に書ける役割名(解析時に許すものの全体)。
FIT_Y_ROLES = tuple(dict.fromkeys(
    BODICE_FIT_Y_ROLES + SLEEVE_FIT_Y_ROLES + PANTS_FIT_Y_ROLES))


def parse_fit_anchors(text: str | None,
                       roles: tuple[str, ...] = FIT_X_ROLES) -> list[tuple[str, float]]:
    """`data-fit-x` / `data-fit-y`属性("role:x role:x ...")を [(role, x), ...] にする。

    座標の昇順で返す。役割名が未知、または数値でない場合は例外にする
    (静かに無視すると「基準点が無いので従来通り一律スケーリング」に
    落ちてしまい、直したはずの不具合が黙って復活するため)。
    """
    if not text:
        return []
    anchors: list[tuple[str, float]] = []
    for token in text.split():
        role, sep, value = token.partition(":")
        if not sep:
            raise BodiceFitError(f"体型合わせの基準点の書式が不正です: {token!r}")
        if role not in roles:
            raise BodiceFitError(f"体型合わせの基準点に未知の役割があります: {role!r}")
        try:
            anchors.append((role, float(value)))
        except ValueError as exc:
            raise BodiceFitError(f"体型合わせの基準点の座標が数値ではありません: {token!r}") from exc
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
                 shoulder_width_cm: float, bust_scale: float,
                 block: Block = ADULT_FEMALE) -> list[tuple[float, float]]:
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
    # テンプレートは成人女子の首幅で描かれているので、「デザインの比」は
    # 必ず成人女子の標準値との比で測る(round42。ここに子ども原型の式を
    # 入れると、同じテンプレートが別のデザイン比に化ける)。
    neck_half_std = neck_half_cm(_STANDARD_BUST_CM, ADULT_FEMALE)
    design_ratio = neck_offsets[0] / neck_half_std
    neck_half = neck_half_cm(bust_cm, block) * design_ratio

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
                                 shoulder_width_cm: float, bust_scale: float,
                                 block: Block = ADULT_FEMALE) -> float | None:
    """実際に型紙へ反映される肩幅(cm)を返す。基準点が無ければ None。

    `build_x_map`と同じ手順で肩先の位置を求めるが、返すのは肩幅そのもの
    (=中心からの距離×2)。入力どおりに置けない極端な体型でクランプが
    効いたかどうかを、利用者へ開示するために使う
    (`engine/scaling.py`の`bodice_fit_clamp_warnings`)。
    """
    if not anchors:
        return None
    knots = build_x_map(anchors, bust_cm, shoulder_width_cm, bust_scale, block)
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
                      ry: float,
                      y_knots: list[tuple[float, float]] | None = None
                      ) -> list[tuple[str, list[float]]]:
    """X は区分線形写像で、Y は一律 ry 倍(または y_knots による区分線形)で変形する。

    `engine.svgpath.scale_segments`のX方向だけを差し替えたもの。
    ベジエの制御点も同じ写像を通す(上の「限界」の注記を参照)。

    round23で `y_knots` を追加した。袖ぐりの深さをバストに応じて変えるため、
    Y方向も「首の付け根の線 / 脇の下の線 / 裾」を節点とする区分線形写像に
    できるようにしてある(`build_y_map`参照)。省略すれば従来どおり一律 ry 倍。
    """
    def _y(value: float) -> float:
        return map_x(value, y_knots) if y_knots else value * ry

    out: list[tuple[str, list[float]]] = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "H":
            out.append(("H", [map_x(nums[0], knots)]))
        elif cmd == "V":
            out.append(("V", [_y(nums[0])]))
        else:
            vals = [map_x(v, knots) if k % 2 == 0 else _y(v)
                    for k, v in enumerate(nums)]
            out.append((cmd, vals))
    return out


#: 袖ぐりの深さが、バスト1cmあたり何cm深くなるか(round23)。
#:
#: 文化式婦人原型の袖ぐり深さ「B/12 + 13.7」の**増分**をそのまま使う。
#: 絶対値をこの式に置き換えないのは、このリポジトリの身頃テンプレートが
#: 首の付け根の線から測って23.5cmという、文化式とは基準線の取り方が違う
#: 値を実測で選んでいるため(scripts/generate_templates.pyの
#: `BODICE_AH_DEPTH`のコメント参照)。標準M(バスト83)では増分0になるので、
#: 標準サイズの型紙はround22までと1mmも変わらない。
#:
#: 【round22までの実測】袖ぐりの深さは身長比だけで決まっていて、バストが
#: 変わってもほとんど動かなかった:
#:
#:   バスト  袖ぐり深さ  文化式の目安   差
#:     60      23.02      21.58     +1.43
#:     83      23.43      23.50     -0.07
#:    110      23.50      25.75     -2.25
#:    130      23.50      27.42     -3.92   ← 脇の下が4cm浅い
#:
#: 袖ぐりが4cm浅いと、腕を上げられないどころか脇が食い込む。逆に小さい
#: サイズでは1.4cm深く、袖ぐりが浮く。
ARMHOLE_DEPTH_PER_BUST_CM = 1.0 / 12.0


def armhole_depth_cm(template_depth_cm: float, bust_cm: float,
                      height_scale: float, block: Block = ADULT_FEMALE,
                      height_cm: float | None = None) -> float:
    """変形後の袖ぐり深さ(首の付け根の線から脇の下まで)。

    丈方向の伸縮(身長比)はそのまま効かせたうえで、バストが標準から
    離れたぶんだけ文化式の増分を足す。

    round42: 原型が袖ぐり深さの**絶対値**の式を持っている場合
    (子ども原型の「身長/8 + 1」)は、テンプレートからの増分ではなく
    その式をそのまま使う。増分方式はテンプレートの23.5cmを起点にしていて、
    起点が成人女子の体型に紐づいているためである。実測(子ども):

        身長   増分方式   子ども原型   差
        120     15.93     16.00     +0.07
        130     17.75     17.25     -0.50
        140     19.74     18.50     -1.24
        150     21.73     19.75     -1.98

    身長150cmで袖ぐりが2cm深い。脇の下が2cm下がると、腕を下ろしたときに
    脇に布がたまる。
    """
    if block.armhole_depth is not None:
        if height_cm is None:
            raise ValueError(
                f"原型「{block.label}」の袖ぐり深さは身長から決まりますが、"
                "身長が渡されていません。")
        return block.armhole_depth.value(bust_cm, height_cm)
    return (template_depth_cm * height_scale
            + (bust_cm - _STANDARD_BUST_CM) * ARMHOLE_DEPTH_PER_BUST_CM)


def build_y_map(anchors: list[tuple[str, float]], bust_cm: float,
                 height_scale: float, block: Block = ADULT_FEMALE,
                 height_cm: float | None = None) -> list[tuple[float, float]]:
    """Y方向の区分線形写像の節点を作る(round23)。

    `data-fit-y`("neck:… underarm:… hem:…")から、

      首の付け根の線 … 身長比でそのまま動く(丈の基準)
      脇の下の線     … 身長比 + バストによる増分(`armhole_depth_cm`)
      裾             … 身長比でそのまま動く(着丈は身長で決まる)

    という3点を通す写像を作る。裾を身長比のままにしてあるので、
    **着丈は変わらず、袖ぐりの深さだけが動く**(その分、脇線が短くなる)。
    節点の外側(タートルネックの台襟など)は端の区間の傾きで延長する。
    """
    by_role = {role: x for role, x in anchors}
    neck = by_role.get("neck")
    underarm = by_role.get("underarm")
    waist = by_role.get("waist")
    hem = by_role.get("hem")
    if neck is None or underarm is None or hem is None:
        return []
    neck_dst = neck * height_scale
    depth = armhole_depth_cm(underarm - neck, bust_cm, height_scale,
                              block, height_cm)
    hem_dst = hem * height_scale
    underarm_dst = neck_dst + depth
    # 順序が崩れる(脇の下が裾より下に来る等)入力では写像を作らない。
    if not (neck_dst < underarm_dst < hem_dst):
        return []
    knots = [(neck, neck_dst), (underarm, underarm_dst), (hem, hem_dst)]
    if waist is not None and underarm < waist < hem:
        # round26: ウエストの線は身長比でそのまま動く。袖ぐりが深くなった
        # ぶん脇線が短くなるのは「脇の下〜ウエスト」の側で吸収する。
        waist_dst = waist * height_scale
        if underarm_dst < waist_dst < hem_dst:
            knots.insert(2, (waist, waist_dst))
    return knots

#: 標準M(バスト83)で実際に生成される、片腕ぶんの袖ぐり周長(cm)。
#:
#: 袖山の高さを「袖ぐりに比例」させるための基準。テンプレートの袖山12cmは
#: この袖ぐりに対して設計された値なので、袖ぐりがこの値のときに倍率1.0に
#: なるようにしてある(標準サイズの型紙は変わらない)。
#: 実測値であり、tests/test_sleeve_cap_height.py が実際に生成した身頃から
#: 測った値と一致することを検証している。
#:
#: 【round31で39.72→40.59へ更新した理由】袖ぐりの点(胸幅・背幅)を新文化式の
#: 位置へ合わせた(`fit_armhole_width`)結果、標準Mの袖ぐりが実際に0.87cm
#: 長くなった。**基準の方が実物とずれたまま**だと、標準サイズなのに袖山の
#: 倍率が1.0からずれる(=標準サイズの袖が理由なく変わる)。値を合わせに
#: 行ったのではなく、実物が動いたぶんだけ基準を追随させている。
#: 標準Mの袖山の高さは、この更新の結果12.00cm→12.26cmになる。
#: 【round43で40.59→41.75へ更新した理由】肩傾斜を製図の角度(前22°/後ろ18°)
#: で引き直した結果、肩先が前0.60cm・後ろ0.65cm上がり、標準Mの袖ぐりが
#: 実際に1.16cm長くなった。round31と同じで、**基準の方が実物とずれたまま**
#: だと標準サイズなのに袖山の倍率が1.0からずれる(=標準サイズの袖が理由なく
#: 変わる)。数字を合わせに行ったのではなく、実物が動いたぶんだけ基準を
#: 追随させている。
STANDARD_ARMHOLE_PER_ARM_CM = 41.75


def sleeve_cap_height_scale(armhole_per_arm_cm: float) -> float:
    """袖山の高さの倍率を、実際の袖ぐり周長から求める(round24)。

    【round23までの問題】袖山の高さは袖丈比だけで動いていた。つまり
    **袖ぐりが大きくなっても袖山は高くならず**、袖山カーブの長さを袖ぐりに
    合わせるために幅ばかりが広がっていた。実測(袖幅=二の腕まわり・平置き):

      バスト  袖ぐり(片腕)  round23の袖幅  袖山の高さ
        60      34.63        25.5        12.0
        83      39.72        32.0        12.0
       110      49.92        44.2        12.0
       130      58.69        54.2        12.0   ← 二の腕に対して大きすぎる

    袖山の高さは袖ぐり寸法に比例させるのが製図の定石(目安は袖ぐり÷3)で、
    テンプレートの12cmも「袖ぐり39.7cmに対して÷3の目安に近い値」として
    選ばれている(scripts/generate_templates.pyのコメント)。倍率1.0のまま
    据え置いていたのは、単にその関係を実装していなかったためである。
    """
    if armhole_per_arm_cm <= 0:
        return 1.0
    return armhole_per_arm_cm / STANDARD_ARMHOLE_PER_ARM_CM


def apply_design_length_to_y_map(knots: list[tuple[float, float]],
                                  design_length_cm: float,
                                  keep_above_role: str,
                                  anchors: list[tuple[str, float]],
                                  ) -> list[tuple[float, float]] | None:
    """出来上がりの丈を指定どおりにしつつ、**上半分は動かさない**写像を作る。

    round57で追加。それまで丈の指定(`design_length_cm`)は、パーツ全体の
    Y倍率を`指定の丈 ÷ テンプレートの丈`で置き換えていた。スカートや
    パンツならそれでよい——上端がウエストで、縫い合わせる相手の形が
    丈で変わらないからである。

    **袖と身頃では、それをやると縫えなくなる。**

      袖   … 上半分は袖山(cap〜underarm)で、その曲線の長さが袖ぐりと
             合うように作ってある。全体を縦に縮めると袖山も縮み、
             袖ぐりより短くなって**袖が付かない**。
      身頃 … 上半分は襟ぐりと袖ぐり(neck〜underarm)で、ここは採寸から
             決まる。全体を縮めると袖ぐりが浅くなり、**袖が入らない**。

    そこで、`keep_above_role`(袖なら"underarm"、身頃なら"underarm")の
    線より上は**すでに決まった写像のまま**にし、そこから裾までの区間だけを
    伸縮させて、全体の丈を指定値に合わせる。

    Args:
        knots: ここまでに決まった (元のY, 変形後のY) の節点。
        design_length_cm: 出来上がりの丈(cm)。パーツの上端から裾まで。
        keep_above_role: この役割の線より上は動かさない。
        anchors: `data-fit-y`の (役割, 元のY)。

    Returns:
        新しい節点。区間が作れない場合(節点が足りない・指定が短すぎて
        上半分に食い込む等)は**None**を返す——無理に縮めて袖山を壊すより、
        丈の指定を効かせない方がまだよい。呼び出し側はNoneを受けたら
        利用者にその旨を伝える。
    """
    if not knots or design_length_cm <= 0:
        return None
    by_role = {role: y for role, y in anchors}
    keep_y = by_role.get(keep_above_role)
    if keep_y is None:
        return None
    # 変形後の「動かさない線」の位置を、いまの写像から読む。
    kept_dst = _interpolate_knots(knots, keep_y)
    if kept_dst is None:
        return None
    top_src, top_dst = knots[0]
    hem_src, hem_dst = knots[-1]
    if not (top_src < keep_y < hem_src):
        return None
    target_hem_dst = top_dst + design_length_cm
    remaining = target_hem_dst - kept_dst
    # 「動かさない線」より下が無くなる(または反転する)指定は受け付けない。
    if remaining <= 0:
        return None
    current = hem_dst - kept_dst
    if current <= 0:
        return None
    ratio = remaining / current
    adjusted: list[tuple[float, float]] = []
    for src, dst in knots:
        if src <= keep_y:
            adjusted.append((src, dst))
        else:
            adjusted.append((src, kept_dst + (dst - kept_dst) * ratio))
    if not any(src > keep_y for src, _ in adjusted):
        # 裾側の節点が無いと、区間として伸ばす先が無い。
        return None
    return adjusted


def _interpolate_knots(knots: list[tuple[float, float]], src_y: float) -> float | None:
    """区分線形写像の節点から、その元Yに対応する変形後Yを読む。"""
    if not knots:
        return None
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= src_y <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (src_y - x0) / (x1 - x0)
    return None


def build_sleeve_y_map(anchors: list[tuple[str, float]], cap_scale: float,
                        length_scale: float) -> list[tuple[float, float]]:
    """袖のY方向の区分線形写像の節点を作る(round24)。

    `data-fit-y`("cap:… underarm:… hem:…")から、

      袖山のてっぺん … そのまま(y=0)
      袖山の高さ     … 袖ぐりに比例(`sleeve_cap_height_scale`)
      袖口           … 袖丈比(=丈は従来どおり袖丈で決まる)

    という3点を通す写像を作る。**袖丈は変わらず、袖山の高さだけが動く**。
    順序が崩れる場合は写像を作らない(呼び出し側が一律倍率へ落ちる)。
    """
    by_role = {role: y for role, y in anchors}
    cap = by_role.get("cap")
    underarm = by_role.get("underarm")
    hem = by_role.get("hem")
    if cap is None or underarm is None or hem is None:
        return []
    cap_dst = cap * length_scale
    underarm_dst = cap_dst + (underarm - cap) * cap_scale
    hem_dst = hem * length_scale
    if not (cap_dst < underarm_dst < hem_dst):
        return []
    return [(cap, cap_dst), (underarm, underarm_dst), (hem, hem_dst)]


#: 股上(ウエスト〜股ぐり)が、ヒップ1cmあたり何cm深くなるか(round25)。
#:
#: 製図で広く使われる目安「股上 = ヒップ/4 + 2〜3cm」の**増分**をそのまま
#: 使う。絶対値をこの式に置き換えないのは、テンプレートの股上25cmが
#: 「身長/8 + 5 = 24.75 → 25cm」という身長基準で選ばれているためで、
#: 標準M(ヒップ91)では増分0になり型紙が変わらないようにしてある。
#: ちなみに標準Mでは、ヒップ基準の目安(91/4+2 = 24.75)と身長基準の目安が
#: ぴったり一致する。
#:
#: 【round24までの実測】股上は身長比だけで決まっていて、ヒップが変わっても
#: 動かなかった(身長158cm固定):
#:
#:   ヒップ  股上(型紙)  目安(H/4+2)   差
#:     80      25.00      22.00     +3.00
#:     91      25.00      24.75     +0.25
#:    105      25.00      28.25     -3.25
#:    120      25.00      32.00     -7.00   ← 股ぐりが7cm浅い
#:
#: 股上が7cm浅いパンツは、座れないどころか立っていても股が食い込む。
PANTS_RISE_PER_HIP_CM = 0.25


def pants_rise_cm(template_rise_cm: float, hip_cm: float,
                   height_scale: float) -> float:
    """変形後の股上(ウエスト〜股ぐり)。

    丈方向の伸縮(身長比)はそのまま効かせたうえで、ヒップが標準から離れた
    ぶんだけ目安の増分を足す。
    """
    return (template_rise_cm * height_scale
            + (hip_cm - _STANDARD_HIP_CM) * PANTS_RISE_PER_HIP_CM)


def build_pants_y_map(anchors: list[tuple[str, float]], hip_cm: float,
                       height_scale: float) -> list[tuple[float, float]]:
    """パンツのY方向の区分線形写像の節点を作る(round25)。

    `data-fit-y`("waist:… crotch:… hem:…")から、

      ウエスト … そのまま(y=0)
      股ぐり   … 身長比 + ヒップによる増分(`pants_rise_cm`)
      裾       … 股ぐりから下(股下)は身長比で伸縮

    という3点を通す写像を作る。股下は脚の長さ(身長)で、股上は体の厚み
    (ヒップ)で決まる**別々の量**なので、総丈は両者の和として変わる
    (身頃の着丈を固定したのとは事情が違う。ヒップが大きい人は股ぐりから
    上に必要な布が増えるぶん、ウエストから裾までが長くなるのが正しい)。
    """
    by_role = {role: y for role, y in anchors}
    waist = by_role.get("waist")
    crotch = by_role.get("crotch")
    hem = by_role.get("hem")
    if waist is None or crotch is None or hem is None:
        return []
    waist_dst = waist * height_scale
    rise = pants_rise_cm(crotch - waist, hip_cm, height_scale)
    inseam = (hem - crotch) * height_scale
    crotch_dst = waist_dst + rise
    hem_dst = crotch_dst + inseam
    if not (waist_dst < crotch_dst < hem_dst):
        return []
    return [(waist, waist_dst), (crotch, crotch_dst), (hem, hem_dst)]


def hip_widening_cm(bust_cm: float, hip_cm: float, bodice_ease_cm: float,
                     hip_ease_cm: float) -> float:
    """身頃の裾を、ヒップが通る幅まで開かせる量(片側・cm)。round26で追加。

    【round25までの実害】身頃の裾は**ヒップの高さ**にある(テンプレートの
    丈58cmは首の付け根からヒップまで)。ところが幅はバストだけで決まり、
    さらにウエストダーツが裾を摘んでいたため、裾がヒップより細くなっていた。
    実測(前身頃+後身頃の裾の開き寸法):

      B/W/H        裾の開き   ヒップ+ゆとり     差
      83/66/91      91.00       95.0        -4.0
      83/58/98      83.97      102.0       -18.0   ← 腰を通らない
      83/50/100     72.94      104.0       -31.1   ← 到底通らない

    18cm足りない服は、そもそも履けない(かぶれない)。**着られない型紙を
    黙って出していた**ことになる。

    ここで返すのは「バストで決まる幅では足りないぶん」を4で割った値
    (前後2枚 × 左右2辺 = 4辺で分担するため)。バストの方が大きい体型では
    0を返し、従来どおり裾までまっすぐな脇線になる。
    """
    needed = hip_cm + hip_ease_cm
    have = bust_cm + bodice_ease_cm
    return max(0.0, (needed - have) / 4.0)


#: 脇線の傾き(|dx|/|dy|)の上限。`engine/compatibility.py`の
#: NEAR_VERTICAL_MAX_DX_RATIO と同じ値でなければならない——これを超えると
#: 脇線が「ほぼ垂直」と認識されなくなり、縫い合わせ長さのチェックが
#: **黙ってスキップされる**(round27で実際に起きた。バスト50・ヒップ170の
#: ような極端な体型で、脇線の傾きが0.78になり検出できていなかった)。
#: tests/test_hip_clearance.py が両者の一致を固定している。
SIDE_SEAM_MAX_SLOPE = 0.25


def hip_widening_start_y(waist_y: float, underarm_y: float, hem_y: float,
                          widening_cm: float) -> tuple[float, float]:
    """脇線を開かせ始める高さと、実際に開かせる量を決める(round27)。

    開かせる量が大きいほど脇線は寝る。傾きが`SIDE_SEAM_MAX_SLOPE`を超えると
    脇線として認識されなくなるので、そうならないよう

      1. まずウエストの線から開かせる(標準的な形)
      2. 傾きが立ちすぎるなら、開かせ始める高さを**脇の下まで**引き上げて
         走る距離を稼ぐ
      3. それでも足りなければ、傾きの上限に収まるところで開き量を止める

    という順で決める。3に至った場合は返り値の量が要求より小さくなるので、
    呼び出し側が「ヒップが通る幅を確保しきれなかった」と開示する。
    """
    if widening_cm <= 0:
        return waist_y, 0.0
    for start in (waist_y, underarm_y):
        run = hem_y - start
        if run > 0 and widening_cm / run <= SIDE_SEAM_MAX_SLOPE:
            return start, widening_cm
    run = max(0.0, hem_y - underarm_y)
    return underarm_y, run * SIDE_SEAM_MAX_SLOPE


#: ウエストで脇線を絞る量の、余り全体に対する割合(round29)。
#: 新文化式のウエストダーツ配分表の c(脇線)=11% をそのまま使う
#: (engine/darts.pyの`WAIST_DART_SHARE_SIDE_SEAM`と同じ値。判定を2か所に
#: 書かないよう、そちらから取る)。
#:
#: 【なぜ要るか】round28まで脇線は袖の下から裾までまっすぐで、ウエストを
#: 絞るのはダーツだけだった。配分表では脇線が11%を担う。実物の型紙でも
#: フィットした身頃の脇線はウエストでくびれている。これが無いと、
#: ダーツだけで全部を摘むことになり、深すぎるダーツか、絞りきれない
#: ウエストのどちらかになる。


def _split_lines_at_y(segments: list[tuple[str, list[float]]], y: float
                       ) -> list[tuple[str, list[float]]]:
    """高さ`y`を跨ぐ直線(L)セグメントを、その高さで2本に割る。

    曲線(C)は割らない。身頃の輪郭でウエストの高さを跨ぐのは脇線(直線)
    だけなので、これで足りる。
    """
    out: list[tuple[str, list[float]]] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    for cmd, nums in segments:
        if cmd == "M":
            cx, cy = nums[0], nums[1]
            start_x, start_y = cx, cy
            out.append((cmd, list(nums)))
            continue
        if cmd == "L":
            x1, y1 = nums[0], nums[1]
            lo, hi = (cy, y1) if cy <= y1 else (y1, cy)
            if lo < y < hi:
                t = (y - cy) / (y1 - cy)
                out.append(("L", [cx + t * (x1 - cx), y]))
            out.append(("L", [x1, y1]))
            cx, cy = x1, y1
            continue
        if cmd == "Z":
            out.append(("Z", []))
            cx, cy = start_x, start_y
            continue
        out.append((cmd, list(nums)))
        if len(nums) >= 2:
            cx, cy = nums[-2], nums[-1]
    return out


def waist_nip_limit_cm(underarm_y: float, waist_y: float, hem_y: float,
                        nip_cm: float,
                        hip_widen_below_waist: float = 0.0) -> tuple[float, float]:
    """ウエストで脇線を絞れる量を、傾きの上限に収める(round30)。

    Returns:
        (実際に絞る量, 絞りきれなかった量)。どちらも片側のcm。

    絞ると脇線は袖の下→ウエストで内へ、ウエスト→裾で外へ傾く。傾きが
    `SIDE_SEAM_MAX_SLOPE`を超えると`engine/compatibility.py`が脇線と
    認識できなくなり、**縫い合わせのチェックが黙ってスキップされる**
    (round27でヒップ側の開きに同じ問題があり、`hip_widening_start_y`で
    同じ形の対処をしている)。

    【なぜround30で要るようになったか】伸びる生地の型紙はダーツを入れない
    ので、ウエストの絞りを脇線が全部担う。実測(バスト83/ウエスト66/
    ヒップ91、伸縮率50%)では絞り量4.0cmに対し縦14.5cmで傾き0.28となり、
    上限0.25を超えて**6体型中5体型で脇線が検出不能**になっていた。
    """
    if nip_cm <= 0:
        return 0.0, 0.0
    up_run = waist_y - underarm_y
    down_run = hem_y - waist_y
    if min(up_run, down_run) <= 0:
        return 0.0, nip_cm
    # 袖の下→ウエストは絞りだけ。ウエスト→裾は、絞りから戻る動きに
    # ヒップの開き(`hip_widen_below_waist`)が重なるので、その分を差し引く。
    allowed_down = SIDE_SEAM_MAX_SLOPE * down_run - hip_widen_below_waist
    allowed = min(SIDE_SEAM_MAX_SLOPE * up_run, max(0.0, allowed_down))
    applied = min(nip_cm, allowed)
    return applied, max(0.0, nip_cm - applied)


def apply_waist_nip(segments: list[tuple[str, list[float]]], cf_x: float,
                     underarm_y: float, waist_y: float, hem_y: float,
                     nip_cm: float) -> list[tuple[str, list[float]]]:
    """ウエストの高さで脇線を内側へ絞る(round29)。

    絞り量は袖の下(underarm_y)で0、ウエスト(waist_y)で`nip_cm`、裾(hem_y)で
    再び0になるよう直線的に変化させる。中心前(cf_x)からの距離を縮めるので、
    左右対称のまま形が崩れない。

    バストの幅(袖の下の高さ)と裾の幅(ヒップの高さ)はどちらも動かさない
    ——動かすと、せっかく合わせたバスト周・ヒップ周がずれる。
    """
    if nip_cm <= 0 or not (underarm_y < waist_y < hem_y):
        return segments

    # 【なぜ先に節点を足すか】脇線は袖の下から裾まで**1本の直線**なので、
    # 途中のウエストの高さには点が無い。点を動かす写像だけでは、両端しか
    # 動かせず直線は直線のまま——実測では絞り量1.22cmを計算しておきながら
    # 半幅が24.12cmから1mmも動かなかった。ウエストの高さを跨ぐ直線を、
    # そこで2本に割ってから動かす。
    segments = _split_lines_at_y(segments, waist_y)

    # 【なめらかなカーブにしなかった理由(round29で実測)】脇線はウエストで
    # 「くの字」に折れる。折れ角は実測で約9.5度(絞り1.0cmを縦12cmで
    # 入って出る)なので、実物の型紙の直線的なウエスト絞りと同程度に収まる。
    # 上下の中間にも点を足し、コサインでなめらかに変化させる版を試したが、
    # 脇線の断片が3〜5cmに細かく割れ、縫い合わせチェック側で脇線を1本に
    # まとめる条件(engine/compatibility.pyの`_MIN_JOINABLE_FRAGMENT_CM`)を
    # 割り込んで、40件以上のテストが落ちた。見た目のなめらかさのために
    # 「脇線を脇線と認識できる」という土台を崩す取引はしない。

    def _offset(y: float) -> float:
        if y <= underarm_y or y >= hem_y:
            return 0.0
        if y <= waist_y:
            return nip_cm * (y - underarm_y) / (waist_y - underarm_y)
        return nip_cm * (hem_y - y) / (hem_y - waist_y)

    def _x(x: float, y: float) -> float:
        offset = _offset(y)
        if offset <= 0:
            return x
        distance = x - cf_x
        if abs(distance) < 1e-9:
            return x
        # 中心へ寄せすぎて左右が入れ替わらないよう、距離の半分までに留める。
        offset = min(offset, abs(distance) / 2.0)
        return cf_x + distance - (offset if distance > 0 else -offset)

    out: list[tuple[str, list[float]]] = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd in ("H", "V"):
            out.append((cmd, list(nums)))
        else:
            vals = list(nums)
            for k in range(0, len(vals) - 1, 2):
                vals[k] = _x(vals[k], vals[k + 1])
            out.append((cmd, vals))
    return out


#: 背幅(中心後から後ろの袖ぐりの点まで)を求める新文化式の式(round31)。
#: 胸幅(`chest_width_cm`)と対になる値で、資料では一貫して `B/8 + 7.4`。
BACK_WIDTH_DIVISOR = ADULT_FEMALE.back_width.divisor
BACK_WIDTH_CONST = ADULT_FEMALE.back_width.const


def back_width_cm(bust_cm: float, block: Block = ADULT_FEMALE) -> float:
    """中心後から後ろの袖ぐりの点までの幅(背幅・cm)。新文化式の B/8 + 7.4。

    block: round42。子ども原型では B/5 + 1.2(`engine/blocks.py`)。
    """
    return block.back_width.value(bust_cm)


def bodice_side_width_cm(part_type: str, bust_cm: float,
                          block: Block = ADULT_FEMALE) -> float:
    """このパーツで、中心から袖ぐりの点までの距離(cm)。前は胸幅、後ろは背幅。"""
    return (back_width_cm(bust_cm, block) if part_type == "back_bodice"
            else chest_width_cm(bust_cm, block))


#: 袖ぐりのえぐれ量を、元のテンプレートの何倍まで動かしてよいか(round31)。
#: 下限0だと袖ぐりが「肩先から脇の下への単調な線」になり、腕が回らない。
#: 上限は、えぐりすぎて袖ぐりが胸の側へ食い込むのを防ぐ。どちらも効いた
#: 場合は、狙いの胸幅/背幅に届かなかったこととして開示する。
ARMHOLE_SCOOP_MIN_FACTOR = 0.3
ARMHOLE_SCOOP_MAX_FACTOR = 5.0


def _bezier_x(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1.0 - t
    return (u * u * u * p0 + 3 * u * u * t * p1
            + 3 * u * t * t * p2 + t * t * t * p3)


def _extreme_inward_x(p0x: float, p1x: float, p2x: float, p3x: float,
                       sign: float, steps: int = 400) -> float:
    """袖ぐり曲線が、いちばん内側(中心寄り)へ出る位置のx。"""
    best = None
    for k in range(steps + 1):
        x = _bezier_x(p0x, p1x, p2x, p3x, k / steps)
        if best is None or x * sign > best * sign:
            best = x
    return best


def _solve_scoop_factor(shoulder_x: float, under_x: float, a: float, b: float,
                         sign: float, e_target: float,
                         lo: float, hi: float, iterations: int = 60) -> float:
    """えぐれ量の倍率fを、袖ぐりの点が狙いの位置に来るよう二分法で求める。

    【なぜ二分法か(round31で直した誤り)】最初は「ベジエ曲線は制御点に
    ついて線形だから、内向きオフセットをf倍すれば内側への出っ張りも
    f倍になる」として f = e_target / e_current で決めていた。これは誤り。
    曲線上のxは

        x(t) = (B0+B1)·肩先x + (B2+B3)·脇下x + sign·f·(B1·a + B2·b)

    で、肩先からの出っ張り (x(t) − 肩先x)·sign には**fに比例しない項**
    (弦が脇の下へ向かって外側へ降りていく分)が残る。実測でも、この式で
    決めた倍率では前身頃の胸幅が狙いから最大1.59cmずれた。

    fに対して出っ張りは単調増加(a,b≥0)なので、二分法なら確実に解ける。
    """
    def excursion(f: float) -> float:
        p1 = shoulder_x + sign * a * f
        p2 = under_x + sign * b * f
        return (_extreme_inward_x(shoulder_x, p1, p2, under_x, sign) - shoulder_x) * sign

    if excursion(hi) <= e_target:
        return hi
    if excursion(lo) >= e_target:
        return lo
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        if excursion(mid) < e_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def fit_armhole_width(segments: list[tuple[str, list[float]]],
                       underarm_y: float, cf_x: float,
                       target_from_cf_cm: float,
                       tol: float = 1e-3) -> tuple[list, float, bool]:
    """袖ぐりのえぐれ量を、胸幅(背幅)の式が指す位置に合わせる(round31)。

    Returns:
        (変形後のsegments, 実際に届いた「中心から袖ぐりの点まで」の距離,
         上限/下限に当たったか)。

    【なぜ必要か】round30まで、袖ぐりのえぐれ量はテンプレートの定数
    (`BODICE_AH_SCOOP`=2.5cm)のままだった。袖ぐりの位置は肩先から
    えぐれ量ぶん内側に決まるので、**胸幅・背幅がバストではなく肩幅で
    決まっていた**。実測(中心から袖ぐりの点まで。肩幅を37cmに固定):

        バスト   胸幅の式   実測    差
          60     13.70    15.48   +1.78
          83     16.57    17.61   +1.04
         110     19.95    17.93   −2.02
         130     22.45    18.08   −4.37

    バスト130で4.4cm足りないということは、前身頃の胸のあたりが左右あわせて
    8.7cm狭いということで、胸の前で突っ張る。逆にバスト60では広すぎて、
    袖ぐりが浅く腕が上がらない。

    肩幅を採寸から決める(round14)方針はそのままに、**袖ぐりのえぐれ量**を
    動かして、袖ぐりの点が式の位置に来るようにする。えぐれ量は曲線の
    制御点の内向きオフセットに比例するので、そのオフセットを一律に
    倍率fで伸縮すれば、いちばん内側へ出る量もfに比例する(ベジエ曲線が
    制御点について線形であることから)。

    肩先より内側へ届かない場合(肩幅に対してバストが大きすぎる)は、
    上限で止めて、届かなかったことを呼び出し側が開示する。
    """
    out: list[tuple[str, list[float]]] = []
    cursor = (0.0, 0.0)
    start = (0.0, 0.0)
    achieved: list[float] = []
    clamped = False
    for cmd, nums in segments:
        if cmd == "M":
            cursor = (nums[0], nums[1])
            start = cursor
            out.append((cmd, list(nums)))
            continue
        if cmd != "C" or len(nums) < 6:
            out.append((cmd, list(nums)))
            if cmd == "Z":
                cursor = start
            elif len(nums) >= 2:
                cursor = (nums[-2], nums[-1])
            continue

        p0, p3 = cursor, (nums[4], nums[5])
        cursor = p3
        # 袖ぐりは「片方の端が脇の下の高さにある曲線」。首ぐりは両端とも
        # 上にあるので当たらない。
        at_underarm = [abs(p0[1] - underarm_y) <= 0.05, abs(p3[1] - underarm_y) <= 0.05]
        if not any(at_underarm) or all(at_underarm):
            out.append((cmd, list(nums)))
            continue
        if at_underarm[0]:
            under, shoulder = p0, p3
            c_under, c_shoulder = (nums[0], nums[1]), (nums[2], nums[3])
        else:
            under, shoulder = p3, p0
            c_under, c_shoulder = (nums[2], nums[3]), (nums[0], nums[1])

        sign = 1.0 if shoulder[0] < cf_x else -1.0     # 内側(中心)へ向かう向き
        target_x = cf_x - sign * target_from_cf_cm
        a = (c_shoulder[0] - shoulder[0]) * sign
        b = (c_under[0] - under[0]) * sign
        current = _extreme_inward_x(p0[0], nums[0], nums[2], p3[0], sign)
        e_current = (current - shoulder[0]) * sign
        e_target = (target_x - shoulder[0]) * sign
        if e_current <= tol or e_target <= tol or a < 0 or b < 0:
            # えぐれていない、または狙いが肩先より外を指している(肩幅に
            # 対してバストが大きすぎる。袖ぐりの点は肩先より外へは出られ
            # ない)。触らずに、届かなかったこととして開示する。
            out.append((cmd, list(nums)))
            achieved.append(abs(cf_x - current))
            clamped = True
            continue
        limited = _solve_scoop_factor(
            shoulder[0], under[0], a, b, sign, e_target,
            ARMHOLE_SCOOP_MIN_FACTOR, ARMHOLE_SCOOP_MAX_FACTOR)
        # 上限/下限で止まった=狙いへ届かなかった、として開示する。
        if abs(limited - ARMHOLE_SCOOP_MIN_FACTOR) < 1e-9 or \
                abs(limited - ARMHOLE_SCOOP_MAX_FACTOR) < 1e-9:
            clamped = True
        new = list(nums)
        if at_underarm[0]:
            new[0] = under[0] + sign * b * limited
            new[2] = shoulder[0] + sign * a * limited
        else:
            new[0] = shoulder[0] + sign * a * limited
            new[2] = under[0] + sign * b * limited
        out.append((cmd, new))
        achieved.append(abs(cf_x - _extreme_inward_x(p0[0], new[0], new[2], p3[0], sign)))

    if not achieved:
        return segments, target_from_cf_cm, False
    return out, sum(achieved) / len(achieved), clamped


def apply_hip_widening(segments: list[tuple[str, list[float]]], cf_x: float,
                        start_y: float, hem_y: float, widening_cm: float
                        ) -> list[tuple[str, list[float]]]:
    """`start_y`から裾へ向かって、脇線を左右へ開かせる(round26)。

    開き量は`start_y`で0、裾で`widening_cm`になるよう直線的に増やす
    (それより上は動かさない)。中心前(cf_x)からの距離に一定量を足すので、
    裾の線もダーツの口も同じだけ広がり、左右対称のまま形が崩れない。

    脇線は厳密な垂直ではなくなるが、傾きは`hip_widening_start_y`が
    `SIDE_SEAM_MAX_SLOPE`以内に収めている。`engine/compatibility.py`の
    `_is_side_seam_edge`はその範囲を「ほぼ垂直」として受け付ける。
    """
    if widening_cm <= 0 or hem_y <= start_y:
        return segments

    def _x(x: float, y: float) -> float:
        if y <= start_y:
            return x
        t = min(1.0, (y - start_y) / (hem_y - start_y))
        offset = widening_cm * t
        distance = x - cf_x
        if abs(distance) < 1e-9:
            return x
        return cf_x + distance + (offset if distance > 0 else -offset)

    out: list[tuple[str, list[float]]] = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd in ("H", "V"):
            # 身頃テンプレートは H/V を使っていない(すべて M/L/C/Z)。
            # 将来使われた場合に静かに誤った形にならないよう、そのまま返す。
            out.append((cmd, list(nums)))
        else:
            vals = list(nums)
            for k in range(0, len(vals) - 1, 2):
                vals[k] = _x(vals[k], vals[k + 1])
            out.append((cmd, vals))
    return out


#: 胸幅(前中心から前の袖ぐりまでの幅)を求める新文化式の式(round29)。
#: 原型製図の資料で一貫して `B/8 + 6.2` と記されている。
CHEST_WIDTH_DIVISOR = ADULT_FEMALE.chest_width.divisor
CHEST_WIDTH_CONST = ADULT_FEMALE.chest_width.const


def chest_width_cm(bust_cm: float, block: Block = ADULT_FEMALE) -> float:
    """前中心から前の袖ぐりまでの幅(胸幅・cm)。新文化式の B/8 + 6.2。

    block: round42。子ども原型では B/5(`engine/blocks.py`)。
    """
    return block.chest_width.value(bust_cm)


#: BPを胸幅の二等分点からどれだけ脇側へずらすか(cm)。新文化式の製図では
#: 「前胸幅を二等分し、そこから0.7cm脇側へ動かした点がBP」とする。
BUST_POINT_OFFSET_FROM_CHEST_HALF_CM = 0.7

#: BP(バストポイント)の中心前からの距離を求める式の係数(round28)。
#:
#: 【round28の値と、round29で置き換えた理由】round28では
#: 「BP間隔 ≒ (B/12 + 2.5) × 2」という目安を使っていた。これは製図の
#: 資料に当たらずに置いた概算で、バストが大きいほど実際より外へ出る:
#:
#:   バスト   round28(B/12+2.5)   新文化式(胸幅/2+0.7)   差
#:     83          9.42                8.99           +0.43
#:    110         11.67               10.68           +0.99
#:    125         12.92               11.61           +1.31
#:
#: 新文化式は胸幅そのものから決めるので、傾きが 1/12 ではなく 1/16 に
#: なる。BP間隔はバストほど速くは広がらない、という当たり前の性質が
#: 式に入っている。round29ではこちらを既定にした
#: (定数は「胸幅の式 + 0.7cm」から導く。値を直接書かない)。
#:
#: 【round27までの実測】脇ダーツ(バストダーツ)は、BPの位置を
#: 「脇線に沿った比率」で決めていた(BUST_APEX_HEIGHT_RATIO=0.42、
#: BUST_APEX_OFFSET_RATIO=0.45)。脇線は袖付けから裾までなので、
#: 0.42という比率が指す高さは**ウエストのあたり**になる。実測
#: (バスト110・前身頃):
#:
#:   ダーツ先端 (x=12.98, y=38.52)   ← y=38.5 はウエストの高さ
#:   BPの推定    CFから16.5cm
#:   実際のBP    バストライン(y≒25.8)上、CFから11.7cm
#:
#: **バストダーツがバストではなくウエストを向いていた。** 先端が12cm下、
#: 5cm外にずれているので、布の膨らみもそこに出る——胸の丸みを作るための
#: ダーツが、胸の下で余る原因になっていた。
BUST_POINT_FROM_CF_DIVISOR = CHEST_WIDTH_DIVISOR * 2.0            # = 16
BUST_POINT_FROM_CF_CONST = (CHEST_WIDTH_CONST / 2.0
                            + BUST_POINT_OFFSET_FROM_CHEST_HALF_CM)  # = 3.8


def bust_point_from_cf_cm(bust_cm: float,
                          bust_point_spacing_cm: float | None = None) -> float:
    """中心前からBP(バストポイント)までの水平距離(cm)。

    bust_point_spacing_cm:
        round29。採寸した**乳間**(左右の乳頭の間隔)。与えられたらその半分を
        そのまま返す。推定式より採寸の方が確かなので、式には戻さない。
    """
    if bust_point_spacing_cm is not None and bust_point_spacing_cm > 0:
        return bust_point_spacing_cm / 2.0
    return chest_width_cm(bust_cm) / 2.0 + BUST_POINT_OFFSET_FROM_CHEST_HALF_CM


def bust_point_y_cm(bust_line_y: float, front_neck_y: float | None = None,
                    bust_point_drop_cm: float | None = None) -> float:
    """変形後の座標系での、BPの高さ(y)。

    原型の製図では、BPはバストライン(袖ぐり底の線)の上にあるものとして
    描く。そこで既定はバストラインそのもの。

    **乳下がり**(前中央で首の付け根からBPまでの長さ)を採寸してもらえた
    場合だけ、そちらを使う。バストラインは「袖ぐりの深さ」から決まる線で
    あって、その人の胸の高さそのものではないので、実測がある方が確かである。
    首の付け根の高さ(front_neck_y)が分からない場合は使えないので、
    バストラインへ戻る。

    【正直な限界】バストラインより上へBPを持ち上げることは許していない。
    バストラインは袖ぐりの底でもあり、そこより上にダーツの口を開けると
    袖ぐりを壊すため。実測がバストラインより上を指す場合はバストラインで
    止める(その場合、胸の丸みは実際より少し低い位置に出る)。
    """
    if (bust_point_drop_cm is None or bust_point_drop_cm <= 0
            or front_neck_y is None):
        return bust_line_y
    return max(bust_line_y, front_neck_y + bust_point_drop_cm)
