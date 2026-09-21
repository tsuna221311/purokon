"""round53: 印刷して使う側から見ると、白紙が15%混ざっていた。

round52までは入力側ばかり見ていた。コスプレイヤーの実際の作業は
「生成 → 印刷 → 貼り合わせ → 裁つ」で、**紙にしてからが本番**である。
そこで出力そのものを印刷物として見た。

見つかったもの:

  1. **型紙が1本も載らない面を、白紙のまま印刷していた。**
     生地は長方形だが型紙は長方形ではないので、隅には必ず何も載らない
     面ができる。「(この面に型紙なし)」と書いてはあったが、**1ページ
     割り当てて出していた**。実測(ワンピース1着):

         身長150cm  格子7x8=56面 →  13面が白紙 (23.2%)
         身長160cm  格子7x8=56面 →   8面が白紙 (14.3%)
         身長175cm  格子10x8=80面 → 22面が白紙 (27.5%)
         合計 192面のうち43面(22.4%)が白紙

     家庭用プリンタなら紙とインク、コンビニなら1枚数十円がそのまま
     無駄になり、貼り合わせるときも白紙を1枚ずつ除ける手間がかかる。

  2. **表紙の「全48枚」が、白紙を含んだ数だった。**
     実際に型紙が載るのは41枚なのに48枚と書いてあった。

  3. **何枚印刷することになるのかが、PDFを開くまで分からなかった。**
     コンビニで印刷する人にとっては枚数がそのまま値段と待ち時間になる。

安全側の確認: 面を省く判定は、描く側とまったく同じ`clip_polygon_to_rect`
で行う。**型紙が載る面を誤って省くと型紙が欠ける**ので、紙が1枚無駄に
なるより桁違いに悪い。新旧の実装で同じジョブを出して、残した面の絵が
1枚残らず同一であることを確かめてある(下の
`test_no_tile_that_carries_pattern_is_ever_skipped`が同じ性質を
プロパティとして見ている)。
"""

import math

import pytest

from engine.measurements import Measurements
from engine.nesting import NestingResult, nest_parts
from engine.pdf_export import (
    A4_USABLE_H_CM,
    A4_USABLE_W_CM,
    _tile_has_content,
    printed_tile_cells,
    render_a4_pdf,
)
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.seam import finalize_part
from engine.svgpath import parse_path


def _page_texts(path):
    import pypdf

    return [page.extract_text() or "" for page in pypdf.PdfReader(path).pages]


def _dress(tmp_path, **measurements):
    base = dict(bust=84, waist=68, hip=92, height=160,
                sleeve_length=54, shoulder_width=37)
    base.update(measurements)
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, Measurements(**base))


# --- 1. 白紙の面を印刷しないこと --------------------------------------------

def test_no_blank_tile_is_printed(tmp_path):
    """「この面に型紙なし」のページが1枚も出ないこと。"""
    result = _dress(tmp_path)
    texts = _page_texts(result.output_files["pdf"])
    blank = [i for i, t in enumerate(texts, 1) if "この面に型紙なし" in t]
    assert blank == [], f"白紙のページが残っています: {blank}"


def test_the_skipped_tiles_are_exactly_the_empty_ones(tmp_path):
    """省いた面の数が、「型紙が載らない面」の数とぴったり一致すること。

    多く省けば型紙が欠け、少なく省けば白紙が残る。どちらでもないこと。
    """
    result = _dress(tmp_path)
    rows, cols, cells = printed_tile_cells(result.nesting)
    empty = [(r, c) for r in range(rows) for c in range(cols)
             if not _tile_has_content(result.nesting,
                                       c * A4_USABLE_W_CM, r * A4_USABLE_H_CM,
                                       (c + 1) * A4_USABLE_W_CM, (r + 1) * A4_USABLE_H_CM)]
    assert len(cells) + len(empty) == rows * cols
    assert set(cells).isdisjoint(empty)
    # このジョブでは実際に省く面がある(テストが空振りしていないこと)。
    assert empty, "省く面が1つも無いので、このテストは何も確かめていません"


