"""measurements.py — 採寸値と標準Mサイズの定義。

採寸値(B/W/H/身長/袖丈/肩幅)を標準Mサイズとの差分でX/Y比例変形する、
という処理を実装するための入力データ構造。
"""

from __future__ import annotations
from dataclasses import dataclass, fields

# 採寸として許容する範囲（cm）。パタンナー業務で現実的にありえる範囲の外側は
# 入力ミス（単位違い・桁間違い）である可能性が高いため、早期に弾く。
#
# 【round42で下限を子どもまで広げた】round41までの下限は
# 身長120 / 袖丈30 / 肩幅25 / バスト50 で、これは**成人女子だけを見た範囲**
# だった。子ども服の型紙を引こうとすると、
#   1歳(身長80・袖丈24)・4歳(身長102)・6歳(身長114)
# はどれも入力の時点でエラーになり、**そもそも試せなかった**。
# 参考寸法の出典: MAISON DE AS「採寸の仕方【男性・女性・子供】」
# https://maisondeas.com/taking-measurements/
# (1歳: 身長80・バスト50・ウエスト48・ヒップ50・肩幅24・袖丈24)
#
# 下限は「1歳児より一回り小さいところ」に置いてある。単位間違い(1.6mと
# 入力する等)は依然として弾かれる。**どの原型に合うか**は範囲ではなく
# 原型ごとの警告で伝える(engine/blocks.pyの`height_note`)——
# 境目の体型は実在するので、入力を拒むのではなく選び直せるようにする。
_VALID_RANGES = {
    "bust": (40.0, 160.0),
    "waist": (35.0, 150.0),
    "hip": (40.0, 170.0),
    "height": (70.0, 210.0),
    "sleeve_length": (15.0, 90.0),
    "shoulder_width": (18.0, 60.0),
    # round25で追加した任意項目(二の腕まわり)。指定された場合のみ検証する。
    "upper_arm": (15.0, 60.0),
    # round29で追加した任意項目。
    # 乳間: 左右の乳頭の間隔。9号(バスト83)で18cm前後。
    "bust_point_spacing": (10.0, 40.0),
    # 乳下がり: 前中央で首の付け根からバストの一番高いところまで。
    # ドレメ式の参考寸法で7号16.5cm〜17号21cm。
    "bust_point_drop": (10.0, 40.0),
    # round75で追加した任意項目(頭囲)。成人女性の平均57cm・男性58cmで、
    # 帽子のサイズ展開が概ね54〜62cmなので、子どもから大きめまで入る幅。
    "head_circumference": (40.0, 70.0),
}


#: 未指定(None)を許す任意の採寸項目(round25)。
_OPTIONAL_FIELDS = frozenset({"upper_arm", "bust_point_spacing",
                              "bust_point_drop", "head_circumference"})


