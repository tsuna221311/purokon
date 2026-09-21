"""round54: 1着を2色で作ろうとすると、配置図が使えなかった。

round53の最後に「いまのいちばん大きなコスプレ向けの穴」と自分で書いた件に
手を付けた。キャラクターの衣装は**1着が1種類の生地でできていない**——
本体の色、差し色、襟や袖口の別布と3〜5種類使うのがふつうである。

実測(白い身頃＋紺のスカート、身長160cm):

    買い物メモ : 幅140cmを181cm       ← 1種類ぶんの数字
    実際に要る : 白 幅110cmを122cm ＋ 紺 幅110cmを124cm = 246cm

数字が66cm足りないだけではない。**配置図そのものが使えない**のが本題で、
全パーツを1枚に詰めた配置では白のパーツと紺のパーツが交互に並ぶ。
その紙を白い生地の上に置いても、紺のパーツのぶんだけ穴が空く。

直した内容:
  ・パーツを生地ごとに分け、生地ごとに配置・書き出し・買い物メモを作る
  ・型紙の表紙と全ページの隅に生地の名前を印字する(50枚の紙が2つの山に
    分かれるので、1枚混ざると「白い生地にスカートを載せて裁つ」になる)
  ・「紺」「金」「黒」——いちばんよく使う色の漢字が、埋め込みフォントに
    無いため**黙って消えていた**(実測:「紺サテン」→「サテン」)。
    色と素材の常用字をフォントに入れ、それでも落ちる字は警告する
  ・生地を1種類しか使わない生成は、round53とまったく同じ出力のまま
"""

import os

import pytest

from engine.fabric_groups import (
    ASSIGNABLE_AREAS,
    DEFAULT_FABRIC_NAME,
    MAX_FABRIC_GROUPS,
    FabricGroupError,
    normalize_assignments,
    split_parts,
    uses_multiple_fabrics,
)
from engine.measurements import Measurements
from engine.pdf_export import COMMON_FABRIC_NAME_CHARS, unprintable_characters
from engine.pipeline import PatternForgePipeline, build_garment_spec


def _dress(tmp_path, assignments=None, **kwargs):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, Measurements(bust=84, waist=68, hip=92, height=160,
                            sleeve_length=54, shoulder_width=37),
        fabric_group_assignments=assignments, **kwargs)


def _page_texts(path):
    import pypdf

    return [page.extract_text() or "" for page in pypdf.PdfReader(path).pages]


# --- 1. 生地ごとに分かれること ----------------------------------------------

def test_parts_are_split_by_the_fabric_they_are_cut_from(tmp_path):
    result = _dress(tmp_path, {"bodice": "白ブロード", "sleeve": "白ブロード",
                                "skirt": "紺サテン"})
    names = [g.name for g in result.fabric_groups]
    assert names == ["白ブロード", "紺サテン"], names
    by_name = {g.name: g for g in result.fabric_groups}
    assert by_name["白ブロード"].part_labels == ["前身頃", "後身頃", "袖"]
    assert by_name["紺サテン"].part_labels == ["スカート"]
    # 分け落ちが無いこと(どのパーツも、どれか1つの生地に必ず入る)。
    assert sum(len(g.parts) for g in result.fabric_groups) == len(result.finalized_parts)


def test_each_fabric_is_laid_out_on_its_own(tmp_path):
    """生地ごとに配置し直していること。

    全パーツを1枚に詰めた配置は、2色の衣装では**どちらの生地でも使えない**。
    """
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    for group in result.fabric_groups:
        placed_types = {p.part.part_type for p in group.nesting.placed}
        own_types = {p.part_type for p in group.parts}
        assert placed_types <= own_types, (
            f"{group.name} の配置に、別の生地のパーツが混ざっています: "
            f"{placed_types - own_types}")


def test_each_fabric_gets_its_own_amount_to_buy(tmp_path):
    """必要量が生地ごとに出ること(合計しても買う単位にならない)。"""
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    lengths = {g.name: g.nesting.used_length_cm for g in result.fabric_groups}
    assert len(lengths) == 2
    assert all(length > 0 for length in lengths.values()), lengths
    # 1枚に詰めた場合より、合計は必ず長くなる(別々に並べ直すため)。
    single = _dress(tmp_path)
    assert sum(lengths.values()) > single.nesting.used_length_cm


