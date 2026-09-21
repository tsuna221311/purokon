"""plausibility.py — 採寸値の「たぶん測り間違い」を、生成する前に指摘する。round33で追加。

【round32まで何が足りなかったか】採寸ミスは、この型紙がうまくいかない
いちばんの原因である。にもかかわらず、指摘は**生成したあと**にしか出て
いなかった(`engine/scaling.py`のクランプ警告、round31の胸幅の警告)。
1日の生成回数を1回使い、PDFを開いて初めて「肩幅の採寸を確かめてください」
と言われる。入れた直後に分かれば、その回は使わずに済む。

【何を指摘して、何を指摘しないか】
ここで出すのは「**その値だと型紙側で辻褄が合わない**」ことだけである。
「あなたの体型は標準から外れている」という指摘はしない——外れた体型のために
採寸から作るサービスなので、それを咎めるのは筋が違う。判定はすべて、
このエンジンが既に持っている根拠に紐づけてある:

  * 変形できる範囲(`MIN_SCALE`/`MAX_SCALE` = 標準の0.7〜1.6倍)。これを
    超えると、実際には範囲内の近い値へ丸めて生成する(=入力どおりの
    型紙にならない)。round13からある実測に基づく制限。
  * 袖ぐりの点は肩先より外へ出せない。新文化式の胸幅 B/8+6.2 が肩幅の
    半分を超える入力は、幾何的に成立しない(round31で実測・開示済み)。
  * ウエストからヒップを通す。ヒップがウエストより細いと、スカート・
    パンツを履く動作が成り立たない。
  * 項目の入れ違い。バストよりウエストが**大きい**入力は、体型として
    有り得ないわけではないが、実際には「バスト欄とウエスト欄を逆に入れた」
    ことの方がはるかに多い。断定せず、確認を促す。

【正直な限界】
  * ここは**警告であって検証ではない**。指摘があっても生成は止めない
    (止めると、本当にその体型の人が使えなくなる)。
  * 「測り間違いでないのに指摘される」ことは起こりうる。文面は必ず
    「確かめてください」で、「間違っています」とは書かない。
  * 単位の取り違え(inchで入力した等)は、有効範囲(`_VALID_RANGES`)の
    時点で弾かれるものが多いので、ここでは個別に見ていない。
"""

from __future__ import annotations
from dataclasses import dataclass

from .bodice_fit import chest_width_cm
from .measurements import Measurements, STANDARD_M
from .part_specs import MAX_SCALE, MIN_SCALE

#: 画面で「どの入力欄の話か」を示すためのキー(HTMLのid接尾辞と揃える)。
FIELD_LABELS_JA: dict[str, str] = {
    "bust": "バスト",
    "waist": "ウエスト",
    "hip": "ヒップ",
    "height": "身長",
    "sleeve_length": "袖丈",
    "shoulder_width": "肩幅",
    "upper_arm": "二の腕まわり",
    "bust_point_spacing": "乳間",
    "bust_point_drop": "乳下がり",
}

#: 変形できる範囲を見る対象。標準サイズに対する倍率で判定する。
#: (袖丈・肩幅は身頃と別の倍率で使われるので、それぞれ自分の標準と比べる。)
_SCALED_FIELDS = ("bust", "waist", "hip", "height", "sleeve_length", "shoulder_width")


@dataclass(frozen=True)
class MeasurementHint:
    """採寸値についての指摘1件。

    field: 対象の入力欄(画面でその欄の近くに出すため)。
    severity: "warning"(型紙が入力どおりにならない) / "check"(確認を促す)。
    """
    field: str
    severity: str
    message: str

    def as_dict(self) -> dict:
        return {"field": self.field, "severity": self.severity,
                "message": self.message}


def _out_of_scale_range(field: str, value: float) -> MeasurementHint | None:
    standard = getattr(STANDARD_M, field)
    if not standard:
        return None
    ratio = value / standard
    if MIN_SCALE <= ratio <= MAX_SCALE:
        return None
    lo, hi = standard * MIN_SCALE, standard * MAX_SCALE
    clamped = lo if ratio < MIN_SCALE else hi
    return MeasurementHint(
        field, "warning",
        f"{FIELD_LABELS_JA[field]}{value:g}cmは、テンプレートを正確に変形できる範囲"
        f"({lo:.1f}〜{hi:.1f}cm)の外です。このままでも生成はできますが、"
        f"実際には{clamped:.1f}cm相当の型紙になります。"
        "単位(cm)と入力欄を確かめてください。")


def measurement_hints(m: Measurements) -> list[MeasurementHint]:
    """採寸値から「確かめてほしいこと」を返す。無ければ空リスト。

    生成の前に呼ぶ想定。生成は止めない。
    """
    hints: list[MeasurementHint] = []

    # 1. 変形できる範囲の外(実際には丸められる)。
    for field in _SCALED_FIELDS:
        hint = _out_of_scale_range(field, getattr(m, field))
        if hint is not None:
            hints.append(hint)

    # 2. 項目の入れ違いが疑わしい組み合わせ。
    if m.waist > m.bust:
        hints.append(MeasurementHint(
            "waist", "check",
            f"ウエスト({m.waist:g}cm)がバスト({m.bust:g}cm)より大きくなっています。"
            "入力欄を取り違えていないか確かめてください"
            "(そういう体型であればこのまま進めて問題ありません)。"))
    if m.hip < m.waist:
        hints.append(MeasurementHint(
            "hip", "check",
            f"ヒップ({m.hip:g}cm)がウエスト({m.waist:g}cm)より細くなっています。"
            "スカート・パンツはウエストからヒップを通して履くので、この値だと"
            "履く動作が成り立ちません。入力欄を確かめてください。"))

    # 3. 幾何的に成立しない肩幅(round31で実測・開示した制約と同じ判定)。
    #    袖ぐりの点は肩先より外へは出せないので、胸幅の式が肩幅の半分を
    #    超えると、その差だけ胸のあたりが狭い型紙になる。
    need_half = chest_width_cm(m.bust)
    if m.shoulder_width / 2.0 < need_half:
        short = (need_half - m.shoulder_width / 2.0) * 2.0
        hints.append(MeasurementHint(
            "shoulder_width", "check",
            f"バスト{m.bust:g}cmに対して肩幅{m.shoulder_width:g}cmが狭く、"
            f"胸幅が左右あわせて約{short:.1f}cm足りない型紙になります。"
            "肩幅は「左右の肩先の間を背中側で測った長さ」です"
            "(腕の付け根から付け根まで、ではありません)。確かめてください。"))

    # 4. 袖丈と身長の釣り合い。袖丈は身長比で変形するので、極端にずれると
    #    「袖だけが体に合わない」型紙になる。標準(158cm/52cm)からの比で見る。
    expected_sleeve = STANDARD_M.sleeve_length * (m.height / STANDARD_M.height)
    if expected_sleeve > 0:
        ratio = m.sleeve_length / expected_sleeve
        if ratio < MIN_SCALE or ratio > MAX_SCALE:
            hints.append(MeasurementHint(
                "sleeve_length", "check",
                f"身長{m.height:g}cmに対して袖丈{m.sleeve_length:g}cmは、"
                f"標準的な釣り合い(約{expected_sleeve:.0f}cm)から大きく離れています。"
                "袖丈は「肩先から手首まで」です。確かめてください"
                "(半袖・七分袖のデザインであればこのままで問題ありません)。"))

    return hints
