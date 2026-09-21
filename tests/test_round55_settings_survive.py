"""round55: 「生成履歴から再生成」が、別の服を作っていた。

round54で足した生地の割り当てを、他の機能と組み合わせて壊しにいったところ、
**3つとも「黙って無視する」経路**が見つかった。いちばん重いのは3つ目で、
round54とは関係なく以前から壊れていた。

実測(裏地あり・生地2種類・スカート丈45cm・一方方向生地で作った型紙を、
マイページの「生成履歴」から再生成):

    元          : 裏地あり / 生地2種類 / 幅110cm×122cm
    再生成の結果: 裏地なし / 生地1種類 / 幅140cm×181cm

画面に出たのは「再生成しました。ダウンロード: …」だけである。
1週間後に同じ型紙を刷り直したつもりの人は、**スカートが17cm長く、
裏地が無く、生地の分かれていない**型紙で布を裁つことになる。

原因は、設定を渡す場所と保存する場所が別々に書かれていたこと。
`generate_from_selection`は12個の設定を受け取るのに、再生成は
allow_rotation / 縫い代 / 裾の縫い代 の**3つしか渡していなかった**。
設定を足すたびに2か所を直す作りだったので、round38の一方方向生地、
round40の補正、round41の裏地、round52の丈、round54の生地——
**足されたものが順に落ちていった**。

直し方は「渡すもの」と「保存するもの」を同じ1つの辞書にすること。
下の`test_every_setting_the_form_reads_is_stored_for_regeneration`が、
新しい設定を足したときに落ちる見張りになる。

他の2つ:
  ・サイズ展開では、生地の割り当てを受け取って検査までしながら
    **エンジンへ渡していなかった**(round52と同じ形の取り落とし)。
  ・手持ち生地の判定が、全パーツを1枚に詰めた長さで答えていた。
    「白い身頃＋紺のスカート」の紺だけを110×130cm持っている人に
    「117cm足りません」——紺のぶんは124cmで、**実際には収まっていた**。
    持っている生地を使わせ損ねる、いちばん困る間違え方である。
"""

import json
import re

import pytest

import app as app_module


MEASUREMENTS = {
    "bust": "84", "waist": "68", "hip": "92", "height": "160",
    "sleeve_length": "54", "shoulder_width": "37",
}
GARMENT = {
    "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
}
#: 「全部入り」の任意設定。再生成で1つでも落ちたら、別の服になる。
ALL_OPTIONS = {
    "lining": "on",
    "length_skirt": "45",
    "fabric_skirt": "紺サテン",
    "one_way_fabric": "on",
    "shrink_percent": "3",
    "pattern_repeat_cm": "20",
    "seam_allowance_cm": "1.5",
    "hem_seam_allowance_cm": "3",
    "fit": "relaxed",
    "alter_waist": "2",
}


