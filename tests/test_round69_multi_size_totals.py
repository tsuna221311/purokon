"""round69: サイズ展開の画面に、「何枚刷るか」も「合わせて何を買うか」も無かった。

コスプレの合わせ（同じ衣装を何人ぶんか作る）のつもりで、サイズ展開を
使った。S・M・Lを選んで生成すると、画面に出るのはこれだけだった。

    サイズ S  パーツ数 7 / 布ロス率 20.3% / 幅140cm の生地を 2.0m
    サイズ M  パーツ数 7 / 布ロス率 17.3% / 幅140cm の生地を 2.0m
    サイズ L  パーツ数 7 / 布ロス率 14.2% / 幅140cm の生地を 2.0m

**サーバは全部送っていた。** 各サイズの中身は単一サイズとまったく同じ
`result.summary()`で、印刷枚数も買い物メモも入っている。画面が
描いていなかっただけである(round36が警告3種を拾ったときと同じ形で、
そのとき拾い残した物が残っていた)。

【実測】サーバが送っているのに、サイズ展開の画面が描いていなかったもの

```
    pdf_sheet_count   印刷枚数     ← 3サイズで**143枚**。コンビニの代金そのもの
    shopping_list     買い物メモ   ← 接着芯・ファスナー・収縮の注記
    assembly_steps    縫う順番
    parts             パーツ一覧
    darts_by_part     ダーツの場所
```

さらに、**全サイズを合わせた数字はどこにも無かった**。3人ぶん作る人が
知りたいのは「全部で何m買うか」「全部で何枚刷るか」である。

直したこと:
  * サイズごとの行に印刷枚数を足した(単一サイズはround53から出している)
  * `MultiSizeResult.totals()` を足し、合計を画面の上に出した

このファイルが見張るのは:

  1. 合計が、各サイズの値と食い違う
  2. 1サイズでも収まらない生地幅を「合計」に混ぜる
  3. 足し算の前提（サイズごとに別々に裁つ）を黙る
  4. 画面が、送られてきた数字を落とす
"""

import re
from pathlib import Path

import pytest

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

ROOT = Path(__file__).resolve().parents[1]
_APP_JS_RAW = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")


