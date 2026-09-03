"""scaling.py — 体型スケーリング（採寸差分によるテンプレート変形）。

採寸値を標準Mサイズとの差分でX/Y比例変形する実装。パタンナーが最も
時間をかける「採寸→型紙補正」をアルゴリズムで代替する。
"""

from __future__ import annotations
from dataclasses import dataclass
from types import SimpleNamespace

from .bodice_fit import build_x_map, effective_shoulder_width_cm, remap_segments_x
from .darts import apply_bust_dart, apply_pants_waist_dart, apply_skirt_waist_dart, apply_waist_dart
from .measurements import Measurements, STANDARD_M
from .part_specs import (
    LOWER_GARMENT_PART_TYPES, MAX_SCALE, MIN_SCALE, PART_SCALE_RULES, ScaleRule,
    clamp_scale, clamp_scale_for_part, lower_garment_x_scale,
)
from .svgpath import scale_segments, bounding_box, segments_to_polyline

#: measurements.Measurements のフィールド名 -> 画面表示用の日本語ラベル。
_MEASUREMENT_LABELS: dict[str, str] = {
    "bust": "バスト",
    "waist": "ウエスト",
    "hip": "ヒップ",
    "height": "身長",
    "sleeve_length": "袖丈",
    "shoulder_width": "肩幅",
}


@dataclass(frozen=True)
class ScaledPart:
    part_type: str
    variation: str
    segments: list
    scale_x: float
    scale_y: float
    width_cm: float
    height_cm: float
    dart_count: int = 0


def compute_scale_factors(measurements: Measurements, part_type: str) -> tuple[float, float]:
    """パーツ種ごとの規則に従い、標準Mサイズに対する (rx, ry) 倍率を求める。

    collar/cuffs/waistband(帯状パーツ)には、身頃等より広いクランプ範囲を使う
    (`clamp_scale_for_part`、engine/part_specs.py参照)。矩形をX方向にだけ
    伸縮する変形は倍率に関わらず自己交差しないため、曲線を含むパーツ向けの
    安全域(MIN_SCALE〜MAX_SCALE)をそのまま当てはめる理由が無く、実際には
    それが原因で「Measurements上は有効な入力(例: ウエスト150cm)なのに
    クランプされ、約3割短いバンドが生成される」ことがあった(round11で
    発見・修正)。
    """
    rule: ScaleRule | None = PART_SCALE_RULES.get(part_type)
    if rule is None:
        return (1.0, 1.0)

    def _ratio(measure_name: str | None) -> float:
        if measure_name is None:
            return 1.0
        actual = getattr(measurements, measure_name)
        standard = getattr(STANDARD_M, measure_name)
        return clamp_scale_for_part(actual / standard, part_type)

    if part_type in LOWER_GARMENT_PART_TYPES:
        # スカート・パンツの幅は、ウエストとヒップの両方が必要とする倍率の
        # 大きい方を使う(engine/part_specs.pyのLOWER_GARMENT_FITのコメント参照)。
        rx = clamp_scale_for_part(
            lower_garment_x_scale(measurements.waist, measurements.hip), part_type)
        return (rx, _ratio(rule.y_measure))

    return (_ratio(rule.x_measure), _ratio(rule.y_measure))


#: `data-fit-x`基準点による区間別変形の対象になるパーツ種(round14)。
#: これ以外のパーツは従来通りX/Y一律の比例変形。
FIT_ANCHOR_PART_TYPES = {"front_bodice", "back_bodice", "front_bodice_zip_panel"}


