"""segmentation.py — イラストからパーツ領域を抽出する（STEP②「SAM分割」相当）。

本来はSAM(Segment Anything Model)でイラストを意味のある領域に分割する設計。
SAMは重み・依存が重い(チェックポイントが数百MB〜)ため、このリポジトリには
まだ同梱していない。

代わりに、輪郭(シルエット)抽出ベースの軽量な SimpleSilhouetteSegmenter を
既定実装として用意した。環境変数 SAM_CHECKPOINT_PATH が設定されていて
`segment_anything` パッケージが使える場合は、本物のSAMを使う SAMSegmenter に
自動的に切り替わる（get_default_segmenter）。

どちらの実装も同じ Segmenter インターフェースを満たすので、AIパイプライン
(pipeline.py)側のコードは変更せずに差し替えられる。

【round7での再検討: MiDaS(深度推定)を採用しない判断の再確認・詳細化】
  以前から「MiDaS(深度推定)は縫い代補正の補助として検討したが、技術難易度・
  投資対効果の観点から現時点では本実装に含めていない」とだけ記していたが、
  round7で「何のために検討したのか」「なぜ見送ったのか」を、SAMを見送った
  時と同じ水準の具体的な技術的根拠まで掘り下げて再調査した。

  想定していた用途: このアプリのイラストモードは、SAM/SimpleSilhouetteSegmenter
  で領域を切り出し、Claude APIで各領域の`part_type`/`variation`(例:
  「パフスリーブ」「プリーツスカート」)を判定するところまでで、実際の
  パターン形状は`pattern_templates/`の固定テンプレート+採寸スケーリングを
  使う(下記「AI連携部分について」README節、および本ファイル冒頭参照)。
  つまり、イラストに描かれた「実際のふくらみ・ギャザー量・プリーツの
  折り込み分量」はテンプレート側の固定値であり、イラスト自体からは
  読み取っていない。MiDaSで単眼深度マップが得られれば、イラスト上の
  「ふくらんで見える箇所」を検出し、それをダーツ・ギャザー・プリーツの
  分量調整のヒントに使えるのではないか、というのが検討の出発点だった。

  round7で実際に、この開発環境からMiDaSの学習済み重みを取得できるか
  (プロトタイピングして実測できるか)を試した: `torch`はPyPI経由で
  インストールできたが、公式配布元である`torch.hub.load('intel-isl/MiDaS',
  ...)`はgithub.com/raw.githubusercontent.comへのHTTPアクセスが必要であり、
  この環境のネットワーク許可リスト外であるため実際に接続を試みたところ
  `HTTPError: HTTP Error 400: Bad Request`で失敗した。代替のHugging Face
  経由での取得も試みたが、同様に`huggingface.co`への接続が
  `403 Forbidden`で失敗した。したがって、この開発環境では実際にMiDaSの
  推論を1回も実行できておらず、本物の深度マップによる実測評価はできて
  いない(正直な限界。SAMの重みを本リポジトリに同梱していないのと同じ
  理由で、この開発・検証環境から重み配布元へ到達できないことも影響している。
  ただしこれはこの検証環境固有のネットワーク制限であり、実際の運用環境
  (開発者自身のマシン等、通常のインターネット接続がある環境)では重みを
  取得できる可能性が高い点は明記しておく。つまりこの接続失敗自体は
  不採用の決定的な理由ではない)。

  実際に不採用と判断した理由は、それとは別に以下の2点である。
  1. MiDaSはVOC/NYU等の自然写真データセットで学習・検証されたモデルで
     あり、その深度推定は「連続的な陰影(shading)・遮蔽(occlusion)の
     写真的な手がかり」を前提にしている。一方、このアプリのイラスト
     モードが実際に受け取る入力は、`SimpleSilhouetteSegmenter`の
     docstring(本ファイル)が明記する通り「明度ベースの輪郭抽出」で
     扱えることを前提にした、単色・フラットな塗り分けやシンプルな
     線画が中心のファッションイラストである。写真的な陰影勾配に
     乏しいこの種の画像に対して、自然写真で検証されたMiDaSがどこまで
     意味のある深度信号を出せるかは、モデルの想定学習分布から大きく
     外れており、実測できていない以上「動くはずだ」と楽観視すること
     自体がこのプロジェクトの正直な文書化方針(未検証の精度を主張
     しない)に反する。
  2. 仮に何らかの深度マップが得られたとしても、それを「ダーツの
     深さ・ギャザーの分量・プリーツの折り込み幅」といった具体的な
     cm単位のパターン修正量に変換する対応関係は、このプロジェクトには
     存在しない(検証用の正解データも無い)。パーツ分割(SAM)の場合は
     出力(マスク)がそのまま既存パイプラインの「領域→part_type判定」に
     素直に接続できたのに対し、深度マップの場合は「深度→パターン
     修正量」という、ゼロから設計・検証が必要な全く新しい変換ロジックが
     必要になる。この変換を正解データ無しに実装すれば、round6までの
     バストダーツ調査(engine/darts.py参照)で明示的に避けてきた
     「未検証の精度向上を主張する」ことに他ならず、採用しない。

  以上により、SAMは「重みを用意すれば既存パイプラインにそのまま接続できる、
  スコープの明確な機能」として現状維持(未同梱・プラガブル)する一方、
  MiDaSは「そもそも入力データの性質・出力の使い道の両方に、検証されて
  いない大きな前提が必要」という理由で、round7時点でも本実装に含めない
  という判断を維持する。
"""

