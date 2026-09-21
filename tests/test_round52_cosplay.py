"""round52: コスプレイヤーとして使ってみて見つかったもの。

「キャラクターの衣装を作る」つもりで通しで触った。原型からの服づくりと
違うのは、**寸法が体ではなく絵で決まっている**ことである。膝上・膝下・
くるぶし丈・床に着く丈——シルエットが丈そのもので、身長に比例させた丈では
別のキャラクターになる。

見つかったもの:

  1. **丈を指定する手段が、利用者側に無かった。**
     エンジンの `design_length_overrides` はround39から存在し
     `engine/stash.py`(手持ち生地に収める経路)が使っていた。つまり
     **動く機能が、画面からもAPIからも触れないまま7ラウンド置かれていた**。
     実測: 身長160cmでスカート高さ62.0cm固定。45cmのミニも、
     100cmのロングも作れなかった。

  2. **カスタムパーツに、黙って縫い代が付いていた。**
     この機能の案内文は「マント・翼・**EVAフォーム装甲プレート**」と、
     **縫わない素材を名指しで勧めている**。ところが輪郭には他のパーツと
     同じ縫い代が足され、そのことはどこにも書かれていなかった。
     実測: 30×40cmの板が、裁断線32×42cmで出ていた。フォームや樹脂板は
     線の上で切るので、黙って2cm大きい型紙は間違いのもとになる。

このファイルのテストは、1件ずつ**手当てを元に戻すと落ちること**を
確認してある(round45以降の手順)。
"""

import json
import math

import pytest

import app as app_module
from engine.illustration_fit import SKIRT_LENGTH_RANGE_CM


BASE = {
    "bust": "84", "waist": "68", "hip": "92", "height": "160",
    "sleeve_length": "54", "shoulder_width": "37",
}


def _manual(client, **extra):
    data = dict(BASE, mode="manual", neckline="round_neck",
                sleeve_style="straight", skirt_style="flare")
    data.update(extra)
    return client.post("/api/generate", data=data)


# --- 1. 丈を指定できること --------------------------------------------------

def _generate(tmp_path, custom_panel_requests=None, **extra):
    """エンジンを直接呼ぶ(出力ファイルのパースを挟まずに寸法を見るため)。

    フォーム解析(HTTP層)と型紙の寸法(エンジン)は別々のテストで見る。
    """
    from engine.pipeline import (
        PatternForgePipeline, build_garment_spec, build_custom_panel_requests,
    )
    from engine.measurements import Measurements

    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    if custom_panel_requests:
        spec.parts.extend(custom_panel_requests)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    return pipeline.generate_from_selection(
        spec,
        Measurements(bust=84, waist=68, hip=92, height=160,
                     sleeve_length=54, shoulder_width=37),
        skip_export=True,
        **extra,
    )


def _input_tag(body: str, field_name: str) -> str:
    """`name="..."`を含む`<input ...>`タグ1つ分だけを切り出す。

    ページ全体を対象に`'min="20"' in body`のように見ると、**別の欄**の
    属性に当たって通ってしまう(round52で実際にそうなった)。
    """
    import re
    match = re.search(r"<input\b[^>]*\bname=\"%s\"[^>]*>" % re.escape(field_name), body)
    assert match, f'name="{field_name}" の入力欄がありません'
    return match.group(0)


def _part_height_cm(result, part_type):
    parts = [p for p in result.finalized_parts if p.part_type == part_type]
    assert parts, f"{part_type} のパーツがありません"
    ys = [y for p in parts for (_x, y) in p.cut_line]
    return max(ys) - min(ys)


def test_the_skirt_length_can_actually_be_set(tmp_path):
    """指定した丈が、型紙の寸法として現れること。

    これが無いと、キャラクターの丈(膝上・くるぶし・床に着く)に
    合わせる方法が一切無い。round52より前は身長からの比例だけだった。
    """
    default_h = _part_height_cm(_generate(tmp_path), "skirt")
    short_h = _part_height_cm(
        _generate(tmp_path, design_length_overrides={"skirt": 45.0}), "skirt")
    long_h = _part_height_cm(
        _generate(tmp_path, design_length_overrides={"skirt": 100.0}), "skirt")

    assert short_h < default_h < long_h, (short_h, default_h, long_h)
    # 指定は**出来上がり**の丈。裁断線には上下の縫い代が乗るので、
    # 「指定値以上・指定値+縫い代4cm以内」に収まることを見る。
    assert 45.0 <= short_h <= 45.0 + 4.0, short_h
    assert 100.0 <= long_h <= 100.0 + 4.0, long_h


