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
  - 前身頃と後ろ身頃の**肩線**の長さ比較(round21で追加。前後で別々の
    ネックラインを選べるようにしたため、首の開き幅が違う組み合わせで
    肩線が食い違うようになった。`shoulder_seam_length`参照)。
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

#: round31: いせ込みの量を、袖ぐり寸法(AH)に対する割合で決める。
#:
#: 【出典と、固定値2.0cmでは何が足りなかったか】新文化式の袖の製図では
#: いせ分量を「前後身頃AH寸法×0.05」として求める(袖の2枚袖では6〜8%。
#: 布帛のテーラードジャケットはもっと多く取る)。round30まではこの量を
#: 体型によらず2.0cmに固定していた。標準Mサイズの袖ぐり(片腕約40.6cm)
#: では 40.6×0.05 = 2.03cm で、**固定値2.0cmはちょうど標準Mの5%だった**
#: ——つまり元の値は正しく、体が大きくなっても増えないことだけが誤りだった。
#: 実測(round31時点の袖ぐり):
#:     バスト60 →片腕35.4cm→いせ1.77cm(固定値では2.0で0.2cm多い)
#:     バスト83 →片腕40.6cm→いせ2.03cm(ほぼ同じ)
#:     バスト130→片腕52.8cm→いせ2.64cm(固定値では0.6cm足りない)
#: いせが足りないと袖山の丸みが出ず、腕を前へ出したとき肩先が突っ張る。
#: 多すぎると縫うときにタックが寄る。
SLEEVE_CAP_EASE_RATIO = 0.05
#: 上の割合で決めたいせ込みの、下限と上限(cm)。下限は「これ以下だと
#: 丸みが出ない」、上限は「これ以上は家庭用ミシンで縮めきれずタックに
#: なる」という洋裁上の目安(布帛で1.5〜3cm程度)。
SLEEVE_CAP_EASE_MIN_CM = 1.5
SLEEVE_CAP_EASE_MAX_CM = 3.0


def sleeve_cap_ease_cm(armhole_per_arm_cm: float | None,
                        drop_shoulder: bool = False) -> float:
    """袖ぐり(片腕・cm)に対するいせ込みの量(cm)。

    袖ぐりが分からない場合は、従来どおりの固定値を返す。

    round76: ドロップショルダーでは、いせ込みを減らす。肩先が腕の上まで
    落ちているので、肩先の丸みをいせで作る必要が無い。東レACS
    「第十六章 ドロップショルダージャケットのパターンとデジタルトワル
    チェック」は「ドロップショルダー袖にするため、袖山線のいせ量を減らし
    全体で15mm前後とする」と書いている。値は
    `engine/drop_shoulder.py`の`DROP_SLEEVE_CAP_EASE_CM`。
    """
    if drop_shoulder:
        from .drop_shoulder import DROP_SLEEVE_CAP_EASE_CM
        return DROP_SLEEVE_CAP_EASE_CM
    if not armhole_per_arm_cm or armhole_per_arm_cm <= 0:
        return SLEEVE_CAP_EASE_CM
    return min(SLEEVE_CAP_EASE_MAX_CM,
               max(SLEEVE_CAP_EASE_MIN_CM,
                   armhole_per_arm_cm * SLEEVE_CAP_EASE_RATIO))

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

#: round71: たたみ出し(truing)したダーツの口が、脇線から外れてよい上限(cm)。
#:
#: 胸ぐせダーツは先端をBPへ斜めに刺すので、口を脇線の上に並べると
#: **2本の脚の長さが揃わない**(round70まで実測で8〜14%ずれていた)。
#: `engine/darts.py`の`_equalise_legs`が脚を揃える。その結果、口は
#: 脇線から少し外れる(片方は外へ、もう片方は内へ)。
#: ここを見張る側も、その出っ張りを織り込んでおかないと**ダーツを
#: ダーツと認識できず**、脇線の断片が救済されない(実測: 前身頃の脇線が
#: 35.2cmのはずが31.4cmと報告され、「そのままでは縫えません」という
#: 誤った警告が出た)。
#:
#: 生成側(`engine/darts.py`)はこの値を上限としてたたみ出しを諦めるので、
#: 出っ張りがこれを超えることはない。**2か所で同じ値を持たないよう、
#: 生成側はここから読む。**
#: round71: 3.0から2.0へ下げた。実測(バスト130・ウエスト120・ヒップ170)で
#: 脚の差が5.01cmあり、半分の2.5cmだけ口が脇線から外れた。そこまで外れると
#: 脇線が「ほぼ垂直」でなくなり、見張る側が脇線として数えられない
#: (実測: 前身頃53.3cm・後ろ63.9cmと10.6cm食い違い、誤った警告が出た)。
#: **極端な体型では、揃えないまま出す**方を選ぶ——脚が揃っていない型紙は
#: round70までと同じで、少なくとも今より悪くはならない。
DART_TRUING_MAX_OFFSET_CM = 2.0
#: 隣り合う2辺を「一直線に続いている」とみなす、傾き(dx/dy)の差の上限。
#: round29。脇線がウエスト・裾で折れるときの折れ角(実測0.004〜0.04)は
#: 通し、袖ぐりのカーブの折れ角(1辺ごとに約0.15)は通さない値。
_COLLINEAR_SLOPE_TOL = 0.05
#: 向きが変わっていても同じ脇線としてつなぐための、辺1本の最小の長さ(cm)。
#: 脇線はウエストで内側へ折れ、そこから裾へ向かって外へ開くので、
#: その折れ目では傾きの符号が変わる(実測: +0.055 → −0.059)。一方、
#: 袖ぐりのカーブを折れ線にしたときの1本の長さは実測で最大2.10cm
#: (バスト60、curve_steps既定)なので、この値なら混ざらない。
_MIN_JOINABLE_FRAGMENT_CM = 2.5
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


#: 脇線と認める「ほぼ垂直」の許容。|dx| がこの比率×|dy| 以下なら垂直とみなす。
#:
#: round26で追加。round25まで脇線は**厳密に垂直**(dx≈0)であることを前提に
#: していたが、round26で裾をヒップに合わせるために脇線を下へ向かってわずかに
#: 外へ開かせた(`engine/bodice_fit.py`の`hip_widening_cm`)。実測での傾きは
#: 最大でも縦34cmに対し横3cm弱(比0.09)なので、0.25は十分な余裕がある一方、
#: 首ぐりの縦の辺や裾のような別の辺を拾うほど緩くはない。
NEAR_VERTICAL_MAX_DX_RATIO = 0.25


