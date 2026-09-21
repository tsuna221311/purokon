"""round61: 同じPDFの中で、裏地の裾の数字が2つあった。

裏地付きで生成して、刷り上がりの「縫う順番」を最初から読んだ。
手順11と手順12が、同じことについて違う数字を言っていた:

    11. 裾を始末する
        …裏地の裾の縫い代は0cmで、表地より**1cm**短く裁ってあります…

    12. 裏地を身頃に合わせる
        …型紙が持っている数字は、裏地の裾が表地より**2cm**短いことと…

規則は「表地の裾の縫い代 − 2cm」だが、負の縫い代は作れないので、
既定(裾1.0cm)では**1.0cmしか引けない**。手順11は計算した値、手順12は
手書きの2cmで、手書きの方が嘘だった。

【この間違いは2度目である】round46で`lining_notes`の決め打ちを実測値に
直したとき、同じ主張が縫う順番にも手書きされていて取り残された。
round49がそれを直し、`hem_reduction_sentence`に文を1つにまとめ、
assembly.pyにこう書き残した:

    # round49: 裏地の説明は engine/lining.py に1つだけ置いた文を使う。
    # 以前はここに「表地より2cm短く」と手書きしてあり、…
    # **この1文だけが取り残されて** 既定(裾1.0cm)で「2cm短く」と
    # 嘘を言い続けていた。

**その警告の10行下に、あとから足された手順12が同じ2cmを書いていた。**
コメントでは再発を止められなかったので、このファイルで止める。

ついでに同じ形をしている箇所を2つ直した。どちらも今は定数と一致して
いるが、定数を変えると文だけが古い数字を言い続ける:

  * `lining.py` 「規則どおりの2cmは引けていません」
  * `fabric.py` 「(この型紙では1%でも3%でも同じ切り売り単位に収まります)」
"""

import ast
import re
import subprocess

import pytest

from engine import fabric as fabric_module
from engine import lining as lining_module
from engine.assembly import assembly_steps
from engine.lining import (LINING_HEM_REDUCTION_CM, hem_gap_phrase,
                            hem_reduction_cm, hem_reduction_sentence)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec


MEAS = Measurements(bust=88, waist=70, hip=94, height=162,
                    sleeve_length=55, shoulder_width=39)

#: 数字＋単位。手書きで埋め込まれていないかを探すのに使う。
_NUMBER_WITH_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:cm|ｃｍ|mm|%|度|°)")


def _steps_text(hem_cm: float) -> str:
    """その裾の縫い代で出る、縫う順番の全文。"""
    pipeline = PatternForgePipeline(output_dir="/tmp/pf-r61-unused")
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(
        spec, MEAS, skip_export=True, lining=True,
        hem_seam_allowance_cm=hem_cm)
    return " ".join(f"{s.title} {s.detail}" for s in result.assembly_steps())


# ---------------------------------------------------------------------------
# 1. 同じPDFの中で、数字が食い違わないこと
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hem_cm", [0.5, 1.0, 2.0, 3.0, 4.0])
def test_the_lining_hem_gap_is_the_same_number_everywhere(hem_cm):
    """裏地の裾が「何cm短いか」が、手順のどこでも同じ値であること。

    round60まで、既定(裾1.0cm)で手順11が1cm・手順12が2cmと言っていた。
    """
    text = _steps_text(hem_cm)
    removed = hem_reduction_cm(hem_cm)
    claimed = set(re.findall(r"表地より(\d+(?:\.\d+)?)cm短", text))
    claimed |= set(re.findall(r"表地より(\d+(?:\.\d+)?)cm短いこと", text))
    assert claimed, f"裾{hem_cm}cm: 「表地より○cm短い」が1つも出ていません"
    assert claimed == {f"{removed:g}"}, (
        f"裾{hem_cm}cm: 実際は{removed:g}cm短いのに、手順は{sorted(claimed)}と"
        "言っています")


def test_the_default_case_is_the_one_that_was_wrong():
    """既定の設定で、実際に食い違いが直っていること。

    利用者のほとんどは既定のまま使う。round60まで、その既定が壊れていた。
    """
    text = _steps_text(1.0)
    assert "表地より1cm短く裁ってあります" in text
    assert "表地より2cm短い" not in text, text[-400:]


@pytest.mark.parametrize("hem_cm", [0.0, 0.5, 1.0, 3.0])
def test_the_final_step_never_claims_a_gap_that_does_not_exist(hem_cm):
    """引ける量が0のときに「0cm短い」と言わないこと。

    嘘ではないが、読んだ人は「何が引いてあるのか」と探すことになる。
    """
    phrase = hem_gap_phrase(hem_cm)
    if hem_reduction_cm(hem_cm) <= 0:
        assert "短い" not in phrase, phrase
        assert "表地と同じです" in phrase, phrase
    else:
        assert "短いこと" in phrase, phrase


