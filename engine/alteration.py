"""alteration.py — 着てみて合わなかったときに、型紙を直す。round40で追加。

【round39まで何が足りなかったか】この製品は**型紙を出すところで終わって
いた**。実際に縫ってみて、肩が窮屈だった・背中が余った・ウエストがきつかった
——そのとき利用者にできるのは、採寸値を変えて全部やり直すことだけだった。
やり直しても、なぜ合わなかったのかが分からないままなので、同じところで
また失敗する。型紙を出す機能と、出した型紙を直す機能。後者が無いままだと、
失敗した人はここに戻ってこない。

【この製品の補正の考え方 — 症状を当てない】
「なで肩ですか?」と聞いて、こちらで補正量を決めるやり方は採らない。
どれくらいなで肩なのかは、こちらには分かりようがないからである。
代わりに**利用者が実物で測った余り/不足をcmで入力する**。
これは「補正機能付き原型型紙」が採っているやり方で、
  「肩で余った布をつまんで、余った量を入力します。10mm余っていれば、
   10を入力します」
  「首元が余るので、同様に余った量を測って入力します。10mm余っていれば、
   -10を入力します」
のように、**数字の出どころが利用者の実測**になる。当てずっぽうが入らない。
出典: 補正機能付き原型型紙の使いかた https://xn--6xw240d.net/genkei-kreader.htm

【補正できる量には上限がある】
MAISON DE ASは「体型補正は0.5〜0.8cm程度まで」に限定し、それを超える場合は
「幅と丈の併用が必要」としている。ここでもその線を超えたら黙って適用せず、
**そう伝える**(`LARGE_ALTERATION_CM`)。型紙の一部だけを大きく動かすと、
縫い合わせる相手との長さが合わなくなる。
出典: 市販の型紙の補正方法 https://maisondeas.com/sewing-pattern-corrections/
"""

from __future__ import annotations

from dataclasses import dataclass

#: この量を超える補正は「大きすぎる」と伝える(cm)。
#: 出典: MAISON DE AS「体型補正は0.5〜0.8cm程度まで」。上側の0.8cmを採る。
#: 超えても適用は止めない——止めると利用者は何もできなくなる——が、
#: 「一部だけ動かすと縫い合わせの相手と合わなくなる」ことは必ず伝える。
LARGE_ALTERATION_CM = 0.8

#: 受け付ける補正量の絶対値の上限(cm)。これを超えるのは入力ミスとみなす。
#: 5cmは、標準Mの肩幅(37cm)に対して1割を超える。補正ではなく別サイズの話。
MAX_ALTERATION_CM = 5.0


@dataclass(frozen=True)
class AlterationKind:
    """補正の種類。画面に出す説明と、測り方をここに持つ。"""
    key: str
    label: str
    #: どこをどう測って入力するか。ここが曖昧だと数字の意味が揺れる。
    how_to_measure: str
    #: 正の値・負の値がそれぞれ何を意味するか。
    positive_means: str
    negative_means: str
    source_name: str
    source_url: str

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label,
                "how_to_measure": self.how_to_measure,
                "positive_means": self.positive_means,
                "negative_means": self.negative_means,
                "source_name": self.source_name, "source_url": self.source_url}


_GENKEI = ("補正機能付き原型型紙の使いかた",
            "https://xn--6xw240d.net/genkei-kreader.htm")
_COCONO = ("ここのの衣装製作日記「型紙補正！肩幅を広げる方法」",
            "https://coconoyousai.net/post-2702/")
_MAISON = ("MAISON DE AS「市販の型紙の補正方法」",
            "https://maisondeas.com/sewing-pattern-corrections/")

