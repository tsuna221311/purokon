"""round63: 新しく入った人が読める形を、崩さないための見張り。

チームに下級生が入るので、コードを読める形に整理した。整理そのものは
一度やれば終わりだが、**放っておくとまた元に戻る**——長い関数は、
1行ずつ足されて長くなる。だから測って止める。

このラウンドで測った値:

    _build_from_spec   663行 → 261行 (段階ごとに名前を付けて外へ出した)
    api_generate       498行 → 275行 (モードごとに分けた)

どちらも**動きは1つも変えていない**。`scripts/snapshot_outputs.py`で
9通りの型紙を出し、PDFの全ページ画像・DXFの図形・SVG・縫う順番・注記の
文章を、整理の前後で突き合わせて同じであることを確かめてある。

ここで見張るのは3つ:

  1. 最初に読む関数が、また長くならないこと
  2. `docs/はじめに.md` の地図が、実際のファイルと食い違わないこと
  3. `_build_from_spec` の目次に書いた段階が、実在すること
"""

import ast
import pathlib
import re

import pytest


REPO = pathlib.Path(__file__).resolve().parent.parent


def _functions(path: str) -> dict[str, int]:
    """そのファイルの関数名 -> 行数。"""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    return {node.name: node.end_lineno - node.lineno + 1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


# ---------------------------------------------------------------------------
# 1. 最初に読む関数が、また長くならないこと
# ---------------------------------------------------------------------------

#: 新しく入った人が**最初に開く**関数と、その上限(行)。
#:
#: 上限はround63で整理したあとの実測値に、少しだけ余裕を足した値である。
#: 機能を足すときにここが伸びそうになったら、**段階を1つ外へ出す**のが
#: このコードのやり方(`_prepare_settings`や`_respond_manual`がその例)。
#:
#: 【なぜこの2つだけか】コード全体に上限を課すと、描画のように「上から
#: 順に読むのが自然な」長い関数まで無理に割ることになる。見張るのは
#: 「そこから読み始める場所」に絞る。
ENTRY_POINTS = {
    ("engine/pipeline.py", "_build_from_spec"): (
        300, "型紙ができる流れの本体。ここを読んで全体像がつかめること"),
    ("app.py", "api_generate"): (
        320, "画面から来た値の入口。モードごとの中身は別の関数にある"),
}


@pytest.mark.parametrize("path, name", sorted(ENTRY_POINTS))
def test_the_first_function_you_read_stays_short(path, name):
    limit, why = ENTRY_POINTS[(path, name)]
    length = _functions(path)[name]
    assert length <= limit, (
        f"{name} が {length}行 になりました(上限{limit}行)。{why}。\n"
        "段階を1つ、名前を付けて外へ出してください"
        "（やり方は docs/はじめに.md と、この関数の並びを見てください）。")


def test_the_phases_are_actually_separate_functions():
    """段階が、本当に別の関数として存在すること。

    目次だけ書いて中身が1つの関数のまま、では読めるようにならない。
    """
    methods = _functions("engine/pipeline.py")
    for phase in ("_prepare_settings", "_scale_every_part",
                   "_finalize_every_part", "_nest_on_fabric",
                   "_draw_lining", "_export_files", "_build_fabric_groups"):
        assert phase in methods, f"{phase} がありません"
        assert methods[phase] < 200, (
            f"{phase} が{methods[phase]}行あります。段階の中身としては長すぎます")


def test_each_mode_has_its_own_function():
    """3つのモードが、それぞれ自分の関数を持っていること。"""
    functions = _functions("app.py")
    for mode in ("_respond_manual", "_respond_illustration", "_respond_multi_size"):
        assert mode in functions, f"{mode} がありません"
        assert functions[mode] < 200, f"{mode} が{functions[mode]}行あります"


# ---------------------------------------------------------------------------
# 2. 「はじめに」の地図が、実際と食い違わないこと
# ---------------------------------------------------------------------------

GUIDE = "docs/はじめに.md"


def _guide_text() -> str:
    return (REPO / GUIDE).read_text(encoding="utf-8")


def test_the_guide_exists_and_readme_points_at_it():
    assert (REPO / GUIDE).exists(), f"{GUIDE} がありません"
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "docs/はじめに.md" in readme, "READMEから案内していません"
    # 案内は**最初のほう**に無いと意味がない(1万行の下では見つからない)。
    assert readme.index("docs/はじめに.md") < 1000, \
        "案内がREADMEの奥にあります。最初に見える場所へ置いてください"


def test_every_engine_file_in_the_map_really_exists():
    """地図に載っているファイルが、全部実在すること。

    消えたファイルが地図に残っていると、新しい人はそれを探しに行く。
    """
    missing = [name for name in re.findall(r"`(\w+\.py)`", _guide_text())
               if not (REPO / "engine" / name).exists()
               and not (REPO / name).exists()
               and not (REPO / "scripts" / name).exists()
               and not (REPO / "tests" / name).exists()]
    assert not missing, f"地図に載っているのに無いファイル: {missing}"


def test_every_engine_file_is_on_the_map():
    """`engine/` のファイルが、地図から漏れていないこと。

    漏れていると、新しい人は「これは何をするのか」を自分で探すことになる。
    """
    listed = set(re.findall(r"`(\w+\.py)`", _guide_text()))
    actual = {p.name for p in (REPO / "engine").glob("*.py")
              if p.name != "__init__.py"}
    missing = sorted(actual - listed)
    assert not missing, (
        f"地図に載っていない engine のファイル: {missing}。"
        f"{GUIDE} の表に1行足してください")


def test_every_script_the_guide_tells_you_to_run_exists():
    """地図が「走らせてください」と言う道具が、全部あること。"""
    commands = re.findall(r"python3 (scripts/\w+\.py)", _guide_text())
    assert commands, "走らせる道具が1つも書かれていません"
    missing = [c for c in commands if not (REPO / c).exists()]
    assert not missing, f"案内にあるのに無い道具: {missing}"


def test_the_guide_stays_short_enough_to_read_in_ten_minutes():
    """「最初の10分」と言っている以上、10分で読める長さであること。

    日本語で1分に400〜600字として、10分なら4,000〜6,000字くらい。
    ここを超えるなら、それは「はじめに」ではなく資料である。
    """
    text = _guide_text()
    characters = len(re.sub(r"\s", "", text))
    assert characters <= 6000, (
        f"{characters}字あります。10分では読めません——"
        "詳しい話は README.md 側へ移してください")


# ---------------------------------------------------------------------------
# 3. 目次が、実際の呼び出しと合っていること
# ---------------------------------------------------------------------------

def test_the_table_of_contents_matches_what_is_called():
    """`_build_from_spec` の目次に書いた段階が、本当に呼ばれていること。

    名前を変えたのに目次を直し忘れると、地図が嘘になる。
    """
    source = (REPO / "engine/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_build_from_spec")
    doc = ast.get_docstring(fn) or ""
    listed = set(re.findall(r"`(_\w+)`", doc))
    assert listed, "目次に段階が1つも書かれていません"

    called = {node.func.attr for node in ast.walk(fn)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)}
    not_called = sorted(listed - called)
    assert not not_called, (
        f"目次に書いてあるのに呼ばれていない段階: {not_called}")


def test_the_guide_and_the_docstring_list_the_same_phases():
    """「はじめに」の流れと、コードの目次が同じであること。

    2か所に同じ順番を書いているので、片方だけ直されると食い違う
    (round61で3回やった間違いと同じ形)。
    """
    source = (REPO / "engine/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_build_from_spec")
    in_code = re.findall(r"`(_\w+)`", ast.get_docstring(fn) or "")
    in_guide = re.findall(r"^\s*\d+\. (_\w+)", _guide_text(), re.MULTILINE)
    assert in_code == in_guide, (
        f"コードの目次 {in_code} と、はじめにの流れ {in_guide} が違います")
