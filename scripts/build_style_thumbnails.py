"""build_style_thumbnails.py — 形を選ぶためのサムネイルSVGを作る。round34で追加。

【なぜ要るか】round33まで、ネックライン・袖・スカートの形は**文字の
プルダウンだけ**で選んでいた。「スウィートハートネック」「ベル」
「マーメイド」——名前を知っている人にしか選べない。作るのは衣装で、
選んでいるのは形なのだから、形を見て選べる方がよい。

【どう作るか】絵を描き起こすのではなく、**実際のテンプレート型紙の輪郭を
そのまま縮小して**サムネイルにする。描き起こした絵は、テンプレートを
直したときに黙って古くなる(絵と型紙が食い違っていても誰も気づかない)。
輪郭そのものを使えば、その食い違いが原理的に起こらない。

ネックラインは、身頃の上のほうだけを切り出す(全体を出すと、6種類とも
ほぼ同じ長方形に見えて区別が付かない。違うのは首まわりだけ)。
袖・スカートはパーツ全体を出す(形の違いが全体に出るため)。

使い方:
    python3 scripts/build_style_thumbnails.py

出力: web/static/thumbs/{種類}__{バリエーション}.svg
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.svgpath import bounding_box, segments_to_polyline  # noqa: E402
from engine.templates_db import TemplateDB  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "web" / "static" / "thumbs"

#: サムネイルの見た目(型紙のプレビューと同じ色づかいにして、同じものだと
#: 分かるようにする)。
_FILL = "#f3efe6"
_STROKE = "#8a8171"
_STROKE_WIDTH = 0.9

#: 身頃は上から何割を切り出すか。首ぐりの違いが見える範囲。
#: 0.45だと胸の下まで入って首の違いが小さく見え、0.30だと肩先が切れる。
BODICE_TOP_FRACTION = 0.38

#: 輪郭を折れ線にするときの分割数。曲線(首ぐり・袖山)がカクつかない程度。
_CURVE_STEPS = 48

#: どのパーツ種の、どのバリエーションを出すか。
#: 前開き用(*_zip)は、選ぶのはチェックボックスであって形の選択肢では
#: ないので出さない。
TARGETS: dict[str, str] = {
    "neckline": "front_bodice",
    "sleeve": "sleeve",
    "skirt": "skirt",
    "collar": "collar",
    "pants": "front_pants",
}


def _thumbnail_svg(segments, crop_top_fraction: float | None = None) -> str:
    """パーツの輪郭から、1枚のサムネイルSVGの文字列を作る。"""
    points = segments_to_polyline(segments, curve_steps=_CURVE_STEPS)
    if len(points) < 3:
        raise ValueError("輪郭の点が足りません")
    min_x, min_y, max_x, max_y = bounding_box(segments)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        raise ValueError("輪郭の大きさが0です")

    if crop_top_fraction is not None:
        # 上から一定割合だけを見せる。輪郭自体は切らず、viewBoxで切り取る
        # (切ると開いた線になり、塗りがおかしくなる)。
        height = height * crop_top_fraction

    pad = max(width, height) * 0.06
    view = (f"{min_x - pad:.2f} {min_y - pad:.2f} "
            f"{width + pad * 2:.2f} {height + pad * 2:.2f}")
    d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" '
        f'preserveAspectRatio="xMidYMin meet" aria-hidden="true">'
        f'<path d="{d}" fill="{_FILL}" stroke="{_STROKE}" '
        f'stroke-width="{_STROKE_WIDTH}" stroke-linejoin="round"/>'
        f'</svg>\n'
    )


def main() -> None:
    db = TemplateDB()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped: list[str] = []
    for kind, part_type in TARGETS.items():
        crop = BODICE_TOP_FRACTION if kind == "neckline" else None
        for available_type, variation in db.available():
            if available_type != part_type or variation.endswith("_zip"):
                continue
            segments = db.get(part_type, variation)
            if segments is None:
                continue
            try:
                svg = _thumbnail_svg(segments, crop)
            except ValueError as exc:
                skipped.append(f"{kind}/{variation}: {exc}")
                continue
            name = variation or "standard"
            (OUTPUT_DIR / f"{kind}__{name}.svg").write_text(svg, encoding="utf-8")
            written += 1
    print(f"書き出し完了: {written}枚 -> {OUTPUT_DIR}")
    for line in skipped:
        print("  スキップ:", line)


if __name__ == "__main__":
    main()
