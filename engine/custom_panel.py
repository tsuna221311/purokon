"""custom_panel.py — 定型テンプレートに当てはまらない自由形状パーツ。round9で追加。

これまでの「テンプレート＋変形」方式は、既存の`pattern_templates/`のいずれか
（ネックライン・袖・スカート等、標準Mサイズの比率で起こした既知の輪郭）に
必ず当てはめる設計だった。アニメ画像のコスプレ衣装や、舞台衣装のラフな
デザイン画のように、そもそも定型のカテゴリに当てはまらない形状（マント・
翼・肩当て・胸当て等の装甲プレート・小道具など）は、この方式では原理的に
対応できない。

このモジュールは、利用者が画像から取得した輪郭（自動抽出または手動トレース、
あるいはその両方を組み合わせたもの）を、参照線1本の実寸(cm)を基準に
比例スケーリングして、そのままカット用の型紙パーツ（part_type="custom_panel"）
にする機能を提供する。

正直な限界（最初に明記する）:
  - **画像に写っている輪郭は「体にドレープした状態の見た目」であり、平らな
    状態の型紙パーツの形そのものではない。** 実際の縫製では、身頃・スカート
    のように体に沿ってドレープする部分の型紙は、見た目の輪郭とは異なる形状
    （ゆとり分・ダーツ・見返し等を織り込んだ、体に巻き付けた時に初めて
    見た目通りになる形）をしている。このモジュールは輪郭を**そのまま**
    拡大縮小するだけなので、体にフィットさせたい部分に使うと、縫い上げた
    ときに見た目通りのフィット感にならない可能性が高い。
  - このモジュールが正直に実力を発揮できるのは、**体に沿わない平面的な
    パーツ**（マント・帯・旗・翼・EVAフォーム等で作る装甲プレートのような
    硬質な小道具）である。実際のコスプレ制作でも「参考画像を印刷し、
    実寸に拡大縮小してから輪郭通りに切り出す」という手法が広く使われており、
    この機能はその手法をそのままコード化したものに近い。
  - 校正（画像のピクセル距離→実寸cm）は、利用者が指定した2点間の直線距離
    1本だけを基準にした**一様な**拡大縮小である。画像が斜めから描かれている
    (パース/遠近感がある)場合、実際の形状とはズレが生じる。
  - 自動抽出したシルエットは`engine/segmentation.py`の
    `SimpleSilhouetteSegmenter`と同じ限界（複雑な背景・人物着用写真等では
    精度が落ちる）を持つ。手動トレース（頂点のクリック指定）はこの限界を
    受けないが、利用者自身の手間が増える。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    from shapely.geometry import Polygon as _ShapelyPolygon
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover - shapely未導入環境向け
    _HAS_SHAPELY = False

#: 1パーツあたりの頂点数の許容範囲。少なすぎると多角形にならず、
#: 多すぎるとブラウザでの手動調整・自動トレースの誤検出が扱いにくい上、
#: サーバー側の処理コストも無視できなくなる。
MIN_CUSTOM_PANEL_POINTS = 3
MAX_CUSTOM_PANEL_POINTS = 300

#: 校正後のパーツの外接矩形が、この範囲(cm)に収まらない場合はエラーにする
#: (`engine/part_specs.py`のMIN_SCALE/MAX_SCALEと同じ「明らかに単位/桁を
#: 間違えた入力を早期に弾く」ための安全装置)。
MIN_CUSTOM_PANEL_DIMENSION_CM = 2.0
MAX_CUSTOM_PANEL_DIMENSION_CM = 300.0

#: 校正用の参照線(reference line)の2点が近すぎると、わずかなクリック位置の
#: 誤差で校正倍率が暴走する(距離で割るため)。ピクセル単位の最小距離。
MIN_REFERENCE_PIXEL_DISTANCE = 2.0

#: 校正用の実寸(cm)側の許容範囲。
MIN_REFERENCE_CM = 0.5
MAX_REFERENCE_CM = 300.0

#: 1回のリクエストで追加できるカスタムパーツの上限(乱用防止)。
MAX_CUSTOM_PANELS_PER_REQUEST = 12

#: measurement_fieldとして指定を許可する採寸項目(Measurementsのフィールド名)。
ALLOWED_MEASUREMENT_FIELDS = {"bust", "waist", "hip", "height", "sleeve_length", "shoulder_width"}

CUSTOM_PANEL_PART_TYPE = "custom_panel"

#: ラベル(パーツ名)の最大長。型紙PDF/DXFにそのまま印字されるため、
#: 極端に長い文字列がレイアウトを壊さないよう上限を設ける。
MAX_LABEL_LENGTH = 40

#: 1つのカスタムパーツで指定できる枚数(quantity)の上限。
MAX_CUSTOM_PANEL_QUANTITY = 8


def validate_label(raw_label: object) -> str:
    if not isinstance(raw_label, str) or not raw_label.strip():
        raise CustomPanelError("カスタムパーツにはラベル(名前)を入力してください。")
    label = raw_label.strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise CustomPanelError(f"ラベルは{MAX_LABEL_LENGTH}文字以内にしてください。")
    return label


def validate_quantity(raw_quantity: object) -> int:
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        raise CustomPanelError("枚数(quantity)は整数で指定してください。") from None
    if not (1 <= quantity <= MAX_CUSTOM_PANEL_QUANTITY):
        raise CustomPanelError(f"枚数(quantity)は1〜{MAX_CUSTOM_PANEL_QUANTITY}の範囲で指定してください。")
    return quantity


class CustomPanelError(ValueError):
    """カスタムパーツの入力(輪郭・校正情報)が不正な場合に送出する。

    ValueErrorのサブクラスにしているのは、app.py側の既存の
    `except ValueError`(採寸値エラー等と同じ「文言をこちらが完全に制御する
    安全な入力エラー」経路)にそのまま乗せられるようにするため。
    """


def _parse_xy(item: object, what: str) -> tuple[float, float]:
    try:
        if isinstance(item, dict):
            x, y = float(item["x"]), float(item["y"])
        else:
            x, y = float(item[0]), float(item[1])
    except (KeyError, TypeError, ValueError, IndexError):
        raise CustomPanelError(f"{what}の座標データが不正です。") from None
    if not (math.isfinite(x) and math.isfinite(y)):
        raise CustomPanelError(f"{what}の座標に不正な数値が含まれています。")
    return (x, y)


def _validate_points(raw_points: object, what: str = "輪郭") -> list[tuple[float, float]]:
    """複数点（輪郭全体）用。頂点数の範囲チェックを含む。"""
    if not isinstance(raw_points, (list, tuple)):
        raise CustomPanelError(f"{what}の形式が不正です。")
    if not (MIN_CUSTOM_PANEL_POINTS <= len(raw_points) <= MAX_CUSTOM_PANEL_POINTS):
        raise CustomPanelError(
            f"{what}の頂点数は{MIN_CUSTOM_PANEL_POINTS}〜{MAX_CUSTOM_PANEL_POINTS}個の"
            f"範囲にしてください（現在{len(raw_points)}個）。"
        )
    return [_parse_xy(item, what) for item in raw_points]


def _validate_point_pair(raw_point: object, what: str) -> tuple[float, float]:
    """校正用の参照点1個用。輪郭とは違い、単一の(x, y)座標そのもの。"""
    return _parse_xy(raw_point, what)


def resolve_reference_cm(reference_cm: float | None, measurement_field: str | None,
                          measurements: "object | None") -> float:
    """校正用の実寸(cm)を、手入力値または採寸値から解決する。

    round9のAskUserQuestionで「両方できるようにして」という回答だったため、
    (1) 利用者が直接cm値を入力する方式と、(2) 既存の採寸値
    (バスト・身長等)を参照線の実寸として流用する方式の両方に対応する。
    どちらも「参照線1本の実寸」という同じ形の入力に正規化されるため、
    以降のスケーリング計算は完全に共通化できる。
    """
    if reference_cm is not None:
        try:
            value = float(reference_cm)
        except (TypeError, ValueError):
            raise CustomPanelError("reference_cmは数値で指定してください。") from None
        if not (MIN_REFERENCE_CM <= value <= MAX_REFERENCE_CM):
            raise CustomPanelError(
                f"基準寸法は{MIN_REFERENCE_CM}〜{MAX_REFERENCE_CM}cmの範囲で指定してください。"
            )
        return value
    if measurement_field:
        if measurement_field not in ALLOWED_MEASUREMENT_FIELDS or measurements is None:
            raise CustomPanelError(f"measurement_fieldが不正です: {measurement_field!r}")
        return float(getattr(measurements, measurement_field))
    raise CustomPanelError("reference_cm または measurement_field のいずれかを指定してください。")


def calibrate_points_to_cm(raw_points: object, ref_point_a: object, ref_point_b: object,
                            reference_cm: float) -> list[tuple[float, float]]:
    """トレースした輪郭(任意の単位、通常は画像のピクセル座標)を、参照線
    (ref_point_a〜ref_point_b、同じ単位系の2点)の実寸(reference_cm)を基準に
    一様スケーリングしてcm単位の輪郭に変換する。

    変換後は外接矩形の左上が原点(0,0)付近に来るよう平行移動する（他の
    テンプレートSVGと同様、原点近くに配置する慣習に合わせているだけで、
    ネスティング時にどのみち再配置されるため必須ではない）。
    """
    points = _validate_points(raw_points, what="輪郭")
    a = _validate_point_pair(ref_point_a, what="参照点A")
    b = _validate_point_pair(ref_point_b, what="参照点B")

    pixel_distance = math.hypot(b[0] - a[0], b[1] - a[1])
    if pixel_distance < MIN_REFERENCE_PIXEL_DISTANCE:
        raise CustomPanelError(
            "校正用の参照線の2点が近すぎます。実寸が分かっている、なるべく"
            "離れた2点を指定してください。"
        )
    if not (MIN_REFERENCE_CM <= reference_cm <= MAX_REFERENCE_CM):
        raise CustomPanelError(
            f"基準寸法は{MIN_REFERENCE_CM}〜{MAX_REFERENCE_CM}cmの範囲で指定してください。"
        )

    scale = reference_cm / pixel_distance  # cm / (入力座標の1単位)
    cm_points = [(x * scale, y * scale) for x, y in points]

    min_x = min(p[0] for p in cm_points)
    min_y = min(p[1] for p in cm_points)
    normalized = [(x - min_x, y - min_y) for x, y in cm_points]

    width = max(p[0] for p in normalized) - min(p[0] for p in normalized)
    height = max(p[1] for p in normalized) - min(p[1] for p in normalized)
    if width < MIN_CUSTOM_PANEL_DIMENSION_CM and height < MIN_CUSTOM_PANEL_DIMENSION_CM:
        raise CustomPanelError(
            f"校正結果のパーツが小さすぎます(幅{width:.1f}cm×高さ{height:.1f}cm)。"
            "参照線の実寸(reference_cm)や輪郭の指定を見直してください。"
        )
    if width > MAX_CUSTOM_PANEL_DIMENSION_CM or height > MAX_CUSTOM_PANEL_DIMENSION_CM:
        raise CustomPanelError(
            f"校正結果のパーツが大きすぎます(幅{width:.1f}cm×高さ{height:.1f}cm、"
            f"上限{MAX_CUSTOM_PANEL_DIMENSION_CM}cm)。参照線の実寸(reference_cm)や"
            "輪郭の指定を見直してください。"
        )
    return normalized


def mirror_points_x(cm_points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """パーツ自身の外接矩形の左右を反転した点列を返す(左右対称パーツ用)。

    肩当て・パウルドロン等、体の左右で鏡像になるパーツを1回のトレースから
    両方作れるようにするための補助。単純な水平反転であり、実際の左右で
    絵柄・パース(遠近感)が非対称な場合まではケアしない(正直な限界)。
    """
    if not cm_points:
        return []
    max_x = max(p[0] for p in cm_points)
    return [(max_x - x, y) for x, y in cm_points]


def points_to_segments(cm_points: list[tuple[float, float]]) -> list[tuple[str, list[float]]]:
    """cm単位の頂点列を、このプロジェクト共通のパスセグメント形式に変換する。

    shapelyが使える場合、自己交差を`Polygon.buffer(0)`で可能な範囲まで
    自動修復する(`engine/seam.py`の縫い代オフセット処理が自己交差した
    多角形に対して不安定になるため、可能な限りここで健全化しておく)。
    自動修復できない場合は明確なエラーにする(黙って歪んだ型紙を出さない、
    このプロジェクト一貫の方針)。
    """
    if len(cm_points) < MIN_CUSTOM_PANEL_POINTS:
        raise CustomPanelError("輪郭の頂点数が不足しています。")

    coords = list(cm_points)
    if _HAS_SHAPELY:
        poly = _ShapelyPolygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.geom_type != "Polygon":
            raise CustomPanelError(
                "輪郭が自己交差しており、自動修復できませんでした。"
                "トレースをやり直してください。"
            )
        coords = list(poly.exterior.coords)[:-1]  # 終点=始点の重複を除く
        if len(coords) < MIN_CUSTOM_PANEL_POINTS:
            raise CustomPanelError("輪郭の自己交差を修復した結果、多角形として成立しませんでした。")

    segments: list[tuple[str, list[float]]] = [("M", [coords[0][0], coords[0][1]])]
    for x, y in coords[1:]:
        segments.append(("L", [x, y]))
    segments.append(("Z", []))
    return segments


@dataclass(frozen=True)
class CustomPanelSpec:
    """1つのカスタムパーツの、校正済み(cm単位)の入力をまとめたもの。

    `points_cm`は既に`calibrate_points_to_cm`を通した後の実寸(cm)座標。
    生成履歴からの再生成(round8機能)では、ピクセル座標や校正情報を
    保持し直す必要がなく、この校正済み座標だけをJSONに保存すれば
    再現できる(app.pyのregen_spec参照)。
    """
    label: str
    points_cm: list[tuple[float, float]]
    quantity: int = 1
    mirror: bool = False
