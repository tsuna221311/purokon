from engine.templates_db import TemplateDB, REQUIRED_PARTS


def test_all_required_templates_are_present():
    db = TemplateDB()
    assert db.missing() == []
    assert len(db.available()) == len(REQUIRED_PARTS)


def test_get_returns_segments_for_known_part():
    db = TemplateDB()
    segments = db.get("front_bodice", "round_neck")
    assert segments is not None
    assert segments[0][0] == "M"


def test_get_returns_none_for_unknown_part():
    db = TemplateDB()
    assert db.get("does_not_exist", "") is None


def test_get_returns_none_for_known_part_type_with_unknown_variation():
    # 以前はvariationが一致しない場合、part_typeだけで最初に見つかった
    # （ファイルシステムの走査順に依存する）無関係のテンプレートを
    # 静かに返してしまっていた。誤った型紙が生成される前に、
    # ここでNoneを返して呼び出し側(pipeline._build_from_spec)が
    # 明確なエラーを出せるようにする。
    db = TemplateDB()
    assert db.get("front_bodice", "no_such_variation") is None
    assert db.get("front_bodice", "round_neck") is not None  # 完全一致は引き続き取得できる


def test_attr_extraction_is_not_confused_by_id_attribute_before_d(tmp_path):
    # _attr()は以前、rf'{name}\s*=\s*"([^"]*)"' という無anchorの正規表現で
    # name="d" を検索していた。これは「id="..."」の "d=" 部分にも一致して
    # しまうため、<path>要素に id 属性が d 属性より前に書かれていると、
    # d(パスデータ)のつもりでid属性の値を取り出してしまうバグがあった。
    # 実在のテンプレートSVGはどれもid属性を持たないため今のところ
    # 到達しないが、将来だれかがid属性を追加した場合に備え、正しい方の
    # d属性の値(本物のパスデータ)が取得できることを確認する。
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">\n'
        '  <path id="mypart" data-part="front_bodice" data-variation="round_neck"\n'
        '    fill="none" d="M 8 0.0 L 30 60.0 Z" />\n'
        "</svg>"
    )
    svg_path = tmp_path / "id_before_d.svg"
    svg_path.write_text(svg, encoding="utf-8")

    db = TemplateDB(template_dir=str(tmp_path))
    segments = db.get("front_bodice", "round_neck")

    assert segments is not None
    # 修正前は "mypart" というゴミ文字列がparse_path()に渡され、
    # IndexError（テンプレートDB全体の初期化失敗）を引き起こしていた。
    assert segments == [("M", [8.0, 0.0]), ("L", [30.0, 60.0]), ("Z", [])]


def test_attr_still_matches_a_standalone_d_attribute_with_no_id_present():
    # 通常ケース(id属性が存在しない)の回帰確認。境界チェックを追加した
    # ことで、通常のd属性マッチングを壊していないことを保証する。
    svg = '<path data-part="sleeve" data-variation="straight" d="M 0 0 L 1 1 Z" />'
    assert TemplateDB._attr(svg, "d") == "M 0 0 L 1 1 Z"
    assert TemplateDB._attr(svg, "data-part") == "sleeve"
