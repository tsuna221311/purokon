"""fabric.py — 「何を、どれだけ買えばよいか」を組み立てる。round38で追加。

【round37まで何が足りなかったか】画面には「幅150cm の生地を 2.6m」とだけ
出ていた。これは**エンジンが選んだ1つの幅**の結果で、他の幅なら何m要るかは
内部で計算しているのに捨てていた。近所の店に110cm幅しか置いていない人は、
自分で換算するしかなかった。接着芯も「接着芯あり」と書くだけで量は出さず、
地直しの縮み分は「その分を足して購入してください」と丸投げしていた。

【このモジュールが出すもの / 出さないもの】
出すのは、**この型紙について実際に計算できる数字**だけ:

  * 生地幅ごとの必要丈(幅を変えてネスティングを実際に回し直した実測)
  * 接着芯の必要量(接着芯が要るパーツだけを、芯地の幅で並べ直した実測)
  * 地直しの縮み分を見込んだ購入量
  * 柄合わせをする場合の上乗せ量の**上限**

出さないのは、値段(変動する・地域差がある)と、店の在庫。
素材の提案は、洋裁の資料に当たって**出典を明記できるものだけ**を出す。
資料に記述が見つからなかった形については、何も言わない——
それらしいことを書けば、根拠のない助言が型紙に載る。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cutting import needs_interfacing
from .nesting import DEFAULT_FABRIC_WIDTHS_CM, nest_parts

#: 生地を買うときの丸め単位(cm)。10cm単位で切り売りされるのが普通。
BUY_ROUND_UP_CM = 10

#: 接着芯の一般的な生地幅(cm)。表地より狭いことが多い。
#: 出典: 手芸店で流通している接着芯の主要規格(90cm幅・112cm幅)。
#: ここでは狭い方(90cm)で見積もる——広い方で見積もって足りないより、
#: 狭い方で見積もって余る方が、失敗が軽い。
INTERFACING_WIDTH_CM = 90.0

#: 地直し(水通し)で縮む量の目安(%)。綿・麻の場合。
#: 出典: うさこの洋裁工房「布のゆがみを取ろう！ 地直し・水通し」
#: https://yousai.net/how_to/kiso/jinaosi
#: 「日本の検査基準では形状変化率1〜3%が許容値」「1mあたり1〜3cm縮む」。
#: 同記事は実例として1mが4.5cm縮んだ例も挙げているので、これは**目安の幅**
#: であって保証ではない。
COTTON_LINEN_SHRINK_MIN_PERCENT = 1.0
COTTON_LINEN_SHRINK_MAX_PERCENT = 3.0

#: 水通しが要らない素材。出典は上と同じ記事。
#: 「ポリエステルなどの化学繊維は水では縮まない」「絹やアセテートなどは
#:  水で光沢がなくなる」「ウールは水ではなく摩擦でちぢむ」。
NO_WATER_SHRINK_MATERIALS = ("ポリエステルなどの化学繊維", "絹・アセテート", "ウール")


@dataclass(frozen=True)
class WidthOption:
    """ある生地幅で作った場合の見積もり。"""
    width_cm: float
    used_length_cm: float
    buy_length_cm: int
    waste_ratio: float
    all_parts_fit: bool

    def as_dict(self) -> dict:
        return {"width_cm": self.width_cm,
                "used_length_cm": round(self.used_length_cm, 1),
                "buy_length_cm": self.buy_length_cm,
                "waste_ratio": round(self.waste_ratio, 4),
                "all_parts_fit": self.all_parts_fit}


@dataclass(frozen=True)
class FabricSuggestion:
    """どんな生地が向くか。出典付き。"""
    part_label: str
    text: str
    source_name: str
    source_url: str

    def as_dict(self) -> dict:
        return {"part_label": self.part_label, "text": self.text,
                "source_name": self.source_name, "source_url": self.source_url}


@dataclass
class ShoppingList:
    """買い物メモ。"""
    widths: list[WidthOption] = field(default_factory=list)
    recommended_width_cm: float | None = None
    interfacing_length_cm: int = 0
    interfacing_width_cm: float = INTERFACING_WIDTH_CM
    shrink_buy_length_cm: tuple[int, int] | None = None
    pattern_repeat_extra_cm: int = 0
    suggestions: list[FabricSuggestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: round41: 裏地の生地幅ごとの必要量。裏地を付けない生成では空。
    #: 表地とは別の生地なので、`widths`に混ぜず別の表として出す。
    lining_widths: list[WidthOption] = field(default_factory=list)
    lining_recommended_width_cm: float | None = None
    #: round68: 前開きの「開き寸法」(cm)。前開きでない型紙では None。
    #:
    #: round67まで、縫う順番は「前開きファスナーを付ける」と言うのに、
    #: 買い物メモにファスナーが**一度も出てこなかった**。生地屋で
    #: このページを見ながら買う人は、生地と接着芯だけ買って帰ることになる。
    #: 値は型紙の中心前を実測したもの(`engine/pipeline.py`の
    #: `_front_opening_length_cm`)。
    front_opening_cm: float | None = None
    #: 開きの下端が何で閉じるか。"waist"(スカート・パンツとの縫い目) /
    #: "hem"(裾まで開く) / ""(前開きでない)。
    #: **どの種類のファスナーを買うかは決めない**——下まで開く必要が
    #: あるかは着方の設計であって、型紙から決まる事実ではない。
    #: ここで言うのは「型紙がどうなっているか」だけである。
    front_opening_bottom: str = ""

    def as_dict(self) -> dict:
        return {
            "widths": [w.as_dict() for w in self.widths],
            "recommended_width_cm": self.recommended_width_cm,
            "interfacing_length_cm": self.interfacing_length_cm,
            "interfacing_width_cm": self.interfacing_width_cm,
            "lining_widths": [w.as_dict() for w in self.lining_widths],
            "lining_recommended_width_cm": self.lining_recommended_width_cm,
            "shrink_buy_length_cm": list(self.shrink_buy_length_cm)
                                     if self.shrink_buy_length_cm else None,
            "pattern_repeat_extra_cm": self.pattern_repeat_extra_cm,
            "front_opening_cm": (round(self.front_opening_cm, 1)
                                  if self.front_opening_cm else None),
            "front_opening_bottom": self.front_opening_bottom,
            "suggestions": [s.as_dict() for s in self.suggestions],
            "notes": list(self.notes),
        }


def round_up_to_buy(length_cm: float) -> int:
    """切り売りの単位へ切り上げる。"""
    if length_cm <= 0:
        return 0
    units = int(length_cm // BUY_ROUND_UP_CM)
    if length_cm - units * BUY_ROUND_UP_CM > 1e-9:
        units += 1
    return units * BUY_ROUND_UP_CM


def yardage_options(parts: list, widths: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                     allow_rotation: bool = False,
                     one_way_fabric: bool = False) -> list[WidthOption]:
    """生地幅ごとに、実際にネスティングし直して必要丈を出す。

    表を引くのではなく**実際に並べ直して測る**。同じ型紙でも、幅が変われば
    詰め方が変わり、必要丈は単純な比例にならない(幅が1.4倍でも丈が1/1.4に
    なるとは限らない——パーツが横に2枚並ぶかどうかで段が変わる)。
    """
    options: list[WidthOption] = []
    for width in sorted(widths):
        result = nest_parts(parts, fabric_width_cm=width,
                             allow_rotation=allow_rotation,
                             one_way_fabric=one_way_fabric)
        options.append(WidthOption(
            width_cm=width,
            used_length_cm=result.used_length_cm,
            buy_length_cm=round_up_to_buy(result.used_length_cm),
            waste_ratio=result.waste_ratio,
            all_parts_fit=not result.unplaced,
        ))
    return options


def interfacing_length_cm(parts: list,
                           width_cm: float = INTERFACING_WIDTH_CM) -> int:
    """接着芯が要るパーツだけを芯地の幅に並べ直して、必要な長さを出す。

    面積から割り出すのではなく、表地と同じやり方で**実際に並べて測る**。
    面積÷幅では、細長いパーツが並ばない事情(衿やウエストバンドは長い)を
    取りこぼす。
    """
    interfaced = [p for p in parts if needs_interfacing(p.part_type)]
    if not interfaced:
        return 0
    result = nest_parts(interfaced, fabric_width_cm=width_cm, allow_rotation=False)
    if result.unplaced:
        # 芯地の幅に収まらないパーツがある。長さで見積もるより、
        # 収まらないことを呼び出し側へ伝えた方がよいので0を返さず、
        # 収まった分＋収まらないパーツの丈の合計を上限として返す。
        extra = sum(p.height_cm for p in result.unplaced)
        return round_up_to_buy(result.used_length_cm + extra)
    return round_up_to_buy(result.used_length_cm)


def buy_length_with_shrink(need_cm: float, shrink_percent: float) -> int:
    """縮む生地で、地直し後に`need_cm`残すために買う長さ。

    【よくある間違い】「3%縮むから3%足す」は正しくない。買った長さLは
    地直し後に L×(1−p) になるので、必要量Nを残すには **N ÷ (1−p)** 要る。
    Nに(1+p)を掛けるのとは、pが大きいほど差が開く
    (p=10%なら 1.10倍 と 1.111倍 で、2mに対して2cmの違い)。
    """
    if shrink_percent <= 0:
        return round_up_to_buy(need_cm)
    if shrink_percent >= 100:
        raise ValueError("縮率は100%未満で指定してください")
    return round_up_to_buy(need_cm / (1.0 - shrink_percent / 100.0))


def layout_row_count(result) -> int:
    """配置結果が縦に何段になっているかを数える。

    y方向に重なりのあるパーツを1つの段としてまとめる。柄合わせの上乗せ量を
    見積もるのに要る(下の`pattern_repeat_extra_cm`参照)。
    """
    # bboxは (min_x, min_y, max_x, max_y)。段の判定に使うのはyだけ。
    spans = sorted((p.bbox()[1], p.bbox()[3]) if callable(p.bbox)
                    else (p.bbox[1], p.bbox[3]) for p in result.placed)
    if not spans:
        return 0
    rows = 1
    current_end = spans[0][1]
    for start, end in spans[1:]:
        if start >= current_end - 1e-9:      # 前の段と重なっていない = 次の段
            rows += 1
            current_end = end
        else:
            current_end = max(current_end, end)
    return rows


def pattern_repeat_extra_cm(row_count: int, repeat_cm: float) -> int:
    """柄合わせのために余分に要る丈の**上限**。

    【この数字の出どころ】柄が縦にリピート幅Rで繰り返す生地で、あるパーツを
    柄に合わせて置くには、そのパーツを最大Rだけ下へずらせばよい
    (Rずらせば柄は元と同じ見え方に戻るので、Rを超えてずらす意味は無い)。

    ここで数えるのは**パーツの枚数ではなく段の数**である。横に並んだパーツは
    同じ縦の帯を占めるので、その帯全体をRずらせば帯の中のパーツはすべて
    収まる——枚数で数えると、同じ段のぶんを何重にも数えてしまう。
    段がm段あれば、余分に要るのは最大 R×m。

    これは幾何から出る**上限**であって、実際にはもっと少なく済むことが多い
    (たまたま柄が合っている段は、ずらす必要が無い)。
    当てずっぽうではないが、**保証された必要量でもない**ので上限として示す。

    手芸店の目安とも突き合わせておく。クラフトハートトーカイは
    「柄が大きい場合や柄合わせが必要な場合は、通常より2〜3割
    (柄の一送り分)多く用意する」としている。
    https://www.crafthearttokai.jp/handmade_info/faq_cloth5/
    上の上限が必要量の2〜3割から大きく外れる場合は、呼び出し側が
    そのことも伝える(`build_shopping_list`参照)。
    """
    if repeat_cm <= 0 or row_count <= 0:
        return 0
    return round_up_to_buy(repeat_cm * row_count)


# --- 素材の提案 ---------------------------------------------------------------
#
# 出典のあるものだけを載せる。当たった資料に記述が見つからなかった形については
# **何も言わない**。それらしいことを書けば、根拠のない助言が型紙に載る。

_NUNOCOTO_SKIRT = ("nunocoto fabric「スカート（大人服）作りにおすすめの生地と型紙」",
                    "https://book.nunocoto-fabric.com/35327")
_NUNOCOTO_PANTS = ("nunocoto fabric「パンツ（大人服）作りにおすすめの生地」",
                    "https://book.nunocoto-fabric.com/35453")
_NUNOCOTO_SHIRT = ("nunocoto fabric「色々な種類のシャツ/ブラウス/チュニックにおすすめの生地」",
                    "https://book.nunocoto-fabric.com/14691")
_YOUSAI_FABRIC = ("うさこの洋裁工房「プロの洋裁の先生が教える生地の選び方」",
                   "https://yousai.net/how_to/kijinoerabikata")

#: (part_type, variation) -> (説明, 出典)
_SUGGESTIONS: dict[tuple[str, str], tuple[str, tuple[str, str]]] = {
    ("skirt", "circle"): (
        "ドレープ性が高くて軽い生地が向きます(ビエラ、サマーウール、サテン、"
        "シフォン、アムンゼン、クレープデシンなど)。張りのある生地だと、"
        "裾が広がりすぎます。", _NUNOCOTO_SKIRT),
    ("skirt", "flare"): (
        "ドレープ性が高くて軽い生地が向きます(ビエラ、サマーウール、サテン、"
        "シフォン、アムンゼン、クレープデシンなど)。", _NUNOCOTO_SKIRT),
    ("skirt", "pleated"): (
        "Aラインに広げたいなら張りのあるしっかりした生地(オックス、"
        "タイプライター、チノクロス、デニムなど)、Iラインに落としたいなら"
        "柔らかく薄い生地が向きます。", _NUNOCOTO_SKIRT),
    ("skirt", "wrap"): (
        "張りのある生地が向きます(タイプライター、ヘリンボーン、ツイード、"
        "ベロア、ダンボールニットなど)。", _NUNOCOTO_SKIRT),
    ("skirt", "tight"): (
        "しわになりにくいポリエステルツイルなどが向きます。ただし湿気を"
        "吸わないので熱がこもりやすく、裏地を付けると着心地がよくなります。",
        _YOUSAI_FABRIC),
    ("pants", "wide"): (
        "軽くてドレープ性のある生地が向きます(リネンツイル・リネンサージ、"
        "ビエラ、チノクロス、アムンゼン、クレープデシンなど)。", _NUNOCOTO_PANTS),
    ("pants", "tapered"): (
        "張りのある生地や光沢のある生地が向きます(ブロード、タイプライター、"
        "チノクロス、サマーウール、ツイード、ベロアなど)。", _NUNOCOTO_PANTS),
    ("sleeve", "puff"): (
        "袖にボリュームを出すので、張りのある生地が向きます。", _NUNOCOTO_SHIRT),
    ("sleeve", "bell"): (
        "袖口が広がるので、柔らかい生地が向きます。", _NUNOCOTO_SHIRT),
    ("front_bodice", "*"): (
        "身頃は、綿ブロード・綿サテン・T/Cブロードなどが扱いやすい生地です"
        "(綿サテンは柔らかくさらさらしていますが、しわになりやすい)。",
        _YOUSAI_FABRIC),
}

#: パンツの種類のうち、当たった資料に直接の記述が無かったもの。
#: 黙って何も出さないと「調べていない」のか「向く生地が無い」のか
#: 分からないので、呼び出し側が一言添えるために持っておく。
_NO_SOURCE_FOUND = {
    ("skirt", "mermaid"), ("pants", "cropped"), ("pants", "shorts"),
    ("pants", "flare"),
}

#: パンツのpart_typeは前後で分かれているので、提案を引くときは1つにまとめる。
_PANTS_TYPES = {"front_pants", "back_pants"}


def fabric_suggestions(parts: list) -> tuple[list[FabricSuggestion], list[str]]:
    """このパーツ構成に向く生地を、出典付きで返す。

    Returns:
        (提案の一覧, 資料が見つからなかった形についての注記)
    """
    from .part_names import part_type_label, style_label

    seen: set[tuple[str, str]] = set()
    out: list[FabricSuggestion] = []
    missing: list[str] = []
    for part in parts:
        part_type = "pants" if part.part_type in _PANTS_TYPES else part.part_type
        variation = getattr(part, "variation", "") or ""
        key = (part_type, variation)
        if key in seen:
            continue
        seen.add(key)

        entry = _SUGGESTIONS.get(key) or _SUGGESTIONS.get((part_type, "*"))
        if entry:
            text, (source_name, source_url) = entry
            label = part_type_label(part.part_type)
            if variation:
                label = f"{label}（{style_label(variation)}）"
            out.append(FabricSuggestion(label, text, source_name, source_url))
        elif key in _NO_SOURCE_FOUND:
            label = part_type_label(part.part_type)
            if variation:
                label = f"{label}（{style_label(variation)}）"
            missing.append(label)

    notes: list[str] = []
    if missing:
        notes.append(
            "・".join(dict.fromkeys(missing))
            + "については、当たった資料に向く生地の記述が見つかりませんでした。"
            "分からないので何も書きません(似た形の記述から推測すると、"
            "根拠のない助言になります)。")
    return out, notes


#: 柄合わせの上乗せが、必要量のこの割合を超えたら「手芸店の目安より多い」と
#: 一言添える。出典(クラフトハートトーカイ)の「2〜3割」の上側を採る。
PATTERN_EXTRA_RULE_OF_THUMB_MAX = 0.30


#: round68: ファスナーの「長さ」の定義。出典のある事実だけを書く。
#:
#: YKK(ファスナーのメーカー)の説明では、閉じた状態で
#: 「スライダー頭端より下止先端まで」が製品の長さである。
#: 出典: YKK㈱ ジャパンカンパニー「ファスナーの寸法」
#: https://lyncs.ykkfastening.com/shop/pages/about_products_05.aspx
ZIP_LENGTH_SOURCE_NAME = "YKK㈱ ジャパンカンパニー「ファスナーの寸法」"
ZIP_LENGTH_SOURCE_URL = (
    "https://lyncs.ykkfastening.com/shop/pages/about_products_05.aspx")

#: 買ったファスナーが長いときの詰め方。
#: 出典: うさこの洋裁工房「ファスナーのサイズ変更の仕方」
#: https://yousai.net/how_to/bubunnui/kobetu/fastener
#: (「オープンファスナーや金属ファスナーはサイズ変更は下側でのサイズ変更が
#:   しにくいので、上側を調節してください」)
ZIP_SHORTEN_SOURCE_NAME = "うさこの洋裁工房「ファスナーのサイズ変更の仕方」"
ZIP_SHORTEN_SOURCE_URL = "https://yousai.net/how_to/bubunnui/kobetu/fastener"


def front_opening_note(front_opening_cm: float, bottom: str) -> str:
    """前開きのファスナーについての注記(round68)。

    **どの長さの製品を買えというところまでは言わない。** 市販の長さの
    刻みに出典が見つからなかったので、「開き寸法以上を選ぶ」という
    選び方だけを書く(短くはできるので、長い側は詰めれば足りる)。

    種類(下まで開くオープンファスナーかどうか)も決めない。型紙から
    決まるのは「開きの下端が何で閉じるか」までで、着方の設計は
    利用者のものである。
    """
    bottom_phrase = {
        "waist": "開きの下端は、スカート・パンツとの縫い目で閉じます。",
        "hem": "開きの下端は裾で、そこまで開きます。",
    }.get(bottom, "")
    # round61の教訓: 同じ数字を2か所に違う丸めで書かない。画面・PDF・
    # この文のどれもが、`front_opening_cm`を小数第1位まで同じに出す。
    return (
        f"前開きファスナーが要ります。型紙の中心前を測った開き寸法は"
        f"{front_opening_cm:.1f}cmです。{bottom_phrase}"
        "市販のファスナーの「長さ」は、閉じた状態でスライダーの頭から"
        f"下止めの先までを指します(出典: {ZIP_LENGTH_SOURCE_NAME} "
        f"{ZIP_LENGTH_SOURCE_URL} )。"
        "長いものは詰められますが短いものは伸ばせないので、"
        f"{front_opening_cm:.1f}cm以上のものを選んでください。"
        "詰めるときは上側で詰めます"
        "(オープンファスナーや金属ファスナーは下側で詰めにくいためです。"
        f"出典: {ZIP_SHORTEN_SOURCE_NAME} {ZIP_SHORTEN_SOURCE_URL} )。"
    )


def build_shopping_list(parts: list, *, widths: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                         allow_rotation: bool = False,
                         one_way_fabric: bool = False,
                         shrink_percent: float | None = None,
                         pattern_repeat_cm: float | None = None,
                         lining_parts: list | None = None,
                         front_opening_cm: float | None = None,
                         front_opening_bottom: str = "") -> ShoppingList:
    """買い物メモを組み立てる。

    Args:
        shrink_percent: 生地の収縮率(%)。生地のタグに書いてあればその値。
            Noneなら、綿・麻の目安(1〜3%)の幅で示す。
        pattern_repeat_cm: 柄の縦のリピート幅(cm)。柄合わせをする場合のみ。
        lining_parts: 裏地のパーツ一式(round41、engine/lining.py)。渡された
            場合だけ、裏地の必要量を**別の生地として**並べ直して出す。
            表地のパーツと同じ表に混ぜてはいけない——別の生地なので、
            合計しても買う単位にならない。
        front_opening_cm: 前開きの開き寸法(cm、round68)。前開きの型紙の
            ときだけ渡す。ここは測らない——測るのは型紙を持っている
            `engine/pipeline.py`側(`_front_opening_length_cm`)。
        front_opening_bottom: 開きの下端("waist" / "hem")。
    """
    options = yardage_options(parts, widths, allow_rotation=allow_rotation,
                               one_way_fabric=one_way_fabric)
    usable = [o for o in options if o.all_parts_fit] or options
    # 「おすすめ」は、全パーツが収まる中でいちばん短く買える幅。
    # 布ロス率ではなく**買う長さ**で選ぶ——買い物メモなので、
    # 利用者が払うのは長さであって、ロス率ではない。
    recommended = min(usable, key=lambda o: (o.buy_length_cm, o.width_cm))

    memo = ShoppingList(
        widths=options,
        recommended_width_cm=recommended.width_cm,
        interfacing_length_cm=interfacing_length_cm(parts),
        front_opening_cm=front_opening_cm,
        front_opening_bottom=front_opening_bottom if front_opening_cm else "",
    )
    if front_opening_cm:
        memo.notes.append(front_opening_note(front_opening_cm,
                                              memo.front_opening_bottom))

    need = recommended.used_length_cm
    if shrink_percent is not None and shrink_percent > 0:
        buy = buy_length_with_shrink(need, shrink_percent)
        memo.shrink_buy_length_cm = (buy, buy)
        memo.notes.append(
            f"収縮率{shrink_percent:g}%で地直しすると、買った長さは"
            f"{100 - shrink_percent:g}%になります。裁つのに{need:.0f}cm要るので、"
            f"買うのは{buy}cmです(必要量に{shrink_percent:g}%足すのではなく、"
            f"{100 - shrink_percent:g}%で割った値です)。")
    elif shrink_percent is None:
        lo = buy_length_with_shrink(need, COTTON_LINEN_SHRINK_MIN_PERCENT)
        hi = buy_length_with_shrink(need, COTTON_LINEN_SHRINK_MAX_PERCENT)
        memo.shrink_buy_length_cm = (lo, hi)
        # 1%と3%が同じ切り上げ単位に収まることがある。そのときに
        # 「210〜210cm」と書くと、幅があるように読めて紛らわしい。
        amount = f"{lo}cm" if lo == hi else f"{lo}〜{hi}cm"
        memo.notes.append(
            f"綿・麻は地直し(水通し)で縮みます。日本の検査基準では"
            f"形状変化率{COTTON_LINEN_SHRINK_MIN_PERCENT:g}〜"
            f"{COTTON_LINEN_SHRINK_MAX_PERCENT:g}%が許容値で、"
            f"その範囲なら買うのは{amount}です"
            # round61: ここも「1%」「3%」を手書きしていた。すぐ上の文は
            # 定数から出しているので、許容値を変えるとこの括弧だけが
            # 古い数字を言い続ける。同じ定数から出す。
            + (f"(この型紙では{COTTON_LINEN_SHRINK_MIN_PERCENT:g}%でも"
               f"{COTTON_LINEN_SHRINK_MAX_PERCENT:g}%でも"
               "同じ切り売り単位に収まります)。"
               if lo == hi else "。")
            + f"生地のタグに収縮率が書いてあれば、その値で計算し直せます。"
            f"化学繊維・絹・ウールは水通しが要らないので、"
            f"{recommended.buy_length_cm}cmのままで足ります。")

    if pattern_repeat_cm and pattern_repeat_cm > 0:
        rows = layout_row_count(nest_parts(
            parts, fabric_width_cm=recommended.width_cm,
            allow_rotation=allow_rotation, one_way_fabric=one_way_fabric))
        extra = pattern_repeat_extra_cm(rows, pattern_repeat_cm)
        memo.pattern_repeat_extra_cm = extra
        ratio = extra / need if need > 0 else 0.0
        note = (f"柄合わせをする場合、配置は縦{rows}段なので、"
                f"各段を最大{pattern_repeat_cm:g}cmずらすことになり、"
                f"余分に要るのは最大{extra}cmです(これは上限で、"
                f"実際にはもっと少なく済むことが多い)。")
        if ratio > PATTERN_EXTRA_RULE_OF_THUMB_MAX:
            note += (f"必要量の{ratio:.0%}にあたり、手芸店でよく言われる"
                     f"「2〜3割多め」より大きい値です。柄が大きい型紙なので、"
                     f"店で相談することをおすすめします。")
        memo.notes.append(note)

    if one_way_fabric:
        memo.notes.append(
            "一方方向の生地(起毛・別珍・コーデュロイ・片方向プリント)として"
            "配置しました。全パーツの上下の向きを揃えてあるので、"
            "毛の向きや柄の向きが途中で逆になりません。")

    if lining_parts:
        # 裏地は表地と同じ幅の候補で並べ直す。裏地は「一方方向」ではないが、
        # 回転の可否は表地と揃える——別々にすると、同じ型紙なのに表と裏で
        # 布目の向きが違う、という説明できない状態になる。
        lining_options = yardage_options(lining_parts, widths,
                                          allow_rotation=allow_rotation,
                                          one_way_fabric=one_way_fabric)
        memo.lining_widths = lining_options
        lining_usable = [o for o in lining_options if o.all_parts_fit] or lining_options
        lining_recommended = min(lining_usable,
                                  key=lambda o: (o.buy_length_cm, o.width_cm))
        memo.lining_recommended_width_cm = lining_recommended.width_cm
        memo.notes.append(
            f"裏地は表地とは別の生地です。幅{lining_recommended.width_cm:g}cmなら"
            f"{lining_recommended.buy_length_cm}cm買えば足ります"
            f"(実際に並べ直した実測。表地の必要量とは足し合わせないでください)。")

    suggestions, notes = fabric_suggestions(parts)
    memo.suggestions = suggestions
    memo.notes.extend(notes)
    return memo