from __future__ import annotations
import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage

from .custom_panel import MAX_CUSTOM_PANEL_POINTS as _AUTO_TRACE_MAX_POINTS

try:
    import shapely.geometry as _sg
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover - shapely未導入環境向け
    _HAS_SHAPELY = False

BBox = tuple[int, int, int, int]


@dataclass
class SegmentedRegion:
    label: str  # "torso" / "left_sleeve" / "right_sleeve" / "lower_body" など
    bbox: BBox  # ピクセル座標 (x0, y0, x1, y1)
    mask: "np.ndarray | None" = None

    def crop(self, image: Image.Image) -> Image.Image:
        return image.crop(self.bbox)


class Segmenter(ABC):
    @abstractmethod
    def segment(self, image: Image.Image) -> list[SegmentedRegion]:
        """イラストをパーツ候補領域に分割する。"""


class SimpleSilhouetteSegmenter(Segmenter):
    """SAM無し環境向けの軽量フォールバック。

    正確な意味分割ではなく「だいたいこの辺にパーツがある」という当たりを
    つけるための簡易実装であり、精度が必要な場面では SAMSegmenter に置き換える。
    以前は「背景は明るい単色」という前提の明度しきい値だけで判定していたが、
    それだと透明PNGや白以外の背景（濃色・グラデーション等）でほぼ確実に失敗
    していた。以下の2段構えで、対応範囲と失敗検知を改善している:

      1. アルファチャンネルに実質的な透明部分があれば、それをそのまま前景
         マスクとして使う（キャラクターイラストで最も信頼できる情報源）。
      2. アルファが無い/不透明なら、4隅のパッチ色を平均して背景色を推定し、
         そこからの色距離でマスクを作る（白背景前提を撤廃）。

    さらに、前景が「ほぼ無い」「ほぼ全体」のどちらの極端になった場合は
    分割そのものが信頼できないと判断し、空リストを返す
    （呼び出し側のpipelineが「手動選択モードを使ってください」という
    分かりやすいエラーに変換する）。silent に変な領域を返すよりはっきり
    失敗を伝える方が、意味不明な型紙が出てくるより安全という判断。
    """

    #: 前景が画像全体に対してこの比率より少ない/多い場合は判定不能として扱う。
    MIN_FOREGROUND_RATIO = 0.02
    MAX_FOREGROUND_RATIO = 0.95
    #: 背景色推定に使う、4隅のパッチの一辺のピクセル数。
    CORNER_PATCH_SIZE = 12
    #: 背景色からのユークリッド距離(0-255スケール)がこれを超えたら前景とみなす。
    COLOR_DISTANCE_THRESHOLD = 40
    #: 前景マスク計算に使う画像の長辺の上限(px)。実際のスマートフォン写真
    #: (12MP=4000x3000程度)をフル解像度でnumpy処理すると、実測で数秒〜十数秒
    #: かかることが実写相当のテスト画像で確認された（この処理は「だいたい
    #: この辺にパーツがある」という大まかな当たりを付けるためだけのもので、
    #: ピクセル単位の精度は不要）。長辺をこのサイズまで縮小してから前景マスクと
    #: バウンディングボックスを計算し、最後に元画像の座標系へ逆変換することで、
    #: 実際にパーツを切り出す際は元の解像度のまま使いつつ、計算コストだけを
    #: 大幅に下げる。
    MAX_ANALYSIS_DIMENSION = 1600

    def __init__(self, neck_ratio: float = 1 / 8, hip_ratio: float = 4 / 8,
                 sleeve_width_ratio: float = 0.18):
        self.neck_ratio = neck_ratio
        self.hip_ratio = hip_ratio
        self.sleeve_width_ratio = sleeve_width_ratio

    def _analysis_image_and_scale(self, image: Image.Image) -> tuple[Image.Image, float]:
        """マスク計算用に縮小した画像と、元解像度への逆変換に使う倍率を返す。

        scale は「縮小後の座標 × (1/scale) = 元画像の座標」となるように、
        縮小後÷縮小前の比率(1.0以下)として返す。
        """
        w, h = image.size
        longest = max(w, h)
        if longest <= self.MAX_ANALYSIS_DIMENSION or longest == 0:
            return image, 1.0
        scale = self.MAX_ANALYSIS_DIMENSION / longest
        new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
        resized = image.resize(new_size, Image.Resampling.LANCZOS)
        return resized, scale

    def _foreground_mask(self, image: Image.Image) -> "np.ndarray | None":
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = np.array(image.convert("RGBA"))
            alpha = rgba[:, :, 3]
            if alpha.min() < 250:  # 実質的な透明部分がある場合のみアルファを信用する
                return alpha > 127

        rgb = np.array(image.convert("RGB")).astype(np.int16)
        h, w, _ = rgb.shape
        p = min(self.CORNER_PATCH_SIZE, h // 2 or 1, w // 2 or 1)
        corners = np.concatenate([
            rgb[:p, :p].reshape(-1, 3), rgb[:p, -p:].reshape(-1, 3),
            rgb[-p:, :p].reshape(-1, 3), rgb[-p:, -p:].reshape(-1, 3),
        ])
        background_color = corners.mean(axis=0)
        distance = np.linalg.norm(rgb - background_color, axis=2)
        return distance > self.COLOR_DISTANCE_THRESHOLD

    def _largest_component_mask(self, mask: "np.ndarray") -> "np.ndarray":
        """前景マスクから、最大の連結領域だけを残したマスクを返す。

        実写画像でのテストで見つかった不具合の修正: ブランドタグ・ロゴ
        シールの写り込みや、1枚の写真に複数の衣類が離れて置かれている
        「コーディネート写真」では、前景マスクが複数の分離した領域に分かれる。
        以前は単純にマスク全体のバウンディングボックス(全前景ピクセルの
        最小/最大座標)を取っていたため、本体の衣類とは無関係な小さな
        写り込みだけでネックライン等の位置が大きくずれてしまっていた
        （実測で、隅の小さなタグ1つだけでネックライン相当の境界が4割近く
        移動するケースを確認）。8近傍で連結成分をラベル付けし、最大の
        ピクセル数を持つ成分（＝本体の衣類とみなす）だけを残すことで、
        無関係な写り込みの影響を除去する。
        """
        if not mask.any():
            return mask
        structure = np.ones((3, 3), dtype=bool)  # 8近傍（斜め接触も連結とみなす）
        labeled, num_features = ndimage.label(mask, structure=structure)
        if num_features <= 1:
            return mask
        counts = np.bincount(labeled.ravel())
        counts[0] = 0  # ラベル0は背景なので候補から除外
        largest_label = int(counts.argmax())
        return labeled == largest_label

    def segment(self, image: Image.Image) -> list[SegmentedRegion]:
        analysis_image, scale = self._analysis_image_and_scale(image)
        mask = self._foreground_mask(analysis_image)
        if mask is None:
            return []
        mask = self._largest_component_mask(mask)

        total = mask.size
        foreground_ratio = float(mask.sum()) / total if total else 0.0
        if not (self.MIN_FOREGROUND_RATIO <= foreground_ratio <= self.MAX_FOREGROUND_RATIO):
            # 前景が少なすぎる(何も検出できていない)か多すぎる(背景推定が失敗し
            # 画像全体を前景と誤認している)ため、この結果は信頼できない。
            return []

        ys, xs = np.where(mask)
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())

        if scale != 1.0:
            # マスクは縮小画像上で計算したので、切り出しに使う元画像の座標系に
            # 逆変換する（切り出し(crop)自体は元の解像度のまま行い、精度を
            # 落とさない）。
            inv = 1.0 / scale
            orig_w, orig_h = image.size
            x0, y0 = int(x0 * inv), int(y0 * inv)
            x1 = min(orig_w, int((x1 + 1) * inv))
            y1 = min(orig_h, int((y1 + 1) * inv))
            x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)

        fig_h = max(1, y1 - y0)
        fig_w = max(1, x1 - x0)

        neck_y = y0 + int(fig_h * self.neck_ratio)
        hip_y = y0 + int(fig_h * self.hip_ratio)
        sleeve_w = max(1, int(fig_w * self.sleeve_width_ratio))

        return [
            SegmentedRegion("torso", (x0, neck_y, x1, hip_y)),
            SegmentedRegion("left_sleeve", (x0, neck_y, x0 + sleeve_w, hip_y)),
            SegmentedRegion("right_sleeve", (x1 - sleeve_w, neck_y, x1, hip_y)),
            SegmentedRegion("lower_body", (x0, hip_y, x1, y1)),
        ]

    #: `auto_trace_outline`が単純化(simplify)に使う許容誤差の、輪郭の
    #: 対角線長に対する比率。大きいほど頂点数は減るが形状の再現度は落ちる。
    SIMPLIFY_TOLERANCE_RATIO = 0.004
    #: 単純化後もなお頂点数が多すぎる場合、許容誤差を大きくしながら
    #: 再試行する最大回数(無限ループ防止)。
    _SIMPLIFY_MAX_RETRIES = 6

    def auto_trace_outline(self, image: Image.Image) -> list[tuple[float, float]] | None:
        """画像から前景シルエットの輪郭を自動抽出する(round9で追加)。

        カスタムパーツ機能(`engine/custom_panel.py`)の「画像から自動抽出」
        モードが使う。`segment()`と同じ前景マスク計算
        (`_foreground_mask`/`_largest_component_mask`/解析用縮小)を再利用し、
        `trace_boundary_pixels`(Moore-neighbor tracing)で輪郭ピクセル列を
        求めた後、shapelyの`simplify`で頂点数を実用的な範囲まで減らし、
        最後に元画像の解像度の座標系へ逆変換して返す。

        `segment()`と同じ理由で、前景が検出できない/検出結果が信頼できない
        （占有率が極端に小さい/大きい）場合はNoneを返す
        （呼び出し側は「手動トレースをお試しください」という案内に倒す）。
        """
        analysis_image, scale = self._analysis_image_and_scale(image)
        mask = self._foreground_mask(analysis_image)
        if mask is None:
            return None
        mask = self._largest_component_mask(mask)

        total = mask.size
        foreground_ratio = float(mask.sum()) / total if total else 0.0
        if not (self.MIN_FOREGROUND_RATIO <= foreground_ratio <= self.MAX_FOREGROUND_RATIO):
            return None

        boundary = trace_boundary_pixels(mask)
        if boundary is None:
            return None

        simplified = _simplify_polygon_points(
            boundary,
            tolerance_ratio=self.SIMPLIFY_TOLERANCE_RATIO,
            max_points=_AUTO_TRACE_MAX_POINTS,
            max_retries=self._SIMPLIFY_MAX_RETRIES,
        )
        if simplified is None or len(simplified) < 3:
            return None

        inv = 1.0 / scale if scale else 1.0
        return [(x * inv, y * inv) for x, y in simplified]