@dataclass(frozen=True)
class Measurements:
    """1人分の採寸値（単位: cm）。"""

    bust: float
    waist: float
    hip: float
    height: float
    sleeve_length: float
    shoulder_width: float
    #: 二の腕まわり(round25で追加した**任意**項目)。
    #:
    #: 指定すると袖幅がこの実測から決まる。未指定(None)なら従来どおり
    #: 袖ぐりから相似で決まる(engine/scaling.pyの`scale_sleeve_to_cap_length`)。
    #: 位置引数の並びを変えないよう末尾に置き、既定値をNoneにしてある
    #: (既存の呼び出しを1つも書き換えずに済む)。
    upper_arm: float | None = None
    #: 乳間(round29で追加した**任意**項目)。左右の乳頭の間隔(cm)。
    #:
    #: 指定するとBP(バストポイント)の左右位置がこの実測から決まる。未指定
    #: なら新文化式の推定式(胸幅/2 + 0.7)にフォールバックする
    #: (engine/bodice_fit.pyの`bust_point_from_cf_cm`)。
    bust_point_spacing: float | None = None
    #: 乳下がり(round29で追加した**任意**項目)。前中央で首の付け根から
    #: バストの一番高いところ(BP)までの長さ(cm)。
    #:
    #: 指定するとBPの**高さ**がこの実測から決まる。未指定なら原型と同じく
    #: 「BPはバストライン(袖ぐり底の線)の上にある」とみなす
    #: (engine/bodice_fit.pyの`bust_point_y_cm`)。
    bust_point_drop: float | None = None
    #: 頭囲(round75で追加した**任意**項目)。眉間から後頭部の一番出ている
    #: ところまでを一周した長さ(cm)。
    #:
    #: フードの大きさがこの実測から決まる(engine/hood.py)。未指定なら
    #: 成人女性の平均57cmで引き、**その旨を利用者へ開示する**。
    head_circumference: float | None = None

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None and f.name in _OPTIONAL_FIELDS:
                continue          # 任意項目は未指定を許す
            if not isinstance(value, (int, float)):
                raise TypeError(f"{f.name} は数値である必要があります: {value!r}")
            if value <= 0:
                raise ValueError(f"{f.name} は正の値である必要があります: {value}")
            lo, hi = _VALID_RANGES[f.name]
            if not (lo <= value <= hi):
                raise ValueError(
                    f"{f.name}={value} は現実的な範囲({lo}〜{hi}cm)外です。"
                    " 単位(cm)や入力値を確認してください。"
                )

    def as_dict(self) -> dict[str, float]:
        """採寸値の辞書。未指定の任意項目は**含めない**。

        JSONのレスポンスや保存済みプロフィールにNoneが混ざると、受け手が
        「0cm」と誤って扱いうるため、項目ごと落とす。
        """
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) is not None}


# JIS L 4005 成人女子M相当を参考にした標準体型（概算値）。
# テンプレート型紙(pattern_templates/)はすべてこの体型を基準に作られている。
STANDARD_M = Measurements(
    bust=83.0,
    waist=66.0,
    hip=91.0,
    height=158.0,
    sleeve_length=52.0,
    shoulder_width=37.0,
)


# --- round5「複数サイズの一括生成(グレーディング)」で追加 -----------------
#
# 本物のアパレル業務における「グレーディング」は、ブランド・アイテムごとに
# 個別に設定された「グレーディングルール(号数間の各部位の増減量)」を使う、
# 職人的なノウハウの塊であり、本プロジェクトがそれを正確に再現することは
# できない。ここではJIS L4005のS/M/L系列で一般的に見られる「バスト・ウエスト・
# ヒップは4cm刻み、身長は号数で変えない(同じ着丈のまま)、肩幅・袖丈は1cm刻み」
# という大まかな傾向を単純化した、線形の近似ルールを採用する。
#
# 正直な限界: 実際の号数展開は各部位が号数に比例して単純に増減するわけではなく
# (例えばバストは号数が上がるほど増分が微妙に変わることがある)、かつ本ルールは
# あくまで既定値であり、ブランド・アイテム固有のグレーディングルールを反映した
# ものではない。あくまで「基準として入力した1サイズ分の採寸値から、目安となる
# 前後のサイズを機械的に生成する」ための単純化した近似であることを明記する。
STANDARD_SIZE_GRADE_CM: dict[str, float] = {
    "bust": 4.0,
    "waist": 4.0,
    "hip": 4.0,
    "height": 0.0,
    "sleeve_length": 1.0,
    "shoulder_width": 1.0,
    # round25: 二の腕まわり。バスト4cm刻みに対して1.0cmは、実務の
    # グレーディングで使われる範囲(1.0〜1.4cm)の下限にあたる控えめな値。
    "upper_arm": 1.0,
    # round29: 乳間・乳下がり。どちらも推測ではなく、既に根拠のある値から
    # 導いている。
    #   乳下がり: ドレメ式の参考寸法(7号16.5→9号17→11号18→13号19→
    #             15号20→17号21cm)は号数1つあたり約1.0cm。
    #   乳間: 新文化式のBPの式から 乳間 = 2×(B/16 + 3.8) なので、
    #         バスト4cm刻みに対して 2×4/16 = 0.5cm。
    "bust_point_spacing": 0.5,
    "bust_point_drop": 1.0,
    # round75: 頭囲。サイズ展開でバストが4cm動いても、頭はほとんど
    # 変わらない(帽子はS/M/Lで2cm刻み)。**0.0にはしない**——0だと
    # 「グレーディングの対象外」なのか「刻みが0」なのか読めないので、
    # 帽子のサイズ展開のいちばん細かい刻みである0.5cmを置く。
    "head_circumference": 0.5,
}

