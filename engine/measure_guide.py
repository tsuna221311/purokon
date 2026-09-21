"""measure_guide.py — 各採寸項目の「どこを、どう測るか」。round34で追加。

【なぜ要るか】採寸ミスはこのサービスがうまくいかない最大の原因である。
round33で「入れた値が型紙側で辻褄が合わない」ことは指摘できるようになったが、
**そもそも正しく測る手助けは何もしていなかった**。とくに肩幅は、腕の付け根
から付け根までを測ってしまう人が多く(正しくは背中側で左右の肩先の間)、
round33の指摘文でもわざわざ「腕の付け根から付け根まで、ではありません」と
書く羽目になっていた。指摘するより先に、測る場所を示す方が早い。

文面は採寸の解説からそのまま取っている(出典: MAISON DE AS「採寸の仕方」
https://maisondeas.com/taking-measurements/ )。ここで独自の測り方を
考案してはいけない——測り方が変われば、この型紙の式が前提にしている
寸法の意味が変わってしまう。

`web/templates/index.html`の採寸図(SVG)と、この辞書のキーが対応している
(`data-measure="bust"` 等)。図と文が別々の場所で管理されると片方だけ
古くなるので、**文はここが唯一の出どころ**で、画面はここから受け取る。
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MeasureGuide:
    """1つの採寸項目の測り方。

    label: 画面に出す名前。
    how: どこからどこまでを、どう測るか(1〜2文)。
    caution: よくある間違い。無ければ空文字。
    """
    label: str
    how: str
    caution: str = ""

    def as_dict(self) -> dict:
        return {"label": self.label, "how": self.how, "caution": self.caution}


MEASURE_GUIDES: dict[str, MeasureGuide] = {
    "bust": MeasureGuide(
        "バスト",
        "胸のいちばん高い位置に、メジャーを水平に一周させて測ります。"
        "締め付けないでください。",
        "下着を着けた状態で測ります。",
    ),
    "waist": MeasureGuide(
        "ウエスト",
        "胴のいちばん細いところを、水平に一周させて測ります。",
        "息を吸って止めた状態ではなく、自然に立って測ります。",
    ),
    "hip": MeasureGuide(
        "ヒップ",
        "おしりのいちばん太いところを、水平に一周させて測ります。",
    ),
    "height": MeasureGuide(
        "身長",
        "靴を脱いで、頭のてっぺんから床までを測ります。",
        "丈の全体をこの値で決めるので、他の項目より影響が大きい項目です。",
    ),
    "sleeve_length": MeasureGuide(
        "袖丈",
        "腕をやや曲げ、肩先の骨から手首の小指側の骨までを測ります。",
        "腕をまっすぐ伸ばして測ると、肘の分だけ短くなります。",
    ),
    "shoulder_width": MeasureGuide(
        "肩幅",
        "背中側で、右の肩先の骨から首の付け根を通って左の肩先の骨までを測ります。",
        "腕の付け根から付け根まで、ではありません。ここを取り違えると、"
        "袖ぐりの位置が体に合わなくなります。",
    ),
    "upper_arm": MeasureGuide(
        "二の腕まわり",
        "二の腕のいちばん太いところを、水平に一周させて測ります。",
        "任意です。入れると袖幅がこの実測で決まります。",
    ),
    "bust_point_spacing": MeasureGuide(
        "乳間",
        "左右の乳首から乳首までの間隔を測ります。",
        "任意です。入れると胸ぐせダーツの向きがこの実測で決まります。",
    ),
    "bust_point_drop": MeasureGuide(
        "乳下がり",
        "前中央で、首の付け根からバストのいちばん高いところまでを測ります。",
        "任意です。入れるとダーツの向かう高さがこの実測で決まります。",
    ),
}

#: 図の上で光らせる順(画面の入力欄と同じ並び)。
MEASURE_ORDER: tuple[str, ...] = (
    "bust", "waist", "hip", "height", "sleeve_length", "shoulder_width",
    "upper_arm", "bust_point_spacing", "bust_point_drop",
)


def guides_as_dict() -> dict[str, dict]:
    """画面へ渡すための辞書。`data-*`属性経由でJSに渡す(CSP対応)。"""
    return {key: MEASURE_GUIDES[key].as_dict() for key in MEASURE_ORDER}