def _x_range_at_y(points: list[tuple[float, float]], y: float) -> tuple[float, float] | None:
    """閉じた輪郭の、高さ y における x の最小・最大を求める。

    その高さをまたぐ辺すべてについて交点の x を集める。「この辺は
    パーツの外周(脇線)に乗っているか」を、x座標そのものではなく
    **その高さでの外側かどうか**で判定するために使う(脇線が傾いていると、
    パーツ全体の最小x/最大xと突き合わせる従来の判定では、上の方の
    区間を取りこぼす)。
    """
    xs: list[float] = []
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        if y1 == y2:
            if abs(y1 - y) <= _COORD_TOL:
                xs.extend([x1, x2])
            continue
        lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
        if not (lo - _COORD_TOL <= y <= hi + _COORD_TOL):
            continue
        t = (y - y1) / (y2 - y1)
        xs.append(x1 + t * (x2 - x1))
    if not xs:
        return None
    return min(xs), max(xs)


#: 「ほぼ垂直」の上限と比べるときの許容(cm)。上の`_is_side_seam_edge`参照。
#: 脇線を作る側が上限ぴったりの傾きを作るので、丸め誤差ぶんだけ緩める。
#: 「ほぼ垂直」の上限に足す余裕(cm)。
#:
#: round35で 1e-6 として入れた——脇線を作る側(`engine/bodice_fit.py`)が
#: 傾きを上限**ちょうど**まで開かせるので、浮動小数の丸めで左右の
#: 鏡像のうち片方だけが落ちる、という事故を防ぐためだった。
#:
#: round71で 0.25cm に広げた。ダーツを縫って閉じたときに脇線が縮む量の
#: 見積もりを直した結果、ウエストの点が最大0.8cmほど動く。裾は
#: ヒップで決まって動かないので、ウエント〜裾の走りの傾きがその分だけ
#: 変わる。実測(バスト84・ウエスト60・ヒップ150): |dx|が5.02→5.13cmに
#: なり、上限5.0625cmを**0.07cm**超えて落ちた。結果、脇線が29.8cmと
#: 報告され(正しくは71.6cm)、「そのままでは縫えません」という誤った
#: 警告が出た。
#:
#: 0.25cmにしても袖ぐりを飲み込まないことは、round35から置いてある
#: `test_the_rescue_does_not_swallow_the_armhole`で見張っている
#: (袖ぐりのカーブは1本2.1cm以下で、脇の下の高さでも除外される)。
_SLOPE_TOLERANCE = 0.25


def _is_side_seam_edge(points: list[tuple[float, float]],
                        p1: tuple[float, float], p2: tuple[float, float],
                        edge_tol: float = 0.5,
                        min_run: float = _MIN_VERTICAL_RUN_CM,
                        extra_dx_cm: float = 0.0) -> str | None:
    """この辺が脇線(パーツの左右いずれかの外周)に乗っているか(round26)。

    乗っていれば "left"/"right" を、そうでなければ None を返す。条件は3つ:

      1. 十分に長い縦の走り(min_run以上、既定は_MIN_VERTICAL_RUN_CM)である
         こと。首ぐりの短い縦の辺やダーツの斜め辺を除外する。
         round28: `side_seam_runs`は、断片をつなぐ候補を集める段階だけ
         min_runを緩めて呼ぶ(長さの判定は連結した走り全体で行う)。
      2. ほぼ垂直(NEAR_VERTICAL_MAX_DX_RATIO以内)であること。裾やダーツの
         口のような横向きの辺を除外する。
      3. **その高さでの**輪郭の外側に乗っていること。パーツの内側にある
         縦の辺(スクエアネックの首ぐり等)を除外する。round25までは
         「パーツ全体の最小x/最大xと一致」で見ていたが、脇線が傾くと
         上の方の区間を取りこぼすため、高さごとに見るようにした。
    """
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    if abs(dy) < min_run:
        return None
    # round35: 上限との比較に微小な許容を足す。
    #
    # 【なぜ必要か】脇線を作る側(`engine/bodice_fit.py`の`hip_widening_start_y`
    # と`waist_nip_limit_cm`)は、傾きが`NEAR_VERTICAL_MAX_DX_RATIO`を
    # **ちょうど**超えないところまで開かせる/絞る。つまり極端な体型では、
    # 脇線の傾きは意図的に上限ぴったりになる。そこを厳密な `>` で見ると、
    # 浮動小数の丸めで**左右の鏡像のうち片方だけが落ちる**。
    # 実測(バスト84・ウエスト60・ヒップ150): |dx|も上限も1.113で、
    # 左は通り右は落ちた。その結果、右の脇線が上端4.59cmぶん短く測られ、
    # `side_seam_length`が「片方は中心前(CF)の縁だ」と誤って判定して
    # 前身頃の脇線を31.0cmと報告——後ろ71.9cmと**40.9cm**食い違って
    # 「そのままでは縫えません」という誤った警告が出ていた。
    # round71: `extra_dx_cm`は、たたみ出ししたダーツの口へ入る/出る辺
    # だけに足す許容。たたみ出しで口が脇線から外れるので、その辺は
    # 脇線としては不自然に傾く(実測: dx1.29/dy3.50 = 0.37、上限0.25超)。
    # 全体の上限を緩めると袖ぐりを飲み込むので、**ダーツに隣り合う辺に
    # 限って**緩める(呼び出し側が判定して渡す)。
    if abs(dx) > NEAR_VERTICAL_MAX_DX_RATIO * abs(dy) + _SLOPE_TOLERANCE + extra_dx_cm:
        return None
    span = _x_range_at_y(points, (y1 + y2) / 2.0)
    if span is None:
        return None
    mid_x = (x1 + x2) / 2.0
    if abs(mid_x - span[0]) <= edge_tol + extra_dx_cm:
        return "left"
    if abs(mid_x - span[1]) <= edge_tol + extra_dx_cm:
        return "right"
    return None


#: 脇線の辺の並び。(輪郭上の番号, "left"/"right", 始点, 終点)。
SideSeamEdge = tuple[int, str, tuple[float, float], tuple[float, float]]


def _is_dart_notch_at(points: list[tuple[float, float]], i: int,
                       edge_tol: float) -> bool:
    """points[i] から始まる3点が、脇線に入れたダーツのV字ノッチか。

    ノッチは (口の上端, 先端, 口の下端) の3点で、口の2点は**脇線の上**に
    あり、先端だけが大きく内側へ離れている。

    【round29で「ほぼ同じx」をやめた】脇線は厳密な垂直ではない——裾を
    ヒップに合わせて開かせ、ウエストで絞るので傾いている。口の幅が6cmある
    大きな胸ぐせダーツでは、その傾き(最大0.25)だけで口の2点のxが1.5cm
    離れうる。固定の許容0.5cmで見ていたため、大きいダーツほどノッチと
    認識されず、脇線の断片が救済されなかった(実測: バスト130で前身頃の
    脇線が52.3cm・後ろ身頃が62.7cmと10.4cm食い違って見えた)。
    口の2点が「脇線として許される傾きの範囲に収まっているか」で見る。
    """
    if i + 2 >= len(points):
        return False
    a, tip, b = points[i], points[i + 1], points[i + 2]
    # round71: 脇線のダーツは、口が**縦に**並ぶ。裾の上向きダーツは横に
    # 並ぶので、ここで分かれる。
    #
    # 【なぜ要るか】この下で、たたみ出しの出っ張りぶん許容を広げる。
    # 広げるだけだと、裾に開いたウエストダーツのV字(口の幅3cm・
    # ほぼ水平)まで「脇線のダーツ」として拾ってしまう(実測: 先端が
    # 4つのはずが6つ数えられた)。
    if abs(a[1] - b[1]) < abs(a[0] - b[0]):
        return False
    mouth_tol = edge_tol + NEAR_VERTICAL_MAX_DX_RATIO * abs(a[1] - b[1])
    # round71: たたみ出しで口が脇線から外れるぶんは、**口どうしの比較にだけ**
    # 足す。先端の判定にまで足すと、閾値が3倍に効いて
    # 「先端が内側にある」が満たせなくなる(実測: 先端は口から13.34cm
    # 内側にあるのに、閾値が14.13cmに膨らんでダーツと認識されなくなった)。
    if abs(a[0] - b[0]) > mouth_tol + DART_TRUING_MAX_OFFSET_CM:
        return False
    # 先端は口よりはっきり内側にあること(傾きのゆらぎと区別する)。
    return abs(tip[0] - a[0]) > 3.0 * mouth_tol


