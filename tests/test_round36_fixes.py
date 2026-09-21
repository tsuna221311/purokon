"""round36: 実際に画面から触ってみて見つけた、3つの穴。

round35で「体型を変えて総当たり」はやったので、今回は**構成と画面**を
変えて触った。パンツ・衿・カフス・ウエストバンド・プリンセス・前開きの
264通り、伸びる生地の96通りはどちらも問題0件で、幾何は健全だった。
穴は全部「出来上がった型紙を、利用者にどう伝えるか」の側にあった。

1. サイズ展開すると、大きいサイズの警告が画面から消えていた
2. カスタムパーツが縫製手順に一言も出てこなかった
3. 利用者が付けたパーツ名の漢字が、型紙から黙って消えていた
"""

import pytest

from engine.assembly import assembly_steps
from engine.measurements import Measurements
from engine.pdf_export import unprintable_characters
from engine.pipeline import (PatternForgePipeline, build_custom_panel_requests,
                              build_garment_spec)

STANDARD = Measurements(84, 68, 92, 160, 54, 37)


def _pipeline(tmp_path):
    return PatternForgePipeline(output_dir=str(tmp_path))


def _with_custom(spec, label, points=((0, 0), (40, 0), (48, 60), (0, 60))):
    reqs = build_custom_panel_requests(label, list(points), 1, False)
    return type(spec)(parts=list(spec.parts) + list(reqs),
                      princess_line=spec.princess_line)


# --- 1) サイズ展開で、大きいサイズの警告が消えていた -------------------------

def test_every_size_carries_its_own_warnings(tmp_path):
    """サイズごとの警告・注記が、APIの応答に載っていること。

    【実際に起きていたこと】画面(`renderMultiSizeResults`)は
    `result.summary()`を丸ごと受け取っていたのに、描いていたのはパーツ数と
    布ロス率だけだった。実測(バスト100/ウエスト90/ヒップ138、M・L・XL)で、
    XLだけ
      - ヒップ146cmが変形可能範囲を超え、145.6cm相当に丸められている
      - スカートが生地幅に収まらず2枚に分割されている
    という状態だったが、画面には「パーツ数 6」(M・Lは4)としか出ず、
    **なぜ増えたのかも、型紙が採寸どおりでないことも分からなかった**。
    単一サイズなら赤い箱で強調している内容である。
    サイズ展開は大きいサイズほどこれらに当たりやすいので、ここで落とすのが
    いちばん痛い。
    """
    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style="circle")
    multi = pipeline.generate_multi_size(
        spec, Measurements(100, 90, 138, 165, 56, 40), ["M", "L", "XL"])

    summaries = {size: r.summary() for size, r in multi.results.items()}
    # 前提: XLだけが実際に警告の出る状態になっていること
    assert summaries["XL"]["split_panels"] == {"skirt": 2}, summaries["XL"]["split_panels"]
    assert summaries["M"]["split_panels"] == {}

    xl = summaries["XL"]
    assert any("ヒップ" in w for w in xl["measurement_warnings"]), xl["measurement_warnings"]
    assert any("分けました" in n for n in xl["design_notes"]), xl["design_notes"]

    # 画面が読む鍵が、全サイズで必ず存在すること(欠落やNoneではない)。
    # ここが欠けると`renderMultiSizeResults`が黙って何も描かなくなる。
    for size, s in summaries.items():
        for key in ("measurement_warnings", "unplaced_warnings", "design_notes",
                     "split_panels", "compatibility_warnings", "used_length_cm",
                     "fabric_width_cm"):
            assert key in s, f"{size} に {key} が無い"
            assert s[key] is not None, f"{size} の {key} が None"


# --- 2) カスタムパーツが縫製手順に出てこなかった -----------------------------

def test_a_custom_panel_is_not_left_out_of_the_sewing_order(tmp_path):
    """カスタムパーツについて、手順が黙っていないこと。

    【実際に起きていたこと】マントを1枚足して生成すると、型紙にはマントが
    印刷されるのに、縫う順番は9工程すべて身頃・袖・スカートの話で終わり、
    **マントに一言も触れていなかった**。しかも最後が「裾を始末する」なので、
    型紙のとおり作り終えたと読めてしまう。利用者の手元には、裁ったのに
    どこにも使っていない布が残る。
    """
    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = pipeline.generate_from_selection(_with_custom(spec, "マント"), STANDARD)

    assert any(p.display_name == "マント" for p in result.finalized_parts)
    steps = result.assembly_steps()
    mentioning = [s for s in steps if "マント" in s.detail or "マント" in s.parts]
    assert mentioning, [s.title for s in steps]