def test_the_chosen_length_is_disclosed_as_a_note(tmp_path):
    """身長からの比例ではないことを、出力に書いてあること。

    黙って指定どおりにすると、「身長から出た丈」だと思ったまま
    裁ってしまう。どちらで決まった寸法なのかは型紙に書く。
    """
    result = _generate(tmp_path, design_length_overrides={"skirt": 45.0})
    notes = "\n".join(result.design_notes)
    assert "45cm" in notes, notes
    assert "身長からの比例ではありません" in notes, notes


def test_the_note_is_not_emitted_when_nothing_was_overridden(tmp_path):
    result = _generate(tmp_path)
    assert not any("身長からの比例ではありません" in n for n in result.design_notes)


def test_the_back_piece_follows_the_front_length(tmp_path):
    """前後で丈が食い違わないこと(脇線が合わないと縫えない)。"""
    result = _generate(tmp_path, design_length_overrides={"skirt": 50.0})
    heights = {p.label_suffix: max(y for _x, y in p.cut_line) - min(y for _x, y in p.cut_line)
               for p in result.finalized_parts if p.part_type == "skirt"}
    assert len(set(round(h, 3) for h in heights.values())) == 1, heights


# --- 2. 入力欄として受け取れること(HTTP層) ---------------------------------

def test_the_form_accepts_a_skirt_length(client):
    response = _manual(client, length_skirt="45")
    assert response.status_code == 200, response.get_json().get("error")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "45cm" in notes, notes


def test_the_form_accepts_a_trouser_length(client):
    """パンツ丈の欄は、前後どちらのパーツにも効くこと。

    前パンツだけ短くして後ろが元のままだと、脇線が合わず縫えない。
    """
    lengths = app_module._parse_design_lengths({"length_front_pants": "88"})
    assert lengths == {"front_pants": 88.0, "back_pants": 88.0}, lengths


def test_a_blank_length_changes_nothing(client):
    """空欄は「指定なし」であること(0cmでも400でもない)。"""
    assert app_module._parse_design_lengths({"length_skirt": ""}) == {}
    assert app_module._parse_design_lengths({"length_skirt": "   "}) == {}
    assert app_module._parse_design_lengths({}) == {}


@pytest.mark.parametrize("value", ["5", "500", "0", "-40"])
def test_an_out_of_range_length_is_refused_with_the_range(client, value):
    response = _manual(client, length_skirt=value)
    assert response.status_code == 400
    error = response.get_json()["error"]
    lo, hi = SKIRT_LENGTH_RANGE_CM
    assert f"{lo:g}〜{hi:g}cm" in error, error
    assert "スカート丈" in error, error


def test_a_non_numeric_length_is_refused_in_japanese(client):
    response = _manual(client, length_skirt="ひざ下")
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "数値で入力してください" in error, error
    # 何を入れたのかを見せる(「ひざ下」と書いた本人に伝わるように)。
    assert "ひざ下" in error, error


def test_the_range_shown_on_screen_comes_from_the_engine(client):
    """画面のmin/maxを、エンジンと同じ定数から出していること。

    画面とエンジンで別々に数字を書くと、片方を直したときに
    「入力はできるのに400になる」欄ができる。
    """
    body = client.get("/").get_data(as_text=True)
    lo, hi = SKIRT_LENGTH_RANGE_CM
    # **その入力欄の**min/maxを見る。ページのどこかに"20"があること、
    # では弱すぎる(最初そう書いていて、スカート欄だけ15〜200に
    # 焼き付けてもパンツ欄の20に当たって通った)。
    for field_name in ("length_skirt", "length_front_pants"):
        tag = _input_tag(body, field_name)
        assert f'min="{lo:g}"' in tag, (field_name, tag)
        assert f'max="{hi:g}"' in tag, (field_name, tag)


def test_the_length_fields_are_labelled(client):
    """入力欄にラベルが結び付いていること(スクリーンリーダー/タップ領域)。"""
    body = client.get("/").get_data(as_text=True)
    for field_id in ("field-length-skirt", "field-length-pants"):
        assert f'for="{field_id}"' in body, field_id
        assert f'id="{field_id}"' in body, field_id


# --- 3. イラストモードでも指定が優先されること ------------------------------

