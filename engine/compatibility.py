"""compatibility.py — パーツ間の縫い合わせ長さの整合性チェック(round6で追加)。

このプロジェクトは各part_type(front_bodice/skirt/waistband等)を独立に
体型スケーリング・ダーツ追加している(engine/scaling.py・engine/darts.py参照。
PART_SCALE_RULESの通り、パーツごとに異なる採寸項目の比率で幅・丈を変形する)。
この「パーツごとに独立」という設計は実装をシンプルに保てる一方、
実際に縫い合わされる2つの辺(例: 前身頃の脇線と後ろ身頃の脇線、
スカートのウエストラインとウエストバンド)が、スケーリングやダーツの
結果として異なる長さになってしまう可能性を作り込みやすい、という
副作用がある。このモジュールは、生成済みの`FinalizedPart`(engine/seam.py)
の輪郭(`stitch_line`)から実際の縫い合わせ辺の長さを幾何的に測り、
組み合わせるはずの2辺の長さが一定以上ずれている場合に警告として報告する。

できること:
  - 前身頃(front_bodice / front_bodice_zip_panel)と後ろ身頃(back_bodice)の
    脇線の長さ比較(ダーツで摘まれた分を差し引いた「縫い閉じた後の長さ」で
    比較する)。
  - スカート(skirt)のウエストラインとウエストバンド(waistband)の長さ比較。
  - パンツ(front_pants/back_pants)のウエストラインとウエストバンドの
    長さ比較。
  - 袖(sleeve)の袖口とカフス(cuffs)の長さ比較。
  - 身頃の首ぐりと衿(collar)の長さ比較(round15で追加)。
  帯状パーツ(衿/カフス/ウエストバンド)の長さは、round15から外接矩形の幅では
  なく**実際に相手へ縫い付けられる辺**の長さで測る(`seam_edge_length`)。
  襟先やボタンタブは左右へ張り出すため、両者は最大30%ずれる。
  - 前身頃(front_bodice)+後ろ身頃(back_bodice)の袖ぐりと、袖(sleeve)の
    袖山カーブの長さ比較(round11で追加、round12で絶対値比較に改めた)。
    袖山は袖ぐりより「いせ込み」(SLEEVE_CAP_EASE_CM)の分だけ長いのが正常
    なので、その分を加えた期待値と比べる。パフ袖のようにデザイン上さらに
    大きくギャザーを寄せる袖は、SLEEVE_CAP_DESIGN_GATHER_CMで追加分を
    見込む。

できないこと(正直な範囲の限定):
  - あくまで「境界線の長さ」という1次元の量の比較であり、形状(カーブの
    曲率、ノッチ位置等)の整合性までは見ていない。長さが一致していても
    縫い合わせたときに形が合わない可能性は別途ある。
  - (round15で対応)首ぐり(ネックライン)と衿(collar)の長さ比較。round14までは
    「どの辺がネックラインかを汎用的に検出するのが難しい」という理由で
    見送っていたが、身頃の輪郭では**y座標が最小になる点がちょうど左右の
    首の付け根の2点だけ**になる(肩先は肩下がりのぶん下にあり、首ぐりは
    そこから下へ落ち込む)という性質を使えば、ネックライン形状に依存せず
    測れることが分かった(`neckline_length`)。残る限定は2つ:
    タートルネックは首ぐり自体が台襟なので測る対象が無い(衿との併用は
    `build_garment_spec`が拒否する)。前開きの片側パネル
    (front_bodice_zip_panel)は見返しの張り出しがあり、y最小の点が1つしか
    現れないため測れない(この場合、衿は従来通り採寸比で作られる)。
  - 縫い代(seam_allowance)を含めた裁断線(cut_line)ではなく、縫い線
    (stitch_line、縫い代を含まない完成線)同士の長さを比較している。
    これは「実際に縫い合わされる位置」を比較するという目的に対して
    正しい選択だが、縫い代の付け方(辺ごとに異なる縫い代幅機能等)に
    誤りがあっても、このチェッカーでは検出できない。
  - round7で、waistband/cuffsを独立した採寸比率ではなく相手パーツ
    (skirt/pants/sleeve)の実際の縫い線長さに合わせて変形する方式
    (engine/scaling.pyの`scale_band_to_target_width`、engine/pipeline.pyの
    `_waistband_target_width_cm`/`_cuffs_target_width_cm`参照)に変更した
    ことで、上記の「テンプレート同士の基準寸法が独立で揃わない」という
    根本原因そのものは解消した。ただし、ウエストバンドはボタン/ホック等の
    「打ち合わせ分」(WAISTBAND_CLOSURE_EASE_CM)だけ、カフスも同様に開閉の
    ゆとり分(CUFFS_EASE_CM)だけ、意図的に相手パーツより長く作る。これは
    実際の洋裁でも通常そうする(バンドがスカートの開き寸法と完全に同じ
    長さだと、閉じたときにきつすぎて着脱できない)。このチェッカーは
    その意図的な差分を「不整合」と誤判定しないよう、比較対象の期待値に
    あらかじめこのゆとり分を加えてから許容誤差判定を行う。
  - front_bodice_zip_panel(前開き用の片側パネル)の袖ぐりは、袖山との
    比較対象に含めていない。zip_panelの輪郭はshapelyの半平面交差
    (scripts/generate_templates.pyの`_front_zip_panel_d`)で幾何的に
    再構成されており、front_bodice/back_bodiceのような「輪郭の先頭点が
    必ず肩先になる」という規則が保証されないため、`armhole_length`の
    検出方法(輪郭の先頭から脇線までを辿る)を安全に適用できない。
  - 袖山と袖ぐりの比較は、あくまで「長さ」の比較である。実際の縫い付け
    では、いせ込みを袖山のどの範囲に配分するか(通常は前後の肩寄りに多く、
    脇の下には入れない)まで指定して初めて意図通りの丸みが出るが、
    そこまでは見ていない。
"""

