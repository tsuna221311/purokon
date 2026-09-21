"""cutting.py — 型紙の各パーツに書く「裁ち方の指示」(round31)。

JIS L 0110「衣料パターンの表示記号」は、パターン1枚ごとに
**何を何枚裁つか**が分かるようになっていることを前提にしている
(表示記号そのものは形の記号だが、布目線・裁断枚数・生地の種類・
接着芯の指示が揃って初めて「そのまま裁断に使える型紙」になる)。
round30まで、この型紙が書いていたのは布目線とパーツ名だけだった。

実際に困るのは次の2つで、どちらも縫い始める前に布を無駄にする:

  1. **わ裁ちの取り違え** —— 日本の市販型紙は身頃を「半身+わ裁ち」で
     出すものが多い。この型紙の身頃は左右がつながった**全幅**で出て
     いるので、そのつもりで中心を布のわ(輪)に合わせて置くと、
     倍の幅の身頃が裁ち上がる。「わ裁ち不要」と書いてあれば起きない。
  2. **接着芯の貼り忘れ** —— 衿・見返し・カフス・ウエストバンドには
     接着芯を貼るのが定石で、貼らないと衿が立たずカフスがよれる。
     出典: DRCOS「接着芯の縫い代処理」(https://dr-cos.com/kt-interfacing.html)
     ——「襟や見返し、カフスなどには必ず接着芯を貼ります」。

裏地・別布は、このエンジンがまだ生成しないので書かない
(書けば「裏地も付ける型紙だ」と読めてしまう)。
"""

from __future__ import annotations

#: 接着芯を**全面に**貼るパーツ種。上記の出典どおり、衿・カフスと、
#: それに準じるウエストバンド(伸びどめが要る帯)。
#: 身頃・袖・スカート・パンツには貼らない。
INTERFACED_PART_TYPES: frozenset[str] = frozenset({
    "collar", "cuffs", "waistband",
})

#: 接着芯を**一部にだけ**貼るパーツ種 -> どこに貼るか(round33)。
#:
#: 【round31で雑だった点】前開きの片側パネル(`front_bodice_zip_panel`)を
#: 上の集合に入れていたため、「表地1枚 わ裁ち不要 接着芯あり」と書かれた。
#: このパーツは**身頃の半身に見返し(裏側の折り返し布)が付いた形**なので、
#: そのまま読むと身頃全体に芯を貼ることになり、板のように固い前身頃が
#: 出来上がる。芯が要るのは中心前の見返し部分だけである。
PARTIAL_INTERFACING: dict[str, str] = {
    "front_bodice_zip_panel": "見返し部分に接着芯",
}

#: 生地の種類。裏地・別布を生成しないので、今は表地しかない。
FABRIC_LABEL = "表地"


def needs_interfacing(part_type: str) -> bool:
    """接着芯が要るパーツか(全面・一部を問わない)。"""
    return part_type in INTERFACED_PART_TYPES or part_type in PARTIAL_INTERFACING


def interfacing_note(part_type: str) -> str:
    """接着芯の指示。要らないパーツでは空文字。"""
    if part_type in PARTIAL_INTERFACING:
        return PARTIAL_INTERFACING[part_type]
    return "接着芯あり" if part_type in INTERFACED_PART_TYPES else ""


def cutting_note(part_type: str, cut_quantity: int = 1,
                  cut_on_fold: bool = False) -> str:
    """パーツに書き添える裁ち方の指示。

    >>> cutting_note("front_bodice")
    '表地1枚 わ裁ち不要'
    >>> cutting_note("collar", 2)
    '表地2枚 わ裁ち不要 接着芯あり'
    >>> cutting_note("front_bodice_zip_panel")
    '表地1枚 わ裁ち不要 見返し部分に接着芯'
    """
    parts = [f"{FABRIC_LABEL}{max(1, int(cut_quantity))}枚"]
    parts.append("わ裁ち" if cut_on_fold else "わ裁ち不要")
    note = interfacing_note(part_type)
    if note:
        parts.append(note)
    return " ".join(parts)
