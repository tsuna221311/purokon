"""panel_split.py — 生地幅に収まらないパーツを、縦に分割する。round35で追加。

【round34まで何が起きていたか】生地幅(最大150cm)に収まらないパーツは
`engine/nesting.py`が「配置できなかったもの(unplaced)」として脇へ置き、
型紙のSVG/PDFには**描かれない**。つまり出来上がる型紙から、そのパーツが
まるごと消える。

round11のテストには「実際に総当たりして確認したところ、現状のテンプレート・
倍率の範囲ではunplacedが発生するケースは存在しない(=製品としては到達不能)」
と書いてあったが、**それはもう本当ではない**。round9で追加した
サーキュラースカートは幅がヒップにほぼ比例して伸びるため、実測で

    ウエスト60〜150 x ヒップ70〜170 を10cm刻みで総当たりした110通りのうち
    **70通り**で、スカートが生地幅(150cm)に収まらず型紙から消えていた。
    消え始めるのは**ヒップ143cm**から(1cm刻みで二分探索して確認)。

つまり「ヒップが143cm以上の人がサーキュラースカートを選ぶと、
スカートの無いワンピースの型紙が出てくる」状態だった。

【なぜ「警告を出す」で終わりにしないか】この型紙には元々開示の仕組みが
あって、警告自体は出ていた(`_unplaced_warnings`)。だが利用者にできるのは
「別の形を選び直す」だけで、**選んだ形は作れないまま**である。実際の
洋裁では、大きなスカートは中心で縫い合わせる2枚以上に分けて裁つ——
サーキュラースカートは2枚接ぎ・4枚接ぎが普通の作り方で、1枚で裁つ方が
むしろ例外である。分けられるものは分ければ、そのまま作れる。

【何を分けて、何を分けないか】
分けてよいのは、**そこに縫い目が入っても仕立てとして成り立つ**パーツだけ。
スカートとパンツは中心に縫い目が入る型紙が普通にある。身頃は分けない
(切り替え線は`engine/princess.py`が別の考え方で扱う。ここで勝手に
中心に縫い目を入れると、前中心の見返し・ファスナー・柄合わせの前提が
壊れる)。衿・カフス・ウエストバンドのような帯も分けない(長さが命の
パーツで、継ぐと伸び止めの効きが変わる)。

分割線は**布目線に平行な縦線**にする。横に切ると、布目の向きが変わって
落ち感が左右で変わる。
"""

from __future__ import annotations

from .svgpath import bounding_box, segments_to_polyline

#: 縦に分けてよいパーツ種。理由はモジュールdocstring参照。
SPLITTABLE_PART_TYPES: frozenset[str] = frozenset({"skirt", "front_pants", "back_pants"})

#: 分割後の1枚が、これより細くなる分け方はしない(cm)。
#: 細長い布は裁つのも縫うのも難しく、縫い代のオフセットも不安定になる。
MIN_PANEL_WIDTH_CM = 12.0

#: 何枚まで分けるか。5枚以上に分かれるほど大きいパーツは、そもそも
#: この型紙が想定している作り方から外れているので、分けずに開示する。
MAX_PANELS = 4

#: 分割線の左右に足す縫い代。呼び出し側が渡す(既定は1cm)。
#: 分けた2枚は「縫い合わせて元の1枚になる」必要があるので、
#: 新しくできた縁のぶんだけ布が余分に要る。


def panels_needed(width_cm: float, max_fabric_width_cm: float,
                   seam_allowance_cm: float) -> int:
    """このパーツを何枚に分ければ生地幅に収まるかを返す。1なら分けなくてよい。

    分けると、内側にできる縫い目の数だけ縫い代が増える。n枚に分けると
    新しい縁は 2(n-1) 本できるので、必要な総幅は
    `width + 2(n-1) * 縫い代` になり、1枚あたりはそれを n で割った値。
    """
    if width_cm <= max_fabric_width_cm:
        return 1
    for n in range(2, MAX_PANELS + 1):
        per_panel = (width_cm + 2 * (n - 1) * seam_allowance_cm) / n
        if per_panel <= max_fabric_width_cm and per_panel >= MIN_PANEL_WIDTH_CM:
            return n
    return 1     # 分けても収まらない/細くなりすぎる。呼び出し側が開示する。