def test_each_fabric_gets_its_own_files(tmp_path):
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    for group in result.fabric_groups:
        for fmt in ("svg", "pdf", "dxf"):
            path = group.output_files[fmt]
            assert os.path.getsize(path) > 0, (group.name, fmt)
    # 2種類目以降は、ダウンロードの鍵としても取り出せること
    # (ここに入れ忘れると「生成できているのに取りに行けない」になる)。
    assert "fabric2_pdf" in result.output_files
    assert result.output_files["fabric2_pdf"] == result.fabric_groups[1].output_files["pdf"]


def test_an_area_that_is_not_in_the_garment_does_nothing(tmp_path):
    """構成に無いパーツに名前を書いても、空の生地を作らないこと。"""
    result = _dress(tmp_path, {"pants": "黒ツイル", "collar": "金ラメ"})
    assert result.fabric_groups == [], [g.name for g in result.fabric_groups]


def test_writing_the_same_name_everywhere_is_still_one_fabric(tmp_path):
    result = _dress(tmp_path, {"bodice": "同じ生地", "sleeve": "同じ生地",
                                "skirt": "同じ生地"})
    assert result.fabric_groups == []


# --- 2. どの生地の型紙かが、紙の上で分かること ------------------------------

def test_the_cover_of_each_pdf_names_its_fabric(tmp_path):
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    for group in result.fabric_groups:
        cover = _page_texts(group.output_files["pdf"])[0]
        assert f"「{group.name}」から裁つ型紙" in cover, cover[:120]


def test_every_tile_page_names_its_fabric(tmp_path):
    """全ページに生地名が入ること。

    50枚の紙が2つの山に分かれるので、1枚混ざるだけで
    「白い生地の上にスカートの型紙を載せて裁つ」事故になる。
    表紙だけに書いても、貼り合わせる段になると見えない。
    """
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    for group in result.fabric_groups:
        tiles = [t for t in _page_texts(group.output_files["pdf"])
                 if "PatternForge" in t]
        assert tiles, group.name
        missing = [t for t in tiles if group.name not in t]
        assert not missing, f"{group.name}: {len(missing)}枚に生地名がありません"


def test_a_single_fabric_pdf_has_no_fabric_name(tmp_path):
    """1種類しか使わないときは、余計な名前を出さないこと。

    「表地」とだけ書かれた行が全ページに増えても、伝わる情報は増えない。
    """
    result = _dress(tmp_path)
    cover = _page_texts(result.output_files["pdf"])[0]
    assert cover.startswith("貼り合わせ図と記号の凡例"), cover[:60]
    assert "から裁つ型紙" not in cover


# --- 3. 生地の名前が、黙って消えないこと ------------------------------------

@pytest.mark.parametrize("name", ["紺サテン", "金ラメ", "エナメル黒", "赤別珍",
                                   "白ブロード", "本体の色", "差し色"])
def test_common_fabric_names_are_printable(name):
    """よく使う色・素材の名前が、そのまま印字できること。

    round54以前は「紺サテン」が「サテン」、「金ラメ」が「ラメ」、
    「エナメル黒」が「エナメル」になっていた——**色だけが消える**。
    どの生地の型紙かを見分けるための名前なので、色が消えるのは致命的。
    """
    assert unprintable_characters(name) == [], name


def test_the_common_characters_are_actually_in_the_font():
    """一覧に足した字が、実際にフォントに入っていること。

    一覧に書いただけでフォントを作り直し忘れると、黙って消える状態に戻る。
    """
    missing = unprintable_characters(COMMON_FABRIC_NAME_CHARS)
    assert missing == [], (
        f"フォント未収録: {''.join(missing)} / "
        "`python3 scripts/build_pattern_label_font.py` を実行してください")


def test_an_unprintable_fabric_name_is_warned_about(tmp_path):
    """それでも落ちる字があるときは、裁つ前に伝えること。"""
    result = _dress(tmp_path, {"skirt": "薔薇柄シフォン"})
    notes = [w for w in result.measurement_warnings if "生地の名前" in w]
    assert notes, result.measurement_warnings
    assert "薔" in notes[0] and "柄シフォン" in notes[0], notes[0]


