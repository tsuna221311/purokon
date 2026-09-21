"""generate_templates.py — 標準Mサイズのテンプレート型紙SVGをまとめて生成する。

このプロジェクトの型紙エンジンは「テンプレート＋変形」方式を採用している。
ここで生成する60種のSVGが、その"テンプレート"の実体(round9でネックライン
前開き対応の拡大・新バリエーション6種を追加。round8時点までは47種)。
各SVGは engine.templates_db.TemplateDB が読み込む1枚1パーツの標準Mサイズ原型で、
実際の採寸に合わせた変形は engine.scaling が行う。

寸法はJIS成人女子M相当（バスト84cm・ウエスト68cm・ヒップ92cm・身長160cm前後）を
基準に、パタンナー業務でよく使われる比率で概算した簡易原型。実務投入する場合は
本物のパタンナー監修の原型に差し替えることを推奨する（README参照）。

再実行すれば pattern_templates/ 以下のテンプレートを毎回同じ内容で再生成できる
（テンプレートは "データ" として versionable にしてある）。
"""

from __future__ import annotations
import os
import sys
from typing import NamedTuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_REPO_ROOT, "pattern_templates")
# front_bodice_zip_panel生成でengine.svgpath(パス解析・ポリライン化)を使うため、
# リポジトリルートをsys.pathへ追加する(python3 scripts/generate_templates.py の
# ように直接スクリプトとして実行すると、既定ではscripts/自身しかsys.pathに
# 乗らずimport engineが失敗するため)。
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine.bodice_fit import BODICE_EASE_CM, neck_half_cm  # noqa: E402


from engine import hood as _hood_module


def _segments_to_d(segments) -> str:
    """`engine/svgpath.py`のセグメント列を、SVGの"d"文字列に戻す。"""
    out = []
    for name, coords in segments:
        if name == "Z":
            out.append("Z")
        else:
            out.append(name + " " + " ".join(f"{v:.3f}" for v in coords))
    return " ".join(out)


def _write(filename: str, part: str, variation: str, width: str, height: str,
           view_w: float, view_h: float, d: str, comment: str,
           fit_x: str | None = None, seam_edge: str | None = None,
           fit_y: str | None = None) -> None:
    """テンプレートSVGを1枚書き出す。

    fit_x は round14 で追加した「体型合わせの基準点(X座標)」。
    `engine/bodice_fit.py`が、身頃を採寸に合わせて変形するときに
    「この点は肩先」「この点は首の付け根」と知るために使う
    (詳細は`_bodice_anchors`のコメントを参照)。テンプレート本体と
    同じファイルに持たせているのは、テンプレートの寸法を変えたときに
    基準点だけが古いまま取り残される(engine側に定数として二重に
    持つと必ず起きる)のを構造的に防ぐため。

    seam_edge は round15 で追加した「相手に縫い付けられる辺はどちらか」
    ("top"=y最小側 / "bottom"=y最大側)。衿・カフス・ウエストバンドのような
    帯状パーツで使う。round14まで、これらのパーツの長さは**外接矩形の幅**で
    測られていたが、実際に縫い付けられる辺は矩形の幅と一致しない
    (例: シャツカラーは左右に襟先が張り出すので外接矩形40cmに対し縫い付け辺は
    32cm、ボタンタブ付きカフスは外接矩形24cmに対し20cm)。詳細は
    `engine/compatibility.py`の`seam_edge_length`を参照。
    """
    attrs = ""
    if fit_x:
        attrs += f'\n    data-fit-x="{fit_x}"'
    if fit_y:
        # round23で追加した「体型合わせの基準線(Y座標)」。袖ぐりの深さを
        # バストに応じて変えるために、engine/bodice_fit.pyが
        # 「この線が首の付け根」「この線が脇の下」「この線が裾」と知る必要がある。
        attrs += f'\n    data-fit-y="{fit_y}"'
    if seam_edge:
        attrs += f'\n    data-seam-edge="{seam_edge}"'
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {view_w} {view_h}">
  <!-- {comment} -->
  <path
    data-part="{part}"
    data-variation="{variation}"{attrs}
    fill="none" stroke="black" stroke-width="0.1"
    d="{d}" />
