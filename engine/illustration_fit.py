"""illustration_fit.py — 描かれた服の「丈」と「広がり」を測って型紙へ反映する
(round17で追加)。

【round16までの問題】
イラストモード(`PatternForgePipeline.generate_from_illustration`)は、
イラストを分割して各領域を判定し、`(part_type, variation)`——つまり
**60種のテンプレートのうちどれを使うか**——だけを決めていた。描かれた
丈・裾の広がり・袖の長さといった造形は、どこにも渡っていなかった。

実測(同じ採寸で、明らかに違う2着のラフを入力):

  入力                        出てきたスカート     出てきた袖
  短い・パフ袖・広がった裾     80.0 × 60.0 cm      31.7 × 52.0 cm
  長い・細袖・細い裾           80.0 × 60.0 cm      31.7 × 52.0 cm

**1mmも違わない。** 「イラストから型紙を起こす」と言いながら、実際には
採寸どおりの標準型紙が出ていただけだった。

【このモジュールがすること】
シルエットのマスクから**幅の分布**を測り、そこから design(デザイン)として
意味のある比率を取り出す。分割器の領域(`SegmentedRegion`)は外接矩形を
固定比率で切っただけで服の形を表さないので、マスクそのものを測る。

取り出すもの:
  waist_y        … 胴のいちばんくびれた位置(上半身と下半身の境目)
  skirt_ratio    … (くびれから裾までの高さ) ÷ (肩からくびれまでの高さ)
                    → 背丈(身長の約1/4)を基準にスカート丈をcmで決める
  hem_flare      … くびれより下の最大幅 ÷ くびれの幅
                    → タイト/フレア/サーキュラーのどれに近いかを決める
  sleeve_hem_row … 袖が水平に切れている行(round22)
                    → 袖の有無・袖丈・袖の形を決め、同時に「くびれを
                      測ってよい範囲」の下限にもなる

【袖(round22で対応。round17では一度断念していた)】
round17では「くびれより幅が広い行を袖とみなす」方法を試し、スカートも
同じ条件を満たすため長袖の絵でも短袖の絵でも比が0.99と1.00になって
区別できず、断念した。round22で**見る量を変えて**成立させた:
幅ではなく**外側の輪郭が1行で内側へ跳ぶ量**を見る。袖は先端が水平に
切れているので必ず跳び、ノースリーブの袖ぐりは滑らかな曲線なので跳ばない
(実測で34〜107px 対 1px)。詳しくは`sleeve_hem_row`のdocstring参照。

この「袖の裾の行」は、袖以外にも効く。この行より上ではシルエットの幅が
「胴 + 左右の袖」なので、**そこで胴のくびれを測ってはいけない**。
round21まではこれを見ておらず、長袖の絵でスカート丈と裾の広がりが
静かに壊れていた(丈比1.61→0.71、広がり2.49→1.68)。

比率だけを使うので、絵の解像度・トリミングに依存しない。cmへ直す基準は
背丈(首の付け根〜ウエスト、身長の約1/4)で、採寸から確定している値である。

【正直な限界】
- ここで測れるのは**シルエットの外形**だけである。ダーツ・切替線・前立て・
  ドレープといった内部の構造は、輪郭に現れないので読めない。
- 測れなかった項目はNoneを返し、呼び出し側は従来通り採寸から決める
  (黙って当てずっぽうの値を入れない)。
- 前後の区別はしない(1枚のイラストから読むので、後ろ姿の情報が無い)。
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover - numpy未導入環境向け
    _HAS_NUMPY = False

#: シルエットが画像の端に接しているかを見るときの、端とみなす幅(px)。
#: 1pxちょうどを要求すると、書き出し時のアンチエイリアスで外れる。
IMAGE_EDGE_TOLERANCE_PX = 2

#: 裾の広がり(=くびれより下の最大幅 ÷ ウエスト幅)として、服なら取りうる上限。
#:
#: テンプレートでいちばん広いサーキュラースカートが2.824倍、実測では
#: 床までのサーキュラードレスの絵が4.16倍だった。それを大きく超える値は、
#: 服ではないものを測っている。実測(公式の宣材ポスターをそのまま入力):
#: **599.00倍**。この値がそのまま「イラストから読み取った裾の広がり:
#: ウエスト幅の599.00倍」という注記になり、型紙が出ていた(round73)。
HEM_FLARE_MAX = 6.0

# スカート丈の比にも同じ上限を置こうとして、**やめた**。くびれを探す範囲が
# シルエットの25〜70%(`WAIST_SEARCH_BAND`)に限られているので、比は構造上
# 0.43〜3.00にしかならない。上限を置いても1度も効かない。
#: くびれを探すとき、「ウエストより下は細くならない」の判定から外す、
#: 裾のすぐ上の帯(服の範囲の高さに対する比)。
#: 波形の裾やスカラップで幅が細くなる分を無視するため(round72)。
HEM_IGNORE_RATIO = 0.03

#: くびれ(ウエスト)を探す縦方向の範囲。シルエットの上端からの比率。
#: 頭・首を含む絵でも胴のくびれがこの範囲に入るよう、広めに取る。
WAIST_SEARCH_BAND = (0.25, 0.70)

#: くびれと認めるのに必要な「前後の行との幅の差」の倍率。前後どちらから
#: 見てもこの倍率以上に太くなっていて初めて、くびれ(極小)とみなす。
WAIST_MIN_PROMINENCE = 1.06
#: 上の判定で上側を見る範囲。シルエットの高さに対する比率。
WAIST_MIN_PROMINENCE_SPAN = 0.06
#: 「くびれより下でこれ以上細くならない」判定の許容幅(px)。
#: 描線のアンチエイリアスで数px揺れるため、厳密な単調性は要求しない。
WAIST_BELOW_TOLERANCE_PX = 3

#: 測定値として採用する最小の画素数。これ未満の細いシルエットは
#: 比率の誤差が大きすぎるので測らない。
MIN_MEASURABLE_PX = 24

#: スカートのバリエーションごとの「広がり」= (パーツの最大幅 ÷ ウエスト幅)。
#: 生成済みのテンプレートから実測した値で、当てずっぽうの数値ではない
#: (tests/test_illustration_fit.py がテンプレートと一致することを検証する)。
#: pleated と flare が同じ値なのは、この2つがシルエットの幅としては同一で、
#: 裾のジグザグ(プリーツ表現)の有無だけが違うため(既存の設計)。
SKIRT_FLARE_BY_VARIATION: dict[str, float] = {
    "tight": 1.387,
    "wrap": 1.971,
    "pleated": 2.353,
    "flare": 2.353,
    "mermaid": 2.570,
    "circle": 2.824,
}

#: 背丈(首の付け根からウエストまで)が身長に占める割合。
#:
#: イラストで測れるのは「肩からくびれまで」と「くびれから裾まで」の**比**
#: なので、cmに直すには前者の実寸が要る。身頃テンプレートの丈(58cm)は
#: 首の付け根から**ヒップ**までの長さで、くびれまでの長さではない。
#: 当初これを基準にしてしまい、ミディ丈もロング丈もそろって上限の120cmへ
#: 張り付いた(実測)。背丈は身長のおよそ1/4で、身長158cmなら38.7cmとなり、
#: JIS成人女子M相当の背丈(約38cm)とよく一致する。
NAPE_TO_WAIST_RATIO = 0.245

#: スカート丈として型紙が成立する範囲(cm)。読み取り結果がここを外れる場合は
#: 絵の解釈を誤っている可能性が高いので端で止め、その旨を利用者へ開示する。
SKIRT_LENGTH_RANGE_CM = (20.0, 120.0)


@dataclass(frozen=True)
class DesignProportions:
    """イラストから読み取れた、デザイン上の比率。読めない項目はNone。

    round18で `image_count` / `skirt_ratio_samples` / `hem_flare_samples` を
    追加した。複数枚のイラストから読んだ場合、各項目は中央値で、
    samples には元になった枚数が入る。
    """
    skirt_ratio: float | None = None
    hem_flare: float | None = None
    image_count: int = 1
    skirt_ratio_samples: int = 0
    hem_flare_samples: int = 0
    #: round20: 人物が着ている絵と判断し、頭や脚を除いて測ったか。
    figure_detected: bool = False
    #: round22: 袖がウエストを覆っていて、胴のくびれが測れなかったか。
    waist_hidden_by_sleeve: bool = False
    #: round72: 人物の絵で、色から袖を読めなかった理由(読めたなら空文字)。
    sleeve_unreadable_reason: str = ""
    #: round73: 読み取れた値が服として成立しなかったときの、その値の説明。
    implausible_reason: str = ""

    def notes(self) -> list[str]:
        """利用者に開示する、読み取り結果の説明。"""
        out: list[str] = []
        if self.image_count > 1:
            out.append(f"イラスト{self.image_count}枚を読み取り、各項目の中央値を使いました。")
        if self.skirt_ratio is not None:
            source = (f"({self.skirt_ratio_samples}/{self.image_count}枚から)"
                      if self.image_count > 1 else "")
            out.append("イラストから読み取ったスカート丈の比: "
                       f"背丈(肩〜ウエスト)の{self.skirt_ratio:.2f}倍{source}")
        if self.hem_flare is not None:
            source = (f"({self.hem_flare_samples}/{self.image_count}枚から)"
                      if self.image_count > 1 else "")
            out.append("イラストから読み取った裾の広がり: "
                       f"ウエスト幅の{self.hem_flare:.2f}倍{source}")
        if self.figure_detected:
            out.append(
                "人物が着ているイラストと判断し、頭・脚を除いた「服の範囲」で"
                "測りました。襟ぐりの形はシルエットに現れないため読み取れません"
                "(服だけを写した画像を使うと襟ぐりも反映されます)。"
            )
        if self.sleeve_unreadable_reason:
            # round72: 読めなかったことを、**読めなかったと言う**。
            # round71まではここで黙って採寸どおりの袖にしていたので、
            # 袖なしの絵にも袖が2枚付いてきた。
            out.append(
                f"袖は絵から読み取れませんでした({self.sleeve_unreadable_reason})。"
                "袖の形と長さは採寸値から決めています——**絵が袖なしでも袖が"
                "付きます**ので、要らなければ手動モードで外してください。"
            )
        if self.implausible_reason:
            # round73: 服として成立しない値を、注記に書いて型紙にしていた。
            out.append(
                f"絵から丈・広がりを読み取れませんでした"
                f"({self.implausible_reason})。寸法は採寸値から決めています。"
                "**人物の全身が、周りに余白を残して1人だけ写っている画像**なら"
                "読み取れます(ロゴ・帯・タイトル文字が入っていると、それも"
                "服の一部として測ってしまいます)。"
            )
        if self.waist_hidden_by_sleeve:
            out.append(
                "長袖がウエストを覆っているため、胴のくびれがシルエットに現れず、"
                "スカート丈と裾の広がりは読み取れませんでした"
                "(袖の無い/短い絵、または袖を体から離した絵を1枚加えると読めます)。"
                "寸法は採寸値から決めています。"
            )
        elif (self.skirt_ratio is None and self.hem_flare is None
                and not self.implausible_reason):
            # round73: 理由が分かっているときは、そちらだけを出す。
            # 両方出すと「読み取れませんでした」が2行続いて、具体的な方が
            # 埋もれる。
            out.append(
                "イラストからは丈・広がりを読み取れませんでした"
                "(シルエットが小さすぎる、輪郭が背景と分離できない等)。"
                "寸法は採寸値のみから決めています。"
            )
        return out


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def combine_proportions(readings: list["DesignProportions"]) -> "DesignProportions":
    """複数枚のイラストから読んだ比率を1つにまとめる(round18で追加)。

    項目ごとに、読み取れた枚数だけを集めて**中央値**を取る。平均ではなく
    中央値なのは、1枚だけ大きく外れた読み取り(見切れている、別カット、
    小物だけのアップ等)に引きずられないようにするため。読み取れた枚数が
    0の項目はNoneのままで、呼び出し側は採寸から決める。

    どの項目が何枚から決まったかは`notes()`で利用者へ開示する。
    """
    if not readings:
        return DesignProportions(image_count=0)
    skirt = [r.skirt_ratio for r in readings if r.skirt_ratio is not None]
    flare = [r.hem_flare for r in readings if r.hem_flare is not None]
    return DesignProportions(
        skirt_ratio=_median(skirt) if skirt else None,
        hem_flare=_median(flare) if flare else None,
        image_count=len(readings),
        skirt_ratio_samples=len(skirt),
        hem_flare_samples=len(flare),
        figure_detected=any(r.figure_detected for r in readings),
        # 1枚でも読めていれば、そちらを使う(袖に隠されていた旨は出さない)。
        waist_hidden_by_sleeve=(not skirt and not flare
                                 and any(r.waist_hidden_by_sleeve for r in readings)),
        # round72: 1枚でも袖が読めていれば、読めなかった旨は出さない。
        sleeve_unreadable_reason=(
            ""
            if any(not r.sleeve_unreadable_reason and r.figure_detected
                   for r in readings)
            else next((r.sleeve_unreadable_reason for r in readings
                       if r.sleeve_unreadable_reason), "")),
        # round73: 1枚でも丈か広がりが読めていれば、そちらを使う。
        # どれも読めず、外れた値だけが出ていたときに理由を出す。
        implausible_reason=("" if (skirt or flare) else
                            next((r.implausible_reason for r in readings
                                  if r.implausible_reason), "")),
    )


def _column_widths(mask) -> list[int]:
    """各行(y)の前景の幅(px)。"""
    return [int(row.sum()) for row in mask]


def _row_runs(row) -> list[tuple[int, int]]:
    """1行の前景を、連続した区間(run)の列として返す。"""
    xs = np.where(row)[0]
    if xs.size == 0:
        return []
    runs = []
    start = int(xs[0])
    for a, b in zip(xs, xs[1:]):
        if b != a + 1:
            runs.append((start, int(a)))
            start = int(b)
    runs.append((start, int(xs[-1])))
    return runs


def _torso_widths(mask) -> list[int]:
    """各行の「胴の幅」(px)。腕や袖が体から離れて描かれている行では、
    左右の腕を除いた**真ん中の塊**の幅を返す(round22で追加)。

    【なぜ必要か】腕を下ろした人物のイラストでは、ウエストの高さの幅が
    「胴 + 左右の腕」になる。round20で人物込みの絵を読めるようにしたとき、
    裾の広がりが服だけの絵の2.48に対して2.12までしか戻らなかったのは
    これが理由で、「腕がウエストに重なるぶん甘く出る」として限界に
    記載していた。腕が体から離れて描かれている行では、前景が
    「腕 | 胴 | 腕」の3つの塊に分かれるので、真ん中を取れば胴の幅が
    そのまま得られる。round20のテスト図で実測すると、y=290の全幅115pxに
    対し真ん中の塊は83pxで、**服だけの絵の83pxとぴったり一致する**。

    塊がちょうど3つのときだけ真ん中を使う。1つ(腕が体に接している、
    普通の服だけの絵)や2つ(片腕だけ離れている、見切れている等)では
    どれが胴かを決められないので、従来どおり全幅を使う——推測で
    細い方を胴だと決めつけない。
    """
    out = []
    for row in mask:
        runs = _row_runs(row)
        if len(runs) == 3:
            out.append(runs[1][1] - runs[1][0] + 1)
        else:
            out.append(int(row.sum()))
    return out


def _measurable_rows(mask, hem_y: int | None) -> list[bool]:
    """その行の幅を「胴の幅」として信用してよいか(round23で追加)。

    信用してよいのは次のどちらか:
      * 袖/腕の先より下の行(そこにはもう袖が写っていない)
      * 袖/腕が体から離れて描かれている行(前景が「腕|胴|腕」の3つに
        分かれるので、真ん中を取れば胴の幅そのもの。`_torso_widths`)

    round22では「袖の先より下」だけを見ていた。そのため、袖が体から
    離れて描かれた長袖の絵——アニメのイラストでは普通にある——でも、
    ウエストが読めるのに読まずに諦めていた。離れていれば胴は見えている。

    この一手で、round22に「正直な限界」として書いた3つが同時に解けた:
      * 長袖の絵でスカート丈・裾の広がりが読めない
      * パフスリーブと7分袖を長袖と区別できない(袖丈がcmで測れないため)
      * 人物込みの絵で腕がウエストの幅に混ざる
    どれも「袖/腕に覆われた行を一律に捨てていた」ことが原因だった。
    """
    if not _HAS_NUMPY or mask is None:
        return []
    out = []
    for y, row in enumerate(mask):
        if hem_y is None or y > hem_y:
            out.append(True)
        else:
            out.append(len(_row_runs(row)) == 3)
    return out


def first_detached_arm_row(mask, top: int, bottom: int) -> int | None:
    """腕(または袖)が体から離れて描かれ始める行を返す(round22で追加)。

    前景が「腕 | 胴 | 腕」の3つの塊に分かれる最初の行である。この行より
    **上**では腕が体に接していて、幅から腕を分離できない。したがって
    そこで胴のくびれを測ってはいけない。

    【これを見ないと何が起きるか】round20のテスト図(腕を下ろした人物)で
    実測すると、腕はy=330で終わる。round21までのくびれ探索は、まさにその
    **y=331**をくびれとして採用していた——腕が消えて幅が急に細くなる行を
    「胴がいちばんくびれた所」と取り違えていたわけである。そこから
    スカート丈46.4cmという値が出ていたが、これは服ではなく**腕の長さ**を
    測った結果だった。同じワンピースを服だけで描いた絵ではくびれが
    見つからない(この図の胴は5%しか細くなっていない)ことからも、
    それが実在しないくびれだったと分かる。
    """
    if not _HAS_NUMPY or mask is None:
        return None
    for y in range(max(0, top), min(bottom + 1, len(mask))):
        if len(_row_runs(mask[y])) == 3:
            return y
    return None


def _find_waist(widths: list[int], top: int, bottom: int, height: int,
                 measurable: list[bool] | None = None) -> tuple[int | None, int | None]:
    """幅の分布から「くびれ(ウエスト)」の行と幅を探す。

    round22で`measure_proportions`から切り出した(`measure_sleeves`が同じ
    くびれを、袖丈をcmへ換算する基準として使うため。2か所に書き写すと
    片方だけ直して静かに食い違う)。

    「探索範囲の中でいちばん細い行」ではなく、**前後より細い行(極小)**で
    あることを要求する。単に最小値を取ると、シルエットが上から下へ単調に
    広がる絵(くびれの無いAラインなど)では探索範囲の上端がそのまま選ばれ、
    意味の無い値になる。実測でも、3種類の別々の絵がそろって「丈比3.0」と
    いう同じ値を返し、区別できていなかった。

    `measurable` は round23 で追加した(round22では「袖の裾より下」という
    単純な下限だった)。行ごとに「その幅を胴の幅として信用してよいか」を
    示す真偽値の列で、**袖/腕に覆われている行を除く**のに使う。
    袖が体から離れて描かれている行は、覆われていても真ん中の塊を取れば
    胴の幅が分かるので信用してよい(`_torso_widths`/`_measurable_rows`)。
    """
    lo = top + int(height * WAIST_SEARCH_BAND[0])
    hi = top + int(height * WAIST_SEARCH_BAND[1])
    window = max(2, int(height * WAIST_MIN_PROMINENCE_SPAN))

    def ok(y: int) -> bool:
        return measurable is None or (0 <= y < len(measurable) and measurable[y])

    waist_y = None
    waist_width = None
    for y in range(lo, min(hi + 1, len(widths))):
        w = widths[y]
        if w <= 0 or not ok(y):
            continue
        # round22: 「上側にはっきり太い所がある」の判定に**袖に覆われた行**を
        # 使ってはいけない。そこでの幅は胴ではなく「胴+左右の袖」なので、
        # 袖の裾のすぐ下の行が必ず条件を満たしてしまい、袖の裾がそのまま
        # くびれとして採用される(これが長袖の絵で丈比・広がりが壊れていた
        # 原因そのもの)。胴が見えている行が十分に無ければ、くびれは
        # 「測れない」とする。
        above_from = max(top, y - window)
        above = [widths[k] for k in range(above_from, y) if widths[k] > 0 and ok(k)]
        # round72: 裾のすぐ上の帯は「下側」から外す。
        #
        # 波形の裾・スカラップ・不規則な裾は、いちばん下のあたりで幅が
        # 細くなる。そこを「ウエストより細い行」と数えると、条件(b)が
        # 満たせずくびれが見つからない。実測(床までのサーキュラー
        # ドレス): 裾の波のせいでスカート丈が読めなくなっていた。
        # 裾の形は丈にも広がりにも関係しないので、見ない。
        below_limit = bottom - int(height * HEM_IGNORE_RATIO)
        below = [widths[k] for k in range(y + 1, max(y + 2, below_limit) + 1)
                 if k <= bottom and widths[k] > 0 and ok(k)]
        if len(above) < max(2, window // 2) or not below:
            continue
        # くびれの条件は2つ:
        #   (a) 上側にはっきり太い所がある(=そこまで細くなってきている)
        #   (b) それより下で、これ以上細くならない(=ここが胴の最小)
        # 「下側も太くなっていること」まで要求すると、裾が細いタイトな
        # シルエットでくびれを見つけられなかった(実測)。裾が広がるかどうかは
        # 広がり(hem_flare)の側で別に測るので、ここでは要求しない。
        if (max(above) >= w * WAIST_MIN_PROMINENCE
                and min(below) >= w - WAIST_BELOW_TOLERANCE_PX):
            if waist_width is None or w < waist_width:
                waist_width, waist_y = w, y
    return waist_y, waist_width


def measure_proportions(mask, colours=None) -> DesignProportions:
    """シルエットのマスクから、デザイン上の比率を測る。

    mask は `SimpleSilhouetteSegmenter.silhouette_mask` が返す2値配列。
    """
    if not _HAS_NUMPY or mask is None:
        return DesignProportions()
    # round73: 端で切れている絵からは、丈も広がりも読まない
    # (`runs_off_the_picture`のdocstringに実測を記載)。
    cropped = runs_off_the_picture(mask)
    if cropped:
        return DesignProportions(implausible_reason=cropped)

    # round72: 人物の絵で色から袖を読めなかった理由。読めたなら空文字。
    sleeve_reason = ""
    if colours is not None and getattr(colours, "reason", ""):
        sleeve_reason = colours.reason

    # round20: 人物が着ている絵では、頭・脚を除いた「服の範囲」で測る。
    # 全体で測ると、くびれを脚の間に見つけて広がりが1.00になる等、
    # すべての値が静かに壊れる(garment_spanのコメントに実測を記載)。
    span = garment_span(mask, colours)
    if span is None:
        return DesignProportions()
    top, bottom, figure_detected = span
    reason = sleeve_reason if figure_detected else ""
    height = bottom - top + 1
    if height < MIN_MEASURABLE_PX:
        return DesignProportions(sleeve_unreadable_reason=reason)

    # round22: 腕/袖が体から離れて描かれている行では、腕を除いた
    # 「胴の幅」で測る(_torso_widthsのdocstringに実測を記載)。
    widths = _torso_widths(mask)

    # 1. くびれ(ウエスト)を探す。上半身と下半身の境目。
    #
    #    「探索範囲の中でいちばん細い行」ではなく、**前後より細い行(極小)**
    #    であることを要求する。単に最小値を取ると、シルエットが上から下へ
    #    単調に広がる絵(くびれの無いAラインなど)では探索範囲の上端が
    #    そのまま選ばれ、意味の無い値になる。実測でも、3種類の別々の絵が
    #    そろって「丈比3.0」という同じ値を返し、区別できていなかった。
    #    くびれが見つからない絵では丈は測らない(Noneを返す)。
    #
    #    round22: **袖に覆われた行では胴のくびれを測れない**(そこでの幅は
    #    「胴+左右の袖」だから)。袖の裾より上を探索対象から外す。これを
    #    しないと、長袖の絵では袖の裾そのものをくびれと誤認して、丈比が
    #    1.61→0.71、広がりが2.49→1.68という**もっともらしい別の値**が
    #    静かに出ていた(`sleeve_hem_row`のdocstringに実測を記載)。
    lo = top + int(height * WAIST_SEARCH_BAND[0])
    hi = top + int(height * WAIST_SEARCH_BAND[1])
    #
    #    人物が着ている絵ではこの補正をかけない。腕の先(手首)も袖の裾と
    #    まったく同じ段差として現れるため、どの絵でも必ず「袖がウエストを
    #    覆っている」と判定され、round20で読めるようにした値がすべて
    #    読めなくなる。人物込みの絵で腕がウエストの幅に混ざる件は、
    #    round20に「広がりが服だけの絵より甘く出る」限界として記載済み。
    #    round23: 人物が着ている絵でも同じ判定を使う。腕の先も袖の裾と
    #    まったく同じ段差として現れるので、両方を「袖/腕の先」として扱い、
    #    そこより上は**腕が体から離れて描かれている行だけ**を信用する
    #    (`_measurable_rows`)。round22では人物込みの絵ではこの補正を
    #    丸ごと切っていたが、離れて描かれていれば胴は見えている。
    #    round72: ここを「色から読んだ腕の下端(`colours.arm_bottom`)」に
    #    置き換える案を書いて、**やめた**。パフ袖の絵で`sleeve_hem_row`が
    #    袖ではなく裾の861行を返していたのが動機だったが、それは
    #    淡い身頃がシルエットの穴になっていたせいで、穴を埋めたら消えた。
    #    直したあとに測り直すと、4枚の絵すべてで両者は同じ行を返す
    #    (690/800/690/690)。**戻しても落ちないので、入れない**。
    found_hem = sleeve_hem_row(mask, top, bottom)
    hem_y = found_hem[0] if found_hem else None
    measurable = _measurable_rows(mask, hem_y)
    # くびれがあるとすれば、袖の先より上(=探索範囲の始まりから袖の先まで)の
    # どこかである。そこに「胴が見えている行」が1つも無ければ、くびれは
    # シルエットに現れていないので読まない。1つでもあれば(袖が体から離れて
    # 描かれている等)、その範囲で従来どおり探す。
    band_start = lo
    if measurable:
        lo = next((y for y in range(lo, min(hi + 1, len(measurable))) if measurable[y]), lo)
    waist_y, waist_width = _find_waist(widths, top, bottom, height, measurable=measurable)
    torso_hidden = (
        hem_y is not None and hem_y >= band_start
        and not any(measurable[y] for y in range(band_start, min(hem_y + 1, len(measurable))))
    )
    if waist_y is None or not waist_width:
        if torso_hidden:
            # 袖がウエストを覆っていて、胴のくびれがシルエットに現れない。
            # 上半分のいちばん細い行を基準にする従来の代替手段も、その行が
            # 袖ぶんだけ太いので使えない。読まずに、その旨を開示する。
            return DesignProportions(sleeve_unreadable_reason=reason,
                                     figure_detected=figure_detected,
                                     waist_hidden_by_sleeve=True)
        # くびれが見つからない=上下の境目を決められない。丈は測らず、
        # 裾の広がりだけを「上半分のいちばん細い行」を基準に測る。
        band = [widths[y] for y in range(lo, min(hi + 1, len(widths)))
                if widths[y] > 0 and (not measurable or measurable[y])]
        if not band:
            return DesignProportions(sleeve_unreadable_reason=reason)
        reference = min(band)
        lower = [widths[y] for y in range(lo, bottom + 1) if widths[y] > 0]
        return DesignProportions(
            sleeve_unreadable_reason=reason,
            skirt_ratio=None,
            hem_flare=(max(lower) / reference) if lower and reference else None,
            figure_detected=figure_detected,
        )

    torso_px = waist_y - top
    if torso_px < MIN_MEASURABLE_PX / 2:
        return DesignProportions(sleeve_unreadable_reason=reason)

    # 2. スカート丈の比 = くびれから裾までの高さ ÷ 肩からくびれまでの高さ。
    skirt_px = bottom - waist_y
    skirt_ratio = skirt_px / torso_px if skirt_px > 0 else None

    # 3. 裾の広がり = くびれより下でいちばん広い行の幅 ÷ くびれの幅。
    #    テンプレート側の指標(SKIRT_FLARE_BY_VARIATION = パーツの最大幅 ÷
    #    ウエスト幅)と同じ定義にしてある。サーキュラースカートのように裾が
    #    曲線の場合、最下行だけを見ると幅がほぼ0になるため、最大幅で測る。
    lower = [widths[y] for y in range(waist_y, bottom + 1) if widths[y] > 0]
    hem_flare = (max(lower) / waist_width) if lower else None

    # round73: 服として成立しない値は採らない。
    #
    # round72まではここで測った値をそのまま返していた。ロゴ・帯・タイトル
    # 文字ごと測った画像では「ウエスト幅の599.00倍」という数が出て、それが
    # そのまま利用者への注記になり、いちばん広いスカートの型紙が出ていた。
    # 数が桁違いなら、測っているのは服ではない。
    # 丈も広がりも、同じ1本の「くびれ」から出ている。どちらかが服として
    # あり得ない値なら、くびれの場所そのものが間違っているので**両方捨てる**。
    # 片方だけ残すと、もっともらしい方だけが注記になって型紙に入る
    # (実測: 広がり414倍を捨てたあと、同じくびれから出た丈2.80倍＝109cmが
    # そのまま残っていた)。
    bad: list[str] = []
    if hem_flare is not None and hem_flare > HEM_FLARE_MAX:
        bad.append(f"裾の広がりがウエストの{hem_flare:.2f}倍")
    if bad:
        hem_flare = None
        skirt_ratio = None

    return DesignProportions(sleeve_unreadable_reason=reason,
                             implausible_reason="、".join(bad),
                             skirt_ratio=skirt_ratio, hem_flare=hem_flare,
                             figure_detected=figure_detected)


def choose_skirt_variation(hem_flare: float | None, default: str) -> str:
    """読み取った裾の広がりに、いちばん近いスカートのバリエーションを選ぶ。

    テンプレートを変形して任意の広がりを作るのではなく、既存の6種から
    選ぶ形にしている。テンプレートはどれも「ウエストからヒップまでの
    張り出し」「裾のカーブ」を含めて設計・検証済みで、広がりだけを
    後から引き伸ばすとその設計が崩れるため(正直な単純化)。
    """
    if hem_flare is None:
        return default
    return min(SKIRT_FLARE_BY_VARIATION,
               key=lambda v: abs(SKIRT_FLARE_BY_VARIATION[v] - hem_flare))


def nape_to_waist_cm(height_cm: float) -> float:
    """身長から背丈(首の付け根〜ウエスト)を求める。イラストの比をcmへ直す基準。"""
    return height_cm * NAPE_TO_WAIST_RATIO


def skirt_length_cm(skirt_ratio: float | None, height_cm: float) -> tuple[float | None, bool]:
    """イラストの比と身長から、スカート丈(cm)と「クランプしたか」を返す。

    クランプの範囲(SKIRT_LENGTH_RANGE_CM)を外れる読み取り結果は、絵の
    解釈を誤っている可能性が高いので端で止める。止めたことは呼び出し側が
    利用者へ開示する(黙って別の寸法を出さない、というこのプロジェクトの方針)。
    """
    if skirt_ratio is None or skirt_ratio <= 0:
        return None, False
    raw = nape_to_waist_cm(height_cm) * skirt_ratio
    lo, hi = SKIRT_LENGTH_RANGE_CM
    clamped = max(lo, min(hi, raw))
    return clamped, abs(clamped - raw) > 1e-6

# --- 首ぐりの形(round18で追加) ---------------------------------------------
#
# 服だけが写った画像(平置き・ハンガー・マネキン。このアプリが推奨している
# 入力)では、**シルエットの上辺の凹みがそのまま襟ぐり**である。上辺のいちばん
# 高い2点(=首の付け根)の間の落ち込みを測れば、形を見分けられる。
#
# しきい値は、このリポジトリの前身頃テンプレート6種を実際に塗りつぶし描画して
# 測った値から決めた(当てずっぽうの数値ではない。tests/test_illustration_fit.py
# の`test_neckline_detector_recognises_our_own_templates`が、テンプレートを
# 描き変えたら気付けるように固定している):
#
#   variation    深さ/幅   最深付近の平坦率   中央の深さ/最深
#   turtle        0.00        1.00              -      (凹み自体が無い)
#   boat          0.10        0.38             1.00
#   square        0.39        0.93             1.00
#   sweetheart    0.49        0.23             0.57    (中央が盛り上がる)
#   round         0.53        0.22             1.00
#   v             0.92        0.03             1.00

#: 凹みがこれ未満なら「襟ぐりの落ち込みが無い」=タートル(立ち衿)とみなす。
NECKLINE_FLAT_TOP_DEPTH_RATIO = 0.03
#: 中央の深さが最深のこれ未満なら、中央が盛り上がっている=スウィートハート。
NECKLINE_SWEETHEART_CENTER_RATIO = 0.80
#: 最深付近が平らな割合がこれ以上なら、底が水平=スクエア。
NECKLINE_SQUARE_FLAT_RATIO = 0.70
#: 深さ/幅がこれ未満なら、浅く横に広い=ボート。
NECKLINE_BOAT_DEPTH_RATIO = 0.20
#: 深さ/幅がこれ以上で、かつ底が平らでなければ、1点に向かって落ちる=Vネック。
NECKLINE_V_DEPTH_RATIO = 0.72
#: 「最深付近」とみなす、最深からの許容(開き幅に対する比率)。
NECKLINE_FLAT_TOLERANCE_RATIO = 0.015
#: 首ぐりと認めるのに必要な開き幅(px)。これ未満は測定誤差が大きすぎる。
NECKLINE_MIN_OPENING_PX = 16
#: 襟ぐりの開きが、服の幅に占める割合の上限。
#:
#: 上辺全体が真っ平ら(=いちばん高い点が端から端まで続く)場合、それは
#: 襟ぐりではなくベアトップのようなシルエットか、単に上辺が水平に描かれて
#: いるだけである。テンプレートの実測では最も広いボートネックでも0.60
#: (開き215px / 服の幅360px)なので、それより余裕を見た値で足切りする。
#: 超えた場合はNoneを返し、判定器の結果に委ねる(当てずっぽうに
#: タートルネックだと決めつけない)。
NECKLINE_MAX_OPENING_SPAN_RATIO = 0.75


def measure_neckline(mask) -> str | None:
    """シルエットの上辺から、襟ぐりの形(バリエーション名)を推定する。

    返すのは front_bodice のバリエーション名
    ("round_neck"/"v_neck"/"square_neck"/"boat_neck"/"sweetheart"/
    "turtle_neck")。判定できない場合はNoneで、呼び出し側は従来通り
    判定器(`engine/part_classifier.py`)の結果を使う。

    正直な限界: 人物や髪が写り込んでいる画像では、上辺が服ではなく頭部の
    輪郭になるので測れない(このアプリはもともと「服だけが写った画像」を
    推奨している)。前開きや打ち合わせのように、襟ぐりが左右非対称な
    デザインも想定していない。
    """
    if not _HAS_NUMPY or mask is None:
        return None
    # round20: 人物が着ている絵では、襟ぐりは服の内側の線であってシルエット
    # には現れない(上辺は頭部の輪郭になる)。実測でも、人物込みの絵から
    # sweetheart という頭の形に由来する誤判定が出ていた。読まずにNoneを返す。
    span = garment_span(mask)
    if span is not None and span[2]:
        return None
    columns = np.where(mask.any(axis=0))[0]
    if columns.size < NECKLINE_MIN_OPENING_PX:
        return None
    top = np.array([int(np.where(mask[:, x])[0][0])
                    for x in range(int(columns[0]), int(columns[-1]) + 1)])
    highest = int(top.min())
    # 首の付け根 = 上辺がいちばん高い点。その左右端の間が襟ぐり。
    shoulders = np.where(top <= highest + 1)[0]
    left, right = int(shoulders[0]), int(shoulders[-1])
    opening = right - left
    if opening < NECKLINE_MIN_OPENING_PX:
        return None
    if opening > len(top) * NECKLINE_MAX_OPENING_SPAN_RATIO:
        return None
    profile = top[left:right + 1]
    depth = int(profile.max()) - highest
    depth_ratio = depth / opening

    if depth_ratio < NECKLINE_FLAT_TOP_DEPTH_RATIO:
        return "turtle_neck"

    tolerance = max(1, int(opening * NECKLINE_FLAT_TOLERANCE_RATIO))
    flat_ratio = float((profile >= profile.max() - tolerance).sum()) / len(profile)
    center_ratio = (int(profile[len(profile) // 2]) - highest) / depth if depth else 1.0

    if center_ratio < NECKLINE_SWEETHEART_CENTER_RATIO:
        return "sweetheart"
    if flat_ratio >= NECKLINE_SQUARE_FLAT_RATIO:
        return "square_neck"
    if depth_ratio < NECKLINE_BOAT_DEPTH_RATIO:
        return "boat_neck"
    if depth_ratio >= NECKLINE_V_DEPTH_RATIO:
        return "v_neck"
    return "round_neck"

# --- 人物が着ている絵から、服の範囲だけを取り出す(round20で追加) -----------
#
# 【なぜ必要か】このアプリが想定する入力のひとつが「アニメの画像」、つまり
# **人物が衣装を着ている絵**である。ところがシルエットには頭・髪・腕・脚が
# 含まれるので、そのまま測るとすべての値が壊れる。実測(同じ衣装で比較):
#
#   入力              裾の広がり   スカート丈    襟ぐりの判定
#   服だけ              2.48       —           (上辺が水平)
#   人物が着ている      1.00       20cm        sweetheart(頭の輪郭)
#
# 広がりが1.00になるのは「くびれ」を脚の間に見つけてしまい、その下の最大幅
# (脚)と比べているため。丈が短く出るのは、基準の胴の高さに頭が含まれ、
# 裾の位置が足先になっているため。**黙って誤った寸法を出す**のが最も悪い
# 振る舞いなので、服の範囲を切り出してから測る。
#
# 【やり方】幅の分布から、首(頭と肩の間の強いくびれ)と裾(スカートから脚へ
# 幅が急落して戻らない位置)を探す。どちらも見つからなければ「服だけの絵」
# として従来どおり全体を使う。

#: 首と認めるための、下の肩幅に対する幅の比の上限。
#: 実測(簡易人物シルエット)では首20px・肩100pxで0.20だった。
NECK_MAX_WIDTH_RATIO = 0.60
#: 首を探す範囲(シルエット上端からの比率)。
NECK_SEARCH_BAND = 0.35
#: 首より上(=頭)がこれ以上の高さを占めていなければ、頭とみなさない。
MIN_HEAD_HEIGHT_RATIO = 0.04
#: 首から下って「肩に着いた」とみなす、直下の最大幅に対する比。
SHOULDER_WIDTH_RATIO = 0.80
#: 首の上に「頭」があると認めるための、首の幅に対する頭の幅の比。
#:
#: これを課さないと、**服の襟ぐりそのもの**を首と誤検出する。身頃の
#: テンプレートは上端が襟ぐりで、そこだけ幅が狭く下へ行くほど広がるため、
#: 首の条件(下が広い)を満たしてしまう。実際に導入前は、自前テンプレート
#: 6種すべてで襟ぐりの読み取りがNoneになった。頭は首より明確に太いので、
#: 「首より上に、首より太い塊がある」ことを要求すれば区別できる。
HEAD_MIN_WIDTH_RATIO = 1.5
#: 頭は肩から下の体より**細い**。この比を超えて太ければ頭ではない。
#:
#: これを課さないと、**ウエストのくびれ**を首と誤検出する。上に身頃+袖、
#: 下にスカートがある絵では、ウエストは「上下より細い行」という首と同じ
#: 条件を満たしてしまう。実際に導入前は、ミディ丈のワンピースでウエストを
#: 首と判定し、服の上端がスカートの途中(y=248)になっていた。
#: 実測: 人物シルエットは頭70px・肩100pxで0.70、ワンピースのウエストは
#: 上(身頃+袖)170px・下(スカート)120pxで1.42。
HEAD_MAX_VS_BODY_RATIO = 0.75
#: 首から肩を探す範囲(シルエットの高さに対する比率)。首と肩は隣接している。
SHOULDER_SEARCH_RATIO = 0.10
#: 裾と認めるための、それまでの最大幅に対する幅の比の上限。
HEM_DROP_RATIO = 0.60
#: 裾より下がずっと細いままであることを確かめる範囲の割合。
HEM_SUSTAIN_RATIO = 0.7


def runs_off_the_picture(mask) -> str:
    """シルエットが画像の端で切れているなら、その説明を返す(round73)。

    測れる絵は、**人物の周りに背景がぐるりとある**。端で切れている絵では、
    切れた先に何があるかが写っていない——袖の先が無い、裾が無い——のに、
    シルエットの上では「そこで終わっている」ようにしか見えない。

    【実測】公式の宣材ポスターをそのまま入れたときの読み取り:

        裾の広がり  ウエスト幅の599.00倍   ← ロゴ・帯・タイトル文字ごと測った
        スカート丈  背丈の1.75倍 → 68cm   ← もっともらしいが、服ではない

    round72までは、この画像から**何の断りもなく型紙が出ていた**。手で
    人物だけを切り抜いても、腕が左右の端で切れていれば同じことが起きる。

    判定は3つ:
      * 左と右の**両方**に接している —— 左右どちらかに続きがある
      * 上に接している —— 頭・肩が切れている
    下だけに接しているのは、足が画面の下端に立っている普通の構図なので通す。
    """
    if not _HAS_NUMPY or mask is None:
        return ""
    solid = np.asarray(mask).astype(bool)
    if solid.ndim != 2 or not solid.any():
        return ""
    edge = IMAGE_EDGE_TOLERANCE_PX
    top = bool(solid[:edge + 1].any())
    left = bool(solid[:, :edge + 1].any())
    right = bool(solid[:, -edge - 1:].any())
    if left and right:
        return "人物が画像の左右の端で切れています"
    if top:
        return "人物が画像の上端で切れています"
    return ""


def shoulder_row(mask) -> int | None:
    """シルエットの中で「肩線」にあたる行。頭が写っていないならNone。

    首は「上部で幅が強く落ち込み、その下がはっきり広くなる行」として出る。
    そこから下って幅がはっきり広がった最初の行が肩線。

    round72に独立した関数へ出した。`garment_span`の中だけで使っていたが、
    **色を読むときにも肩の位置が要る**ため(`engine/skin_tone.read_colours`)。
    色の読み取りはもともとシルエットの上端を肩とみなしていて、頭の描かれた
    絵では顔と髪から「服の色」を拾い、顔の肌色を12行続く素肌と見て
    **頭の高さを袖の裾**と読んでいた。
    """
    if not _HAS_NUMPY or mask is None:
        return None
    rows = np.where(mask.any(axis=1))[0]
    if rows.size < MIN_MEASURABLE_PX:
        return None
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1
    widths = [int(row.sum()) for row in mask]

    neck_limit = top + int(height * NECK_SEARCH_BAND)
    best_neck = None
    for y in range(top + int(height * MIN_HEAD_HEIGHT_RATIO), min(neck_limit, bottom)):
        w = widths[y]
        if w <= 0:
            continue
        below = widths[y + 1:min(bottom + 1, y + 1 + int(height * 0.25))]
        below = [v for v in below if v > 0]
        if not below:
            continue
        above = [v for v in widths[top:y] if v > 0]
        if not above or max(above) < w * HEAD_MIN_WIDTH_RATIO:
            continue   # 首の上に頭が無い = これは服の襟ぐり
        if max(above) > max(below) * HEAD_MAX_VS_BODY_RATIO:
            continue   # 上が下より太い = 頭ではなくウエストのくびれ
        if w <= max(below) * NECK_MAX_WIDTH_RATIO:
            if best_neck is None or w < widths[best_neck]:
                best_neck = y
    if best_neck is None:
        return None
    # 首そのものではなく、肩の位置(=服の上端)まで下ろす。探索範囲を短く
    # 取るのは、遠くのスカートの幅を目標にしてしまうとスカートの途中を
    # 肩と誤判定するため(実測で発生した)。
    shoulder = best_neck
    limit = min(bottom + 1, best_neck + 1 + int(height * SHOULDER_SEARCH_RATIO))
    look = [v for v in widths[best_neck:limit] if v > 0]
    target = max(look) * SHOULDER_WIDTH_RATIO if look else 0
    for y in range(best_neck, limit):
        if widths[y] >= target:
            shoulder = y
            break
    return shoulder


def garment_span(mask, colours=None) -> tuple[int, int, bool] | None:
    """シルエットのうち「服が写っている範囲」の上端・下端と、人物を検出したか。

    返り値は (top, bottom, figure_detected)。マスクが使えない場合はNone。
    figure_detected が True のときは、頭または脚を除外している。

    round72: `colours`(`engine/skin_tone.read_colours`の結果)を渡すと、
    裾は**服の色が写っているいちばん下**として決める。

    【なぜ形だけでは足りないか】シルエットだけで裾を探すときは「幅が
    急に落ちて、その後も戻らない行」を裾とする。ところが長袖の絵では、
    **腕が終わる行**でも幅が同じように落ちる。実測(長袖の絵):

        シルエットだけ   裾=801行(手首)  → スカート丈 26cm
        服の色で見る     裾=961行(裾)    → スカート丈 49cm

    26cmは膝上のミニスカートで、絵は膝丈である。もっともらしい別の値が
    出るので、利用者は気付けない。
    """
    if not _HAS_NUMPY or mask is None:
        return None
    rows = np.where(mask.any(axis=1))[0]
    if rows.size < MIN_MEASURABLE_PX:
        return None
    top, bottom = int(rows[0]), int(rows[-1])
    height = bottom - top + 1
    widths = [int(row.sum()) for row in mask]
    detected = False

    # 1. 首・肩を探して、頭を外す。
    shoulder = shoulder_row(mask)
    if shoulder is not None:
        top = shoulder
        detected = True

    # 2. 裾を探す。色から読めているならそれを使う(上のdocstring参照)。
    if colours is not None and getattr(colours, "garment_bottom", None) is not None:
        garment_bottom = int(colours.garment_bottom)
        if top + MIN_MEASURABLE_PX <= garment_bottom <= bottom:
            return top, garment_bottom, True

    # 形だけで裾を探す: 幅がそれまでの最大から急落し、その後も戻らない位置。
    #    スカートの裾から下は脚だけになるので、幅が戻らないことが決め手。
    running_max = 0
    hem = None
    start = top + int((bottom - top) * 0.35)   # 胴の途中から下を見る
    for y in range(start, bottom + 1):
        w = widths[y]
        if w > running_max:
            running_max = w
            continue
        if running_max <= 0 or w > running_max * HEM_DROP_RATIO:
            continue
        rest = [v for v in widths[y:bottom + 1] if v > 0]
        if not rest:
            continue
        # 急落した後、残りの大半が細いままであること。
        narrow = sum(1 for v in rest if v <= running_max * HEM_DROP_RATIO)
        if narrow >= len(rest) * HEM_SUSTAIN_RATIO:
            hem = y - 1
            break
    if hem is not None and hem > top + MIN_MEASURABLE_PX:
        bottom = hem
        detected = True

    if bottom - top < MIN_MEASURABLE_PX:
        return None
    return top, bottom, detected


# --- 袖を読む(round22で追加) -----------------------------------------------
#
# 【round21までの状態】袖はまったく読めていなかった。既定の分割器
# (SimpleSilhouetteSegmenter)は袖の領域を「シルエットの外接矩形の左右18%の
# 帯」という固定比率で切っているだけで、袖そのものを捉えていない。その結果、
# 半袖の絵でも長袖の絵でもノースリーブの絵でも、生成される袖はまったく同じ
# だった(袖丈は採寸値どおり、形は判定器の既定値)。
#
# 【読める根拠】袖の裾は、シルエットの輪郭に**1行で終わる段差**として現れる。
# 袖は胴から左右へ出て下がり、その先で水平に切れているからである。一方、
# ノースリーブの袖ぐりは滑らかな曲線なので、段差にならない。自前の
# テンプレートから「服だけの絵」を合成して実測した、外側の輪郭が1行で
# 内側へ跳ぶ量(px, 1cm=6px):
#
#   袖あり(6種)  … 34〜107px (5.7〜17.8cm)
#   ノースリーブ … 1px
#
# 2桁違うので、しきい値で確実に分けられる。段差の位置から袖丈が、段差より
# 上の輪郭の形から袖の膨らみ方が読める。実測(合成した絵 → 期待値):
#
#   袖            袖丈cm(期待)   最広位置(期待)
#   cap            16.9(17.0)     0.77(0.7)
#   puff           30.7(30.8)     0.53(0.5)
#   three_quarter  37.9(38.0)     0.39(0.3)
#   straight       51.9(52.0)     0.30(0.3)
#   curve          51.9(52.0)     0.30(0.3)
#   bell           51.9(52.0)     0.99(1.0)
#
# 袖丈は0.1cm以内で戻ってくる。最広位置(=いちばん太い所が袖山からどのくらい
# 下か)は、同じ袖丈のstraight/curve(0.30)とbell(0.99)を分けるのに使う。

#: 袖の裾と認めるための、外側の輪郭が1行で内側へ跳ぶ量(シルエットの幅に対する比)。
#: 実測では袖ありで最小34px/幅約410px=0.083、ノースリーブは1px=0.002。
SLEEVE_HEM_STEP_RATIO = 0.02
#: 袖の裾を探す範囲(シルエットの高さに対する比率)。これより下は
#: スカートの裾や脚であって袖ではない。
SLEEVE_SEARCH_BAND = 0.75
#: 肩の付け根(袖が始まる位置)が、シルエットの上端からどれだけ下がっているか。
#: 身頃テンプレートの肩下がり(前5.3cm)を背丈(38.7cm)で割った実測値。
SHOULDER_DROP_RATIO = 5.3 / 38.7
#: 袖丈として受け付ける範囲(cm)。これを外れた読み取りは使わない。
SLEEVE_LENGTH_RANGE_CM = (8.0, 75.0)
#: 各袖テンプレートの実寸(cm)と、幅がいちばん広くなる位置(袖山からの比)。
#: どちらもテンプレートを実際に塗りつぶし描画して測った値(当てずっぽうではない)。
SLEEVE_TEMPLATE_LENGTH_CM = {
    "cap": 17.0, "puff": 30.8, "three_quarter": 38.0,
    "straight": 52.0, "curve": 52.0, "bell": 52.0,
}
SLEEVE_TEMPLATE_WIDEST_AT = {
    "cap": 0.7, "puff": 0.5, "three_quarter": 0.3,
    "straight": 0.3, "curve": 0.3, "bell": 1.0,
}
#: 袖丈でどれを選ぶかの境目(cm)。上の実測値の中点。
_CAP_PUFF_BOUNDARY_CM = (17.0 + 30.8) / 2      # 23.9
_PUFF_TQ_BOUNDARY_CM = (30.8 + 38.0) / 2       # 34.4
_TQ_LONG_BOUNDARY_CM = (38.0 + 52.0) / 2       # 45.0
#: 長袖のうちベルスリーブと認める「最広位置」の下限。straightの0.3と
#: bellの1.0の中点。
BELL_WIDEST_AT_MIN = (0.3 + 1.0) / 2           # 0.65


@dataclass(frozen=True)
class SleeveReading:
    """イラストから読み取った袖(round22で追加)。"""

    length_cm: float | None = None
    #: いちばん太い所が袖山からどのくらい下か(0=袖山、1=袖口)。
    widest_at: float | None = None
    #: 袖の裾の段差が見つからなかった=ノースリーブと判断した。
    sleeveless: bool = False
    #: 袖がウエストを覆っている(=長袖)。この場合、袖丈をcmへ換算する
    #: 基準(背丈)がシルエットに写っていないので length_cm は None になる。
    covers_waist: bool = False

    @property
    def detected(self) -> bool:
        return (self.length_cm is not None or self.sleeveless
                or self.covers_waist)


def _outer_edges(mask) -> tuple[list[int], list[int]]:
    """各行の、前景のいちばん左といちばん右のx(前景が無い行は-1)。"""
    lefts, rights = [], []
    for row in mask:
        xs = np.where(row)[0]
        if xs.size:
            lefts.append(int(xs[0]))
            rights.append(int(xs[-1]))
        else:
            lefts.append(-1)
            rights.append(-1)
    return lefts, rights


def sleeve_hem_row(mask, top: int, bottom: int) -> tuple[int, str] | None:
    """袖の裾(袖が水平に切れている行)と、それを見つけた側を返す(round22)。

    【なぜ輪郭の段差で分かるのか】袖は胴から左右へ出て下がり、その先で
    水平に切れている。だから外側の輪郭は、袖の裾で**1行のうちに**大きく
    内側へ跳ぶ。一方ノースリーブの袖ぐりは滑らかな曲線なので跳ばない。
    自前のテンプレートから合成した「服だけの絵」での実測(幅約410pxの絵):

        袖あり(6種)   … 34〜107px の跳び
        ノースリーブ  … 1px

    2桁違うので、しきい値で確実に分けられる。

    【この行が、袖以外にも効く重要な意味を持つ】この行より**上**では、
    シルエットの幅は「胴 + 左右の袖」であって胴の幅ではない。したがって
    **袖に覆われた範囲で胴のくびれ(ウエスト)を測ってはいけない**。
    round21まではこれを見ておらず、長袖の絵では袖の裾そのものを
    「いちばん細い行」=ウエストと誤認して、スカート丈と裾の広がりが
    静かに壊れていた。実測(同じ胴・同じスカートで袖だけ差し替えた合成画):

        袖            検出したくびれy   真値   丈比   広がり
        なし/cap/puff       285         288    1.61   2.49  (正しい)
        three_quarter       320         288    1.26   2.19
        straight/bell       404         288    0.71   1.68  (大きく誤り)

    丈比が1.61→0.71、広がりが2.49→1.68と、**もっともらしい別の値**が
    出るので利用者は気付けない。`measure_proportions`はこの行より下だけを
    くびれの探索対象にし、そこに見つからない場合は「袖がウエストを隠して
    いて測れない」として読み取りを見送る。
    """
    if not _HAS_NUMPY or mask is None:
        return None
    height = bottom - top + 1
    if height < MIN_MEASURABLE_PX:
        return None
    widths = _column_widths(mask)
    garment_width = max(widths[top:bottom + 1]) if bottom >= top else 0
    if garment_width <= 0:
        return None
    min_step = max(2.0, garment_width * SLEEVE_HEM_STEP_RATIO)

    lefts, rights = _outer_edges(mask)
    limit = top + int(height * SLEEVE_SEARCH_BAND)
    best_step, hem_y, side = 0.0, None, None
    # 左右それぞれで探し、大きい方の跳びを採る(片袖しか描かれていない絵や、
    # 片側が見切れている絵でも読めるように)。
    for y in range(top + 1, min(limit, bottom)):
        for edges, name, sign in ((lefts, "left", 1), (rights, "right", -1)):
            a, b = edges[y], edges[y + 1]
            if a < 0 or b < 0:
                continue
            step = (b - a) * sign
            if step > best_step:
                best_step, hem_y, side = step, y, name
    if hem_y is None or best_step < min_step:
        return None
    return hem_y, side


def measure_sleeves(mask, height_cm: float, colours=None) -> SleeveReading:
    """シルエットから袖の有無・袖丈・袖の形を読み取る(round22で追加)。

    3つの場合に分かれる:

      1. 袖の裾の段差が無い → **ノースリーブ**。
      2. 段差があり、その**下**に胴のくびれが見つかる → 袖はウエストより
         上で終わっている。くびれまでの高さ(=背丈)を基準に袖丈をcmで測る。
      3. 段差はあるが、その下にくびれが見つからない → 袖がウエストを
         覆っている = **長袖**。この場合、cmへ換算する基準そのものが
         シルエットに写っていないので袖丈は測らず、長袖であることだけを
         返す(袖丈は従来どおり採寸値から決まる)。

    人物が着ている絵では読まない。腕そのものが袖と同じ張り出しとして写り、
    袖の裾と手首の区別がシルエットには現れないからである。
    """
    if not _HAS_NUMPY or mask is None:
        return SleeveReading()
    # 「端で切れている絵からは袖も読まない」という一行をここへ入れて、
    # **やめた**(round73)。端で切れた絵を何枚作っても、袖丈は入れる前から
    # Noneで、外しても落ちるテストを作れなかった。人物の絵では色から読む
    # ところで落ち、服だけの絵では段差が見つからないためである。
    span = garment_span(mask, colours)
    if span is None:
        return SleeveReading()
    top, bottom, figure_detected = span
    if figure_detected:
        # round72: 人物が着ている絵では、**色**で袖を読む。
        #
        # シルエットだけでは、素肌の腕も袖も同じ黒い塊にしか見えない。
        # round71まではここで諦めており、その結果**袖なしの絵にも袖の
        # 型紙が2枚付いてきた**(実測。READMEのround72参照)。
        # 素肌と服は色が違うので、腕のどこまでが袖かは色なら読める。
        return _sleeves_from_colours(mask, height_cm, colours, top, bottom)
    height = bottom - top + 1
    if height < MIN_MEASURABLE_PX:
        return SleeveReading()

    found = sleeve_hem_row(mask, top, bottom)
    if found is None:
        return SleeveReading(sleeveless=True)
    hem_y, side = found

    widths = _torso_widths(mask)
    lefts, rights = _outer_edges(mask)

    # 袖の形: 袖山から袖の裾までの間で、外側の輪郭がいちばん外へ出る位置。
    # 基準のx(幅0の位置)は、袖の裾のすぐ下の輪郭=胴の脇に取る。基準が多少
    # ずれても「いちばん外へ出る位置」は変わらない。袖口の幅そのものは基準の
    # ずれをまともに受けるので使わない(実測でcapが0.00→0.49、puffが
    # 0.15→0.56とずれた)。
    edges = lefts if side == "left" else rights
    sign = 1 if side == "left" else -1
    reference = edges[hem_y + 1]
    profile = [(reference - edges[y]) * sign
               for y in range(top, hem_y) if edges[y] >= 0]
    widest_at = None
    if len(profile) >= 4 and max(profile) > 0:
        widest_at = profile.index(max(profile)) / (len(profile) - 1)

    waist_y, _waist_width = _find_waist(widths, top, bottom, height,
                                         measurable=_measurable_rows(mask, hem_y))
    if waist_y is None or waist_y <= top:
        # 袖がウエストを覆っている = 長袖。cmの基準が写っていないので
        # 袖丈は測らない。
        return SleeveReading(widest_at=widest_at, covers_waist=True)

    torso_px = waist_y - top
    shoulder_px = torso_px * SHOULDER_DROP_RATIO
    length_px = (hem_y - top) - shoulder_px
    if length_px <= 0:
        return SleeveReading(widest_at=widest_at)
    length_cm = length_px / torso_px * nape_to_waist_cm(height_cm)
    if not (SLEEVE_LENGTH_RANGE_CM[0] <= length_cm <= SLEEVE_LENGTH_RANGE_CM[1]):
        # 範囲外は、袖ではない何かの段差(小物、髪、背景の切れ目)を拾った
        # 可能性が高い。丈は使わない。
        return SleeveReading(widest_at=widest_at)

    return SleeveReading(length_cm=length_cm, widest_at=widest_at)


def _sleeves_from_colours(mask, height_cm: float, colours,
                           top: int, bottom: int) -> SleeveReading:
    """色から読んだ結果(`engine/skin_tone.read_colours`)を袖の読みに直す。

    読めていなければ、round71までと同じく**何も返さない**
    (袖は採寸どおりになり、呼び出し側がその旨を利用者へ開示する)。
    """
    if colours is None or not getattr(colours, "usable", False):
        return SleeveReading()
    if colours.sleeveless:
        return SleeveReading(sleeveless=True)
    if colours.covers_wrist:
        return SleeveReading(covers_waist=True)
    hem_y = colours.sleeve_hem_y
    if hem_y is None:
        return SleeveReading()

    # 袖丈をcmへ直す基準は、シルエットだけのときとまったく同じ——
    # 肩から胴のくびれまでを背丈(身長の約1/4)とみなす。
    widths = _torso_widths(mask)
    height = bottom - top + 1
    waist_y, _w = _find_waist(widths, top, bottom, height,
                               measurable=_measurable_rows(mask, hem_y))
    if waist_y is None or waist_y <= top:
        return SleeveReading(covers_waist=True)
    torso_px = waist_y - top
    shoulder_px = torso_px * SHOULDER_DROP_RATIO
    length_px = (hem_y - top) - shoulder_px
    if length_px <= 0:
        return SleeveReading()
    length_cm = length_px / torso_px * nape_to_waist_cm(height_cm)
    if not (SLEEVE_LENGTH_RANGE_CM[0] <= length_cm <= SLEEVE_LENGTH_RANGE_CM[1]):
        # 範囲外は、袖ではない何か(小物・髪・手袋)を拾った可能性が高い。
        return SleeveReading()
    return SleeveReading(length_cm=length_cm)


def choose_sleeve_variation(reading: SleeveReading, default: str) -> str | None:
    """読み取った袖から、いちばん近い袖テンプレートを選ぶ(round22)。

    ノースリーブと判断した場合は None を返す(呼び出し側で袖を足さない)。
    読み取れなかった場合は `default`(判定器が選んだ袖)をそのまま返す。

    正直な限界: **straightとcurveは見分けていない**。両者の違いは袖口の
    細まり方だけ(袖口/最大幅が0.77と0.71)で、絵から読み取れる精度では
    区別できない。長袖でベルスリーブでなければstraightにする。
    """
    if reading.sleeveless:
        return None
    if reading.covers_waist:
        # 袖がウエストより下まである = 長袖。ベルスリーブだけは形で分かる。
        if reading.widest_at is not None and reading.widest_at >= BELL_WIDEST_AT_MIN:
            return "bell"
        return "straight"
    if reading.length_cm is None:
        return default
    if reading.length_cm < _CAP_PUFF_BOUNDARY_CM:
        return "cap"
    if reading.length_cm < _PUFF_TQ_BOUNDARY_CM:
        return "puff"
    if reading.length_cm < _TQ_LONG_BOUNDARY_CM:
        return "three_quarter"
    if reading.widest_at is not None and reading.widest_at >= BELL_WIDEST_AT_MIN:
        return "bell"
    return "straight"
