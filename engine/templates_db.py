"""
templates_db.py — テンプレートSVGを読み込む「型紙データベース」。

templates/ フォルダの .svg を読み、part_type + variation をキーに引ける。
③テンプレート取得ステップがここを使う。

本物のSVG型紙（人間が用意した標準Mサイズ）を保持し、
エンジンはそれを④で変形する。これが「テンプレート＋変形」方式の実体。
"""

from __future__ import annotations
import os
import re
from .bodice_fit import parse_fit_anchors
from .svgpath import parse_path

# プロジェクトルート/pattern_templates を既定の格納先にする。
_DEFAULT_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pattern_templates"
)

# 標準で用意するテンプレート型紙カタログ(round9でネックライン前開き対応
# 拡大・新バリエーション6種を追加。以前は47種)。
# TemplateDB.missing() で「まだSVGが用意されていない組み合わせ」を検出できる。
REQUIRED_PARTS: list[tuple[str, str]] = [
    ("front_bodice", "round_neck"),
    ("front_bodice", "v_neck"),
    ("front_bodice", "turtle_neck"),
    ("front_bodice", "square_neck"),
    ("front_bodice", "boat_neck"),
    ("front_bodice", "sweetheart"),
    ("front_bodice_zip_panel", "round_neck"),
    ("front_bodice_zip_panel", "v_neck"),
    # round9で前開き対応ネックラインをround_neck/v_neckの2種から
    # turtle_neckを除く5種へ拡大した(engine/pipeline.py
    # ZIP_COMPATIBLE_NECKLINESのコメント参照)。
    ("front_bodice_zip_panel", "square_neck"),
    ("front_bodice_zip_panel", "boat_neck"),
    ("front_bodice_zip_panel", "sweetheart"),
    ("back_bodice", "round_neck"),
    ("back_bodice", "v_neck"),
    ("back_bodice", "turtle_neck"),
    ("back_bodice", "square_neck"),
    ("back_bodice", "boat_neck"),
    ("back_bodice", "sweetheart"),
    ("back_bodice", "round_neck_zip"),
    ("back_bodice", "v_neck_zip"),
    ("back_bodice", "square_neck_zip"),
    ("back_bodice", "boat_neck_zip"),
    ("back_bodice", "sweetheart_zip"),
    ("sleeve", "straight"),
    ("sleeve", "curve"),
    ("sleeve", "puff"),
    ("sleeve", "bell"),
    ("sleeve", "cap"),
    ("sleeve", "three_quarter"),
    ("skirt", "flare"),
    ("skirt", "tight"),
    ("skirt", "pleated"),
    ("skirt", "wrap"),
    ("skirt", "mermaid"),
    ("skirt", "circle"),
    ("front_pants", ""),
    ("front_pants", "wide"),
    ("front_pants", "tapered"),
    ("front_pants", "shorts"),
    ("front_pants", "flare"),
    ("front_pants", "cropped"),
    ("back_pants", ""),
    ("back_pants", "wide"),
    ("back_pants", "tapered"),
    ("back_pants", "shorts"),
    ("back_pants", "flare"),
    ("back_pants", "cropped"),
    ("collar", ""),
    ("collar", "shirt_collar"),
    ("collar", "peter_pan_collar"),
    ("collar", "bow_collar"),
    ("collar", "ruffle_collar"),
    ("collar", "convertible_collar"),
    ("cuffs", ""),
    ("cuffs", "wide"),
    ("cuffs", "ruffle"),
    ("cuffs", "button_tab"),
    ("waistband", ""),
    ("waistband", "wide"),
    ("waistband", "elastic"),
    ("waistband", "contour"),
]