def test_the_typed_length_wins_over_the_illustration(client):
    """絵から読み取った丈より、入力した丈を優先すること。

    絵は縮尺が無いので丈は推定でしかない。実際に着る人の寸法で
    決めた方が確実で、画面にもそう書いてある。
    """
    import io
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (460, 560), (240, 560)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    data = dict(BASE, mode="illustration", length_skirt="70")
    data["illustration"] = (io.BytesIO(buffer.getvalue()), "front.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "70cm" in notes, notes
    assert "身長からの比例ではありません" in notes, notes


# --- 4. カスタムパーツの縫い代を開示すること --------------------------------

def _plate_panel(width_cm=30.0, height_cm=40.0):
    """30×40cmの「装甲プレート」1枚。校正はreference_cmで与える。"""
    return json.dumps([{
        "label": "装甲プレート",
        "points": [[0, 0], [width_cm, 0], [width_cm, height_cm], [0, height_cm]],
        "ref_point_a": [0, 0], "ref_point_b": [width_cm, 0],
        "reference_cm": width_cm,
        "quantity": 1, "mirror": False,
    }])


def test_the_seam_allowance_on_a_custom_panel_is_disclosed(client):
    """縫わない素材を名指しで勧めている以上、縫い代が付くことを言うこと。

    実測: 30×40cmの板が、裁断線32×42cmで出ていた。
    EVAフォームや樹脂板は線の上で切るので、黙って2cm大きい型紙を
    渡すと、そのまま2cm大きい装甲ができあがる。
    """
    response = _manual(client, custom_panels_json=_plate_panel(),
                       seam_allowance_cm="1.0")
    assert response.status_code == 200, response.get_json().get("error")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "カスタムパーツ" in notes and "縫い代" in notes, notes
    assert "1cm" in notes, notes
    # 「どうすればよいか」まで書く(設定を0にする / 単独で作り直す)。
    assert "0" in notes and "出来上がり線" in notes, notes


def test_the_disclosure_names_no_section_number(client):
    """案内に画面の見出し番号(⑨など)を焼き付けないこと。

    見出しの番号は入力モードによって振り直されるうえ、この文は**PDFに
    印刷される**。紙の上で「⑨」と言われても、その番号は画面にしかない。
    round49で同じ間違いをして直したので、テストで固定する。
    """
    response = _manual(client, custom_panels_json=_plate_panel(),
                       seam_allowance_cm="1.0")
    notes = "\n".join(response.get_json()["design_notes"])
    assert not any(ch in notes for ch in "①②③④⑤⑥⑦⑧⑨⑩"), notes


def test_no_disclosure_when_the_seam_allowance_is_already_zero(client):
    """縫い代0で作ったなら、この注意書きは要らないこと。

    出るべきでない場面で出る文は、読み飛ばす癖をつけさせる。
    """
    response = _manual(client, custom_panels_json=_plate_panel(),
                       seam_allowance_cm="0")
    assert response.status_code == 200, response.get_json().get("error")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "カスタムパーツの裁断線には" not in notes, notes


def test_the_v1_api_also_applies_the_length(client):
    """公開API(/api/v1/generate)でも丈が効くこと。

    このエンドポイントのdocstringは「`/api/generate`と同じフォーム
    フィールドを受け付ける」と約束している。round41に**読み取った値を
    1つも渡していなかった**実バグが見つかっているのが、まさにこの呼び出し
    なので、新しい項目を足したら毎回ここも見る
    (実際、手動・イラストの2経路だけ壊して確かめたときは素通りした)。
    """
    import re
    client.post("/signup", data={"email": "length-api@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    created = client.post("/account/api-keys", data={"name": "丈テスト"},
                          follow_redirects=True).get_data(as_text=True)
    match = re.search(r"(pf_live_[A-Za-z0-9_\-]+)", created)
    assert match, "APIキーが発行されていません"

    data = dict(BASE, neckline="round_neck", sleeve_style="straight",
                skirt_style="flare", length_skirt="45")
    response = client.post("/api/v1/generate", data=data,
                           headers={"Authorization": f"Bearer {match.group(1)}"})
    assert response.status_code == 200, response.get_json().get("error")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "45cm" in notes, notes


# --- 5. 縫い代0を指定できること ---------------------------------------------
#
# 上の注意書きが「縫い代の設定を0にしてください」と案内しているのに、
# **画面とAPIは0を弾いていた**(下限0.3cm)。その下限は「細すぎてミシンで
# 扱えない」という**縫う前提**の根拠で、フォーム・樹脂板には当てはまらない。
# エンジンは0を正しく扱えていた(実測: 30×40cmの板が裁断線30.0×40.0cm)。

def test_zero_seam_allowance_is_accepted(client):
    """0を指定できること。自分の案内どおりに操作できるようにする。"""
    response = _manual(client, custom_panels_json=_plate_panel(),
                       seam_allowance_cm="0")
    assert response.status_code == 200, response.get_json().get("error")


def test_zero_seam_allowance_actually_removes_the_allowance(tmp_path):
    """0のとき、裁断線が描いた輪郭そのものになること。"""
    from engine.pipeline import build_custom_panel_requests, CUSTOM_PANEL_PART_TYPE

    result = _generate(
        tmp_path,
        custom_panel_requests=build_custom_panel_requests(
            "装甲プレート", [(0.0, 0.0), (30.0, 0.0), (30.0, 40.0), (0.0, 40.0)],
            quantity=1, mirror=False),
        seam_allowance_cm=0.0)
    plate = [p for p in result.finalized_parts
             if p.part_type == CUSTOM_PANEL_PART_TYPE][0]
    xs = [x for x, _y in plate.cut_line]
    ys = [y for _x, y in plate.cut_line]
    assert math.isclose(max(xs) - min(xs), 30.0, abs_tol=0.05)
    assert math.isclose(max(ys) - min(ys), 40.0, abs_tol=0.05)


@pytest.mark.parametrize("value", ["0.1", "0.2", "-1", "5"])
def test_a_too_thin_seam_allowance_is_still_refused(client, value):
    """0と下限の間は、これまでどおり弾くこと。

    0.1cmは「縫わない」という意思表示ではなく、縫うつもりでの入力ミス。
    0を通したついでに全部通してしまうと、縫えない型紙が黙って出る。
    """
    response = _manual(client, seam_allowance_cm=value)
    assert response.status_code == 400, value
    assert "縫い代は" in response.get_json()["error"]


def test_the_refusal_mentions_that_zero_is_available(client):
    """弾くときに、0という出口があることを書くこと。"""
    response = _manual(client, seam_allowance_cm="0.1")
    assert "0を指定できます" in response.get_json()["error"]


def test_sewing_at_zero_seam_allowance_is_disclosed(tmp_path):
    """縫うパーツが0で出たら、そのことを言うこと。

    0を通せるようにした副作用で、身頃や袖まで0で出せてしまう。
    縫い代の無い型紙で布を裁つと、縫った分だけ小さい服になる——
    裁ってからでは戻せない。
    """
    result = _generate(tmp_path, seam_allowance_cm=0.0)
    notes = "\n".join(result.design_notes)
    assert "縫い代0で出力しました" in notes, notes
    assert "小さく仕上がります" in notes, notes


def test_no_sewing_warning_when_the_seam_allowance_is_normal(tmp_path):
    result = _generate(tmp_path, seam_allowance_cm=1.0)
    assert not any("縫い代0で出力しました" in n for n in result.design_notes)


def test_the_screen_offers_zero_and_says_why(client):
    """画面のmin属性と説明が、0を通す実装と揃っていること。"""
    body = client.get("/").get_data(as_text=True)
    tag = _input_tag(body, "seam_allowance_cm")
    assert f'min="{app_module.SEAM_ALLOWANCE_NONE_CM:g}"' in tag, tag
    assert f'max="{app_module.MAX_SEAM_ALLOWANCE_CM:g}"' in tag, tag
    assert "線の上で切る" in body, "0を指定してよい場面が説明されていません"


def test_no_disclosure_without_custom_panels(client):
    response = _manual(client, seam_allowance_cm="1.0")
    notes = "\n".join(response.get_json()["design_notes"])
    assert "カスタムパーツの裁断線には" not in notes, notes


def test_the_measured_gap_is_what_the_note_claims(tmp_path):
    """注意書きの中身が実態と合っていること(四方に縫い代が付く)。

    「1cmが四方に付く」と書いた以上、30×40cmの板は32×42cmで出るはず。
    **これがround52で実測した現象そのもの**で、文だけ直して実装がずれたら
    こちらが先に落ちる。
    """
    from engine.pipeline import build_custom_panel_requests, CUSTOM_PANEL_PART_TYPE

    requests = build_custom_panel_requests(
        "装甲プレート", [(0.0, 0.0), (30.0, 0.0), (30.0, 40.0), (0.0, 40.0)],
        quantity=1, mirror=False)
    result = _generate(tmp_path, custom_panel_requests=requests,
                       seam_allowance_cm=1.0)
    plates = [p for p in result.finalized_parts
              if p.part_type == CUSTOM_PANEL_PART_TYPE]
    assert plates, [p.part_type for p in result.finalized_parts]
    plate = plates[0]

    def span(points):
        xs = [x for x, _y in points]
        ys = [y for _x, y in points]
        return max(xs) - min(xs), max(ys) - min(ys)

    stitch_w, stitch_h = span(plate.stitch_line)
    cut_w, cut_h = span(plate.cut_line)
    # 出来上がり線は描いたとおり。
    assert math.isclose(stitch_w, 30.0, abs_tol=0.1), stitch_w
    assert math.isclose(stitch_h, 40.0, abs_tol=0.1), stitch_h
    # 裁断線は四方に1cmずつ = 各辺+2cm。
    assert math.isclose(cut_w, 32.0, abs_tol=0.1), cut_w
    assert math.isclose(cut_h, 42.0, abs_tol=0.1), cut_h
