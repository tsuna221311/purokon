"""lining.py — 裏地の型紙を表地の型紙から引く。round41で追加。

【何をするモジュールか】
表地の確定パーツ(`FinalizedPart`)から、同じ**縫い線**を持つ裏地のパーツを
作る。表地と違うのは次の2点だけで、どちらも出典のある数字に限っている:

  1. 裾の縫い代を **2cm 減らす**
  2. 後ろ身頃だけ、背中心に **2cm 足して 1cm のきせ(タック)** をたたむ

【なぜ「縫い線は同じ」なのか — 正直な限界の記録】
資料はどれも「裏布には必ずゆとり分を入れて縫製します」(MAISON DE AS)と
書くが、**肩・袖ぐり・脇でそれぞれ何cm足すのかを数字で書いた資料は、
今回当たった範囲では見つからなかった**。見つからない数字を「たぶん0.3cm
くらい」で埋めれば、根拠のない寸法が型紙に載る。だからここでは足さない。
足す代わりに、資料が**数字で書いている**唯一のゆとり——背中心のきせ——
だけを入れ、肩・袖ぐり・脇のゆとりについては「このエンジンは入れていない」
と注記に明記する(`lining_notes`)。

【きせの根拠】
かたやまゆうこ「裏地付きコートの作り方」
https://ameblo.jp/katagami-sewing/entry-12345397762.html
  「1cmのきせ分、布の長さでいうと2cm、これが重要」
  「これが無いと、表身頃がつっぱります」
MAISON DE AS「裏地の付け方」 https://maisondeas.com/lining/
  「ウエストラインから上のきせ分は1cm位必要になる」
2つの資料が独立に「1cm」と書いているので、この数字は採る。
深さ1cmの折り山は布を2cm食う(折って戻すので1cmの倍)ため、型紙側では
背中心に2cmを足す。

なお両資料の「きせ」は**背中心に縫い目がある**型紙が前提で、左右の
後ろ身頃がそれぞれ1cmずつ余分を持って縫い合わされる。このエンジンの
後ろ身頃は左右つながった1枚で出る(`FinalizedPart.cut_on_fold`は常にFalse、
背中心に縫い目が無い)ので、同じ2cmを**背中心で切り開いて広げ**、深さ1cmの
片ひだとしてたたむ形にした。既製服の裏地が背中心にひだを持つのと同じ
処理で、たたんだあとの出来上がり幅は表地と一致する。

【裾の根拠】
うさこの洋裁工房「裏地付けの基本」 https://yousai.net/how_to/bubunnui/migoro/urajituke
  「表地の裾の縫い代-2ｃｍ分出来上がり線から短く切る」
  表4cm→裏2cm、表3cm→裏1cm、表2cm→裏は出来上がり線(=0cm)。
`lining_hem_allowance_cm`はこの3つの実例をそのまま再現する。

【採らなかった流儀】
かたやまゆうこの記事は「表身頃は4cm、裏身頃は0cm」とし、裏地の**出来上がり
線そのもの**を表地より2cm短くする。うさこは出来上がり線は同じで**縫い代**を
2cm減らす。仕上がりの見え方(裏地が2cm控えられる)は同じだが、型紙の丈が
違う。どちらが正しいというより流儀の違いなので、片方を黙って選ばず、
`lining_notes`に「この型紙はうさこ式で引いてある」と書いて残す。

【必要量の突き合わせ】
旭化成「裏地の付け方(必要量の目安)」
https://www.asahi-kasei.co.jp/fibers/lining/home/tukekata.html
の概算式を`reference_lining_length_cm`に持ち、ネスティングの実測値と
並べて出す(`yardage_reference_note`)。当初は round38 の「柄合わせの
上乗せ量」と同じく「目安から外れたら警告」にしていたが、実測すると
**ほぼ必ず外れる**(概算式は前後の身頃を縦に並べる前提、このエンジンは
横に並べる)ので、警告ではなく並記に変えた。詳しくはその関数のdocstring。
"""

from __future__ import annotations