# サイズ名 -> 基準サイズ(入力した採寸値をこのサイズとみなす)からの刻み数。
# 号数展開の系列としてよく使われるXS/S/M/L/XLの5段階のみをサポートする。
STANDARD_SIZE_STEPS: dict[str, int] = {"XS": -2, "S": -1, "M": 0, "L": 1, "XL": 2}
STANDARD_SIZE_ORDER: tuple[str, ...] = ("XS", "S", "M", "L", "XL")


def graded_measurements(base: Measurements, size: str,
                         grade_cm: dict[str, float] | None = None) -> Measurements:
    """基準となる採寸値(base、通常は利用者が「自分の実測値」として入力した
    もの)を「M」相当とみなし、そこから刻み幅で前後にずらしたサイズの
    採寸値を返す。

    例えば`size="L"`なら、既定では(grade_cm未指定なら)バスト・ウエスト・
    ヒップはbaseよりそれぞれ+4cm、肩幅・袖丈は+1cm、身長はbaseのまま、
    という採寸値になる。

    grade_cm: round7で追加。指定すれば、`STANDARD_SIZE_GRADE_CM`の代わりに
        この呼び出しだけで使う部位ごとのカスタム刻み幅(下記
        「カスタムグレーディングルール」参照)。全項目を指定する必要はなく、
        指定しなかった項目は既定値(STANDARD_SIZE_GRADE_CM)のまま使われる。
        事前に`validate_custom_grade_cm()`で検証済みの値を渡すこと
        (この関数自体は値の範囲を検証しない)。
    """
    if size not in STANDARD_SIZE_STEPS:
        raise ValueError(
            f"size は {sorted(STANDARD_SIZE_STEPS)} のいずれかを指定してください: {size!r}"
        )
    step = STANDARD_SIZE_STEPS[size]
    effective_grade_cm = dict(STANDARD_SIZE_GRADE_CM)
    if grade_cm:
        effective_grade_cm.update(grade_cm)
    values = {}
    for name in effective_grade_cm:
        current = getattr(base, name)
        # round25: 任意項目(二の腕まわり)は、未指定ならサイズ展開しても
        # 未指定のまま。0cmとして扱うと入力検証で落ちる。
        values[name] = (None if current is None
                        else current + effective_grade_cm[name] * step)
    return Measurements(**values)


# --- round7「カスタムグレーディングルール対応」で追加 -----------------------
#
# round6の調査(このファイル冒頭のコメント、および下記「グレーディング
# ルールの精度向上」の調査結果参照)で、「本物のアパレル業務における
# グレーディングルールは、ブランド・アイテムごとに個別に設定された職人的な
# ノウハウであり、本プロジェクトが根拠を持って再現できる公開された標準値は
# 見つからなかった」という結論に至った。実在しない「より正確な既定値」を
# 推測で作ることは、実際には精度が上がっていないのに精度が上がったという
# 誤った印象を与えかねないため見送っている。
#
# その代わり、自社の実際のグレーディングルール(部位ごとの号数1段階あたりの
# 増減量)を既に把握している利用者(仕立て業者・ブランド等)が、そのルールを
# そのまま入力できるようにする方が、存在しない標準値を捏造するより正直な
# 対応だと判断した。`validate_custom_grade_cm()`で検証した上で
# `graded_measurements()`/`grading_relative_change_notes()`に渡す。
#: カスタムグレーディングルールの各部位刻み幅として許容する範囲(cm)。
#: これは号数1段階あたりの「増減量」であり、実際の採寸値(cm)そのものでは
#: ない。既定値(STANDARD_SIZE_GRADE_CM、最大4.0cm)よりはるかに広い範囲を
#: 許容しつつ、「刻み幅の欄に採寸値をそのまま入力してしまう」ような単位
#: 違いの入力ミスを早期に弾くための現実的な上限を設けている。
_CUSTOM_GRADE_CM_RANGE = (-20.0, 20.0)


