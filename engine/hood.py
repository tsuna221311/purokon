"""hood.py — フード(パーカーの頭巾)の型紙を引く。round75で追加。

【round74までの状態】フードは**作れなかった**。パーツ種は身頃・袖・
スカート・パンツ・衿・カフス・ウエストバンドの7つで、衿はどれも
「首に巻く帯」である(`collar__*`)。頭を覆うものが1つも無い。

コスプレ衣装でフードの付いた上着は珍しくない。作れないので、利用者は
そこだけ別の型紙を探すことになる。

【このモジュールがすること】
フードを**製図する**。テンプレートを採寸比で伸縮させる他のパーツと違い、
フードは**2つの独立した寸法**に同時に従わなければならない:

  1. 頭が入ること          … 頭囲から決まる
  2. 首ぐりに縫い付くこと  … 身頃の首ぐりの長さから決まる

比率で伸縮させると、どちらか片方しか合わない。だから引く。

【引き方と出典】
MAISON DE AS「フードの製図方法」 https://maisondeas.com/hood-pattern/

    頭回り寸法 … 眉間から後頭部の一番出てるところまでを一周測り、2で割る
    フード寸法 … NP(ネックポイント)から頭頂部を通り一周測り、2で割る
    縦 … 「フード寸法に2〜5cm足した寸法」(例: フード寸法39cm → 41〜44cm)
    横 … 「頭回り寸法から1〜3cm引いた寸法」(例: 頭回り28cm → 25〜27cm)

玉置の仕事場「フードの作り方」 https://tamasan.com/lecture/801/

    前中心の下げ幅 … 「約2〜4cm」(立体的フード)、「2.5cm」(平面的フード)

幅のある指定はどれも**真ん中**を採る(縦 +3.5cm、横 −2cm)。端を採ると、
なぜその端なのかを説明できない。

【正直な限界】
- **フード寸法(NP→頭頂→一周÷2)は、測っていなければ頭囲から見積もる。**
  資料が挙げている例が「頭回り28cm(=頭囲56cm)のときフード寸法39cm」の
  1組だけなので、その比(0.696)をそのまま使っている。**1例からの
  当てはめ**であって、資料がその比を書いているわけではない。
  測った値を入れれば、そちらが使われる。
- 2枚剥ぎ(中心後で縫い合わせる)のフードだけを引く。3枚剥ぎ・
  ドローコード穴・紐通しの始末は入っていない。
- 裏フードは、表と同じ形で作る前提(`engine/lining.py`と同じ考え方)。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 縦(フードの高さ)に足す量(cm)。資料は「2〜5cm」で、その真ん中。
HOOD_HEIGHT_EASE_CM = 3.5
#: 横(フードの奥行き)から引く量(cm)。資料は「1〜3cm」で、その真ん中。
HOOD_DEPTH_REDUCTION_CM = 2.0
#: 前中心の下げ幅(cm)。玉置の「平面的フード 2.5cm」をそのまま採る。
HOOD_FRONT_DROP_CM = 2.5

#: 顔の開き(前端)を裏側へ折る量(cm)。
#:
#: 出典: うさこの洋裁工房「フードの作り方」
#: https://yousai.net/how_to/bubunnui/collar/hood
#:   「前中心だけ2cm、他は1cm」「顔が出る所の縫い代を2cm裏側にアイロンで折る」
HOOD_FRONT_FOLD_CM = 2.0

#: 頭囲から「フード寸法」を見積もる比。
#:
#: 資料(MAISON DE AS)の作例が「頭回り28cm・フード寸法39cm」の1組。
#: 頭回りは頭囲の半分なので頭囲56cm、39/56 = 0.696。**1例からの当てはめ**で
#: あることは、このモジュールのdocstringと利用者への注記に書いてある。
HOOD_LENGTH_FROM_HEAD_RATIO = 39.0 / 56.0

#: 頭囲を測っていない場合に使う、成人女性の頭囲(cm)。
#:
#: 出典: ライオン堂「帽子のサイズの測り方は？頭囲の平均と年齢別のサイズ目安」
#: https://lion-do.jp/blog/boushi/73
#:   成人女性「約57センチ」「ボリュームゾーンは、56cm〜58cm」
#:
#: より確かな出典として産総研「日本人頭部寸法データベース2001」(317名・
#: 頭囲を含む16項目)があるが、統計量はメールで申し込んで受け取る形式で、
#: この環境から数値を得られなかった。**帽子店の記事の値**であることを、
#: 利用者への注記にも書く。
DEFAULT_HEAD_CIRCUMFERENCE_CM = 57.0

#: 首ぐりの長さに対して、フードの付け根がこれ以上短い/長いと引けない。
#: 引けないときは黙って歪めず、その旨を返す。
HOOD_NECK_TOLERANCE_CM = 0.5

#: フードの奥行きに対する、首ぐり側の最小の割合。
#:
#: フードの付け根(首ぐりの半分)が奥行きに近づくほど、顔の開きが前へ
#: 倒れる。0.95を超えると前端がほぼ垂直になり、頭が入らない。
HOOD_MIN_FRONT_SETBACK_RATIO = 0.05


@dataclass(frozen=True)
class HoodPlan:
    """フードを引くのに要る寸法(cm)。"""

    head_circumference_cm: float
    hood_length_cm: float
    neckline_cm: float
    #: 奥行き(前後方向)。頭回り − 2cm。
    depth_cm: float
    #: 高さ。フード寸法 + 3.5cm。
    height_cm: float
    #: 付け根(1枚あたり)。首ぐりの半分。
    neck_edge_cm: float
    #: 前端が、いちばん前から何cm後ろに付くか。
    front_setback_cm: float
    #: 頭囲を測らずに既定値を使ったか。
    head_estimated: bool
    #: フード寸法を頭囲から見積もったか。
    length_estimated: bool
    #: 引けなかった理由(引けたなら空文字)。
    reason: str = ""

    @property
    def usable(self) -> bool:
        return not self.reason


def hood_length_from_head_cm(head_circumference_cm: float) -> float:
    """頭囲から「フード寸法」(NP→頭頂→一周÷2)を見積もる。"""
    return float(head_circumference_cm) * HOOD_LENGTH_FROM_HEAD_RATIO


def plan_hood(neckline_cm: float,
              head_circumference_cm: float | None = None,
              hood_length_cm: float | None = None) -> HoodPlan:
    """フードの寸法を決める。

    `neckline_cm`は身頃の首ぐりの**全長**(前+後ろ)。フードは2枚剥ぎなので、
    1枚の付け根はその半分になる。
    """
    head_estimated = head_circumference_cm is None
    head = float(head_circumference_cm if head_circumference_cm is not None
                 else DEFAULT_HEAD_CIRCUMFERENCE_CM)
    length_estimated = hood_length_cm is None
    length = float(hood_length_cm if hood_length_cm is not None
                   else hood_length_from_head_cm(head))

    depth = head / 2.0 - HOOD_DEPTH_REDUCTION_CM
    height = length + HOOD_HEIGHT_EASE_CM
    neck_edge = float(neckline_cm) / 2.0
    setback = depth - neck_edge

    # 付け根は下げ幅のぶん反っているので、**弧長**が首ぐりの半分になるよう
    # 前端の位置を解く。直線の長さで置くと、実測で0.18cm長く出た。
    if neckline_cm > 0 and head > 0 and setback > 0:
        setback = _setback_for_arc(depth, height, neck_edge, setback)

    reason = ""
    if neckline_cm <= 0 or head <= 0:
        reason = "首ぐりか頭囲が分かりません"
    elif setback < depth * HOOD_MIN_FRONT_SETBACK_RATIO:
        # 首ぐりが頭の奥行きとほぼ同じ。前端が立ってしまい、頭が入らない。
        reason = (f"首ぐり({neckline_cm:.1f}cm)に対して頭({head:.1f}cm)が"
                  f"小さすぎて、フードの形になりません")
    return HoodPlan(head_circumference_cm=head, hood_length_cm=length,
                    neckline_cm=float(neckline_cm), depth_cm=depth,
                    height_cm=height, neck_edge_cm=neck_edge,
                    front_setback_cm=max(0.0, setback),
                    head_estimated=head_estimated,
                    length_estimated=length_estimated, reason=reason)


def neck_edge_segments(depth_cm: float, height_cm: float,
                        setback_cm: float) -> list[tuple[str, list[float]]]:
    """付け根(首ぐりに縫い付ける辺)だけを取り出した、前下から後ろ下への道。

    `hood_segments`と**同じ式**でなければならないので、ここ1か所に置いて
    両方から使う(2か所に書き写すと、片方だけ直して静かに食い違う)。
    """
    drop = HOOD_FRONT_DROP_CM
    span = depth_cm - setback_cm
    return [
        ("M", [setback_cm, height_cm + drop]),
        ("C", [setback_cm + span * 0.35, height_cm + drop * 0.55,
               setback_cm + span * 0.70, height_cm + drop * 0.12,
               depth_cm, height_cm]),
    ]


def _neck_edge_length(depth_cm: float, height_cm: float,
                       setback_cm: float) -> float:
    from .compatibility import _path_length
    from .svgpath import segments_to_polyline
    return _path_length(segments_to_polyline(
        neck_edge_segments(depth_cm, height_cm, setback_cm), curve_steps=400))


def _setback_for_arc(depth_cm: float, height_cm: float, target_cm: float,
                      first_guess_cm: float) -> float:
    """付け根の**弧長**が target になる前端の位置を二分探索で解く。

    前端を後ろへ下げるほど付け根は短くなるので、単調である。
    """
    lo, hi = 0.0, depth_cm
    if _neck_edge_length(depth_cm, height_cm, first_guess_cm) <= target_cm:
        hi = first_guess_cm
    else:
        lo = first_guess_cm
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _neck_edge_length(depth_cm, height_cm, mid) > target_cm:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    return (lo + hi) / 2.0


def hood_segments(plan: HoodPlan) -> list[tuple[str, list[float]]]:
    """フード1枚ぶんの輪郭を、`engine/svgpath.py`のセグメント列で返す。

    座標は cm。向きは「前が左、上が上」。

        (0,0) 前上 ─────────── 上の丸み ───────── (D, 0.12H) 後ろ上
          \\                                          |
           \\  顔の開き(前端)                          | 中心後(2枚を縫い合わせる)
            \\                                         |
        (S, H+drop) 前下 ──── 付け根(首ぐりへ) ──── (D, H) 後ろ下

    - D … 奥行き(頭回り − 2cm)
    - H … 高さ(フード寸法 + 3.5cm)
    - S … 前端の後退量(D − 首ぐりの半分)
    - drop … 前中心の下げ幅 2.5cm

    付け根の長さが首ぐりの半分ちょうどになるよう、前下の点を置いている。
    """
    d = plan.depth_cm
    h = plan.height_cm
    s = plan.front_setback_cm
    drop = HOOD_FRONT_DROP_CM
    top = h * 0.12
    return [
        # 前端(顔の開き)。上の角から前下へ、ゆるく反らせる。
        ("M", [0.0, 0.0]),
        ("C", [-0.6, h * 0.45, s * 0.35, h * 0.80, s, h + drop]),
        # 付け根。前下から後ろ下へ、下げ幅ぶんの浅いカーブ
        # (式は`neck_edge_segments`と共有する)。
        neck_edge_segments(d, h, s)[1],
        # 中心後(2枚を縫い合わせる辺)。まっすぐ上へ。
        ("L", [d, top]),
        # 上の丸み。後ろ上から前上へ。
        ("C", [d * 0.92, top * 0.18, d * 0.45, -0.4, 0.0, 0.0]),
        ("Z", []),
    ]


def hood_notes(plan: HoodPlan | None) -> list[str]:
    """利用者に開示する、フードの引き方の説明。"""
    if plan is None:
        return []
    if not plan.usable:
        return [f"フードは引けませんでした({plan.reason})。"]
    out = [
        f"フードは、頭囲{plan.head_circumference_cm:.0f}cm・"
        f"首ぐり{plan.neckline_cm:.1f}cmから引きました"
        f"(高さ{plan.height_cm:.1f}cm × 奥行き{plan.depth_cm:.1f}cm、2枚剥ぎ)。"
        "縦は「フード寸法+2〜5cm」、横は「頭回り−1〜3cm」の真ん中を採って"
        "います(出典: MAISON DE AS「フードの製図方法」)。",
    ]
    if plan.head_estimated:
        out.append(
            f"**頭囲を測っていないので、成人女性の平均{DEFAULT_HEAD_CIRCUMFERENCE_CM:.0f}cm"
            "で引きました**(出典: 帽子店ライオン堂の記事)。頭囲を測って"
            "入れると、そちらで引き直します。")
    if plan.length_estimated:
        out.append(
            "フード寸法(首の付け根から頭のてっぺんを通って一周した長さの半分)は、"
            f"頭囲から{HOOD_LENGTH_FROM_HEAD_RATIO:.3f}倍として見積もっています。"
            "この比は資料の作例1つから当てはめたもので、資料が比として"
            "書いている値ではありません。")
    return out
