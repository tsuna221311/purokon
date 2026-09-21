"""blocks.py — 原型(ブロック)の定義。round42で追加。

【round41まで何が足りなかったか】このエンジンの身頃は、はじめから最後まで
**新文化式の婦人原型**の式で組まれていた。背幅 B/8+7.4、胸幅 B/8+6.2、
前ネック幅 B/24+3.4、胸ぐせダーツ (B/4−2.5)°——どれも成人女子の体型から
導かれた式である。にもかかわらず、採寸欄には身長120cmから入力できたので、
**子どもの寸法を入れると、子どもの体に成人女子の原型を当てた型紙が出て
いた**。しかも一言も断っていなかった。

実測(身長120cm・バスト60cmの子ども。子ども原型の値との差):

    項目          エンジン   子ども原型      差
    背幅(片側)     14.90     13.20      -1.70
    胸幅(片側)     13.70     12.00      -1.70
    前ネック幅       5.90      6.40      +0.50
    胸ぐせ角度      12.5°      8.0°      -4.5°
    ゆとり(総回り)   8.00     15.00      +7.00

背幅・胸幅が片側1.7cm(左右で3.4cm)広く、ゆとりは7cm足りず、胸ぐせダーツは
6歳児の型紙に4.5°ぶん余計に入っていた。**子ども向けの型紙として売り物に
ならない**。

【このモジュールがすること】
「どの原型の式で引くか」を1つのデータにまとめ、身頃の式を引く箇所が
そこを見るようにする。式はすべて `値 = もと/除数 + 定数` の形に収まるので、
`Formula` 1つで表せる(定数だけの式は除数をNoneにする)。

【今あるのは2つ。男性原型は入っていない】
  * `ADULT_FEMALE` … 成人女子(新文化式)。round41までの挙動そのまま。
  * `CHILD`        … 子ども(新文化式子供原型)。

男性原型は**今回入れられなかった**。式が数字で書かれた資料が、無料で
読める範囲では見つからなかったためである(見つかったのは実物大の型紙の
販売ページと、教科書のスキャンを無断掲載したPDFだけだった)。
「男性は胸ぐせダーツが要らない」ところまでは分かるが、背幅・胸幅・
袖ぐり深さ・肩傾斜の式が分からないまま半分だけ作って「男性原型」と
名乗るのは、根拠のない寸法を型紙に載せることになる。だから入れない。
入れるのに要るのは、**式が数字で書かれた出典**ひとつだけである。

【出典】
成人女子(新文化式):
  MAISON DE AS「【原型製図】レディース原型作り(新文化式)」
  https://maisondeas.com/pattern-block-new-bunka/
子ども(新文化式子供原型):
  MAISON DE AS「【原型製図】子供原型作り(新文化)」
  https://maisondeas.com/kids-pattern-block-new-bunka/
子どもの参考寸法:
  MAISON DE AS「採寸の仕方【男性・女性・子供】」
  https://maisondeas.com/taking-measurements/
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Formula:
    """`値 = もと/divisor + const` の形の製図式。

    divisor が None なら「もと」を見ない定数(子どもの胸ぐせ8°など)。
    base は「もと」に何を入れるか: "bust"(バスト) か "height"(身長)。
    """
    divisor: float | None
    const: float
    base: str = "bust"

    def __post_init__(self) -> None:
        if self.base not in ("bust", "height"):
            raise ValueError(f"baseは'bust'か'height'です: {self.base!r}")
        if self.divisor is not None and self.divisor == 0:
            raise ValueError("divisorに0は指定できません")

    def value(self, bust_cm: float, height_cm: float | None = None) -> float:
        if self.divisor is None:
            return self.const
        source = bust_cm if self.base == "bust" else height_cm
        if source is None:
            raise ValueError(
                f"この式は{self.base}を必要としますが渡されていません: {self}")
        return source / self.divisor + self.const

    def text(self) -> str:
        """注記に出す、人間が読める式(「B/8 + 7.4cm」など)。"""
        if self.divisor is None:
            return f"{self.const:g}"
        name = "B" if self.base == "bust" else "身長"
        sign = "+" if self.const >= 0 else "−"
        if self.const == 0:
            return f"{name}/{self.divisor:g}"
        return f"{name}/{self.divisor:g} {sign} {abs(self.const):g}"


@dataclass(frozen=True)
class Block:
    """1つの原型(ブロック)。身頃の製図の式をまとめて持つ。"""

    key: str
    label: str
    source_name: str
    source_url: str

    #: この原型が想定している身長の範囲(cm)。外れたら**警告**を出すが、
    #: 生成そのものは止めない——境目の体型は実在するので、
    #: 「この原型は身長◯〜◯cm向けです」と伝えて選び直せるようにする。
    height_range_cm: tuple[float, float]

    #: 背幅(後ろ中心から後ろの袖ぐりの点まで、片側cm)。
    back_width: Formula
    #: 胸幅(前中心から前の袖ぐりの点まで、片側cm)。
    chest_width: Formula
    #: 前ネック幅(前中心から首の付け根まで、片側cm)。
    neck_half: Formula
    #: 胸ぐせダーツの角度(度)。
    bust_dart_angle: Formula
    #: 「標準」のゆとり(身頃の総回りに足す量、cm)。
    #: 利用者が選ぶゆとり(fitted/relaxed)は、この値からの増減として効く。
    standard_ease: Formula

    #: 袖ぐり深さ(首の付け根の線から脇の下まで、cm)の**絶対値**の式。
    #: Noneなら、テンプレートの深さを身長比で伸縮させたうえでバストぶんの
    #: 増分を足す従来方式を使う(`engine/bodice_fit.py`の`armhole_depth_cm`)。
    armhole_depth: Formula | None = None

    #: 肩傾斜(水平線に対する角度、度)。前身頃・後ろ身頃で違う。
    #:
    #: 【なぜ要るか】round42まで、このエンジンの肩線の傾きは**製図した角度で
    #: はなかった**。肩先のx位置だけを「肩幅/2」に置き、y位置はテンプレートの
    #: 形を身長比で伸縮した結果に任せていたので、傾きは体型の副産物になる。
    #: 実測(前肩傾斜。原型はどちらも22°/23°と書いているのに):
    #:
    #:     体型                     前      後ろ
    #:     標準M(身長158 B83 肩37)  24.48°  21.13°
    #:     背が高い(身長185)        28.06°  24.35°
    #:     背が低い(身長145)        22.67°  19.53°
    #:     いかり肩(肩幅42)         20.54°  17.65°
    #:     なで肩(肩幅32)           30.10°  26.21°
    #:
    #: **背を高くしただけで肩の傾きが3.6°変わる**。丈方向の伸縮が肩先の
    #: 落ち(rise)だけを伸ばし、肩幅で決まる横(run)は伸びないためである。
    #: 肩幅を狭く入力した人は、なで肩でもないのに30°の肩線を渡される。
    #:
    #: 製図では逆で、**先に角度を引いてから肩幅を測る**。round43でその順に
    #: 直し、肩先のyを「首の付け根から、この角度で下がった位置」に置く。
    shoulder_slope_front_deg: float = 22.0
    shoulder_slope_back_deg: float = 18.0

    #: 型紙にBP(バストポイント)の記号を描くか。
    draws_bust_point: bool = True

    #: テンプレートを縮められる下限の倍率。Noneなら全体の既定
    #: (`engine/part_specs.py`の`MIN_SCALE`=0.7)を使う。
    #:
    #: 【なぜ原型ごとに要るか】0.7は成人女子だけを見て置かれた値で、
    #: 標準M(身長158cm)の0.7倍は110.6cmにあたる。子どもの参考寸法12段階の
    #: うち**10段階**がこれに当たり、身長80cmの子の身頃丈が44.1cm——
    #: 身長108cmの子とまったく同じ丈——で出ていた(実測)。
    #:
    #: 【下げてよいと言える根拠】倍率を0.7から0.2まで下げて、
    #: 身長70〜80cmの体型で「身頃+袖+スカート+衿+カフス」を生成し、
    #: 裁断線・縫い線がshapelyで有効な単純多角形であること、縫い合わせ長さの
    #: 整合警告が出ないこと、配置できないパーツが出ないことを確認した。
    #: **0.2まで一度も壊れなかった**ので、0.7は幾何の限界ではなく
    #: 「異常入力への歯止め」だったと分かる。歯止めそのものは
    #: `_VALID_RANGES`が担っている。
    min_scale: float | None = None

    def ease_cm(self, bust_cm: float) -> float:
        return self.standard_ease.value(bust_cm)

    def shoulder_slope_deg(self, part_type: str) -> float:
        """このパーツの肩傾斜(度)。後ろ身頃だけ後ろの角度を使う。"""
        return (self.shoulder_slope_back_deg if part_type.startswith("back_")
                else self.shoulder_slope_front_deg)

    def height_note(self, height_cm: float) -> str | None:
        """身長がこの原型の想定から外れていれば、その注記を返す。"""
        lo, hi = self.height_range_cm
        if lo <= height_cm <= hi:
            return None
        return (f"「{self.label}」は身長{lo:g}〜{hi:g}cm向けの原型です"
                f"(入力された身長は{height_cm:g}cm)。"
                f"{'小さすぎる' if height_cm < lo else '大きすぎる'}体型では、"
                "背幅・胸幅・袖ぐりの深さが体に合わない可能性があります。"
                "原型の選択を確かめてください。"
                f" 出典: {self.source_name} {self.source_url}")


#: 成人女子(新文化式)。round41までの挙動そのまま——数値は1つも変えていない。
#:
#: 背幅 B/8+7.4 / 胸幅 B/8+6.2 / 前ネック幅 B/24+3.4 /
#: 胸ぐせ (B/4−2.5)°。
#:
#: ゆとり8.0cmだけは新文化式の原型そのもの(B/2+6、総回り12cm)ではなく、
#: **このエンジンが布帛の身頃向けに選んだ値**である(round23。理由は
#: `engine/bodice_fit.py`の`BODICE_EASE_CM`のコメント参照)。原型の式では
#: ないが、「標準ゆとり」は原型ごとに持つべき値なのでここに置く。
ADULT_FEMALE = Block(
    key="adult_female",
    label="大人（女性）",
    source_name="MAISON DE AS「【原型製図】レディース原型作り(新文化式)」",
    source_url="https://maisondeas.com/pattern-block-new-bunka/",
    height_range_cm=(140.0, 190.0),
    back_width=Formula(8.0, 7.4),
    chest_width=Formula(8.0, 6.2),
    neck_half=Formula(24.0, 3.4),
    bust_dart_angle=Formula(4.0, -2.5),
    standard_ease=Formula(None, 8.0),
    armhole_depth=None,
    # 「SNPを基点として水平線に対して22°の前肩傾斜をとり」
    # 「SNPを基点に水平線に対して18°の後ろ肩傾斜をとり」
    shoulder_slope_front_deg=22.0,
    shoulder_slope_back_deg=18.0,
    draws_bust_point=True,
    min_scale=None,
)

#: 子ども(新文化式子供原型)。
#:
#: 出典の製図手順から、そのまま式にできたものだけを入れている:
#:   背幅   = バスト/5 + 1.2      (「背幅（バスト寸法÷5+1.2）」)
#:   胸幅   = バスト/5            (「胸幅（バスト寸法÷5）」)
#:   前ネック幅 = 背幅/2 − 0.2 = B/10 + 0.4
#:            (「背幅寸法を2等分した点…その点からA点までを後ろ襟ぐり幅(◎)」
#:             「前襟ぐり幅（◎-0.2）」)
#:   胸ぐせ  = 8°                 (「Fを基点に8°とり」)
#:   ゆとり  = バスト/4            (「バスト寸法÷2にゆとり分バスト寸法÷8」
#:             ——半身にB/8なので総回りではB/4)
#:   袖ぐり深さ = 身長/8 + 1        (「背丈(身長÷4)」「A点から背丈÷2+1(ゆとり)」)
#:
#: BPは描かない。子どもの体にバストポイントは無く、出典の製図にも
#: BPは出てこない(胸ぐせ8°は袖ぐり側で回す操作として書かれている)。
CHILD = Block(
    key="child",
    label="子ども",
    source_name="MAISON DE AS「【原型製図】子供原型作り(新文化)」",
    source_url="https://maisondeas.com/kids-pattern-block-new-bunka/",
    height_range_cm=(80.0, 150.0),
    back_width=Formula(5.0, 1.2),
    chest_width=Formula(5.0, 0.0),
    neck_half=Formula(10.0, 0.4),
    bust_dart_angle=Formula(None, 8.0),
    standard_ease=Formula(4.0, 0.0),
    armhole_depth=Formula(8.0, 1.0, base="height"),
    # 「前身頃SNPを基点に水平線に対し、23°の前肩傾斜をとり」
    # 「SNPを基点に水平線に対して19°の後ろ肩傾斜をとり」
    shoulder_slope_front_deg=23.0,
    shoulder_slope_back_deg=19.0,
    draws_bust_point=False,
    # `_VALID_RANGES`の下限がすべて通る値。いちばんきついのは袖丈で
    # 15cm ÷ 標準52cm = 0.288。それを下回る0.25にしてある
    # (`tests/test_round42_blocks.py`が、範囲を動かしてもこの値が
    #  下限を割らないことを見張る)。
    min_scale=0.25,
)

BLOCKS: dict[str, Block] = {b.key: b for b in (ADULT_FEMALE, CHILD)}
DEFAULT_BLOCK_KEY = ADULT_FEMALE.key


def get_block(key: str | None) -> Block:
    """キーから原型を引く。Noneや空文字なら既定(成人女子)。

    知らないキーはエラーにする——黙って既定に落とすと、子どもを選んだ
    つもりで大人の型紙が出る。
    """
    if not key:
        return BLOCKS[DEFAULT_BLOCK_KEY]
    if key not in BLOCKS:
        raise ValueError(
            f"原型は {sorted(BLOCKS)} のいずれかを指定してください: {key!r}")
    return BLOCKS[key]


def block_warnings(block: Block, height_cm: float) -> list[str]:
    """この原型では体型が合っていない、という**警告**(round42)。

    【なぜ`block_notes`と分けるか】round32で、注記(青い「この型紙の
    作り方」)と警告(赤い「縫う前に確認してください」)を分けた。身長が
    原型の想定から外れているのは**確認してほしいこと**なので警告側に置く。

    そして、**既定の原型でも出す**。round42で最初に書いたときは
    `block_notes`の中に混ぜていたため、既定(成人女子)では早期returnで
    捨てられていた——身長100cmの子に大人の原型を当てたときこそ出したい
    警告なのに、そのときだけ出ない、という取りこぼしになっていた
    (`tests/test_round42_blocks.py`が実際に落ちて発覚)。
    """
    note = block.height_note(height_cm)
    return [note] if note else []


def block_notes(block: Block, bust_cm: float, height_cm: float) -> list[str]:
    """この原型で引いたことと、使った式を開示する注記(round42)。

    既定の成人女子では**何も出さない**——round41までと同じ型紙なので、
    毎回同じ説明が並ぶのは邪魔なだけである。既定以外を選んだときだけ、
    「何の式で引いたか」と出典を出す。

    身長が原型の想定から外れている場合の警告は`block_warnings`が持つ
    (原型を問わず出す必要があるため)。
    """
    if block.key == DEFAULT_BLOCK_KEY:
        return []
    notes = [
        f"原型「{block.label}」で引きました。"
        f"背幅={block.back_width.text()}cm・胸幅={block.chest_width.text()}cm・"
        f"前ネック幅={block.neck_half.text()}cm・"
        f"胸ぐせダーツ={block.bust_dart_angle.value(bust_cm):g}°・"
        f"ゆとり={block.ease_cm(bust_cm):.1f}cm"
        + (f"・袖ぐり深さ={block.armhole_depth.text()}cm"
           if block.armhole_depth is not None else "")
        + f"。出典: {block.source_name} {block.source_url}",
    ]
    if not block.draws_bust_point:
        notes.append(
            "この原型ではBP(バストポイント)の印を型紙に描きません。"
            "出典の製図にBPが出てこないためです。")
    return notes


#: 男性原型を**入れなかった**理由。READMEと画面の両方から参照する。
#:
#: 黙って「無い」ままにすると、利用者は探し続けることになる。
#: 何が足りないのかまで書いておけば、資料を持っている人が持ってこられる。
MENS_BLOCK_ABSENT_NOTE = (
    "男性の原型はまだありません。背幅・胸幅・袖ぐり深さ・肩傾斜の式が"
    "数字で書かれた資料が、無料で読める範囲では見つからなかったためです"
    "(見つかったのは実物大の型紙の販売ページと、教科書のスキャンを"
    "無断掲載したPDFだけでした)。「男性は胸ぐせダーツが要らない」ところまでは"
    "分かりますが、残りの式が分からないまま半分だけ作って「男性原型」と"
    "名乗ると、根拠のない寸法が型紙に載ります。"
    "式が数字で書かれた出典が1つあれば入れられます。"
)