def _clip_x(points: list[tuple[float, float]], x_lo: float, x_hi: float
             ) -> list[tuple[float, float]] | None:
    """点列を x の帯 [x_lo, x_hi] で切り取る(Sutherland–Hodgman)。

    型紙の輪郭は凸とは限らないが、**縦の直線2本で切る**だけなので、
    切り口が2点より多くなる形(x方向に凹んだ輪郭)でなければ正しく閉じる。
    スカート・パンツの輪郭は左右の縁が単調なのでこれで足りる。
    """
    def _clip_half(poly, keep_left: bool, bound: float):
        out = []
        n = len(poly)
        for i in range(n):
            cur = poly[i]
            nxt = poly[(i + 1) % n]
            cur_in = (cur[0] <= bound) if keep_left else (cur[0] >= bound)
            nxt_in = (nxt[0] <= bound) if keep_left else (nxt[0] >= bound)
            if cur_in:
                out.append(cur)
            if cur_in != nxt_in:
                dx = nxt[0] - cur[0]
                if abs(dx) > 1e-12:
                    t = (bound - cur[0]) / dx
                    out.append((bound, cur[1] + t * (nxt[1] - cur[1])))
        return out

    poly = list(points)
    if poly and poly[0] == poly[-1]:
        poly = poly[:-1]
    poly = _clip_half(poly, True, x_hi)
    if len(poly) < 3:
        return None
    poly = _clip_half(poly, False, x_lo)
    if len(poly) < 3:
        return None
    # 同じ点が続くと、縫い代のオフセットが不安定になるので間引く。
    cleaned: list[tuple[float, float]] = []
    for p in poly:
        if not cleaned or abs(p[0] - cleaned[-1][0]) > 1e-9 or abs(p[1] - cleaned[-1][1]) > 1e-9:
            cleaned.append(p)
    return cleaned if len(cleaned) >= 3 else None


def split_into_panels(segments: list, panel_count: int) -> list[list] | None:
    """輪郭を、縦の線で`panel_count`枚に等分する。

    返すのは各パネルのセグメント列(左から順)。分けられない形なら None。
    """
    if panel_count < 2:
        return None
    min_x, _min_y, max_x, _max_y = bounding_box(segments)
    width = max_x - min_x
    if width <= 0:
        return None
    points = segments_to_polyline(segments, curve_steps=200)
    panels: list[list] = []
    for i in range(panel_count):
        lo = min_x + width * i / panel_count
        hi = min_x + width * (i + 1) / panel_count
        clipped = _clip_x(points, lo - 1e-6, hi + 1e-6)
        if clipped is None:
            return None
        segs = [("M", [clipped[0][0], clipped[0][1]])]
        for x, y in clipped[1:]:
            segs.append(("L", [x, y]))
        segs.append(("Z", []))
        panels.append(segs)
    return panels


#: 分けたときのラベル(左から順)。2枚なら「左」「右」、3枚以上は番号。
def panel_labels(panel_count: int) -> list[str]:
    if panel_count == 2:
        return ["左", "右"]
    return [f"{i + 1}枚目" for i in range(panel_count)]


def merge_part_labels(labels: list[str]) -> str:
    """同じ説明を共有するパーツ名を、1つの読みやすい表記にまとめる。

    【なぜ必要か】前身頃と後ろ身頃のように、同じ理由で同時に分かれる
    パーツは必ず対で出る。素直に1件ずつ書くと、100文字を超える同じ説明が
    画面に2回並ぶ(実際にブラウザで確認した)。読む側にとって2件目は
    情報量ゼロなので、共通の前置きをくくり出して1件にする。

        ["スカート（サーキュラー） 前", "スカート（サーキュラー） 後"]
        -> "スカート（サーキュラー） 前・後"
    """
    labels = [s for s in dict.fromkeys(labels)]     # 順序を保ったまま重複除去
    if len(labels) <= 1:
        return labels[0] if labels else ""
    # 全部に共通する先頭部分を探す(1文字ずつ。パーツ名は短いので十分)。
    prefix = labels[0]
    for other in labels[1:]:
        while prefix and not other.startswith(prefix):
            prefix = prefix[:-1]
    # 共通部分が短すぎる(=別物)なら、くくり出さずに素直に並べる。
    if len(prefix) < 2:
        return "・".join(labels)
    tails = [s[len(prefix):].strip() for s in labels]
    if not all(tails):        # 片方が他方の前置きそのもの。まとめると意味が変わる
        return "・".join(labels)
    return f"{prefix.rstrip()} " + "・".join(tails)


def split_note(part_labels: str | list[str], panel_count: int,
                seam_allowance_cm: float) -> str:
    """分けたことを利用者へ伝える文。"""
    label = (merge_part_labels(part_labels)
             if isinstance(part_labels, list) else part_labels)
    return (
        f"{label}は生地幅に収まらないため、{panel_count}枚に分けました。"
        f"縦の分割線どうしを縫い代{seam_allowance_cm:g}cmで縫い合わせると、"
        "元の1枚になります(大きなスカートを中心で接ぐのは、実際の洋裁でも"
        "普通の作り方です)。分割線は布目線に平行なので、落ち感は変わりません。"
    )