def test_a_printable_fabric_name_is_not_warned_about(tmp_path):
    result = _dress(tmp_path, {"skirt": "紺サテン"})
    assert not [w for w in result.measurement_warnings if "生地の名前" in w]


# --- 4. 入力の検査 ----------------------------------------------------------

def test_an_unknown_area_is_refused():
    with pytest.raises(FabricGroupError):
        normalize_assignments({"sode": "白"})


def test_a_blank_name_is_treated_as_the_default():
    assert normalize_assignments({"skirt": "", "bodice": "   "}) == {}
    assert normalize_assignments(None) == {}


def test_a_name_that_is_too_long_is_refused():
    with pytest.raises(FabricGroupError):
        normalize_assignments({"skirt": "あ" * 21})


def test_a_name_with_newlines_is_flattened():
    assert normalize_assignments({"skirt": " 紺\n サテン "}) == {"skirt": "紺 サテン"}


def test_too_many_fabrics_are_refused():
    raw = {area.key: f"生地{i}" for i, area in enumerate(ASSIGNABLE_AREAS)}
    assert len(raw) > MAX_FABRIC_GROUPS
    with pytest.raises(FabricGroupError) as excinfo:
        normalize_assignments(raw)
    assert f"{MAX_FABRIC_GROUPS}種類まで" in str(excinfo.value)


def test_the_form_accepts_and_refuses_the_same_way(client):
    ok = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
        "fabric_skirt": "紺サテン",
    })
    assert ok.status_code == 200, ok.get_json().get("error")
    groups = ok.get_json()["fabric_groups"]
    assert [g["name"] for g in groups] == [DEFAULT_FABRIC_NAME, "紺サテン"]
    # 生成した分のリンクが、実際に取りに行けること。
    for key in ("pdf", "fabric2_pdf", "fabric2_svg"):
        assert key in ok.get_json()["download"], key
        assert client.get(ok.get_json()["download"][key]).status_code == 200, key

    ng = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
        "fabric_skirt": "あ" * 25,
    })
    assert ng.status_code == 400
    assert "20文字まで" in ng.get_json()["error"]


def test_a_single_fabric_generation_reports_no_groups(client):
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
    })
    assert response.get_json()["fabric_groups"] is None


def test_the_screen_offers_a_field_for_every_assignable_area(client):
    body = client.get("/").get_data(as_text=True)
    for area in ASSIGNABLE_AREAS:
        assert f'name="fabric_{area.key}"' in body, area.key
        assert f'for="field-fabric-{area.key}"' in body, area.key
    js = client.get("/static/app.js").get_data(as_text=True)
    assert js.count("renderFabricGroups") >= 2, "生地ごとの表を描く処理が呼ばれていません"


# --- 5. 1種類しか使わない生成が、変わっていないこと --------------------------

def test_one_fabric_keeps_the_previous_behaviour(tmp_path):
    """既定(割り当て無し)では、round53までと同じものが出ること。

    実際のバイト比較はPDFにjob_idと時刻が入るためできないので、
    「生地ごとの仕組みを一切通らない」ことと、主要な数字が
    割り当て無しの生成と一致することで見る。
    """
    plain = _dress(tmp_path)
    assert plain.fabric_groups == []
    assert plain.summary()["fabric_groups"] is None
    assert not any(k.startswith("fabric") for k in plain.output_files)

    # 「全部同じ名前」を書いても、1種類として同じ結果になること。
    same = _dress(tmp_path, {"bodice": DEFAULT_FABRIC_NAME,
                              "sleeve": DEFAULT_FABRIC_NAME,
                              "skirt": DEFAULT_FABRIC_NAME})
    assert same.fabric_groups == []
    assert same.nesting.used_length_cm == plain.nesting.used_length_cm
    assert same.nesting.fabric_width_cm == plain.nesting.fabric_width_cm
    assert same.summary()["pdf_sheet_count"] == plain.summary()["pdf_sheet_count"]


def test_splitting_helpers_agree_with_each_other(tmp_path):
    result = _dress(tmp_path)
    parts = result.finalized_parts
    assert uses_multiple_fabrics(parts, {"skirt": "紺"}) is True
    assert uses_multiple_fabrics(parts, {}) is False
    assert uses_multiple_fabrics(parts, {"pants": "黒"}) is False
    assert [g.name for g in split_parts(parts, {})] == [DEFAULT_FABRIC_NAME]