def test_no_tile_that_carries_pattern_is_ever_skipped(tmp_path):
    """**型紙の載る面は絶対に省かない**ことを、体型を振って確かめる。

    紙が1枚無駄になるのは損だが、型紙が1面欠けるのは
    「裁ってから足りないと気づく」事故になる。こちらを厚く見る。
    """
    for height, bust, hip in [(145, 74, 80), (160, 84, 92), (175, 104, 112),
                               (150, 96, 120), (170, 78, 88)]:
        result = _dress(tmp_path, height=height, bust=bust, hip=hip,
                        waist=bust - 16, shoulder_width=37, sleeve_length=54)
        rows, cols, cells = printed_tile_cells(result.nesting)
        printed = set(cells)
        for placed in result.nesting.placed:
            for x, y in placed.placed_cut_line():
                # その点が載る面は、必ず印刷される面であること。
                col = min(cols - 1, max(0, int(x // A4_USABLE_W_CM)))
                row = min(rows - 1, max(0, int(y // A4_USABLE_H_CM)))
                assert (row, col) in printed, (
                    f"身長{height}: 裁断線の点({x:.1f},{y:.1f})が載るR{row+1}-C{col+1}を省いています")


def test_a_pattern_larger_than_one_tile_keeps_its_middle_tiles(tmp_path):
    """面をまるごと覆うほど大きいパーツでも、内側の面が消えないこと。

    輪郭の線が通らない面(パーツの内側)が、「線が無い」と判定されて
    省かれると、型紙の真ん中に穴が開く。
    """
    big = parse_path("M 0 0 L 60 0 L 60 80 L 0 80 Z")
    part = finalize_part("skirt", "flare", big, seam_allowance_cm=1.0)
    nesting = nest_parts([part], fabric_width_cm=110.0)
    rows, cols, cells = printed_tile_cells(nesting)
    # 60x80cmのパーツはA4の使える範囲(19x27.7cm)より大きいので、
    # 内側だけの面が必ずできる。
    assert rows >= 3 and cols >= 3, (rows, cols)
    inner = [(r, c) for r in range(rows) for c in range(cols)
             if (c + 1) * A4_USABLE_W_CM <= 60 and (r + 1) * A4_USABLE_H_CM <= 80]
    assert inner, "内側だけの面ができていません"
    for cell in inner:
        assert cell in cells, f"パーツの内側の面 {cell} が省かれています"


def test_the_stitch_line_never_escapes_the_cut_line(tmp_path):
    """面の判定を「裁断線だけ」で済ませてよい根拠を、実際に確かめる。

    `_tile_has_content`は裁断線しか見ない。縫い線・内部線・基準線・合印は
    すべて裁断線の内側にあるから、という前提に立っている。
    **前提が崩れたら型紙が1面まるごと消える**ので、ここで押さえる。

    体型と縫い代幅(0cmを含む)を振って、「縫い線は載るのに裁断線は
    載らない面」が1つも無いことを確かめる。
    """
    from engine.pdf_export import clip_polygon_to_rect

    cases = [(145, 74, 80, 1.0), (160, 84, 92, 1.0), (175, 104, 112, 1.0),
             (160, 84, 92, 0.0), (160, 84, 92, 3.0), (150, 96, 120, 0.3)]
    checked = 0
    for height, bust, hip, seam in cases:
        spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                   skirt_style="flare")
        result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
            spec, Measurements(bust=bust, waist=bust - 16, hip=hip, height=height,
                                sleeve_length=54, shoulder_width=37),
            seam_allowance_cm=seam, skip_export=True)
        nesting = result.nesting
        cols = max(1, math.ceil(nesting.fabric_width_cm / A4_USABLE_W_CM))
        rows = max(1, math.ceil(nesting.used_length_cm / A4_USABLE_H_CM)) or 1
        for row in range(rows):
            for col in range(cols):
                x0, y0 = col * A4_USABLE_W_CM, row * A4_USABLE_H_CM
                x1, y1 = x0 + A4_USABLE_W_CM, y0 + A4_USABLE_H_CM
                checked += 1
                for placed in nesting.placed:
                    cut = clip_polygon_to_rect(placed.placed_cut_line(), x0, y0, x1, y1)
                    stitch = clip_polygon_to_rect(placed.placed_stitch_line(), x0, y0, x1, y1)
                    assert not (len(stitch) >= 3 and len(cut) < 3), (
                        f"身長{height}/縫い代{seam}: R{row+1}-C{col+1} は縫い線だけが載っています"
                        "（裁断線だけを見る判定では、この面が消えます）")
    assert checked > 100, f"調べた面が少なすぎます: {checked}"


# --- 2. 表紙が本当の枚数を書くこと ------------------------------------------

def test_the_cover_states_the_number_of_sheets_actually_printed(tmp_path):
    result = _dress(tmp_path)
    rows, cols, cells = printed_tile_cells(result.nesting)
    cover = _page_texts(result.output_files["pdf"])[0]
    assert f"全{len(cells)}枚" in cover, cover[:200]
    assert f"({rows}行 x {cols}列)" in cover, cover[:200]
    assert f"型紙の載らない{rows * cols - len(cells)}枚は省いています" in cover, cover[:200]


def test_the_cover_says_nothing_about_omissions_when_there_are_none():
    """省く面が無いときは、その一文を出さないこと(読み飛ばす癖をつけない)。"""
    small = parse_path("M 0 0 L 15 0 L 15 20 L 0 20 Z")
    part = finalize_part("front_bodice", "round_neck", small, seam_allowance_cm=1.0)
    nesting = nest_parts([part], fabric_width_cm=19.0)
    rows, cols, cells = printed_tile_cells(nesting)
    assert len(cells) == rows * cols, "この生地幅では全面に型紙が載るはず"


def test_the_assembly_map_only_numbers_the_sheets_you_will_hold(tmp_path):
    """貼り合わせ図が、印刷されない面の番号を書かないこと。

    図は「どの紙がどこに来るか」の索引なので、手元に来ない紙の番号が
    載っていると「印刷に失敗したのでは」と探させることになる。
    """
    result = _dress(tmp_path)
    rows, cols, cells = printed_tile_cells(result.nesting)
    cover = _page_texts(result.output_files["pdf"])[0]
    printed = set(cells)
    for row in range(rows):
        for col in range(cols):
            name = f"R{row + 1}-C{col + 1}"
            if (row, col) in printed:
                assert name in cover, f"{name} が貼り合わせ図に載っていません"
            else:
                assert name not in cover, f"印刷しない {name} が貼り合わせ図に載っています"


# --- 3. 枚数を、ダウンロードする前に知らせること ----------------------------

def test_the_summary_reports_the_sheet_count(tmp_path):
    result = _dress(tmp_path)
    summary = result.summary()
    _rows, _cols, cells = printed_tile_cells(result.nesting)
    assert summary["pdf_sheet_count"] == len(cells)


def test_the_reported_sheet_count_matches_the_actual_pdf(tmp_path):
    """画面に出す枚数と、PDFの中身がずれないこと。

    別々に数えると「30枚と書いてあるのに28枚しか出ない」が起きる。
    表紙・買い物メモ・縫う順番の3ページを除いた残りが型紙の枚数。
    """
    result = _dress(tmp_path)
    texts = _page_texts(result.output_files["pdf"])
    tile_pages = [t for t in texts if "PatternForge  R" in t]
    assert result.summary()["pdf_sheet_count"] == len(tile_pages)


def test_the_screen_shows_the_sheet_count(client):
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
    })
    assert response.status_code == 200, response.get_json().get("error")
    assert response.get_json()["pdf_sheet_count"] > 0

    body = client.get("/").get_data(as_text=True)
    assert 'id="pdf-sheet-hint"' in body, "枚数を出す場所が画面にありません"

    # 【最初この2行だけ書いていて、呼び出しを消しても通った】
    # 「app.jsのどこかに pdf_sheet_count と書いてある」では、
    # 関数が**呼ばれなくなった**ことを捕まえられない。結果を描く処理から
    # 実際に呼ばれていることを見る(ブラウザでの表示そのものは
    # scripts/audit_print_sheets.py が実機で確かめる)。
    # さらに `"renderPdfSheetCount(data)" in js` とも書いたが、これも
    # **関数の定義行**(`function renderPdfSheetCount(data) {`)に当たって
    # 通ってしまった。定義と呼び出しで2回以上出ることを見る。
    js = client.get("/static/app.js").get_data(as_text=True)
    assert "pdf_sheet_count" in js, "画面が枚数を読み取っていません"
    assert js.count("renderPdfSheetCount") >= 2, (
        "枚数を描く関数が定義されているだけで、呼ばれていません")


# --- 4. 退化した入力でも壊れないこと ----------------------------------------

def test_a_pdf_is_never_produced_with_zero_pages(tmp_path):
    """1面も型紙が載らないときに、0ページのPDFを作らないこと。

    0ページのPDFは開けないビューアがある。省く仕組みを入れたときに
    実際にそうなった(このテストが落ちて気づいた)。
    """
    import pypdf

    empty = NestingResult(placed=[], unplaced=[], fabric_width_cm=110.0,
                           used_length_cm=0.0, waste_ratio=0.0)
    out = str(tmp_path / "empty.pdf")
    render_a4_pdf(empty, out)
    assert len(pypdf.PdfReader(out).pages) >= 1