def side_seam_edges(points: list[tuple[float, float]],
                     edge_tol: float = 0.5,
                     underarm_y: float | None = None) -> list[SideSeamEdge]:
    """輪郭のうち、脇線に属する辺を(番号つきで)返す(round28)。

    round31で`underarm_y`を追加した。与えられた場合、その高さより**上**に
    ある辺は脇線候補にしない。脇線は定義上、脇の下から下にしかない。

    【なぜ形だけでは足りなくなったか】round31で後ろ身頃の袖ぐりを
    新文化式の背幅線(B/8+7.4)に接するよう引き直したところ、後ろの袖ぐりは
    **ほぼ直線**になった(バスト83・肩幅37で、肩先18.50cmに対し背幅
    17.77cm——19cm降りる間に0.73cmしかえぐれない)。これは製図として
    正しい(新文化式の後ろ袖ぐりは元々ほぼ直線で、前だけがはっきり
    えぐれる)のだが、その結果:

      * 袖ぐりの各辺が「ほぼ垂直で輪郭の外側」を満たし、
      * 脇線の延長線との差も0.07cmしかない(実測)

    ため、**傾きでも長さでも脇線と区別できなくなった**。実測(伸びる生地・
    バスト83/ウエスト50/ヒップ100)で、後ろの脇線が107.69cmと出た
    (正しくは前と同じ69.58cm。差は袖ぐりを飲み込んだぶん)。

    しきい値を絞る方向は行き止まりである(区別できる差が実際に無い)。
    代わりに、エンジンが既に知っている「脇の下の高さ」を渡す。
    `FinalizedPart.reference_lines`のバスト線(BL)がその高さそのものなので、
    パーツを持つ呼び出し側(`side_seam_length`・`armhole_length`)は
    `underarm_y_of`で取り出して渡せる。渡されなければround30までと
    まったく同じ動きになる。

    基本の判定は`_is_side_seam_edge`のまま——つまりround27までと同じ辺は
    そのまま脇線として数える。round28で加えたのは**ダーツの口をまたいだ
    短い断片の救済**だけ。

    【なぜ必要になったか】round27までダーツの口は脇線のちょうど真ん中
    あたりに開いていたので、口の上下どちらの断片も5cm(_MIN_VERTICAL_RUN_CM)を
    ゆうに超えていた。round28でダーツをBP(バストポイント)へ向けたことで、
    口は脇の下から6cm——脇線の**上端のすぐ下**——へ移り、口より上の断片が
    4.65cmしか残らなくなる。すると単独では5cmに届かず黙って捨てられ、実測
    (バスト110・ウエスト85・ヒップ112)で

        前身頃の脇線 55.20cm / 後ろ身頃 64.50cm  ← 上の4.65cm×2を取りこぼした

    となった(前後の脇線長が食い違う=縫えない、という誤検出)。

    【しきい値をただ下げなかった理由】袖ぐりのカーブは、バストが小さく
    肩幅が広い体型ではほぼ垂直になる。実測(バスト60・肩幅37)では袖ぐりの
    4本の辺が「ほぼ垂直で、その高さの輪郭の外側」を満たし、合計7.6cmに
    なる。長さだけで見ると脇線と区別できず、飲み込むと袖ぐり長が
    33.9cm→3.45cmになる(実測)。そこで、つながったかたまりごとに

      * 合計が_MIN_VERTICAL_RUN_CM以上であること、に加えて
      * **単独でも**_MIN_VERTICAL_RUN_CM以上の辺を1本以上含むこと

    を求める。袖ぐりの当該区間は1本あたり最長1.97cmなので確実に外れる。

    round29で、脇線をウエストで絞る(`engine/bodice_fit.py`の
    `apply_waist_nip`)ようにしたことで、脇線はウエストの高さでも折れる。
    そこで折れた断片は5cmに満たないことがある(実測: バスト140・肩幅30で
    4.93cm)ので、ダーツの口をまたぐ場合だけでなく**素直に隣接する場合**も
    同じかたまりとして扱う。
    """
    # round71: たたみ出ししたダーツの口に隣り合う辺は、脇線としては
    # 不自然に傾く(口が脇線から外れているため)。その辺だけ傾きの許容を
    # 広げる。どの辺かは、ダーツのV字を見つければ決まる——口Aへ入る辺と
    # 口Bから出る辺の2本である。
    dart_adjacent: set[int] = set()
    for i in range(max(0, len(points) - 3)):
        if _is_dart_notch_at(points, i, edge_tol):
            if i >= 1:
                dart_adjacent.add(i - 1)
            dart_adjacent.add(i + 2)

    strong: dict[int, str] = {}
    weak: dict[int, str] = {}
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        if underarm_y is not None and min(p1[1], p2[1]) < underarm_y - edge_tol:
            continue        # 脇の下より上=袖ぐり側。脇線ではない。
        extra = DART_TRUING_MAX_OFFSET_CM if i in dart_adjacent else 0.0
        side = _is_side_seam_edge(points, p1, p2, edge_tol, min_run=0.05,
                                  extra_dx_cm=extra)
        if side is None:
            continue
        weak[i] = side
        if _is_side_seam_edge(points, p1, p2, edge_tol, extra_dx_cm=extra) is not None:
            strong[i] = side

    # 断片を「つながり」でまとめる。隣どうし、またはダーツの口をまたいで
    # 隣どうしなら同じかたまり。
    def _slope(i: int) -> float:
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        dy = y2 - y1
        return (x2 - x1) / dy if abs(dy) > 1e-9 else 0.0

    # round35: 脇の下の高さが分かっているなら、断片をつなぐ**ヒューリスティック
    # 自体が要らない**。候補はすでに「脇の下より下」「ほぼ垂直」「その高さの
    # 輪郭の外側」を満たしていて、それは脇線の定義そのものだからである。
    # 左右それぞれを1つのかたまりにまとめる。
    #
    # 【なぜこれが要ったか】round28〜31で足した「断片をつなぐ規則」
    # (ほぼ一直線 or 両方2.5cm以上)は、袖ぐりを飲み込まないための苦肉の策
    # だった。しかし胸ぐせダーツが2本入る体型では、脇線が3つの断片に割れ、
    # 上の2つが 4.59cm と 2.06cm——どちらも「5cm以上の辺」を含まず、
    # かつ 2.06cm < 2.5cm なので下の長い断片ともつながらない。結果、
    # **上の6.65cmが丸ごと捨てられていた**。実測(バスト84・ウエスト60・
    # ヒップ150)で、前身頃の脇線57.88cm・後ろ身頃71.85cmと**14.0cm**
    # 食い違い、「そのままでは縫えません」という警告が出ていた。
    # 実際には前も35.59cmあり、縫える型紙だった——測り方が悪かっただけ。
    if underarm_y is not None:
        by_side: dict[str, list[int]] = {}
        for idx, side in sorted(weak.items()):
            by_side.setdefault(side, []).append(idx)
        accepted_by_side: dict[int, str] = {}
        for side, idxs in by_side.items():
            total = sum(_edge_length(points[i], points[i + 1]) for i in idxs)
            if total < _MIN_VERTICAL_RUN_CM:
                continue      # 数mmの切れ端は脇線ではない
            for i in idxs:
                accepted_by_side[i] = side
        return [(i, side, points[i], points[i + 1])
                for i, side in sorted(accepted_by_side.items())]

    groups: list[list[int]] = []
    #: ダーツのV字をまたいだかたまり(`id()`で覚える)。
    spans_a_dart: set[int] = set()
    dart_groups: list[list[int]] = []
    current: list[int] = []
    just_crossed_a_dart = False
    i = 0
    n = len(points) - 1
    while i < n:
        side = weak.get(i)
        # 素直に隣接する場合は、**ほぼ一直線に続いている**ときだけつなぐ。
        # 脇線がウエストや裾で折れるときの折れ角はごく浅い(実測0.004)。
        # 袖ぐりのカーブは1本ごとに0.15ずつ向きが変わるので、この条件で
        # 脇線と地続きにならない(`test_the_rescue_does_not_swallow_the_armhole`)。
        # round71: ダーツのV字を1つまたいだ直後は、傾きや長さを問わず
        # 同じかたまりとして続ける。ダーツは脇線にしか開かないので、
        # その両側の断片が同じ脇線に属することは形を見るまでもない。
        # (脚を揃えて口が脇線から外れたことで、口の上下の断片が短く・
        #  傾くようになり、round28からの「ほぼ一直線 or 両方2.5cm以上」
        #  ではつながらなくなった。実測バスト130: 3.07cmと1.84cmの断片が
        #  別々のかたまりになり、どちらも捨てられた。)
        joins = not current or just_crossed_a_dart or (
            weak.get(current[-1]) == side
            and (abs(_slope(i) - _slope(current[-1])) <= _COLLINEAR_SLOPE_TOL
                 # 向きが変わる箇所(ウエストで絞ってから裾へ開く、など)でも、
                 # 両方が「短い折れ線ではない」なら同じ脇線とみなす。袖ぐりの
                 # カーブは折れ線1本が2.1cm以下(実測)なので混ざらない。
                 or min(_edge_length(points[i], points[i + 1]),
                        _edge_length(points[current[-1]],
                                     points[current[-1] + 1]))
                 >= _MIN_JOINABLE_FRAGMENT_CM))
        if side is not None and joins:
            current.append(i)
            just_crossed_a_dart = False
            i += 1
            continue
        # round71: 長さ0の辺は、かたまりを切らずに素通りする。
        #
        # 【なぜ要るか】ウエストで絞ると、その高さに同じ点が2つ並ぶ
        # (長さ0の辺ができる)。round70まではこの辺の両側が同じ傾きで
        # つながっていたので、切れても次のかたまりが長い辺を含んでいて
        # 困らなかった。round71でダーツの脚を揃えたところ、口の上下の
        # 断片が傾き、**長さ0の辺より上が「5cm以上の辺を含まないかたまり」**
        # になって丸ごと捨てられた。実測(バスト110): 脇の下が25.75cmの
        # はずが44.35cmと判定され、袖ぐりの深さが18.6cm深く出た。
        if current and _edge_length(points[i], points[i + 1]) < _COORD_TOL:
            i += 1
            continue
        if current and _is_dart_notch_at(points, i, edge_tol):
            spans_a_dart.add(id(current))
            just_crossed_a_dart = True
            i += 2      # ダーツのV字をまたぐ(縫い閉じれば消える)
            continue
        if current:
            # かたまりを閉じるだけ。iは進めない——この辺自身が次の
            # かたまりの先頭になりうる(脇線が裾で折れる箇所など)。
            groups.append(current)
            if id(current) in spans_a_dart:
                dart_groups.append(current)
            current = []
            just_crossed_a_dart = False
            continue
        i += 1
    if current:
        groups.append(current)
        if id(current) in spans_a_dart:
            dart_groups.append(current)

    accepted: dict[int, str] = {}
    for group in groups:
        # 単独で_MIN_VERTICAL_RUN_CM以上の辺を1本も含まないかたまりは、
        # 脇線ではない。袖ぐりのカーブは、バストが小さく肩幅が広い体型では
        # 「ほぼ垂直で輪郭の外側」の辺が4本続き(合計7.6cm)、長さだけで見ると
        # 脇線と区別できない。1本あたりは最長1.97cmなので、この条件で外れる。
        # round71: ダーツのV字をまたいだかたまりは、**それだけで脇線である**。
        #
        # 胸ぐせダーツは脇線にしか開かない(袖ぐりにも首ぐりにも開かない)
        # ので、「ダーツをまたいで続いている」ことは脇線であることの
        # 何よりの証拠である。5cm以上の辺を1本含むこと、という条件は
        # 袖ぐりを飲み込まないための代用品でしかない。
        #
        # 【なぜ要るか】胸ぐせダーツが2本並ぶ体型では、脇線が3つ以上の
        # 断片に割れる。round70までは断片が縦にまっすぐ並んでいたので
        # 下の長い辺と地続きになれたが、round71で脚を揃えて口が脇線から
        # 外れた結果、上の断片(3〜5cm)だけで1つのかたまりになり、
        # 5cm以上の辺を含まないので丸ごと捨てられた。実測(バスト130):
        # 脇の下が27.42cmのはずが45.19cmと判定され、袖ぐりの深さが
        # 17.8cm深く出た。
        if not any(i in strong for i in group) and group not in dart_groups:
            continue
        total = sum(_edge_length(points[i], points[i + 1]) for i in group)
        if total < _MIN_VERTICAL_RUN_CM:
            continue
        for i in group:
            accepted[i] = weak[i]

    return [(i, side, points[i], points[i + 1])
            for i, side in sorted(accepted.items())]