from dataclasses import replace

from .seam import FinalizedPart, Point, finalize_from_stitch_line

#: 裏地の裾の縫い代を、表地より何cm減らすか。
#: 出典: うさこの洋裁工房「表地の裾の縫い代-2ｃｍ分出来上がり線から短く切る」
LINING_HEM_REDUCTION_CM = 2.0

#: 背中心のきせ(折り山)の深さ(cm)。出典はモジュールdocstring。
CB_PLEAT_DEPTH_CM = 1.0

#: きせのために型紙へ足す布の長さ(cm)。深さ1cmの折り山は布を2cm食う。
#: 出典: かたやまゆうこ「1cmのきせ分、布の長さでいうと2cm」。
CB_PLEAT_FABRIC_CM = CB_PLEAT_DEPTH_CM * 2.0

#: 裏地を付けるパーツ種。身頃・袖・スカート・パンツ。
#: 衿・カフス・ウエストバンドは「裏地を付ける」のではなく接着芯を貼って
#: 表布で二重にする部位なので、裏地の型紙は引かない(engine/cutting.pyの
#: `needs_interfacing`が芯地側で面倒を見ている)。
LINED_PART_TYPES = frozenset({
    "front_bodice", "back_bodice",
    "front_bodice_center", "front_bodice_side",
    "back_bodice_center", "back_bodice_side",
    "front_bodice_zip_panel",
    "sleeve",
    "skirt",
    "front_pants", "back_pants",
})

#: 背中心のきせを入れるパーツ種。資料の記述は「後ろ身頃の背中心」に限られる
#: ので、後ろ身頃だけに入れる(前身頃・袖・スカートには入れない)。
#: 背中心が輪郭の**内側**を通る左右一体のパーツに限る——
#: `back_bodice_side`は背中心を含まない脇側のパネルなので対象外。
CB_PLEAT_PART_TYPES = frozenset({"back_bodice", "back_bodice_center"})

#: 裏地パーツのラベルに付ける接尾辞。
LINING_LABEL = "裏"


def lining_hem_allowance_cm(outer_hem_cm: float) -> float:
    """表地の裾の縫い代から、裏地の裾の縫い代を求める。

    うさこの洋裁工房「表地の裾の縫い代-2ｃｍ」。同記事の実例:
    表4cm→裏2cm、表3cm→裏1cm、表2cm→裏0cm(出来上がり線で裁つ)。
    2cmを下回る表地では0cmで止める(負の縫い代は存在しない)。
    """
    return max(0.0, float(outer_hem_cm) - LINING_HEM_REDUCTION_CM)


def hem_reduction_cm(outer_hem_cm: float) -> float:
    """裏地の裾が、表地より**実際に**何cm短いか。

    規則は「表地の裾の縫い代-2cm」だが、負の縫い代は作れないので0で止まる。
    表地の裾が2cm未満のときは、減った量は2cmではない。
    """
    return float(outer_hem_cm) - lining_hem_allowance_cm(outer_hem_cm)


def hem_gap_phrase(outer_hem_cm: float) -> str:
    """「裏地の裾が表地より○cm短いこと」という言い回し(round61で追加)。

    縫う順番の最後(「裏地を身頃に合わせる」)が、型紙の持っている数字を
    数え上げるときに使う。**そこには2cmと手書きしてあった**——
    既定(裾1.0cm)では1.0cmしか引けないので、同じPDFの中で
    手順11(「表地より1cm短く」)と食い違っていた。

    引ける量が0のときは「短い」と言わない。0cm短い、は嘘ではないが、
    読んだ人は「何か引いてあるのか」と探すことになる。
    """
    removed = hem_reduction_cm(outer_hem_cm)
    if removed <= 1e-9:
        return ("型紙が持っている数字は"
                f"(表地の裾の縫い代が{float(outer_hem_cm):g}cmなので、"
                "裏地の裾は表地と同じです)、")
    return f"型紙が持っている数字は、裏地の裾が表地より{removed:g}cm短いことと、"