#: Moore近傍を「西(W)」から時計回りに8方向並べたもの。(dy, dx)のオフセット。
#: round9で追加(`trace_boundary_pixels`参照)。
_MOORE_NEIGHBORS_CLOCKWISE_FROM_WEST: tuple[tuple[int, int], ...] = (
    (0, -1),   # W
    (-1, -1),  # NW
    (-1, 0),   # N
    (-1, 1),   # NE
    (0, 1),    # E
    (1, 1),    # SE
    (1, 0),    # S
    (1, -1),   # SW
)


def _mask_at(mask: "np.ndarray", y: int, x: int) -> bool:
    """マスク範囲外は背景(False)として扱う安全なアクセサ。"""
    h, w = mask.shape
    if 0 <= y < h and 0 <= x < w:
        return bool(mask[y, x])
    return False


def trace_boundary_pixels(mask: "np.ndarray") -> list[tuple[int, int]] | None:
    """2値マスクから、単一の連結成分の輪郭を(x, y)ピクセル座標の列として抽出する。

    round9で追加。「Moore-neighbor tracing」と呼ばれる古典的な輪郭追跡
    アルゴリズム(Jacobの停止条件付き)の実装。SAM/深層学習ベースの
    セグメンテーションとは異なり、外部ライブラリを増やさずnumpyだけで
    実装できる(このプロジェクトが一貫して「重い依存を増やさない」方針を
    取ってきたことに合わせた)。

    前提: `mask`は既に`_largest_component_mask`等で単一の連結成分に
    絞り込まれた、塗りつぶされた(中実な)前景マスクであること。細い線画の
    骨格(1ピクセル幅の線)のような形状は対象外(このアルゴリズムの一般的な
    既知の限界であり、本プロジェクト独自の制約ではない)。

    戻り値は輪郭に沿ったピクセル座標(x, y)の列(始点と終点は重複させない、
    呼び出し側でZ(閉じる)相当として扱う前提)。前景が無い/1ピクセルしかない
    等、多角形として意味を持たない場合はNoneを返す。

    アルゴリズム概要:
      1. 走査順(上から下、各行は左から右)で最初に見つかった前景ピクセルを
         開始点とする。走査順の性質上、その直前に見たはずの「西(左隣)」の
         ピクセルは常に背景であることが保証される(そうでなければ、その
         西のピクセルの方が先に見つかっているはず)ため、追跡の初期
         backtrack(直前に見た背景ピクセル)として使える。
      2. 現在のピクセルについて、backtrackの位置から時計回りにMoore近傍
         (8方向)を1つずつ調べ、最初に見つかった前景ピクセルを次の現在
         ピクセルとする。backtrackは「その直前に調べた背景ピクセル」に
         更新する。
      3. 開始点に「同じbacktrackの状態で」戻ってきたら終了する
         (Jacobの停止条件。単に座標が開始点と一致しただけで止めると、
         括れの強い形状で1周する前に誤って停止することがあるため)。
      4. 想定外の無限ループを避けるため、輪郭長の上限(マスクの全ピクセル数
         の4倍)に達したら安全側に打ち切る(実際の中実マスクでは理論上
         到達しないはずだが、防御的に上限を設けている)。
    """
    h, w = mask.shape
    start = None
    for y in range(h):
        row_xs = mask[y].nonzero()[0]
        if row_xs.size:
            start = (y, int(row_xs[0]))
            break
    if start is None:
        return None

    start_y, start_x = start
    # 走査順の性質上、西隣は常に背景("西"が無い(x=0)場合も範囲外=背景扱い)。
    initial_backtrack = (start_y, start_x - 1)

    boundary: list[tuple[int, int]] = [start]
    current = start
    backtrack = initial_backtrack
    max_steps = max(1, h * w * 4)

    for _ in range(max_steps):
        dy0, dx0 = backtrack[0] - current[0], backtrack[1] - current[1]
        try:
            start_idx = _MOORE_NEIGHBORS_CLOCKWISE_FROM_WEST.index((dy0, dx0))
        except ValueError:
            # backtrackが8近傍に該当しない(理論上到達しないはずの状態)。
            # 安全側に打ち切る。
            break

        found = None
        prev = backtrack
        for offset in range(1, 9):
            dy, dx = _MOORE_NEIGHBORS_CLOCKWISE_FROM_WEST[(start_idx + offset) % 8]
            candidate = (current[0] + dy, current[1] + dx)
            if _mask_at(mask, *candidate):
                found = candidate
                break
            prev = candidate

        if found is None:
            # current自身が孤立ピクセル(前景の隣接ピクセルが無い)。
            break

        current = found
        backtrack = prev
        boundary.append(current)

        if current == start and backtrack == initial_backtrack:
            break

    if len(boundary) < 3:
        return None
    # (y, x) -> (x, y) の画像座標に変換して返す。
    return [(x, y) for y, x in boundary]