</svg>
'''
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", path)


# ---------------------------------------------------------------------------
# 身頃原型(round12で全面的に作り直した)
# ---------------------------------------------------------------------------
#
# 【作り直した理由】round11までの身頃は、標準体型(バスト83cm)で
# 前身頃30cm+後身頃30cm=胴回り60cmしかなく、バストに対して31cm不足していた
# (バスト100cmの体型でも72cmで約36cm不足)。実寸1:1で印刷して裁っても着られない
# 寸法である。原因は、輪郭が「肩線」を独立した線分として持たず、ネックラインの
# 曲線が左右の肩先を直接つないでいたことにある。この構造だと、
#   - 胴回りだけ広げると肩幅が取り残されて袖ぐりが異常に大きくなる
#   - 肩幅を広げるとネックラインの開きが肩幅と同じだけ広がってしまう
# ため、寸法だけの調整では直せなかった。round12で肩線とネックラインを分離した
# 身頃原型に作り直した。
#
# 【寸法の導出】いずれもSTANDARD_M(バスト83・肩幅37・身長158)から、
# 文化式婦人原型で一般に使われる算出式を単純化して求めている。
# 「それらしい曲線を当てずっぽうで描く」ことは避け、各値の根拠を残す。
# 着用ゆとり(布帛の身頃で一般的な範囲)。round23から engine/bodice_fit.py に
# 置いてある——採寸に合わせて身頃の幅を決め直すのに同じ値が必要で、
# 二重に書くとずれるため(neck_half_cmと同じ理由)。
_STD_BUST, _STD_SHOULDER, _STD_HEIGHT = 83.0, 37.0, 158.0

BODICE_W = (_STD_BUST + BODICE_EASE_CM) / 2      # 1枚の幅 = 胴回りの半分 = 45.5
BODICE_CF = BODICE_W / 2                          # 中心前(中心後) = 22.75
_SHOULDER_HALF = _STD_SHOULDER / 2                # 中心から肩先まで = 18.5
BODICE_SHOULDER_L = BODICE_CF - _SHOULDER_HALF    # 左肩先 x = 4.25
BODICE_SHOULDER_R = BODICE_CF + _SHOULDER_HALF    # 右肩先 x = 41.25
# 首幅の式は engine/bodice_fit.py に置いてある(採寸に合わせて首幅を
# 決め直すのに同じ式が必要で、二重に書くとずれるため)。バスト83で6.86cm。
BODICE_NECK_HALF = neck_half_cm(_STD_BUST)        # 首幅(中心から片側) = 6.86
BODICE_DROP_F = _STD_HEIGHT / 20 - 2.6            # 前肩下がり = 5.30
BODICE_DROP_B = BODICE_DROP_F - 0.8               # 後肩下がり = 4.50(前より水平寄り)
BODICE_AH_DEPTH = 23.5                            # 首の付け根の線から脇の下まで
BODICE_HEM = 58.0                                 # 首の付け根の線から裾まで(ヒップ丈)
#: 首の付け根の線からウエストまで(背丈)。JIS成人女子M相当の背丈は約38cm。
#: round26で追加。裾(ヒップ丈)とウエストは別の高さなので、ウエストで絞り、
#: そこから裾へ向かってヒップに合わせて開く、という形を作るのに要る。
BODICE_WAIST_Y = 38.0
# 袖ぐり曲線が弦からえぐれる量。1.5〜3cm程度が自然な範囲で、この値のとき
# 袖ぐり(片腕)は前19.5cm+後20.2cm=39.7cmになる。バスト83の標準的な袖ぐり
# (概ねバスト/2=41.5cm前後)に収まる値として選んだ
# (袖ぐり深さを浅くすると必要なえぐれ量が非現実的に大きくなるため、
#  深さ23.5cmとえぐれ2.5cmの組み合わせを実測で選定している)。
BODICE_AH_SCOOP = 2.5
#: 前首ぐりの深さ(中心前での落ち込み)。
BODICE_NECK_DEPTH_F = _STD_BUST / 24 + 4.3        # = 7.76
#: 後首ぐりの深さ。前より浅くするのが通例。
BODICE_NECK_DEPTH_B = 2.5


def _armhole_d(from_shoulder: bool, shoulder_x: float, side_x: float,
                drop: float, shift: float, scoop: float = BODICE_AH_SCOOP) -> str:
    """肩先と脇の下を結ぶ袖ぐり曲線(C1本)を組み立てる。

    from_shoulder=Trueなら肩先→脇の下、Falseなら脇の下→肩先の向きで返す
    (輪郭を一周する向きに合わせるため)。scoopは弦から身頃の内側へ
    えぐれる量で、これが袖ぐりの曲線長を決める。
    """
    sign = 1.0 if side_x < shoulder_x else -1.0   # 内側(中心)へ向かう向き
    sy = shift + drop
    ey = shift + BODICE_AH_DEPTH
    dy = ey - sy
    c_shoulder = (shoulder_x + sign * scoop * 1.05, sy + dy * 0.40)
    c_side = (side_x + sign * scoop * 1.25, sy + dy * 0.75)
    if from_shoulder:
        return (f" C {c_shoulder[0]:.3f} {c_shoulder[1]:.3f},"
                f" {c_side[0]:.3f} {c_side[1]:.3f}, {side_x:.3f} {ey:.3f}")
    return (f" C {c_side[0]:.3f} {c_side[1]:.3f},"
            f" {c_shoulder[0]:.3f} {c_shoulder[1]:.3f}, {shoulder_x:.3f} {sy:.3f}")


def _bodice_path(neck: "Neckline", drop: float, body_shift: float = 0.0) -> str:
    """前身頃・後身頃で共通の輪郭を組み立てる。

    輪郭を回る順序は、既存の幾何処理が前提にしている性質を保つように
    決めてある(この順序を変えると各所が壊れる):

      1. 先頭(M)は必ず左肩先。`engine/compatibility.py`の`armhole_length`が
         「輪郭の先頭から最初の長い縦線(脇線)までが袖ぐり」という前提で
         測っているため。
      2. 脇線は左右それぞれ1本の長い縦のLセグメント。
         `engine/compatibility.py`の`side_seam_length`が「縦線がちょうど2本」を
         前提にし、`engine/darts.py`の`_find_side_seam_segment_indices`も
         同じ条件で脇ダーツの挿入位置を探すため。
      3. 裾は最もyが大きい水平のLセグメント1本。`engine/darts.py`の
         `_find_hem_segment_index`がウエストダーツの挿入位置に使うため。
      4. 中心前(中心後)はちょうど左右の肩先の中点。
         `_front_zip_panel_d`が中心前をこの中点として求めるため。

    肩線(肩先と首の付け根を結ぶ斜めの直線)は、上記2の「縦線」条件にも
    3の「水平線」条件にも当てはまらないため、これらの検出を乱さない。

    【round14で直した不具合】首の付け根のx座標を、首ぐりの種類によらず
    常に`BODICE_NECK_HALF`で計算していた。ボートネックだけは
    `_neckline_d`側で開きを1.75倍に広げているため、肩線の終点
    (=BODICE_NECK_HALF基準)と首ぐり曲線の終点(=1.75倍基準)が食い違い、
    **左右非対称な身頃**になっていた(左の首の付け根x=10.75、右x=29.61。
    肩線の水平方向の長さが左6.5cm・右11.6cmと2倍近く違う)。実際に
    輪郭を描画して発見した。首ぐり側が実際に使った開き幅
    (`Neckline.half_width`)をここへ渡すようにして解消した。
    """
    sl, sr = BODICE_SHOULDER_L, BODICE_SHOULDER_R
    neck_l = BODICE_CF - neck.half_width
    neck_r = BODICE_CF + neck.half_width
    hem_y = body_shift + BODICE_HEM
    ah_y = body_shift + BODICE_AH_DEPTH
    return (
        f"M {sl:.3f} {body_shift + drop:.3f}"
        + _armhole_d(True, sl, 0.0, drop, body_shift)
        + f" L 0 {hem_y:.3f}"
        + f" L {BODICE_W:.3f} {hem_y:.3f}"
        + f" L {BODICE_W:.3f} {ah_y:.3f}"
        + _armhole_d(False, sr, BODICE_W, drop, body_shift)
        + f" L {neck_r:.3f} {body_shift:.3f}"
        + f" {neck.d}"
        + f" L {sl:.3f} {body_shift + drop:.3f}"
        + " Z"
    )


def _bodice_anchors(neck_half: float) -> str:
    """身頃テンプレートの「体型合わせの基準点」(X座標)を書き出す。

    round14で追加。身頃は round13 まで、X方向を**バスト比で一律に**
    拡大縮小していた。その結果、利用者が入力した肩幅がまったく使われず、
    肩幅までバスト比で決まっていた(実測で最大+10.9cm/-6.2cmの誤差)。
    首の開きも同じ理由でバスト比そのままに広がっていた。

    ここで基準点を明示しておくと、`engine/bodice_fit.py`が
      脇線 … バストで決まる
      肩先 … 入力された肩幅で決まる
      首の付け根 … 文化式の前ネック幅(B/24+3.4)で決まる
    という具合に、区間ごとに違う倍率で変形できる(区分線形の写像)。

    役割(role)の意味:
      side     … 脇線(パーツの左右端)。バスト比で動く。
      shoulder … 肩先。入力肩幅で動く。
      neck     … 首の付け根(肩線と首ぐりの境目)。ネック幅の式で動く。
      cf       … 中心前(中心後)。左右対称の中心。
      cut      … 前開きパネルの裁ち割り線(中心前から見返し幅ぶん外側)。
                 見返し幅は体型によらず一定なので、cfからの距離を保つ。
    """
    return " ".join([
        "side:0.000",
        f"shoulder:{BODICE_SHOULDER_L:.3f}",
        f"neck:{BODICE_CF - neck_half:.3f}",
        f"cf:{BODICE_CF:.3f}",
        f"neck:{BODICE_CF + neck_half:.3f}",
        f"shoulder:{BODICE_SHOULDER_R:.3f}",
        f"side:{BODICE_W:.3f}",
    ])


def _bodice_y_anchors(body_shift: float = 0.0) -> str:
    """身頃テンプレートの「体型合わせの基準線」(Y座標)を書き出す(round23)。

    役割(role)の意味:
      neck     … 首の付け根の線(丈を測る基準)。身長比で動く。
      waist    … ウエストの線(背丈)。身長比で動く。round26で追加。
                 ここから裾へ向かって、脇線をヒップに合わせて開かせる。
      underarm … 脇の下の線。身長比に加え、バストに応じて深くなる
                 (文化式の袖ぐり深さ B/12+13.7 の増分。
                  engine/bodice_fit.py の `armhole_depth_cm` 参照)。
      hem      … 裾。身長比で動く(着丈は身長で決まる)。

    round22まではY方向を身長比で一律に伸縮していたため、袖ぐりの深さが
    バストでほとんど変わらず、バスト130cmで文化式の目安より3.9cm浅い
    (=脇が食い込む)型紙が出ていた。
    """
    return " ".join([
        f"neck:{body_shift:.3f}",
        f"underarm:{body_shift + BODICE_AH_DEPTH:.3f}",
        f"waist:{body_shift + BODICE_WAIST_Y:.3f}",
        f"hem:{body_shift + BODICE_HEM:.3f}",
    ])


class Neckline(NamedTuple):
    """首ぐりの曲線と、それが実際に使った開き幅(中心から片側)。

    round14で`str`から変更した。`_bodice_path`が肩線の終点を決めるのに
    「首ぐりが実際に使った開き幅」を知る必要があるため
    (知らずにBODICE_NECK_HALF固定で描いていたのがボートネックの
    左右非対称の原因だった)。
    """
    d: str
    half_width: float


def _neckline_d(kind: str, body_shift: float = 0.0, depth: float | None = None,
                 half_width: float | None = None, stand: float = 0.0) -> Neckline:
    """首ぐりの曲線(右の首の付け根 → 左の首の付け根)を組み立てる。

    `_bodice_path`が肩線を別に描くようになったため、ここは純粋に
    「首の開き」だけを表す。round11までは肩先どうしを直接つないでいたので、
    首の開きと肩幅を独立に決められなかった(この関数を分けた目的)。

    kind:
      round     … 丸首。中心で`depth`だけ落ち込む。
      v         … Vネック。中心の1点まで直線で落ちる。
      square    … スクエアネック。角ばった浅いスコップ。
      boat      … ボートネック。`half_width`を広げ、浅く水平に近い開き。
      sweetheart… スウィートハート。中央がハート型に2つの丸みで凹む。
      turtle    … タートル。首ぐりは水平に閉じ、`stand`の高さの台襟を立てる。
    """
    cf = BODICE_CF
    hw = half_width if half_width is not None else BODICE_NECK_HALF
    nl, nr = cf - hw, cf + hw
    y0 = body_shift
    d = depth if depth is not None else BODICE_NECK_DEPTH_F

    if kind == "round":
        # 中心での落ち込みが実際にdepthになるよう、制御点は約4/3倍の位置に置く
        # (3次ベジエの中点は制御点のy平均の3/4になるため)。
        cy = y0 + d * 4.0 / 3.0
        return Neckline(f"C {nr - hw * 0.30:.3f} {cy:.3f}, {nl + hw * 0.30:.3f} {cy:.3f}, {nl:.3f} {y0:.3f}", hw)
    if kind == "v":
        return Neckline(f"L {cf:.3f} {y0 + d:.3f} L {nl:.3f} {y0:.3f}", hw)
    if kind == "square":
        return Neckline(f"L {nr:.3f} {y0 + d:.3f} L {nl:.3f} {y0 + d:.3f} L {nl:.3f} {y0:.3f}", hw)
    if kind == "boat":
        cy = y0 + d * 4.0 / 3.0
        return Neckline(f"C {nr - hw * 0.22:.3f} {cy:.3f}, {nl + hw * 0.22:.3f} {cy:.3f}, {nl:.3f} {y0:.3f}", hw)
    if kind == "sweetheart":
        # 中央に緩やかな山を作り、その左右を丸くくぼませる(ハート型)。
        #
        # round12で形を作り直した際、当初は首の付け根のすぐ隣から急に深く
        # 落とす制御点にしていたため、実際にレンダリングして確認すると
        # 丸みではなく左右2本の尖った切れ込みになっていた。首の付け根の
        # 直後はほぼ横方向に出てから丸くくぼむよう制御点を置き直した
        # (3案を描き比べて選定)。
        peak_y = y0 + d * 0.42
        return Neckline(f"C {cf + hw * 0.98:.3f} {y0 + d * 0.55:.3f},"
                        f" {cf + hw * 0.62:.3f} {y0 + d * 1.10:.3f}, {cf:.3f} {peak_y:.3f}"
                        f" C {cf - hw * 0.62:.3f} {y0 + d * 1.10:.3f},"
                        f" {cf - hw * 0.98:.3f} {y0 + d * 0.55:.3f}, {nl:.3f} {y0:.3f}", hw)
    if kind == "turtle":
        # 台襟の付け根まで垂直に立ち上げ、水平に渡してから下りる。
        top = y0 - stand
        return Neckline(f"L {nr:.3f} {top:.3f} L {nl:.3f} {top:.3f} L {nl:.3f} {y0:.3f}", hw)
    raise ValueError(f"未知のネックライン種別: {kind}")


FACING_WIDTH_CM = 4.0  # 前開きファスナー用の見返し(facing)幅の既定値。


def _front_zip_panel_d(neck: "Neckline", facing_width: float = FACING_WIDTH_CM) -> str:
    """前開きファスナー用に、front_bodiceを中心前で実際に分割した右半分の
    輪郭を作り、見返し(facing)分の折り返し代を追加した"d"文字列を返す。

    round5より前は、front_zip=Trueにしても前身頃は「ネックライン形状を
    ファスナー用に浅くしただけの、輪郭は従来通り1枚の対称パーツ」という
    簡易版だった（実際に中心前を裁ち割りにする構造は未実装）。ここでは
    `_bodice_path`で組み立てた対称な輪郭を、中心前のx座標(shoulder_lと
    shoulder_rの中点)で実際に幾何的に分割する。カーブ(ベジエ)を含む
    複雑な輪郭を手計算で正確に半分に割るのは誤りやすいため、
    `engine.svgpath`でポリライン化した上でshapelyの半平面交差
    (intersection)を使い、数値的に正確な分割点を求める。

    分割してできた中心前の縁(直線)に沿って、外側(中心からさらに離れる
    方向)へfacing_width分だけ矩形状に張り出させることで、ファスナーを
    縫い付けるための見返し分量を輪郭そのものに含める。

    正直な範囲の限定: 実際の見返しは縁の形状(ネックライン等)に沿って
    幅が一定になるように成形されることが多いが、ここでは単純な矩形の
    張り出しで近似している。また、折り返し線(fold line)自体を型紙上に
    破線で示す機能は無く、輪郭に見返し分の生地を含めているだけである
    （縫い代線・合印・布目線と同様の「表示用アノテーション」は今回は
    見返しの折り返し線には対応していない）。左右対称な2枚(左パネル・
    右パネル)を使う想定で、ここではその片側分だけを生成する
    (PAIR_LABELSの"front_bodice_zip_panel": ("左","右")で両方使う)。
    """
    import shapely.geometry as sg

    from engine.svgpath import parse_path, segments_to_polyline

    cut_x = BODICE_CF
    d_full = _bodice_path(neck, BODICE_DROP_F, body_shift=0.0)
    segments = parse_path(d_full)
    pts = segments_to_polyline(segments, curve_steps=24)
    closed = pts[:-1] if pts[0] == pts[-1] else pts
    full_poly = sg.Polygon(closed)

    minx, miny, maxx, maxy = full_poly.bounds
    half_plane = sg.box(cut_x, miny - 10, maxx + 10, maxy + 10)
    right_half = full_poly.intersection(half_plane)
    coords = list(right_half.exterior.coords)[:-1]  # 最後は最初と重複する閉環なので除く

    # 中心線(x≈cut_x)上にある2点(ネックライン側・裾側)を見つける。
    on_cut = [i for i, (x, _y) in enumerate(coords) if abs(x - cut_x) < 1e-6]
    if len(on_cut) != 2:
        raise RuntimeError(
            f"front_bodice_zip_panelの中心前分割に失敗しました(cut_x={cut_x}上の"
            f"点が{len(on_cut)}個見つかりました。2個である必要があります)。"
        )
    i, j = sorted(on_cut)
    # coordsはi,jが隣り合っているはず(中心線に沿った直線区間がそのまま
    # 1区間として残るため)。隣り合っていない場合は分割の前提が崩れている。
    if j != i + 1 and not (i == 0 and j == len(coords) - 1):
        raise RuntimeError("front_bodice_zip_panelの中心前分割の頂点順序が想定と異なります。")

    top_pt, bottom_pt = coords[i], coords[j]
    top_flap = (cut_x - facing_width, top_pt[1])
    bottom_flap = (cut_x - facing_width, bottom_pt[1])

    new_coords = coords[:i + 1] + [top_flap, bottom_flap] + coords[j:]
    parts = [f"M {new_coords[0][0]:.3f} {new_coords[0][1]:.3f}"]
    for x, y in new_coords[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    parts.append("Z")
    return " ".join(parts)


MARGIN = 2  # パンツパーツ左右の余白(見た目のバランス用。原点0との衝突を避ける)


# ---------------------------------------------------------------------------
# パンツ(round12(続き)で寸法を作り直した)
# ---------------------------------------------------------------------------
#
# 【作り直した理由】round11までのパンツは、標準体型(ウエスト66・ヒップ91)で
#   - ウエスト周が4枚合わせて40cm(必要68cmに対し28cm不足)
#   - 裾幅が1枚4cm = 脚まわり8cm(足首が通らない)
#   - 股上が総丈100cmのうち50cmと、実際(約25cm)の倍
# という状態で、身頃・袖・スカートと同じく型紙として成立していなかった。
#
# 【寸法の導出】STANDARD_M(ウエスト66・ヒップ91・身長158)から:
#   1枚(前または後の片脚)あたり
#     ウエスト側 = (66 + ゆとり2) / 4 = 17cm
#     ヒップ側   = (91 + ゆとり4) / 4 = 23.75cm
#     ヒップの位置 = ウエストから18cm下
#     股上(ウエスト〜股ぐり) = 身長/8 + 5 = 24.75 → 25cm
#     股下(股ぐり〜裾)       = 身長 × 0.45 = 71cm
#     総丈 = 96cm
#     股ぐりの出し(中心線より内側への張り出し) = 前 ヒップ/16 ≒ 5.7cm /
#                                                後 ヒップ/10 ≒ 9.1cm
#   後ろの股ぐりを前より大きく出すのは実務の定石(臀部の厚みを吸収するため)。
PANTS_WAIST_QUARTER = 17.0     # ウエスト側(中心線→脇線)
PANTS_HIP_QUARTER = 23.75      # ヒップ側(中心線→脇線)
PANTS_HIP_Y = 18.0             # ウエストからヒップまで
PANTS_RISE = 25.0              # 股上(ウエスト〜股ぐり)
PANTS_FRONT_CROTCH_EXT = 5.7   # 前の股ぐりの出し
PANTS_BACK_CROTCH_EXT = 9.1    # 後ろの股ぐりの出し


def _pants_panel_d(hem_half: float, length: float, is_back: bool) -> str:
    """パンツの前パーツ/後ろパーツで共通の輪郭を組み立てる。

    座標系: x=0 が股ぐりの最も内側(股ぐりの出しの先端)、
    中心線(センターフロント/センターバック)は x=ext、脇線は x=ext+ヒップ幅。
    y=0 がウエストライン、下へ向かって増える。

    輪郭を回る順序は、既存の幾何処理が前提にしている性質に合わせてある:
      - 上端(ウエストライン)は最もyが小さい水平のLセグメント。
        `engine/darts.py`の`_find_top_edge_segment_index`がウエストダーツの
        挿入位置に使う。
      - 中心線・脇線は縦の直線で、ダーツ挿入の邪魔をしない。

    hem_half: 裾でのこのパーツの幅(脚まわりの半分)。
    """
    ext = PANTS_BACK_CROTCH_EXT if is_back else PANTS_FRONT_CROTCH_EXT
    cx = ext                                   # 中心線
    side_waist = ext + PANTS_WAIST_QUARTER     # ウエストの脇側
    side_hip = ext + PANTS_HIP_QUARTER         # ヒップの脇側
    leg_axis = ext + PANTS_HIP_QUARTER / 2     # 脚のおおよその中心
    hem_out = leg_axis + hem_half / 2
    hem_in = leg_axis - hem_half / 2
    rise = PANTS_RISE

    # 後ろは中心線を外側へわずかに膨らませ、臀部のゆとりを表現する。
    cb_bulge = 1.6 if is_back else 0.0

    return (
        # ウエストライン(中心 → 脇)
        f"M {cx:.2f} 0 L {side_waist:.2f} 0"
        # 脇線: ウエスト → ヒップ(外へ張り出す) → 裾
        f" C {side_waist + 1.2:.2f} {PANTS_HIP_Y * 0.45:.2f},"
        f" {side_hip:.2f} {PANTS_HIP_Y * 0.7:.2f}, {side_hip:.2f} {PANTS_HIP_Y:.2f}"
        f" L {hem_out:.2f} {length:.2f}"
        # 裾
        f" L {hem_in:.2f} {length:.2f}"
        # 股下(インシーム): 裾 → 股ぐりの先端
        f" L 0 {rise:.2f}"
        # 股ぐりのカーブ: 先端 → 中心線(ヒップの高さ付近で合流)
        f" C {ext * 0.35:.2f} {rise - 4.5:.2f}, {cx:.2f} {rise - 3.0:.2f},"
        f" {cx:.2f} {PANTS_HIP_Y:.2f}"
        # 中心線: ヒップ → ウエスト(後ろはわずかに外へ膨らむ)
        + (f" C {cx - cb_bulge:.2f} {PANTS_HIP_Y * 0.6:.2f},"
           f" {cx - cb_bulge:.2f} {PANTS_HIP_Y * 0.3:.2f}, {cx:.2f} 0"
           if is_back else f" L {cx:.2f} 0")
        + " Z"
    )


def front_bodice(variation: str, neck: Neckline, comment: str,
                  extra_h: float = 0.0, body_shift: float = 0.0) -> None:
    """前身頃を書き出す。身頃本体(肩線・袖ぐり・脇線・裾)は共通で、
    首ぐり部分(neck)だけ差し替える。"""
    d = _bodice_path(neck, BODICE_DROP_F, body_shift)
    _write(f"front_bodice__{variation}.svg", "front_bodice", variation,
           f"{BODICE_W:g}cm", f"{BODICE_HEM + extra_h:g}cm",
           BODICE_W, BODICE_HEM + extra_h, d, comment,
           fit_x=_bodice_anchors(neck.half_width),
           fit_y=_bodice_y_anchors(body_shift))


def back_bodice(variation: str, neck: Neckline, comment: str,
                 extra_h: float = 0.0, body_shift: float = 0.0) -> None:
    d = _bodice_path(neck, BODICE_DROP_B, body_shift)
    _write(f"back_bodice__{variation}.svg", "back_bodice", variation,
           f"{BODICE_W:g}cm", f"{BODICE_HEM + extra_h:g}cm",
           BODICE_W, BODICE_HEM + extra_h, d, comment,
           fit_x=_bodice_anchors(neck.half_width),
           fit_y=_bodice_y_anchors(body_shift))


def front_bodice_zip_panel(variation: str, neck: Neckline, comment: str) -> None:
    """前開きファスナー用に中心前で分割した前身頃の片側パネルを書き出す。

    `_front_zip_panel_d`が実際の分割・見返し追加を行う。viewBoxの幅は
    「右半分の最大x座標(=身頃の幅) - 中心前x座標 + 見返し幅」に、
    余白として少し足して決める。
    """
    d = _front_zip_panel_d(neck)
    view_w = BODICE_W - (BODICE_CF - FACING_WIDTH_CM) + 1
    # 前開きパネルは中心前より右(=右半身)だけを持つ片側パーツなので、
    # 基準点も右半分と裁ち割り線ぶんだけを書き出す(座標系は身頃と共通で、
    # 平行移動していないためx座標はそのまま使える)。
    fit_x = " ".join([
        f"cut:{BODICE_CF - FACING_WIDTH_CM:.3f}",
        f"cf:{BODICE_CF:.3f}",
        f"neck:{BODICE_CF + neck.half_width:.3f}",
        f"shoulder:{BODICE_SHOULDER_R:.3f}",
        f"side:{BODICE_W:.3f}",
    ])
    _write(f"front_bodice_zip_panel__{variation}.svg", "front_bodice_zip_panel", variation,
           f"{view_w:g}cm", f"{BODICE_HEM:g}cm", view_w, BODICE_HEM, d, comment,
           fit_x=fit_x, fit_y=_bodice_y_anchors())


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 前身頃 6種 -----------------------------------------------------
    #
    # round12で、首ぐりを生のパス文字列ではなく`_neckline_d`による宣言的な
    # 指定に改めた。round11までは肩先どうしを結ぶ曲線に絶対座標を直接
    # 書いており、身頃の寸法を変えるたびに15種すべてを手で引き直す必要が
    # あった(そして肩幅と首の開きを独立に決められなかった)。
    front_bodice("round_neck", _neckline_d("round"),
                 "前身頃テンプレート(標準Mサイズ) ラウンドネック")
    front_bodice("v_neck", _neckline_d("v", depth=BODICE_NECK_DEPTH_F + 6),
                 "前身頃テンプレート(標準Mサイズ) Vネック")
    front_bodice("turtle_neck",
                 _neckline_d("turtle", body_shift=4, stand=4),
                 "前身頃テンプレート(標準Mサイズ) タートルネック"
                 "(首ぐりを水平に閉じ、高さ4cmの台襟を立てた形)",
                 extra_h=4, body_shift=4)
    front_bodice("square_neck", _neckline_d("square", depth=BODICE_NECK_DEPTH_F - 2),
                 "前身頃テンプレート(標準Mサイズ) スクエアネック(角ばった浅いスコップ)")
    front_bodice("boat_neck",
                 _neckline_d("boat", depth=2.5, half_width=BODICE_NECK_HALF * 1.75),
                 "前身頃テンプレート(標準Mサイズ) ボートネック"
                 "(首の開きを左右に広げ、浅く水平に近いカーブにした形。"
                 "round11までは肩幅点そのものを広げて再現していたが、"
                 "round12で肩線と首ぐりを分離したため、首の開きだけを広げられる)")
    front_bodice("sweetheart", _neckline_d("sweetheart", depth=BODICE_NECK_DEPTH_F + 2),
                 "前身頃テンプレート(標準Mサイズ) スウィートハートネック"
                 "(中央がハート型に浅くくぼむ、2つの丸みが連なる首ぐり)")

    # 前開きファスナー用の前パネル(round5で実際に中心前を裁ち割りにする構造
    # へ変更。詳細は_front_zip_panel_dのdocstring参照)。part_typeは
    # front_bodice(通常の前身頃)ではなく front_bodice_zip_panel。
    # 見返し分を追加した左右対称の片側パネルを1枚だけ生成し、実際の生成では
    # PAIR_LABELS経由で2枚(左右)使う。
    #
    # round11までは、前開き版のために肩点をずらした別の座標を手で用意して
    # いたが(そのぶん首ぐりも引き直しが必要だった)、round12で肩線と首ぐりを
    # 分離したので、非ファスナー版とまったく同じ首ぐり指定をそのまま使える。
    # タートルネックだけは台襟と前立てが干渉するため対象外(従来通り)。
    front_bodice_zip_panel("round_neck", _neckline_d("round"),
                            "前開きファスナー用 前パネル(標準Mサイズ・片側) ラウンドネック。"
                            "中心前で分割し、見返し(facing)分を追加した実寸法。")
    front_bodice_zip_panel("v_neck", _neckline_d("v", depth=BODICE_NECK_DEPTH_F + 6),
                            "前開きファスナー用 前パネル(標準Mサイズ・片側) Vネック。"
                            "中心前で分割し、見返し(facing)分を追加した実寸法。")
    front_bodice_zip_panel("square_neck", _neckline_d("square", depth=BODICE_NECK_DEPTH_F - 2),
                            "前開きファスナー用 前パネル(標準Mサイズ・片側) スクエアネック。")
    front_bodice_zip_panel("boat_neck",
                            _neckline_d("boat", depth=2.5, half_width=BODICE_NECK_HALF * 1.75),
                            "前開きファスナー用 前パネル(標準Mサイズ・片側) ボートネック。")
    front_bodice_zip_panel("sweetheart", _neckline_d("sweetheart", depth=BODICE_NECK_DEPTH_F + 2),
                            "前開きファスナー用 前パネル(標準Mサイズ・片側) スウィートハートネック。")

    # --- 後身頃 6種(前より首ぐりが浅い) --------------------------------
    #
    # 後ろの首ぐりは前より浅くするのが通例(BODICE_NECK_DEPTH_B)。
    # 肩下がりも後ろの方が水平寄り(BODICE_DROP_B)にしてある。
    back_bodice("round_neck", _neckline_d("round", depth=BODICE_NECK_DEPTH_B),
                "後身頃テンプレート(標準Mサイズ) ラウンドネック")
    back_bodice("v_neck", _neckline_d("v", depth=BODICE_NECK_DEPTH_B + 3),
                "後身頃テンプレート(標準Mサイズ) Vネック(前ほど深くしない)")
    back_bodice("turtle_neck", _neckline_d("turtle", body_shift=4, stand=4),
                "後身頃テンプレート(標準Mサイズ) タートルネック",
                extra_h=4, body_shift=4)
    back_bodice("square_neck", _neckline_d("square", depth=BODICE_NECK_DEPTH_B),
                "後身頃テンプレート(標準Mサイズ) スクエアネック(前より浅め)")
    back_bodice("boat_neck",
                _neckline_d("boat", depth=2.0, half_width=BODICE_NECK_HALF * 1.75),
                "後身頃テンプレート(標準Mサイズ) ボートネック(前より浅め)")
    back_bodice("sweetheart", _neckline_d("sweetheart", depth=BODICE_NECK_DEPTH_B + 1.5),
                "後身頃テンプレート(標準Mサイズ) スウィートハートネック(前より浅め)")
    # 前開きファスナー版に対応する後身頃。round12で肩線と首ぐりを分離した
    # 結果、後身頃側は非ファスナー版と同じ寸法でよくなった(round11までは
    # 前パネル側の肩点に合わせるため別の座標を用意していた)が、
    # part_type+variationの組み合わせで参照されるため名前は残す。
    back_bodice("round_neck_zip", _neckline_d("round", depth=BODICE_NECK_DEPTH_B),
                "後身頃テンプレート(標準Mサイズ) ラウンドネック+前開きファスナー")
    back_bodice("v_neck_zip", _neckline_d("v", depth=BODICE_NECK_DEPTH_B + 3),
                "後身頃テンプレート(標準Mサイズ) Vネック+前開きファスナー")
    back_bodice("square_neck_zip", _neckline_d("square", depth=BODICE_NECK_DEPTH_B),
                "後身頃テンプレート(標準Mサイズ) スクエアネック+前開きファスナー")
    back_bodice("boat_neck_zip",
                _neckline_d("boat", depth=2.0, half_width=BODICE_NECK_HALF * 1.75),
                "後身頃テンプレート(標準Mサイズ) ボートネック+前開きファスナー")
    back_bodice("sweetheart_zip", _neckline_d("sweetheart", depth=BODICE_NECK_DEPTH_B + 1.5),
                "後身頃テンプレート(標準Mサイズ) スウィートハートネック+前開きファスナー")

    # --- 袖 6種 -----------------------------------------------------------
    #
    # 【round12で身頃と合わせて再調整】round11で袖を「実際に縫える寸法」に
    # 作り直した時点では、身頃の袖ぐりは片腕36.2cmだった。round12で身頃原型を
    # 作り直した結果、袖ぐりは片腕39.7cm(前19.5+後20.2)になったため、
    # 袖もそれに合わせて測り直している。
    #
    #   - 袖山カーブ長 = 袖ぐり39.7cm + いせ込み約2cm ≒ 41.7cm を目標にする
    #     (いせ込みは、袖山を袖ぐりよりわずかに長く作って丸みを出す洋裁の
    #      定石。布帛で1.5〜3cm程度)。
    #   - 袖幅(二の腕まわり・平置き) 32cm。成人女子Mの二の腕まわり約27cm+
    #     ゆとり5cm相当で、上の袖山カーブ長とも整合する。
    #   - 袖山の高さ 12cm。製図の目安(袖ぐり÷3 ≒ 13.2cm)に近く、
    #     幅32cm・高さ12cmで袖山41.98cm(いせ込み+2.28cm)になる。
    #     round11時点(袖ぐり36.2cm)では高さ10cmだったが、袖ぐりが大きくなった
    #     ぶん袖山も高く取れるようになり、製図の目安に近づいた。
    #   - 袖丈 52cm(STANDARD_M.sleeve_lengthそのもの)。以降も従来通り
    #     袖丈の比率でY方向にスケーリングされるため、採寸値がそのまま
    #     出来上がりの袖丈になる。
    #
    # 袖山カーブ(先頭の M + C 2本)は全variationで共通の作り方にしてある
    # (engine/compatibility.pyの`sleeve_cap_length`がこの規約に依存している)。
    _SLEEVE_CAP_W = 32      # 袖幅(二の腕まわり・平置き)
    _SLEEVE_CAP_H = 12      # 袖山の高さ
    _SLEEVE_LENGTH = 52     # 袖丈(STANDARD_M.sleeve_lengthと一致させる)

    def _sleeve_cap_d(x0: float = 0.0, w: float = _SLEEVE_CAP_W, h: float = _SLEEVE_CAP_H) -> str:
        """袖山カーブ(輪郭の先頭。両端が同じyになる2本のベジエ)を組み立てる。"""
        return (f"M {x0:g} {h:g}"
                f" C {x0 + w * 0.15:g} {h * 0.25:g}, {x0 + w * 0.35:g} 0, {x0 + w / 2:g} 0"
                f" C {x0 + w * 0.65:g} 0, {x0 + w * 0.85:g} {h * 0.25:g}, {x0 + w:g} {h:g}")

    def _sleeve_y_anchors(length: float, cap_h: float = _SLEEVE_CAP_H) -> str:
        """袖テンプレートの「体型合わせの基準線」(Y座標)を書き出す(round24)。

        役割(role)の意味:
          cap      … 袖山のてっぺん(y=0)。
          underarm … 袖山カーブが終わり、袖の脇が始まる線(=袖山の高さ)。
                     袖ぐりの寸法に比例して動く。
          hem      … 袖口。袖丈で動く。

        round23まで袖山の高さは袖丈比だけで動いていた。つまり**袖ぐりが
        大きくなっても袖山が高くならず**、袖山カーブの長さを合わせるために
        幅ばかりが広がっていた(engine/scaling.pyの`scale_sleeve_to_cap_length`
        のコメントに実測を記載)。袖山の高さは袖ぐり寸法に比例させるのが
        製図の定石(目安は袖ぐり÷3)である。
        """
        return " ".join([
            "cap:0.000",
            f"underarm:{cap_h:.3f}",
            f"hem:{length:.3f}",
        ])

    _write("sleeve__straight.svg", "sleeve", "straight", "32cm", "52cm", 32, 52,
           _sleeve_cap_d() + " L 28 52 L 4 52 Z",
           "袖テンプレート(標準Mサイズ) 直線袖。袖山カーブ42.0cm(袖ぐり39.7cm+"
           "いせ込み2.3cm)、袖幅32cm、袖丈52cm。袖口に向けてわずかに絞る。",
           fit_y=_sleeve_y_anchors(52))
    _write("sleeve__curve.svg", "sleeve", "curve", "32cm", "52cm", 32, 52,
           _sleeve_cap_d() + " C 31 22, 28.5 37, 27 52 L 5 52 C 3.5 37, 1 22, 0 12 Z",
           "袖テンプレート(標準Mサイズ) カーブ袖。袖山は直線袖と共通で、脇を"
           "カーブで絞って腕に沿わせたフィット袖(袖口幅22cm)。",
           fit_y=_sleeve_y_anchors(52))
    _write("sleeve__puff.svg", "sleeve", "puff", "37cm", "31cm", 37, 31,
           _sleeve_cap_d(0, 37, 14)
           + " L 34 30 C 29 27, 24 33, 18.5 30 C 13 27, 8 33, 3 30 Z",
           "袖テンプレート(標準Mサイズ) パフ袖。袖山を意図的に大きく(幅37cm・"
           "高さ14cm、袖山カーブ48.7cm)取り、袖ぐり39.7cmに対して約9cm(うち"
           "通常のいせ込み2cm、デザイン上のギャザー約7cm)を縮めて付ける想定。"
           "丈は短め(30cm)。実際のギャザー分量の指定機能は無く、輪郭の形状のみの近似。",
           fit_y=_sleeve_y_anchors(31, 14))
    _write("sleeve__bell.svg", "sleeve", "bell", "46cm", "52cm", 46, 52,
           _sleeve_cap_d(7) + " L 46 52 L 0 52 Z",
           "袖テンプレート(標準Mサイズ) ベルスリーブ。袖山は直線袖と同じ"
           "(幅32cm)だが、袖口に向かって大きく末広がりに広がる(裾幅46cm)。"
           "実際のドレープ(垂れ具合)は再現しておらず、末広がりの輪郭のみの近似。",
           fit_y=_sleeve_y_anchors(52))
    _write("sleeve__cap.svg", "sleeve", "cap", "32cm", "17cm", 32, 17,
           _sleeve_cap_d()
           + " C 27.2 15, 20.8 17, 16 17 C 11.2 17, 4.8 15, 0 12 Z",
           "袖テンプレート(標準Mサイズ) キャップスリーブ。肩先を覆う程度の"
           "ごく短い袖(丈17cm)で、上下とも緩いカーブの三日月型。脇の直線部分は"
           "無い。袖山カーブは他の袖と共通のため、袖ぐりにはそのまま付く。",
           fit_y=_sleeve_y_anchors(17))
    _write("sleeve__three_quarter.svg", "sleeve", "three_quarter", "32cm", "38cm", 32, 38,
           _sleeve_cap_d() + " L 28.5 38 L 3.5 38 Z",
           "袖テンプレート(標準Mサイズ) 7分袖。直線袖(丈52cm)と袖山を共通に"
           "したまま丈38cm(約7.3分)で打ち切り、袖口をわずかに絞った。",
           fit_y=_sleeve_y_anchors(38))

    # --- スカート 6種 -------------------------------------------------------
    #
    # 【round12(続き)で寸法を作り直した経緯】round11までのスカートは、標準体型
    # (ウエスト66・ヒップ91)でウエスト周が前後2枚合わせて40cmしかなく、28cm
    # 不足していた。さらにタイトスカートの輪郭がウエストから裾へ単調に細く
    # なるだけで、ヒップの張り出しがまったく無く、腰を通らない形だった。
    # 身頃・袖と同じ考え方で、採寸値から寸法を導出し直した。
    #
    #   1枚(前半身または後半身)あたり
    #     ウエスト側 = (ウエスト66 + ゆとり2) / 2 = 34cm
    #     ヒップ側   = (ヒップ91 + ゆとり4) / 2 = 47.5cm
    #     ヒップの位置 = ウエストから18cm下(身長158の約11.5%)
    #
    # フレア・プリーツ・ラップ・サーキュラーは裾へ広がる分でヒップ寸法を
    # 満たすため、ヒップ位置に別途カーブを入れていない(実際に18cm下の幅を
    # 計算して47.5cm以上あることを確認済み)。タイトとマーメイドは細身の
    # デザインなのでヒップのカーブを明示的に入れている。
    #
    # スカートは幅(X)のみヒップ比で変形する(丈は固定)。ウエストとヒップの
    # 差は engine/darts.py の apply_skirt_waist_dart がウエストダーツとして
    # 吸収する(tight/mermaidのみ)。
    _SKIRT_WAIST_HALF = 34.0    # ウエスト側の半周
    _SKIRT_HIP_HALF = 47.5      # ヒップ側の半周
    _SKIRT_HIP_Y = 18.0         # ウエストからヒップまでの距離
    _SKIRT_LEN = 60.0           # スカート丈(ウエストから裾まで。膝下丈)

    def _skirt_x(width: float) -> tuple[float, float]:
        """指定の幅を、テンプレート座標の中央に配置したときの左右のxを返す。"""
        cx = _SKIRT_HIP_HALF / 2 + 4.0   # 全variationで共通の中心(余白込み)
        return (cx - width / 2, cx + width / 2)

    def _skirt_view_w(max_width: float) -> float:
        return _SKIRT_HIP_HALF / 2 + 4.0 + max_width / 2 + 4.0

    wl, wr = _skirt_x(_SKIRT_WAIST_HALF)
    hl, hr = _skirt_x(_SKIRT_HIP_HALF)

    # タイト: ウエスト34 → ヒップ47.5(18cm下) → 裾44へわずかに絞る
    tl, tr = _skirt_x(44.0)
    _write("skirt__tight.svg", "skirt", "tight",
           f"{_skirt_view_w(47.5):g}cm", f"{_SKIRT_LEN:g}cm", _skirt_view_w(47.5), _SKIRT_LEN,
           f"M {wl:g} 0 L {wr:g} 0"
           f" C {wr + 2:g} {_SKIRT_HIP_Y * 0.45:g}, {hr:g} {_SKIRT_HIP_Y * 0.75:g}, {hr:g} {_SKIRT_HIP_Y:g}"
           f" L {tr:g} {_SKIRT_LEN:g} L {tl:g} {_SKIRT_LEN:g}"
           f" L {hl:g} {_SKIRT_HIP_Y:g}"
           f" C {hl:g} {_SKIRT_HIP_Y * 0.75:g}, {wl - 2:g} {_SKIRT_HIP_Y * 0.45:g}, {wl:g} 0 Z",
           "スカートテンプレート(標準Mサイズ・半身) タイト。ウエスト34cm→"
           "ヒップ47.5cm(18cm下)→裾44cmと、腰の張り出しを経てわずかに絞る。"
           "幅方向(X)のみヒップ比で変形し、engine/darts.pyのapply_skirt_waist_dartが"
           "ヒップ-ウエスト比の差分に応じたウエストダーツをさらに追加する。")

    # フレア: ウエスト34 → 裾80へ直線的に広がる(18cm下で約47.8cm≥47.5)
    fl, fr = _skirt_x(80.0)
    _write("skirt__flare.svg", "skirt", "flare",
           f"{_skirt_view_w(80):g}cm", f"{_SKIRT_LEN:g}cm", _skirt_view_w(80), _SKIRT_LEN,
           f"M {wl:g} 0 L {wr:g} 0 L {fr:g} {_SKIRT_LEN:g} L {fl:g} {_SKIRT_LEN:g} Z",
           "スカートテンプレート(標準Mサイズ・半身) フレア(裾に向けて大きく広がる)。"
           "ウエスト34cm→裾80cm。ヒップ位置(18cm下)でも約47.8cmあり、"
           "フレア分でヒップ寸法を満たすためヒップのカーブは入れていない。"
           "意図的にウエストで摘まずフレアで逃がすデザインのため、"
           "apply_skirt_waist_dartは適用しない。")

    # プリーツ: フレアより控えめに広がり、裾に折り目のジグザグ
    pl, pr = _skirt_x(80.0)
    zig = []
    steps = 8
    for i in range(steps + 1):
        x = pr - (pr - pl) * i / steps
        zig.append(f"L {x:.2f} {_SKIRT_LEN - (2 if i % 2 else 0):g}")
    _write("skirt__pleated.svg", "skirt", "pleated",
           f"{_skirt_view_w(80):g}cm", f"{_SKIRT_LEN:g}cm", _skirt_view_w(80), _SKIRT_LEN,
           f"M {wl:g} 0 L {wr:g} 0 " + " ".join(zig) + " Z",
           "スカートテンプレート(標準Mサイズ・半身) プリーツ。ウエスト34cm→"
           "裾80cmで、裾に沿った浅いジグザグでプリーツの折り目を簡易的に"
           "表現している(実際の折り込み分量・重なりは再現していない、"
           "見た目の輪郭のみの近似)。flareと同様、apply_skirt_waist_dartは適用しない。")

    # ラップ: 裾の片側が斜めに切り上がる非対称シルエット
    rl, rr = _skirt_x(76.0)
    _wrap_cut_y = 30.0        # 斜めの切り上がりが始まる高さ(ヒップ18cmより下)
    _wrap_cut_x = _skirt_x(58.0)[0]   # その高さでの左端
    _write("skirt__wrap.svg", "skirt", "wrap",
           f"{_skirt_view_w(76):g}cm", f"{_SKIRT_LEN:g}cm", _skirt_view_w(76), _SKIRT_LEN,
           f"M {wl:g} 0 L {wr:g} 0 L {rr:g} {_SKIRT_LEN:g}"
           f" L {rl + 30:g} {_SKIRT_LEN:g} L {_wrap_cut_x:g} {_wrap_cut_y:g} Z",
           "スカートテンプレート(標準Mサイズ・半身) ラップ(裾左側が斜めに"
           "切り上がる、前巻きスカート風の非対称シルエット)。ウエスト34cm→"
           "裾76cm。斜めの切り上がりはヒップ位置(18cm下)より下の30cmから"
           "始めており、腰まわりでは必要なヒップ寸法を確保している"
           "(round12の作り直し時、切り上がりが高すぎてヒップ位置の幅が"
           "33.9cmしか無い状態を実測で検出して修正した)。"
           "実際の巻き込み・打ち合わせ分量は再現していない、輪郭のみの近似。"
           "apply_skirt_waist_dartは適用しない。")

    # マーメイド: ヒップのカーブを経て膝下まで細身、そこから裾へ大きく広がる
    ml, mr = _skirt_x(88.0)
    kl, kr = _skirt_x(46.0)
    _write("skirt__mermaid.svg", "skirt", "mermaid",
           f"{_skirt_view_w(88):g}cm", f"{_SKIRT_LEN:g}cm", _skirt_view_w(88), _SKIRT_LEN,
           f"M {wl:g} 0 L {wr:g} 0"
           f" C {wr + 2:g} {_SKIRT_HIP_Y * 0.45:g}, {hr:g} {_SKIRT_HIP_Y * 0.75:g}, {hr:g} {_SKIRT_HIP_Y:g}"
           f" L {kr:g} 45 L {mr:g} {_SKIRT_LEN:g} L {ml:g} {_SKIRT_LEN:g} L {kl:g} 45"
           f" L {hl:g} {_SKIRT_HIP_Y:g}"
           f" C {hl:g} {_SKIRT_HIP_Y * 0.75:g}, {wl - 2:g} {_SKIRT_HIP_Y * 0.45:g}, {wl:g} 0 Z",
           "スカートテンプレート(標準Mサイズ・半身) マーメイド。ウエスト34cm→"
           "ヒップ47.5cm→膝下(裾から15cm手前)46cmまで細身にフィットし、"
           "そこから裾88cmへ一気に広がる。tightと同様フィットしたデザインのため、"
           "apply_skirt_waist_dartの対象に含める(SKIRT_DART_ELIGIBLE_VARIATIONS参照)。")

    # サーキュラー: フレアよりさらに広く、裾を曲線にして円裁ちらしさを近似
    cl, cr = _skirt_x(96.0)
    _write("skirt__circle.svg", "skirt", "circle",
           f"{_skirt_view_w(96):g}cm", f"{_SKIRT_LEN + 4:g}cm", _skirt_view_w(96), _SKIRT_LEN + 4,
           f"M {wl:g} 0 L {wr:g} 0 L {cr:g} {_SKIRT_LEN:g}"
           f" C {cr - 24:g} {_SKIRT_LEN + 4:g}, {cl + 24:g} {_SKIRT_LEN + 4:g}, {cl:g} {_SKIRT_LEN:g} Z",
           "スカートテンプレート(標準Mサイズ・半身) サーキュラー。ウエスト34cm→"
           "裾96cmとフレアよりさらに広く、裾を直線ではなく緩い曲線にして"
           "円裁ちらしい丸みを近似的に表現した。正直な限界: 実際の円裁ち"
           "(1/4円・1/2円パネル)の正確な円弧幾何ではなく、フレアパネルの"
           "延長線上の近似(直線の脇線+曲線の裾)にとどまる。"
           "apply_skirt_waist_dartの対象外(SKIRT_DART_ELIGIBLE_VARIATIONS参照)。")

    # --- パンツ(前後別パーツ、round5より。round12で寸法を作り直した) ------
    #
    # 各variationについて、裾幅と丈だけを変えたfront_pants(股ぐりの出しが
    # 小さい・中心線は直線)とback_pants(股ぐりの出しが大きい・中心線は
    # わずかに外へ膨らむ)を1組ずつ生成する。寸法の導出は`_pants_panel_d`の
    # 上のコメントを参照。
    #
    # 裾幅は「脚まわりの半分」で指定する(前パーツ+後ろパーツで脚1周)。
    # 例: standard の 21cm は脚まわり42cmで、一般的なストレートの裾に相当する。
    _PANTS_VARIATIONS = [
        # (variation, hem_half(脚まわりの半分), length(総丈))
        ("", 21.0, 96.0),          # ストレート(脚まわり42cm)
        ("wide", 28.0, 96.0),      # ワイド(脚まわり56cm)
        ("tapered", 16.0, 96.0),   # テーパード(脚まわり32cm)
        ("flare", 30.0, 96.0),     # フレア(脚まわり60cm)
        ("shorts", 25.0, 38.0),    # ショーツ(股上25cmを確保した最短丈)
        ("cropped", 16.0, 78.0),   # クロップド(くるぶし上)
    ]
    for variation, hem_half, length in _PANTS_VARIATIONS:
        fname_suffix = variation or "standard"
        for is_back, part_type in ((False, "front_pants"), (True, "back_pants")):
            ext = PANTS_BACK_CROTCH_EXT if is_back else PANTS_FRONT_CROTCH_EXT
            view_w = ext + PANTS_HIP_QUARTER + 2.0
            d = _pants_panel_d(hem_half=hem_half, length=length, is_back=is_back)
            side = "後ろ" if is_back else "前"
            # round25で追加した「体型合わせの基準線」(Y座標)。股上(ウエスト〜
            # 股ぐり)は身長ではなくヒップで決まる量なので、engine側が股ぐりの
            # 線を知っている必要がある(engine/bodice_fit.pyの
            # `build_pants_y_map`参照)。
            fit_y = " ".join([
                "waist:0.000",
                f"crotch:{PANTS_RISE:.3f}",
                f"hem:{length:.3f}",
            ])
            _write(f"{part_type}__{fname_suffix}.svg", part_type, variation,
                   f"{view_w:.2f}cm", f"{length:g}cm", view_w, length, d,
                   f"パンツ{side}パーツテンプレート(標準Mサイズ・片脚、"
                   f"variation={variation or '標準'})。"
                   f"ウエスト側{PANTS_WAIST_QUARTER:g}cm・ヒップ側{PANTS_HIP_QUARTER:g}cm"
                   f"(4枚でウエスト68cm・ヒップ95cm)、股上{PANTS_RISE:g}cm、"
                   f"総丈{length:g}cm、裾は脚まわり{hem_half * 2:g}cm。"
                   + ("後ろは股ぐりの出しを前より大きく取り(9.1cm)、中心線を"
                      "わずかに外へ膨らませて臀部のゆとりを表現している。"
                      if is_back else
                      "前は股ぐりの出しを小さく(5.7cm)、中心線は直線。"),
                   fit_y=fit_y)
    _write("collar__standard.svg", "collar", "", "40cm", "6cm", 40, 6,
           "M 2 0 C 0 0, 0 2, 0 3 L 0 6 L 40 6 L 40 3 C 40 2, 40 0, 38 0 Z",
           "衿テンプレート(標準Mサイズ) スタンドカラー用の帯状パーツ。",
           seam_edge="bottom")
    _write("collar__shirt_collar.svg", "collar", "shirt_collar", "40cm", "6cm", 40, 6,
           "M 4 0 L 0 3 L 4 6 L 36 6 L 40 3 L 36 0 Z",
           "衿テンプレート(標準Mサイズ) シャツカラー(左右の襟先が尖った形)。",
           seam_edge="bottom")
    _write("collar__peter_pan_collar.svg", "collar", "peter_pan_collar", "40cm", "10cm", 40, 10,
           "M 2 0 C 0 0, 0 4, 0 5 C 0 8, 4 10, 10 10 L 30 10"
           " C 36 10, 40 8, 40 5 C 40 4, 40 0, 38 0 Z",
           "衿テンプレート(標準Mサイズ) ピーターパンカラー(丸く平らに寝かせる、"
           "standardより幅広の襟)。",
           seam_edge="top")
    _write("collar__bow_collar.svg", "collar", "bow_collar", "44cm", "6cm", 44, 6,
           "M 6 0 L 0 3 L 6 6 L 38 6 L 44 3 L 38 0 Z",
           "衿テンプレート(標準Mサイズ) ボウカラー(shirt_collarよりさらに長く"
           "尖った左右の襟先で、リボン結び風の見た目を表現)。実際に結ぶ紐部分の"
           "延長は含まない、帯部分のみの近似。",
           seam_edge="bottom")
    _write("collar__ruffle_collar.svg", "collar", "ruffle_collar", "40cm", "8cm", 40, 8,
           "M 0 0 L 40 0 L 40 6"
           " C 36 4, 32 8, 28 6 C 24 4, 20 8, 16 6 C 12 4, 8 8, 4 6"
           " C 2 5, 0 7, 0 6 Z",
           "衿テンプレート(標準Mサイズ) フリルカラー。ネックライン側(上端)は"
           "直線のまま、外側(下端)を波状の曲線にしてフリル(ひだ飾り)の見た目を"
           "簡易的に表現した。実際のひだの折り込み分量は再現していない。",
           seam_edge="top")
    _write("collar__convertible_collar.svg", "collar", "convertible_collar", "40cm", "9cm", 40, 9,
           "M 6 0 C 2 0, 0 3, 0 4 L 6 9 L 34 9 L 40 4 C 40 3, 38 0, 34 0 Z",
           "衿テンプレート(標準Mサイズ) コンバーチブルカラー(round9追加)。"
           "シャツの開襟カラーのように、左右の襟先が角(ノッチ)状に大きく"
           "尖って外側へ開く形状で、standard(スタンドカラー)とは明確に異なる"
           "輪郭にしている。shirt_collarより衿の高さ(9cm)があり、"
           "peter_pan_collarのような丸みではなく角の効いた直線的な折り返しで"
           "区別した。",
           seam_edge="bottom")
    # round75: フード。ここで書き出すのは**標準M(頭囲57cm・首ぐり37.3cm)の
    # 1枚ぶん**で、実際の生成では`engine/hood.py`が採寸から引き直す。
    # テンプレートを置いてあるのは、他のパーツと同じく「どんな形か」を
    # ファイルとして見られるようにするためと、テンプレートの一覧を
    # 数え上げる仕組み(TemplateDB)に載せるため。
    _hood_plan = _hood_module.plan_hood(neckline_cm=37.30)
    _hood_d = _segments_to_d(_hood_module.hood_segments(_hood_plan))
    _write("hood__standard.svg", "hood", "",
           f"{_hood_plan.depth_cm:.1f}cm", f"{_hood_plan.height_cm + 3:.1f}cm",
           round(_hood_plan.depth_cm + 0.2, 1), round(_hood_plan.height_cm + 3, 1),
           _hood_d,
           "フードテンプレート(標準Mサイズ・2枚剥ぎの1枚)。"
           f"頭囲57cm・首ぐり37.3cmから引いた形で、高さ{_hood_plan.height_cm:.1f}cm・"
           f"奥行き{_hood_plan.depth_cm:.1f}cm・付け根{_hood_plan.neck_edge_cm:.1f}cm。"
           "実際の生成ではengine/hood.pyが採寸から引き直すので、この形は"
           "そのままでは使われない(どんな形かを見るための見本)。",
           seam_edge="bottom")
    _write("cuffs__standard.svg", "cuffs", "", "20cm", "6cm", 20, 6,
           "M 0 0 L 20 0 L 20 6 L 0 6 Z",
           "カフステンプレート(標準Mサイズ) 袖口の帯状パーツ。",
           seam_edge="top")
    _write("cuffs__wide.svg", "cuffs", "wide", "20cm", "9cm", 20, 9,
           "M 0 0 L 20 0 L 20 9 L 0 9 Z",
           "カフステンプレート(標準Mサイズ) ワイドカフス(standardより帯の幅が広い)。",
           seam_edge="top")
    _write("cuffs__ruffle.svg", "cuffs", "ruffle", "20cm", "6cm", 20, 6,
           "M 0 0 L 20 0 L 20 5"
           " C 18 3, 16 6, 14 4 C 12 3, 10 6, 8 4 C 6 3, 4 6, 2 4"
           " C 1 3.5, 0 5, 0 4 Z",
           "カフステンプレート(標準Mサイズ) フリルカフス。ruffle_collarと同じ"
           "技法(上端は直線、下端を波状にしてフリルを簡易的に表現)を袖口の"
           "帯に適用したもの。",
           seam_edge="top")
    _write("cuffs__button_tab.svg", "cuffs", "button_tab", "24cm", "9cm", 24, 9,
           "M 0 0 L 20 0 L 20 6 L 24 6 L 24 9 L 14 9 L 14 6 L 0 6 Z",
           "カフステンプレート(標準Mサイズ) ボタンタブ付きカフス(round9追加)。"
           "standardと同じ帯(幅20cm・高さ6cm)の右端に、ボタン留め用の"
           "オーバーラップ部分を表す矩形のタブ(幅10cm・帯下端から3cm張り出し)を"
           "追加した。実際のボタン穴・ボタン位置のマーキング(合印)までは"
           "含まない、タブの輪郭のみの近似。",
           seam_edge="top")
    _write("waistband__standard.svg", "waistband", "", "70cm", "8cm", 70, 8,
           "M 0 0 L 70 0 L 70 8 L 0 8 Z",
           "ウエストバンドテンプレート(標準Mサイズ) スカート/パンツ共通の帯状パーツ。",
           seam_edge="top")
    _write("waistband__wide.svg", "waistband", "wide", "70cm", "12cm", 70, 12,
           "M 0 0 L 70 0 L 70 12 L 0 12 Z",
           "ウエストバンドテンプレート(標準Mサイズ) ワイドウエストバンド"
           "(standardより帯の幅が広い)。",
           seam_edge="top")
    _write("waistband__elastic.svg", "waistband", "elastic", "70cm", "10cm", 70, 10,
           "M 0 0 L 70 0 L 70 8"
           " C 65 6, 60 10, 55 8 C 50 6, 45 10, 40 8 C 35 6, 30 10, 25 8"
           " C 20 6, 15 10, 10 8 C 5 6, 0 10, 0 8 Z",
           "ウエストバンドテンプレート(標準Mサイズ) 伸縮(ゴム)ウエストバンド。"
           "上端(ウエスト側の縫い付け線)は直線のまま、下端を波状の曲線にして"
           "ゴム通しによる縮み(シャーリング)の見た目を簡易的に表現した。"
           "実際の伸縮率・ゴム分量の計算はしていない、見た目のみの近似。",
           seam_edge="top")
    _write("waistband__contour.svg", "waistband", "contour", "70cm", "10cm", 70, 10,
           "M 0 2 C 20 0, 50 0, 70 2 L 70 10 C 50 8, 20 8, 0 10 Z",
           "ウエストバンドテンプレート(標準Mサイズ) コンター(体に沿う形)"
           "ウエストバンド(round9追加)。standard/wideのような上下が完全に"
           "平行な直線の帯ではなく、上端・下端とも中央がわずかに持ち上がる"
           "緩いカーブにして、実際のウエストラインの曲線に沿う「シェイプド"
           "ウエストバンド」の見た目を近似的に表現した。実際の体型ごとの"
           "曲線量の計測は行っておらず、見た目のみの近似(elasticとの違いは"
           "上端も曲線にしている点。elasticは上端を直線のまま、下端のみ"
           "シャーリングの波を表現している)。",
           seam_edge="top")


if __name__ == "__main__":
    main()