def hem_reduction_sentence(outer_hem_cm: float) -> str:
    """裏地の裾について、「実際にどうしたか」を述べる1文。

    【round49で見つけたこと】round46で`lining_notes`の「2cm減らしています」
    という決め打ちを実測値に直したが、**同じ主張がもう1か所**、
    縫う順番(engine/assembly.py の「裾を始末する」)にも手書きされていて、
    そちらは直っていなかった。既定(裾1.0cm)で、PDFに刷られる手順に

        「裏地の裾の縫い代は0cmで、**表地より2cm短く**裁ってあります」

    と出ていた——1.0から2.0は引けないので、実際は1cm短いだけである。
    同じ規則を2か所で手書きしていたのが原因なので、文そのものをここ1つに
    まとめ、両方から呼ぶようにした。
    """
    lining_hem = lining_hem_allowance_cm(outer_hem_cm)
    removed = hem_reduction_cm(outer_hem_cm)
    sentence = (f"裏地の裾の縫い代は{lining_hem:g}cmで、"
                f"表地より{removed:g}cm短く裁ってあります"
                "(うさこの洋裁工房「表地の裾の縫い代-2ｃｍ分出来上がり線から"
                "短く切る」)。")
    if removed < LINING_HEM_REDUCTION_CM - 1e-9:
        # round61: ここも「2cm」を手書きしていた。いまは定数と一致して
        # いるが、規則(`LINING_HEM_REDUCTION_CM`)を変えたらこの文だけが
        # 嘘になる——round46→49で起きたのと同じ形である。定数から出す。
        sentence += (f"表地の裾の縫い代が{float(outer_hem_cm):g}cmしかないため、"
                     f"規則どおりの{LINING_HEM_REDUCTION_CM:g}cmは引けていません"
                     f"(裏地の裾は{lining_hem:g}cm＝出来上がり線で裁つことに"
                     "なります)。")
    else:
        sentence += "そのぶん裏地が表から見えずに収まります。"
    return sentence


def _ring(points: list[Point]) -> list[Point]:
    """閉じた点列から、末尾の重複点を落とした環を返す。"""
    if len(points) > 1 and points[0] == points[-1]:
        return list(points[:-1])
    return list(points)


def _side(x: float, center_x: float) -> int:
    if x > center_x:
        return 1
    if x < center_x:
        return -1
    return 0


def spread_at_center(points: list[Point], center_x: float,
                     half_cm: float) -> list[Point]:
    """縦線 x=center_x で輪郭を切り開き、左右を`half_cm`ずつ離す。

    背中心にきせ分の布を足すための操作。輪郭が縦線をまたぐ辺は交点で分割し、
    左側は-half_cm、右側は+half_cm平行移動する。結果として輪郭の幅は
    `2*half_cm`広がり、切り口には縦線に沿った隙間ができる——その隙間が
    たたむひだの分量になる。

    輪郭が縦線と交わらない場合(パーツが片側に寄っている場合)は、
    そのまま全体を平行移動するだけになり、幅は広がらない。呼び出し側は
    `CB_PLEAT_PART_TYPES`で「背中心が輪郭の内側を通るパーツ」に限ることで
    この状態を避けている。
    """
    ring = _ring(points)
    n = len(ring)
    if n < 3 or half_cm <= 0:
        return list(points)
    sides = [_side(p[0], center_x) for p in ring]
    if all(s == 0 for s in sides):
        return list(points)

    def _neighbour(idx: int, step: int) -> int:
        """idxから step方向へ進んで、最初に見つかる 0でない側を返す。"""
        j = idx
        for _ in range(n):
            j = (j + step) % n
            if sides[j] != 0:
                return sides[j]
        return 0  # pragma: no cover - all-zeroは上で弾いてある

    out: list[Point] = []
    for i in range(n):
        p, q = ring[i], ring[(i + 1) % n]
        sp, sq = sides[i], sides[(i + 1) % n]
        if sp != 0:
            out.append((p[0] + half_cm * sp, p[1]))
        else:
            # 頂点がちょうど中心線の上にある場合。前後の辺がどちら側から
            # 来てどちら側へ抜けるかで、1点のままか2点に割れるかが決まる。
            prev_s = _neighbour(i, -1)
            next_s = _neighbour(i, +1)
            out.append((center_x + half_cm * prev_s, p[1]))
            if next_s != prev_s:
                out.append((center_x + half_cm * next_s, p[1]))
        if sp != 0 and sq != 0 and sp != sq:
            # 辺が中心線をまたぐ。交点で切って、両側へ離した2点を入れる。
            t = (center_x - p[0]) / (q[0] - p[0])
            y = p[1] + t * (q[1] - p[1])
            out.append((center_x + half_cm * sp, y))
            out.append((center_x + half_cm * sq, y))
    out.append(out[0])
    return out