def scale_template(part_type: str, variation: str, segments: list,
                    measurements: Measurements,
                    fit_anchors: list[tuple[str, float]] | None = None) -> ScaledPart:
    """テンプレートのセグメントを採寸に合わせて変形し、寸法情報も併せて返す。

    線形の比例変形(X/Y均一倍率)を行った後、front_bodice/back_bodiceに限り、
    バスト-ウエスト比の差分から算出したウエストダーツを追加する
    (engine.darts参照)。線形スケーリングだけでは「バスト基準で幅を決めると
    ウエストが太すぎる/ウエスト基準だとバストがきつい」という体型差を
    表現できないため、その最小限の補正として機能する。

    さらにfront_bodiceに限り、バスト絶対値が標準サイズを超える分に応じた
    脇ダーツ(apply_bust_dart)も追加する。ウエストダーツとは独立した別の
    不足（バスト位置周りの丸みを平面パターンで表現できない問題）に対する
    補正で、両方とも該当すれば両方とも追加される。

    skirt(tight)に限り、ヒップ比とウエスト比の差分に応じたウエストダーツ
    (apply_skirt_waist_dart)も追加する。skirtは幅をヒップ比のみで変形して
    いるため、ヒップに対してウエストが標準より細い体型ではウエストラインが
    たるむという不足があり、その最小限の補正として機能する。

    pantsは全variationに限り、同じくヒップ比とウエスト比の差分に応じた
    ウエストダーツ(apply_pants_waist_dart)を追加する。skirtと異なり
    「フレアで逃がす」デザイン上の選択肢が無いため、脚のシルエットに
    関わらず全variationが対象になる。

    round14の追加: `fit_anchors`(テンプレートSVGの`data-fit-x`属性)が
    与えられた身頃パーツは、X方向を一律の倍率ではなく**区間ごとに違う倍率**
    で変形する(`engine/bodice_fit.py`)。これにより脇線はバスト、肩先は
    入力された肩幅、首の付け根はネック幅の式で決まるようになる。
    round13までは全体をバスト比で一律に伸縮していたため、入力した肩幅が
    使われず、実測で最大10.9cmの誤差が出ていた。

    `fit_anchors`が無い(=テンプレートが基準点を持たない、または呼び出し側が
    渡していない)場合は従来通り一律の比例変形にフォールバックする。
    このフォールバックが「静かに古い挙動へ戻る」経路になりうるため、
    tests/test_bodice_fit.py で「全身頃テンプレートが基準点を持つこと」と
    「パイプラインが実際に基準点を渡していること」を検証している。
    """
    rx, ry = compute_scale_factors(measurements, part_type)
    if fit_anchors and part_type in FIT_ANCHOR_PART_TYPES:
        knots = build_x_map(fit_anchors, measurements.bust,
                            measurements.shoulder_width, rx)
        scaled = remap_segments_x(segments, knots, ry)
    else:
        scaled = scale_segments(segments, rx, ry)
    scaled, waist_dart_count = apply_waist_dart(part_type, scaled, measurements)
    scaled, bust_dart_count = apply_bust_dart(part_type, scaled, measurements)
    scaled, skirt_dart_count = apply_skirt_waist_dart(part_type, variation, scaled, measurements)
    scaled, pants_dart_count = apply_pants_waist_dart(part_type, variation, scaled, measurements)
    dart_count = waist_dart_count + bust_dart_count + skirt_dart_count + pants_dart_count
    min_x, min_y, max_x, max_y = bounding_box(scaled)
    return ScaledPart(
        part_type=part_type,
        variation=variation,
        segments=scaled,
        scale_x=rx,
        scale_y=ry,
        width_cm=max_x - min_x,
        height_cm=max_y - min_y,
        dart_count=dart_count,
    )


