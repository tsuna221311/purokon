# 管理人衣装：前・後身頃も型紙から起こす試作

2026-10-04。裾A/B/Cだけでなく、対応する前身頃2枚・後身頃1枚の縫い線と合印を型紙生成結果から3D向けデータへ書き出した。4サイズ（バスト76/83/92/104 cm）で上身頃と裾の縫い線長の一致、輪郭の三角分割を実行できた。3Dでは従来の手作業コート上部を非表示にし、型紙輪郭から作った上身頃の面を既存の3D形状ガイドに沿わせた。したがって**輪郭とメッシュは型紙由来だが、立体的な着用形状は推定ガイド由来**であり、縫製完成モデルではない。

実行例：

`python scripts/export_endministrator_panels.py`

`blender -b -t 4 --python scripts/simulate_endministrator_pattern_panels.py -- output/endministrator_pattern_drape/panels.json output/endministrator_pattern_bodice_v2 output/endministrator_commercial_sewn_v4/endministrator_sewn_costume.blend with-body pattern-bodice`

上身頃の仮の裾線は、縦方向の起伏を含む弧長で114.00 cmに調整した。型紙の前30.75 cm×2枚＋後52.50 cmと合計長は一致し、前回の約7.89 cmずつの仮の未接合区間は数値上なくなった。ただし上身頃と裾パネルは別オブジェクトのままで、縫い目の力を共有しない。各裾パネル上辺の3D折れ線長もまだ型紙より0.19～0.22 cm短い。

| 検査 | 体との衝突あり | 体との衝突なし |
| --- | ---: | ---: |
| 右前Bの平均変位 | 8.13 cm | 8.48 cm |
| 上身頃裾の総弧長 | 114.00 cm | 114.00 cm |

右前Bは大きく折れ、正面画像が前回より悪化した。体との衝突を外しても続くため、衝突設定だけでは説明できない。型紙を縮めずに胴体側の弧長だけを合わせたこと、裾の脇配置と実際の縫合が未解決であることを次の検討対象にする。**この版を製品の完成プレビューとして採用しない。** 以前の `output/endministrator_pattern_drape_v7` を比較基準として保持する。

市販品同等の判定には、使用生地の物性、背面・側面の確定形状、実際の縫い付けと可動試験、同条件の市販現物比較が引き続き必要である。[比較対象の公表されたセット構成](https://cossky.com/products/arknights-endfield-the-female-endministrator-women-outfit-halloween-carnival-party-cosplay-costume)は参照可能だが、実物の縫製・素材強度をオンラインの商品情報だけで検証することはできない。
