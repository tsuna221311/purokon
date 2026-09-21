"""round57: 「正直な限界」に書いたまま残していたものを、順につぶす。

このファイルは前半5件ぶん。

  1. **袖丈・着丈を指定できるようにした。** round52は「袖ぐりと連動するので
     同じやり方では縫い合わせ長さが崩れる」として見送っていた。テンプレートが
     `data-fit-y`("neck/underarm/waist/hem"、袖は"cap/underarm/hem")を
     持っているので、**袖ぐりより下だけ**を伸縮させれば壊さずに当てられる。
     実測: 袖丈30cm/70cm、着丈40cm/80cmのいずれでも
     `check_seam_compatibility`の不一致は0件のまま。
  2. **白紙の面を印刷するかどうかを選べるようにした**(round53で省くように
     したとき、選ぶ余地を作っていなかった)。
  3. **再生成で何が復元されたかを画面に出すようにした**(round55で中身は
     合うようになったが、画面の見え方は設定が落ちていた頃と同じだった)。
  4. **手持ち生地の寸法を生地ごとに入れられるようにした**(round55で判定は
     生地ごとになったのに、寸法は1枚ぶんしか受け取れなかった)。
  5. **イラストから作ったものを再生成できるようにした。** 画像は今までどおり
     保存しない——作り直すのに要るのは画像ではなく、**画像から決まった結果**
     (パーツ構成と丈)だからである。

  おまけ(5を直す途中で見つけた実害): **イラストモードは、裏地・補正・
  一方方向の生地・収縮率・柄のリピート・原型の6つを受け取りながら
  エンジンへ渡していなかった。** 画面に欄があり、値の検査まで通るのに
  効かない——round55で手動側を直したのとまったく同じ取り落としである。
  実測: 裏地ありで生成しても、裏地の型紙が出なかった。
"""

import inspect
import json
import re

import pytest

import app as app_module
from engine.compatibility import check_seam_compatibility
from engine.measurements import Measurements
from engine.pdf_export import printed_tile_cells
from engine.pipeline import PatternForgePipeline, build_garment_spec


MEAS = Measurements(bust=84, waist=68, hip=92, height=160,
                    sleeve_length=54, shoulder_width=37)
FORM = {"bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare"}


def _build(tmp_path, **kwargs):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS, skip_export=True, **kwargs)


def _height_of(result, part_type):
    parts = [p for p in result.finalized_parts if p.part_type == part_type]
    assert parts, part_type
    ys = [y for p in parts for _x, y in p.stitch_line]
    return max(ys) - min(ys)


# --- 1. 袖丈・着丈 ----------------------------------------------------------

@pytest.mark.parametrize("length", [30.0, 45.0, 70.0])
def test_the_sleeve_length_can_be_set_exactly(tmp_path, length):
    result = _build(tmp_path, design_length_overrides={"sleeve": length})
    assert abs(_height_of(result, "sleeve") - length) < 0.2


@pytest.mark.parametrize("length", [40.0, 60.0, 80.0])
def test_the_bodice_length_can_be_set(tmp_path, length):
    """後身頃は指定どおり。前身頃は胸のダーツぶんだけ紙の上で長くなる。"""
    result = _build(tmp_path, design_length_overrides={"front_bodice": length,
                                                        "back_bodice": length})
    assert abs(_height_of(result, "back_bodice") - length) < 0.2
    assert _height_of(result, "front_bodice") >= length


@pytest.mark.parametrize("overrides", [
    {"sleeve": 30.0}, {"sleeve": 70.0},
    {"front_bodice": 40.0, "back_bodice": 40.0},
    {"front_bodice": 80.0, "back_bodice": 80.0},
])
def test_changing_the_length_never_breaks_the_seams(tmp_path, overrides):
    """**これが本題**。丈を変えても、袖山と袖ぐりが合ったままであること。

    パーツ全体を縦に縮めると袖山も縮み、袖ぐりより短くなって袖が付かない。
    round52が袖丈・着丈を見送った理由がこれで、だからこそ丈を変えた状態で
    縫い合わせ長さを見る。
    """
    result = _build(tmp_path, design_length_overrides=overrides)
    issues = check_seam_compatibility(result.finalized_parts)
    assert issues == [], [str(i) for i in issues]


def test_the_armhole_does_not_move_when_the_length_changes(tmp_path):
    """袖ぐりより上は、丈を変えても1mmも動かないこと。"""
    base = _build(tmp_path)
    short = _build(tmp_path, design_length_overrides={"sleeve": 30.0})
    def cap_width(result):
        part = [p for p in result.finalized_parts if p.part_type == "sleeve"][0]
        xs = [x for x, _y in part.stitch_line]
        return max(xs) - min(xs)
    assert abs(cap_width(base) - cap_width(short)) < 0.05, "袖幅が変わっています"


