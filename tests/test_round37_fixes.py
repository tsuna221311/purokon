"""round37: 読めるか・触れるか・伝わるか、を実際に確かめて直した。

round35は体型、round36は構成と画面を変えて触った。round37は
**画面が誰にとって使えるか**を見た。

1. 色: 白の上でだけ確かめた色を、色付きの箱の中でも使っていた
2. 操作: 動的に作る入力欄3つに、支援技術へ読まれる名前が無かった
3. 文言: 送信が大きすぎたときの案内が、当たってもいない上限を名指ししていた
"""

import io
import re

import pytest

import app as appmod


@pytest.fixture()
def client(monkeypatch):
    """レート制限だけ緩めたテスト用クライアント。

    レート制限そのものは正しく働いている(round37の実測で確認済み)。
    ここで見たいのは文言なので、それに当たらないようにする。
    """
    monkeypatch.setattr(appmod._generate_rate_limiter, "max_requests", 100000)
    return appmod.app.test_client()


def _csrf(client) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]+)"', client.get("/").data)
    assert match, "CSRFトークンが取れませんでした"
    return match.group(1).decode()


# --- 3) 大きすぎる送信の案内 --------------------------------------------------

def test_a_huge_outline_is_not_blamed_on_an_image(client):
    """画像を1枚も送っていないのに「画像が大きすぎます」と言わないこと。

    【実際に起きていたこと】カスタムパーツの輪郭(custom_panels_json)は
    **ファイルではなくフォームの値**として送る。Werkzeugはファイル以外の
    フォームの値に別の上限(既定約500KB)を持っており、輪郭を細かくすると
    そちらに当たる。

    ところが413の文言は「アップロードされた画像が大きすぎます（上限12MB）」
    と決め打ちだった。実測(round37)では、**画像を1枚も添付していないのに
    そう言われ**、しかも送信全体は1.9MBで12MBに届いていなかった——
    「12MBより小さいのに大きすぎると言われる」という、直しようのない案内。
    """
    payload = '[{"label":"x","points":' + str([[i, i] for i in range(100000)]) \
              + ',"reference_cm":10}]'
    response = client.post("/api/generate", data={
        "csrf_token": _csrf(client), "mode": "manual",
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
        "custom_panels_json": payload,
    })
    assert response.status_code == 413
    error = (response.get_json(silent=True) or {}).get("error", "")
    assert "画像が大きすぎます" not in error, error
    # 当たった方の上限を名指しし、何を減らせばよいかを言うこと
    assert "カスタムパーツ" in error and "頂点" in error, error
    assert "500KB" in error or "KB" in error, error


def test_an_actually_huge_upload_still_names_the_overall_limit(client):
    """本当に画像が大きい場合は、全体の上限(12MB)を案内すること。

    片方を直した拍子にもう片方が的外れになっていないことを見る。
    """
    big = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * (13 * 1024 * 1024))
    response = client.post("/api/generate", data={
        "csrf_token": _csrf(client), "mode": "illustration",
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "illustration": (big, "big.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 413
    error = (response.get_json(silent=True) or {}).get("error", "")
    assert "12MB" in error, error
    assert "画像" in error, error


def test_the_message_users_actually_see_is_the_fixed_one(client):
    """利用者へ実際に届くのは、グローバルのエラーハンドラであること。

    【round37で踏んだ落とし穴】最初、view関数の`except`節の文言だけを
    直した。だがCSRF検証が`before_request`で本文を読むため、413は
    **view関数に入る前**に送出され、`@app.errorhandler(413)`の方が
    応答を返す。そちらが古い文言のままだったので、直したつもりで
    画面には古い文言が出続けていた。

    3か所すべてが同じ関数を使っていることを、ソースを読んで固定する。
    """
    source = open(appmod.__file__, encoding="utf-8").read()
    # 古い決め打ちの文言を**応答として返している**箇所が残っていないこと。
    # (由来を説明しているコメント・docstringの中に文字列として出てくるのは
    #  残してよい——なぜ直したのかが分からなくなる方が困る。)
    assert not re.search(r'"error":\s*f?"アップロードされた画像が大きすぎます', source), \
        "古い文言をそのまま返している箇所が残っています"
    # 413を返す箇所は、すべて共通の関数を通ること
    returns_413 = re.findall(r'return jsonify\(\{[^}]*\}\), 413', source)
    assert returns_413, "413を返す箇所が見つかりません"
    for fragment in returns_413:
        assert "_too_large_message()" in fragment, fragment


# --- 異常系が500にならないこと -----------------------------------------------

@pytest.mark.parametrize("overrides,expect_in_message", [
    ({"bust": ""}, "数値"),
    ({"bust": "たくさん"}, "数値"),
    ({"bust": "-50"}, "正の値"),
    ({"bust": "999999"}, "範囲"),
    ({"bust": "NaN"}, "範囲"),
    ({"bust": "Infinity"}, "範囲"),
    ({"neckline": "banana"}, "neckline"),
    ({"sleeve_style": "banana"}, "sleeve_style"),
    ({"seam_allowance_cm": "-5"}, "縫い代"),
    ({"seam_allowance_cm": "500"}, "縫い代"),
    ({"hem_seam_allowance_cm": "500"}, "裾の縫い代"),
    ({"custom_panels_json": "{{{not json"}, "JSON"),
    ({"custom_panels_json": '{"a":1}'}, "配列"),
    ({"custom_panels_json": '[{"label":"x","points":[[0,0]],"reference_cm":10}]'}, "頂点数"),
    ({"custom_panels_json": '[{"label":"x","points":"あ","reference_cm":10}]'}, "不正"),
    ({"fit": "stretch", "stretch_percent": "9999"}, "範囲"),
    ({"fit": "stretch", "stretch_percent": "のびる"}, "数値"),
])
def test_bad_input_is_refused_clearly_not_with_an_internal_error(
        client, overrides, expect_in_message):
    """壊れた入力に対して、500ではなく意味の分かる400を返すこと。

    500を返すと利用者には何も伝わらない(「エラーが発生しました」だけ)。
    何を直せばよいかが文言に入っていることまで見る。
    """
    data = {
        "csrf_token": _csrf(client), "mode": "manual",
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
    }
    data.update(overrides)
    response = client.post("/api/generate", data=data)
    assert response.status_code < 500, response.get_data(as_text=True)[:300]
    assert response.status_code == 400, response.status_code
    error = (response.get_json(silent=True) or {}).get("error", "")
    assert expect_in_message in error, f"{expect_in_message!r} が {error!r} に無い"