def _simplify_polygon_points(points: list[tuple[int, int]], tolerance_ratio: float,
                              max_points: int, max_retries: int) -> list[tuple[float, float]] | None:
    """輪郭追跡が返す「階段状」のピクセル境界を、shapelyの`simplify`で
    実用的な頂点数まで間引く(round9で追加)。

    Moore-neighbor tracingは輪郭に沿った全ピクセルを1つずつ辿るため、
    ちょっとした形状でも数百〜数千頂点になり、そのままではブラウザでの
    手動調整や型紙としての扱いに適さない。許容誤差(tolerance、輪郭の
    対角線長に対する比率)を`max_points`以下に収まるまで倍々に増やしながら
    再試行する。shapelyが無い環境では簡易フォールバックとして間引きのみ行う。
    """
    if len(points) < 3:
        return None
    if not _HAS_SHAPELY:
        if len(points) <= max_points:
            return [(float(x), float(y)) for x, y in points]
        step = max(1, len(points) // max_points)
        return [(float(x), float(y)) for x, y in points[::step]]

    try:
        poly = _sg.Polygon(points)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.geom_type != "Polygon":
            return None
    except Exception:
        return None

    minx, miny, maxx, maxy = poly.bounds
    diagonal = math.hypot(maxx - minx, maxy - miny)
    tolerance = max(0.5, diagonal * tolerance_ratio)

    coords: list[tuple[float, float]] = []
    for _ in range(max_retries):
        simplified = poly.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty or simplified.geom_type != "Polygon":
            return None
        coords = list(simplified.exterior.coords)[:-1]
        if len(coords) <= max_points:
            return coords
        tolerance *= 2

    if len(coords) > max_points:
        step = max(1, len(coords) // max_points)
        coords = coords[::step]
    return coords if len(coords) >= 3 else None


class SAMSegmenter(Segmenter):
    """本物のSegment Anything Modelを使う実装。

    `pip install segment-anything` とチェックポイント(.pth)が必要。
    利用可能な場合、get_default_segmenter() が自動的にこちらへ切り替える。
    """

    def __init__(self, checkpoint_path: str, model_type: str = "vit_b"):
        try:
            from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
        except ImportError as exc:  # pragma: no cover - 重い依存は通常環境に無い
            raise RuntimeError(
                "segment_anything パッケージが見つかりません。"
                " `pip install segment-anything` を実行し、SAMの重み(.pth)を"
                " SAM_CHECKPOINT_PATH に設定してください。"
            ) from exc
        sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
        self._generator = SamAutomaticMaskGenerator(sam)

    def segment(self, image: Image.Image) -> list[SegmentedRegion]:  # pragma: no cover
        arr = np.array(image.convert("RGB"))
        masks = self._generator.generate(arr)
        regions = []
        for m in masks:
            x, y, w, h = m["bbox"]
            regions.append(SegmentedRegion(
                label="unknown", bbox=(int(x), int(y), int(x + w), int(y + h)),
                mask=m.get("segmentation"),
            ))
        return regions


def get_default_segmenter() -> Segmenter:
    """SAMの重みが用意されていれば SAMSegmenter、無ければ簡易実装を返す。"""
    checkpoint = os.environ.get("SAM_CHECKPOINT_PATH")
    if checkpoint and os.path.exists(checkpoint):
        try:
            return SAMSegmenter(checkpoint)
        except RuntimeError:
            pass
    return SimpleSilhouetteSegmenter()