def test_a_length_that_would_eat_the_armhole_is_refused_and_disclosed(tmp_path):
    """短すぎる指定は当てず、**そう言う**こと。黙って無視しない。"""
    result = _build(tmp_path, design_length_overrides={"front_bodice": 20.0,
                                                        "back_bodice": 20.0})
    notes = "\n".join(result.design_notes)
    assert "できませんでした" in notes, notes
    assert "指定どおり20cm" not in notes, "当てていないのに「指定どおり」と書いています"


def test_the_form_accepts_the_new_length_fields(client):
    lengths = app_module._parse_design_lengths(
        {"length_sleeve": "30", "length_front_bodice": "50"})
    assert lengths == {"sleeve": 30.0, "front_bodice": 50.0, "back_bodice": 50.0}
    body = client.get("/").get_data(as_text=True)
    for name in ("length_sleeve", "length_front_bodice"):
        assert f'name="{name}"' in body, name


# --- 2. 白紙の面を印刷するかどうか ------------------------------------------

def test_empty_tiles_can_be_printed_on_request(tmp_path):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    skipped = pipeline.generate_from_selection(spec, MEAS)
    full = pipeline.generate_from_selection(spec, MEAS, include_empty_tiles=True)

    rows, cols, _cells = printed_tile_cells(skipped.nesting)
    assert full.summary()["pdf_sheet_count"] == rows * cols
    assert skipped.summary()["pdf_sheet_count"] < rows * cols

    # どちらも、画面に出す枚数とPDFの中身が一致すること。
    import pypdf
    for result in (skipped, full):
        tiles = [p for p in pypdf.PdfReader(result.output_files["pdf"]).pages
                 if "PatternForge" in (p.extract_text() or "")]
        assert result.summary()["pdf_sheet_count"] == len(tiles)