def test_the_two_steps_read_from_the_same_place():
    """手順11と手順12が、同じ1か所から数字を取っていること。

    文面を別々に組み立てていると、また片方だけ直されて食い違う。
    """
    source = ast.parse(open("engine/assembly.py", encoding="utf-8").read())
    called = {node.func.id for node in ast.walk(source)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "hem_reduction_sentence" in called, "手順11が自分で書いています"
    assert "hem_gap_phrase" in called, "手順12が自分で書いています"


# ---------------------------------------------------------------------------
# 2. 規則を変えたら、文がついてくること
# ---------------------------------------------------------------------------

def test_the_wording_follows_the_rule_not_a_hand_written_number(monkeypatch):
    """規則の数字(2cm)を変えたら、文の中の数字も変わること。

    ここが手書きだと、規則を直した人は文が嘘になったことに気づけない。
    """
    monkeypatch.setattr(lining_module, "LINING_HEM_REDUCTION_CM", 3.0)
    sentence = lining_module.hem_reduction_sentence(1.0)
    assert "規則どおりの3cmは引けていません" in sentence, sentence
    assert "規則どおりの2cm" not in sentence


def test_the_shrink_range_follows_its_constants(monkeypatch):
    """地直しの許容値(1〜3%)を変えたら、注記の数字も変わること。"""
    monkeypatch.setattr(fabric_module, "COTTON_LINEN_SHRINK_MIN_PERCENT", 2.0)
    monkeypatch.setattr(fabric_module, "COTTON_LINEN_SHRINK_MAX_PERCENT", 4.0)
    pipeline = PatternForgePipeline(output_dir="/tmp/pf-r61-unused")
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    notes = " ".join(result.shopping_list.notes)
    if "同じ切り売り単位に収まります" in notes:
        assert "2%でも4%でも" in notes, notes
        assert "1%でも3%でも" not in notes, notes
    assert "形状変化率2〜4%" in notes, notes


# ---------------------------------------------------------------------------
# 3. 手書きの数字そのものを止める
# ---------------------------------------------------------------------------

#: 利用者に見せる文を組み立てるモジュール。ここでは「出典の引用」以外に
#: 数字を手書きしてはいけない——同じ数字が計算側にもあると、必ず片方が
#: 古くなる(round46・49・61に3回起きた)。
_TEXT_MODULES = ("engine/assembly.py", "engine/lining.py", "engine/fabric.py")


#: **わざと手書きしている**数字と、その理由。
#:
#: 出典の引用(「…」の中)は自動で対象外にしている。それ以外で手書きが
#: 正しいのは、「この型紙の計算とは関係がない数字」だけである。
#: 足すときは必ず理由を書くこと——理由が書けないなら、それは計算した値
#: から出すべき数字である。
_HAND_WRITTEN_ON_PURPOSE = {
    ("engine/lining.py", "裏地の丈そのものを表地より2cm短くする流儀"):
        "採らなかった別の流儀(かたやまゆうこ式)がそう書いている値。"
        "この型紙の計算とは関係がない",
    ("engine/lining.py", "出典の実例は表4cm→裏2cm"):
        "出典が挙げている実例そのもの。計算式ではなく、出典の表である",
    ("engine/fabric.py", "縮率は100%未満で指定してください"):
        "割合の上限そのもの。規則ではなく量の性質なので、変わりようがない",
}


def _literal_numbers_outside_quotations(path: str) -> list[str]:
    """その文字列の中で、「」の外にある数字＋単位を集める。

    出典の引用(「…」)に含まれる数字は、**出典がそう書いている**ので
    手書きで正しい。それ以外は計算した値から出すべきものである。
    ただし`_HAND_WRITTEN_ON_PURPOSE`に理由を書いて登録したものは除く。
    """
    tree = ast.parse(open(path, encoding="utf-8").read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    # f文字列の書式指定(`:.1f`のような部分)は刷られる文ではない。
    format_specs = {spec for node in ast.walk(tree)
                    if isinstance(node, ast.FormattedValue) and node.format_spec
                    for spec in ast.walk(node.format_spec)
                    if isinstance(spec, ast.Constant)}

    allowed = [snippet for (module, snippet) in _HAND_WRITTEN_ON_PURPOSE
               if module == path]
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node in format_specs:
            continue
        text = node.value
        if text in docstrings:
            continue          # 説明文であって、刷られる文ではない
        if any(snippet in text for snippet in allowed):
            continue          # 理由を書いて登録してある
        # 「」の中を取り除いてから探す(引用は対象外)。
        outside = re.sub(r"「[^」]*」", "", text)
        for hit in _NUMBER_WITH_UNIT.findall(outside):
            found.append(f"{path}: {hit} … {text[:60]}")
    return found


def test_no_hand_written_numbers_in_the_text_we_print():
    """刷る文の中に、出典の引用でない手書きの数字が無いこと。

    round49はこれをコメントで警告したが、**その10行下**で同じ間違いが
    再発した。コメントは読まれなければ効かない。テストなら落ちる。
    """
    problems = []
    for path in _TEXT_MODULES:
        problems.extend(_literal_numbers_outside_quotations(path))
    assert not problems, (
        "計算した値ではなく手書きの数字が刷られます。"
        "計算した値から出すか、わざと手書きするなら"
        "`_HAND_WRITTEN_ON_PURPOSE`に理由を書いて登録してください:\n  "
        + "\n  ".join(problems))


def test_every_hand_written_number_still_exists():
    """理由を書いて登録した手書きが、まだその文に残っていること。

    文を書き直したあとも登録が残っていると、次に手書きを足した人を
    黙って見逃すことになる。
    """
    for (path, snippet), reason in _HAND_WRITTEN_ON_PURPOSE.items():
        source = open(path, encoding="utf-8").read()
        assert snippet in source, f"{path} に「{snippet}」がもうありません"
        assert len(reason) > 10, f"{snippet} の理由が書かれていません"


# ---------------------------------------------------------------------------
# 4. 刷り上がりで確かめる
# ---------------------------------------------------------------------------

def test_the_printed_pdf_does_not_contradict_itself(tmp_path):
    """実際に書き出したPDFの全文に、食い違う数字が無いこと。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(spec, MEAS, lining=True)
    text = subprocess.run(["pdftotext", result.output_files["pdf"], "-"],
                          capture_output=True, text=True, check=True).stdout
    flat = text.replace("\n", "")
    claims = set(re.findall(r"表地より(\d+(?:\.\d+)?)cm短", flat))
    assert claims == {f"{hem_reduction_cm(1.0):g}"}, (
        f"PDFの中で数字が食い違っています: {sorted(claims)}")