def validate_custom_grade_cm(grade_cm: dict[str, float]) -> dict[str, float]:
    """カスタムグレーディングルール(部位ごとの号数1段階あたりのcm刻み幅)の
    妥当性を検証し、float化した辞書を返す。

    キーは`STANDARD_SIZE_GRADE_CM`と同じ6項目のうち一部または全部を指定
    できる(指定しない項目は`graded_measurements()`側で既定値のまま使われる)。
    値は数値で、`_CUSTOM_GRADE_CM_RANGE`の範囲内であること。
    """
    unknown = sorted(set(grade_cm) - set(STANDARD_SIZE_GRADE_CM))
    if unknown:
        raise ValueError(
            f"grade_cmに指定できない項目があります: {unknown}。"
            f"指定可能な項目は{sorted(STANDARD_SIZE_GRADE_CM)}です。"
        )
    lo, hi = _CUSTOM_GRADE_CM_RANGE
    validated: dict[str, float] = {}
    for name, value in grade_cm.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(f"grade_cm[{name!r}] は数値である必要があります: {value!r}")
        if not (lo <= value <= hi):
            raise ValueError(
                f"grade_cm[{name!r}]={value} は現実的な範囲({lo}〜{hi}cm)外です。"
                "号数1段階あたりの増減量(採寸値そのものではない)を指定してください。"
            )
        validated[name] = float(value)
    return validated


# --- round6「複数サイズ間の形状一貫性の調査」で追加 -------------------------
#
# `graded_measurements`は各サイズの採寸値を独立に算出するだけで、生成される
# 型紙の輪郭やダーツ本数がサイズの並び順に対して「見た目に自然な連続性」を
# 持つかどうかは、複数サイズ機能を追加したround5の時点では検証していなかった。
# round6でこれを実際に調査した。
#
# 調査方法: `scale_template()`を直接呼び出す(重いフルパイプラインを介さない)
# 高速な経路で、bust/waist/hipの組み合わせを70〜120cm(5cm刻み)・50〜100cm
# (5cm刻み)・70〜120cm(5cm刻み)の範囲で総当たりし(有効な採寸範囲外の組み
# 合わせは除外)、それぞれを基準(M相当)としてXS〜XLの5サイズにグレーディング
# した上で、front_bodice・back_bodice・skirt(tight)の3パーツ合計ダーツ本数を
# サイズごとに算出した。1331通りの基準体型を検証した結果、42通り(約3.2%)で
# 「あるサイズのダーツ本数が、両隣のサイズと比べて谷(局所的に少ない)または
# 山(局所的に多い)になる」という、サイズ順に見て不連続な変化が見つかった
# (例: bust=70/waist=50/hip=70cmを基準にすると、ダーツ合計本数が
# XS=0→S=4→M=0→L=0→XL=0のように、Sサイズだけ突出して多くなる)。
#
# 根本原因: ダーツの要否・本数は「バスト比とウエスト比の差」のような**比率**
# のしきい値(`compute_dart_plan`等の`MIN_DART_INTAKE_CM`等)で決まる一方、
# サイズ間のグレーディングは`STANDARD_SIZE_GRADE_CM`という**絶対cm刻み**で
# 各部位を動かす。この2つの計算方式(比率ベースの判定 × 絶対値ベースの
# グレーディング)の組み合わせにより、ある部位の比率がサイズの節目付近で
# 「しきい値をまたぐ・またがない」を細かく行き来してしまうことがあり、
# 結果としてダーツ本数がサイズの並び順に対して単調に増減しない(=谷や山が
# 生じる)ケースが一定割合で発生する。
#
# 対応方針: 各サイズ単体で見れば、そのサイズの採寸比率に対して算出される
# ダーツ本数は正しい(バグではない)。問題は「サイズ間で並べたときの見た目の
# 一貫性」であり、これを完全に解消するには、ダーツ判定をサイズ単体の比率
# ではなく「基準サイズからの差分の推移」に基づいて設計し直す必要があるが、
# これは単一サイズ生成のダーツ判定ロジック(既に本番で使われている
# `compute_dart_plan`等)を複数サイズ生成のためだけに変更することになり、
# 影響範囲・リスクが大きい。round6では、より低リスクな対応として、
# この不整合を検出して利用者に正直に開示する診断機能
# (`detect_dart_count_inconsistencies`)を追加するに留めた。