def _signup(client, email="regen@example.com"):
    client.post("/signup", data={"email": email, "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)


def _generate(client, **extra):
    data = dict(MEASUREMENTS, mode="manual", **GARMENT)
    data.update(extra)
    response = client.post("/api/generate", data=data)
    assert response.status_code == 200, response.get_json().get("error")
    return response.get_json()


def _spec_of(client, job_id):
    with app_module.db._connect() as conn:
        row = conn.execute("SELECT spec_json FROM jobs WHERE job_id = ?",
                            (job_id,)).fetchone()
    assert row and row[0], f"{job_id} のspec_jsonがありません"
    return json.loads(row[0])


# --- 1. 再生成で設定が落ちないこと ------------------------------------------

def test_every_setting_is_stored_for_regeneration(client):
    """生成に使った設定が、そのまま履歴に残ること。

    **新しい設定を足したときに落ちる見張り**。`generate_from_selection`の
    引数のうち、保存できないもの(生成のたびに決まるもの)以外が全部
    `generation_kwargs`に入っていることを見る。
    """
    import inspect

    _signup(client, "store@example.com")
    payload = _generate(client, **ALL_OPTIONS)
    spec = _spec_of(client, payload["job_id"])
    stored = spec["generation_kwargs"]

    signature = inspect.signature(
        app_module.pipeline.generate_from_selection.__wrapped__
        if hasattr(app_module.pipeline.generate_from_selection, "__wrapped__")
        else app_module.pipeline.generate_from_selection)
    # 保存しないもの(保存する意味が無いもの)は、ここに理由と一緒に書く。
    NOT_STORED = {
        "garment_spec",          # spec_json の "garment_spec" が別に持つ
        "measurements",          # 同上("measurements")
        "fabric_width_candidates",  # 既定の候補幅。利用者は選べない
        "skip_export",           # 測るだけの生成に使う内部の都合
    }
    expected = {name for name in signature.parameters
                if name not in NOT_STORED and name != "self"}
    missing = sorted(expected - set(stored))
    assert not missing, (
        f"再生成で落ちる設定があります: {missing} / "
        "app.py の generation_kwargs に足してください")


@pytest.mark.parametrize("option, check", [
    ("lining", lambda p: p["lining"] is not None),
    ("length_skirt", lambda p: any("指定どおり" in n for n in p["design_notes"])),
    ("fabric_skirt", lambda p: p["fabric_groups"] is not None),
])
def test_a_regenerated_pattern_keeps_each_setting(client, option, check):
    """再生成しても、その設定が効いたままであること。"""
    _signup(client, f"keep-{option}@example.com")
    first = _generate(client, **{option: ALL_OPTIONS[option]})
    assert check(first), f"元の生成で {option} が効いていません"

    response = client.post(f"/account/jobs/{first['job_id']}/regenerate",
                           follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = re.search(r"/download/([0-9a-f]{12})/pdf", body)
    assert match, "再生成のリンクが見つかりません"
    new_job = match.group(1)

    # 再生成後の型紙が、元と同じ設定で作られていること。
    # (spec_jsonは引き継がれるので、そこから確かめる)
    stored = _spec_of(client, new_job)["generation_kwargs"]
    if option == "lining":
        assert stored["lining"] is True
    elif option == "length_skirt":
        assert stored["design_length_overrides"] == {"skirt": 45.0}
    else:
        assert stored["fabric_group_assignments"] == {"skirt": "紺サテン"}


def test_a_regenerated_pattern_uses_the_same_amount_of_fabric(client):
    """出てくる型紙そのものが同じであること(設定が効いた結果を見る)。"""
    _signup(client, "same@example.com")
    first = _generate(client, **ALL_OPTIONS)
    response = client.post(f"/account/jobs/{first['job_id']}/regenerate",
                           follow_redirects=True)
    new_job = re.search(r"/download/([0-9a-f]{12})/pdf",
                        response.get_data(as_text=True)).group(1)
    # 裏地・2種類目の生地のファイルが、再生成でも作られていること。
    for fmt in ("pdf", "lining_pdf", "fabric2_pdf"):
        got = client.get(f"/download/{new_job}/{fmt}")
        assert got.status_code == 200, f"再生成で {fmt} が作られていません"


@pytest.mark.parametrize("extra", [
    {"fit": "custom", "ease_bodice": "14", "ease_waist": "8"},
    {"fit": "stretch", "stretch_percent": "50", "upper_arm": "27"},
])
def test_a_hand_entered_ease_can_be_stored_and_restored(client, extra):
    """「ゆとりを自分で入れる」「伸びる生地」でも、保存・再生成できること。

    この2つは`fit`が文字列ではなく`FitEase`(データクラス)になる。
    そのままJSONにしようとすると
    `TypeError: Object of type FitEase is not JSON serializable`で
    **生成そのものが500になる**——round55で設定一式を保存するように
    したときに実際に踏み、既存のテストが捕まえた。
    """
    _signup(client, f"ease-{extra['fit']}@example.com")
    payload = _generate(client, **extra)

    stored = _spec_of(client, payload["job_id"])["generation_kwargs"]
    assert isinstance(stored["fit"], dict), stored["fit"]
    restored = app_module._restore_generation_kwargs(stored)["fit"]
    assert isinstance(restored, app_module.FitEase)

    response = client.post(f"/account/jobs/{payload['job_id']}/regenerate",
                           follow_redirects=True)
    assert response.status_code == 200
    assert "再生成しました" in response.get_data(as_text=True)


def test_a_preset_fit_is_stored_as_it_is(client):
    _signup(client, "preset-fit@example.com")
    payload = _generate(client, fit="relaxed")
    stored = _spec_of(client, payload["job_id"])["generation_kwargs"]
    assert stored["fit"] == "relaxed"


def test_an_old_history_entry_without_the_new_key_still_regenerates(client):
    """round55より前の履歴(新しいキーが無い)も、これまでどおり再生成できること。"""
    _signup(client, "legacy@example.com")
    first = _generate(client)
    spec = _spec_of(client, first["job_id"])
    spec.pop("generation_kwargs", None)          # 古い履歴の形にする
    with app_module.db._connect() as conn:
        conn.execute("UPDATE jobs SET spec_json = ? WHERE job_id = ?",
                      (json.dumps(spec), first["job_id"]))
        conn.commit()

    response = client.post(f"/account/jobs/{first['job_id']}/regenerate",
                           follow_redirects=True)
    assert response.status_code == 200
    assert "再生成しました" in response.get_data(as_text=True)


# --- 2. サイズ展開でも生地の割り当てが効くこと ------------------------------

def test_multi_size_honours_the_fabric_assignment(client):
    """サイズ展開でも生地を分けること。

    それまでは受け取って検査までしておきながら**エンジンに渡していなかった**
    ので、2色の衣装をS/M/Lで作ると全サイズが1種類の生地の配置で出ていた。
    """
    data = dict(MEASUREMENTS, mode="multi_size", **GARMENT)
    data["sizes"] = ["S", "M"]
    data["fabric_skirt"] = "紺サテン"
    response = client.post("/api/generate", data=data)
    assert response.status_code == 200, response.get_json().get("error")
    results = response.get_json()["results"]
    assert results
    for size, payload in results.items():
        groups = payload["fabric_groups"]
        assert groups, f"{size}: 生地が分かれていません"
        assert [g["name"] for g in groups] == ["表地", "紺サテン"], size


def test_regenerating_a_multi_size_job_keeps_its_settings(client):
    """サイズ展開の再生成でも、設定が落ちないこと。

    手動生成と同じ取り落としが、こちらにもあった(fitと生地の割り当てが
    再生成で消えていた)。**両方直したことを、両方で見る**。
    """
    _signup(client, "multi-regen@example.com")
    data = dict(MEASUREMENTS, mode="multi_size", **GARMENT)
    data["sizes"] = ["S", "M"]
    data["fabric_skirt"] = "紺サテン"
    data["fit"] = "relaxed"
    first = client.post("/api/generate", data=data)
    assert first.status_code == 200, first.get_json().get("error")
    bundle_id = first.get_json()["bundle_job_id"]

    stored = _spec_of(client, bundle_id)["multi_size_kwargs"]
    assert stored["fabric_group_assignments"] == {"skirt": "紺サテン"}
    assert stored["fit"] == "relaxed"

    response = client.post(f"/account/jobs/{bundle_id}/regenerate",
                           follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "再生成しました" in body, body[:200]
    new_bundle = re.search(r"/download/([0-9a-f]{12})/zip", body).group(1)

    import io
    import zipfile
    blob = client.get(f"/download/{new_bundle}/zip").data
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert any("_fabric2" in name for name in names), (
        f"再生成で生地の分かれた型紙が消えています: {sorted(names)}")


def test_the_zip_names_each_fabric_readably(client):
    """ZIPの中で、生地ごとのファイルに読める名前が付くこと。"""
    import io
    import zipfile

    data = dict(MEASUREMENTS, mode="multi_size", **GARMENT)
    data["sizes"] = ["S"]
    data["fabric_skirt"] = "紺サテン"
    response = client.post("/api/generate", data=data)
    assert response.status_code == 200, response.get_json().get("error")
    zip_url = response.get_json()["download"]["zip"]
    blob = client.get(zip_url).data
    names = sorted(zipfile.ZipFile(io.BytesIO(blob)).namelist())
    assert "S/S_fabric2.pdf" in names, names
    assert "S/S_fabric2_projector.pdf" in names, names
    # round49の衝突検査が効いていること(同名が2件入っていない)。
    assert len(names) == len(set(names)), names


# --- 3. 手持ち生地の判定を、生地ごとに答えること ----------------------------

def test_the_stash_verdict_is_per_fabric(client):
    """手持ちの1枚は1種類の生地なので、生地ごとに答えること。

    全パーツ合計で判定すると、紺のスカートぶん(124cm)しか要らない人に
    「117cm足りません」と答えてしまう(実測)。
    """
    payload = _generate(client, fabric_skirt="紺サテン",
                        stash_width_cm="110", stash_length_cm="130")
    by_fabric = payload["stash_verdicts_by_fabric"]
    assert by_fabric, "生地ごとの判定が出ていません"
    assert [v["fabric_name"] for v in by_fabric] == ["表地", "紺サテン"]
    for verdict in by_fabric:
        # どちらも130cm以内に収まる(合計246cmではない)。
        assert verdict["needed_length_cm"] < 130, verdict
        assert verdict["fits"] is True, verdict


def test_the_headline_verdict_is_the_worst_fabric(client):
    """1つしか見ない人に、足りている方を見せないこと。"""
    payload = _generate(client, fabric_skirt="紺サテン",
                        stash_width_cm="110", stash_length_cm="123")
    by_fabric = payload["stash_verdicts_by_fabric"]
    short = [v for v in by_fabric if not v["fits"]]
    assert short, "この長さでは足りない生地があるはず"
    assert payload["stash_verdict"]["fits"] is False
    assert payload["stash_verdict"]["needed_length_cm"] == max(
        v["needed_length_cm"] for v in by_fabric)


def test_a_single_fabric_stash_verdict_is_unchanged(client):
    """生地を分けていないときは、round54までとまったく同じ形で返すこと。"""
    payload = _generate(client, stash_width_cm="140", stash_length_cm="200")
    assert payload["stash_verdicts_by_fabric"] is None
    assert payload["stash_verdict"]["fits"] is True


def test_the_screen_shows_the_per_fabric_verdict(client):
    js = client.get("/static/app.js").get_data(as_text=True)
    assert "stash_verdicts_by_fabric" in js, "画面が生地ごとの判定を読んでいません"
    assert "生地ごとに見ています" in js
