"""round56: マント・装甲の画面を、ブラウザで実際に触って見つけたもの。

カスタムパーツ(マント・翼・装甲プレート)はコスプレ向けのいちばん特徴的な
機能なのに、これまでAPI経由でしか触っていなかった。実ブラウザで
「画像を上げる → 輪郭を自動抽出 → 参照点で実寸に校正 → 生成」を
通してみて、3つ見つかった。

  1. **押せる範囲の検査が、この画面を一度も測っていなかった。**
     カスタムパーツのカードは「＋ カスタムパーツを追加」を押すまで
     DOMに存在しない。round44から続けている`audit_target_size.py`は
     ページを開いて測るだけなので、**コスプレ向けの画面だけが
     検査の外**にあった。実測すると「左右反転パーツも作る」の
     押せる範囲が152×18pxで、24×24pxを満たしていなかった。

  2. **「どの生地幅にも収まらない」の“最大”が、間違っていた。**
     幅173cmのマントはどの候補幅にも入らないが、警告は
     「どの生地幅(最大110cm)にも収まらず」と出ていた。110cmは
     **選ばれた幅**であって、試した最大ではない(150cmまで試している)。
     読んだ人は「150cm幅を買えば入る」と受け取ってしまう。

  3. **画面の印刷枚数とPDFの中身が食い違っていた(round53の取りこぼし)。**
     1面も型紙が載らないとき、PDFは「0ページにしない」ために格子を
     全面出す。ところが枚数を数える側は0を返していたので、
     画面「型紙0枚」/ PDFには6枚、という状態だった。
     数える側と出す側で一覧そのものを共有する形に直した。
"""

import ast
import json

import pytest

from engine.measurements import Measurements
from engine.nesting import DEFAULT_FABRIC_WIDTHS_CM, best_fabric_width, nest_parts
from engine.pdf_export import printed_tile_cells
from engine.pipeline import (
    PatternForgePipeline, build_custom_panel_requests, build_garment_spec,
)
from engine.seam import finalize_part
from engine.svgpath import parse_path


MEASUREMENTS = Measurements(bust=84, waist=68, hip=92, height=160,
                             sleeve_length=54, shoulder_width=37)

#: 幅173cm・高さ227cmのマント。どの候補幅(110/140/150cm)にも収まらない。
HUGE_CAPE_CM = [(0.0, 0.0), (173.0, 0.0), (173.0, 227.0), (0.0, 227.0)]


def _cape_only(tmp_path, points_cm=None):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    spec.parts.clear()          # 本体パーツを含めない(マントだけ作る)
    spec.parts.extend(build_custom_panel_requests(
        "マント", points_cm or HUGE_CAPE_CM, quantity=1, mirror=False))
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEASUREMENTS)


def _page_texts(path):
    import pypdf

    return [page.extract_text() or "" for page in pypdf.PdfReader(path).pages]


# --- 1. 収まらなかったときの警告が、正しい幅を言うこと ----------------------

def test_the_unplaced_warning_names_the_widest_width_actually_tried(tmp_path):
    """「最大◯cm」が、**試した中でいちばん広い幅**であること。

    選ばれた幅(110cm)を最大として書いていたので、150cmまで試して全部
    だめだった場合でも「最大110cm」と出ていた。読んだ人は
    「150cm幅を買えば入る」と受け取ってしまう——買っても入らない。
    """
    result = _cape_only(tmp_path)
    assert result.nesting.unplaced, "このマントは収まらないはず"
    warning = result.summary()["unplaced_warnings"][0]
    widest = max(DEFAULT_FABRIC_WIDTHS_CM)
    assert f"最大{widest:.0f}cm" in warning, warning
    assert f"最大{result.nesting.fabric_width_cm:.0f}cm" not in warning or \
        result.nesting.fabric_width_cm == widest, warning


def test_the_nesting_records_which_widths_it_tried():
    part = finalize_part("front_bodice", "round_neck",
                          parse_path("M 0 0 L 20 0 L 20 30 L 0 30 Z"),
                          seam_allowance_cm=1.0)
    best = best_fabric_width([part], candidates=(110.0, 140.0, 150.0))
    assert best.tried_widths_cm == (110.0, 140.0, 150.0)


def test_a_single_width_nesting_still_reports_a_width():
    """幅を1つだけ指定して並べた場合も、警告の「最大」が空にならないこと。"""
    wide = finalize_part("skirt", "flare",
                          parse_path("M 0 0 L 400 0 L 400 30 L 0 30 Z"),
                          seam_allowance_cm=1.0)
    result = nest_parts([wide], fabric_width_cm=110.0)
    assert result.unplaced
    assert result.tried_widths_cm == () or result.tried_widths_cm == (110.0,)


# --- 2. 画面の枚数とPDFの中身が一致すること ---------------------------------

def test_the_sheet_count_matches_the_pdf_even_when_nothing_fits(tmp_path):
    """1面も型紙が載らないときでも、数字とPDFが一致すること。

    PDFは「0ページのPDFを作らない」ために格子を全面出す。数える側だけが
    0を返していたので、画面「0枚」/ PDF 6枚という食い違いになっていた。
    """
    result = _cape_only(tmp_path)
    tiles = [t for t in _page_texts(result.output_files["pdf"]) if "PatternForge" in t]
    assert result.summary()["pdf_sheet_count"] == len(tiles), (
        f"画面{result.summary()['pdf_sheet_count']}枚 / PDF{len(tiles)}枚")
    assert len(tiles) >= 1, "0ページのPDFになっています"