def test_the_custom_panel_step_does_not_invent_an_attachment_method(tmp_path):
    """付け方を知らないことを、知らないと書いていること。

    このエンジンは、そのパーツが体のどこにどう留まるのかを一切知らない。
    首に結ぶのか肩に縫い付けるのかはパーツ次第で、もっともらしい手順を
    書けば、根拠のない指示が型紙に載る。「分からない」と書くのが正しい。
    """
    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    steps = pipeline.generate_from_selection(
        _with_custom(spec, "マント"), STANDARD).assembly_steps()
    step = next(s for s in steps if "カスタムパーツ" in s.title)
    assert "書けません" in step.detail
    # 縫い方を指示していないこと(知らないことを書かない)
    for invented in ("中表", "縫い代", "ぐし縫い", "合印を合わせて"):
        assert invented not in step.detail, f"知らないはずの指示が入っている: {invented}"


def test_a_pattern_without_custom_panels_gains_no_such_step(tmp_path):
    """カスタムパーツが無ければ、この工程は出ないこと(不要な文を足さない)。"""
    pipeline = _pipeline(tmp_path)
    result = pipeline.generate_from_selection(
        build_garment_spec(neckline="round_neck", sleeve_style="straight",
                            skirt_style="flare"), STANDARD)
    assert not any("カスタムパーツ" in s.title for s in result.assembly_steps())


def test_the_custom_panel_step_comes_last():
    """他の工程と混ざらないよう、最後に置いていること。"""
    from types import SimpleNamespace

    def fake(part_type, name):
        return SimpleNamespace(part_type=part_type, dart_count=0,
                                display_name=name, label_suffix="")

    steps = assembly_steps([fake("front_bodice", "前"), fake("back_bodice", "後"),
                             fake("custom_panel", "マント")])
    assert "カスタムパーツ" in steps[-1].title, [s.title for s in steps]


# --- 3) 利用者が付けた名前の漢字が、型紙から黙って消えていた ------------------

def test_characters_that_cannot_be_printed_are_reported():
    """印刷できない文字を、数え上げられること。"""
    # 収録済みの文字だけなら空
    assert unprintable_characters("マント") == []
    assert unprintable_characters("cape A 12") == []
    # 収録外の漢字は名指しで返る
    missing = unprintable_characters("薔薇の装甲")
    assert "薔" in missing and "薇" in missing
    assert "の" not in missing        # 収録済みの文字は混ぜない
    # 同じ文字は1回だけ
    assert unprintable_characters("薔薔薔") == ["薔"]


def test_a_custom_panel_name_that_would_lose_characters_warns(tmp_path):
    """印刷で文字が落ちる名前を付けたら、裁つ前に伝えること。

    【実際に起きていたこと】カスタムパーツに「薔薇の装甲」と名前を付けると、
    発見時点では薔・薇・装・甲がすべて埋め込みフォントの収録外で、型紙には
    **「の」とだけ印刷される**状態だった。警告はどこにも出ず、利用者は
    「の」と書かれた布を裁つことになる。

    (このあと装・甲は`SUGGESTED_CUSTOM_PANEL_KANJI`で収録したので、
     今このケースで落ちるのは薔・薇だけになり、印字は「の装甲」になる。
     テストの期待値を実態に合わせて直したのであって、**何が落ちても
     必ず名指しで開示する**という中身は変えていない。)

    全漢字を収録すればフォントが10MB超になり、A4分割PDFを配るという
    この製品の形に合わない。直せるのは「黙って落とす」ところだけである。
    """
    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        _with_custom(spec, "薔薇の装甲"), STANDARD)

    notes = [w for w in result.measurement_warnings if "印刷できない" in w]
    assert notes, result.measurement_warnings
    # 落ちる文字を名指しし、実際にどう印字されるかまで見せること
    assert "薔" in notes[0] and "薇" in notes[0]
    assert "「の装甲」" in notes[0], notes[0]
    # 収録済みの文字を「落ちる」と言わないこと
    assert "装・" not in notes[0] and "・甲" not in notes[0], notes[0]


@pytest.mark.parametrize("label", ["マント", "かたあて", "cape", "肩ひも", "翼 左"])
def test_printable_names_do_not_warn(tmp_path, label):
    """印字できる名前では、警告が出ないこと(誤検知が無いこと)。

    ここが鳴りっぱなしだと、本当に文字が落ちるときに気付けなくなる。
    """
    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(_with_custom(spec, label), STANDARD)
    assert not [w for w in result.measurement_warnings if "印刷できない" in w]