from __future__ import annotations
from dataclasses import dataclass
from math import hypot

# ウエストバンドがスカート/パンツのウエスト開き寸法より意図的に長く作られる
# 打ち合わせ分(ボタン/ホック等の重なり)。engine/scaling.pyの
# `scale_band_to_target_width`とengine/pipeline.pyの
# `_waistband_target_width_cm`が、実際にウエストバンドをこの分だけ長く
# 生成する際にも同じ定数を使う(単一の真実の情報源として、値の重複定義を
# 避けるためここに置き、pipeline.py側はここからimportする)。
WAISTBAND_CLOSURE_EASE_CM = 3.0
#: カフスが袖口より意図的に長く作られる開閉のゆとり分。上記と同様の理由で
#: ここを真実の情報源とする。
CUFFS_EASE_CM = 2.0

#: 袖山カーブが袖ぐりより意図的に長く作られる「いせ込み」の量(cm)。
#:
#: 洋裁では、袖山を袖ぐりよりわずかに長く作り、その差を縮めながら縫い付ける
#: ことで肩先の丸みを出す(布帛で1.5〜3cm程度)。袖テンプレートはこの値を
#: 見込んだ寸法で作られている(scripts/generate_templates.pyの袖の節参照)ため、
#: このチェッカーも期待値にこの分を加えてから比較する。
SLEEVE_CAP_EASE_CM = 2.0

#: 上記のいせ込みとは別に、デザイン上わざと大きくギャザーを寄せる袖の、
#: 追加のギャザー分(cm)。パフ袖は袖山を袖ぐりよりかなり大きく作り、縮めて
#: 付けることで膨らみを出すため、これを「不整合」と誤判定しないよう
#: 期待値に加える(scripts/generate_templates.pyのパフ袖の定義と対の値)。
SLEEVE_CAP_DESIGN_GATHER_CM = {
    # パフ袖の袖山は袖ぐりより合計約9cm長い。うち2cmは上のいせ込み分なので、
    # 「デザイン上の追加ギャザー」としてはその差の約7cmになる
    # (この値は実測して決めた。当初9.0と書いていたが、いせ込み分を二重に
    #  数えていることをテストが検出した)。
    "puff": 7.0,
}

#: 【round11→round12の経緯】round11時点では、この比較を「基準体型で実測した
#: 比率からの乖離」で行っていた。当時は袖テンプレートの袖山カーブが袖ぐりより
#: 14cm以上短く(袖ぐり36.2cmに対し袖山22.1cm)、絶対値で比べると袖を含む生成の
#: ほぼ全てで警告が出てしまうため、比率で誤魔化さざるを得なかったからである。
#: round12で袖テンプレート自体を作り直し、袖山カーブが袖ぐり+いせ込みに
#: 一致するようにしたので、この比較は本来あるべき絶対値の比較に戻した。
#: 比率ベースの判定(_ARMHOLE_TO_CAP_BASELINE_RATIO)は役目を終えたため削除。

# 実測値の丸め誤差を吸収するための座標比較の許容誤差(cm)。
_COORD_TOL = 1e-2
# 脇線候補とみなす、垂直な辺の最小の縦方向の長さ(cm)。これより短い辺は
# ノイズ(角の面取り等)とみなして無視する。
_MIN_VERTICAL_RUN_CM = 5.0
# front_bodice_zip_panelのような非対称パーツで、2本の垂直候補のうち
# どちらが「外側の脇線」でどちらが「中心前(CF)/見返しの縁」かを判定する
# ための、両者のy方向の到達点(y_top)の差の閾値(cm)。差がこれ未満なら
# 「左右対称な2本の本物の脇線」(front_bodice/back_bodiceのケース)とみなし
# 両方を合算する。差がこれ以上ならCF/見返し側を除外する
# (engine/darts.pyの`_bust_dart_zip_panel_side_index`と同じ判定軸)。
_CF_VS_SIDE_YTOP_DIFF_CM = 3.0
# 2辺の長さが「一致している」とみなす許容誤差。絶対値・相対値のうち
# 大きい方を実際の許容誤差として使う(小さいパーツでは絶対値が、大きい
# パーツでは相対値が支配的になるようにするため)。
_ABS_TOLERANCE_CM = 1.5
_REL_TOLERANCE = 0.05
# 帯状パーツの「縫い付けられる辺」が、外接矩形の幅に対して最低限占めるはずの
# 割合(`seam_edge_length`参照)。実測では最小がconvertible_collarの0.70。
_MIN_SEAM_EDGE_SPAN_RATIO = 0.5


