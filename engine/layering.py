"""layering.py — 上に羽織る服のゆとりを、中に着る服の出来上がり寸法から決める
(round74で追加)。

【round73までの状態】ゆとりは**素体**に対してしか計算できなかった。
`FIT_PRESETS`は「ぴったり+4cm / 標準+8cm / ゆったり+14cm」で、どれも
バスト実寸に足す量である。中に何を着るかは、どこにも入らない。

そのせいで何が起きるか。1着の衣装を「中に着るワンピース」と「上に羽織る
コート」の2着に分けて作ると、こうなる(素体バスト82cm):

```
    ニットワンピース (中に着る)   出来上がりバスト 90.0cm
    コート           (上に羽織る) 出来上がりバスト 90.0cm  ← まったく同じ
    コート(ゆったり)              出来上がりバスト 96.0cm  ← +6.0cm
```

**上に羽織る方が、中に着る方と同じ太さで出てくる。** 既定のまま2着作ると、
物理的に重ねて着られない。「ゆったり」を選んでも+6cmで、袖のある服の上に
羽織るのに要る10cmに届かない。そして画面には何も出ない——2着とも
「標準のゆとりで作りました」としか言わない。

【このモジュールがすること】
重ね着では、**中に着る服の出来上がり寸法を「体」として扱う**。
外側の服のゆとりは、素体からではなく、中の服の出来上がり寸法から数える。

    外側のゆとり(素体に対して) = (中の服の出来上がり寸法 - 素体) + 重ねる分

「重ねる分」だけが新しい数字で、それには出典がある(下記)。中の服の
出来上がり寸法は、このエンジンが自分で引いた型紙から測れる値なので、
推定でも目安でもない。

【正直な限界】
- **布の厚みは入れていない。** 厚手のコート地やボアを使うと、ここで足した
  分をその厚みが食う。何mm見込むべきかを数字で書いた資料が見つからなかった
  ので、足さずに注記で伝える(`layering_notes`)。
- 袖(二の腕まわり)には、この計算を掛けていない。袖は袖ぐりの長さに
  追従して太るので(`engine/compatibility.py`)、身頃を太らせれば袖も
  一緒に太る。二の腕そのものの重ね着分は見ていない。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 何かの上に重ねて着る服が、**中の服の出来上がり寸法**に対して最低限
#: 足さなければならない量(cm)。
#:
#: 出典: Sewingplums "Ease levels"
#: https://sewingplums.com/2013/10/12/ease-levels/
#:   "A jacket needs to be at least 1 inch larger than what it's layered over"
#: 1インチ = 2.54cm をそのまま採る。
LAYER_MIN_EASE_CM = 2.54

#: **袖のある服**(シャツ・ブラウス・ワンピース)の上に重ねるときの量(cm)。
#:
#: 出典: 同上
#:   "For layering a lined jacket over a sleeved shirt/blouse,
#:    many people prefer at least 4 in / 10 cm"
#: 資料が cm を併記しているので、10.0 をそのまま採る。
LAYER_OVER_SLEEVED_CM = 10.0

#: 重ねる分を、スカート・パンツのウエスト/ヒップにも同じだけ上乗せする。
#: ただし`engine/part_specs.py`の`CUSTOM_EASE_RANGES`が受け付ける上限で止める。
#:
#: 【正直な限界】出典(Sewingplums)が書いているのは**バスト**についてである。
#: 同じ量をウエスト・ヒップへ当てているのは「同じだけ外側にあるのだから
#: 同じだけ要る」という素直な当てはめで、そこに出典は無い。上着の裾が
#: 中のスカートの上に乗らないよりはましだ、という判断で入れている。
WAIST_ADD_MAX_CM = 13.0
HIP_ADD_MAX_CM = 16.0


@dataclass(frozen=True)
class LayerPlan:
    """重ね着のゆとりを計算した結果。"""

    #: 中に着る服の出来上がりバスト(cm)。
    inner_bust_cm: float
    #: 素体のバスト(cm)。
    body_bust_cm: float
    #: 中の服に対して足す量(cm)。
    layer_cm: float
    #: 素体に対するゆとり(cm)。これを`FitEase.bodice_cm`として使う。
    bodice_ease_cm: float
    #: 中に着る服に袖があるか(足す量の根拠が変わる)。
    inner_has_sleeves: bool
    #: スカート・パンツのウエスト/ヒップに足す量(cm)。素の設定への**上乗せ**。
    waist_add_cm: float = 0.0
    hip_add_cm: float = 0.0

    @property
    def outer_bust_cm(self) -> float:
        """上に羽織る服の、狙う出来上がりバスト(cm)。"""
        return self.body_bust_cm + self.bodice_ease_cm


def plan_layer(body_bust_cm: float, inner_bust_cm: float, *,
               inner_has_sleeves: bool = True) -> LayerPlan:
    """上に羽織る服のゆとりを決める。

    `inner_bust_cm`は中に着る服の**出来上がり**バスト(素体ではない)。
    """
    layer = LAYER_OVER_SLEEVED_CM if inner_has_sleeves else LAYER_MIN_EASE_CM
    ease = (float(inner_bust_cm) - float(body_bust_cm)) + layer
    return LayerPlan(inner_bust_cm=float(inner_bust_cm),
                     body_bust_cm=float(body_bust_cm),
                     layer_cm=layer,
                     bodice_ease_cm=ease,
                     inner_has_sleeves=bool(inner_has_sleeves),
                     waist_add_cm=min(layer, WAIST_ADD_MAX_CM),
                     hip_add_cm=min(layer, HIP_ADD_MAX_CM))


def too_tight_to_layer(outer_bust_cm: float | None,
                        inner_bust_cm: float | None) -> str:
    """上に羽織る服が中の服の上に入らないなら、その説明を返す。

    「入らない」の線引きは`LAYER_MIN_EASE_CM`(最低1インチ)。これを
    下回ったら、重ねて着ることはできない。
    """
    if outer_bust_cm is None or inner_bust_cm is None:
        return ""
    gap = float(outer_bust_cm) - float(inner_bust_cm)
    if gap >= LAYER_MIN_EASE_CM:
        return ""
    if gap < 0:
        return (f"上に羽織る服(出来上がりバスト{outer_bust_cm:.1f}cm)が、"
                f"中に着る服({inner_bust_cm:.1f}cm)より"
                f"{-gap:.1f}cm**細い**ので、重ねて着られません")
    return (f"上に羽織る服(出来上がりバスト{outer_bust_cm:.1f}cm)と"
            f"中に着る服({inner_bust_cm:.1f}cm)の差が{gap:.1f}cmしかありません"
            f"(重ねて着るには最低{LAYER_MIN_EASE_CM:.1f}cm要ります)")


def finished_bust_cm(body_bust_cm: float, bodice_ease_cm: float) -> float:
    """その設定で引いた身頃の、出来上がりバスト(cm)。

    身頃は「(バスト + ゆとり) ÷ 4」を四半分として引くので、出来上がりは
    定義上 `バスト + ゆとり` である(`engine/bodice_fit.py`の
    `bodice_x_scale`)。型紙から測り直す関数も書いてみたが、**前開きの
    片側パネルで値が動かない**——`side_seam_edges`が非対称な輪郭では
    見返しの折り返し側を脇線と取り違えるためで、実測すると前開きの
    コートだけゆとりをいくら変えても幅が21.76cmのまま出た。
    測り方の誤りを「エンジンの欠陥」と読み違えかけたので、ここでは
    引いた値そのものを使い、**型紙が本当にその幅になっているか**は
    テスト側で基準点(`fit_anchors_scaled`)から確かめる。
    """
    return float(body_bust_cm) + float(bodice_ease_cm)


def layering_notes(plan: LayerPlan | None) -> list[str]:
    """利用者に開示する、重ね着のゆとりの説明。"""
    if plan is None:
        return []
    source = ("袖のある服" if plan.inner_has_sleeves else "袖の無い服")
    return [
        f"中に着る服(出来上がりバスト{plan.inner_bust_cm:.1f}cm)の上に羽織る"
        f"前提で、この服は出来上がりバスト{plan.outer_bust_cm:.1f}cmで"
        f"引いています(素体{plan.body_bust_cm:.1f}cmに対するゆとりは"
        f"{plan.bodice_ease_cm:.1f}cm)。",
        f"中の服に足した{plan.layer_cm:.1f}cmは、{source}の上に重ねるときの"
        "目安です(出典: Sewingplums「Ease levels」)。"
        f"スカート・パンツのウエストにも+{plan.waist_add_cm:.1f}cm、"
        f"ヒップにも+{plan.hip_add_cm:.1f}cmを上乗せしています"
        "(出典が書いているのはバストについてで、ここは同じ量を当てはめた"
        "だけです)。",
        "**布の厚みは見込んでいません。** 厚手のコート地・ボア・キルティングを"
        "使う場合は、その分を手で足してください"
        "(このエンジンは生地の厚みを入力として持っていません)。",
    ]