def _shift_open(points: list[Point], center_x: float, half_cm: float) -> list[Point]:
    """内部線・基準線用の平行移動。輪郭と違い、線は切り開かず端点の側で寄せる。

    ダーツの線や BL/WL/HL の基準線は「どちら側の布に載っているか」が決まって
    いるので、線ごとに一方へ寄せる。中心線をまたぐ線(BL/WL/HL のように左右に
    渡る線)は、またぐ点で分割せずに**両端をそれぞれの側へ寄せる**——
    ひだをたたんだ状態ではこの線は元通り一直線につながる。
    """
    return [(p[0] + half_cm * (_side(p[0], center_x) or 1), p[1]) for p in points]


def _center_x(points: list[Point]) -> float:
    xs = [p[0] for p in points]
    return (min(xs) + max(xs)) / 2.0


def lining_part(outer: FinalizedPart, *,
                hem_seam_allowance_cm: float | None = None) -> FinalizedPart | None:
    """表地の確定パーツから、対応する裏地のパーツを1枚作る。

    裏地を付けないパーツ種(`LINED_PART_TYPES`にないもの)ではNoneを返す。

    hem_seam_allowance_cm: 表地の裾の縫い代。Noneなら表地が全辺一律
        (`outer.seam_allowance_cm`)だったとみなす。
    """
    if outer.part_type not in LINED_PART_TYPES:
        return None
    outer_hem = (outer.seam_allowance_cm if hem_seam_allowance_cm is None
                 else float(hem_seam_allowance_cm))
    lining_hem = lining_hem_allowance_cm(outer_hem)

    stitch = list(outer.stitch_line)
    internal = [list(line) for line in outer.internal_lines]
    reference = [(label, list(pts)) for label, pts in outer.reference_lines]
    # 合印は**表地とまったく同じ位置**でなければならない。裏地は表地と
    # 同じ縫い目を縫うので、合印がずれれば合わせる目印として役に立たない。
    #
    # `finalize_from_stitch_line`は合印を打ち直すが、`notch_points`
    # (engine/notches.pyが決めた「実際に縫い合わせる辺の上の座標」)を渡せない
    # 場合はパーツ種ごとの**周長比**へフォールバックする(round16の判断)。
    # 周長比で打ち直すと、表地が実座標で打った合印と別の場所に出る。
    # だから打ち直さず、表地の合印をそのまま引き継ぐ。
    notches = [(tuple(a), tuple(b)) for a, b in outer.notches]

    if outer.part_type in CB_PLEAT_PART_TYPES:
        cx = _center_x(stitch)
        half = CB_PLEAT_FABRIC_CM / 2.0
        stitch = spread_at_center(stitch, cx, half)
        internal = [_shift_open(line, cx, half) for line in internal]
        # 背中心を広げたパーツでは、合印も載っている側へ一緒に動く。
        notches = [tuple(_shift_open(list(seg), cx, half)) for seg in notches]
        moved: list[tuple[str, list[Point]]] = []
        for label, pts in reference:
            if label == "CB":
                # 背中心はもう1本の線ではなく、たたむひだの両端になる。
                # 線を2本に分けて、たたむ位置として残す。
                ys = [p[1] for p in pts]
                y0, y1 = min(ys), max(ys)
                for sign in (-1, 1):
                    moved.append(("きせ", [(cx + half * sign, y0),
                                            (cx + half * sign, y1)]))
            else:
                moved.append((label, _shift_open(pts, cx, half)))
        reference = moved

    part = finalize_from_stitch_line(
        outer.part_type, outer.variation, stitch,
        seam_allowance_cm=outer.seam_allowance_cm,
        hem_seam_allowance_cm=lining_hem,
        label_suffix=(f"{outer.label_suffix}{LINING_LABEL}"
                      if outer.label_suffix else LINING_LABEL),
        dart_count=outer.dart_count,
        seam_edge=outer.seam_edge,
        internal_lines=internal,
        reference_lines=reference,
    )
    return replace(part, notches=notches)