#: `reference_lines`のうち、脇の下の高さ(=バストライン)を表すラベル
#: (engine/pipeline.pyの`_reference_lines_for`が付ける)。
UNDERARM_REFERENCE_LABEL = "BL"


def underarm_y_of(part) -> float | None:
    """パーツが持つ基準線から、脇の下の高さ(cm)を取り出す(round31)。

    基準線を持たないパーツではNoneを返し、呼び出し側は形だけの判定へ
    落ちる(round30までとまったく同じ動き)。

    round76: パーツが`underarm_y_cm`を持っていればそちらを優先する。
    ドロップショルダー(engine/drop_shoulder.py)では脇の下が実際に
    下がるが、印字するバスト線(BL)は体の寸法なので動かせない。
    """
    explicit = getattr(part, "underarm_y_cm", None)
    if explicit is not None:
        return explicit
    for label, pts in getattr(part, "reference_lines", ()) or ():
        if label == UNDERARM_REFERENCE_LABEL and pts:
            return pts[0][1]
    return None


def first_side_seam_index(points: list[tuple[float, float]],
                           edge_tol: float = 0.5,
                           underarm_y: float | None = None) -> int | None:
    """輪郭上で、最初に本物の脇線が現れる辺の番号(round28)。

    袖ぐりの長さを測る側(`armhole_length`・`engine/notches.py`の
    `_left_armhole_path`)が「どこで袖ぐりを打ち切るか」に使う。ダーツで
    断片化していても、救済された上の断片から打ち切れる。
    """
    edges = side_seam_edges(points, edge_tol, underarm_y)
    if not edges:
        return None
    return min(i for i, _side, _p1, _p2 in edges)


