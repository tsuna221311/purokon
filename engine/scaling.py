"""scaling.py — 体型スケーリング（採寸差分によるテンプレート変形）。

採寸値を標準Mサイズとの差分でX/Y比例変形する実装。パタンナーが最も
時間をかける「採寸→型紙補正」をアルゴリズムで代替する。
"""

from __future__ import annotations
from dataclasses import dataclass
from types import SimpleNamespace

from .bodice_fit import (
    apply_hip_widening, apply_waist_nip, bodice_bust_cm_for_scale, bodice_x_scale,
    bodice_side_width_cm, fit_armhole_width,
    waist_nip_limit_cm,
    hip_widening_start_y,
    apply_design_length_to_y_map,
    build_pants_y_map, build_sleeve_y_map, build_x_map, build_y_map,
    bust_point_y_cm as bust_point_y_cm_fn, front_neck_depth_cm,
    effective_shoulder_width_cm, hip_widening_cm, remap_segments_x,
    sleeve_cap_height_scale,
)
from .darts import (
    WAIST_DART_SHARE_SIDE_SEAM,
    apply_bust_dart, bust_dart_split_for_part, apply_pants_waist_dart, apply_skirt_waist_dart,
    retrue_bust_darts,
    apply_waist_dart, waist_dart_hip_limited,
)
from .measurements import Measurements, STANDARD_M
from .blocks import ADULT_FEMALE, Block
from .part_specs import (
    BODICE_PART_TYPES, DEFAULT_FIT, FIT_PRESETS, LOWER_GARMENT_PART_TYPES,
    MAX_SCALE, MIN_SCALE, PART_SCALE_RULES, ScaleRule,
    clamp_scale, clamp_scale_for_part, fit_ease, is_stretch,
    lower_garment_x_scale,
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
    #: round57: 丈の指定(`design_length_cm`)を**実際に当てられたか**。
    #: Noneは指定なし。Falseは「短すぎて袖ぐりより下が無くなるので
    #: 当てなかった」——黙って無視すると、指定した数字と違う型紙が出た
    #: ことだけが残るので、呼び出し側が利用者へ開示する。
    design_length_applied: bool | None = None
    #: round26: ヒップを通す幅を確保するために、ウエストダーツの摘み量を
    #: 減らしたか。減らした場合、ウエストは本来より絞りきれていないので
    #: 呼び出し側(engine/pipeline.py)が利用者へ開示する。
    waist_shaping_limited: bool = False
    #: round27: 脇線の傾きの上限に当たって、ヒップが通る幅を確保しきれ
    #: なかった量(周の合計・cm)。0なら確保できている。
    hip_shortfall_cm: float = 0.0
    #: round29: 胸ぐせダーツの口の幅の合計(cm)。この分だけ「口より下」が
    #: 紙の上で下がっており、縫い閉じると元の高さへ戻る。紙の上のyと
    #: 出来上がりのyを行き来するのに要る(engine/pipeline.pyでウエスト
    #: ダーツの先端をBPの手前で止める計算に使う)。
    bust_dart_shift_cm: float = 0.0
    #: round29: 胸ぐせダーツのうち、脇線に収まりきらなかった量(cm)。
    #: 0でなければ、胸の丸みがその分だけ足りない(利用者へ開示する)。
    bust_dart_unfitted_cm: float = 0.0
    #: round30: 脇線の傾きの上限に当たって、ウエストで絞りきれなかった量
    #: (周の合計・cm)。伸びる生地(ダーツ無し)で効く。
    waist_nip_shortfall_cm: float = 0.0
    #: round28: 変形後の座標系でのバストライン(=袖ぐり底の線)のy(cm)。
    #: 身頃のみ。脇ダーツをBPへ向けるのと、ウエストダーツの上の先端を
    #: BPの手前で止めるのに使う。基準線を持たないテンプレートではNone。
    bust_line_y_cm: float | None = None
    #: round40: 体型合わせの基準点を、**変形後の座標**で持つ(役割, x/y)。
    #: `fit_anchors`(テンプレート座標)をそのまま補正に使うと、変形で
    #: 位置がずれているぶんだけ的を外す。実際round40で、ウエストの補正が
    #: 想定の-2.0cmではなく-1.44cmしか効かなかった——テンプレートの
    #: ウエスト線(y=38)を、変形後の座標だと思って使っていたのが原因。
    fit_anchors_scaled: tuple[tuple[str, float], ...] = ()
    fit_anchors_y_scaled: tuple[tuple[str, float], ...] = ()
    #: round29: 変形後の座標系でのBP(バストポイント)の高さ(cm)。
    #: 乳下がりの採寸があればそこから、無ければバストラインと同じ。
    bust_point_y_cm: float | None = None
    #: round27: 変形後の座標系でのウエストの線のy(cm)。身頃のみ。
    #: ここへダイヤモンドダーツを置く(engine/darts.pyの
    #: `waist_diamond_dart_lines`)。基準線を持たないテンプレートではNone。
    waist_y_cm: float | None = None
    #: round76: ドロップショルダーで脇の下を下げた場合の、**下げたあと**の
    #: 高さ(cm)。Noneなら`bust_line_y_cm`と同じ(=下げていない)。
    #:
    #: バスト線(BL)とは別に持つ。BLは型紙に印字する基準線で、体の
    #: バストの高さそのものなので動かせない。一方「脇の下」は、袖ぐりを
    #: どこで打ち切るかの判定(`engine/compatibility.py`の`side_seam_edges`)
    #: に使う値で、ドロップショルダーでは実際に下がる。同じ値を使い回して
    #: いると、下げた袖ぐりの下端が脇線と読まれて袖ぐりが短く測られる
    #: (実測: 後ろ身頃41.34cm→38.40cm)。
    underarm_y_cm: float | None = None
    #: round31: 中心から袖ぐりの点まで(前身頃なら胸幅、後ろ身頃なら背幅)の
    #: 実際の値(cm)。狙い値は`bodice_side_width_cm`。身頃のみ、基準線が
    #: 無ければNone。
    chest_width_cm_actual: float | None = None
    #: round31: 上の狙い値(cm)。実際の値との差が、胸(背)の幅の過不足。
    chest_width_cm_target: float | None = None
    #: round31: 袖ぐりの点を狙いの位置へ動かしきれなかったか。肩幅に対して
    #: バストが大きすぎる(袖ぐりの点は肩先より外へは出られない)場合に立つ。
    chest_width_limited: bool = False


def bodice_ease_for(measurements: Measurements, fit: str | None,
                     block: Block = ADULT_FEMALE) -> float:
    """この原型・このゆとり指定で、身頃の総回りに足すゆとり(cm)。round42。

    利用者が選ぶゆとり(fitted/standard/relaxed/数値指定)は、round41までは
    そのまま絶対値だった。原型が増えると、それでは困る——子ども原型の
    標準ゆとりは B/4(バスト60で15cm)で、成人女子の8.0cmとは別の値である。
    8.0cmのまま子どもの型紙を引くと、出典の原型より7cmきつい身頃になる。

    そこで、**原型の標準ゆとりを基準**にし、利用者の選択はそこからの
    増減として効かせる。成人女子は標準が8.0cmなので、
    「ぴったり4.0 / 標準8.0 / ゆったり14.0」はそのまま同じ値になり、
    round41までの型紙は1mmも変わらない。
    """
    chosen = fit_ease(fit).bodice_cm
    default = FIT_PRESETS[DEFAULT_FIT].bodice_cm
    return block.ease_cm(measurements.bust) + (chosen - default)


def compute_scale_factors(measurements: Measurements, part_type: str,
                           fit: str | None = None,
                           block: Block = ADULT_FEMALE) -> tuple[float, float]:
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
        return clamp_scale_for_part(actual / standard, part_type,
                                     block.min_scale)

    if part_type in BODICE_PART_TYPES:
        # round23: 身頃の幅は「バスト + 一定のゆとり」で決める。バスト比で
        # 一律に拡大縮小すると、テンプレートに織り込まれたゆとり(8cm)まで
        # 比例して増減してしまう(実測でバスト60→5.8cm、130→12.5cm)。
        # 下半身パーツが以前からそうしている(lower_garment_x_scale)のと
        # 同じ考え方で、身頃だけが取り残されていた。
        # round42: ゆとりの基準は**原型ごと**に違う。利用者が選ぶ
        # fitted/relaxed は「その原型の標準ゆとりからの増減」として効かせる
        # (成人女子は標準8.0cmなので、round41までとまったく同じ値になる)。
        return (clamp_scale_for_part(
                    bodice_x_scale(measurements.bust,
                                    bodice_ease_for(measurements, fit, block)),
                    part_type, block.min_scale),
                _ratio(rule.y_measure))

    if part_type in LOWER_GARMENT_PART_TYPES:
        # スカート・パンツの幅は、ウエストとヒップの両方が必要とする倍率の
        # 大きい方を使う(engine/part_specs.pyのLOWER_GARMENT_FITのコメント参照)。
        rx = clamp_scale_for_part(
            lower_garment_x_scale(measurements.waist, measurements.hip, fit),
            part_type, block.min_scale)
        return (rx, _ratio(rule.y_measure))

    return (_ratio(rule.x_measure), _ratio(rule.y_measure))


#: `data-fit-x`基準点による区間別変形の対象になるパーツ種(round14)。
#: これ以外のパーツは従来通りX/Y一律の比例変形。
FIT_ANCHOR_PART_TYPES = {"front_bodice", "back_bodice", "front_bodice_zip_panel"}


def _widen_for_hip(scaled: list, x_knots: list, y_knots: list,
                    measurements: Measurements, fit: "str | None"
                    ) -> tuple[list, float, float]:
    """身頃の裾を、ヒップが通る幅まで開かせる(round26)。

    返り値は (変形後, 確保しきれなかった周の量, ウエストより下で外へ動く量)。

    変形後の座標系で「中心前」「ウエストの線」「裾の線」の位置が要るので、
    X/Yの写像の節点からそれぞれ引く。節点が揃っていない(=基準点を持たない
    テンプレート等)場合は何もしない。
    """
    widening = hip_widening_cm(measurements.bust, measurements.hip,
                               fit_ease(fit).bodice_cm, fit_ease(fit).hip_cm)
    if widening <= 0 or not x_knots or len(y_knots) < 4:
        return scaled, 0.0, 0.0
    # X写像の節点は cf を中心に左右対称に並ぶ。中央の節点が中心前。
    cf_dst = x_knots[len(x_knots) // 2][1]
    # Y写像の節点は [首, 脇の下, ウエスト, 裾] の順(build_y_map参照)。
    underarm_dst = y_knots[1][1]
    waist_dst = y_knots[-2][1]
    hem_dst = y_knots[-1][1]
    start_y, applied = hip_widening_start_y(waist_dst, underarm_dst, hem_dst, widening)
    shortfall = max(0.0, widening - applied) * 4.0     # 4辺の合計=周の不足
    # round30: ウエストより下で脇線が外へ動く量。ウエストの絞り
    # (`_nip_waist`)は同じ区間を内から外へ戻るので、傾きの上限を分け合う。
    # これを渡さないと、両方が別々に上限いっぱいまで使い、合計では超える
    # (実測: バスト83/ウエスト50/ヒップ100の伸びる生地で傾き0.30となり、
    #  ウエストから裾までが脇線と認識されなくなった)。
    span = hem_dst - start_y
    at_waist = applied * min(1.0, max(0.0, (waist_dst - start_y) / span)) if span > 0 else 0.0
    return (apply_hip_widening(scaled, cf_dst, start_y, hem_dst, applied),
            shortfall, applied - at_waist)


def _nip_waist(scaled: list, x_knots: list, y_knots: list,
                measurements: Measurements, fit: "str | None",
                y_shift: float = 0.0,
                hip_widen_below_waist: float = 0.0) -> tuple[list, float]:
    """身頃の脇線をウエストの高さで内側へ絞る(round29)。

    絞る量は「ウエストで余っている量」の`WAIST_DART_SHARE_SIDE_SEAM`。
    余りの測り方はダーツ側(`compute_diamond_dart_plan`)と揃えてある——
    別々の測り方をすると、脇で絞った分とダーツで摘む分の合計が
    ウエスト+ゆとりにならなくなる。

    節点が揃っていない(=基準点を持たないテンプレート)場合は何もしない。
    """
    if not x_knots or len(y_knots) < 4:
        return scaled, 0.0
    cf_dst = x_knots[len(x_knots) // 2][1]
    underarm_dst = y_knots[1][1]
    # 胸ぐせダーツの口より下は、紙の上で y_shift だけ下がっている。
    # ウエストと裾はどちらも口より下なので、両方ずらす(袖の下は口より
    # 上なのでずらさない)。
    waist_dst = y_knots[-2][1] + y_shift
    hem_dst = y_knots[-1][1] + y_shift

    span = _x_range_at_y_from_segments(scaled, waist_dst)
    if span is None:
        return scaled, 0.0
    half_width = (span[1] - span[0]) / 2.0
    target = (measurements.waist + fit_ease(fit).waist_cm) / 4.0
    surplus_per_half = half_width - target
    if surplus_per_half <= 0:
        return scaled, 0.0
    # round30: 伸びる生地の型紙はダーツを入れない(`is_stretch`)。摘む先が
    # 無いので、ウエストの絞りは**すべて脇線**が担う。傾きの上限
    # (`hip_widening_start_y`が使うのと同じ考え方)で頭打ちになった分は
    # 呼び出し側が開示する。
    share = 1.0 if is_stretch(fit) else WAIST_DART_SHARE_SIDE_SEAM
    nip, shortfall = waist_nip_limit_cm(
        underarm_dst, waist_dst, hem_dst, surplus_per_half * share,
        hip_widen_below_waist=hip_widen_below_waist)
    scaled = apply_waist_nip(scaled, cf_dst, underarm_dst, waist_dst, hem_dst, nip)
    return scaled, shortfall * 4.0        # 4辺の合計=ウエスト周の不足


def _x_range_at_y_from_segments(segments: list, y: float) -> tuple[float, float] | None:
    from .compatibility import _x_range_at_y
    from .svgpath import segments_to_polyline

    return _x_range_at_y(segments_to_polyline(segments, curve_steps=200), y)


def scale_template(part_type: str, variation: str, segments: list,
                    measurements: Measurements,
                    fit_anchors: list[tuple[str, float]] | None = None,
                    design_length_cm: float | None = None,
                    fit_anchors_y: list[tuple[str, float]] | None = None,
                    fit: str | None = None,
                    dartless: bool = False,
                    block: Block = ADULT_FEMALE) -> ScaledPart:
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
    rx, ry = compute_scale_factors(measurements, part_type, fit, block)
    bust_point_y_cm: float | None = None
    hip_widen_below_waist = 0.0
    knots_for_nip: list = []
    y_knots_for_nip: list = []
    waist_y_cm: float | None = None
    bust_line_y_cm: float | None = None
    hip_shortfall_cm = 0.0
    chest_width_cm_actual: float | None = None
    chest_width_cm_target: float | None = None
    chest_width_limited = False
    # round57: 身頃と袖は、丈を変えても**上半分を動かさない**。
    #
    # round17以来、丈の指定はパーツ全体のY倍率を
    # `指定の丈 ÷ テンプレートの丈`で置き換えていた。スカート・パンツなら
    # それでよい(上端がウエストで、縫い合わせる相手の形が丈で変わらない)。
    # ところが身頃では襟ぐりと袖ぐり、袖では袖山が上半分にあり、
    # 全体を縮めると**袖ぐりが浅くなって袖が入らない / 袖山が縮んで袖が
    # 付かない**。脇の下の線より下だけを伸縮させて丈を合わせる。
    design_length_applied = None
    keep_length_above = ("underarm"
                         if part_type in BODICE_PART_TYPES or part_type == "sleeve"
                         else None)
    if design_length_cm is not None and design_length_cm > 0 and keep_length_above is None:
        design_length_applied = True
        # round17: イラストから読み取ったデザイン上の丈(cm)で、長さ方向の
        # 倍率を上書きする(engine/illustration_fit.py参照)。採寸から決まる
        # 丈は「体に対する標準的な丈」であって、描かれた服の丈ではない。
        min_x0, min_y0, max_x0, max_y0 = bounding_box(segments)
        template_length = max_y0 - min_y0
        if template_length > 0:
            ry = design_length_cm / template_length
    if part_type in LOWER_GARMENT_PART_TYPES and fit_anchors_y and design_length_cm is None:
        # round25: 股上(ウエスト〜股ぐり)はヒップで、股下は身長で決まる別々の
        # 量である。round24までY方向を身長比で一律に伸縮していたため、
        # ヒップ120cmの体型で股上が7cm浅い型紙が出ていた(座れない)。
        y_knots = build_pants_y_map(fit_anchors_y, measurements.hip, ry)
        if y_knots:
            scaled = remap_segments_x(segments, [], ry, y_knots=y_knots)
            scaled = scale_segments(scaled, rx, 1.0)
        else:
            scaled = scale_segments(segments, rx, ry)
    elif fit_anchors and part_type in FIT_ANCHOR_PART_TYPES:
        knots = build_x_map(fit_anchors, measurements.bust,
                            measurements.shoulder_width, rx, block)
        # round23: 袖ぐりの深さをバストに応じて深くする。Y方向も
        # 「首の付け根の線 / 脇の下の線 / 裾」を節点とする区分線形写像にする。
        # 基準線を持たないテンプレートや、イラストから丈を指定した場合
        # (design_length_cm。丈そのものを差し替えるので袖ぐりの基準線が
        # 意味を持たなくなる)は、従来どおり一律 ry 倍。
        y_knots = (build_y_map(fit_anchors_y, measurements.bust, ry, block,
                                measurements.height)
                   if fit_anchors_y else [])
        if design_length_cm is not None and design_length_cm > 0:
            design_length_applied = False
        if y_knots and design_length_cm is not None and design_length_cm > 0:
            # 脇の下より下だけを伸縮させて、着丈を指定どおりにする。
            # 作れない指定(上半分に食い込む等)ではNoneが返るので、
            # そのときは丈を効かせない(袖ぐりを壊すよりまし)。
            adjusted = apply_design_length_to_y_map(
                y_knots, design_length_cm, "underarm", fit_anchors_y)
            if adjusted is not None:
                y_knots = adjusted
                design_length_applied = True
        scaled = remap_segments_x(segments, knots, ry, y_knots=y_knots or None)
        # round31: 袖ぐりの点(中心から測って、前身頃なら胸幅・後ろ身頃なら
        # 背幅)を、新文化式の式が指す位置へ合わせる。ここまでの変形では
        # 袖ぐりのえぐれ量がテンプレートの定数のままなので、袖ぐりの点は
        # 「肩先からえぐれ量ぶん内側」——つまりバストではなく**肩幅**で
        # 決まっていた(engine/bodice_fit.pyの`fit_armhole_width`に実測)。
        # X方向の写像より後、ヒップの開き・ダーツより前に行う(袖ぐりは
        # ウエストより上にあり、以降の変形はそこへ触らない)。
        if len(y_knots) >= 2 and part_type in BODICE_PART_TYPES:
            cf_src = next((x for role, x in fit_anchors if role == "cf"), None)
            if cf_src is not None:
                chest_width_cm_target = bodice_side_width_cm(
                    part_type, measurements.bust, block)
                scaled, chest_width_cm_actual, chest_width_limited = fit_armhole_width(
                    scaled, underarm_y=y_knots[1][1], cf_x=cf_src * rx,
                    target_from_cf_cm=chest_width_cm_target)
        # round26: 裾はヒップの高さにある。バストで決まる幅では足りない体型
        # では、ウエストの線から裾へ向かって脇線を開かせ、ヒップが通る幅に
        # する(足りないままだと、そもそも着られない型紙になる)。
        scaled, hip_shortfall_cm, hip_widen_below_waist = _widen_for_hip(
            scaled, knots, y_knots, measurements, fit)
        # round27: ウエストの線の位置を控えておく(ダイヤモンドダーツを
        # そこへ置くため)。build_y_mapの節点は [首, 脇の下, ウエスト, 裾]。
        knots_for_nip, y_knots_for_nip = knots, y_knots
        if len(y_knots) >= 4:
            waist_y_cm = y_knots[-2][1]
        # round28: バストライン(=袖ぐり底の線)の位置も控えておく。
        # build_y_mapの節点は [首, 脇の下, ウエスト, 裾] なので、[1]が
        # 脇の下=バストラインにあたる。脇ダーツをBPへ向けるために使う。
        if len(y_knots) >= 2:
            bust_line_y_cm = y_knots[1][1]
            # round29: BPの**高さ**。乳下がりを採寸してもらえた場合だけ、
            # バストライン(袖ぐり底の線)ではなくその実測で決まる。
            # 乳下がりは「前中央で首の付け根から」なので、肩の高さの線
            # (y_knots[0])に前の襟ぐりの深さを足した位置が起点になる。
            bust_point_y_cm = bust_point_y_cm_fn(
                bust_line_y_cm,
                y_knots[0][1] + front_neck_depth_cm(measurements.bust, block),
                measurements.bust_point_drop)
    else:
        scaled = scale_segments(segments, rx, ry)
    hip_ease = fit_ease(fit).hip_cm if part_type in BODICE_PART_TYPES else None
    # round26: ヒップを通すために摘み量を減らしたかどうかを、変形する前の
    # 輪郭から先に調べておく(ダーツを入れた後では裾の形が変わって測れない)。
    waist_shaping_limited = (
        waist_dart_hip_limited(part_type, scaled, measurements, hip_ease)
        if hip_ease is not None else False)
    # round30: 伸びる生地(`is_stretch`)と、切り替え線で分割する身頃
    # (呼び出し側が dartless=True を渡す)はダーツを入れない。
    dartless = dartless or is_stretch(fit)
    scaled, waist_dart_count = apply_waist_dart(
        part_type, scaled, measurements, hip_ease_cm=hip_ease, dartless=dartless)
    # round29: 胸ぐせダーツは、口の幅ぶんだけ「口より下」を下げる
    # (`_shift_below`。縫い閉じてはじめて後ろ身頃と釣り合う)。つまり
    # **前身頃のウエストの線も、紙の上ではその分だけ下がる**。
    # round28まで摘み量は最大3cmだったので誤差が目立たなかったが、
    # round29で新文化式の角度式にしたところ最大10.6cmになり、ウエストの
    # 線を控えた位置(waist_y_cm)が実際の位置から10cm以上ずれた。ダイヤモンド
    # ダーツはその位置に置かれるので、胸の高さに置かれてしまう。
    # 下がった量は、ダーツを入れる前後で裾のyを比べて実測する
    # (ダーツが置けなかった場合は0になり、自動的に何も起きない)。
    _hem_before = bounding_box(scaled)[3]
    bust_dart_unfitted_cm = 0.0
    # round30: 伸びる生地の型紙はダーツを入れない。生地が伸びて胸の丸みに
    # 沿うので、ダーツで作る立体が要らない(ニット原型の定石)。バストラインと
    # BPの高さ自体は記録に残す(内部線として型紙に描くのに使う)ので、
    # ここではダーツを置く経路にだけNoneを渡す。
    bust_dart_count = 0
    if dartless:
        # 【なぜ「基準線を渡さない」では足りないか】`apply_bust_dart`に
        # bust_line_y=None を渡すと、round27までの旧係数へフォールバック
        # してしまう(バスト83超で摘み量が出る)。実測でバスト110・120の
        # 伸びる生地にダーツが2本入っていた。本数0を明示して止める。
        pass
    else:
        if bust_point_y_cm is not None:
            _intakes, bust_dart_unfitted_cm = bust_dart_split_for_part(
                part_type, scaled, measurements, bust_point_y_cm, block)
        scaled, bust_dart_count = apply_bust_dart(
            part_type, scaled, measurements, bust_line_y=bust_point_y_cm,
            block=block)
    if bust_dart_count == 0:
        bust_dart_unfitted_cm = 0.0
    bust_dart_shift = max(0.0, bounding_box(scaled)[3] - _hem_before)
    if waist_y_cm is not None and bust_dart_shift > 0:
        waist_y_cm += bust_dart_shift
    # round29: 脇線をウエストで絞る。新文化式のウエストダーツ配分表で
    # 脇線(c)が担う11%ぶん(`WAIST_DART_SHARE_SIDE_SEAM`)。ここで絞った
    # 残りをダーツが摘む(`waist_dart_share`が正規化済みの割合を返す)。
    #
    # 【なぜ胸ぐせダーツの**後**か】絞るにはウエストの高さに節点が要るので、
    # 脇線はそこで2本に割れる。先に割ってしまうと、胸ぐせダーツを置く側が
    # 「脇線候補がちょうど2本」という前提を満たせなくなるうえ、割れた上側
    # (袖の下〜ウエスト、約12cm)には2本ぶんのダーツの口が入らない
    # (実測: バスト110では12.55cm要るのに12.25cmしかなく、ダーツが消えた)。
    # 後に回せば、胸ぐせダーツは1本の脇線に置かれ、絞りはその上から掛かる。
    waist_nip_shortfall_cm = 0.0
    if part_type in BODICE_PART_TYPES:
        scaled, waist_nip_shortfall_cm = _nip_waist(
            scaled, knots_for_nip, y_knots_for_nip,
            measurements, fit, y_shift=bust_dart_shift,
            hip_widen_below_waist=hip_widen_below_waist)
    # round30: スカート・パンツも、伸びる生地ならダーツを入れない
    # (タイツ・スパッツ類がこれにあたる)。
    if dartless:
        skirt_dart_count = pants_dart_count = 0
    else:
        scaled, skirt_dart_count = apply_skirt_waist_dart(
            part_type, variation, scaled, measurements)
        scaled, pants_dart_count = apply_pants_waist_dart(
            part_type, variation, scaled, measurements)
    dart_count = waist_dart_count + bust_dart_count + skirt_dart_count + pants_dart_count
    # round71: 胸ぐせダーツの脚を、**全ての変形が終わってから**揃え直す。
    # ダーツを作った時点では脚はぴったり揃っているが、そのあとの
    # ウエスト絞り・裾の開きが口の点を動かす(実測0.138cmずれていた)。
    if bust_dart_count:
        scaled = retrue_bust_darts(scaled)
    min_x, min_y, max_x, max_y = bounding_box(scaled)
    # round40: 基準点を変形後の座標へ写して持たせる。knots/y_knotsは
    # fit_anchors/fit_anchors_yと同じ並びの (変形前, 変形後) なので、
    # 役割ラベルと変形後の値を組み合わせるだけでよい。
    def _scaled_anchors(roles, knot_list):
        if not roles or len(roles) != len(knot_list):
            return ()
        return tuple((role, dst) for (role, _src), (_s, dst)
                      in zip(roles, knot_list))

    anchors_scaled = _scaled_anchors(fit_anchors, locals().get("knots") or [])
    anchors_y_scaled = _scaled_anchors(fit_anchors_y, locals().get("y_knots") or [])
    return ScaledPart(
        part_type=part_type,
        variation=variation,
        segments=scaled,
        scale_x=rx,
        scale_y=ry,
        width_cm=max_x - min_x,
        height_cm=max_y - min_y,
        dart_count=dart_count,
        design_length_applied=design_length_applied,
        waist_shaping_limited=waist_shaping_limited,
        waist_y_cm=waist_y_cm,
        bust_line_y_cm=bust_line_y_cm,
        fit_anchors_scaled=anchors_scaled,
        fit_anchors_y_scaled=anchors_y_scaled,
        bust_point_y_cm=bust_point_y_cm,
        bust_dart_shift_cm=bust_dart_shift,
        bust_dart_unfitted_cm=bust_dart_unfitted_cm,
        waist_nip_shortfall_cm=waist_nip_shortfall_cm,
        hip_shortfall_cm=hip_shortfall_cm,
        chest_width_cm_actual=chest_width_cm_actual,
        chest_width_cm_target=chest_width_cm_target,
        chest_width_limited=chest_width_limited,
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

#: 二の腕まわりを採寸している場合に、袖山の高さを探す範囲(round25)。
#: 幅を腕から固定したうえで、袖山カーブの長さが袖ぐりに一致する高さを
#: 二分探索する。範囲の端に張り付いた場合は`engine/compatibility.py`の
#: チェック5が引き続き警告する(黙って辻褄を合わせない)。
SLEEVE_CAP_HEIGHT_MIN_SCALE = 0.2
SLEEVE_CAP_HEIGHT_MAX_SCALE = 4.0


def _template_cap_height_cm(fit_anchors_y: list[tuple[str, float]] | None
                             ) -> float | None:
    """袖テンプレートの袖山の高さ(cm)。基準線 cap〜underarm の間隔(round76)。

    12という数字をここへ書かない——テンプレートを描き変えたときに
    片方だけが古くなる(README round61「刷る文の中に数字を手書きしない」と
    同じ理由)。
    """
    if not fit_anchors_y:
        return None
    ys = dict(fit_anchors_y)
    if "cap" not in ys or "underarm" not in ys:
        return None
    height = ys["underarm"] - ys["cap"]
    return height if height > 0 else None


def scale_sleeve_to_cap_length(part_type: str, variation: str, segments: list,
                                measurements: Measurements,
                                target_cap_cm: float,
                                armhole_per_arm_cm: float | None = None,
                                fit_anchors_y: list[tuple[str, float]] | None = None,
                                fit: str | None = None,
                                design_length_cm: float | None = None,
                                shoulder_drop_cm: float | None = None,
                                block: Block = ADULT_FEMALE) -> ScaledPart:
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

    # round42: 袖丈の倍率も原型の下限に従う。ここだけ既定(0.7)のままだと、
    # 身長80〜131cmの子どもの袖丈が**全部38.4cm**で出ていた(実測)。
    _, ry = compute_scale_factors(measurements, part_type, block=block)

    # round24: 袖山の高さも袖ぐりに比例させる。round23までは袖丈比だけで
    # 動いていたため、袖ぐりが大きくなっても袖山が高くならず、袖山カーブの
    # 長さを合わせるために**幅ばかりが広がっていた**(バスト130で袖幅
    # 54.2cm。二の腕に対して大きすぎる)。袖山の高さを袖ぐりに比例させると
    # 45.98cmに収まる。袖丈は変わらない(`build_sleeve_y_map`)。
    # 丈の指定を当てられたかを、探索の中から拾う(下のScaledPartに載せる)。
    applied_flag: dict[str, bool] = {}

    def _shape_with(rx: float, cap_scale: float | None) -> list:
        knots = (build_sleeve_y_map(fit_anchors_y, cap_scale, ry)
                 if fit_anchors_y and cap_scale is not None else [])
        # round57: 袖丈の指定は、**袖山より下だけ**を伸縮させて当てる。
        # 全体を縦に縮めると袖山のカーブまで縮み、袖ぐりより短くなって
        # 袖が付かなくなる(袖山の長さは、この関数がわざわざ袖ぐりに
        # 合わせている当のものである)。
        if knots and design_length_cm is not None and design_length_cm > 0:
            adjusted = apply_design_length_to_y_map(
                knots, design_length_cm, "underarm", fit_anchors_y)
            applied_flag["ok"] = adjusted is not None
            if adjusted is not None:
                knots = adjusted
        scaled = scale_segments(segments, rx, 1.0 if knots else ry)
        if knots:
            scaled = remap_segments_x(scaled, [], ry, y_knots=knots)
        return scaled

    def _cap_len_of(shape: list) -> float:
        value = sleeve_cap_length(
            SimpleNamespace(stitch_line=segments_to_polyline(shape)))
        return value if value is not None else 0.0

    # round25: 二の腕まわりを採寸しているなら、**袖幅は腕から決める**のが
    # 正しい。袖ぐりに合わせるべきなのは袖山カーブの長さなので、幅を腕で
    # 固定したうえで袖山の高さの方を探す(実際のパタンナーの手順もこの順序)。
    # 採寸していない場合(従来)は、袖山の高さを袖ぐりに比例させて幅を探す。
    template_box = bounding_box(segments)
    template_width = template_box[2] - template_box[0]
    fixed_width_scale = None
    # round76: ドロップショルダーでは、袖山の高さは袖ぐりの25%(出典は
    # engine/drop_shoulder.py)に**決める**。決めた以上そこを探索変数には
    # できないので、二の腕を測っていても幅の方を探す側へ回す
    # (袖幅が二の腕から決まらなくなることは利用者へ開示する)。
    if (measurements.upper_arm is not None and template_width > 0
            and fit_anchors_y and shoulder_drop_cm is None):
        fixed_width_scale = (
            (measurements.upper_arm + fit_ease(fit).sleeve_cm) / template_width)

    if fixed_width_scale is not None:
        lo, hi = SLEEVE_CAP_HEIGHT_MIN_SCALE, SLEEVE_CAP_HEIGHT_MAX_SCALE

        def cap_len_h(cap_scale: float) -> float:
            return _cap_len_of(_shape_with(fixed_width_scale, cap_scale))

        if target_cap_cm <= 0 or cap_len_h(lo) <= 0:
            return scale_template(part_type, variation, segments, measurements,
                                   fit=fit, block=block)
        if cap_len_h(hi) < target_cap_cm:
            cap_scale = hi
        elif cap_len_h(lo) > target_cap_cm:
            cap_scale = lo
        else:
            while (hi - lo > 1e-6
                   and abs(cap_len_h((lo + hi) / 2.0) - target_cap_cm) > SLEEVE_FIT_TOLERANCE_CM):
                mid = (lo + hi) / 2.0
                if cap_len_h(mid) < target_cap_cm:
                    lo = mid
                else:
                    hi = mid
            cap_scale = (lo + hi) / 2.0
        scaled = _shape_with(fixed_width_scale, cap_scale)
        min_x, min_y, max_x, max_y = bounding_box(scaled)
        return ScaledPart(
            part_type=part_type, variation=variation, segments=scaled,
            scale_x=fixed_width_scale, scale_y=ry,
            width_cm=max_x - min_x, height_cm=max_y - min_y, dart_count=0,
        )

    cap_scale_from_armhole = (sleeve_cap_height_scale(armhole_per_arm_cm)
                              if armhole_per_arm_cm else None)
    if shoulder_drop_cm is not None and armhole_per_arm_cm:
        from .drop_shoulder import cap_height_scale as _drop_cap_height_scale
        template_cap_height = _template_cap_height_cm(fit_anchors_y)
        if template_cap_height:
            dropped = _drop_cap_height_scale(armhole_per_arm_cm, template_cap_height)
            if dropped is not None:
                cap_scale_from_armhole = dropped

    def _shape(rx: float) -> list:
        return _shape_with(rx, cap_scale_from_armhole)

    def cap_len(rx: float) -> float:
        return _cap_len_of(_shape(rx))

    lo, hi = SLEEVE_FIT_MIN_SCALE, SLEEVE_FIT_MAX_SCALE
    if target_cap_cm <= 0 or cap_len(lo) <= 0:
        return scale_template(part_type, variation, segments, measurements,
                               fit=fit, block=block)
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

    scaled = _shape(rx)
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
        design_length_applied=(applied_flag.get("ok")
                                if design_length_cm else None),
    )


def bodice_fit_clamp_warning(fit_anchors: list[tuple[str, float]],
                              measurements: Measurements,
                              block: Block = ADULT_FEMALE) -> str | None:
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
    rx, _ry = compute_scale_factors(measurements, "front_bodice", block=block)
    effective = effective_shoulder_width_cm(
        fit_anchors, measurements.bust, measurements.shoulder_width, rx, block)
    if effective is None or abs(effective - measurements.shoulder_width) <= 0.05:
        return None
    return (
        f"肩幅={measurements.shoulder_width:g}cmは、バスト={measurements.bust:g}cmから"
        f"決まる身頃の幅に収まらないため、実際には{effective:.1f}cm相当として"
        "型紙を生成しました(肩先は脇線より内側にしか置けません)。"
        "バストか肩幅のどちらかの採寸値を確認してください。"
    )


def measurement_clamp_warnings(measurements: Measurements,
                                fit: str | None = None,
                                block: Block = ADULT_FEMALE) -> list[str]:
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
        # round23: バストは身頃の幅を「バスト + 一定のゆとり」で決めるように
        # なったので、クランプに当たる実際の境界も動いた(83×1.6=132.8cmから
        # (83+8)×1.6-8=137.6cmへ)。ここで従来どおり素のバスト比を見ていると、
        # **実際には正しく生成できている値に対して「132.8cm相当にしました」と
        # 嘘の注記を出す**ことになる。倍率の決め方と、それを利用者へ説明する
        # 文言は同じ式から作る。
        if field_name == "bust":
            ease = bodice_ease_for(measurements, fit, block)
            ratio = bodice_x_scale(actual, ease)
            low = bodice_bust_cm_for_scale(MIN_SCALE, ease)
            high = bodice_bust_cm_for_scale(MAX_SCALE, ease)

            def to_cm(r, _ease=ease):
                return bodice_bust_cm_for_scale(r, _ease)
        else:
            ratio = actual / standard
            # round42: 下限は原型ごとに違う(`Block.min_scale`)。既定のまま
            # 文言を作ると、実際にはクランプしていないのに
            # 「◯cm相当にしました」と**嘘の注記**が出る。
            min_scale = MIN_SCALE if block.min_scale is None else block.min_scale
            low, high = standard * min_scale, standard * MAX_SCALE

            def to_cm(r, _standard=standard):
                return _standard * r

        # round42: 実際にクランプされたかどうかも原型の下限で判定する。
        # 既定(0.7)で判定すると、子ども原型では**クランプしていないのに
        # 警告が出る**(実測: 身長80〜131cmの全サイズで、身長・袖丈・肩幅・
        # ヒップに身に覚えのない「◯cm相当にしました」が並んでいた)。
        low_ratio = MIN_SCALE if block.min_scale is None else block.min_scale
        clamped_ratio = max(low_ratio, min(MAX_SCALE, ratio))
        if clamped_ratio != ratio:
            effective = to_cm(clamped_ratio)
            warnings.append(
                f"{label}={actual:g}cmはテンプレートの変形可能範囲"
                f"(標準サイズの{low_ratio:g}〜{MAX_SCALE}倍 ≒ "
                f"{low:.1f}〜{high:.1f}cm)を"
                f"超えているため、実際には{effective:.1f}cm相当として"
                "型紙を生成しました。正確な型紙が必要な場合は手作業での"
                "補正を検討してください。"
            )
    return warnings