def build_lining_parts(parts: list[FinalizedPart], *,
                       hem_seam_allowance_cm: float | None = None
                       ) -> list[FinalizedPart]:
    """表地のパーツ一式から、裏地のパーツ一式を作る（順序は表地と同じ）。"""
    out: list[FinalizedPart] = []
    for part in parts:
        lining = lining_part(part, hem_seam_allowance_cm=hem_seam_allowance_cm)
        if lining is not None:
            out.append(replace(lining, cut_quantity=part.cut_quantity,
                                cut_on_fold=part.cut_on_fold))
    return out


# --- 必要量の突き合わせ(旭化成の概算式) ----------------------------------
_ASAHI_SOURCE = (
    "旭化成「裏地の付け方」"
    " https://www.asahi-kasei.co.jp/fibers/lining/home/tukekata.html")


def reference_lining_length_cm(kind: str, *, length_cm: float,
                               sleeve_cm: float = 0.0
                               ) -> tuple[int, int] | None:
    """旭化成が挙げている裏地の必要量の目安(cm)を(最小, 最大)で返す。

    式はいずれも同社ページの記載そのまま:
      スカート     … (スカート丈+10cm) × 2〜3 (幅が広い型は×3〜4)
      パンツ総裏   … (パンツ丈 × 2) + 10cm
      ジャケット総裏 … (着丈 × 2) + (袖丈 × 2) + 20cm

    同ページにはワンピース総裏の式
    「(スカートの使用量)+(背丈×2)+(袖丈×2)+20cm」もあるが、**背丈**は
    このエンジンが採寸項目として持っていない(`Measurements`にバスト・
    ウエスト・ヒップ・身長・袖丈・肩幅はあるが、背丈は無い)。身頃の
    パーツ丈で代用すると、それは着丈であって背丈ではないので、式の
    意味が変わる。当てられない式は当てない——ここには実装しない。

    知らない`kind`ではNoneを返す(でたらめな数字を返さない)。
    """
    length_cm = float(length_cm)
    if kind == "skirt":
        # 「×2〜3」と「×3〜4」の2通りが挙がっているので、下限2・上限4。
        return (int(round((length_cm + 10) * 2)), int(round((length_cm + 10) * 4)))
    if kind == "pants":
        value = int(round(length_cm * 2 + 10))
        return (value, value)
    if kind == "jacket":
        value = int(round(length_cm * 2 + float(sleeve_cm) * 2 + 20))
        return (value, value)
    return None


def lining_kind(parts: list[FinalizedPart]) -> str | None:
    """裏地パーツの構成から、旭化成の式のどれに当たるかを判定する。

    上下が組み合わさった構成(身頃+スカート、身頃+パンツ)はNoneを返す。
    ワンピースの式は背丈を要求し、この上下セットに当たる式は元の資料に
    無いので、当てはめる式が無い。
    """
    types = {p.part_type for p in parts}
    has_bodice = any(t.startswith(("front_bodice", "back_bodice")) for t in types)
    has_skirt = "skirt" in types
    has_pants = bool(types & {"front_pants", "back_pants"})
    if has_bodice and (has_skirt or has_pants):
        return None
    if has_bodice:
        return "jacket"
    if has_pants and not has_skirt:
        return "pants"
    if has_skirt and not has_pants:
        return "skirt"
    return None