#: 直せる症状の一覧。ここに無いものは直せない——**それも正直に言う**。
ALTERATION_KINDS: tuple[AlterationKind, ...] = (
    AlterationKind(
        key="shoulder_slope",
        label="肩の傾き（なで肩・いかり肩）",
        how_to_measure=(
            "着たときに肩の先で布が余るなら、余った分をつまんで測ります。"
            "逆に首元が余って肩先が突っ張るなら、首元で余った分を測ります。"),
        positive_means="肩先で余った分だけ肩線を下げます（なで肩の直し方）",
        negative_means="首元で余った分だけ肩線を上げます（いかり肩の直し方）",
        source_name=_GENKEI[0], source_url=_GENKEI[1]),
    AlterationKind(
        key="shoulder_width",
        label="肩幅",
        how_to_measure=(
            "肩の縫い目が、自分の肩先より内側／外側にどれだけずれているかを測ります。"),
        positive_means="肩先を外へ出して広げます",
        negative_means="肩先を内へ入れて狭めます",
        source_name=_COCONO[0], source_url=_COCONO[1]),
    AlterationKind(
        key="bust_width",
        label="胸まわり",
        how_to_measure=(
            "胸まわりが何cm足りない／余っているかを、着た状態で測ります"
            "（一周ぶんの値を入れてください）。"),
        positive_means="一周ぶんの不足を4分の1ずつ脇へ出します",
        negative_means="一周ぶんの余りを4分の1ずつ脇で詰めます",
        source_name=_MAISON[0], source_url=_MAISON[1]),
    AlterationKind(
        key="waist_width",
        label="ウエスト",
        how_to_measure="ウエストが何cm足りない／余っているかを一周ぶんで測ります。",
        positive_means="一周ぶんの不足を4分の1ずつ脇へ出します",
        negative_means="一周ぶんの余りを4分の1ずつ脇で詰めます",
        source_name=_MAISON[0], source_url=_MAISON[1]),
    AlterationKind(
        key="hip_width",
        label="ヒップ",
        how_to_measure="ヒップが何cm足りない／余っているかを一周ぶんで測ります。",
        positive_means="一周ぶんの不足を4分の1ずつ脇へ出します",
        negative_means="一周ぶんの余りを4分の1ずつ脇で詰めます",
        source_name=_MAISON[0], source_url=_MAISON[1]),
)

ALTERATION_KEYS = tuple(kind.key for kind in ALTERATION_KINDS)
_BY_KEY = {kind.key: kind for kind in ALTERATION_KINDS}

#: 補正が効くパーツ種。身頃だけである(袖・スカートの丈は
#: `design_length_overrides`で直せるので、ここでは扱わない)。
ALTERABLE_PART_TYPES = frozenset({
    "front_bodice", "back_bodice",
    "front_bodice_center", "front_bodice_side",
    "back_bodice_center", "back_bodice_side",
    "front_bodice_zip_panel",
})

#: 一周ぶんの不足を、片側の脇へ何倍で配分するか。
#: 出典: MAISON DE AS「不足分の1/4を外側に出し、脇線を引き直す」。
#: 前身頃・後ろ身頃それぞれに脇が1本ずつあり、左右で2本ずつ = 合計4本。
#: だから1本あたり1/4である。
SIDE_SEAM_SHARE = 0.25


def validate(alterations: dict[str, float]) -> dict[str, float]:
    """入力された補正量を検算し、意味のあるものだけ返す。

    知らない項目・0・範囲外はここで弾く。範囲外は黙って丸めず、
    エラーにする——勝手に丸めると、利用者は自分の入れた数字が
    使われたと思い込む。
    """
    cleaned: dict[str, float] = {}
    for key, raw in (alterations or {}).items():
        if key not in _BY_KEY:
            raise ValueError(f"知らない補正です: {key}")
        value = float(raw)
        if abs(value) > MAX_ALTERATION_CM:
            raise ValueError(
                f"{_BY_KEY[key].label}の補正は±{MAX_ALTERATION_CM:g}cmまでです"
                f"（入力値 {value:g}cm）。これより大きい場合は、補正ではなく"
                "採寸値そのものを見直してください。")
        if abs(value) < 1e-9:
            continue
        cleaned[key] = value
    return cleaned


