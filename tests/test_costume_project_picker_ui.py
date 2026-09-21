"""衣装カタログの検索・選択導線がトップ画面へ出ていることを確認する。"""

import app as application


def test_index_renders_costume_project_search_and_category_picker():
    client = application.app.test_client()
    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="costume-project-search"' in html
    assert 'id="costume-project-category"' in html
    assert 'id="costume-project-selection-summary"' in html
    assert 'id="switch-to-reference-mode"' in html
    assert 'id="reference-review-result"' in html
    assert 'data-project-key=' not in html
    # 50キャラを選択肢として実際にレンダリングする。
    assert html.count('<option value="') >= 51  # 「指定しない」+ 50プリセット