def detect_dart_count_inconsistencies(dart_counts_by_size: dict[str, int]) -> list[str]:
    """サイズごとのダーツ本数の辞書から、サイズの並び順(`STANDARD_SIZE_ORDER`)
    に対して不連続な変化(谷または山)をしているサイズを検出し、説明文の
    リストを返す。

    `dart_counts_by_size`に3サイズ未満しか含まれない場合は、谷/山を判定
    する両隣が揃わないため常に空リストを返す。連続する3サイズが同じ本数
    (平ら)の場合は谷でも山でもないため検出しない。
    """
    ordered_sizes = [s for s in STANDARD_SIZE_ORDER if s in dart_counts_by_size]
    if len(ordered_sizes) < 3:
        return []

    counts = [dart_counts_by_size[s] for s in ordered_sizes]
    messages: list[str] = []
    for i in range(1, len(counts) - 1):
        prev_size, cur_size, next_size = ordered_sizes[i - 1], ordered_sizes[i], ordered_sizes[i + 1]
        prev_count, cur_count, next_count = counts[i - 1], counts[i], counts[i + 1]
        is_valley = cur_count < prev_count and cur_count < next_count
        is_peak = cur_count > prev_count and cur_count > next_count
        if is_valley or is_peak:
            messages.append(
                f"{cur_size}サイズのダーツ本数({cur_count}本)が、"
                f"{prev_size}サイズ({prev_count}本)・{next_size}サイズ({next_count}本)と比べて"
                "サイズ順に不連続に変化しています(体型比率とグレーディングの"
                "絶対cm刻みの兼ね合いで起こる既知の現象です。各サイズ単体としては"
                "正しく算出されていますが、サイズ間で見た目の一貫性が無く見える"
                "場合があります)。"
            )
    return messages