def yardage_reference_note(parts: list[FinalizedPart], used_length_cm: float,
                            fabric_width_cm: float) -> str | None:
    """実測の必要丈に、外部の概算の目安を並べた注記を返す。

    【なぜ「警告」ではなく「並べるだけ」なのか — 実測の記録】
    最初はround38の柄合わせと同じく「目安から外れたら警告」にしていたが、
    実際に測ると**ほぼ必ず外れる**。身頃+袖(バスト84・着丈65.8・袖丈56.0)で
    旭化成式は264cm、このエンジンの実測は幅110cmで122.1cm——ちょうど半分
    である。理由もはっきりしていて、概算式は前身頃と後ろ身頃を生地の上で
    **縦に並べる**前提(着丈×2)だが、このエンジンは幅110cmに横2枚並べて
    いるからで、どちらも間違っていない。毎回鳴る警告は警告ではないので、
    「実測はこれ・目安はこれ・違う理由はこれ」を1文で並べるだけにした。

    ただし実測が目安を**上回った**場合だけは話が別で、そのときは
    「概算より多く要る型紙」なので、買う前に気づけるよう一言足す
    (バスト100のフレアスカート付きなど、パーツが横に並ばない構成で起こりうる)。
    """
    kind = lining_kind(parts)
    if kind is None or not parts:
        return None
    heights: dict[str, float] = {}
    for part in parts:
        heights[part.part_type] = max(heights.get(part.part_type, 0.0),
                                       part.height_cm)
    bodice_h = max((h for t, h in heights.items()
                    if t.startswith(("front_bodice", "back_bodice"))), default=0.0)
    lower_h = max((h for t, h in heights.items()
                   if t in ("skirt", "front_pants", "back_pants")), default=0.0)
    sleeve_h = heights.get("sleeve", 0.0)
    if kind == "jacket":
        rng = reference_lining_length_cm("jacket", length_cm=bodice_h,
                                          sleeve_cm=sleeve_h)
    else:
        rng = reference_lining_length_cm(kind, length_cm=lower_h)
    if rng is None:  # pragma: no cover - kindは上で絞ってある
        return None
    low, high = rng
    amount = f"{low}cm" if low == high else f"{low}〜{high}cm"
    note = (f"裏地の必要丈は、この型紙を幅{fabric_width_cm:g}cmに実際に並べた実測で"
            f"{used_length_cm:.0f}cmです。生地幅を見ない概算の目安では{amount}"
            f"({_ASAHI_SOURCE})。")
    if used_length_cm > high:
        note += ("実測の方が概算より長くなっています。"
                 "パーツが横に並ばない大きさなので、目安の数字で買うと足りません。"
                 "実測の方の数字で買ってください。")
    else:
        note += ("実測の方が短いのは、概算式が前身頃と後ろ身頃を縦に並べる"
                 "前提なのに対し、この型紙は横に並べているためです。"
                 "どちらかが間違いというわけではありません。")
    return note