def side_seam_length(part) -> float | None:
    """身頃の脇線の長さ(ダーツを縫い閉じた後の実際の長さ)を求める。

    対象は front_bodice / front_bodice_zip_panel / back_bodice と、round30で
    追加した切り替え線の脇パーツ(front_bodice_side / back_bodice_side)。

    front_bodice/back_bodiceは左右対称で、脇線が2本ある想定。
    front_bodice_zip_panelは非対称で、輪郭上には「外側の脇線」と
    「中心前(CF)/見返しの縁」の2本の長い垂直候補があるが、後者は
    脇線ではないため除外する必要がある。両者はy方向の到達点(y_top)の
    差(_CF_VS_SIDE_YTOP_DIFF_CM超か否か)で区別する
    (engine/darts.pyの`_bust_dart_zip_panel_side_index`と同じ判定軸)。

    【round12で加えた条件】脇線は必ずパーツの左右いずれかの端にある。
    round12でスクエアネックの首ぐりを引き直した際、その縦の辺(深さ5.8cm)が
    「十分に長い縦線」の条件を満たしてしまい、首ぐりの2辺まで脇線候補に
    数えられて候補4本→判定不能(None)になる、という不具合が実際に起きた。
    長さのしきい値を上げて誤魔化すのではなく、「脇線はパーツの端にある」と
    いう本来の性質を条件に加えて区別する(首ぐりはパーツの内側にあるので
    確実に除外できる)。

    【round26で一般化した点】脇線が**厳密に垂直**であることをやめた。
    裾をヒップに合わせるため、脇線は下へ向かってわずかに外へ開く
    (`engine/bodice_fit.py`の`hip_widening_cm`)。そのため

      * 垂直判定を「dx≈0」から「ほぼ垂直」(NEAR_VERTICAL_MAX_DX_RATIO)へ、
      * 「端にある」の判定を「パーツ全体の最小x/最大xと一致」から
        「**その高さでの**外側と一致」(`_x_range_at_y`)へ、
      * 合算を「同じxに乗る辺の長さの合計」から「同じ側(左/右)に属する辺の
        実長の合計」へ

    それぞれ一般化した。傾きが0の場合は従来とまったく同じ結果になる
    (tests/test_compatibility.py の脇線テストがそれを固定している)。

    想定外の形状(候補が0本、または左右どちらとも判定できない等)の場合は
    Noneを返し、呼び出し側で安全側に倒す(警告を出さない)。
    """
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return None

    #: 「その高さでの外側」と一致しているとみなす許容(cm)。ダーツで脇線が
    #: 断片化した箇所や、描線の丸めで数mmずれることがあるため。
    edge_tol = 0.5
    sides: dict[str, list[float]] = {"left": [], "right": []}
    y_tops: dict[str, list[float]] = {"left": [], "right": []}

    # round28: 辺ごとではなく「走り」でまとめる(side_seam_runs参照)。
    # ダーツで断片化した脇線も1本として数えられる。
    for _i, side, p1, p2 in side_seam_edges(points, edge_tol, underarm_y_of(part)):
        sides[side].append(_edge_length(p1, p2))
        y_tops[side].append(min(p1[1], p2[1]))

    # 【round66で直した実バグ】中心前(CF)と脇線を見分けるy_topを、
    # **脇の下で切り詰める前**の輪郭から取り直す。
    #
    # round31で`side_seam_edges`に「脇の下より上の辺は候補にしない」を
    # 足した。これ自体は正しい(後ろ袖ぐりが脇線と区別できなくなったため)
    # が、その結果**どの候補もy_topが脇の下の高さちょうどになる**。
    # 上の`y_tops`はその切り詰め後の値なので、どんな形でも差は0になり、
    # 下の「差が3cmを超えたら非対称」という判定は二度と成立しない。
    #
    # 実測(バスト88・前開き): 前身頃パネルの2本の縦線は
    #
    #     切り詰め無し  脇線 y_top=24.7 / 中心前の縁 y_top=8.1  → 差16.6cm
    #     脇の下で切る  脇線 y_top=24.7 / 中心前の縁 y_top=24.7 → 差0cm
    #
    # 差0で「左右対称な本物の脇線2本」とみなされ、中心前の縁(42.1cm)まで
    # 足して77.3cmになっていた。正しい脇線は35.2cmで、後ろ身頃の片側と
    # ぴったり同じである。長さは切り詰め後のものを使い、**見分けるための
    # y_topだけ**を切り詰め無しで取る。
    full_y_tops: dict[str, list[float]] = {"left": [], "right": []}
    for _i, side, p1, p2 in side_seam_edges(points, edge_tol, None):
        full_y_tops[side].append(min(p1[1], p2[1]))

    clusters = [(sum(lengths),
                 min(full_y_tops[side]) if full_y_tops[side] else min(y_tops[side]))
                for side, lengths in sides.items() if lengths]
    if not clusters:
        return None
    if len(clusters) == 1:
        return clusters[0][0]

    (len_a, ytop_a), (len_b, ytop_b) = clusters
    if abs(ytop_a - ytop_b) > _CF_VS_SIDE_YTOP_DIFF_CM:
        # 非対称: y_topが大きい方(=ネックラインから遠い方)が本物の脇線。
        return len_a if ytop_a > ytop_b else len_b
    # 対称: どちらも本物の脇線(front_bodice/back_bodiceの左右)なので合算する。
    return len_a + len_b


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