def test_the_warning_survives_a_font_rebuild(tmp_path):
    """フォントを作り直しても、この警告は「利用者入力」を見ていること。

    固定文言(`PDF_STATIC_TEXTS`・assembly.py等)は
    `scripts/build_pattern_label_font.py`が集めて収録するので、
    再ビルドすれば落ちなくなる。だが利用者が入力する名前は**何が来るか
    分からない**ので、再ビルドでは永久に解決しない。だからこの警告は
    「フォントを直し忘れた」ための仮の措置ではなく、恒久的な開示である。
    その性質を、収録され得ない文字(私用領域)で固定しておく。
    """
    private_use = ""       # 私用領域。どうビルドしても入らない
    assert unprintable_characters(private_use) == list(private_use)

    pipeline = _pipeline(tmp_path)
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None)
    result = pipeline.generate_from_selection(
        _with_custom(spec, f"マント{private_use}"), STANDARD)
    assert [w for w in result.measurement_warnings if "印刷できない" in w]


def test_the_examples_this_product_suggests_are_printable():
    """製品自身が例として勧めている名前は、必ず型紙に印字できること。

    【なぜ特別扱いするか】カスタムパーツ名は自由入力なので、全部を先回りして
    フォントに収録することはできない(全漢字を入れるとフォントが10MB超になり、
    A4分割PDFを配るこの製品の形に合わない)。だから一般には
    `_unprintable_label_warnings`が「印字されません」と開示する。

    ただし、**製品が「例: マント・翼・肩当て・装甲プレート」と勧めておいて、
    その通り入力すると文字が消える**のは筋が通らない。round36で実測したところ、
    画面が挙げている6語のうちマント以外の5語すべてで文字が落ちていた
    (翼→空、装甲プレート→「プレート」、肩当て→「肩て」、小道具→「小」)。
    画面の例を増やしたら、`SUGGESTED_CUSTOM_PANEL_KANJI`にも足すこと——
    このテストがそれを忘れさせない。
    """
    for example in ("マント", "翼", "装甲プレート", "肩当て", "胸当て", "小道具"):
        assert unprintable_characters(example) == [], example


def test_the_suggested_examples_actually_appear_in_the_ui():
    """上のテストが見ている例が、画面の文言と食い違っていないこと。

    画面の例だけ増やしてテストを更新しなければ、テストは通るのに
    文字が落ちる——それでは意味が無いので、実際のテンプレートを読む。
    """
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent
            / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    for example in ("マント", "翼", "装甲プレート", "肩当て"):
        assert example in html, f"画面に例 {example} が見当たらない"


def test_every_name_the_engine_itself_generates_is_printable(tmp_path):
    """エンジンが自分で作るパーツ名は、必ず型紙に印字できること。

    【なぜ分けて考えるか】カスタムパーツの名前は利用者の自由入力なので、
    落ちる文字は開示するしかない。だが**エンジンが自分で組み立てた名前**が
    化けるのは、利用者にはどうしようもない——直すべきは開示ではなく収録である。

    実測(round36)で実際に踏んだ: カスタムパーツで「左右反転パーツも作る」を
    選ぶと、2枚目のラベルが`f"{label}(反転)"`になる。この「反」がどの収集
    対象(part_names/cutting/assembly/PDF_STATIC_TEXTS)にも入っておらず、
    型紙には「翼 左(転)」と印字されていた。

    ここでは、実際に生成しうるパーツ名を構成違いで集めて、1文字も落ちない
    ことを確かめる。名前の組み立て方を変えたときに、ここが鳴る。
    """
    pipeline = _pipeline(tmp_path)
    specs = [
        build_garment_spec(neckline="round_neck", sleeve_style="straight",
                            skirt_style="flare", include_collar=True,
                            collar_style="shirt_collar", include_cuffs=True,
                            cuffs_style="wide", include_waistband=True,
                            waistband_style="wide"),
        build_garment_spec(neckline="v_neck", sleeve_style="puff",
                            skirt_style=None, include_pants=True,
                            pants_style="wide"),
        build_garment_spec(neckline="square_neck", sleeve_style="bell",
                            skirt_style="tight", princess_line=True),
        build_garment_spec(neckline="boat_neck", sleeve_style=None,
                            skirt_style="circle", front_zip=True),
    ]
    # 左右反転を含むカスタムパーツ(ラベル自体は印字できる名前にしておき、
    # エンジンが付け足す部分だけを見る)
    reqs = build_custom_panel_requests("翼", [(0, 0), (40, 0), (48, 60), (0, 60)],
                                        1, True)
    specs.append(type(specs[0])(parts=list(specs[0].parts) + list(reqs),
                                 princess_line=specs[0].princess_line))

    bad = []
    for spec in specs:
        result = pipeline.generate_from_selection(spec, STANDARD)
        for part in result.finalized_parts:
            missing = unprintable_characters(part.display_name)
            if missing:
                bad.append((part.display_name, missing))
    assert not bad, bad