def scale_band_to_target_width(part_type: str, variation: str, segments: list,
                                target_width_cm: float) -> ScaledPart:
    """帯状パーツ(waistband/cuffs)を、独立した採寸比率ではなく、実際に縫い
    合わせる相手パーツ(スカート/パンツのウエストライン、袖の袖口)の完成後の
    長さに直接合わせてX方向だけを変形する(round7で追加)。

    round6で追加した縫い合わせ長さの整合性チェッカー(engine/compatibility.py)
    により、標準的な採寸でもskirt⇔waistband・sleeve⇔cuffsの組み合わせで
    ほぼ常に警告が出ることが分かっていた。原因を追ったところ、waistbandは
    「ウエスト比」、cuffsは「袖丈比」で、それぞれ独立にスケーリングしており、
    相手パーツ(skirt/sleeve)側は「ヒップ比」「肩幅比」等の全く別の採寸項目で
    独立にスケーリングされていたため、両者が偶然にも一致する保証が構造的に
    無かった(テンプレート同士の基準寸法自体が独立に決められていたことが
    根本原因)。実際のパタンナー業務でも、ウエストバンド/カフスは単独で
    採寸から起こすのではなく「縫い合わせる相手の完成後の辺の長さ」に合わせて
    作るのが通常であり、この関数はその考え方をそのままコード化したもの。
    呼び出し側(engine/pipeline.py)で、相手パーツの実際の縫い線長さ(ダーツ
    考慮後)にクロージャー/ゆとり分の定数を加えた値を`target_width_cm`として
    渡す。相手パーツが存在しない(例: スカート/パンツ無しでwaistbandだけ
    指定する等、通常は想定しない組み合わせ)場合は、呼び出し側が従来通り
    `scale_template()`にフォールバックする。

    実装時に見つかった不具合（修正済み）: 当初は`scale_template()`と同様に
    `clamp_scale()`(標準サイズの0.7〜1.6倍という、直接入力された採寸値の
    誤り検知を目的としたクランプ)を通していたが、これは意図と逆効果だった。
    このクランプは「利用者が入力した採寸値が単位間違い等で明らかに異常な
    場合に、それ以上テンプレートを壊れた形に変形しないための安全装置」で
    あり、この関数が受け取る`target_width_cm`は利用者の直接入力ではなく
    相手パーツを実際にスケーリングした後の正確な幾何計算結果である。
    実際、標準体型でもwaistbandテンプレートの原寸(約70cm)とskirtの
    ウエストライン合計(約32〜44cm)の比が0.6前後になるケースがあり、これは
    0.7の下限に引っかかって常にクランプされてしまい、「相手に合わせて
    伸縮させる」という本関数の目的そのものが機能しなくなっていた
    (クランプ後の幅が常に約49cmで固定され、どんな採寸を入れても
    ウエストバンド長が変わらないという不具合として現れ、実際に
    `pipeline.generate_from_selection()`を複数の採寸で呼び出し比較して
    発見した)。相手パーツ側の採寸自体はすでに`scale_template()`内で
    `clamp_scale()`によるガードを経ているため、ここで追加のクランプは
    不要と判断し、単純な比率変換のみを行うようにした。

    【round15での位置づけの変更】この関数は「外接矩形の幅」を目標に合わせる。
    しかし襟先やボタンタブが左右へ張り出す帯では、外接矩形の幅と実際に
    縫い付けられる辺の長さが最大30%ずれる(`scale_band_to_seam_length`の
    docstringの実測表参照)。そのため生成パイプラインからの呼び出しは
    すべて`scale_band_to_seam_length`へ移した。この関数は「縫い付け辺の
    宣言が無い場合」と同じ挙動(=外接矩形基準)を表す薄い別名として残す。
    """
    return scale_band_to_seam_length(part_type, variation, segments,
                                     target_width_cm, seam_edge="")


#: 帯状パーツを縫い付け辺の長さに合わせるときの、倍率の探索範囲と打ち切り幅。
BAND_FIT_MIN_SCALE = 0.05
BAND_FIT_MAX_SCALE = 20.0
BAND_FIT_TOLERANCE_CM = 0.005