def shoulder_seam_length(part) -> float | None:
    """前身頃/後ろ身頃の**肩線**(左肩先 ⇔ 左の首の付け根)の長さを求める。

    round21で追加。前身頃と後ろ身頃で**違うネックライン**を組み合わせられる
    ようにしたことで、初めて「肩線の長さが前後で食い違う」組み合わせが
    作れるようになったため、それを検出する必要が生じた。

    測り方は`armhole_length`と同じく、`_bodice_path`
    (scripts/generate_templates.py)が保証している輪郭の並び順に依拠する。
    輪郭は必ず**左肩先から始まり**、一周して

        … → 右袖ぐり → 首ぐり → **肩線** → (Zで左肩先へ戻る)

    の順で閉じる。つまり**閉じる直前の1辺がちょうど肩線**である。首ぐりの
    形状(丸/V/角/ハート/台襟)に依存しないので、`neckline_length`が測れない
    タートルネックでも測れる。

    ダーツはこの辺を動かさない(脇ダーツは脇線に、ウエストダーツは裾に
    挿入される。engine/darts.pyの`_find_side_seam_segment_indices`・
    `_find_hem_segment_index`参照)ので、ダーツ追加後の輪郭でも同じ辺を指す。

    front_bodice_zip_panelには対応しない(`armhole_length`と同じ理由で、
    輪郭の先頭点が肩先である保証が無いため)。想定外の形状ではNoneを返す。
    """
    if part.part_type not in {"front_bodice", "back_bodice"}:
        return None
    points = _closed_points(part.stitch_line)
    if len(points) < 3:
        return None
    # 末尾は始点(左肩先)に戻っている。閉じる直前の「別の点」が首の付け根。
    end = points[-1]
    for i in range(len(points) - 2, -1, -1):
        if _edge_length(points[i], end) > _COORD_TOL:
            return _edge_length(points[i], end)
    return None


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

    # round26: 脇線は厳密な垂直ではなくなった(裾をヒップに合わせて開かせる
    # ため)。「同じx上の辺の長さの合計」で本物の脇線を見分ける方法は使えない
    # ので、`side_seam_length`と同じ判定——ほぼ垂直で、その高さでの外側に
    # 乗っている辺——に揃える。傾き0なら従来とまったく同じ結果になる。
    # round28: 打ち切り位置は「最初の脇線の**走り**の先頭」。辺ごとに見ると、
    # ダーツで脇線の上端が短く切れている場合にそこを見落とし、ダーツの斜辺
    # までを袖ぐりとして数えてしまう(side_seam_runs参照)。
    # round31: 脇の下の高さを渡す。後ろの袖ぐりはほぼ直線なので、
    # 形だけでは脇線と区別できない(`side_seam_edges`のdocstring参照)。
    stop = first_side_seam_index(points, underarm_y=underarm_y_of(part))
    if stop is None:
        return None  # 想定外の形状(脇線に到達しなかった)。
    total = sum(_edge_length(points[i], points[i + 1]) for i in range(stop))
    return total * 2.0


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


def seam_edge_path(points: list[tuple[float, float]], seam_edge: str) -> list[tuple[float, float]]:
    """帯状パーツの「相手に縫い付けられる辺」を、x最小側→x最大側の点列で返す
    (round16で`seam_edge_length`から切り出した)。

    長さを測るのにも(`seam_edge_length`)、その辺の上に合印を打つのにも
    (`engine/notches.py`)同じ辺の定義が要る。2箇所に別々の判定を書くと
    必ずずれるので、ここを唯一の定義元にする(実際、切り出す前は合印側の
    判定が襟先やボタンタブを辺に含めてしまい、長さの計測と食い違っていた)。

    判定は2段階:
      1. 宣言された側の端(y最小 or y最大)に沿って**連続して並ぶ**点列。
         衿・カフス・ウエストバンドのほとんどはここで決まる。襟先や
         ボタンタブのような張り出しはこの連続区間から外れるので、
         自動的に除かれる。
      2. その区間が外接矩形の幅の半分に満たない場合(=辺自体が曲線で、
         頂点付近がたまたま水平に見えているだけ。waistband/contourが該当)は、
         左右の端点を、宣言された側を通って結ぶ経路を使う。
    """
    if seam_edge not in ("top", "bottom") or len(points) < 3:
        return []
    ring = _closed_points(points)
    cycle = ring[:-1] if ring[0] == ring[-1] else list(ring)
    n = len(cycle)
    if n < 3:
        return []
    ys = [p[1] for p in cycle]
    xs = [p[0] for p in cycle]
    target_y = min(ys) if seam_edge == "top" else max(ys)
    span = max(xs) - min(xs)

    on_edge = [abs(p[1] - target_y) <= _COORD_TOL for p in cycle]
    best: list[tuple[float, float]] = []
    for start in range(n):
        if not on_edge[start] or (on_edge[start - 1] and start != 0):
            continue
        run = []
        i = start
        for _ in range(n):
            if not on_edge[i]:
                break
            run.append(cycle[i])
            i = (i + 1) % n
        if len(run) >= 2 and _path_length(run) > _path_length(best):
            best = run
    if best and (span <= 0 or _path_length(best) >= span * _MIN_SEAM_EDGE_SPAN_RATIO):
        return best if best[0][0] <= best[-1][0] else list(reversed(best))

    # 辺そのものが曲線のケース。
    min_x, max_x = min(xs), max(xs)

    def _pick(x_target: float) -> int:
        candidates = [i for i, p in enumerate(cycle) if abs(p[0] - x_target) <= _COORD_TOL]
        if not candidates:
            return -1
        key = (lambda i: cycle[i][1]) if seam_edge == "top" else (lambda i: -cycle[i][1])
        return min(candidates, key=key)

    i, j = _pick(min_x), _pick(max_x)
    if i < 0 or j < 0 or i == j:
        return []
    lo, hi = (i, j) if i < j else (j, i)
    path_a = cycle[lo:hi + 1]
    path_b = cycle[hi:] + cycle[:lo + 1]

    def _mean_y(path):
        return sum(p[1] for p in path) / len(path) if path else float("inf")

    if seam_edge == "top":
        path = path_a if _mean_y(path_a) <= _mean_y(path_b) else path_b
    else:
        path = path_a if _mean_y(path_a) >= _mean_y(path_b) else path_b
    return path if path and path[0][0] <= path[-1][0] else list(reversed(path))


def _path_length(path: list[tuple[float, float]]) -> float:
    return sum(_edge_length(a, b) for a, b in zip(path, path[1:])) if len(path) > 1 else 0.0


