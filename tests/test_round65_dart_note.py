"""round65: 「ダーツが入ったパーツ」の説明が、実物と違うパーツ名を挙げていた。

パソコンで一着ぶん生成して、裁つ前の確認をするつもりで結果を読んだ。
ダーツはV字の切り込みなので、**どのパーツのどこを見るか**が要る。
画面にはこう書いてあった:

    ✓ 体型に応じて、ダーツを合計8本追加しました
      （身頃のウエスト/脇ダーツ、タイトスカートのウエストダーツなど、
        V字の切り込みが目印です）

この括弧の中は `web/templates/index.html` に**手書き**されていて、
合計の数だけが差し込まれていた。14通りの構成で実測した結果:

```
    文が出た構成                                    11通り
      うち、挙げたパーツにダーツが1本も入っていない  10通り
      うち、ダーツが入っているのに触れないパーツがある 2通り

    B88 W70 H94   どの裾でも(サーキュラー/タイト/マーメイド/プリーツ/パンツ)
                  ダーツは前身頃・後身頃だけ。**タイトでもスカートには入らない**
    B88 W60 H100  パンツ  身頃12本 + パンツ8本 → 文はパンツに触れない
    B88 W60 H100  マーメイド 身頃12本 + マーメイド4本 → 文は「タイトスカート」と言う
    B88 W60 H100  スカートだけ スカート4本 → 文は「身頃」と言う（身頃は無い）
```

**縫う順番(`engine/assembly.py`)は、最初からこれを正しくやっていた。**
`dart_count`を持つパーツを集めて名前を並べている。同じ画面の20行隣で、
説明の方だけが例示を手書きしていた。

直し方: `summary()`に`darts_by_part`を足し、画面はそれを並べる。
**パーツ名を画面に書かない。**

このファイルが見張るのは:

  1. `darts_by_part` が、実際にダーツを持つパーツと食い違う
  2. 画面のダーツ説明に、またパーツ名を手書きする
  3. 画面が `darts_by_part` 以外から名前を作る
"""

import re
from pathlib import Path

import pytest

from engine.measurements import Measurements
from engine.part_names import PART_TYPE_LABELS_JA, VARIATION_LABELS_JA
from engine.pipeline import PatternForgePipeline, build_garment_spec

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

#: 標準的な体型と、ウエストが細い体型。後者ではスカート・パンツにも入る。
BODIES = {
    "標準": Measurements(bust=88, waist=70, hip=94, height=163,
                          sleeve_length=56, shoulder_width=39),
    "ウエストが細い": Measurements(bust=88, waist=60, hip=100, height=163,
                                    sleeve_length=56, shoulder_width=39),
}

SHAPES = {
    "サーキュラー": dict(skirt_style="circle"),
    "タイト": dict(skirt_style="tight"),
    "マーメイド": dict(skirt_style="mermaid"),
    "プリーツ": dict(skirt_style="pleated"),
    "パンツ": dict(skirt_style=None, include_pants=True),
}

CASES = [(b, s) for b in BODIES for s in SHAPES]


@pytest.fixture(scope="module")
def pipe():
    return PatternForgePipeline()


def _summary(pipe, body: str, shape: str) -> dict:
    spec = build_garment_spec(**SHAPES[shape])
    result = pipe.generate_from_selection(spec, BODIES[body], skip_export=True)
    return result.summary(), result


@pytest.mark.parametrize("body,shape", CASES)
def test_darts_by_part_matches_the_parts_that_really_have_darts(pipe, body, shape):
    """説明の元になる一覧が、実物とずれたら落ちる。"""
    summary, result = _summary(pipe, body, shape)
    expected = {p.name_without_dart_count: p.dart_count
                for p in result.finalized_parts if p.dart_count}
    got = {row["name"]: row["dart_count"] for row in summary["darts_by_part"]}
    assert got == expected, (body, shape)


@pytest.mark.parametrize("body,shape", CASES)
def test_the_total_and_the_breakdown_agree(pipe, body, shape):
    """合計だけが別の数になっていたら落ちる。"""
    summary, _ = _summary(pipe, body, shape)
    assert sum(row["dart_count"] for row in summary["darts_by_part"]) \
        == summary["darts_applied"], (body, shape)


@pytest.mark.parametrize("body,shape", CASES)
def test_every_named_part_is_really_in_this_pattern(pipe, body, shape):
    """この型紙に無いパーツ名を挙げたら落ちる（これが今回の不具合そのもの）。"""
    summary, _ = _summary(pipe, body, shape)
    printed = [p["display_name"] for p in summary["parts"]]
    for row in summary["darts_by_part"]:
        assert any(name.startswith(row["name"]) for name in printed), (
            f"{body}/{shape}: 説明が「{row['name']}」を挙げていますが、"
            f"この型紙のパーツは {printed} です。")