@dataclass(frozen=True)
class CompatibilityWarning:
    kind: str
    message: str
    expected_cm: float
    actual_cm: float

    @property
    def diff_cm(self) -> float:
        return abs(self.expected_cm - self.actual_cm)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "message": self.message,
            "expected_cm": round(self.expected_cm, 1),
            "actual_cm": round(self.actual_cm, 1),
            "diff_cm": round(self.diff_cm, 1),
        }


def _closed_points(stitch_line: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """stitch_lineを、最初と最後が同じ点になるよう閉じたリストとして返す。

    `engine.svgpath.segments_to_polyline`が返す点列は、パスが明示的に
    始点へ戻るセグメントを含んでいれば既に閉じているが、そうでない場合に
    備えて末尾に始点を補う(以降の「隣接する2点」の走査で、最後の点から
    最初の点への辺を取りこぼさないようにするため)。
    """
    if not stitch_line:
        return stitch_line
    if stitch_line[0] == stitch_line[-1]:
        return list(stitch_line)
    return list(stitch_line) + [stitch_line[0]]


def _sum_length_at(points: list[tuple[float, float]], axis: int, target: float,
                    tol: float = _COORD_TOL) -> float:
    """閉じた点列の各辺(隣接2点)のうち、両端点のaxis番目の座標が
    targetにtol以内で一致するものだけを対象に、もう一方の軸方向の長さを
    合計する。

    axis=0(x座標一致)なら「縦方向の辺(脇線)」の長さ合計、axis=1
    (y座標一致)なら「横方向の辺(ウエストライン・裾・袖口)」の長さ合計に
    使う。ダーツのV字ノッチは、口(mouth)の2点はちょうどtargetの直線上に
    あるが、先端(tip)へ向かう2本の斜め辺はtargetからずれるため自動的に
    除外される。結果として、この合計は「ダーツを縫い閉じた後に実際に
    残る辺の長さ」に一致する。
    """
    total = 0.0
    n = len(points)
    if n < 2:
        return total
    other = 1 - axis
    for i in range(n - 1):
        p1 = points[i]
        p2 = points[i + 1]
        if abs(p1[axis] - target) <= tol and abs(p2[axis] - target) <= tol:
            total += abs(p2[other] - p1[other])
    return total


def _sum_length_at_x(points: list[tuple[float, float]], x: float,
                      tol: float = _COORD_TOL) -> float:
    return _sum_length_at(points, axis=0, target=x, tol=tol)


def _sum_length_at_y(points: list[tuple[float, float]], y: float,
                      tol: float = _COORD_TOL) -> float:
    return _sum_length_at(points, axis=1, target=y, tol=tol)


def _group_by_proximity(values: list[float], tol: float) -> list[list[float]]:
    """1次元の値のリストを、隣接値との差がtol以内なら同じグループにまとめる。

    「四捨五入したグリッドに丸める」方式だと、たまたま境界付近の値が
    隣接グリッドに分かれてしまう罠があるため、ソート後に逐次比較する
    素朴な方式にしている(候補点数は実際には数個程度なのでO(n log n)で十分)。
    """
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and abs(groups[-1][-1] - v) <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def side_seam_length(part) -> float | None:
    """前身頃/後ろ身頃(front_bodice・front_bodice_zip_panel・back_bodice)の
    脇線の長さ(ダーツを縫い閉じた後の実際の長さ)を求める。

    front_bodice/back_bodiceは左右対称で、脇線が2本ある想定。
    front_bodice_zip_panelは非対称で、輪郭上には「外側の脇線」と
    「中心前(CF)/見返しの縁」の2本の長い垂直候補があるが、後者は
    脇線ではないため除外する必要がある。両者はy方向の到達点(y_top)の
    差(_CF_VS_SIDE_YTOP_DIFF_CM超か否か)で区別する
    (engine/darts.pyの`_bust_dart_zip_panel_side_index`と同じ判定軸)。

    【round12で加えた条件】脇線は必ずパーツの左右いずれかの端(x座標が最小
    または最大)にある。round12でスクエアネックの首ぐりを引き直した際、
    その縦の辺(深さ5.8cm)が「十分に長い縦線」の条件を満たしてしまい、
    首ぐりの2辺まで脇線候補に数えられて候補4本→判定不能(None)になる、
    という不具合が実際に起きた。長さのしきい値を上げて誤魔化すのではなく、
    「脇線はパーツの端にある」という本来の性質を条件に加えて区別する
    (首ぐりはパーツの内側にあるので確実に除外できる)。

    想定外の形状(垂直候補が0本、または3本以上見つかった等)の場合は
    Noneを返し、呼び出し側で安全側に倒す(警告を出さない)。
    """
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return None

    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)

    candidate_xs: list[float] = []
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        if abs(x1 - x2) > _COORD_TOL or abs(y2 - y1) < _MIN_VERTICAL_RUN_CM:
            continue
        x_mid = (x1 + x2) / 2.0
        # パーツの左端・右端のいずれかに乗っている縦線だけを脇線候補とする。
        if min(abs(x_mid - min_x), abs(x_mid - max_x)) > _COORD_TOL:
            continue
        candidate_xs.append(x_mid)

    if not candidate_xs:
        return None

    groups = _group_by_proximity(candidate_xs, tol=0.5)
    clusters = []
    for group in groups:
        x_repr = sum(group) / len(group)
        total = _sum_length_at_x(points, x_repr, tol=_COORD_TOL)
        ys_at_x = [p[1] for p in points[:-1] if abs(p[0] - x_repr) <= 0.5]
        y_top = min(ys_at_x) if ys_at_x else None
        clusters.append((x_repr, total, y_top))

    if len(clusters) == 1:
        return clusters[0][1]

    if len(clusters) == 2:
        (_, len_a, ytop_a), (_, len_b, ytop_b) = clusters
        if ytop_a is None or ytop_b is None:
            return None
        if abs(ytop_a - ytop_b) > _CF_VS_SIDE_YTOP_DIFF_CM:
            # 非対称: y_topが大きい方(=ネックラインから遠い方)が本物の脇線。
            return len_a if ytop_a > ytop_b else len_b
        # 対称: どちらも本物の脇線(front_bodice/back_bodiceの左右)なので合算する。
        return len_a + len_b

    return None  # 想定外の形状(候補が3本以上)。安全側に倒す。