def lining_notes(parts: list[FinalizedPart], outer_hem_cm: float) -> list[str]:
    """裏地の型紙に付ける注記。入れた数字とその出典、入れなかったものを書く。"""
    if not parts:
        return []
    lining_hem = lining_hem_allowance_cm(outer_hem_cm)
    # round46: ここは「2cm減らしています」と決め打ちで書いていたが、
    # 負の縫い代は存在しないので `lining_hem_allowance_cm` は0で止める。
    # 表地の裾が2cm未満だと、実際に減った量は2cmではない。
    # 既定の縫い代は全辺1.0cmなので、**何も指定しなければ必ずこの状態**に
    # なり、「表地の1.0cmから2cm減らしています」——1.0から2.0は引けない——
    # という、計算の合わない文が既定で出ていた(round46に実際に動かして発見)。
    # round49: 引き算そのものは `hem_reduction_cm` 1か所に置く。
    # round46でここだけ直したとき、同じ計算を手書きしていた
    # engine/assembly.py の「裾を始末する」が取り残され、PDFに刷られる
    # 手順では「表地より2cm短く」と嘘が残っていた。
    removed = hem_reduction_cm(outer_hem_cm)
    notes = [
        f"裏地の裾の縫い代は{lining_hem:.1f}cmです"
        f"(表地の{outer_hem_cm:.1f}cmから{removed:.1f}cm減らしています)。"
        "出典: うさこの洋裁工房「裏地付けの基本」"
        " https://yousai.net/how_to/bubunnui/migoro/urajituke "
        "「表地の裾の縫い代-2ｃｍ分出来上がり線から短く切る」。",
        "裏地の出来上がり線は表地と同じ寸法で引いてあります。"
        # ここに出てくる2cmは、**別の流儀がそう書いている**値であって、
        # この型紙の計算とは関係がない(tests/test_round61_one_source_of_truth
        # の`_HAND_WRITTEN_ON_PURPOSE`に理由を書いて登録してある)。
        "裏地の丈そのものを表地より2cm短くする流儀もありますが"
        "(かたやまゆうこ「表身頃は4cm、裏身頃は0cm」)、"
        "この型紙は「出来上がり線は同じ・縫い代だけ2cm減らす」うさこ式です。",
    ]
    if removed < LINING_HEM_REDUCTION_CM - 1e-9:
        # round46: 引き切れなかったことを、はっきり言う。
        # 「0.0cm」とだけ書かれても、それが出来上がり線で裁つという意味だとは
        # 読み取れないし、規則どおり2cm引けなかったことも分からない。
        notes.append(
            f"ただし表地の裾の縫い代が{outer_hem_cm:.1f}cmしかないため、"
            # round61: ここも「2cm」を手書きしていた(この規則を手書きした
            # 3か所目)。規則を変えると、この文だけが古い数字を言い続ける。
            f"規則どおりの{LINING_HEM_REDUCTION_CM:g}cmは引けず"
            f"{removed:.1f}cmしか減らしていません"
            f"（裏地の裾は{lining_hem:.1f}cm＝出来上がり線で裁つことになります）。"
            "出典の実例は表4cm→裏2cm、表3cm→裏1cm、表2cm→裏0cmで、"
            "裾の縫い代が2cm以上あることを前提にしています。"
            # 見出しの番号(⑧など)は入力モードで振り直されるので書かない
            # (round41で手順番号をDOM順に振り直すようにした。番号を文章に
            #  焼き付けると、モードによって指す先がずれる)。PDFに刷られる
            # 文でもあり、そこには番号が無い。
            "裾を折り返して始末するなら、「縫い代」の設定で裾だけ別に"
            "3〜4cm程度を指定してから引き直してください。")
    if any(p.part_type in CB_PLEAT_PART_TYPES for p in parts):
        notes.append(
            f"後ろ身頃の裏地は、背中心に{CB_PLEAT_FABRIC_CM:.0f}cm足してあります。"
            f"縫う前に深さ{CB_PLEAT_DEPTH_CM:.0f}cmのひだにたたむと、"
            "表地と同じ幅に戻ります(型紙の「きせ」の線どうしを合わせます)。"
            "出典: かたやまゆうこ「裏地付きコートの作り方」"
            " https://ameblo.jp/katagami-sewing/entry-12345397762.html "
            "「1cmのきせ分、布の長さでいうと2cm、これが重要」"
            "「これが無いと、表身頃がつっぱります」／"
            "MAISON DE AS「裏地の付け方」 https://maisondeas.com/lining/ "
            "「ウエストラインから上のきせ分は1cm位必要になる」。")
    notes.append(
        "肩・袖ぐり・脇のゆとりは足していません。"
        "「裏布には必ずゆとり分を入れて縫製します」と書く資料はありますが、"
        "各部位で何cm足すのかを数字で書いた資料が見つかりませんでした。"
        "見つからない数字を推測で埋めると、根拠のない寸法が型紙に載るので"
        "入れていません。")
    return notes