@pytest.mark.parametrize("body,shape", CASES)
def test_no_part_with_darts_is_left_out(pipe, body, shape):
    """ダーツが入っているのに黙っているパーツがあれば落ちる。

    （round64まで、パンツに8本入っても文はパンツに触れなかった。）
    """
    summary, result = _summary(pipe, body, shape)
    named = {row["name"] for row in summary["darts_by_part"]}
    for part in result.finalized_parts:
        if part.dart_count:
            assert part.name_without_dart_count in named, (
                f"{body}/{shape}: {part.display_name} にダーツが入っているのに、"
                "説明に出てきません。")


@pytest.mark.parametrize("body,shape", CASES)
def test_each_part_reports_its_own_dart_count(pipe, body, shape):
    """パーツごとの本数を、表示名を切り出さずに取れること。"""
    summary, result = _summary(pipe, body, shape)
    by_id = {p["identifier"]: p["dart_count"] for p in summary["parts"]}
    for part in result.finalized_parts:
        assert by_id[part.identifier] == part.dart_count


def test_the_plain_name_does_not_carry_the_dart_suffix(pipe):
    """並べたときに「[ダーツ4本] 4本」と重ならないこと。"""
    _, result = _summary(pipe, "ウエストが細い", "タイト")
    darted = [p for p in result.finalized_parts if p.dart_count]
    assert darted
    for part in darted:
        assert "[ダーツ" not in part.name_without_dart_count
        assert part.display_name.startswith(part.name_without_dart_count)


# --- 画面側 -----------------------------------------------------------------

def _dart_note_block() -> str:
    start = INDEX.index('<div id="dart-note"')
    end = INDEX.index('<div id="compatibility-warning"', start)
    return INDEX[start:end]


def test_the_dart_note_names_no_part_by_hand():
    """ダーツ説明にパーツ名を書き戻したら落ちる。

    round64まで「身頃のウエスト/脇ダーツ、タイトスカートのウエストダーツ」と
    書いてあり、10通り中8通りで外れていた。名前は実物から来るものだけにする。
    """
    block = _dart_note_block()
    names = set(PART_TYPE_LABELS_JA.values()) | set(VARIATION_LABELS_JA.values())
    for name in sorted(names):
        if not name.strip():
            continue
        assert name not in block, (
            f"ダーツの説明に「{name}」と書かれています。"
            "この文が出る構成でそのパーツにダーツが入るとは限りません"
            "（engine/pipeline.py の darts_by_part から並べてください）。")


def test_the_dart_note_has_a_place_for_the_real_parts():
    """並べる場所と、それを埋める処理があること。"""
    assert 'id="dart-note-list"' in _dart_note_block()
    assert '"dart-note-list"' in APP_JS


def _strip_js_comments(source: str) -> str:
    """// と /* */ を落とす。

    コメントを残したまま文字列を探すと、**説明文だけで通ってしまう**。
    実際、最初に書いたときはこの関数が無く、`data.darts_by_part` を
    参照しない実装に差し替えてもテストが通った(上の注釈に
    その文字列が書いてあったため)。
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//")[0] for line in source.splitlines())


APP_JS_CODE = _strip_js_comments(APP_JS)


def _render_dart_note_body() -> str:
    start = APP_JS_CODE.index("function renderDartNote(")
    rest = APP_JS_CODE[start + 10:]
    end = rest.index("\nfunction ")
    return APP_JS_CODE[start:start + 10 + end]


def test_the_screen_builds_the_list_from_the_engine():
    """名前の出どころが darts_by_part であること（コメントを除いて見る）。"""
    body = _render_dart_note_body()
    assert "data.darts_by_part" in body
    assert "row.name" in body


def test_the_script_does_not_name_any_part_either():
    """画面側のコードにパーツ名を書き戻したら落ちる。

    HTMLから消しても、JSに書けば同じ間違いが復活する。
    """
    body = _render_dart_note_body()
    for name in sorted(set(PART_TYPE_LABELS_JA.values())
                        | set(VARIATION_LABELS_JA.values())):
        if not name.strip():
            continue
        assert name not in body, f"renderDartNote に「{name}」と書かれています。"


def test_the_screen_does_not_cut_the_name_out_of_the_display_name():
    """表示名から「[ダーツN本]」を切り出して名前を作り直していないこと。"""
    assert "[ダーツ" not in APP_JS_CODE