def waist_opening_length(part) -> float:
    """スカート/パンツのウエストライン(上端)の開き寸法(ダーツ考慮後)を求める。"""
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return 0.0
    top_y = min(p[1] for p in points)
    return _sum_length_at_y(points, top_y)


def hem_or_wrist_opening_length(part) -> float:
    """袖の袖口(下端)の開き寸法(ダーツ考慮後)を求める。"""
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return 0.0
    bottom_y = max(p[1] for p in points)
    return _sum_length_at_y(points, bottom_y)


def _edge_length(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return hypot(p2[0] - p1[0], p2[1] - p1[1])


def armhole_length(part) -> float | None:
    """前身頃(front_bodice)/後ろ身頃(back_bodice)の袖ぐり(袖付け線)の
    合計弧長(左右両方)を求める(round11で追加)。

    `_bodice_path`(scripts/generate_templates.py)の構造上、front_bodice/
    back_bodiceの輪郭は必ず左肩先の点(M {shoulder_l} {body_shift})から
    始まり、
      左袖ぐりカーブ → 脇線(長い縦の辺) → 裾 → 脇線(長い縦の辺)
      → 右袖ぐりカーブ → 襟ぐり → (Zで先頭点に戻る)
    の順に並ぶ。左の袖ぐりは「輪郭の先頭から、実際の脇線が始まる点まで」
    として曖昧さ無く取り出せるため、まずこれを測る。

    脇線の判定は`side_seam_length`と同じ考え方を使う。単に「dxがほぼ0の
    辺」というだけでは、袖ぐりカーブの途中にある脇の下の短い接続辺
    (約4cm、_MIN_VERTICAL_RUN_CM未満)も条件を満たしてしまうため、
    その辺と同じx上にある辺の長さの合計(`_sum_length_at_x`。バストダーツで
    脇線が断片化していても、ダーツの斜め辺は除外して正しく合算される)が
    _MIN_VERTICAL_RUN_CM以上になって初めて「本物の脇線に到達した」と
    判定し、そこで走査を打ち切る。

    右の袖ぐりは個別には測っていない(襟ぐりの開始位置を汎用的に検出
    するのが難しいため。モジュールdocstring「できないこと」参照)。
    ただし`_bodice_path`は左右で同じshoulder_curve_x/y・underarm_yを使って
    カーブを生成しており左右対称なので、左の袖ぐりを2倍すればパーツ全体
    (左右合計)の袖ぐり長さになる。実際、全ネックラインで同じ値になること、
    ネックライン形状に依存しないことをテストで確認している。

    front_bodice_zip_panelには対応しない(輪郭の先頭点が肩先である保証が
    無いため。モジュールdocstring参照)。想定外の形状(脇線に到達しないまま
    輪郭を一周した等)ではNoneを返し、呼び出し側で安全側に倒す。
    """
    if part.part_type not in {"front_bodice", "back_bodice"}:
        return None
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return None

    total = 0.0
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        if abs(p1[0] - p2[0]) <= _COORD_TOL and abs(p2[1] - p1[1]) > _COORD_TOL:
            x_candidate = (p1[0] + p2[0]) / 2.0
            if _sum_length_at_x(points, x_candidate) >= _MIN_VERTICAL_RUN_CM:
                return total * 2.0
        total += _edge_length(p1, p2)

    return None  # 想定外の形状(脇線に到達しなかった)。


def sleeve_cap_length(part) -> float | None:
    """袖(sleeve)の袖山カーブ(身頃の袖ぐりに縫い付けられる側)の弧長を
    求める(round11で追加)。

    全ての袖テンプレート(pattern_templates/sleeve__*.svg、生成は
    scripts/generate_templates.py)は、輪郭が "M {x0} {y0} C ... C ..." と
    いう共通構造で始まり、袖山カーブの両端(袖山の左右の付け根)が同じy座標
    (y0)になるように作られている。この規約を使い、輪郭の先頭点(袖山の
    片端)から、再びy≈y0に戻る最初の点(袖山のもう片端)までの弧長を、
    ポリライン近似で合計する。

    想定外の形状(y0に戻る点が見つからない、点が少なすぎる等)ではNoneを
    返し、呼び出し側で安全側に倒す。
    """
    points = part.stitch_line
    if len(points) < 3:
        return None

    y0 = points[0][1]
    total = 0.0
    for i in range(1, len(points)):
        total += _edge_length(points[i - 1], points[i])
        if abs(points[i][1] - y0) <= _COORD_TOL:
            return total

    return None  # 想定外の形状(y0に戻る点が見つからなかった)。


#: 衿の首ぐり側の辺が、身頃の首ぐりに対して意図的に長く作られる分(cm)。
#:
#: ウエストバンド(打ち合わせ分3cm)やカフス(開閉のゆとり2cm)と違い、衿は
#: 首ぐりにぐるりと縫い付けられるだけで、閉じるための重なりを衿自身が
#: 持つわけではない(前開きの重なりは前身頃側の見返しが担う)。したがって
#: 縫い付け辺の長さは首ぐりと一致しているのが正しく、既定は0にしてある。
#: 「名前のある0」として置いているのは、将来ここに前立て分等を足す場合に
#: 生成側(engine/pipeline.py)と検査側(このモジュール)がずれないようにするため。
COLLAR_EASE_CM = 0.0

#: 首ぐりの長さを測れない身頃のバリエーション(部分一致で判定する)。
#:
#: タートルネックは首ぐりそのものが台襟(立ち上がり)になっていて、輪郭の
#: 最上端は「台襟の上端」という自由端であり、衿を縫い付ける首ぐり線では
#: ない。ここを首ぐりとして測ると台襟の上端(標準Mで13.7cm)を返してしまう
#: ため、明示的に対象外にする。
NECKLINE_UNMEASURABLE_VARIATIONS = ("turtle",)


def neckline_length(part) -> float | None:
    """前身頃/後ろ身頃の首ぐり(衿を縫い付ける辺)の弧長を求める(round15で追加)。

    `_bodice_path`(scripts/generate_templates.py)の構造上、身頃の輪郭で
    y座標が最小になる点は「左右の首の付け根」の2点だけで、その間を通る
    区間がちょうど首ぐりになる(肩先は肩下がりのぶん下にあり、首ぐりは
    そこから下へ落ち込むため、ほかにy最小の点は現れない)。ラウンド/V/
    スクエア/ボート/スウィートハートのいずれでもこの性質は共通で、
    ネックライン形状ごとの個別対応は要らない。

    対象外(Noneを返す):
      - front_bodice_zip_panel … 中心前で裁ち割った片側パネルで、輪郭に
        見返しの張り出しが加わるため、y最小の点が1つしか現れない。
      - タートルネック … 上記NECKLINE_UNMEASURABLE_VARIATIONSのコメント参照。
      - 想定外の形状(y最小の点が2つ見つからない)。

    round14までこの計測が無かったため、衿(collar)は首ぐりとまったく無関係に
    バスト比で拡大縮小されていた(モジュールdocstringの「できないこと」参照)。
    """
    if part.part_type not in {"front_bodice", "back_bodice"}:
        return None
    if any(token in part.variation for token in NECKLINE_UNMEASURABLE_VARIATIONS):
        return None
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return None
    top_y = min(p[1] for p in points)
    idx = [i for i, p in enumerate(points) if abs(p[1] - top_y) <= _COORD_TOL]
    if len(idx) < 2:
        return None
    i, j = idx[0], idx[-1]
    chain = points[i:j + 1]
    if len(chain) < 2:
        return None
    return sum(_edge_length(a, b) for a, b in zip(chain, chain[1:]))


def band_length(part) -> float:
    """帯状パーツ(ウエストバンド/衿/カフス)の外接矩形の幅を返す。

    【round15での位置づけの変更】以前はこれを「帯の長さ」としてそのまま
    縫い合わせ長さの比較に使っていた。しかし帯の外接矩形の幅は、実際に
    相手へ縫い付けられる辺の長さと一致しない:

      パーツ                     外接矩形   縫い付け辺
      collar/shirt_collar          40.0cm     32.0cm   (襟先が左右へ張り出す)
      collar/bow_collar            44.0cm     32.0cm   (同上)
      collar/convertible_collar    40.0cm     28.0cm   (襟先が角状に張り出す)
      collar/peter_pan_collar      40.0cm     36.0cm   (内側が首ぐり側)
      cuffs/button_tab             24.0cm     20.0cm   (ボタンタブが張り出す)
      waistband/contour            70.0cm     70.1cm   (辺そのものが曲線)

    比較にも、相手へ合わせる変形にも`seam_edge_length`を使う。この関数は
    パーツの見た目の大きさ(配置・表示用)を表す値として残している。
    """
    points = part.stitch_line
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    return max(xs) - min(xs)


def seam_edge_length(part) -> float:
    """帯状パーツの「相手に縫い付けられる辺」の実際の長さを求める(round15)。

    どちらの辺が縫い付け側かはテンプレートSVGの`data-seam-edge`属性
    ("top"=y最小側 / "bottom"=y最大側)で宣言されており、
    `TemplateDB.get_seam_edge`→`engine/seam.py`の`finalize_part`経由で
    パーツに載っている。宣言が無いパーツでは外接矩形の幅(=`band_length`、
    round14までと同じ)へフォールバックする。

    測り方は2段階:
      1. 宣言された側の端(y最小 or y最大)にある**水平な辺の長さの合計**。
         衿・カフス・ウエストバンドのほとんどはここで決まる。襟先やボタン
         タブのような張り出しは、そのyに乗っていないので自動的に除かれる。
      2. 合計が0の場合(=その辺自体が曲線。waistband/contourが該当)は、
         左右の端点の間を、その側を通って結ぶ輪郭の弧長を合計する。
    """
    edge = getattr(part, "seam_edge", "")
    points = part.stitch_line
    if not edge or len(points) < 3:
        return band_length(part)
    closed = _closed_points(points)
    ys = [p[1] for p in closed]
    target_y = min(ys) if edge == "top" else max(ys)

    # 帯の縫い付け辺は、帯の幅の大半を占めるはず(いちばん短いconvertible_collar
    # でも外接矩形の70%)。これを下回る短い水平線しか見つからない場合は、
    # 「辺そのものが曲線で、その頂点付近がたまたま水平に見えているだけ」
    # (waistband/contourが該当。頂点付近の6cmだけが水平と判定される)なので、
    # 下の弧長計算へ回す。
    xs_all = [p[0] for p in closed]
    span = max(xs_all) - min(xs_all)
    run = _sum_length_at_y(closed, target_y)
    if run > 0 and (span <= 0 or run >= span * _MIN_SEAM_EDGE_SPAN_RATIO):
        return run

    # 辺そのものが曲線のケース。左右の端で、宣言された側にある点を選び、
    # その2点を結ぶ2つの経路のうち、平均yが端に近い方を縫い付け辺とする。
    xs = [p[0] for p in closed]
    min_x, max_x = min(xs), max(xs)

    def _pick(x_target: float) -> int:
        candidates = [i for i, p in enumerate(closed) if abs(p[0] - x_target) <= _COORD_TOL]
        if not candidates:
            return -1
        key = (lambda i: closed[i][1]) if edge == "top" else (lambda i: -closed[i][1])
        return min(candidates, key=key)

    i, j = _pick(min_x), _pick(max_x)
    if i < 0 or j < 0 or i == j:
        return band_length(part)
    lo, hi = (i, j) if i < j else (j, i)
    path_a = closed[lo:hi + 1]
    path_b = closed[hi:] + closed[:lo + 1]

    def _mean_y(path):
        return sum(p[1] for p in path) / len(path) if path else float("inf")

    if edge == "top":
        path = path_a if _mean_y(path_a) <= _mean_y(path_b) else path_b
    else:
        path = path_a if _mean_y(path_a) >= _mean_y(path_b) else path_b
    return sum(_edge_length(a, b) for a, b in zip(path, path[1:]))


def _mismatched(expected_cm: float, actual_cm: float) -> bool:
    if expected_cm <= 0:
        return False
    tolerance = max(_ABS_TOLERANCE_CM, expected_cm * _REL_TOLERANCE)
    return abs(expected_cm - actual_cm) > tolerance


def _all(parts, part_types: set[str]) -> list:
    return [p for p in parts if p.part_type in part_types]


def check_seam_compatibility(finalized_parts: list) -> list[CompatibilityWarning]:
    """生成済みの全パーツから、縫い合わせ長さの不整合を検出する。

    パーツの組み合わせ自体が存在しない場合(例: スカートを選んでいない、
    カフスを選んでいない)は、その組み合わせのチェックを単純にスキップする
    (「無い物同士は比較しようがない」ため、警告にはしない)。
    """
    warnings: list[CompatibilityWarning] = []

    # 1. 前身頃(front_bodice/front_bodice_zip_panel) vs 後ろ身頃(back_bodice)の脇線。
    front_parts = _all(finalized_parts, {"front_bodice", "front_bodice_zip_panel"})
    back_parts = _all(finalized_parts, {"back_bodice"})
    if front_parts and back_parts:
        front_lengths = [side_seam_length(p) for p in front_parts]
        back_lengths = [side_seam_length(p) for p in back_parts]
        if all(v is not None for v in front_lengths) and all(v is not None for v in back_lengths):
            front_total = sum(front_lengths)
            back_total = sum(back_lengths)
            if _mismatched(back_total, front_total):
                warnings.append(CompatibilityWarning(
                    kind="side_seam",
                    message=(
                        f"前身頃の脇線の長さ(合計{front_total:.1f}cm)と、後ろ身頃の"
                        f"脇線の長さ(合計{back_total:.1f}cm)が{abs(front_total - back_total):.1f}cm"
                        "一致していません。脇はこの2辺を縫い合わせるため、差が大きいと"
                        "そのままでは縫えません。"
                        "(round13までは、前身頃に脇ダーツが入るだけでこの警告が出ていました。"
                        "脇ダーツの口の幅ぶん前身頃の脇線が短いままだったためで、"
                        "round14で前身頃側に丈を足して一致させています。"
                        "engine/darts.pyの`_shift_below`参照)"
                    ),
                    expected_cm=back_total,
                    actual_cm=front_total,
                ))

    # 2. スカート(skirt)のウエストライン vs ウエストバンド(waistband)。
    skirt_parts = _all(finalized_parts, {"skirt"})
    waistband_parts = _all(finalized_parts, {"waistband"})
    if skirt_parts and waistband_parts:
        skirt_total = sum(waist_opening_length(p) for p in skirt_parts)
        band_total = sum(seam_edge_length(p) for p in waistband_parts)
        # ウエストバンドは打ち合わせ分(WAISTBAND_CLOSURE_EASE_CM)だけ、
        # スカートのウエスト開きより意図的に長く作られるのが正常なので、
        # その分を加えた上で期待値と比較する(モジュールdocstring参照)。
        expected_band_total = skirt_total + WAISTBAND_CLOSURE_EASE_CM
        if _mismatched(expected_band_total, band_total):
            warnings.append(CompatibilityWarning(
                kind="waist_opening_skirt",
                message=(
                    f"スカートのウエストラインの合計({skirt_total:.1f}cm)+"
                    f"打ち合わせ分{WAISTBAND_CLOSURE_EASE_CM:.1f}cmに対し、"
                    f"ウエストバンドの長さ({band_total:.1f}cm)が"
                    f"{abs(expected_band_total - band_total):.1f}cm一致していません。"
                ),
                expected_cm=expected_band_total,
                actual_cm=band_total,
            ))

    # 3. パンツ(front_pants/back_pants)のウエストライン vs ウエストバンド。
    pants_parts = _all(finalized_parts, {"front_pants", "back_pants"})
    if pants_parts and waistband_parts:
        pants_total = sum(waist_opening_length(p) for p in pants_parts)
        band_total = sum(seam_edge_length(p) for p in waistband_parts)
        expected_band_total = pants_total + WAISTBAND_CLOSURE_EASE_CM
        if _mismatched(expected_band_total, band_total):
            warnings.append(CompatibilityWarning(
                kind="waist_opening_pants",
                message=(
                    f"パンツのウエストラインの合計({pants_total:.1f}cm)+"
                    f"打ち合わせ分{WAISTBAND_CLOSURE_EASE_CM:.1f}cmに対し、"
                    f"ウエストバンドの長さ({band_total:.1f}cm)が"
                    f"{abs(expected_band_total - band_total):.1f}cm一致していません。"
                ),
                expected_cm=expected_band_total,
                actual_cm=band_total,
            ))

    # 4. 袖(sleeve)の袖口 vs カフス(cuffs)。
    sleeve_parts = _all(finalized_parts, {"sleeve"})
    cuffs_parts = _all(finalized_parts, {"cuffs"})
    if sleeve_parts and cuffs_parts:
        sleeve_total = sum(hem_or_wrist_opening_length(p) for p in sleeve_parts)
        cuffs_total = sum(seam_edge_length(p) for p in cuffs_parts)
        # 左右2枚のカフスはそれぞれ独立に閉じる輪(手首を通す筒)であり、
        # それぞれが自分の開閉ゆとり分を持つ(scale_band_to_target_width()は
        # カフス1枚ごとにCUFFS_EASE_CMを加えて生成する)。そのため、左右
        # 合計同士を比較するここでは、ゆとり分もカフスの枚数分だけ加える
        # 必要がある(1回分しか加えないと、実際には整合しているのに
        # 「カフス合計が枚数×ゆとり分だけ長すぎる」という誤検出になる)。
        expected_cuffs_total = sleeve_total + CUFFS_EASE_CM * len(cuffs_parts)
        if _mismatched(expected_cuffs_total, cuffs_total):
            warnings.append(CompatibilityWarning(
                kind="wrist_opening",
                message=(
                    f"袖口の合計({sleeve_total:.1f}cm)+開閉のゆとり分"
                    f"{CUFFS_EASE_CM:.1f}cm×{len(cuffs_parts)}枚に対し、カフスの長さ"
                    f"(合計{cuffs_total:.1f}cm)が"
                    f"{abs(expected_cuffs_total - cuffs_total):.1f}cm一致していません。"
                ),
                expected_cm=expected_cuffs_total,
                actual_cm=cuffs_total,
            ))

    # 5. 前身頃+後ろ身頃の袖ぐり vs 袖(sleeve)の袖山
    # (round11で追加、round12で絶対値比較に改めた。上記
    #  SLEEVE_CAP_EASE_CMのコメントに経緯を記載)。
    # front_bodice_zip_panelは対象外(armhole_lengthのdocstring参照)。
    armhole_front_parts = _all(finalized_parts, {"front_bodice"})
    armhole_back_parts = _all(finalized_parts, {"back_bodice"})
    if armhole_front_parts and armhole_back_parts and sleeve_parts:
        front_armholes = [armhole_length(p) for p in armhole_front_parts]
        back_armholes = [armhole_length(p) for p in armhole_back_parts]
        if all(v is not None for v in front_armholes) and all(v is not None for v in back_armholes):
            # armhole_lengthは1パーツぶん(左右2つ分)を返すので、
            # 「片腕ぶんの袖ぐり周長」は前後の合計を2で割った値になる。
            armhole_per_arm = (sum(front_armholes) + sum(back_armholes)) / 2.0

            sleeves_by_variation: dict[str, list] = {}
            for p in sleeve_parts:
                sleeves_by_variation.setdefault(p.variation, []).append(p)

            for variation, group in sleeves_by_variation.items():
                cap_lengths = [sleeve_cap_length(p) for p in group]
                if not all(v is not None for v in cap_lengths):
                    continue
                gather = SLEEVE_CAP_DESIGN_GATHER_CM.get(variation, 0.0)
                expected_per_sleeve = armhole_per_arm + SLEEVE_CAP_EASE_CM + gather
                for part, cap in zip(group, cap_lengths):
                    if not _mismatched(expected_per_sleeve, cap):
                        continue
                    gather_note = (f"+デザイン上のギャザー{gather:.1f}cm" if gather else "")
                    warnings.append(CompatibilityWarning(
                        kind="armhole_sleeve_cap",
                        message=(
                            f"袖ぐり(片腕){armhole_per_arm:.1f}cm+いせ込み"
                            f"{SLEEVE_CAP_EASE_CM:.1f}cm{gather_note}に対し、"
                            f"袖({variation}{(' ' + part.label_suffix) if part.label_suffix else ''})の"
                            f"袖山カーブが{cap:.1f}cmで、"
                            f"{abs(expected_per_sleeve - cap):.1f}cm一致していません。"
                            "身頃はバスト、袖は肩幅と別々の採寸で拡大縮小するため、"
                            "その釣り合いが標準から大きく外れた体型で起こります。"
                            "差が大きいと袖を袖ぐりに縫い付けられません。"
                        ),
                        expected_cm=expected_per_sleeve,
                        actual_cm=cap,
                    ))

    # 6. 身頃の首ぐり vs 衿(collar)。round15で追加。
    #    round14までは「どの辺が首ぐりか」を汎用的に取り出せないという理由で
    #    見送っていたが、身頃の輪郭ではy最小の点がちょうど左右の首の付け根に
    #    なるという性質(`neckline_length`参照)を使えば、ネックライン形状に
    #    依存せずに測れることが分かったため実装した。
    collar_parts = _all(finalized_parts, {"collar"})
    neckline_parts = _all(finalized_parts, {"front_bodice", "back_bodice"})
    if collar_parts and neckline_parts:
        lengths = [neckline_length(p) for p in neckline_parts]
        if all(v is not None for v in lengths):
            neckline_total = sum(lengths)
            expected_collar = neckline_total + COLLAR_EASE_CM
            collar_total = sum(seam_edge_length(p) for p in collar_parts)
            if _mismatched(expected_collar, collar_total):
                warnings.append(CompatibilityWarning(
                    kind="neckline_collar",
                    message=(
                        f"身頃の首ぐりの長さ(前+後で{neckline_total:.1f}cm)に対し、"
                        f"衿の首ぐり側の辺が{collar_total:.1f}cmで、"
                        f"{abs(expected_collar - collar_total):.1f}cm一致していません。"
                        "衿はこの辺を首ぐりにぐるりと縫い付けるため、差が大きいと"
                        "そのままでは付けられません。"
                    ),
                    expected_cm=expected_collar,
                    actual_cm=collar_total,
                ))

    return warnings