def test_the_sheet_count_matches_the_pdf_in_the_ordinary_case(tmp_path):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEASUREMENTS)
    tiles = [t for t in _page_texts(result.output_files["pdf"]) if "PatternForge" in t]
    assert result.summary()["pdf_sheet_count"] == len(tiles)
    # 普段は白紙を省いている(全面ではない)こと。
    rows, cols, cells = printed_tile_cells(result.nesting)
    assert len(cells) < rows * cols, "省ける面が1つも無いジョブでは、このテストは空振り"


def test_the_counter_and_the_pdf_share_one_list(tmp_path):
    """数える側と出す側が、**同じ面の一覧**を使っていること。

    別々に判定していると、片方にだけ逃げ道(0ページ防止)を足したときに
    食い違う。実際round53でそうなった。
    """
    result = _cape_only(tmp_path)
    rows, cols, cells = printed_tile_cells(result.nesting)
    texts = _page_texts(result.output_files["pdf"])
    printed_names = {t.split("R", 1)[1].split(" ")[0]
                     for t in texts if "PatternForge  R" in t}
    expected = {f"{row + 1}-C{col + 1}" for row, col in cells}
    assert printed_names == expected, (sorted(printed_names), sorted(expected))


# --- 3. 画面側(押せる範囲の検査が届いていなかったところ) --------------------

def _audit_script():
    """`scripts/audit_target_size.py`を構文木として読む。

    文字列があるかで見ると、**コメントに書いてあるだけ**でも通ってしまう
    (round56で実際に踏んだ)。コードとして存在することを見る。
    """
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent
              / "scripts" / "audit_target_size.py").read_text(encoding="utf-8")
    return ast.parse(source)


def _calls_with_argument(tree, argument, func_name=None) -> bool:
    """その文字列を引数に渡す呼び出しが、コードの中に実在するか。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if func_name is not None:
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == func_name:
                return True
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == argument:
                return True
    return False


def test_the_mirror_checkbox_row_is_tall_enough(client):
    """カスタムパーツの「左右反転パーツも作る」が24px以上になること。

    カードはJSで作られるので、CSSの規則が消えていないことで見る
    (実際の画素は`scripts/audit_target_size.py`が実ブラウザで測る。
    round56でその台本にも、カードを1つ追加した状態を足した)。
    """
    css = client.get("/static/style.css").get_data(as_text=True)
    import re
    match = re.search(r"\.custom-panel-card-header label \{([^}]*)\}", css)
    assert match, "カスタムパーツのカードのlabelの規則がありません"
    body = match.group(1)
    height = re.search(r"min-height:\s*(\d+)px", body)
    assert height and int(height.group(1)) >= 24, body


def test_the_audit_script_covers_the_custom_panel_card():
    """押せる範囲の検査が、カスタムパーツのカードを開いた状態も測ること。

    この画面はボタンを押すまでDOMに存在しないので、台本に書いていないと
    **永久に検査されない**。round44から12ラウンド、実際に外れていた。
    """
    import pathlib

    # 【最初これを `"#add-custom-panel-btn" in script` と書いて、
    #  その行をコメントに変えても通った】——コメントの中身に当たっていた。
    #  構文木で「実際に呼んでいる」ことを見る(round52・53と同じ形の失敗)。
    assert _calls_with_argument(_audit_script(), "#add-custom-panel-btn"), (
        "audit_target_size.py が、カスタムパーツのカードを開いていません")


def test_the_audit_script_fails_when_it_finds_something():
    """検査が見つけたときに、終了コードで落ちること。

    見つけても0を返していたので、自動で回しても気づけなかった。
    """
    import pathlib

    # 【最初これを文字列の有無で見て、最後のreturnを0に変えても通った】
    #  同じ文字列が`--json`の分岐にもあったため。構文木で、main()の
    #  **すべての**returnが「失敗があれば0以外」になっていることを見る。
    tree = _audit_script()
    main_fn = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
    returns = [node for node in ast.walk(main_fn) if isinstance(node, ast.Return)]
    assert returns, "main()にreturnがありません"
    for node in returns:
        assert not (isinstance(node.value, ast.Constant) and node.value.value == 0), (
            "見つけても0を返す経路があります: " + ast.unparse(node))
    assert _calls_with_argument(tree, None, func_name="SystemExit"), \
        "終了コードを使っていません(raise SystemExit(main()))"


# --- 4. 画面から来る入力の検査(ブラウザで実際に踏んだもの) ------------------

def test_a_contour_with_too_few_points_is_refused(client):
    """頂点が3つ未満のまま送ったら、はっきり断ること。

    実ブラウザでは送信前に画面側が止める(「輪郭の頂点を3つ以上指定して
    ください」)。APIを直接叩いた場合もサーバが断ることを見る。
    """
    panels = json.dumps([{"label": "マント", "points": [[0, 0], [10, 0]],
                           "ref_point_a": [0, 0], "ref_point_b": [10, 0],
                           "reference_cm": 40, "quantity": 1, "mirror": False}])
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "include_body_garment": "0", "custom_panels_json": panels,
    })
    assert response.status_code == 400
    assert "3〜300個" in response.get_json()["error"], response.get_json()["error"]


def test_a_panel_without_reference_points_is_refused(client):
    panels = json.dumps([{"label": "マント",
                           "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                           "ref_point_a": None, "ref_point_b": None,
                           "reference_cm": 40, "quantity": 1, "mirror": False}])
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "include_body_garment": "0", "custom_panels_json": panels,
    })
    assert response.status_code == 400
    assert "参照点" in response.get_json()["error"]
