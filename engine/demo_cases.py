"""Fixed, disclosed input sets for the October 2026 presentation demo.

These are hand-specified garment plans, not claims that a single image was
automatically interpreted.  They use one identical measurement set so that
the pattern files can be compared without a hidden size change.
"""

DEMO_MEASUREMENTS = {
    "bust": 83, "waist": 66, "hip": 91,
    "height": 158, "sleeve_length": 52, "shoulder_width": 37,
}

DEMO_CASES = (
    {
        "id": "endministrator",
        "title": "エンドフィールド 管理人（女性）",
        "search_terms": ["管理人", "エンドフィールド", "endministrator"],
        "project_key": "endministrator_female",
        "summary": "コート本体、袖、非対称の裾パネルを分けて製図。装甲・金具は別工程。",
        "sketch": None,
        "doll_pdf": "demo/doll_pdfs/endministrator_one_third_A4.pdf",
        "doll_video": None,
    },
    {
        "id": "miku",
        "title": "初音ミク（定番衣装）",
        "search_terms": ["初音ミク", "ミク", "hatsune miku", "vocaloid"],
        "project_key": "hatsune_miku_classic",
        "summary": "ノースリーブ上身頃、プリーツスカート、布ストラップ。ネクタイ・腕カバーは別工程。",
        "sketch": None,
        "doll_pdf": "demo/doll_pdfs/miku_one_third_A4.pdf",
        "doll_video": None,
    },
    {
        "id": "blue_dress",
        "title": "オリジナル青いドレス",
        "search_terms": ["青いドレス", "青色のドレス", "blue dress", "ドレス"],
        "project_key": "blue_dress_three_view",
        "summary": "新規に描いた正面・側面・背面ラフと、丸首・袖・フレアの固定構成。開きは未確定。",
        "sketch": "demo/blue_dress_three_views.svg",
        "doll_pdf": "demo/doll_pdfs/blue_dress_one_third_A4.pdf",
        "doll_video": "demo/blue_dress_paper_demo.mp4",
    },
)
