"""dxf_export.py — 型紙のDXF出力（CAD・自動裁断機との連携用、round5で追加）。

SVG(画面プレビュー)・PDF(家庭用プリンタでのA4分割印刷)に続く3つ目の出力
形式。業務用の自動裁断機(カッティングプロッタ)やCADソフト(Illustrator・
各種CAM)にそのまま読み込めるよう、A4分割は行わず実寸1:1の単一図面として
出力する(DXFを読み込む側の機材・ソフトウェアは元々実寸で扱える前提)。

出力レイヤー構成:
  CUT_LINE   : 裁断線(cut_line)。実際に機械が切る/人が鋏を入れる線。
  STITCH_LINE: 縫い線(stitch_line)。裁断線の内側にある、縫う位置の参考線。
  NOTCH      : 合印。
  GRAINLINE  : 布目線(矢印は簡略化した2本の短い線分で表現。SVG/PDF同様)。
  LABEL      : パーツ名(display_name)のテキスト。
  WARNING    : 配置できなかったパーツがある場合の警告テキスト。

依存ライブラリとして`ezdxf`を使う。DXF自体はASCIIベースのテキスト形式
だが、HEADER/TABLES/BLOCKS等のセクション構成が複雑で、自前実装は
「一見開けるが実は壊れているファイル」を生むリスクが高いと判断し、
shapely/reportlab/svgwriteと同じ方針で専用ライブラリに頼っている。

座標系について: このアプリの内部座標(cut_line等)はSVGと同じ「左上原点・
Y軸下向き」だが、DXF/CADの慣習は「Y軸上向き」のため、単純にY座標を
生地の総丈(used_length_cm)から引く形で上下反転して出力する(X軸はそのまま)。
反転しないと、実際にDXFをCADソフトで開いたときに型紙が上下逆さまに
表示され、パーツ名ラベルの向きも含めて直感に反する。

正直な制約:
  - A4分割(タイル分割)は行わない。上記の通りDXFを読み込む側は実寸で
    扱える前提のため、PDF側にあるようなタイル分割・貼り合わせガイドは
    そもそも不要という判断。
  - 縫い線(STITCH_LINE)には破線(DASHED)の線種を指定しているが、実際に
    破線として表示されるかはDXFを開くソフト側の線種スケール設定に依存する
    (CADソフトによっては初期状態で実線に見えることがある)。
  - パーツ名ラベル(日本語を含む)はDXFのTEXTエンティティとして埋め込んで
    いる。ezdxf自体はUTF-8のまま正しく書き出す(実際に読み戻して文字列が
    一致することを確認済み)が、読み込み側のCADソフトが使うフォント
    (SHXフォント等)が日本語グリフを持たない環境では文字化けする可能性が
    ある。PDF側(engine/pdf_export.py)のように専用の埋め込みフォントで
    グリフそのものを保証する仕組みはDXFのTEXTエンティティには無い。
  - 配置できなかったパーツ(unplaced)がある場合、SVG/PDFと同様に警告
    テキストを描画するが、これはあくまで開いた人が気づくための表示。
    見落として裁断すると衣服が完成しない実害があるため、利用側は
    `PipelineResult.summary()`の`unplaced_warnings`も必ず併せて確認すべき
    (DXF単体の閲覧では見落とされる可能性があるという正直な限界)。
"""

from __future__ import annotations

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .nesting import NestingResult

Point = tuple[float, float]

_LAYER_COLORS: dict[str, int] = {
    "CUT_LINE": 7,     # 白/黒相当(最も重要な、実際に切る線)
    "STITCH_LINE": 3,  # 緑
    "NOTCH": 1,        # 赤
    "GRAINLINE": 5,    # 青
    "LABEL": 8,        # グレー
    "WARNING": 1,      # 赤
}

# ezdxf.new()の既定状態にはDASHED線種が登録されていない(CONTINUOUSのみ)。
# ezdxf.tools.standards.linetypes()が提供する標準パターンの値をそのまま使う。
_DASHED_PATTERN = [0.6, 0.5, -0.1]


def _drop_closing_duplicate(points: list[Point]) -> list[Point]:
    """閉じた輪郭(先頭==末尾)の末尾重複点を取り除く。

    ezdxfの`add_lwpolyline(..., close=True)`は自動的に始点と終点を結ぶため、
    このアプリのcut_line/stitch_line形式(末尾に始点と同じ座標を持つ)の
    ままだと、長さゼロの余計な最終セグメントができてしまう。
    """
    if points and points[0] == points[-1] and len(points) > 1:
        return points[:-1]
    return list(points)


def render_dxf(result: NestingResult, output_path: str) -> str:
    """ネスティング結果を、実寸1:1のDXFファイル(R2010形式)に書き出す。"""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # 5 = センチメートル(ezdxf.units.CM相当のヘッダ値)
    doc.linetypes.add("DASHED", pattern=_DASHED_PATTERN, description="Dashed")
    for name, color in _LAYER_COLORS.items():
        doc.layers.add(name=name, color=color)
    msp = doc.modelspace()

    total_height_cm = max(result.used_length_cm, 1.0)

    def _flip(points: list[Point]) -> list[Point]:
        return [(x, total_height_cm - y) for x, y in points]

    for placed in result.placed:
        cut = _drop_closing_duplicate(_flip(placed.placed_cut_line()))
        msp.add_lwpolyline(cut, format="xy", close=True, dxfattribs={"layer": "CUT_LINE"})

        stitch = _drop_closing_duplicate(_flip(placed.placed_stitch_line()))
        msp.add_lwpolyline(stitch, format="xy", close=True,
                            dxfattribs={"layer": "STITCH_LINE", "linetype": "DASHED"})

        for a, b in placed.placed_notches():
            (ax, ay), (bx, by) = _flip([a, b])
            msp.add_line((ax, ay), (bx, by), dxfattribs={"layer": "NOTCH"})

        grain = placed.placed_grainline()
        (gx1, gy1), (gx2, gy2) = _flip(list(grain["line"]))
        msp.add_line((gx1, gy1), (gx2, gy2), dxfattribs={"layer": "GRAINLINE"})
        for a, b in grain["arrows"]:
            (ax, ay), (bx, by) = _flip([a, b])
            msp.add_line((ax, ay), (bx, by), dxfattribs={"layer": "GRAINLINE"})

        min_x, min_y, max_x, max_y = placed.bbox()
        (cx, cy) = _flip([((min_x + max_x) / 2, (min_y + max_y) / 2)])[0]
        label = placed.part.display_name
        if placed.rotated:
            # render_layout_svg/render_a4_pdfと同じ注記文言に揃える。
            label += "(90度回転・布目確認)"
        text = msp.add_text(label, dxfattribs={"layer": "LABEL", "height": 0.9})
        text.set_placement((cx, cy), align=TextEntityAlignment.MIDDLE_CENTER)

    if result.unplaced:
        names = "・".join(p.display_name for p in result.unplaced)
        warn_text = msp.add_text(
            f"警告: 型紙に含まれていないパーツ: {names}",
            dxfattribs={"layer": "WARNING", "height": 1.2},
        )
        warn_text.set_placement((0.3, total_height_cm + 1.5), align=TextEntityAlignment.BOTTOM_LEFT)

    doc.saveas(output_path)
    return output_path