def seam_edge_length(part) -> float:
    """帯状パーツの「相手に縫い付けられる辺」の実際の長さを求める(round15)。

    どちらの辺が縫い付け側かはテンプレートSVGの`data-seam-edge`属性
    ("top"=y最小側 / "bottom"=y最大側)で宣言されており、
    `TemplateDB.get_seam_edge`→`engine/seam.py`の`finalize_part`経由で
    パーツに載っている。宣言が無いパーツでは外接矩形の幅(=`band_length`、
    round14までと同じ)へフォールバックする。

    辺の取り出し方は`seam_edge_path`(round16で共通化)に委ねる。
    """
    edge = getattr(part, "seam_edge", "")
    points = part.stitch_line
    if not edge or len(points) < 3:
        return band_length(part)
    path = seam_edge_path(points, edge)
    if len(path) < 2:
        return band_length(part)
    return _path_length(path)


def _mismatched(expected_cm: float, actual_cm: float) -> bool:
    if expected_cm <= 0:
        return False
    tolerance = max(_ABS_TOLERANCE_CM, expected_cm * _REL_TOLERANCE)
    return abs(expected_cm - actual_cm) > tolerance


def shoulder_seams_match(front_cm: float | None, back_cm: float | None) -> bool:
    """前後の肩線が「縫い合わせられる長さ」かどうかを判定する(round21)。

    `check_seam_compatibility`のチェック7とまったく同じ許容誤差を使う。
    別々に書くと、生成前のガードは通したのに生成後のチェッカーが警告する
    (あるいはその逆)という食い違いが起きうるため、判定を1か所に集約する。

    どちらかが測れない(None)場合はTrueを返す——測れないものを根拠に
    組み合わせを拒否はしない(チェッカー側も同じくスキップする)。
    """
    if front_cm is None or back_cm is None:
        return True
    return not _mismatched(back_cm, front_cm)


def _all(parts, part_types: set[str]) -> list:
    return [p for p in parts if p.part_type in part_types]


def hood_neck_edge_length(part) -> float | None:
    """フードの「首ぐりに縫い付ける辺」の弧長(round75で追加)。

    帯状パーツの汎用判定(`seam_edge_path`)は使えない。あれは「宣言された
    側の端に沿って並ぶ点列」か、それが短ければ「x最小の点とx最大の点を
    宣言された側を通って結ぶ経路」を採る。フードの**x最小の点は前上の角**
    (顔の開きのいちばん上)であって、付け根の端ではない。実測すると
    付け根18.6cmのフードに対して121.4cmという値が返り、
    「84.1cm一致していません」という警告が必ず出ていた。

    フードの付け根は、構造上こう取れる:

      * 起点 … いちばん低い点(前中心を2.5cm下げてあるので、ここが最下点)
      * 終点 … 中心後の下の角(xが最大)
      * その間、xは単調に増える

    この3つで一意に決まる。
    """
    if getattr(part, "part_type", "") != "hood":
        return None
    ring = _closed_points(part.stitch_line)
    cycle = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    if len(cycle) < 3:
        return None
    count = len(cycle)
    start = max(range(count), key=lambda i: (cycle[i][1], -cycle[i][0]))
    max_x = max(x for x, _y in cycle)
    for step in (1, -1):
        path = [cycle[start]]
        index = start
        for _ in range(count):
            nxt = (index + step) % count
            if cycle[nxt][0] < path[-1][0] - _COORD_TOL:
                break
            path.append(cycle[nxt])
            index = nxt
            if abs(cycle[nxt][0] - max_x) <= _COORD_TOL:
                break
        if len(path) >= 2 and abs(path[-1][0] - max_x) <= _COORD_TOL:
            return _path_length(path)
    return None


def _collar_or_hood_label(parts: list) -> str:
    """警告の文面で「衿」と「フード」を呼び分ける(round75)。"""
    kinds = {getattr(p, "part_type", "") for p in parts}
    if kinds == {"hood"}:
        return "フード"
    if "hood" in kinds:
        return "衿とフード"
    return "衿"