def scale_band_to_seam_length(part_type: str, variation: str, segments: list,
                               target_cm: float, seam_edge: str = "") -> ScaledPart:
    """帯状パーツ(衿/カフス/ウエストバンド)を、**実際に縫い付けられる辺**の
    長さが target_cm になるようX方向だけ変形する(round15で追加)。

    【なぜ外接矩形ではだめか】round14まで、帯の長さは外接矩形の幅で測って
    いた。だが襟先やボタンタブは左右へ張り出すので、外接矩形の幅は縫い付け
    辺より長い。実測(標準Mサイズのテンプレート):

      パーツ                     外接矩形   縫い付け辺   ずれ
      collar/shirt_collar          40.0cm     32.0cm    -20%
      collar/bow_collar            44.0cm     32.0cm    -27%
      collar/convertible_collar    40.0cm     28.0cm    -30%
      collar/peter_pan_collar      40.0cm     36.0cm    -10%
      cuffs/button_tab             24.0cm     20.0cm    -17%

    外接矩形を目標に合わせると、実際に縫い付けられる辺はその分だけ短く
    仕上がる。例えば袖口20cmに対してボタンタブ付きカフスを作ると、
    縫い付け辺は16.7cmにしかならない。

    どちらの辺が縫い付け側かはテンプレートSVGの`data-seam-edge`属性で
    宣言されている(`TemplateDB.get_seam_edge`)。宣言が無い場合は従来通り
    外接矩形の幅を使う(=`scale_band_to_target_width`と同じ挙動)。

    コンターウエストバンドのように辺そのものが曲線の場合、弧長は倍率に
    対して線形ではないため、袖山合わせ(`scale_sleeve_to_cap_length`)と
    同じく二分探索で倍率を決める。
    """
    from .compatibility import seam_edge_length

    min_x, min_y, max_x, max_y = bounding_box(segments)
    raw_width = max_x - min_x
    if raw_width <= 0 or target_cm <= 0:
        return ScaledPart(part_type=part_type, variation=variation, segments=segments,
                           scale_x=1.0, scale_y=1.0, width_cm=raw_width,
                           height_cm=max_y - min_y, dart_count=0)

    def measured(rx: float) -> float:
        scaled = scale_segments(segments, rx, 1.0)
        return seam_edge_length(SimpleNamespace(
            stitch_line=segments_to_polyline(scaled), seam_edge=seam_edge))

    base = measured(1.0)
    if base <= 0:
        rx = target_cm / raw_width
    else:
        # まず線形の当たりを付ける(直線の辺ならこれで厳密に一致する)。
        rx = target_cm / base
        if abs(measured(rx) - target_cm) > BAND_FIT_TOLERANCE_CM:
            lo, hi = BAND_FIT_MIN_SCALE, BAND_FIT_MAX_SCALE
            for _ in range(60):
                mid = (lo + hi) / 2.0
                if measured(mid) < target_cm:
                    lo = mid
                else:
                    hi = mid
                if hi - lo < 1e-9:
                    break
            rx = (lo + hi) / 2.0

    scaled = scale_segments(segments, rx, 1.0)
    s_min_x, s_min_y, s_max_x, s_max_y = bounding_box(scaled)
    return ScaledPart(
        part_type=part_type,
        variation=variation,
        segments=scaled,
        scale_x=rx,
        scale_y=1.0,
        width_cm=s_max_x - s_min_x,
        height_cm=s_max_y - s_min_y,
        dart_count=0,
    )


#: 袖山カーブを袖ぐりに合わせるとき、幅の倍率を探索する範囲。
#: 下限/上限に張り付いた場合は目標長さに届いていないので、
#: 従来通り`engine/compatibility.py`のチェック5が警告を出す。
SLEEVE_FIT_MIN_SCALE = 0.5
SLEEVE_FIT_MAX_SCALE = 3.0
#: 二分探索の打ち切り幅(cm)。袖山は数十cmの弧なので、0.01cmは十分細かい。
SLEEVE_FIT_TOLERANCE_CM = 0.01


