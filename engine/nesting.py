"""nesting.py — rectpack によるAIネスティング（布ロス削減）。

rectpack / GuillotineBSSFにより、パーツのバウンディングボックスを長方形
ビンパッキング問題として解き、1枚の生地(fabric_width_cm 幅の連続した布)の上に
パーツを詰めて配置する。縫い代・布目方向制約にも対応する（下記参照）。

本物の不定形ネスティング（パーツの輪郭同士を隙間なく組み合わせる、NFP:
no-fit-polygonベースの手法）ではなく、外接矩形での矩形パッキング(rectpack =
2次元パッキング)が基本である点は簡略化として明記しておく。実測の布ロス率は
組み合わせによって上下するため、目標値・概算として扱うこと。

その上で、`_compact_placement()` が矩形パッキング結果に対して軽量な
後処理を行い、実ポリゴン(縫い代込みの裁断線)ベースで「180度回転(常に
布目安全)を使って、外接矩形の隙間にどこまで実際に詰め込めるか」を
貪欲に探索する。台形(スカート等)やカーブした袖のペアでは、この圧縮に
よって実際にパーツ同士が触れ合うところまで詰め直されることを確認して
いる(tests/test_nesting.py参照)が、正直な実測として、複数パーツが混在
する現実的な衣装1式では布ロス率の改善は数値上わずか(実測でおよそ
0〜0.3ポイント程度)であり、本格的なNFPネスティングの代替にはならない。
これは、rectpack自体が既に矩形単位では効率的な配置を見つけていること、
かつこの圧縮が「同じ段(row)の中で、既に確定した隣のパーツに実際にどこ
まで寄せられるか」を貪欲に探すだけで、パーツの入れ替えや段の再構成
までは行わないことによる。安全性については、圧縮後に必ず実ポリゴン
同士の重なりを再検証し、悪化や想定外の重なりを検出した場合は圧縮を
諦めて元の矩形配置をそのまま返す(fail-safe)。

布目方向について（重要）:
  各パーツには縦地方向を示す布目線(grainline)が入っている。90度回転して
  配置すると、そのパーツだけ布目が生地の縦地に対して90度ズレてしまい、
  「縫い代・布目方向制約にも対応」という要件と矛盾する
  （伸縮・ドレープ性が生地の方向によって変わる織物では特に問題になる）。
  そのため既定(allow_rotation=False)では回転を禁止し、全パーツの布目を
  生地の縦地と一致させる「布目安全」な配置のみを行う。
  ニット・不織布・無地の非方向性生地など、回転しても実用上問題ない場合に限り
  呼び出し側が allow_rotation=True を明示的に指定できる（フロントエンドにも
  「非方向性の生地」チェックボックスとして露出している）。

【round5での追加調査・改良】
  `_compact_placement`(圧縮パスの入口)を、複数の処理順を試し・収束する
  まで反復するように拡張した。ただし実際に測定したところ、この拡張が
  追加の布ロス改善をもたらすのはごく一部のケースのみで、多くの現実的な
  衣装スペックでは改善量はゼロだった。より積極的な手法(乱数によるパーツ
  入れ替えの局所探索)も試作したが、効果が不安定な割に計算コストが
  Webリクエスト1回あたり数秒かかり見合わないと判断し、本番コードには
  含めていない。詳細で正直な数値は`_compact_placement`のdocstring参照。

【round6での追加調査・改良】
  rectpack自体の「詰め込みアルゴリズム×並べ替え順」の探索余地を再調査
  したところ、round5までは`_SORT_ALGO_CANDIDATES`(rectpackが提供する
  並べ替え戦略のうち、面積順のSORT_AREA・周囲長順のSORT_PERIの2種類)しか
  試していなかったことが分かった。実際に、細長いパーツと幅広いパーツが
  混在する組み合わせ(例: 前開きファスナー(縦長の左右パネル)+袖)で、この
  2種類のどちらも「本来1段に収まるはずの配置」を見つけられず、不要な
  2段目を使ってしまい布ロス率が約0.60まで悪化する実例を発見した。
  rectpackが提供する残り全ての並べ替え戦略(SORT_DIFF・SORT_SSIDE・
  SORT_LSIDE・SORT_RATIO・SORT_NONE)を追加で試したところ、同じケースで
  SORT_DIFF・SORT_LSIDE・SORT_NONEのいずれもが本来の1段構成(布ロス率
  0.20前後)を見つけられることを確認した。`_best_of`は「試した候補の中で
  布ロス率が最小のものを採用する」設計のため、候補を追加しても既存の
  ケースの結果が悪化することは無く、実測でも1リクエストあたりの処理時間
  への影響は誤差の範囲内(rectpack自体の矩形パッキングが非常に高速な
  ため)だったので、`_SORT_ALGO_CANDIDATES`にrectpackの全並べ替え戦略を
  追加した(詳細はその定数のコメント、および
  tests/test_nesting.pyの`test_round6_expanded_sort_candidates_fix_a_previously_badly_packed_case`
  参照)。

  正直な副作用として、`_best_of`が「圧縮前の生の詰め込み結果」の布ロス率
  だけを見て最良候補を1つ選び、圧縮(`_compact_placement`)はその1件にしか
  適用しない(全候補に圧縮を適用すると処理時間が実測で数倍に増えるため)
  設計のままであるため、候補を追加したことで「圧縮前は僅差で2位だったが、
  圧縮後には僅差で1位より優れていたはずの候補」が選ばれなくなり、ごく
  まれに最終的な布ロス率が0.5ポイント未満のごくわずかな差で悪化する
  ケースが存在することを確認した(実測: 標準M寸の身頃+パンツの組み合わせで
  約0.28→0.28、0.34ポイント程度の悪化)。この悪化幅は今回発見・修正した
  改善幅(前開きファスナーのケースで約40ポイント)に比べて無視できるほど
  小さく、かつ「圧縮は最良候補1件にのみ適用する」という既存の設計判断
  自体(全候補への圧縮適用はコストに見合わない)を変える理由には当たらない
  と判断し、そのまま許容することにした。

【round7での追加調査(3回目)】
  round6は「並べ替え戦略(sort_algo)」側の探索余地を広げたが、「詰め込み
  アルゴリズム(pack_algo)」側は`_PACK_ALGO_CANDIDATES`の3種類のまま
  (GuillotineBssfSas・GuillotineBafSas・MaxRectsBssf)だった。rectpackが
  実際に提供するpack_algoはGuillotine系18種・MaxRects系4種・Skyline系6種の
  合計28種であり、この未探索領域が同種の改善余地を残していないか再調査
  した(`/tmp/nesting_investigation.py`で46通りの衣装スペック×2種類の
  体型×2種類の生地幅=184ケースを、現行3種と全28種それぞれで総当たり
  比較)。

  結果、184ケース中3ケース(約1.6%)で、全28種まで広げると現行3種より
  布ロス率が0.5ポイント超改善することを確認した。最も差が大きかった
  ケース(vネック+ベル袖+ワイドパンツ+シャツカラー+ゴムウエストバンドの
  組み合わせ、生地幅150cm)では、現行3種の最良が約0.260、全28種の最良が
  約0.198と、6.2ポイントの改善が見られた。ただし全28種を毎回試すと
  1リクエストあたりの平均処理時間が約2.6msから約32ms(最大63ms)へと
  約12倍に増えることも実測された(`_best_of`は既に
  3種×7並べ替え×2生地幅=42通りを試す設計のため、28種に広げると
  28×7×2=392通りに増える計算)。

  そこで、どのpack_algoが実際にこれら3ケースの改善を生んでいるかを
  個別に特定したところ、SkylineMwfl・MaxRectsBl・MaxRectsBafの3種類の
  いずれかだけで全28種と同じ最良値に到達できることが分かった(残り25種は
  この184ケードのいずれにおいても、現行3種を上回る結果を一度も出さな
  かった)。そこで、全28種ではなくこの3種のみを追加した6種類構成
  (`_PACK_ALGO_CANDIDATES`参照)で同じ184ケースを再検証し、全28種と
  完全に同じ最良値(悪化ゼロ、全ケース差0.5ポイント未満)を、平均約7.0ms・
  最大約13.6ms(現行3種比で約2.7倍、全28種比で約4.6倍高速)で再現できる
  ことを確認した(詳細は
  tests/test_nesting.pyの`test_round7_expanded_pack_candidates_fix_a_previously_badly_packed_case`
  参照)。`_best_of`の「試した候補の中で最小のものを採用する」設計により、
  追加した候補が既存のケースの結果を悪化させることも無い。

  以上の実測に基づき、`_PACK_ALGO_CANDIDATES`にMaxRectsBl・MaxRectsBaf・
  SkylineMwflの3種類を追加した(全28種のうち、実際に改善に寄与することを
  確認できたものだけを採用し、確認できていない残り22種は処理時間節約の
  ため追加していない)。

【round11での追加調査・改良(4回目): 圧縮対象を「同点候補」まで広げた】
  round6のdocstring(上記)に、副作用として「圧縮は圧縮前の布ロス率が最良の
  候補1件にしか適用しないため、僅差の2位以下が圧縮後には1位を上回っていた
  はずのケースを取りこぼす」という制約を正直に記録していた(標準M寸の
  身頃+パンツで実測約0.34ポイントの悪化)。round11でこれを解消できるか、
  実際に測って検証した。

  まず素朴に「圧縮前の上位K件(K=4)を全て圧縮してから最良を選ぶ」実装を
  試した。162ケース(ネックライン×袖×スカート×パンツ×生地幅3種)の実測で
  25ケース(15%)が改善し悪化はゼロだったが、コストが見合わなかった:
  1リクエストあたりの処理時間が、2パーツ構成で86→322ms、6パーツ構成で
  191→785ms、14パーツ構成で344→1143msと、おおむね3〜4倍に増えた。
  round5で局所探索を「効果が薄いのに数秒かかる」として見送ったのと同じ
  判断基準に照らし、この素朴な実装は採用しないことにした。

  そこで、取りこぼしの根本原因を絞り込んだ。圧縮前の布ロス率は
  「1 - パーツ面積合計 / (生地幅 × 使用長)」という外接矩形ベースの指標で
  あり、実際の配置が異なる候補どうしでも値が完全に同点になることが非常に
  多い。つまり取りこぼしの正体は「僅差の2位」ではなく「同点なのに、
  たまたま先に見つかった1件だけが圧縮される」ことだった。そこで対象を
  「圧縮前の成績が最良と同点で、かつ実際の配置が異なる候補」だけに絞り
  (配置が完全に同一の候補は除外し、上限3件で打ち切る)、同じ162ケースで
  再測定した(round12で撤回したため、この実装は現在は残っていない)。

  結果は素朴なK=4より効果が高く、コストは低かった:
    - 改善したケース: 31/162(19%)。素朴なK=4の25/162(15%)より多い。
    - 最大の改善: 布ロス率が約0.263→約0.131と半減するケースがあった。
    - 処理時間: 6パーツ構成で163→331ms、14パーツ構成で257→480ms。
  この時点では「一部のケースで生地が実際に大きく節約できる価値の方が、
  処理時間の増加より大きい」と判断して採用した。

【round12での撤回: 上記の改良は、実はテンプレートの寸法不正の産物だった】
  round12で袖・身頃のテンプレートを「実際に縫える寸法」に作り直した
  (scripts/generate_templates.py参照)後、同じ測定をやり直したところ、
  round11で観測した大きな改善は再現しなくなった:

    - 432ケース(ネックライン×袖×スカート×パンツ×体型2種×生地幅3種)で
      改善したのは67ケースだが、**改善幅は最大0.43ポイント・中央値0.17
      ポイント**にとどまり、0.5ポイント以上改善するケースは1件も無かった。
    - 一方コストは変わらず、6パーツ構成で150→308ms、14パーツ構成で
      285→540msと、ネスティングの処理時間はおよそ2倍のままだった。

  round11で「布ロス率が半減する」と報告した劇的なケースは、当時の袖が
  異常に小さかった(袖丈22cm・袖山22cm)ために生まれていた特殊な配置に
  依存しており、寸法を正すと消えた。つまりあの改良は、別の欠陥が作った
  歪んだ状況にだけ効いていたことになる。

  「効果が薄いのに処理時間が倍になる」のは、round5で局所探索を見送った
  ときとまったく同じ判断基準に当たる。そのため round12 でこの改良を撤回し、
  round10までと同じ「圧縮前の最良候補1件だけを圧縮する」実装に戻した。
  round6のdocstringに記録した「同点・僅差の候補を取りこぼす」制約は、
  未解消のまま残る(ただし実測での影響は最大0.43ポイント)。

  この一件の教訓として、最適化の効果を測るときは、測定対象そのものが
  正しい前提に立っているかを先に確かめる必要がある、という点を記録しておく。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from itertools import product

from rectpack import (
    GuillotineBssfSas,
    GuillotineBafSas,
    MaxRectsBssf,
    MaxRectsBl,
    MaxRectsBaf,
    SkylineMwfl,
    SORT_AREA,
    SORT_DIFF,
    SORT_LSIDE,
    SORT_NONE,
    SORT_PERI,
    SORT_RATIO,
    SORT_SSIDE,
    newPacker,
)
from shapely.geometry import Polygon as _ShapelyPolygon

from .seam import FinalizedPart, Point

#: 試す生地幅の候補(cm)。日本で一般に流通する反物・生地の幅に合わせている。
#:
#: 【round11で140cmを追加】round10までは110cm(シングル幅)と150cm(ダブル幅)の
#: 2種類だけを試していた。実務で広く流通しているもう1つの標準幅である140cmを
#: 追加できないか、実際の衣装スペック(ネックライン×袖×スカート×パンツの
#: 組み合わせ)72通り×標準体型/大きめ体型で総当たり実測したところ、
#: 26通り(約36%)で布ロス率が改善し、悪化は1件も無かった
#: (`_best_of`が「試した候補の中で最小のものを採用する」設計のため、候補を
#: 増やして悪化することは原理的に起こらない)。最も差が大きかったケース
#: (標準M寸・ラウンドネック+ベル袖+タイトスカート、6パーツ)では布ロス率が
#: 約0.125から約0.063へと半減した。
#:
#: コスト: 生地幅候補が2→3に増えるぶん`nest_parts`の呼び出し回数も1.5倍に
#: なる。実測では1リクエストあたり約25〜85msの増加(2パーツ構成で59→89ms、
#: 14パーツ構成で219→304ms)で、round7で許容した追加コストと同程度の水準に
#: 収まるため採用した。回帰テストは
#: tests/test_nesting.pyの`test_140cm_fabric_width_strictly_beats_110_and_150_for_a_mid_width_case`。
DEFAULT_FABRIC_WIDTHS_CM = (110.0, 140.0, 150.0)
DEFAULT_SEAM_GAP_CM = 0.3

# 圧縮パス(_compact_placement)の対象とするパーツ数・探索候補数の上限。
# 超えた場合は圧縮を諦めて素のbbox配置をそのまま返す(処理時間の暴走防止)。
_COMPACTION_MAX_PARTS = 16
_COMPACTION_MAX_CANDIDATES_PER_AXIS = 12


# 布目を無視できない前提での省ロス探索用に、複数のパッキング戦略を試して
# 一番ロスが小さいものを採用する（回転は許可しないので、探索の余地は
# 「どの順番・どのアルゴリズムで詰めるか」だけになる）。
# 【round7での追加調査・改良】rectpackが提供するpack_algoは全28種類ある
# (Guillotine系18種・MaxRects系4種・Skyline系6種)が、round6まではこの
# うち3種類しか試していなかった。全28種類との比較実測(46スペック×2体型×
# 2生地幅=184ケース)により、MaxRectsBl・MaxRectsBaf・SkylineMwflの3種類を
# 追加することで、残り22種類を追加しなくても全28種類総当たりと同じ最良値
# (184ケース全てで差0.5ポイント未満)に到達できることを確認したため、この
# 3種類のみを追加した。最大で6.2ポイントの布ロス改善が確認できたケースも
# ある(vネック+ベル袖+ワイドパンツ+シャツカラー+ゴムウエストバンドの
# 組み合わせ)。詳細な数値と検証方法はこのファイル冒頭の
# 【round7での追加調査(3回目)】、およびtests/test_nesting.pyの
# `test_round7_expanded_pack_candidates_fix_a_previously_badly_packed_case`
# 参照。
_PACK_ALGO_CANDIDATES = (
    GuillotineBssfSas, GuillotineBafSas, MaxRectsBssf,
    MaxRectsBl, MaxRectsBaf, SkylineMwfl,
)
# 【round6での追加調査・改良】以前はSORT_AREA/SORT_PERIの2種類だけを試して
# いたが、round6でrectpackが提供する並べ替え戦略を総当たりで比較したところ、
# 一部の組み合わせ(細長いパーツと幅広いパーツが混在するケース、例:
# 前開きファスナー+袖)で、SORT_AREA/SORT_PERIのどちらも「本来1段に収まる
# はずの配置」を見つけられず、不要に2段目を使ってしまい布ロス率が0.60前後
# まで悪化する実例を発見した。SORT_DIFF/SORT_SSIDE/SORT_LSIDE/SORT_RATIO/
# SORT_NONEを追加で試したところ、同じケースでSORT_DIFF・SORT_LSIDE・
# SORT_NONEのいずれも本来の1段構成(布ロス率0.20前後)を見つけられることを
# 確認した(詳細はtests/test_nesting.py・READMEの実測値参照)。
# `_best_of`は既に「試した候補の中で布ロス率が最小のものを採用する」設計
# のため、候補を追加しても既存のケースの結果が悪化することは無い
# (追加した候補が既存より劣っていても単に採用されないだけ)。実際に計測した
# ところ、7種類全てを試しても1リクエストあたりの処理時間への影響は誤差の
# 範囲内だった(rectpackの矩形パッキング自体が非常に高速なため)。この
# 安全性(悪化しない)と低コストから、rectpackが提供する並べ替え戦略を
# 全種類候補に加えることにした。
_SORT_ALGO_CANDIDATES = (
    SORT_AREA, SORT_PERI, SORT_DIFF, SORT_SSIDE, SORT_LSIDE, SORT_RATIO, SORT_NONE,
)


def _rotate90_points(points: list[Point]) -> list[Point]:
    """90度回転 (x, y) -> (-y, x)。svgpath.rotate_segments_90 と同じ変換。"""
    return [(-y, x) for x, y in points]


def _bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _flip_180_points(points: list[Point], center: Point) -> list[Point]:
    """centerを基準に180度回転(点対称)する: (x,y) -> (2cx-x, 2cy-y)。

    90度回転(_rotate90_points)と違い、幅・高さは変わらない(det=+1の
    真の回転であり、鏡映(裏返し)ではない)ので、生地の縦地方向を示す
    布目線は常に垂直のまま保たれる(矢印の向きだけ逆になる)。ニット等
    以外の一般的な生地でも安全に使える回転として、90度回転
    (allow_rotation=Trueの時だけ許可)とは別に、既定でも使う。
    """
    cx, cy = center
    return [(2 * cx - x, 2 * cy - y) for x, y in points]


@dataclass
class NestedPart:
    part: FinalizedPart
    x: float
    y: float
    rotated: bool
    # 180度回転(点対称)で配置しているか。90度回転(rotated)と違い常に
    # 布目安全なので、allow_rotationの設定に関係なく使える
    # (engine.nesting._compact_placement 参照)。
    flipped: bool = False

    def _flip_center(self) -> Point:
        min_x, min_y, max_x, max_y = _bbox(self.part.cut_line)
        return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    def _place(self, points: list[Point], shift: tuple[float, float]) -> list[Point]:
        pts = _flip_180_points(points, self._flip_center()) if self.flipped else points
        pts = _rotate90_points(pts) if self.rotated else pts
        pts = [(px - shift[0], py - shift[1]) for px, py in pts]
        return [(px + self.x, py + self.y) for px, py in pts]

    def _shift(self) -> tuple[float, float]:
        """cut_line(縫い代込みの裁断線)のローカル原点を rectpack が想定する
        矩形の左上(0,0)に揃えるためのオフセット。

        offset_polygon は元のテンプレート座標系(左上が概ね(0,0))から外側に
        膨らむため、cut_line のバウンディングボックス最小値は(0,0)ではない
        (縫い代の分だけ負の値になる)。回転する場合はさらに座標系が変わる。
        どちらの場合も、cut_line 自身のバウンディングボックス最小値を引く
        ことで、パーツ全体（縫い線・合印・布目線を含む）を rect.x, rect.y に
        正しく揃えて配置できる。
        """
        pts = self.part.cut_line
        if self.flipped:
            pts = _flip_180_points(pts, self._flip_center())
        pts = _rotate90_points(pts) if self.rotated else pts
        min_x, min_y, _, _ = _bbox(pts)
        return (min_x, min_y)

    def placed_cut_line(self) -> list[Point]:
        return self._place(self.part.cut_line, self._shift())

    def placed_stitch_line(self) -> list[Point]:
        return self._place(self.part.stitch_line, self._shift())

    def placed_notches(self) -> list[tuple[Point, Point]]:
        shift = self._shift()
        return [(self._place([a], shift)[0], self._place([b], shift)[0])
                for a, b in self.part.notches]

    def placed_grainline(self) -> dict:
        shift = self._shift()
        line = self.part.grainline["line"]
        arrows = self.part.grainline["arrows"]
        return {
            "line": (self._place([line[0]], shift)[0], self._place([line[1]], shift)[0]),
            "arrows": [(self._place([a], shift)[0], self._place([b], shift)[0]) for a, b in arrows],
        }

    def bbox(self) -> tuple[float, float, float, float]:
        return _bbox(self.placed_cut_line())


@dataclass
class NestingResult:
    placed: list[NestedPart]
    unplaced: list[FinalizedPart]
    fabric_width_cm: float
    used_length_cm: float
    waste_ratio: float
    total_part_area_cm2: float = field(default=0.0)


def _pack_once(parts: list[FinalizedPart], fabric_width_cm: float, seam_gap_cm: float,
                allow_rotation: bool, pack_algo, sort_algo) -> NestingResult:
    packer = newPacker(pack_algo=pack_algo, sort_algo=sort_algo, rotation=allow_rotation)
    # ビンの長さは「全パーツを縦に積んでも収まる」十分な長さを仮に確保し、
    # 実際に使われた高さだけを後で used_length_cm として計測する。
    max_length = sum(p.height_cm for p in parts) + sum(p.width_cm for p in parts) + 200.0
    packer.add_bin(fabric_width_cm, max_length, count=1)

    for i, part in enumerate(parts):
        packer.add_rect(part.width_cm + seam_gap_cm, part.height_cm + seam_gap_cm, rid=i)
    packer.pack()

    placed_by_rid = {}
    for abin in packer:
        for rect in abin:
            placed_by_rid[rect.rid] = rect

    placed: list[NestedPart] = []
    unplaced: list[FinalizedPart] = []
    used_length = 0.0
    total_part_area = 0.0

    for i, part in enumerate(parts):
        rect = placed_by_rid.get(i)
        if rect is None:
            unplaced.append(part)
            continue
        # rectpackのRect自体は「回転したか」を明示的には返さない(rect.width/
        # rect.heightのみ)ため、元の(幅+隙間)と比較して回転を推定している。
        # 既知の限界: パーツのバウンディングボックスの width_cm と height_cm が
        # (1e-3cm未満の差で)実質完全に一致する場合のみ、この推定は回転を
        # 検出できない。ただしそのように正方形なバウンディングボックスは
        # 回転前後で占有面積・向きが実質同じであり、配置の重なり等の実害は
        # 無い。単に見た目の縦横比が近い(例: sleeve の幅21cm/高さ23cm)
        # だけなら、回転後は明確にwidthの値が変わるため正しく検出できる。
        # 現状の全テンプレート型紙(標準M寸)がこの限界に該当しないことを
        # tests/test_nesting.py で確認している。
        original_w = part.width_cm + seam_gap_cm
        rotated = abs(float(rect.width) - original_w) > 1e-3
        placed.append(NestedPart(part=part, x=float(rect.x), y=float(rect.y), rotated=rotated))
        used_length = max(used_length, float(rect.y) + float(rect.height))
        total_part_area += part.width_cm * part.height_cm

    fabric_area = fabric_width_cm * used_length if used_length else 0.0
    waste_ratio = 1.0 - (total_part_area / fabric_area) if fabric_area else 0.0
    return NestingResult(
        placed=placed,
        unplaced=unplaced,
        fabric_width_cm=fabric_width_cm,
        used_length_cm=used_length,
        waste_ratio=max(0.0, waste_ratio),
        total_part_area_cm2=total_part_area,
    )


def _polygon_of(cut_line: list[Point]) -> _ShapelyPolygon:
    pts = cut_line[:-1] if cut_line and cut_line[0] == cut_line[-1] else cut_line
    return _ShapelyPolygon(pts)


def _clear_of_all(candidate_poly: _ShapelyPolygon, others: list[_ShapelyPolygon],
                   gap_cm: float) -> bool:
    buffered = candidate_poly.buffer(gap_cm / 2.0)
    return not any(buffered.intersects(other) for other in others)


_SLIDE_MAX_ITERATIONS = 24
_SLIDE_TOLERANCE_CM = 0.02


def _slide_min_x(part: FinalizedPart, y: float, flip: bool, x_hi: float,
                  others: list[_ShapelyPolygon], gap_cm: float
                  ) -> tuple[float, _ShapelyPolygon] | None:
    """指定のy・反転状態で、x_hi(既知の配置可能なx)より左に、実ポリゴンの
    重なり判定を使って二分探索でどこまで詰められるかを探す。

    これが「台形(スカート等)やカーブした袖が、外接矩形の隙間に実際に
    どこまで入り込めるか」を確かめる核心部分。単に他パーツのbbox境界を
    候補点にするだけでは、この「実際に触れ合うところまで詰める」動きを
    再現できない。
    """
    def poly_at(x: float) -> _ShapelyPolygon:
        trial = NestedPart(part=part, x=x, y=y, rotated=False, flipped=flip)
        return _polygon_of(trial.placed_cut_line())

    poly_hi = poly_at(x_hi)
    if not _clear_of_all(poly_hi, others, gap_cm):
        return None  # このy・反転状態では、既知の配置(x_hi)すら成立しない

    lo, hi = 0.0, x_hi
    poly_lo = poly_at(lo)
    if _clear_of_all(poly_lo, others, gap_cm):
        return (lo, poly_lo)  # 原点まで詰めても重ならない(最良)

    best_poly = poly_hi
    for _ in range(_SLIDE_MAX_ITERATIONS):
        mid = (lo + hi) / 2.0
        poly_mid = poly_at(mid)
        if _clear_of_all(poly_mid, others, gap_cm):
            hi, best_poly = mid, poly_mid
        else:
            lo = mid
        if hi - lo < _SLIDE_TOLERANCE_CM:
            break
    return (hi, best_poly)


def _compact_once(result: NestingResult, seam_gap_cm: float,
                   order: list[int] | None = None) -> NestingResult:
    """rectpackのbbox配置結果を、実ポリゴン(縫い代込みの裁断線)ベースで
    詰め直す軽量な圧縮パスを、指定した処理順で1回だけ行う。

    本格的な不定形ネスティング(NFP: no-fit-polygon)そのものはこのプロジェクト
    の規模を超える研究レベルの課題であり実装していない(モジュールdocstring
    参照)。代わりに、各パーツを「現在のbbox配置より原点(0,0)側に寄せられる
    余地が実ポリゴンの重なり判定で確認できるか」を貪欲に試す、範囲を絞った
    後処理を行う。180度回転(180度回転は常に布目安全)を組み合わせることで、
    台形(スカート等)やカーブした袖のように、外接矩形には収まらない
    「本来空いている隙間」を一部埋められる。

    Args:
        order: どの順で各パーツを「先に詰める権利」を与えるかを指定する
            パーツindexの並び。Noneなら従来通り(y,x)の昇順(round5より
            `_compact_placement`が複数の順序を試すようになったため、
            外から指定できるように分離した。詳細は`_compact_placement`
            のdocstring参照)。

    安全性:
      - 各パーツは「現在位置と同じか、それより原点に近い(y,x)」しか候補に
        しないため、この処理単体で使用生地丈(used_length_cm)が悪化する
        ことは無い。
      - 全パーツを詰め直した後、実ポリゴン同士が重なっていないかを再検証
        する。想定外の重なりや、集計結果が悪化した場合は、圧縮を諦めて
        引数で渡された元の配置(result)をそのまま返す(fail-safe)。
    """
    placed = result.placed
    n = len(placed)
    if n < 2 or n > _COMPACTION_MAX_PARTS:
        return result

    if order is None:
        order = sorted(range(n), key=lambda i: (placed[i].y, placed[i].x))
    accepted_polys: list[_ShapelyPolygon] = []
    new_placed: list[NestedPart | None] = [None] * n

    for idx in order:
        original = placed[idx]

        if original.rotated:
            # 90度回転済みのパーツは、既にrectpack側の探索結果を尊重し
            # 圧縮の対象にしない(90度回転+180度反転の組み合わせまで検証
            # 範囲を広げると、安全性の見通しが悪くなるため)。
            new_placed[idx] = original
            accepted_polys.append(_polygon_of(original.placed_cut_line()))
            continue

        y_candidates = sorted(
            {0.0, original.y} | {b for poly in accepted_polys for b in (poly.bounds[1], poly.bounds[3])}
        )
        y_candidates = [y for y in y_candidates if y <= original.y][:_COMPACTION_MAX_CANDIDATES_PER_AXIS]

        best = None  # (y, x, flipped, poly)
        for cand_y in y_candidates:
            for flip in (False, True):
                slid = _slide_min_x(original.part, cand_y, flip, original.x, accepted_polys, seam_gap_cm)
                if slid is None:
                    continue
                cand_x, poly = slid
                key = (cand_y, cand_x)
                if best is None or key < (best[0], best[1]):
                    best = (cand_y, cand_x, flip, poly)
            if best is not None and best[0] == cand_y:
                # yはこれ以上小さくならない(候補は昇順に見ている)ので、
                # このyで見つかった時点で確定させて良い。
                break

        if best is not None and (best[0], best[1]) < (original.y, original.x):
            cand_y, cand_x, flip, poly = best
            new_placed[idx] = NestedPart(part=original.part, x=cand_x, y=cand_y,
                                          rotated=False, flipped=flip)
            accepted_polys.append(poly)
        else:
            new_placed[idx] = original
            accepted_polys.append(_polygon_of(original.placed_cut_line()))

    finalized: list[NestedPart] = [p for p in new_placed if p is not None]
    if len(finalized) != n:
        return result  # 想定外(何かが埋まっていない)。安全側に倒す。

    # 安全確認: 圧縮後、実ポリゴン同士が(縫い代の隙間を除いて)重なっていないか
    # 全ペアを再検証する。
    final_polys = [_polygon_of(p.placed_cut_line()) for p in finalized]
    for i in range(len(final_polys)):
        for j in range(i + 1, len(final_polys)):
            overlap = final_polys[i].buffer(-1e-6).intersection(final_polys[j].buffer(-1e-6))
            if overlap.area > 1e-6:
                return result  # 想定外の重なりを検出。安全側に倒して元の配置を返す。

    used_length = max((p.bbox()[3] for p in finalized), default=0.0)
    fabric_area = result.fabric_width_cm * used_length if used_length else 0.0
    waste_ratio = max(0.0, 1.0 - (result.total_part_area_cm2 / fabric_area) if fabric_area else 0.0)

    if used_length > result.used_length_cm + 1e-6 or waste_ratio > result.waste_ratio + 1e-6:
        return result  # 圧縮のはずが悪化した(想定外)。安全側に倒す。

    return NestingResult(
        placed=finalized,
        unplaced=result.unplaced,
        fabric_width_cm=result.fabric_width_cm,
        used_length_cm=used_length,
        waste_ratio=waste_ratio,
        total_part_area_cm2=result.total_part_area_cm2,
    )


# round5「ネスティングの改善」で追加。本格的なNFP(no-fit-polygon)ネスティング
# は引き続きスコープ外だが、既存の単発の圧縮パス(_compact_once、旧
# _compact_placement)には2つの限界があった:
#   (1) 1回のパスで処理順(y,xの昇順)を固定していたため、後ろの順番の
#       パーツが動いた結果できる新しい隙間を、既に処理済みの前の方の
#       パーツが利用する機会が無かった。
#   (2) 常に同じ処理順(位置の昇順)しか試しておらず、実際のビンパッキング
#       でよく使われる「大きい(=後から入れにくい)パーツを先に確定させる」
#       という別の妥当な戦略を試していなかった。
# これらはどちらも「揺すり直す(re-settle)」「複数の戦略を試して良い方を
# 採る」という、既存のrectpack側の複数アルゴリズム探索(_PACK_ALGO_CANDIDATES
# 等)と同じ思想の延長であり、本格的なNFPの実装(輪郭同士のno-fit-polygonを
# 厳密に計算する)とは別物である点は変わらない。
_COMPACTION_MAX_PASSES = 3


def _position_order(placed: list[NestedPart]) -> list[int]:
    """現在の配置位置(y昇順、同じyならx昇順)でパーツindexを並べる。

    従来からの既定の処理順。原点に近いパーツから先に「その場所を確保する
    権利」を与える、素朴だが安定した順序。
    """
    return sorted(range(len(placed)), key=lambda i: (placed[i].y, placed[i].x))


def _largest_area_first_order(placed: list[NestedPart]) -> list[int]:
    """バウンディングボックス面積が大きいパーツから先に処理する順序。

    ビンパッキングの一般的な経験則(大きい荷物ほど後から隙間を見つけにくい
    ため先に確定させる)を、この圧縮パスにもそのまま適用したもの。
    """
    return sorted(range(len(placed)),
                  key=lambda i: -(placed[i].part.width_cm * placed[i].part.height_cm))


def _compact_repeatedly(result: NestingResult, seam_gap_cm: float, order_fn) -> NestingResult:
    """`_compact_once`を、これ以上改善しなくなるか上限回数に達するまで
    繰り返し適用する。

    1回のパスで一部のパーツが動くと、その新しい配置に対して`order_fn`を
    もう一度適用した処理順は、前回とは変わりうる(動いたパーツの位置が
    ソートキーに使われるため)。これにより、前のパスでは処理順の都合で
    見送られた「さらに詰められる余地」を後続のパスが拾えることがある
    (「一度揺すって落ち着かせる」ような動き)。`_compact_once`自体は
    呼び出し1回ごとに独立してfail-safe(その回の入力より悪化しない)なので、
    何回繰り返しても結果が単調に改善するか変化しないかのどちらかにしかならず、
    このループ自体が安全性を損なうことは無い。
    """
    current = result
    for _ in range(_COMPACTION_MAX_PASSES):
        order = order_fn(current.placed)
        nxt = _compact_once(current, seam_gap_cm, order=order)
        no_change = (abs(nxt.used_length_cm - current.used_length_cm) < 1e-6
                     and abs(nxt.waste_ratio - current.waste_ratio) < 1e-6)
        current = nxt
        if no_change:
            break
    return current


def _compact_placement(result: NestingResult, seam_gap_cm: float) -> NestingResult:
    """圧縮パスの入口。複数の処理順それぞれについて`_compact_repeatedly`
    (収束するまでの反復)を行い、その中で最も布ロス率が低い結果を返す。

    **正直な実測結果（過大評価しないための記録）**: 実際に、標準M寸の
    様々な衣装スペック(単体の型紙3〜6枚程度の一般的な組み合わせから、
    8種類のパーツ種を混在させた36枚までの合成テストケースまで)で、
    「単発の圧縮パス(_compact_once、旧`_compact_placement`)」と
    「この反復+複数処理順版」を比較したところ、**ほとんどの組み合わせで
    追加の改善は数値上ゼロだった**(`tests/test_nesting.py`の
    `test_iterative_and_multi_order_compaction_rarely_beats_a_single_pass`
    参照)。理由を調べたところ、rectpackの初期配置+単発の圧縮パスの時点で
    既にこの「貪欲に原点側へ寄せる」という手法が到達できる局所最適に
    達してしまっており、処理順を変えても最終的に見つかる詰め方が同じに
    収束することが多いためだとわかった。

    調査の過程で、単純な処理順の変更よりもっと積極的な手法(乱数による
    パーツペアの入れ替えを何十回も試す局所探索)も試作して測定したところ、
    ごく一部のケース(16パーツの合成テストの一部)で単発の圧縮パスより
    0.3〜0.5ポイント程度小さい布ロス率が見つかることはあったが、
    (1)効果が乱数のシード・具体的なパーツ構成に大きく左右され安定した
    改善とは言えない、(2)60回の試行で1リクエストあたり数秒の追加処理時間
    がかかり、Webサービスの1回の生成リクエストに乗せるには割に合わない、
    という2点から、その手法は本番コードには採用しなかった(正直な判断として
    ここに記録する)。

    結果として、この関数が実際に行っているのは「処理順を2通り(位置の昇順、
    面積の大きい順)試し、それぞれ収束するまで数回繰り返す」という、
    計算コストの低い範囲に留めた拡張であり、本格的なNFPは元より、上記の
    局所探索ほど積極的な最適化でもない。**単発の圧縮パスより悪化することは
    無いという安全性は保証されるが、実際の改善量は多くの場合ゼロに近い**
    という実測結果を、誇張せずそのまま書き残しておく。
    """
    n = len(result.placed)
    if n < 2 or n > _COMPACTION_MAX_PARTS:
        return result

    candidates = [
        _compact_repeatedly(result, seam_gap_cm, _position_order),
        _compact_repeatedly(result, seam_gap_cm, _largest_area_first_order),
    ]
    return min(candidates, key=lambda r: r.waste_ratio)


def nest_parts(parts: list[FinalizedPart], fabric_width_cm: float = 150.0,
               seam_gap_cm: float = DEFAULT_SEAM_GAP_CM,
               allow_rotation: bool = False) -> NestingResult:
    """パーツ群を1本の生地上に自動配置する。

    複数の詰め込みアルゴリズム/並べ替え順を試し、配置できたパーツが最も多く、
    その中で布ロス率が最も低い結果を選ぶ（布目方向は変えない前提での省ロス探索）。

    Args:
        parts: seam.finalize_part() で作った、縫い代込みのパーツ群。
        fabric_width_cm: 生地の幅（110cm / 150cm が主要規格）。
        seam_gap_cm: パーツ間に開ける最小の隙間（裁断時に干渉しないための余白）。
        allow_rotation: 90度回転配置を許可するか。既定はFalse(布目安全)。
            Trueにすると布ロスは減らせるが、回転したパーツの布目が生地の縦地
            からズレる可能性がある（ニット等の非方向性生地でのみ推奨）。
    """
    if not parts:
        return NestingResult(placed=[], unplaced=[], fabric_width_cm=fabric_width_cm,
                              used_length_cm=0.0, waste_ratio=0.0)

    candidates = [
        _pack_once(parts, fabric_width_cm, seam_gap_cm, allow_rotation, pack_algo, sort_algo)
        for pack_algo, sort_algo in product(_PACK_ALGO_CANDIDATES, _SORT_ALGO_CANDIDATES)
    ]
    best = _best_of(candidates, key=lambda r: r.waste_ratio)
    # 圧縮は「圧縮前の布ロス率が最良の候補」1件だけに適用する。round11で
    # 同点の候補もまとめて圧縮する改良を入れたが、round12でテンプレートの
    # 寸法を正した結果その効果がほぼ消えたため撤回した(モジュール
    # docstringの【round11での追加調査・改良】と【round12での撤回】参照)。
    return _compact_placement(best, seam_gap_cm)


def _best_of(results: list[NestingResult], key) -> NestingResult:
    """「全パーツを配置できた結果」を優先し、その中でkeyが最小のものを選ぶ。

    誰も全パーツを配置できなかった場合は、配置できなかった結果同士の中で
    keyが最小のものを選ぶ（配置漏れがある結果を、配置漏れが無い結果より
    優先することは絶対に無いようにする）。nest_parts()（アルゴリズム/
    ソート順の探索）とbest_fabric_width()（生地幅の探索）の両方が同じ
    「全配置優先→keyで最小化」という選択基準を使うため、以前はこの基準が
    2箇所にほぼ同じ形でコピーされており、片方だけ修正すると基準が
    ズレる恐れがあった。
    """
    fully_placed = [r for r in results if not r.unplaced]
    pool = fully_placed or results
    return min(pool, key=lambda r: (len(r.unplaced), key(r)))


def best_fabric_width(parts: list[FinalizedPart],
                       candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                       **kwargs) -> NestingResult:
    """複数の生地幅候補でネスティングを試し、布ロス率が最も低い結果を返す。

    nest_parts()自体が「詰め込みアルゴリズム3種×並べ替え順2種」を内部で
    総当たりするため、このbest_fabric_widthはさらにその外側で「生地幅」を
    総当たりする2段目の探索になる（既定では3×2×2=12通りのrectpack実行）。
    """
    results = [nest_parts(parts, fabric_width_cm=w, **kwargs) for w in candidates]
    return _best_of(results, key=lambda r: r.waste_ratio)