def check_seam_compatibility(finalized_parts: list) -> list[CompatibilityWarning]:
    """生成済みの全パーツから、縫い合わせ長さの不整合を検出する。

    パーツの組み合わせ自体が存在しない場合(例: スカートを選んでいない、
    カフスを選んでいない)は、その組み合わせのチェックを単純にスキップする
    (「無い物同士は比較しようがない」ため、警告にはしない)。
    """
    warnings: list[CompatibilityWarning] = []

    # 1. 前身頃(front_bodice/front_bodice_zip_panel) vs 後ろ身頃(back_bodice)の脇線。
    # round30: 切り替え線(プリンセスライン)で分けた場合、脇線は「脇パーツ」に
    # 乗る。左右2枚あるので、片方だけを見る(前後とも同じ数え方になる)。
    front_parts = _all(finalized_parts,
                       {"front_bodice", "front_bodice_zip_panel"})
    back_parts = _all(finalized_parts, {"back_bodice"})
    front_side_panels = _all(finalized_parts, {"front_bodice_side"})
    back_side_panels = _all(finalized_parts, {"back_bodice_side"})
    if front_side_panels and back_side_panels:
        # 左右2枚で1枚の身頃ぶん。前後をそろえるため、同じ枚数だけ取る。
        front_parts = front_side_panels[:1]
        back_parts = back_side_panels[:1]
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
            # round76: ドロップショルダーかどうかは、身頃が「下げた脇の下」を
            # 持っているかで分かる(`engine/drop_shoulder.py`)。生成側
            # (`engine/pipeline.py`の`_sleeve_target_cap_cm`)と同じ式を使う
            # ためにここで判定する——別々の式を持つと、生成した袖に対して
            # 「袖ぐりに合っていません」と誤った警告が出る。
            dropped = any(getattr(p, "underarm_y_cm", None) is not None
                          for p in armhole_front_parts + armhole_back_parts)

            sleeves_by_variation: dict[str, list] = {}
            for p in sleeve_parts:
                sleeves_by_variation.setdefault(p.variation, []).append(p)

            for variation, group in sleeves_by_variation.items():
                cap_lengths = [sleeve_cap_length(p) for p in group]
                if not all(v is not None for v in cap_lengths):
                    continue
                gather = SLEEVE_CAP_DESIGN_GATHER_CM.get(variation, 0.0)
                ease = sleeve_cap_ease_cm(armhole_per_arm, drop_shoulder=dropped)
                expected_per_sleeve = armhole_per_arm + ease + gather
                for part, cap in zip(group, cap_lengths):
                    if not _mismatched(expected_per_sleeve, cap):
                        continue
                    gather_note = (f"+デザイン上のギャザー{gather:.1f}cm" if gather else "")
                    warnings.append(CompatibilityWarning(
                        kind="armhole_sleeve_cap",
                        message=(
                            f"袖ぐり(片腕){armhole_per_arm:.1f}cm+いせ込み"
                            f"{ease:.1f}cm{gather_note}に対し、"
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
    # round75: フードも「首ぐりにぐるりと縫い付ける辺」を持つので、
    # 衿とまったく同じ見方で確かめる。引いた側(engine/hood.py)は付け根の
    # **弧長**が首ぐりの半分になるよう前端の位置を解いているが、
    # 解いた結果が本当にそうなっているかは、ここで測り直して確かめる。
    collar_parts = _all(finalized_parts, {"collar", "hood"})
    # 【round66で直した実バグ】ここは `{"front_bodice", "back_bodice"}` だった。
    # 前開き(front_zip)を選ぶと前身頃は`front_bodice_zip_panel`2枚になるので、
    # **前身頃がこの集合から静かに消えて、後ろ身頃だけが残る**。それでも
    # `all(v is not None)`は通ってしまうため、後ろだけの首ぐり(実測15.6cm)を
    # 「前+後で15.6cm」と名乗って衿(42.4cm)と比べ、**必ず**
    # 「26.8cm一致していません」と言っていた。実測では前開きを選んだ
    # 3体型×4構成のすべてで出ていた。
    #
    # `neckline_length`は`front_bodice_zip_panel`に対応していない
    # (輪郭の先頭点が肩先である保証が無い。同関数のdocstring参照)ので、
    # ここでは集合に入れて**Noneを出させ**、比較そのものを行わない。
    # 測れないものを、測ったふりで比べない。測れなかったことは
    # `unchecked_seams`が言葉で返す(黙って飛ばすと「確かめて問題なし」と
    # 区別が付かない)。
    neckline_parts = _all(finalized_parts,
                          {"front_bodice", "front_bodice_zip_panel", "back_bodice"})
    if collar_parts and neckline_parts:
        lengths = [neckline_length(p) for p in neckline_parts]
        if all(v is not None for v in lengths):
            neckline_total = sum(lengths)
            expected_collar = neckline_total + COLLAR_EASE_CM
            # round75: フードは付け根の取り方が衿と違う
            # (`hood_neck_edge_length`のdocstring参照)。
            collar_total = sum(
                (hood_neck_edge_length(p) if p.part_type == "hood"
                 else seam_edge_length(p)) or 0.0
                for p in collar_parts)
            if _mismatched(expected_collar, collar_total):
                warnings.append(CompatibilityWarning(
                    kind="neckline_collar",
                    message=(
                        f"身頃の首ぐりの長さ(前+後で{neckline_total:.1f}cm)に対し、"
                        f"{_collar_or_hood_label(collar_parts)}の首ぐり側の辺が"
                        f"{collar_total:.1f}cmで、"
                        f"{abs(expected_collar - collar_total):.1f}cm一致していません。"
                        "衿はこの辺を首ぐりにぐるりと縫い付けるため、差が大きいと"
                        "そのままでは付けられません。"
                    ),
                    expected_cm=expected_collar,
                    actual_cm=collar_total,
                ))

    # 7. 前身頃の肩線 vs 後ろ身頃の肩線。round21で追加。
    #    round20まで後身頃は必ず前身頃と同じネックラインだったため、
    #    肩線の長さが食い違う組み合わせは作れなかった。round21で前後別々の
    #    ネックラインを選べるようにしたことで、初めてこのチェックが要る。
    #
    #    実測(標準Mサイズのテンプレート、engine/compatibility.pyの
    #    `shoulder_seam_length`で測定):
    #      前後とも同じネックライン … 前12.79cm / 後12.48cm(差0.31cm)
    #        ※前が少し長いのは肩下がりが前後で違うため(意図した設計)。
    #      ボートネックと他を混ぜる … 差4.10〜4.89cm
    #        ※ボートネックだけ首の開きが1.75倍広く、そのぶん肩線が短い。
    #    許容誤差(_ABS_TOLERANCE_CM=1.5cm)は、前者を通し後者を捕らえる。
    shoulder_front_parts = _all(finalized_parts, {"front_bodice"})
    shoulder_back_parts = _all(finalized_parts, {"back_bodice"})
    if shoulder_front_parts and shoulder_back_parts:
        front_shoulders = [shoulder_seam_length(p) for p in shoulder_front_parts]
        back_shoulders = [shoulder_seam_length(p) for p in shoulder_back_parts]
        if (all(v is not None for v in front_shoulders)
                and all(v is not None for v in back_shoulders)):
            front_avg = sum(front_shoulders) / len(front_shoulders)
            back_avg = sum(back_shoulders) / len(back_shoulders)
            if not shoulder_seams_match(front_avg, back_avg):
                warnings.append(CompatibilityWarning(
                    kind="shoulder_seam",
                    message=(
                        f"前身頃の肩線({front_avg:.1f}cm)と後ろ身頃の肩線"
                        f"({back_avg:.1f}cm)が{abs(front_avg - back_avg):.1f}cm"
                        "一致していません。肩はこの2辺を縫い合わせるため、"
                        "差が大きいとそのままでは縫えません。"
                        "前後で首の開き幅が違うネックラインを組み合わせると起こります"
                        "(ボートネックは他より首の開きが1.75倍広く、そのぶん肩線が"
                        "短くなります)。"
                    ),
                    expected_cm=back_avg,
                    actual_cm=front_avg,
                ))

    return warnings


#: round66: 測れなかったので確かめていない組み合わせの、その理由。
#:
#: `check_seam_compatibility`は「測れないときは安全側に倒して警告を出さない」
#: という作りである。これは正しいが、**黙って飛ばすと「確かめた結果、
#: 問題なし」と区別が付かない**。前開きファスナー+衿の型紙は、衿の長さを
#: 一度も確かめないまま「警告なし」として出ていた。
#:
#: この製品の方針(`docs/はじめに.md`)は「分からないことは、分からないと書く」
#: なので、飛ばした組み合わせは言葉で返す。
def unchecked_seams(finalized_parts: list) -> list[str]:
    """縫い合わせ長さのうち、測れなかったため確かめていないものを返す。

    返すのは**警告ではない**(型紙がおかしいとは言っていない)。
    「ここは確かめていません」という事実だけである。
    呼び出し側は注記として扱う。
    """
    notes: list[str] = []

    # round75: フードは`hood_neck_edge_length`で測れるので、
    # 「測れなかった」の一覧には入れない。
    collar_parts = _all(finalized_parts, {"collar"})
    if collar_parts:
        neckline_parts = _all(finalized_parts,
                              {"front_bodice", "front_bodice_zip_panel",
                               "back_bodice"})
        measurable = [neckline_length(p) for p in neckline_parts]
        if not neckline_parts or not all(v is not None for v in measurable):
            notes.append(
                # round75: 引く側は割る前の前身頃を測って首ぐりに合わせて
                # いる(`_collar_target_length_cm`)。合わせた結果を**測り直す**
                # 手段がまだ無い、というのがここで言っていることである。
                "衿は身頃の首ぐりの長さに合わせて引いてありますが、"
                "出来上がった型紙で長さが合っているかは、この型紙では"
                "確かめていません（前開きや切り替え線で前身頃が分かれている"
                "型紙は、首ぐりの長さを測る方法をまだ持っていないためです）。"
                "衿を付ける前に、型紙の首ぐりに紙の衿を当てて長さを"
                "見比べてください。")

    return notes