def scale_sleeve_to_cap_length(part_type: str, variation: str, segments: list,
                                measurements: Measurements,
                                target_cap_cm: float) -> ScaledPart:
    """袖を「実際に縫い付ける袖ぐりの長さ」に合わせて幅方向だけ変形する
    (round14で追加)。

    【なぜ必要になったか】round13まで、身頃の幅はバスト比、袖の幅は肩幅比で
    それぞれ独立に決まっていた。round14で身頃の肩先を入力された肩幅に
    固定した結果、袖ぐりの幅(脇線から肩先までの水平距離)がバストと肩幅の
    差をすべて引き受けるようになり、標準から外れた体型で袖ぐりと袖山の
    差が広がった。実測(前後身頃の合計・片腕ぶん):

      体型(バスト/肩幅)     袖ぐり   袖山   差
      83 / 37  (標準)       39.7   42.0  +2.2cm(いせ込みとして適正)
      112 / 39 (バスト特大)  48.3   44.0  -4.3cm(袖が小さすぎて付かない)
      105 / 36 (グラマー)    46.6   41.3  -5.3cm(同上)

    差がマイナスということは「袖山が袖ぐりより短い」=物理的に縫い付け
    られないということで、型紙として成立していない。

    【対処】round7でウエストバンド/カフスに使ったのと同じ考え方
    (`scale_band_to_target_width`のdocstring参照)を袖にも適用する。
    すなわち、採寸から独立に袖の幅を決めるのをやめ、**縫い合わせる相手
    (袖ぐり)の実際の長さ**に袖山カーブの長さが一致するよう幅を決める。
    これは実際のパタンナー業務でも普通に行う操作(袖山の寸法合わせ)。

    袖山の弧長は幅の倍率に対して線形ではない(カーブなので)ため、
    倍率は二分探索で求める。長さ方向(Y)は従来通り袖丈比で変形する。

    目標長さに届かない(探索範囲に張り付く)場合は、届いた範囲で最良の
    倍率を使い、不一致は`engine/compatibility.py`のチェック5が引き続き
    警告する(黙って辻褄を合わせない)。
    """
    from .compatibility import sleeve_cap_length  # 循環importを避けるため関数内で読む

    _, ry = compute_scale_factors(measurements, part_type)

    def cap_len(rx: float) -> float:
        scaled = scale_segments(segments, rx, ry)
        value = sleeve_cap_length(
            SimpleNamespace(stitch_line=segments_to_polyline(scaled)))
        return value if value is not None else 0.0

    lo, hi = SLEEVE_FIT_MIN_SCALE, SLEEVE_FIT_MAX_SCALE
    if target_cap_cm <= 0 or cap_len(lo) <= 0:
        return scale_template(part_type, variation, segments, measurements)
    if cap_len(hi) < target_cap_cm:
        rx = hi
    elif cap_len(lo) > target_cap_cm:
        rx = lo
    else:
        while hi - lo > 1e-6 and abs(cap_len((lo + hi) / 2.0) - target_cap_cm) > SLEEVE_FIT_TOLERANCE_CM:
            mid = (lo + hi) / 2.0
            if cap_len(mid) < target_cap_cm:
                lo = mid
            else:
                hi = mid
        rx = (lo + hi) / 2.0

    scaled = scale_segments(segments, rx, ry)
    min_x, min_y, max_x, max_y = bounding_box(scaled)
    return ScaledPart(
        part_type=part_type,
        variation=variation,
        segments=scaled,
        scale_x=rx,
        scale_y=ry,
        width_cm=max_x - min_x,
        height_cm=max_y - min_y,
        dart_count=0,
    )


def bodice_fit_clamp_warning(fit_anchors: list[tuple[str, float]],
                              measurements: Measurements) -> str | None:
    """入力された肩幅を型紙にそのまま反映できなかった場合の注記を返す
    (round14で追加。反映できた場合は None)。

    肩先は「中心前から肩幅/2」の位置に置くが、身頃の半身の幅(バストで
    決まる)より外側には置けない(置くと輪郭が折り返して型紙にならない)。
    バストに対して極端に肩幅が大きい入力では、`bodice_fit.py`の
    MIN_ARMHOLE_WIDTH_CM で頭打ちになる。このプロジェクトの方針どおり、
    そのときは黙って別の寸法を出すのではなく利用者へ開示する
    (`measurement_clamp_warnings`と同じ位置づけ)。
    """
    if not fit_anchors:
        return None
    rx, _ry = compute_scale_factors(measurements, "front_bodice")
    effective = effective_shoulder_width_cm(
        fit_anchors, measurements.bust, measurements.shoulder_width, rx)
    if effective is None or abs(effective - measurements.shoulder_width) <= 0.05:
        return None
    return (
        f"肩幅={measurements.shoulder_width:g}cmは、バスト={measurements.bust:g}cmから"
        f"決まる身頃の幅に収まらないため、実際には{effective:.1f}cm相当として"
        "型紙を生成しました(肩先は脇線より内側にしか置けません)。"
        "バストか肩幅のどちらかの採寸値を確認してください。"
    )