def _strip_js_comments(source: str) -> str:
    """// と /* */ を落とす(round65の教訓)。

    コメントを残したまま文字列を探すと、**呼び出しをコメントアウト
    しただけで通ってしまう**。round69で実際にそうなった。
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//")[0] for line in source.splitlines())


APP_JS = _strip_js_comments(_APP_JS_RAW)
INDEX = (ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")
APP_PY = (ROOT / "app.py").read_text(encoding="utf-8")

BASE = Measurements(bust=88, waist=68, hip=95, height=163,
                    sleeve_length=58, shoulder_width=39)
#: 円形スカートの大きい体型。生地幅によっては収まらないサイズが出る
#: (実測: M・Lは幅110/140に収まらず、XLは分割されるので収まる)。
WIDE = Measurements(bust=100, waist=90, hip=138, height=165,
                    sleeve_length=56, shoulder_width=40)


@pytest.fixture(scope="module")
def zipped(tmp_path_factory):
    pipe = PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r69a")))
    spec = build_garment_spec(skirt_style="flare", front_zip=True)
    return pipe.generate_multi_size(spec, BASE, ["S", "M", "L"])


@pytest.fixture(scope="module")
def oversized(tmp_path_factory):
    pipe = PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r69b")))
    spec = build_garment_spec(skirt_style="circle")
    return pipe.generate_multi_size(spec, WIDE, ["M", "L", "XL"])


# --- 1. 合計は、各サイズの値の合計である ------------------------------------

def test_the_total_sheet_count_is_the_sum_of_the_sizes(zipped):
    """印刷枚数の合計が、各サイズの合計と一致すること。"""
    totals = zipped.totals()
    expected = sum(r.summary()["pdf_sheet_count"] for r in zipped.results.values())
    assert totals["pdf_sheet_count"] == expected
    assert totals["pdf_sheet_count"] > 0


def test_the_fabric_total_at_each_width_is_the_sum_of_the_sizes(zipped):
    """生地幅ごとの合計が、各サイズの「買う長さ」の合計と一致すること。"""
    totals = zipped.totals()
    for width_text, total in totals["fabric_by_width_cm"].items():
        width = float(width_text)
        expected = 0
        for result in zipped.results.values():
            option = next(o for o in result.summary()["shopping_list"]["widths"]
                          if o["width_cm"] == width)
            expected += option["buy_length_cm"]
        assert total == expected, width


def test_the_recommended_width_is_the_shortest_total(zipped):
    """おすすめの幅が、合計がいちばん短い幅であること。"""
    totals = zipped.totals()
    by_width = {float(w): v for w, v in totals["fabric_by_width_cm"].items()}
    best = min(by_width, key=lambda w: (by_width[w], w))
    assert totals["fabric_recommended_width_cm"] == best
    assert totals["fabric_recommended_length_cm"] == by_width[best]


def test_the_interfacing_total_is_the_sum_of_the_sizes(zipped):
    totals = zipped.totals()
    expected = sum(r.summary()["shopping_list"]["interfacing_length_cm"]
                   for r in zipped.results.values())
    assert totals["interfacing_length_cm"] == expected


def test_one_zipper_per_size_with_that_size_s_opening(zipped):
    """ファスナーはサイズごとに1本で、長さもそのサイズの値であること。"""
    totals = zipped.totals()
    assert len(totals["zippers"]) == len(zipped.results)
    for entry in totals["zippers"]:
        memo = zipped.results[entry["size"]].summary()["shopping_list"]
        assert entry["opening_cm"] == memo["front_opening_cm"]
    # サイズが違えば開き寸法も違う(1つの値を配っていない)。
    assert len({e["opening_cm"] for e in totals["zippers"]}) == len(totals["zippers"])


# --- 2. 収まらない幅を混ぜない ------------------------------------------------

def test_a_width_that_one_size_cannot_use_is_left_out(oversized):
    """1サイズでも収まらない幅は、合計に出さないこと。

    出すと「その幅で全員ぶん作れる」と読める。実測では、幅110/140に
    M・Lが収まらない(XLは分割されるので収まる)。
    """
    totals = oversized.totals()
    fits_everywhere = set()
    for width in (110.0, 140.0, 150.0):
        ok = all(
            next(o for o in r.summary()["shopping_list"]["widths"]
                 if o["width_cm"] == width)["all_parts_fit"]
            for r in oversized.results.values())
        if ok:
            fits_everywhere.add(width)
    assert fits_everywhere, "この採寸ではどの幅も収まらないので、テストが空振りします"
    assert {float(w) for w in totals["fabric_by_width_cm"]} == fits_everywhere


def test_the_oversized_case_really_has_a_width_that_fails(oversized):
    """上のテストが空振りしていないこと（収まらない幅が実在する）。"""
    failures = [
        (size, o["width_cm"])
        for size, r in oversized.results.items()
        for o in r.summary()["shopping_list"]["widths"]
        if not o["all_parts_fit"]
    ]
    assert failures, "収まらない幅が1つも無いので、除外の見張りが働きません"


# --- 3. 前提を黙らない -------------------------------------------------------

def test_the_screen_says_how_the_lengths_were_added_up():
    """足し算の前提を、画面に書いてあること。

    サイズをまたいだ詰め合わせはしていない。黙ると「全部並べ直した
    いちばん短い値」と読める。
    """
    start = APP_JS.index("function renderMultiSizeTotals")
    end = APP_JS.index("\nfunction ", start + 10)
    block = APP_JS[start:end]
    assert "サイズごとに別々に裁つ前提" in block
    assert "詰め合わせ直した値ではありません" in block
    assert 'id="multi-size-totals-caveat"' in INDEX


# --- 4. 画面が落とさない -----------------------------------------------------

def test_the_api_sends_the_totals():
    """サイズ展開の応答に合計が入っていること。"""
    start = APP_PY.index("def _respond_multi_size")
    end = APP_PY.index("\ndef _respond_manual", start)
    assert '"totals": multi.totals(),' in APP_PY[start:end]


def test_the_screen_renders_the_totals():
    assert "renderMultiSizeTotals(data.totals)" in APP_JS
    assert 'id="multi-size-totals"' in INDEX
    for key in ("pdf_sheet_count", "fabric_recommended_width_cm",
                "interfacing_length_cm", "zippers"):
        assert f"totals.{key}" in APP_JS, key


def test_each_size_row_shows_its_sheet_count():
    """サイズごとの行に印刷枚数が出ていること。

    単一サイズはround53から出している。コンビニで刷る人には、これが
    そのまま代金と待ち時間になる。
    """
    start = APP_JS.index('const list = document.getElementById("multi-size-list");')
    end = APP_JS.index("\nfunction ", start)
    block = APP_JS[start:end]
    assert "result.pdf_sheet_count" in block
    assert "result.paper" in block


def test_the_screen_does_not_add_the_numbers_up_itself():
    """画面が合計を計算し直していないこと（数字の出どころを1つにする）。"""
    start = APP_JS.index("function renderMultiSizeTotals")
    end = APP_JS.index("\nfunction ", start + 10)
    block = APP_JS[start:end]
    # 足し算・畳み込みをしていない。並べるだけ。
    assert "reduce(" not in block
    assert not re.search(r"\+=", block)