def notes_for(alterations: dict[str, float]) -> list[str]:
    """何をどれだけ直したかを利用者へ伝える文。

    黙って形を変えない。どの数字がどこに効いたのかが分からないと、
    次に合わなかったときにまた同じ迷い方をする。
    """
    notes: list[str] = []
    for key, value in alterations.items():
        kind = _BY_KEY[key]
        direction = kind.positive_means if value > 0 else kind.negative_means
        notes.append(f"{kind.label}を{abs(value):g}cm補正しました（{direction}）。")
        if abs(value) > LARGE_ALTERATION_CM:
            notes.append(
                f"{kind.label}の補正{abs(value):g}cmは、一般に勧められる範囲"
                f"（{LARGE_ALTERATION_CM:g}cm程度まで）を超えています。"
                "型紙の一部だけを大きく動かすと、縫い合わせる相手との長さが"
                "合わなくなることがあります。採寸値そのものを見直すか、"
                "幅と丈を組み合わせて直すことを検討してください。")
    return notes


# --- 幾何 ---------------------------------------------------------------------

def _anchor(anchors: list[tuple[str, float]], name: str,
             prefer_max: bool) -> float | None:
    """基準点の座標を取り出す。同名が複数あるので、左右どちらかを選ぶ。

    身頃の基準点は `[side, shoulder, neck, cf, neck, shoulder, side]` の
    ように**左右対称に並ぶ**。補正は左右両方に効かせたいので、呼び出し側は
    両側それぞれを取る。
    """
    values = [x for label, x in anchors if label == name]
    if not values:
        return None
    return max(values) if prefer_max else min(values)


def _remap_segments(segments: list, point_map) -> list:
    """全ての座標(ベジエの制御点も含む)を`point_map`に通す。

    テンプレートが使うコマンドは M / L / C / Z だけ(実測で確認済み)なので、
    H / V のような「片方の座標しか持たないコマンド」は考えなくてよい。
    もし将来使うようになったら、ここで取りこぼす。
    """
    out: list = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
            continue
        if cmd in ("H", "V"):
            raise NotImplementedError(
                f"補正は M/L/C/Z だけを想定しています（{cmd} が来ました）")
        mapped: list[float] = []
        for i in range(0, len(nums), 2):
            x, y = point_map(nums[i], nums[i + 1])
            mapped.extend((x, y))
        out.append((cmd, mapped))
    return out


def _blend(value: float, start: float, end: float) -> float:
    """`start`で0、`end`で1になる線形の重み(範囲外は0か1で止める)。"""
    if abs(end - start) < 1e-9:
        return 1.0 if value >= end else 0.0
    t = (value - start) / (end - start)
    return max(0.0, min(1.0, t))