def test_the_screen_offers_the_empty_tile_option(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="include_empty_tiles"' in body
    response = client.post("/api/generate", data=dict(FORM, include_empty_tiles="on"))
    assert response.status_code == 200, response.get_json().get("error")
    rows, cols, _ = printed_tile_cells(
        PatternForgePipeline(output_dir=str(app_module.OUTPUT_DIR))
        .generate_from_selection(
            build_garment_spec(neckline="round_neck", sleeve_style="straight",
                                skirt_style="flare"), MEAS, skip_export=True).nesting)
    assert response.get_json()["pdf_sheet_count"] == rows * cols


# --- 3. 再生成で何が復元されたかを見せる ------------------------------------

def test_the_regeneration_message_lists_what_was_restored():
    described = app_module._describe_restored_settings({
        "lining": True,
        "fabric_group_assignments": {"skirt": "紺サテン"},
        "design_length_overrides": {"front_bodice": 50.0, "back_bodice": 50.0},
        "one_way_fabric": True,
    })
    assert "裏地あり" in described
    assert "紺サテン" in described
    assert "50cm" in described
    assert "一方方向" in described
    # 前後で同じ値は1回だけ書く。
    assert described.count("50cm") == 1, described


def test_the_regeneration_screen_actually_shows_it(client):
    """**画面に出ている**こと。関数があるだけでは意味がない。

    最初この一覧を作る関数だけを見ていて、呼び出しを消しても通った。
    """
    client.post("/signup", data={"email": "show-restored@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    first = client.post("/api/generate", data=dict(
        FORM, lining="on", fabric_skirt="紺サテン")).get_json()
    response = client.post(f"/account/jobs/{first['job_id']}/regenerate",
                           follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "引き継いだ設定" in body, "何が復元されたかが画面に出ていません"
    assert "裏地あり" in body and "紺サテン" in body, body[:300]


def test_the_message_says_so_when_nothing_optional_was_used():
    described = app_module._describe_restored_settings({"lining": False})
    assert "既定のまま" in described


# --- 4. 手持ち生地を生地ごとに ----------------------------------------------

def test_the_stash_can_be_given_per_fabric(client):
    response = client.post("/api/generate", data=dict(
        FORM, fabric_skirt="紺サテン",
        stash_width_cm="110", stash_length_cm="300",
        stash_fabric_name=["表地", "紺サテン"],
        stash_fabric_width_cm=["110", "110"],
        stash_fabric_length_cm=["300", "100"]))
    assert response.status_code == 200, response.get_json().get("error")
    by_fabric = {v["fabric_name"]: v for v in response.get_json()["stash_verdicts_by_fabric"]}
    assert by_fabric["表地"]["have_length_cm"] == 300.0
    assert by_fabric["紺サテン"]["have_length_cm"] == 100.0
    assert by_fabric["表地"]["fits"] is True
    assert by_fabric["紺サテン"]["fits"] is False


def test_a_fabric_without_its_own_size_falls_back_to_the_single_one(client):
    response = client.post("/api/generate", data=dict(
        FORM, fabric_skirt="紺サテン",
        stash_width_cm="110", stash_length_cm="300",
        stash_fabric_name=["紺サテン"],
        stash_fabric_width_cm=["110"],
        stash_fabric_length_cm=["100"]))
    assert response.status_code == 200, response.get_json().get("error")
    by_fabric = {v["fabric_name"]: v for v in response.get_json()["stash_verdicts_by_fabric"]}
    assert by_fabric["表地"]["have_length_cm"] == 300.0, "未入力の生地は共通の寸法で判定する"
    assert by_fabric["紺サテン"]["have_length_cm"] == 100.0


def test_half_filled_per_fabric_stash_is_refused(client):
    response = client.post("/api/generate", data=dict(
        FORM, fabric_skirt="紺サテン",
        stash_fabric_name=["紺サテン"],
        stash_fabric_width_cm=["110"],
        stash_fabric_length_cm=[""]))
    assert response.status_code == 400
    assert "幅と長さの両方" in response.get_json()["error"]


def test_the_screen_builds_a_row_per_fabric(client):
    body = client.get("/").get_data(as_text=True)
    assert 'id="stash-per-fabric"' in body
    js = client.get("/static/app.js").get_data(as_text=True)
    assert js.count("refreshStashPerFabricRows") >= 2, "行を作る処理が呼ばれていません"
    assert "stash_fabric_name" in js


# --- 5. イラストから作ったものの再生成 --------------------------------------

def test_illustration_mode_accepts_every_setting_the_form_reads():
    """イラストモードが、画面にある設定を**全部受け取れる**こと。

    round55で手動側を直したのと同じ取り落としが、こちらに残っていた。
    裏地・補正・一方方向の生地・収縮率・柄のリピート・原型の6つが、
    受け取りながらエンジンへ渡っていなかった(裏地ありで生成しても
    裏地の型紙が出なかった)。
    """
    manual = set(inspect.signature(
        PatternForgePipeline.generate_from_selection).parameters)
    illustration = set(inspect.signature(
        PatternForgePipeline.generate_from_illustration).parameters)
    # 手動にしか無くて当然のもの(イラストが決めるもの/入力そのもの)。
    ONLY_MANUAL = {"garment_spec", "skip_export"}
    missing = sorted(manual - illustration - ONLY_MANUAL)
    assert not missing, (
        f"イラストモードが受け取れない設定があります: {missing}")


def test_illustration_mode_actually_applies_the_lining(tmp_path):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (460, 560), (240, 560)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_illustration(
        image, MEAS, lining=True)
    assert result.lining_parts, "イラストモードで裏地が出ていません"


def test_an_illustration_job_can_be_regenerated(client):
    """イラストから作ったものに、再生成の道があること。

    画像は保存しない。保存するのは**画像から決まった結果**(パーツ構成と丈)
    なので、読み取りをやり直さずに同じ型紙が出る。
    """
    import io

    from PIL import Image, ImageDraw

    client.post("/signup", data={"email": "ill-regen@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (460, 560), (240, 560)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    data = dict(FORM, mode="illustration", lining="on")
    data["illustration"] = (io.BytesIO(buffer.getvalue()), "front.png")
    first = client.post("/api/generate", data=data, content_type="multipart/form-data")
    assert first.status_code == 200, first.get_json().get("error")
    job_id = first.get_json()["job_id"]

    with app_module.db._connect() as conn:
        row = conn.execute("SELECT spec_json FROM jobs WHERE job_id = ?",
                            (job_id,)).fetchone()
    assert row and row[0], "イラストの生成に、作り直すための記録がありません"
    stored = json.loads(row[0])
    assert stored["mode"] == "illustration_replay"
    assert stored["parts"], "読み取ったパーツ構成が残っていません"
    # 画像そのものは保存しないこと(残すのは読み取った結果だけ)。
    assert "image" not in row[0] and "illustration_data" not in row[0]

    response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "再生成しました" in body, body[:200]
    new_job = re.search(r"/download/([0-9a-f]{12})/pdf", body).group(1)
    # 裏地の設定も引き継がれること。
    assert client.get(f"/download/{new_job}/lining_pdf").status_code == 200


def test_the_regenerated_illustration_pattern_matches_the_original(client):
    """作り直した型紙が、元と同じ寸法になること。"""
    import io

    from PIL import Image, ImageDraw

    client.post("/signup", data={"email": "ill-same@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (460, 560), (240, 560)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = dict(FORM, mode="illustration")
    data["illustration"] = (io.BytesIO(buffer.getvalue()), "front.png")
    first = client.post("/api/generate", data=data,
                        content_type="multipart/form-data").get_json()

    response = client.post(f"/account/jobs/{first['job_id']}/regenerate",
                           follow_redirects=True)
    new_job = re.search(r"/download/([0-9a-f]{12})/pdf",
                        response.get_data(as_text=True)).group(1)
    with app_module.db._connect() as conn:
        row = conn.execute("SELECT part_count FROM jobs WHERE job_id = ?",
                            (new_job,)).fetchone()
    assert row[0] == first["part_count"], "作り直した型紙のパーツ数が違います"
