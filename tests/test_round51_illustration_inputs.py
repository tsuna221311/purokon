"""round51: round50で「試していない」と書いた入力を、実際に渡して確かめた。

round50の反省（確かめずに限界を5回書いた）をそのまま適用し、
**自分が前回名指しした未検証項目**から手を付けた:
人物が着ているイラスト、後ろ姿の絵、変な画像、EXIF回転。

見つかったもの:

  1. **後ろ姿の絵だけを渡すと、黙って生成できてしまった。**
     受け取り口の検査は `front + back` を足した枚数しか見ていない。
     後ろの絵は「後身頃の襟ぐりを読むための補助」であって、
     前身頃・袖・スカートは前の絵から読む。後ろだけ渡すと
     **前身頃が既定のまま生成される**——すぐ上のコメントが
     「イラストを見てくれなかったことに利用者が気づけない」ので
     明確なエラーにする、と書いている、まさにその状態だった。
     実測で 200・パーツ6枚が返っていた。
  2. **保存期間を過ぎたダウンロードリンクが、生のJSONを見せていた。**
     `/download/...` は Accept を見ずに
     `{"error":"not found","ok":false}` を返していた。生成物の保存期間は
     既定1時間なので、「リンクをブックマークして翌日開く」は
     ふつうに起こる。そのとき画面に出るのがこれだった。

確かめて**正しかった**もの（記録）:
  ・人物が着ている絵 → 「頭・脚を除いた服の範囲で測った」「襟ぐりは
    シルエットに現れないので読み取れない」と開示して生成できる
  ・前後で襟ぐりが違う絵 → 肩線が合わないことを説明し、前に揃える
  ・前後あわせて6枚の上限 → 7枚で400、6枚ちょうどで成功
  ・真っ白/真っ黒/1x1/極細/グラデーション背景/画像でないファイル
    → すべて日本語の400
  ・EXIFに回転指示のあるJPEG → 見た目どおりの向きで読む
"""

import io
import os
import pathlib

import pytest
from PIL import Image, ImageDraw

import app as app_module


def _garment_png(neck="wide") -> bytes:
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(250, 180), (450, 180), (470, 250), (520, 270), (500, 330),
                  (455, 315), (460, 560), (240, 560), (245, 315), (200, 330),
                  (180, 270), (230, 250)], fill=(90, 110, 160))
    draw.polygon([(240, 560), (460, 560), (520, 860), (180, 860)], fill=(90, 110, 160))
    if neck == "wide":
        draw.ellipse([(275, 170), (425, 205)], fill="white")
    else:
        draw.rectangle([(325, 178), (375, 192)], fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _form(**extra):
    data = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "illustration",
    }
    data.update(extra)
    return data


def _post(client, front=0, back=0):
    data = _form()
    if front:
        data["illustration"] = [(io.BytesIO(_garment_png()), f"f{i}.png")
                                for i in range(front)]
    if back:
        data["illustration_back"] = [(io.BytesIO(_garment_png("high")), f"b{i}.png")
                                     for i in range(back)]
    return client.post("/api/generate", data=data,
                       content_type="multipart/form-data")


# --- 1. 前から見た絵は必須であること ---------------------------------------

def test_a_back_only_upload_is_refused(client):
    """後ろ姿の絵だけでは生成しないこと。

    後ろの絵は補助なので、それだけだと前身頃が既定のまま作られてしまう。
    「イラストを見てくれなかった」ことに気づけないまま型紙が出る。
    """
    response = _post(client, front=0, back=1)
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "前から見た絵" in error, error


def test_no_upload_at_all_is_still_refused(client):
    response = _post(client, front=0, back=0)
    assert response.status_code == 400
    assert "アップロードされていません" in response.get_json()["error"]


def test_a_front_upload_is_enough(client):
    response = _post(client, front=1)
    assert response.status_code == 200, response.get_json().get("error")
    assert response.get_json()["part_count"] > 0


def test_front_and_back_together_work(client):
    response = _post(client, front=1, back=1)
    assert response.status_code == 200, response.get_json().get("error")


def test_the_image_limit_counts_both_sides(client):
    """上限は「前後あわせて」であること(案内文がそう書いている)。"""
    limit = app_module.MAX_ILLUSTRATION_IMAGES
    ok = _post(client, front=limit - 1, back=1)
    assert ok.status_code == 200, ok.get_json().get("error")
    over = _post(client, front=limit - 1, back=2)
    assert over.status_code == 400
    assert f"{limit}枚まで" in over.get_json()["error"]


# --- 2. 保存期間を過ぎたリンクの見え方 --------------------------------------

def _generate(client):
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare",
    })
    assert response.status_code == 200
    return response.get_json()["job_id"]