def _bezier_point(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    """3次ベジエ上の点。"""
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _split_cubic(p0, p1, p2, p3, t: float):
    """3次ベジエを t で2本に分ける(de Casteljau)。"""
    def mid(a, b):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    q0, q1, q2 = mid(p0, p1), mid(p1, p2), mid(p2, p3)
    r0, r1 = mid(q0, q1), mid(q1, q2)
    s = mid(r0, r1)
    return (p0, q0, r0, s), (s, r1, q2, p3)


def _t_at_height(p0, p1, p2, p3, y: float) -> float | None:
    """そのベジエが高さ`y`を横切るパラメータ t を1つ返す(無ければ None)。

    解析的に3次方程式を解く代わりに、細かくサンプリングして符号が変わる
    区間を二分探索する。曲線1本あたり数十回の計算で足りるうえ、
    重解や数値的に不安定な根に振り回されない。
    """
    steps = 32
    prev_t = 0.0
    prev = _bezier_point(p0, p1, p2, p3, 0.0)[1] - y
    for i in range(1, steps + 1):
        t = i / steps
        cur = _bezier_point(p0, p1, p2, p3, t)[1] - y
        if prev == 0.0:
            return prev_t
        if (prev < 0) != (cur < 0):
            lo, hi = prev_t, t
            for _ in range(40):
                mid_t = (lo + hi) / 2.0
                if (_bezier_point(p0, p1, p2, p3, mid_t)[1] - y < 0) == (prev < 0):
                    lo = mid_t
                else:
                    hi = mid_t
            return (lo + hi) / 2.0
        prev_t, prev = t, cur
    return None


def _split_at_heights(segments: list, heights) -> list:
    """基準の高さを横切るところに、頂点を足した輪郭を返す。

    【なぜ要るか】補正の重みは「ウエストの高さで最大、バストとヒップで0」
    という三角形にしてある。ところが輪郭にウエストの高さの頂点が無いと、
    その高さを通る点は上下の頂点の中間として描かれ、**最大の重みが
    かからない**。実測で、ウエストを4cm詰めたつもりが型紙は2.0cmではなく
    1.49cmしか動かなかった。形の問題ではなく、頂点の粗さの問題である。

    横切るところで曲線を分割し(de Casteljau)、直線は内挿して頂点を足す。
    形そのものは1mmも変わらない——同じ曲線を2本に分けているだけ。
    """
    targets = sorted({round(h, 6) for h in heights})
    out: list = []
    current: tuple[float, float] | None = None
    start: tuple[float, float] | None = None
    for cmd, nums in segments:
        if cmd == "M":
            current = start = (nums[0], nums[1])
            out.append((cmd, list(nums)))
        elif cmd == "L":
            end = (nums[0], nums[1])
            crossings = []
            if current is not None:
                for h in targets:
                    lo, hi = min(current[1], end[1]), max(current[1], end[1])
                    if lo + 1e-9 < h < hi - 1e-9:
                        ratio = (h - current[1]) / (end[1] - current[1])
                        crossings.append((ratio, (
                            current[0] + (end[0] - current[0]) * ratio, h)))
            for _ratio, point in sorted(crossings):
                out.append(("L", [point[0], point[1]]))
            out.append(("L", [end[0], end[1]]))
            current = end
        elif cmd == "C":
            p0 = current or (nums[0], nums[1])
            p1 = (nums[0], nums[1])
            p2 = (nums[2], nums[3])
            p3 = (nums[4], nums[5])
            pieces = [(p0, p1, p2, p3)]
            for h in targets:
                nxt = []
                for piece in pieces:
                    lo = min(piece[0][1], piece[3][1])
                    hi = max(piece[0][1], piece[3][1])
                    t = (_t_at_height(*piece, h)
                         if lo - 1e-9 < h < hi + 1e-9 else None)
                    if t is None or t <= 1e-6 or t >= 1 - 1e-6:
                        nxt.append(piece)
                    else:
                        nxt.extend(_split_cubic(*piece, t))
                pieces = nxt
            for piece in pieces:
                out.append(("C", [piece[1][0], piece[1][1],
                                   piece[2][0], piece[2][1],
                                   piece[3][0], piece[3][1]]))
            current = p3
        else:
            out.append((cmd, list(nums)))
            if cmd == "Z":
                current = start
    return out


def _top_y_at(points: list[tuple[float, float]], x: float) -> float | None:
    """輪郭のうち、この x での**いちばん上**の y を線形補間で求める(round43)。

    【なぜ「±1cmの窓のなかで最小」ではだめか】肩線は傾いているので、
    窓の内側で最大0.45cm(24°の肩線・窓±1cm)ずれる。肩傾斜を角度で
    測るのに0.45cmの誤差は大きすぎる(肩幅の半分11.6cmに対して2.2°)。
    輪郭の辺とこの縦線の交点をそのまま取る。
    """
    best: float | None = None
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 == x2:
            continue
        if (x1 - x) * (x2 - x) > 0:
            continue
        t = (x - x1) / (x2 - x1)
        y = y1 + t * (y2 - y1)
        if best is None or y < best:
            best = y
    return best


def measure_shoulder_slope_deg(segments: list, part_type: str,
                                anchors: list[tuple[str, float]],
                                y_anchors: list[tuple[str, float]],
                                bust_line_y_cm: float | None = None
                                ) -> float | None:
    """いまの輪郭の肩線が、水平線に対して何度傾いているかを測る(round43)。

    首の付け根(SNP)と肩先(SP)を輪郭から拾い、その2点を結ぶ線の角度を返す。
    どちらかが拾えない形(基準点を持たないテンプレート等)ではNone。

    肩先の拾い方は`apply_alterations`と同じ——**同じ点を動かす**ので、
    測る点と動かす点が違うと補正が的を外す(round40で実際にそれを踏んだ)。
    """
    from math import atan2, degrees

    if part_type not in ALTERABLE_PART_TYPES or not anchors or not y_anchors:
        return None
    from .svgpath import segments_to_polyline

    points = segments_to_polyline(segments, curve_steps=120)
    if not points:
        return None
    right_shoulder = _anchor(anchors, "shoulder", prefer_max=True)
    right_neck = _anchor(anchors, "neck", prefer_max=True)
    if right_shoulder is None or right_neck is None:
        return None
    y_underarm = (bust_line_y_cm if bust_line_y_cm is not None
                   else _anchor(y_anchors, "underarm", prefer_max=False))
    if y_underarm is None:
        return None

    tip_y = _top_y_at(points, right_shoulder)
    snp_y = _top_y_at(points, right_neck)
    if tip_y is None or snp_y is None:
        return None
    run = right_shoulder - right_neck
    if run <= 1e-6:
        return None
    return degrees(atan2(tip_y - snp_y, run))


def shoulder_slope_correction_cm(segments: list, part_type: str,
                                  anchors: list[tuple[str, float]],
                                  y_anchors: list[tuple[str, float]],
                                  target_deg: float,
                                  bust_line_y_cm: float | None = None
                                  ) -> float:
    """肩先を何cm動かせば、肩傾斜が`target_deg`になるかを返す(round43)。

    返す値の符号は`apply_alterations`の`shoulder_slope`と同じ
    (プラスで肩線が下がる)。測れない場合は0.0——当てずっぽうで動かさない。

    製図では**先に角度を引いてから肩幅を測る**。このエンジンは順序が逆で、
    肩先のxを肩幅で決め、yはテンプレートの形の伸縮に任せていた。その結果、
    肩傾斜が体型の副産物になっていた(`engine/blocks.py`の
    `shoulder_slope_front_deg`に実測)。ここで角度の方に合わせ直す。
    """
    from math import radians, tan

    current = measure_shoulder_slope_deg(segments, part_type, anchors,
                                          y_anchors, bust_line_y_cm)
    if current is None:
        return 0.0
    right_shoulder = _anchor(anchors, "shoulder", prefer_max=True)
    right_neck = _anchor(anchors, "neck", prefer_max=True)
    run = right_shoulder - right_neck
    return run * (tan(radians(target_deg)) - tan(radians(current)))


def apply_alterations(segments: list, part_type: str,
                       anchors: list[tuple[str, float]],
                       y_anchors: list[tuple[str, float]],
                       alterations: dict[str, float],
                       bust_line_y_cm: float | None = None,
                       waist_y_cm: float | None = None) -> list:
    """身頃の輪郭に補正を適用して返す。

    補正が無い、または身頃でない場合はそのまま返す。

    【なぜ基準点を使うか】「肩先」「首の付け根」「脇の下」「ウエスト」の位置は
    テンプレートごとに違う。座標を決め打ちにすると、ネックラインを変えた
    だけで補正がずれる。テンプレートが持っている基準点
    (`fit_anchors` / `fit_anchors_y`)から毎回引く。
    """
    if not alterations or part_type not in ALTERABLE_PART_TYPES:
        return segments
    if not anchors or not y_anchors:
        # 基準点を持たないテンプレートは、どこが肩なのか分からない。
        # 当てずっぽうで動かすくらいなら、何もしない方がよい。
        return segments

    left_shoulder = _anchor(anchors, "shoulder", prefer_max=False)
    right_shoulder = _anchor(anchors, "shoulder", prefer_max=True)
    left_neck = _anchor(anchors, "neck", prefer_max=False)
    right_neck = _anchor(anchors, "neck", prefer_max=True)
    left_side = _anchor(anchors, "side", prefer_max=False)
    right_side = _anchor(anchors, "side", prefer_max=True)
    # 【高さは基準点ではなく、変形結果そのものから取る】
    #
    # 基準点のyは「X/Yの区分線形写像を通したあと」の値だが、身頃はそのあと
    # **胸ぐせダーツの分だけ下へずれる**(`bust_dart_shift`)。実測では、
    # 基準点のウエストが38.48cmなのに、出来上がりのウエスト線は43.51cm
    # だった——5cmずれた位置を「ウエスト」だと思って重みを配っていたので、
    # ウエストの補正は満額の75%しか効かず、ヒップの補正が25%漏れていた。
    # `ScaledPart`が持っている`bust_line_y_cm`/`waist_y_cm`が、変形も
    # ダーツも通したあとの**本当の基準線**である。そちらを使う。
    _min_y = min(nums[i + 1] for _cmd, nums in segments
                  for i in range(0, len(nums), 2)) if segments else 0.0
    _max_y = max(nums[i + 1] for _cmd, nums in segments
                  for i in range(0, len(nums), 2)) if segments else 1.0
    y_neck = _min_y
    y_underarm = (bust_line_y_cm if bust_line_y_cm is not None
                   else _anchor(y_anchors, "underarm", prefer_max=False))
    y_waist = (waist_y_cm if waist_y_cm is not None
                else _anchor(y_anchors, "waist", prefer_max=False))
    y_hem = _max_y
    if None in (left_shoulder, right_shoulder, left_neck, right_neck,
                 left_side, right_side, y_neck, y_underarm, y_waist, y_hem):
        return segments
    if not (y_neck < y_underarm < y_waist <= y_hem):
        # 基準線の並びが想定と違う。当てずっぽうで動かすより、何もしない。
        return segments

    center_x = (left_side + right_side) / 2.0

    # --- 中心からの距離を「その高さでの半幅」で正規化する ---
    #
    # 【なぜ必要か】最初は「中心から脇の基準点まで」で重みを配っていた。
    # だが身頃はウエストで絞ってあるので、**ウエストの高さの脇線は基準点より
    # 内側にある**。その結果、脇線には満額の補正が届かなかった——実測で
    # ウエストを4cm広げたつもりが、型紙は2.0cmではなく1.49cmしか動いて
    # いなかった。中心からの距離を、その高さでの半幅で割って正規化すれば、
    # 「輪郭のいちばん外側」が必ず重み1になる。
    from .svgpath import segments_to_polyline

    points = segments_to_polyline(segments, curve_steps=120)

    def _half_width_at(y: float) -> float:
        near = [px for px, py in points if abs(py - y) <= 0.6]
        if len(near) < 2:
            return max(right_side - center_x, 1e-6)
        return max((max(near) - min(near)) / 2.0, 1e-6)

    # 高さごとに測り直すと重いので、基準の高さで測って間を補間する。
    _samples = [(y, _half_width_at(y))
                for y in (y_neck, y_underarm, y_waist, y_hem)]

    # --- 肩先の高さ ---
    #
    # 【なぜ要るか】肩の補正は「肩先で満額」でなければならない。最初は
    # 首の付け根の線から脇の下の線へ一律に薄めていたが、肩先はその途中
    # (実測で首の付け根から8.1cm、脇の下は23.9cm)にあるので、
    # **肩先の時点で既に66%まで薄まっていた**——1.0cm下げたつもりが
    # 0.62cmしか下がらない。肩先まで満額を保ち、そこから脇の下へ向けて
    # 0にする。
    def _tip_y(shoulder_x: float) -> float:
        near = [py for px, py in points
                 if abs(px - shoulder_x) <= 1.0 and py < y_underarm]
        return max(near) if near else y_neck

    left_tip_y = _tip_y(left_shoulder)
    right_tip_y = _tip_y(right_shoulder)

    def _half_width(y: float) -> float:
        if y <= _samples[0][0]:
            return _samples[0][1]
        for (y0, h0), (y1, h1) in zip(_samples, _samples[1:]):
            if y <= y1:
                t = 0.0 if abs(y1 - y0) < 1e-9 else (y - y0) / (y1 - y0)
                return h0 + (h1 - h0) * t
        return _samples[-1][1]

    slope = alterations.get("shoulder_slope", 0.0)
    shoulder_w = alterations.get("shoulder_width", 0.0)
    bust = alterations.get("bust_width", 0.0)
    waist = alterations.get("waist_width", 0.0)
    hip = alterations.get("hip_width", 0.0)

    def point_map(x: float, y: float) -> tuple[float, float]:
        new_x, new_y = x, y

        # --- 肩の傾き ---
        # 肩先でいちばん効き、首の付け根で0になるように配る。
        # 首元側まで一律に下げると、首ぐりの深さまで変わってしまう。
        if slope:
            if x <= center_x:
                weight = _blend(x, left_neck, left_shoulder)
                tip_y = left_tip_y
            else:
                weight = _blend(x, right_neck, right_shoulder)
                tip_y = right_tip_y
            # 肩先までは満額、そこから脇の下へ向けて0にする。
            depth = 1.0 - _blend(y, tip_y, y_underarm)
            new_y += slope * weight * depth

        # --- 肩幅 ---
        # 肩先を外(内)へ動かし、脇の下で元の線に戻す。
        # 出典(ここのの衣装製作日記)の「脇でもとの線に戻るよう線をひきます」。
        if shoulder_w:
            if x <= center_x:
                weight = _blend(x, left_neck, left_shoulder)
                depth = 1.0 - _blend(y, left_tip_y, y_underarm)
                new_x -= shoulder_w * weight * depth
            else:
                weight = _blend(x, right_neck, right_shoulder)
                depth = 1.0 - _blend(y, right_tip_y, y_underarm)
                new_x += shoulder_w * weight * depth

        # --- 胴回り(胸・ウエスト・ヒップ) ---
        # 一周ぶんの不足の1/4を、その高さの脇へ出す。
        # 出典(MAISON DE AS)の「不足分の1/4を外側に出し、脇線を引き直す」。
        # 高さごとに違う量を出すので、脇線は自然につながる。
        if bust or waist or hip:
            at_bust = 1.0 - _blend(y, y_underarm, y_waist)
            at_waist = (_blend(y, y_underarm, y_waist)
                        * (1.0 - _blend(y, y_waist, y_hem)))
            at_hip = _blend(y, y_waist, y_hem)
            shift = SIDE_SEAM_SHARE * (
                bust * at_bust + waist * at_waist + hip * at_hip)
            # 中心線は動かさず、脇へ向かうほど効かせる。重みは
            # 「中心からの距離 ÷ その高さの半幅」——輪郭のいちばん外側が
            # 必ず1になるので、絞ってある高さでも満額が届く。
            span = min(1.0, abs(x - center_x) / _half_width(y))
            if x <= center_x:
                new_x -= shift * span
            else:
                new_x += shift * span
        return new_x, new_y

    # 基準の高さに頂点を足してから写す。足さないと、重みの山(ウエスト)を
    # 通る点が上下の中間として描かれ、満額が届かない(上の
    # `_split_at_heights` のコメント参照)。
    dense = _split_at_heights(segments, (y_underarm, y_waist))
    return _remap_segments(dense, point_map)