# --- round6「グレーディングルールの精度向上」の調査結果 ---------------------
#
# 「グレーディングルールの精度を上げてほしい」という依頼を受け、実際の
# 号数展開業務で使われる代替案を調査した。
#
# (1) 累進グレーディング(号数が標準から離れるほど刻み幅を大きくする)は
#     一部のブランドで実際に使われる手法だが、具体的な刻み幅は各社の
#     ノウハウであり、本プロジェクトが根拠を持って再現できる公開された
#     標準値は見つからなかった。根拠の無い数値へ単純に置き換えることは、
#     実際には精度が上がっていないのに「精度が上がった」という誤った印象を
#     与えかねないため見送った。
# (2) 乗算式グレーディング(絶対cmではなく体型比率を保つよう刻む)も検討した
#     が、実際の号数展開(JIS L4005含む)は伝統的に「絶対cm刻み」が標準的な
#     手法であり、乗算式への変更はむしろ実務の慣行から外れる方向の変更に
#     なるため見送った。
# (3) グレーディング後の採寸値が解剖学的に矛盾しないか(例: ウエストが
#     バスト/ヒップを超えてしまわないか)を、現実的な基準体型(ウエストが
#     バスト・ヒップより小さい)2110通りで検証したが、矛盾するケースは
#     1件も見つからなかった(現行の絶対cm刻みルール自体に、この観点での
#     具体的な不具合は無い)。
#
# 数値そのものを変更する安全な改善は見つからなかったが、調査の過程で、
# 現行の「絶対cm刻み」方式が原理的に持つ、正直に開示すべき性質を発見した:
# 同じ絶対cmの増減でも、採寸値が小さい体型ほど相対的な変化率が大きくなる
# (例: バスト83cmの標準体型ではXSで-9.6%だが、バスト60cmの小柄な体型では
# 同じ-8cmの変化が-13.3%になる)。これはグレーディングロジックの不具合では
# なく絶対cm刻み方式そのものの数学的な性質だが、利用者が「グレーディング
# されたXSサイズが、Mサイズと比べて想定以上に細く感じる」といった違和感を
# 持った際に、その原因を正しく理解できるよう、相対変化率が大きい場合に
# 開示する診断機能(`grading_relative_change_notes`)を追加した。
_LARGE_RELATIVE_GRADE_THRESHOLD = 0.15
_GRADED_FIELD_LABELS = {"bust": "バスト", "waist": "ウエスト", "hip": "ヒップ"}


def grading_relative_change_notes(base: Measurements, sizes: list[str],
                                   grade_cm: dict[str, float] | None = None) -> list[str]:
    """指定したサイズへグレーディングした際、絶対cm刻み(既定では
    `STANDARD_SIZE_GRADE_CM`、`grade_cm`指定時はそれで上書きした値)が
    baseの実際の採寸値に対して大きな相対変化率になっている項目を検出し、
    説明文のリストを返す。

    同じ絶対cmの増減でも、採寸値が小さい体型ほど相対的な変化率は大きくなる
    (例えばウエスト45cmの人の-8cmは-17.8%だが、ウエスト100cmの人の-8cmは
    -8.0%)。これはグレーディングロジックの不具合ではなく、絶対cm刻み方式
    そのものの数学的な性質だが、体型によっては「サイズ間の変化が大きすぎる
    /小さすぎる」と感じる原因になり得るため、変化率が大きい項目を開示する。

    grade_cm: round7で追加。`graded_measurements()`に渡したのと同じ
        カスタムグレーディングルールをここにも渡すことで、実際に使われた
        刻み幅に基づいた正しい変化率を診断できる(渡さない場合は既定値
        `STANDARD_SIZE_GRADE_CM`のまま計算するため、カスタムルールを
        使った生成に対してこの引数を省略すると、実際とは異なる刻み幅で
        診断してしまう点に注意)。
    """
    effective_grade_cm = dict(STANDARD_SIZE_GRADE_CM)
    if grade_cm:
        effective_grade_cm.update(grade_cm)
    notes: list[str] = []
    seen: set[tuple[str, str]] = set()
    for size in sizes:
        if size not in STANDARD_SIZE_STEPS or size == "M":
            continue
        step = STANDARD_SIZE_STEPS[size]
        for field, label in _GRADED_FIELD_LABELS.items():
            base_value = getattr(base, field)
            if base_value <= 0:
                continue
            delta = effective_grade_cm[field] * step
            relative = delta / base_value
            if abs(relative) < _LARGE_RELATIVE_GRADE_THRESHOLD:
                continue
            key = (size, field)
            if key in seen:
                continue
            seen.add(key)
            notes.append(
                f"{size}サイズでは、{label}が基準値から{delta:+.1f}cm"
                f"({relative * 100:+.1f}%)変化します。絶対cm刻みのグレーディング"
                "は、採寸値が小さいほど同じcm変化が相対的に大きくなるため、"
                f"{label}が細めの体型では特にこの傾向が出ます。実際の号数展開が"
                f"この通りになるとは限らないため、{size}サイズは目安として"
                "扱ってください。"
            )
    return notes
