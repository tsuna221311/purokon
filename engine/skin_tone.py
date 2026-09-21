"""skin_tone.py — イラストの「肌の色」と「服の色」を見分ける(round72で追加)。

【round71までの問題】
イラストモードが絵から読んでいたのは**シルエット(白黒の形)だけ**だった。
人物が着ている絵では、素肌の腕も袖も同じ「黒い塊」として写るので、
`engine/illustration_fit.measure_sleeves` は最初の数行で

    if figure_detected:
        return SleeveReading()

と、**袖の読み取りを丸ごと諦めていた**。docstringにも
「人物が着ている絵では読まない」と書いてある。諦めた結果どうなるかは
書いていなかった——袖は常に採寸どおりの長袖になる。

実測(この検証のために描き起こした3着。詳しくはREADMEのround72):

    絵              出てきた袖              正しくは
    パフ袖          straight 36.1×56.0cm    短い袖
    長袖            straight 36.1×56.0cm    長袖(これだけ合っていた)
    **袖なし**      straight 36.1×56.0cm    **袖は要らない**

袖なしのドレスに、袖の型紙が2枚付いてくる。布も裁って、袖ぐりも
袖を付ける前提で引かれる。

【このモジュールがすること】
シルエットには写らないが、**絵には写っている**情報——色——を使う。
素肌と服は色が違うので、腕のどこまでが袖かが分かる。

    服の色 G … 胸のあたり(シルエット上端のすぐ下・左右の中央)の代表色。
                コスプレ衣装の絵で、ここが服でないことはまず無い。
    肌の色 S … 腕が胴から離れて見えている範囲の、**いちばん下**(手首・手)
                の代表色。立ち姿の絵で手が袖から出ていないことはまず無い。

    腕の塊の色を上から下へ辿り、G から S へ変わる行が袖の裾。
    肩のところで既に S なら袖なし。下まで G のままなら長袖。

【読まないと決める場合】
  * 腕が胴から離れて見えない(腕を組む、手を腰に当てる等)
  * G と S の隔たりが小さい(肌色の服、手袋、タイツ)
  * 左右で答えが食い違う(片腕が隠れている等)

いずれも**黙って当てずっぽうを返さず**、読めなかったことを呼び出し側へ
返す。呼び出し側はそれを利用者へ開示する。

【正直な限界】
- 手袋・アームカバーは「袖」と区別できない(色が服側なら袖として読む)。
- 肌の色が服の色に近い絵は読めない。これは検出できるので、諦める。
- 前後の区別はしない(1枚の絵からは後ろ姿の情報が無い)。
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover - numpy未導入環境向け
    _HAS_NUMPY = False

#: 輪郭線を避けて内側から色を拾うための食い込み量(px)。
#:
#: ラフイラストの輪郭線は3〜4pxある。塊の端ちょうどの色を拾うと、服でも
#: 肌でも**線の色**が返ってきて、両者が同じ色に見える(実測: 肌の代表色が
#: 線の色(43,36,48)になり、服との隔たりを測る意味が無くなった)。
COLOUR_INSET_PX = 7

#: 色を平均するときに、塊の内側から取る幅(px)。
COLOUR_SAMPLE_PX = 12

#: 腕が「胴から離れている」と認めるために、胴の幅が腕の幅の何倍必要か。
#:
#: 裾のスカラップ(波形の裾)も1行が3つ以上の塊に割れるが、どれも同じくらいの
#: 太さである。胴は腕よりはっきり太いので、これで分かれる。
TORSO_VS_ARM_MIN_RATIO = 2.0

#: 腕の帯をひとつながりと見なすときに許す途切れ(シルエットの高さに対する比)。
#:
#: パフ袖のように袖が胴と横にかぶる高さでは、腕と胴が一時的にくっついて
#: 塊が2つになる。実測で18行途切れた。ここで帯を切ると、その下の
#: 素肌の腕を見失う。
ARM_BAND_GAP_RATIO = 0.05

#: 腕の帯の下から何割を「手首・手」として肌の色に使うか。
SKIN_SAMPLE_BOTTOM_RATIO = 0.12

#: 服の色を拾う位置(シルエット上端からの比率)と、中央からの幅(絵の幅比)。
CHEST_BAND = (0.08, 0.16)
CHEST_HALF_WIDTH_RATIO = 0.05

#: 服と肌が「別の色だ」と言うために必要な隔たり。
#:
#: 距離は**redmean**——赤の量で重みを変える、人の目の感じ方に寄せた
#: RGBの距離——で測る。素のRGBの距離だと、淡い水色の身頃(232,236,248)と
#: 肌(246,217,196)の隔たりが57しかなく、はっきり違う色に見えるのに
#: 「近すぎる」と判定されてしまった(実測)。redmeanでは87になる。
#:
#: 実測(この検証の3着): 87 / 529 / 435。
#: 70は、実測でいちばん近かった組(87)を通し、かつ「同じ色の濃淡」を
#: 弾ける値として取った。
MIN_COLOUR_SEPARATION = 70.0

#: 色を拾える最小の塊の幅(px)。輪郭線を避けて内側を見るので、細い塊では
#: **線の色しか取れない**。実測で、パフ袖の上端の細い部分が線の色になり、
#: 肌と判定されていた(袖の裾を310行と読み違えた)。
MIN_SAMPLE_RUN_PX = COLOUR_INSET_PX * 2 + 4

#: 袖があると言うために、肩のあたりの**服の**張り出しが、脇の下の胴の
#: 半幅の何倍必要か。
#:
#: 袖は腕の上へ出るので、服の輪郭が胴より外へ出る。袖なしは肩で切れるので
#: 胴と同じ幅で終わる。実測: パフ袖2.07 / 長袖1.55 / 袖なし0.95。
SLEEVE_WIDTH_MIN_RATIO = 1.20

#: 肩のあたり(シルエット上端からの比率)。服の張り出しをここで測る。
SHOULDER_BAND_RATIO = 0.08

#: 「肌の色」と認める許容。服と肌の隔たりに対する比と、その上限。
#:
#: 【なぜ「服の色に近いか肌の色に近いか」で決めないか】服は1色とは限らない。
#: 実測(パフ袖の絵)では、身頃が淡い水色・スカートが青で、青いスカートは
#: **身頃の色より肌の色の方に近かった**(redmeanで351 対 378)。その結果、
#: スカートが肌と判定され、服の下端が裾(860行)ではなく身頃の下
#: (597行)になっていた。
#:
#: 肌は1色である。「肌の色にどれだけ近いか」だけで決めれば、服が何色
#: あっても関係しない。
SKIN_TOLERANCE_RATIO = 0.45
SKIN_TOLERANCE_MAX = 120.0

#: 袖の裾と認めるために、肌の色が何行続く必要があるか。
#: 1行だけの揺らぎ(髪・装飾・影)で袖が終わったことにしないための下限。
SKIN_RUN_MIN_ROWS = 12

#: 腕の行のうち服の色が占める割合が、これを下回れば「袖なし」。
SLEEVELESS_MAX_GARMENT_RATIO = 0.10

#: 肩の張り出しを「袖だ」と認めるために、その広さが何行で出ている必要があるか。
SLEEVE_SUPPORT_MIN_ROWS = 8

#: スカートの裾と認めるために、布の幅がある行が何行続く必要があるか。
GARMENT_BOTTOM_MIN_ROWS = 8

#: 裾と認めるために、その行の布の幅が「少し上の行」の何割必要か。
#: 波形の裾(スカラップ)の先端だけを裾としないための条件。
HEM_MIN_WIDTH_RATIO = 0.5

#: 左右の袖の裾がこれ以上食い違ったら、読み取らない(シルエットの高さ比)。
#: 片腕が体で隠れている絵などで、片側だけ別のものを拾うのを弾く。
SIDES_MAX_DISAGREEMENT_RATIO = 0.06


@dataclass(frozen=True)
class ColourReading:
    """絵の色から読んだこと。読めなかった項目はNone、理由は`reason`。"""

    garment_rgb: tuple[float, float, float] | None = None
    skin_rgb: tuple[float, float, float] | None = None
    separation: float = 0.0
    arm_top: int | None = None
    arm_bottom: int | None = None
    #: 袖の裾の行(左右の平均)。袖なし・長袖ではNone。
    sleeve_hem_y: int | None = None
    sleeveless: bool = False
    #: 袖が手首まである(＝長袖)。
    covers_wrist: bool = False
    #: 服の色が写っているいちばん下の行。スカートの裾にあたる。
    garment_bottom: int | None = None
    #: 読めなかった理由(空文字なら読めた)。
    reason: str = ""

    @property
    def usable(self) -> bool:
        return not self.reason and self.garment_rgb is not None


def _runs(row) -> list[tuple[int, int]]:
    """1行の中の、前景が続いている区間(始まり, 終わり)の並び。"""
    out: list[tuple[int, int]] = []
    start = None
    for x, value in enumerate(row):
        if value and start is None:
            start = x
        elif not value and start is not None:
            out.append((start, x - 1))
            start = None
    if start is not None:
        out.append((start, len(row) - 1))
    return out


def _dominant(colours):
    """代表色。16刻みに量子化して最も多い箱を選び、その中身の平均を返す。

    平均だけだと、服と肌が半々に入ったときに**どちらでもない色**になる。
    最頻の箱に絞ってから平均すれば、混ざらない。
    """
    if colours is None or len(colours) == 0:
        return None
    quantised = (colours // 16).astype(np.int64)
    key = quantised[:, 0] * 10000 + quantised[:, 1] * 100 + quantised[:, 2]
    values, counts = np.unique(key, return_counts=True)
    chosen = key == values[counts.argmax()]
    return tuple(float(v) for v in colours[chosen].mean(axis=0))


def _distance(a, b) -> float:
    """色の隔たり(redmean)。

    素のRGBの距離は、人の目の感じ方とかなり違う。redmeanは赤の量に
    応じて各成分の重みを変える近似で、係数以外の道具を足さずに
    そこそこ合う。実測で、淡い水色の身頃と肌の隔たりが
    57(素のRGB)→87(redmean)になり、正しく「別の色」と判定できた。
    """
    red_mean = (a[0] + b[0]) / 2.0
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return float(((2 + red_mean / 256.0) * dr * dr
                  + 4 * dg * dg
                  + (2 + (255 - red_mean) / 256.0) * db * db) ** 0.5)


def _sample(pixels, y: int, lo: int, hi: int):
    """塊(lo..hi)の内側から色を取る。輪郭線を避けるため両端を食い込ませる。"""
    a, b = lo + COLOUR_INSET_PX, lo + COLOUR_INSET_PX + COLOUR_SAMPLE_PX
    if b > hi - COLOUR_INSET_PX:
        a, b = lo, hi + 1
    if b <= a:
        a, b = lo, hi + 1
    return pixels[y, a:b]


def arm_band(mask) -> dict[int, tuple[tuple[int, int], tuple[int, int]]]:
    """左右に腕が分かれて見えている行と、その腕の塊を返す。

    条件は3つ:
      * 1行が3つ以上の塊に分かれていること(腕 | 胴 | 腕)
      * 真ん中の塊(胴)が左右の塊(腕)よりはっきり太いこと
        —— 裾のスカラップを腕と取り違えないため
      * **ひとつながりで、いちばん長く続く**帯であること
        —— 腕は肩から手首まで続く。離れたところに現れる3塊は腕ではない

    【「いちばん上から」ではなく「いちばん長く」にした理由】
    最初は上から順につながっている帯を採っていた。ところがアニメ風の絵は
    髪が跳ねる。左右に跳ねた毛先は、頭の高さで**3塊の行**を作る。実測
    (髪の跳ねた袖なしの絵): 3塊の行は191〜194行(毛先)と1305〜1356行
    (裾の波)だけが先に見つかり、腕の帯(336〜690行)は上の毛先から
    100行以上離れているために切り捨てられ、「腕が胴から離れて見えません」
    として色の読み取りごと落ちていた。毛先は数行しか続かないが腕は数百行
    続くので、**いちばん長い帯**を採れば腕が残る。
    """
    if not _HAS_NUMPY or mask is None:
        return {}
    rows: dict[int, tuple[tuple[int, int], tuple[int, int]]] = {}
    for y in range(mask.shape[0]):
        found = _runs(mask[y])
        if len(found) < 3:
            continue
        left, right = found[0], found[-1]
        torso = max(found[1:-1], key=lambda r: r[1] - r[0])
        arm_width = max(left[1] - left[0], right[1] - right[0]) + 1
        if (torso[1] - torso[0] + 1) < arm_width * TORSO_VS_ARM_MIN_RATIO:
            continue
        rows[y] = (left, right)
    if not rows:
        return {}
    filled = np.nonzero(mask.any(axis=1))[0]
    if filled.size == 0:
        return {}
    gap = max(12, int((int(filled[-1]) - int(filled[0]) + 1) * ARM_BAND_GAP_RATIO))
    keys = sorted(rows)
    blocks: list[list[int]] = [[keys[0]]]
    for y in keys[1:]:
        if y - blocks[-1][-1] > gap:
            blocks.append([y])
        else:
            blocks[-1].append(y)
    block = max(blocks, key=len)
    return {y: rows[y] for y in block}


def _cloth_runs(pixels, mask, y: int, skin, tolerance: float,
                 min_px: int) -> list[tuple[int, int]]:
    """その行で「布」と言える幅のある、肌でない区間を返す。

    【なぜ幅を要求するか】輪郭線は3〜4pxの濃い線で、肌の色からは遠い。
    幅を問わずに数えると、**素肌の腕の輪郭線まで「服」になる**。実測で、
    袖なしの絵の肩幅が、服の端(104px)ではなく腕の外側(156px)として
    測られ、袖ありと区別できなかった。脚の輪郭線も同じ理由で「服」に
    数えられ、スカートの裾が脚の先(1331行)になっていた。
    """
    line = mask[y]
    if not line.any():
        return []
    out: list[tuple[int, int]] = []
    start = None
    for x in range(mask.shape[1]):
        cloth = bool(line[x]) and _distance(
            (float(pixels[y, x, 0]), float(pixels[y, x, 1]),
             float(pixels[y, x, 2])), skin) > tolerance
        if cloth and start is None:
            start = x
        elif not cloth and start is not None:
            if x - start >= min_px:
                out.append((start, x - 1))
            start = None
    if start is not None and mask.shape[1] - start >= min_px:
        out.append((start, mask.shape[1] - 1))
    return out


def read_colours(image, mask) -> ColourReading:
    """絵の色から、服と肌を見分けて袖を読む。

    `image` は PIL の画像、`mask` は `silhouette_mask` が返すシルエット。
    2つの大きさが違う場合は、画像をマスクに合わせて縮める。
    """
    if not _HAS_NUMPY or mask is None or image is None:
        return ColourReading(reason="色を読める状態ではありません")
    solid = mask.astype(bool)
    rows = np.nonzero(solid.any(axis=1))[0]
    cols = np.nonzero(solid.any(axis=0))[0]
    if rows.size < 8 or cols.size < 8:
        return ColourReading(reason="シルエットが小さすぎます")
    top, bottom = int(rows[0]), int(rows[-1])
    left_x, right_x = int(cols[0]), int(cols[-1])

    # 頭が写っている絵では、**肩から下**だけを見る。
    #
    # 【実測】最初はシルエットの上端を肩として扱っていた。頭を描いた絵
    # (アニメ風のラフはほぼ全部そう)では、上端は髪のてっぺんになる。
    # 高さ1264pxの絵で、服の色を拾う帯(上端から8〜16%)は194〜295行——
    # 顔と髪で、服は1画素も入っていなかった。その「服の色」は肌に近いので
    # 「服と肌の色が近すぎて見分けられません」となり、**頭を描いただけで
    # 色の読み取りが丸ごと落ちていた**。顔を素肌と読んで頭の高さを袖の裾と
    # することもあった。肩から下を見れば、どちらも起きない。
    from .illustration_fit import shoulder_row
    shoulder = shoulder_row(solid)
    if shoulder is not None and bottom - shoulder >= 8:
        top = shoulder
    height = bottom - top + 1

    from PIL import Image as _Image
    resized = image.convert("RGB").resize((solid.shape[1], solid.shape[0]),
                                           _Image.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float64)

    # --- 服の色: 胸のあたり ---
    y0 = top + int(height * CHEST_BAND[0])
    y1 = max(y0 + 1, top + int(height * CHEST_BAND[1]))
    centre = (left_x + right_x) // 2
    half = max(4, int((right_x - left_x) * CHEST_HALF_WIDTH_RATIO))
    patch = pixels[y0:y1, max(0, centre - half):centre + half]
    patch_mask = solid[y0:y1, max(0, centre - half):centre + half]
    garment = _dominant(patch[patch_mask]) if patch_mask.any() else None
    if garment is None:
        return ColourReading(reason="服の色を拾えませんでした")

    # --- 肌の色: 腕のいちばん下 ---
    arms = arm_band(solid)
    if len(arms) < SKIN_RUN_MIN_ROWS:
        return ColourReading(garment_rgb=garment,
                             reason="腕が胴から離れて見えません")
    keys = sorted(arms)
    lowest = keys[int(len(keys) * (1.0 - SKIN_SAMPLE_BOTTOM_RATIO)):]
    samples = []
    for y in lowest:
        (la, lb), (ra, rb) = arms[y]
        samples.append(_sample(pixels, y, la, lb))
        samples.append(_sample(pixels, y, ra, rb))
    samples = [s for s in samples if len(s)]
    skin = _dominant(np.concatenate(samples)) if samples else None
    if skin is None:
        return ColourReading(garment_rgb=garment,
                             reason="肌の色を拾えませんでした")

    separation = _distance(garment, skin)
    if separation < MIN_COLOUR_SEPARATION:
        return ColourReading(garment_rgb=garment, skin_rgb=skin,
                             separation=separation,
                             arm_top=keys[0], arm_bottom=keys[-1],
                             reason="服と肌の色が近すぎて見分けられません")

    tolerance = min(separation * SKIN_TOLERANCE_RATIO, SKIN_TOLERANCE_MAX)

    # --- 外側の輪郭を、肩から腕の下まで辿る ---
    #
    # 腕が胴から離れて見えている行では**腕の塊**を、まだくっついている行
    # (パフ袖のように袖が胴と横にかぶる高さ)では**いちばん外の塊**を見る。
    # 外側だけを見るので、内側のスカートや小物に引きずられない。
    sides: dict[str, list[str]] = {"left": [], "right": []}
    trace_rows = list(range(top, keys[-1] + 1))
    for y in trace_rows:
        found = _runs(solid[y])
        for index, name in ((0, "left"), (-1, "right")):
            if not found:
                sides[name].append(".")
                continue
            if y in arms:
                a, b = arms[y][0 if index == 0 else 1]
            else:
                a, b = found[index]
            if b - a + 1 < MIN_SAMPLE_RUN_PX:
                sides[name].append(".")     # 細すぎて線の色しか取れない
                continue
            strip = _sample(pixels, y, a, b)
            if not len(strip):
                sides[name].append(".")
                continue
            colour = tuple(float(v) for v in strip.mean(axis=0))
            sides[name].append("S" if _distance(colour, skin) <= tolerance else "G")

    hems: list[int] = []
    for name in ("left", "right"):
        text = "".join(sides[name])
        for i in range(len(text) - SKIN_RUN_MIN_ROWS + 1):
            if text[i:i + SKIN_RUN_MIN_ROWS] == "S" * SKIN_RUN_MIN_ROWS:
                hems.append(trace_rows[i])
                break

    # --- 袖があるか: 肩のあたりで、服が胴より外へ出ているか ---
    #
    # 袖は腕の上へかぶるので、服の輪郭が胴より外へ出る。袖なしは肩で
    # 切れるので胴と同じ幅で終わる。**色で見た服の輪郭**で測るのが肝心で、
    # シルエットの外端だと素肌の腕まで数えてしまう(実測: 袖なしの絵で
    # 比が1.44になり、袖ありと区別できなかった)。
    shoulder_rows = range(top, top + max(2, int(height * SHOULDER_BAND_RATIO)) + 1)
    centre = (left_x + right_x) / 2.0
    per_row: list[float] = []
    for y in shoulder_rows:
        widest = 0.0
        for a, b in _cloth_runs(pixels, solid, y, skin, tolerance,
                                 MIN_SAMPLE_RUN_PX):
            widest = max(widest, centre - a, b - centre)
        if widest > 0:
            per_row.append(widest)
    # いちばん広い行ではなく、**何行も続いて出ている広さ**を採る。
    #
    # 腕の付け根の丸みは、2行ほど輪郭線だけの太い塊になる。そこを最大値
    # として採ると、素肌の腕が袖に見える(実測: 袖なしの絵で肩の服の半幅が
    # 108pxのはずが145pxになり、比が1.02ではなく1.32になっていた)。
    per_row.sort(reverse=True)
    garment_half = (per_row[SLEEVE_SUPPORT_MIN_ROWS - 1]
                    if len(per_row) >= SLEEVE_SUPPORT_MIN_ROWS
                    else (min(per_row) if per_row else 0.0))
    armpit = _runs(solid[keys[0]])
    torso = (max(armpit[1:-1], key=lambda r: r[1] - r[0])
             if len(armpit) >= 3 else (armpit[0] if armpit else (0, 0)))
    torso_half = max(centre - torso[0], torso[1] - centre, 1.0)

    bottom_of_garment = _garment_bottom(pixels, solid, skin, tolerance)
    common = dict(garment_rgb=garment, skin_rgb=skin, separation=separation,
                  arm_top=keys[0], arm_bottom=keys[-1],
                  garment_bottom=bottom_of_garment)

    if garment_half < torso_half * SLEEVE_WIDTH_MIN_RATIO:
        return ColourReading(sleeveless=True, **common)
    if not hems:
        return ColourReading(covers_wrist=True, **common)
    if len(hems) == 2 and abs(hems[0] - hems[1]) > height * SIDES_MAX_DISAGREEMENT_RATIO:
        return ColourReading(reason="左右の袖の読み取りが食い違いました", **common)
    return ColourReading(sleeve_hem_y=int(round(sum(hems) / len(hems))), **common)


def _garment_bottom(pixels, mask, skin, tolerance: float) -> int | None:
    """服の色が写っている、いちばん下の行。

    スカートの裾にあたる。シルエットだけで裾を探すと、**腕が終わって幅が
    落ちる行**を裾と取り違えることがある(実測: 長袖の絵で、手首の行801を
    裾と判定し、本当の裾960を見失った。スカート丈が49cmのはずが26cmに
    なっていた)。服の色で見れば、腕とは無関係に決まる。
    """
    if not _HAS_NUMPY:
        return None
    rows = np.nonzero(mask.any(axis=1))[0]
    if rows.size == 0:
        return None
    #: 1行に服の色の画素がこれだけあれば「服が写っている」とみなす(絵の幅比)。
    need = max(MIN_SAMPLE_RUN_PX, int(mask.shape[1] * 0.02))
    top_row, bottom_row = int(rows[0]), int(rows[-1])
    step = max(4, int((bottom_row - top_row + 1) * 0.02))

    def cloth_width(y: int) -> int:
        if y < 0 or y >= mask.shape[0]:
            return 0
        return sum(b - a + 1
                   for a, b in _cloth_runs(pixels, mask, y, skin, tolerance, need))

    # 裾は「布が**それまでと同じくらいの幅で**終わっている行」である。
    #
    # 条件を2つ置く:
    #   * 何行も続いていること —— 脚の先の丸みは3行だけ輪郭線で太く写る。
    #     実測でそこをスカートの裾(1331行)と読んでいた。
    #   * すぐ上の行と同じくらいの幅があること —— 波形の裾(スカラップ)は
    #     先へ行くほど細くなる。いちばん下の1点を裾とすると、そこより上の
    #     細い行が「ウエストより細い」と数えられ、**くびれが見つからなく
    #     なる**(実測: 床までのドレスでスカート丈が読めなくなった)。
    streak = 0
    lowest: int | None = None
    for y in range(bottom_row, top_row - 1, -1):
        width = cloth_width(y)
        if width and width >= cloth_width(y - step) * HEM_MIN_WIDTH_RATIO:
            if streak == 0:
                lowest = y
            streak += 1
            if streak >= GARMENT_BOTTOM_MIN_ROWS:
                return lowest
        else:
            streak = 0
            lowest = None
    return None
