# 管理人衣装：曲面の身頃・裾を縫い合わせた3D試験

2026-10-04。前回の平面布片で有効だった縫合ばねを、型紙由来の上身頃A/B/Cと裾A/B/Cの曲面配置に拡張した。左右前身頃の向きに合わせ、A側は縫い線上の対応点を逆順に結んだ。裾パネルだけでなく上身頃も同じ布メッシュへ含め、上身頃を暫定3Dガイド上に固定した。実際の縫製、型紙由来の自立した3Dフィット、全身衣装の物理モデルではない。

元の型紙はバスト83 cmの試験寸法。身頃と裾の接合線合計は114.0 cmで、分割点は2D上で一致する。裾の初期3D辺長は2D型紙の99.9～100.0%（5～95百分位）。縫合ばねはA/Bが各53本、後Cが89本。以下の数値は計算上の距離で、実物の縫い目精度を示さない。

| 条件 | Aの変位95百分位 | Bの変位95百分位 | Cの変位95百分位 | A/B/Cの縫い目隙間95百分位 |
| --- | ---: | ---: | ---: | --- |
| 基準布・布同士の衝突あり・開始隙間4 cm | 15.82 cm | 13.74 cm | 10.31 cm | 0.150 / 0.143 / 0.112 cm |
| 同条件＋採寸値から作った仮の胴体 | 15.82 cm | 13.74 cm | 10.31 cm | 0.150 / 0.143 / 0.112 cm |
| 開始隙間0.5 cm | 32.69 cm | 19.59 cm | 18.91 cm | 0.150 / 0.176 / 0.116 cm |
| 軽く曲げにくい未実測の仮設定 | 30.87 cm | 10.64 cm | 5.38 cm | 0.150 / 0.163 / 0.101 cm |
| 同仮設定・布同士の衝突を無効化 | 13.72 cm | 16.30 cm | 22.09 cm | 0.013 / 0.014 / 0.014 cm |

正面・側面・背面のレンダリングを確認した。基準布は裾端が大きく丸まり、横からは複数の布片が垂れたように見える。開始隙間を縮めると左前と背面がさらに折れ、硬い仮設定でも左前のシルエットが崩れた。布同士の衝突を無効にすると縫い目の距離は縮むが、布の重なり・貫通を無視するため有効な改善ではない。採寸値の仮胴体を入れても今回の数値と画像は変化しなかった。

比較した画像：

- [基準布の正面](../output/endministrator_pattern_sewn_curve_v1/pattern_panels_front.png)・[側面](../output/endministrator_pattern_sewn_curve_v1/pattern_panels_side.png)・[背面](../output/endministrator_pattern_sewn_curve_v1/pattern_panels_back.png)
- [硬い仮設定の正面](../output/endministrator_pattern_sewn_structured_v1/pattern_panels_front.png)・[側面](../output/endministrator_pattern_sewn_structured_v1/pattern_panels_side.png)・[背面](../output/endministrator_pattern_sewn_structured_v1/pattern_panels_back.png)

判定：**いずれも市販コスプレの外観・着用感・縫製品質に達していない。完成プレビューには採用しない。** 現行の上身頃は型紙輪郭を手作業3Dの形状ガイドに投影したもので、袖・脇・前開き・裏地・飾りの接合を物理計算していない。裾A/B/Cは本体への上端接合だけを計算し、各片の横辺は未接合。資料は正面イラストだけで背面形状は推定、生地の実測物性と市販現物はない。したがって布設定の数字を調整するだけで同等品質と主張できない。

再実行例：

```text
blender -b -t 4 --python scripts/simulate_endministrator_pattern_panels.py -- output/endministrator_seam_coupon/panels_regrid.json output/endministrator_pattern_sewn_curve_v1 output/endministrator_commercial_sewn_v4/endministrator_sewn_costume.blend free-hang pattern-bodice smooth-hem 0 sewn-bodice 0.08 baseline self-collision
```

次の実装では、コートの下層とオーバーレイの構成を整理し、横辺を縫う設計か自由端にする設計かを型紙・縫製指示で明示する。現行の3Dレンダリングを型紙の出来の証明として扱わない。