class TemplateDB:
    def __init__(self, template_dir: str = _DEFAULT_TEMPLATE_DIR):
        self.template_dir = template_dir
        self._cache: dict[tuple[str, str], list] = {}
        # round14で追加: 体型合わせの基準点(data-fit-x属性)。
        # 詳細は engine/bodice_fit.py と scripts/generate_templates.py の
        # `_bodice_anchors` を参照。
        self._fit_anchors: dict[tuple[str, str], list[tuple[str, float]]] = {}
        # round15で追加: 帯状パーツ(衿・カフス・ウエストバンド)の
        # 「相手に縫い付けられる辺」("top"/"bottom")。
        # engine/compatibility.pyのseam_edge_length参照。
        self._seam_edges: dict[tuple[str, str], str] = {}
        self._load_all()

    def _load_all(self) -> None:
        """templates/ 内の全SVGを読み、data-part / data-variation で索引する。"""
        if not os.path.isdir(self.template_dir):
            return
        for fname in os.listdir(self.template_dir):
            if not fname.endswith(".svg"):
                continue
            path = os.path.join(self.template_dir, fname)
            with open(path, encoding="utf-8") as f:
                svg = f.read()
            part = self._attr(svg, "data-part")
            variation = self._attr(svg, "data-variation")
            d = self._attr(svg, "d")
            if part and d:
                key = (part, variation or "")
                self._cache[key] = parse_path(d)
                self._fit_anchors[key] = parse_fit_anchors(self._attr(svg, "data-fit-x"))
                self._seam_edges[key] = self._attr(svg, "data-seam-edge") or ""

    @staticmethod
    def _attr(svg: str, name: str) -> str | None:
        # 注意: 以前は rf'{name}\s*=\s*"([^"]*)"' という無anchor正規表現で、
        # 属性名の「前」に境界を要求していなかった。そのため name="d" で
        # 検索すると、"id=\"...\"" のような、たまたま name が別の属性名の
        # 末尾と一致してしまう箇所（"i" + "d=" の "d="部分）に誤ってマッチ
        # し、id属性の値をd属性(パスデータ)の値として返してしまうバグが
        # あった（re.search は最初の1件しか返さず、属性名の境界を見ないため）。
        # 実在のテンプレートSVG(pattern_templates/*.svg)はどれも<path>要素に
        # id属性を持たないため今のところ到達しないが、将来だれかが
        # id="..." をdより前に追加すれば、パスデータが静かに壊れた文字列に
        # 置き換わり、parse_path()内でIndexErrorが飛んでTemplateDB全体の
        # 読み込み（＝アプリ起動時のPatternPipeline初期化）が丸ごと落ちる。
        # (?<![\w-]) で「name の直前が英数字・アンダースコア・ハイフンでは
        # ない」ことを要求し、"id=" の "d=" 部分を弾く。
        m = re.search(rf'(?<![\w-]){re.escape(name)}\s*=\s*"([^"]*)"', svg)
        return m.group(1) if m else None

    def get(self, part_type: str, variation: str = ""):
        """パーツ種＋バリエーションでテンプレートのセグメントを取得。

        完全一致(part_type, variation)が無い場合は None を返す。以前は
        variationを無視してpart_typeだけで最初に見つかった候補を返す
        フォールバックがあったが、これは`os.listdir`の走査順（OS/ファイル
        システム依存で不定）に左右される「たまたま一致した無関係の
        テンプレート」を静かに返してしまう罠だったため廃止した。
        バリエーションを問わず何か1件取れればよい呼び出し側は、
        明示的に variation="" を渡すこと（その場合は元々(part_type, "")
        が完全一致キーとして存在する想定）。
        """
        return self._cache.get((part_type, variation))

    def get_fit_anchors(self, part_type: str, variation: str = "") -> list[tuple[str, float]]:
        """体型合わせの基準点を返す(round14)。持たないテンプレートでは空リスト。

        身頃だけが持っている。`engine/scaling.py`が、これがある場合に
        「区間ごとに違う倍率」で変形する(=入力された肩幅を実際に使う)。
        """
        return self._fit_anchors.get((part_type, variation), [])

    def get_seam_edge(self, part_type: str, variation: str = "") -> str:
        """帯状パーツの「縫い付けられる辺」を返す(round15)。宣言が無ければ""。

        衿・カフス・ウエストバンドは、外接矩形の幅と実際に縫い付けられる辺の
        長さが一致しない(襟先やボタンタブが左右へ張り出す、辺そのものが曲線
        である等)。どちらの辺が縫い付け側かはテンプレートの形状で決まるため、
        テンプレート自身に宣言させている(engine側に対応表を置くと、
        テンプレートを描き変えたときに片方だけ古くなる)。
        """
        return self._seam_edges.get((part_type, variation), "")

    def available(self) -> list[tuple[str, str]]:
        return list(self._cache.keys())

    def missing(self) -> list[tuple[str, str]]:
        """REQUIRED_PARTS のうち、まだテンプレートSVGが用意されていない組み合わせ。"""
        return [p for p in REQUIRED_PARTS if p not in self._cache]
