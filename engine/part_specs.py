"""part_specs.py — パーツ種ごとの体型スケーリング規則。

パーツごとに「横のみ(スカート幅)」「縦横両方(袖丈)」のルールを定義して
精度を担保する、という設計をコードとして表現したもの。

x_measure / y_measure に Measurements のフィールド名を指定すると、
「標準Mサイズとの比率」でその軸を変形する。None を指定した軸は変形しない
(常に1.0倍＝標準Mサイズのまま)。
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ScaleRule:
    x_measure: str | None  # 幅方向(X)を決める採寸項目。Noneなら幅は固定。
    y_measure: str | None  # 長さ方向(Y)を決める採寸項目。Noneなら長さは固定。
    note: str = ""


PART_SCALE_RULES: dict[str, ScaleRule] = {
    # 身頃: 幅はバスト、長さは身長（着丈）に比例。縦横両方を変形する。
    "front_bodice": ScaleRule("bust", "height", "身頃は幅=バスト、丈=身長比で両方変形"),
    "back_bodice": ScaleRule("bust", "height", "身頃は幅=バスト、丈=身長比で両方変形"),
    # 前開きファスナー用に中心前で分割した前パネル(round5)。スケーリング則
    # 自体はfront_bodiceと同じ(幅=バスト、丈=身長比)。
    "front_bodice_zip_panel": ScaleRule("bust", "height", "前開き前パネルは幅=バスト、丈=身長比で両方変形"),
    # 袖: 「縦横両方」変形の代表例。
    # 幅(振り)は肩幅、長さは袖丈で変形する。
    "sleeve": ScaleRule("shoulder_width", "sleeve_length", "袖は幅=肩幅、丈=袖丈で両方変形"),
    # スカート: 幅はウエストとヒップの両方から必要量を求める(下記
    # LOWER_GARMENT_FIT参照)。丈(標準M基準の長さ)はデザイン通りに固定する。
    "skirt": ScaleRule("hip", None, "スカートは幅=ウエスト/ヒップの必要量、丈は固定"),
    # パンツ: 幅はスカートと同じ考え方、丈は身長に比例。round5で前パーツ
    # (front_pants)・後ろパーツ(back_pants)に分離した。
    "front_pants": ScaleRule("hip", "height", "パンツ(前)は幅=ウエスト/ヒップの必要量、丈=身長比"),
    "back_pants": ScaleRule("hip", "height", "パンツ(後)は幅=ウエスト/ヒップの必要量、丈=身長比"),
    # 帯状パーツ: 対応する採寸に応じて長さ(=帯の長さ方向であるX)のみ変形する。
    "collar": ScaleRule("bust", None, "衿は首回りの近似としてバスト比でX(帯の長さ)のみ変形"),
    "cuffs": ScaleRule("sleeve_length", None, "カフスは腕の太さの近似として袖丈比でX(帯の長さ)のみ変形"),
    "waistband": ScaleRule("waist", None, "ウエストバンドはウエスト比でX(帯の長さ)のみ変形"),
    # round75: フードは**伸縮させない**。頭囲と首ぐりの2つから製図する
    # (engine/hood.py)。比率で伸ばすと、頭が入る大きさと首ぐりに付く長さの
    # どちらか片方しか合わない。
    "hood": ScaleRule(None, None, "フードは頭囲と首ぐりから製図する(比率で伸縮させない)"),
    # round9で追加: custom_panel(定型に当てはまらない自由形状パーツ、
    # engine/custom_panel.py参照)は、輪郭取得時に校正(参照線の実寸cm)済み
    # のため、採寸値による追加のスケーリングを一切行わない
    # (x_measure/y_measure=Noneの効果は「常に倍率1.0」であることを
    # scale_template()経由で保証している)。
    "custom_panel": ScaleRule(None, None, "カスタムパーツは校正済みの実寸(cm)のためスケーリングしない"),
}

# --- round12(続き)で追加: 下半身パーツの幅は、ウエストとヒップの両方を見る ---
#
# 【なぜ必要か】スカート・パンツは round11 まで幅をヒップ比だけで変形して
# いた。ウエストとヒップの差は engine/darts.py のウエストダーツが吸収する
# 設計だったが、ダーツは「余った幅を摘む」ことしかできず、**足りない幅を
# 足すことはできない**。標準M(ウエスト66・ヒップ91)はウエスト/ヒップ比が
# 0.725とくびれの強い体型なので、それより胴が寸胴寄りの体型では
# ウエストが足りず、スカートやパンツが閉まらない型紙になっていた。
# 実測では、ウエスト88・ヒップ102の体型でウエスト周が13.8cm不足していた。
#
# 【対処】幅の倍率を「ウエストが必要とする倍率」と「ヒップが必要とする倍率」
# の大きい方にする。ウエスト側が効いた場合はヒップにゆとりが出るが、
# 「腰は少しゆるい」で済むのに対し「ウエストが閉まらない」は着られないため、
# こちらを優先する。ヒップ側が効いた場合(くびれの強い体型)は従来通りで、
# 余ったウエスト幅はウエストダーツが摘む。
#
# 基準値はテンプレートの実寸(scripts/generate_templates.py)と対:
#   スカート … 前後2枚で ウエスト68cm / ヒップ95cm
#   パンツ  … 前後左右4枚で ウエスト68cm / ヒップ95cm
# ゆとりは、ウエスト2cm・ヒップ4cm(テンプレート側の設計値と同じ)。
#: 身頃パーツ。幅は「バスト + 一定のゆとり」で決める(round23。
#: engine/bodice_fit.py の BODICE_EASE_CM / bodice_x_scale 参照)。
BODICE_PART_TYPES = {"front_bodice", "back_bodice", "front_bodice_zip_panel"}


# --- round24: ゆとり量を利用者が選べるようにする ---------------------------
#
# round23でゆとりを「体の大きさによらず一定」にしたが、その一定値は
# テンプレートの設計値(身頃8cm / ウエスト2cm / ヒップ4cm)に固定で、
# 利用者は選べなかった。ゆとりは体型ではなく**着方の好み**で決まる量で、
# 衣装制作では特に効いてくる(下に重ね着する、動きの大きい演目、逆に
# 体の線を出したい等)。
#
# 各プリセットの値は、布帛の身頃で一般に使われるゆとりの範囲
#   フィット 4〜6cm / 標準 8〜12cm / ゆったり 14〜20cm
# の中から選んだ。範囲そのものは製図の定石だが、その中のどの値にするかは
# 設計上の選択であり、「計算で求まる唯一の正解」ではない(標準は
# テンプレートの設計値8cmをそのまま使い、既定を選んだ場合に
# round23までと1mmも変わらないようにしてある)。
@dataclass(frozen=True)
class FitEase:
    """1つの「着方」に対応するゆとり量(cm)。"""

    label: str
    bodice_cm: float
    waist_cm: float
    hip_cm: float
    #: 袖(二の腕まわり)のゆとり。round25で追加。テンプレートの袖幅32cmは
    #: 「二の腕まわり約27cm + ゆとり5cm」として設計されている
    #: (scripts/generate_templates.pyのコメント)ので、標準はその5cm。
    #: 二の腕まわりを採寸した場合にだけ効く。
    sleeve_cm: float = 5.0


#: 二の腕まわりの標準値(cm)。テンプレートの袖幅32cmが「二の腕27cm +
#: ゆとり5cm」として設計されている(scripts/generate_templates.py)ので、
#: その27cmをそのまま使う。伸びる生地で二の腕を採寸していない場合に、
#: 縮小率を掛ける相手として要る。
_STANDARD_UPPER_ARM_CM = 27.0

FIT_PRESETS: dict[str, FitEase] = {
    "fitted": FitEase("ぴったり(体の線を出す)", 4.0, 1.0, 2.0, 3.0),
    "standard": FitEase("標準", 8.0, 2.0, 4.0, 5.0),
    "relaxed": FitEase("ゆったり(重ね着・動きの大きい衣装)", 14.0, 4.0, 8.0, 8.0),
}
DEFAULT_FIT = "standard"


#: 自由入力のゆとりとして受け付ける範囲(cm)。round25で追加。
#: 上限は「ゆったり」のさらに上を想定した実用的な上限で、これを超える量は
#: もはやゆとりではなくデザイン(ドレープ・ギャザー)の領域になる。
#:
#: 【round30で下限をマイナスへ広げた】伸びる生地(ニット・ストレッチ)の
#: 型紙は、体の寸法より**小さく**作る(マイナスのゆとり=ネガティブイーズ)。
#: 伸びた状態で体に沿わせるので、体と同寸だと着たときにたるむ。
#: コスプレではボディスーツ・レオタード・タイツ類がまさにこれで、
#: round29までのこのエンジンでは**1枚も作れなかった**(下限が0.0だった)。
#: 下限は、伸縮率100%の生地に対する定石の縮小率
#: (`STRETCH_REDUCTION_TABLE`の最大10%)を、想定しうる最大のバスト160cmに
#: 適用した -16cm を丸めて -20cm としている。
CUSTOM_EASE_RANGES: dict[str, tuple[float, float]] = {
    "bodice_cm": (-20.0, 30.0),
    "waist_cm": (-15.0, 15.0),
    "hip_cm": (-20.0, 20.0),
    "sleeve_cm": (-10.0, 20.0),
}


# --- round30: 伸びる生地(ニット・ストレッチ)への対応 -------------------------
#
# 【伸縮率の測り方】生地を10cm四方に切り、無理なく伸びる長さまで引っぱって
# 測る。15cmまで伸びれば伸縮率50%(atelier hagireの測定ボードの手順)。
#
# 【縮小率】伸縮率の区分ごとに、体の寸法から何%引くか。
# dresspatternmaking.com の "Reduction in Width for Stretch Blocks" の表を
# そのまま使う:
#
#   Stable Knits      (18-25%)  → 2%
#   Moderate Knits    (26-50%)  → 3%
#   Stretchy Knits    (51-75%)  → 5%
#   Super Stretch     (76-100%) → 10%
#
# 【正直な注記: 資料どうしが食い違っている】同じサイトの別記事
# "Stretch Basics for Patternmaking, Part 2: Blocks" は、同じ区分に対して
# 0% / 2% / 3% / 5% という**一段小さい**値を挙げている。さらに別の資料
# (mislope) は「生地の伸びをすべて使い切る」考え方で、伸縮率50%なら
# (1 − 1/1.5) = 33% 引く、という桁違いに大きい値を出す。これは水着・
# レオタードのような**密着させる**衣装の考え方で、同じ「ニット」でも
# 用途が違う。
#
# ここでは、表題そのものが幅の縮小率を扱っている前者の表を既定にし、
# 密着させたい場合は`cling`で「生地の伸びをどこまで使うか」を上げられる
# ようにしてある(既定1.0=表の値そのまま、2.0で倍)。どちらが正しいかは
# 生地と用途で変わるので、片方を正解として黙って決めない。
#: (伸縮率の上限%, 縮小率) の並び。上から順に見て最初に当てはまるものを使う。
STRETCH_REDUCTION_TABLE: tuple[tuple[float, float], ...] = (
    (25.0, 0.02),
    (50.0, 0.03),
    (75.0, 0.05),
    (100.0, 0.10),
)
#: 伸縮率がこれ未満なら、伸びる生地として扱わない(布帛と同じ)。
MIN_STRETCH_PERCENT = 18.0
#: 受け付ける伸縮率の範囲(%)。200%(3倍に伸びる)を超える生地は、
#: 測り間違い(元の長さと伸ばした長さを取り違えた等)の可能性が高い。
STRETCH_PERCENT_RANGE = (0.0, 200.0)
#: 「生地の伸びをどこまで使うか」の範囲。1.0が上表そのまま。
CLING_RANGE = (0.5, 3.0)


def stretch_reduction_ratio(stretch_percent: float, cling: float = 1.0) -> float:
    """伸縮率(%)から、体の寸法に対する縮小率を返す(0.0〜)。

    表の区分の上限を超える伸縮率は、いちばん上の区分(10%)で頭打ちにする。
    伸縮率が`MIN_STRETCH_PERCENT`未満なら0(布帛と同じ扱い)。
    """
    if stretch_percent < MIN_STRETCH_PERCENT:
        return 0.0
    ratio = STRETCH_REDUCTION_TABLE[-1][1]
    for upper, value in STRETCH_REDUCTION_TABLE:
        if stretch_percent <= upper:
            ratio = value
            break
    return ratio * cling


def validate_stretch_input(stretch_percent: float, cling: float = 1.0) -> tuple[float, float]:
    """伸縮率と密着度の入力を検証して返す。範囲外は明確なエラーにする。"""
    for name, value, (lo, hi) in (("伸縮率", stretch_percent, STRETCH_PERCENT_RANGE),
                                   ("密着度", cling, CLING_RANGE)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name}は数値である必要があります: {value!r}")
        if not (lo <= value <= hi):
            raise ValueError(
                f"{name}={value} は指定できる範囲({lo}〜{hi})外です。")
    return float(stretch_percent), float(cling)


def custom_fit_ease(**values: float | None) -> FitEase:
    """数値で直接指定したゆとりから`FitEase`を作る(round25)。

    指定しなかった項目は既定("standard")の値を使う(部分的な上書きが可能)。
    範囲外や数値でない値はエラーにする——黙って丸めると、指定したゆとりと
    実際に使われたゆとりが食い違うことに利用者は気付けない。
    """
    base = FIT_PRESETS[DEFAULT_FIT]
    merged = {"bodice_cm": base.bodice_cm, "waist_cm": base.waist_cm,
              "hip_cm": base.hip_cm, "sleeve_cm": base.sleeve_cm}
    for name, value in values.items():
        if name not in CUSTOM_EASE_RANGES:
            raise ValueError(
                f"ゆとりに指定できる項目は {sorted(CUSTOM_EASE_RANGES)} です: {name!r}")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"ゆとり {name} は数値である必要があります: {value!r}")
        lo, hi = CUSTOM_EASE_RANGES[name]
        if not (lo <= value <= hi):
            raise ValueError(
                f"ゆとり {name}={value} は指定できる範囲({lo}〜{hi}cm)外です。")
        merged[name] = float(value)
    label = ("指定したゆとり("
             f"身頃+{merged['bodice_cm']:g}cm / ウエスト+{merged['waist_cm']:g}cm / "
             f"ヒップ+{merged['hip_cm']:g}cm / 袖+{merged['sleeve_cm']:g}cm)")
    return FitEase(label, merged["bodice_cm"], merged["waist_cm"],
                    merged["hip_cm"], merged["sleeve_cm"])


def stretch_fit_ease(bust_cm: float, waist_cm: float, hip_cm: float,
                      stretch_percent: float, cling: float = 1.0,
                      upper_arm_cm: float | None = None) -> FitEase:
    """伸びる生地のゆとり(=マイナスのゆとり)を、採寸値から組み立てる。

    縮小率は**割合**なので、部位ごとのcmはその部位の寸法から決まる
    (バスト90cmの5%は4.5cm、ウエスト60cmの5%は3.0cm)。`FitEase`は
    cmで持つ仕組みなので、ここで割合をcmへ直す。

    袖(二の腕まわり)は、採寸が無ければ標準的な二の腕27cmを仮に使う。
    ここだけ0にすると、袖幅が「二の腕そのまま」になってしまう。
    """
    stretch_percent, cling = validate_stretch_input(stretch_percent, cling)
    ratio = stretch_reduction_ratio(stretch_percent, cling)
    if ratio <= 0:
        return FIT_PRESETS[DEFAULT_FIT]
    arm = upper_arm_cm if upper_arm_cm else _STANDARD_UPPER_ARM_CM
    label = (f"伸びる生地(伸縮率{stretch_percent:g}%"
             + (f"・密着度{cling:g}" if cling != 1.0 else "")
             + f" → 体の寸法から{ratio * 100:.0f}%引く)")
    return FitEase(label,
                    bodice_cm=-bust_cm * ratio,
                    waist_cm=-waist_cm * ratio,
                    hip_cm=-hip_cm * ratio,
                    sleeve_cm=-arm * ratio)


def is_stretch(fit: "str | FitEase | None") -> bool:
    """このゆとり指定が「伸びる生地」か(=身頃のゆとりがマイナスか)。

    伸びる生地の型紙は、原型の定石として**ダーツを入れない**。生地が
    伸びて胸やウエストの丸みに沿うので、ダーツで作る立体が要らない
    (dresspatternmaking: "Given that knits stretch, you don't need darts.
    …that's why Knit Blocks are dartless.")。判定を1か所に集めておく。
    """
    return fit_ease(fit).bodice_cm < 0


def fit_ease(fit: "str | FitEase | None") -> FitEase:
    """プリセット名(または`FitEase`そのもの)からゆとり量を引く。

    未知の名前はエラーにする。黙って標準へ落とすと、指定したつもりの
    ゆとりが効いていないことに利用者は出来上がりを見るまで気付けない。

    round25から`FitEase`をそのまま渡せる(数値で直接指定した場合。
    `custom_fit_ease`参照)。呼び出し側の配管を増やさずに済ませるため、
    「プリセット名 または ゆとりそのもの」を同じ引数で受ける。
    """
    if isinstance(fit, FitEase):
        return fit
    key = fit or DEFAULT_FIT
    if key not in FIT_PRESETS:
        raise ValueError(
            f"fit は {sorted(FIT_PRESETS)} のいずれかを指定してください: {fit!r}")
    return FIT_PRESETS[key]

LOWER_GARMENT_PART_TYPES = {"skirt", "front_pants", "back_pants"}
LOWER_BASE_WAIST_CM = 68.0
LOWER_BASE_HIP_CM = 95.0
LOWER_WAIST_EASE_CM = 2.0
LOWER_HIP_EASE_CM = 4.0


def lower_garment_x_scale(waist_cm: float, hip_cm: float,
                           fit: str | None = None) -> float:
    """スカート・パンツの幅方向の倍率を、ウエストとヒップの必要量から求める。

    round24で`fit`(ゆとりのプリセット)を受け取るようにした。省略すると
    従来どおりテンプレートの設計値(ウエスト2cm/ヒップ4cm)を使う。
    """
    ease = fit_ease(fit)
    return max((waist_cm + ease.waist_cm) / LOWER_BASE_WAIST_CM,
               (hip_cm + ease.hip_cm) / LOWER_BASE_HIP_CM)


# 極端な入力（例: 身長210cmなど）でテンプレートが破綻しない範囲にクランプする。
MIN_SCALE = 0.7
MAX_SCALE = 1.6

# --- round11で追加: 帯状パーツ専用の、より広いクランプ範囲 -------------------
#
# MIN_SCALE/MAX_SCALE(0.7〜1.6)は、front_bodice/back_bodice/sleeve/skirt/
# front_pants/back_pantsのような「曲線を含み、X/Y両方向に変形するパーツ」が
# 極端な入力で破綻しないための安全域として選ばれている(曲線の制御点を大きく
# 伸縮させると、カーブどうしが交差して型紙として無効な形状になりうる)。
#
# 一方 collar/cuffs/waistband は、いずれもscripts/generate_templates.pyの
# `_write_band`で単純な矩形として生成され、ScaleRule(下記PART_SCALE_RULES)も
# X方向のみを変形する(Y方向は常に1.0倍で固定)。矩形をX方向にだけ伸縮する
# 変形は、倍率がどれだけ大きく/小さくても自己交差が原理的に起こらない
# (4頂点の矩形が細長く/短くなるだけ)。つまりこれらに身頃と同じ狭い
# クランプを適用する理由は無い。
#
# 実際、round11でこのクランプの影響を実測したところ、Measurements自体が
# 受け付ける有効な入力の両端で、3種類とも必ずクランプが効いてしまっていた:
#   collar   (bust比):          有効範囲50〜160cm  → 比率0.602〜1.928
#   cuffs    (sleeve_length比):  有効範囲30〜90cm   → 比率0.577〜1.731
#   waistband(waist比):          有効範囲40〜150cm  → 比率0.606〜2.273
# 例えばウエスト150cmの利用者に対し、ウエストバンドは本来2.273倍にすべき
# ところ1.6倍で頭打ちになり、実測で約3割短い型紙が出ていた(生地を裁って
# 初めて気づく類の実害)。
#
# そこで上記3項目の比率の和集合(最も広い範囲)を帯状パーツ専用のクランプと
# して採用し、有効な採寸値の範囲内では一切クランプが起きないようにした。
# 単位間違い等の異常入力に対する歯止めは、Measurements側の入力検証
# (_VALID_RANGES)が引き続き担う。
BAND_PART_TYPES = {"collar", "cuffs", "waistband"}

#: 帯状パーツの倍率のクランプ範囲。
#:
#: 【round42で式から求めるようにした】round41までは
#: `MIN_SCALE_BAND = 30.0 / 52.0`(cuffsのsleeve_length下限30cm÷標準52cm)と
#: **数値を書き写して**いた。round42で子どもを入力できるように
#: `_VALID_RANGES`の下限を広げた(袖丈30→15cm)ところ、この写しが古いまま
#: 残り、**子どものカフスが約2倍の長さでクランプされる**状態になった
#: (tests/test_measurements_and_scaling.py が実際に落ちて発覚)。
#: 同じ数字を2か所に置くのをやめ、`_VALID_RANGES`と`STANDARD_M`から
#: 毎回求める。以後は範囲を動かしても写し忘れが起きない。
_BAND_DRIVING_MEASURES = ("bust", "sleeve_length", "waist")


def _band_scale_bounds() -> tuple[float, float]:
    from .measurements import STANDARD_M, _VALID_RANGES
    ratios = []
    for name in _BAND_DRIVING_MEASURES:
        lo, hi = _VALID_RANGES[name]
        standard = getattr(STANDARD_M, name)
        ratios.append((lo / standard, hi / standard))
    return (min(r[0] for r in ratios), max(r[1] for r in ratios))


MIN_SCALE_BAND, MAX_SCALE_BAND = _band_scale_bounds()


def clamp_scale_for_part(value: float, part_type: str,
                          min_scale: float | None = None) -> float:
    """part_typeに応じて、通常のクランプか帯状パーツ用の広いクランプを選ぶ。

    min_scale: round42。原型ごとの下限(`engine/blocks.py`の`Block.min_scale`)。
        Noneなら全体の既定(`MIN_SCALE`)。子ども原型はここを下げないと、
        身長110cm未満の型紙が**全部同じ丈**で出る(実測)。
    """
    if part_type in BAND_PART_TYPES:
        return max(MIN_SCALE_BAND, min(MAX_SCALE_BAND, value))
    lo = MIN_SCALE if min_scale is None else min_scale
    return max(lo, min(MAX_SCALE, value))


def clamp_scale(value: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, value))