def measurement_clamp_warnings(measurements: Measurements) -> list[str]:
    """入力された採寸値のうち、テンプレート変形の限界(MIN_SCALE〜MAX_SCALE=
    標準Mサイズの0.7〜1.6倍)を超えているため、実際にはクランプされた
    別の値で型紙が生成されてしまう項目について、正直な注記を返す。

    実際に動かして見つかった不具合（修正済み）: `Measurements`の入力検証
    (`measurements.py`の`_VALID_RANGES`)は「単位/桁間違いらしい値を早期に
    弾く」ためのもので、例えばbustは50〜160cmまで許容している。一方、
    実際にテンプレートを変形できる範囲はここで判定しているMIN_SCALE〜
    MAX_SCALE(標準Mサイズ83cmの0.7〜1.6倍 ≒ 58.1〜132.8cm)に限られる。
    以前はこの2つの範囲の食い違いについて何の警告も出しておらず、実際に
    `/api/generate`へbust=160cmとbust=132.8cm(=83×1.6)を送って比較した
    ところ、生成される前身頃・後身頃の型紙が完全に同一(width_cm=50.0で
    一致)になることを確認した——つまりbust=133cm以上のいずれの値を
    入力しても常に同じ(132.8cm相当の)型紙が返っており、入力した採寸値と
    実際に届く型紙が一致しない状態だった。この種の不整合は特に体型の
    多様な実際の利用者(仕立て業者が扱うプラスサイズ・小さめサイズの
    顧客等、README「採寸プロフィール機能」参照)にとって、生地を実際に
    裁ってから初めて気づく実害のある不具合になりうる。この関数が返す
    注記を`PipelineResult.summary()`経由でAPIレスポンスに含め、フロント
    エンド(index.html/app.js)にも警告として表示することで、クランプが
    発生したことと、実際に使われた相当値を利用者に開示するようにした。

    正直な注記(round11): この判定は常に狭い方の範囲(MIN_SCALE〜MAX_SCALE)を
    基準にしている。round11以降、collar/cuffs/waistband(帯状パーツ)はより
    広いクランプ(`clamp_scale_for_part`)を使うため、例えばwaist=150cmでも
    ウエストバンドの幅自体はクランプされない。ただし同じwaist値はスカート/
    パンツのウエストダーツ計算(engine/darts.py。こちらは従来通り
    clamp_scaleを直接使う)には引き続き影響するため、ここで注記を出すこと
    自体は誤りではない。一方で「ウエストバンドの長さが不正確になる」と
    までは限らなくなった、という点は正直に補足しておく。
    """
    warnings: list[str] = []
    for field_name, label in _MEASUREMENT_LABELS.items():
        actual = getattr(measurements, field_name)
        standard = getattr(STANDARD_M, field_name)
        ratio = actual / standard
        clamped_ratio = clamp_scale(ratio)
        if clamped_ratio != ratio:
            effective = standard * clamped_ratio
            warnings.append(
                f"{label}={actual:g}cmはテンプレートの変形可能範囲"
                f"(標準サイズの{MIN_SCALE}〜{MAX_SCALE}倍 ≒ "
                f"{standard * MIN_SCALE:.1f}〜{standard * MAX_SCALE:.1f}cm)を"
                f"超えているため、実際には{effective:.1f}cm相当として"
                "型紙を生成しました。正確な型紙が必要な場合は手作業での"
                "補正を検討してください。"
            )
    return warnings