def test_an_expired_link_explains_itself_to_a_browser(client):
    """ファイルが消えたあとのリンクが、画面で説明されること。"""
    job_id = _generate(client)
    for name in os.listdir(app_module.OUTPUT_DIR):
        if name.startswith(job_id):
            os.remove(os.path.join(app_module.OUTPUT_DIR, name))

    response = client.get(f"/download/{job_id}/pdf", headers={"Accept": "text/html"})
    assert response.status_code == 404
    body = response.get_data(as_text=True)
    assert "not found" not in body, "生のJSONが出ています"
    assert "保存期間" in body
    # 何時間で消えるかを、設定値から出すこと(文章に焼き付けない)。
    hours = max(1, round(app_module.OUTPUT_TTL_SECONDS / 3600))
    assert f"{hours}時間" in body
    # 次にどうすればよいかを、**押せる導線**として置くこと。
    # 「生成履歴」という語が説明文に出てくるだけでは足りない
    # (最初そう書いていて、導線を消しても通ってしまった)。
    import re as _re
    actions = _re.findall(r'<a [^>]*class="primary"[^>]*>([^<]+)</a>', body)
    assert actions, "次に進むためのボタンがありません"
    assert any(label.strip() in ("もう一度つくる", "マイページの生成履歴へ")
               for label in actions), actions


def test_an_expired_link_still_answers_json_to_api_clients(client):
    job_id = _generate(client)
    for name in os.listdir(app_module.OUTPUT_DIR):
        if name.startswith(job_id):
            os.remove(os.path.join(app_module.OUTPUT_DIR, name))
    response = client.get(f"/download/{job_id}/pdf",
                          headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "not found"}


def test_someone_elses_job_does_not_get_the_expiry_page(client):
    """他人(未知)のjob_idには、保存期間の話をしないこと。

    存在しない場合と持ち主違いを同じ404にして、他人のjob_idの存在を
    外から探れないようにしてある。保存期間の説明を出すのは、
    **持ち主の確認が済んだ後だけ**にする。
    """
    response = client.get("/download/ffffffffffff/pdf",
                          headers={"Accept": "text/html"})
    assert response.status_code == 404
    body = response.get_data(as_text=True)
    assert "保存期間" not in body
    assert "ページが見つかりません" in body


def test_a_malformed_download_url_shows_a_page_to_a_browser(client):
    """途中で切れたブックマークでも、生のJSONを見せないこと。"""
    response = client.get("/download/zzz/pdf", headers={"Accept": "text/html"})
    assert response.status_code == 400
    assert "invalid request" not in response.get_data(as_text=True)
    assert "<html" in response.get_data(as_text=True)
    # APIにはこれまでどおりJSON。
    api = client.get("/download/zzz/pdf", headers={"Accept": "application/json"})
    assert api.get_json()["error"] == "invalid request"


# --- 3. 変な画像を渡したときに、日本語で断ること ----------------------------

@pytest.mark.parametrize("name, make", [
    ("真っ白", lambda: Image.new("RGB", (600, 800), "white")),
    ("真っ黒", lambda: Image.new("RGB", (600, 800), "black")),
    ("1x1", lambda: Image.new("RGB", (1, 1), "white")),
    ("極端に細長い", lambda: Image.new("RGB", (4000, 12), "white")),
])
def test_an_unreadable_picture_is_refused_in_japanese(client, name, make):
    buffer = io.BytesIO()
    make().save(buffer, format="PNG")
    data = _form()
    data["illustration"] = (io.BytesIO(buffer.getvalue()), "x.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "判定できませんでした" in error, f"{name}: {error}"


def test_a_file_that_is_not_an_image_is_refused(client):
    data = _form()
    data["illustration"] = (io.BytesIO(b"not an image at all\n" * 40), "fake.png")
    response = client.post("/api/generate", data=data,
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert "読み込めませんでした" in response.get_json()["error"]


# --- 4. スマホ写真の向き(EXIF) ----------------------------------------------

def test_the_exif_rotation_is_applied(client):
    """横倒しの画素+「回してね」のEXIFを、見た目どおりに読むこと。

    多くのスマホは縦で撮った写真を横倒しの画素で保存し、向きはEXIFに書く。
    無視すると襟ぐり・裾の位置判定が全部ずれる。
    """
    piexif = pytest.importorskip("piexif")

    upright = Image.new("RGB", (500, 900), "white")
    draw = ImageDraw.Draw(upright)
    draw.polygon([(150, 100), (350, 100), (380, 170), (370, 500),
                  (130, 500), (120, 170)], fill=(90, 110, 160))
    draw.polygon([(130, 500), (370, 500), (430, 860), (70, 860)], fill=(90, 110, 160))
    sideways = upright.transpose(Image.ROTATE_90)
    buffer = io.BytesIO()
    sideways.save(buffer, "JPEG",
                  exif=piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}}))

    loaded = app_module._load_uploaded_image(
        type("U", (), {"stream": io.BytesIO(buffer.getvalue())})())
    assert loaded.size == upright.size, \
        f"EXIFの回転が効いていません({loaded.size} != {upright.size})"
