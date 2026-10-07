# 管理人衣装：連続したコート下身頃と非対称の重ね裾

このログの`../output/`リンク先はローカル検証結果であり、GitHubには同梱しない。型紙・レンダリングを再現する際は本文に記したスクリプトと入力寸法を使用する。

2026-10-04。以前の型紙は、上身頃の下に非対称の尖った飾り布3枚だけを直接付ける構成だった。この構造では裾全体を支えるコート生地がなく、3Dで布片が分離して見えた。今回、左右前・後の連続した下身頃3枚を加え、その外側に従来の飾り布3枚を重ねる構成に変更した。後面の形と重ね布の自由端は、正面イラストからの推定である。

## 型紙・裁断データの検査

試験体型はバスト83、ウエスト66、ヒップ91、身長158 cm。下身頃の接合線上辺は左前30.75、右前30.75、後52.50 cmで、上身頃の対応する裾線と一致した。左右脇の縫い線は6辺とも38.0412 cm。A/B/Cの各飾り布の上辺は下身頃の上辺に合わせ、1/4・3/4の合印を付けた。4組の体型寸法で同じ照合テストを通過した。

下身頃3枚にはコート本体と同じ表地を割り当て、飾り布3枚は別布として分けた。裏地の自動生成は下身頃3枚にだけ適用し、飾り布を誤って裏地化しない。試験出力は表地17パーツ、裏地14パーツで、3枚の下身頃裏地を含む。[制作仕様書PDF](../output/pdf/endministrator_lower_shell_specification.pdf)の7ページを画像化して確認し、部品表、接合記号A/B/C、重ねA/B/C、縫製順に欠落や表示のはみ出しは見つからなかった。このPDFは試作用の仕様書で、現物製作の承認書ではない。

実際の印刷用データも別布指定で生成した。[本体の分割印刷PDF](../output/endministrator_lower_shell_print_qa_grouped/8071b9ce0ab1.pdf)は64ページ、[飾り布PDF](../output/endministrator_lower_shell_print_qa_grouped/8071b9ce0ab1_fabric2.pdf)は19ページ、[裏地PDF](../output/endministrator_lower_shell_print_qa_grouped/8071b9ce0ab1_lining.pdf)は61ページ。本文のテキスト検査では本体に下身頃3枚、別布に重ね布3枚、裏地に下身頃3枚があり、飾り布は裏地に混入していない。各PDFの代表ページを画像化し、裁断線・縫い線・部品名を確認した。分割紙面をまたぐ表示は貼り合わせて読む前提であり、全144ページを実際に印刷・貼り合わせた検査はまだ行っていない。

## 3D仮試験

実際の2D型紙の縫い線を三角形メッシュへ変換し、上身頃と下身頃A/B/Cを縫合ばねで接続した。布の質量・硬さは未実測の仮値であり、胴体スキャン、前開き、袖付け、芯地、金具、歩行時の挙動は含まない。以下の隙間はシミュレーション上の数値で、実物の縫製精度を表さない。

| 条件 | 脇B-Cの隙間95百分位 | 脇C-Aの隙間95百分位 | 正面・側面・背面の所見 |
| --- | ---: | ---: | --- |
| 布同士の衝突あり、下身頃のみ | 0.882 cm | 0.567 cm | 連続した裾にはなったが脇が閉じきらず、前裾が大きく折れる |
| 衝突あり、飾り布を下身頃の曲面に重ねる | 0.882 cm | 0.567 cm | 飾り布が強く縮れ、側面・背面の形が破綻する |
| 衝突なし、飾り布あり | 0.012 cm | 0.022 cm | 数値上の隙間は縮むが、布の貫通を許して前後の裾が潰れる |

衝突を切った結果は、隙間の数値が良くても有効な改善ではない。内部の暫定判定では脇縫いの95百分位隙間0.2 cm以下に加え、布同士の衝突を有効にした場合に限って「仮の閉合確認」とする。今回の比較対象はすべて不合格である。飾り布を重ねる3Dモードは明示的な試験オプションのままにし、完成プレビューとして承認しない。

- [下身頃だけの正面](../output/endministrator_lower_shell_v1/drape_sewn_sides/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_sewn_sides/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_sewn_sides/pattern_panels_back.png)
- [飾り布を重ねた正面](../output/endministrator_lower_shell_v1/drape_overlay_mapped/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_overlay_mapped/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_overlay_mapped/pattern_panels_back.png)
- [衝突を無効にした比較正面](../output/endministrator_lower_shell_v1/drape_overlay_no_self_collision/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_overlay_no_self_collision/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_overlay_no_self_collision/pattern_panels_back.png)

## 判定と次の検証

部品構成、2D接合線、布の振り分け、裏地の範囲は改善した。ただし、正面・側面・背面の見た目、飾り布の収まり、実際の生地による動きは市販完成衣装と同等と判定できない。後面・側面の資料、生地と芯地の物性、着用者の実寸、実物の市販比較対象がない。次は側面・背面資料で下身頃の形を確定し、実測した布で飾り布の初期配置と接合を調整する。その後、実寸の仮縫いと市販現物を同条件で撮影し、外観・フィット・縫製・耐久性を比較する。

## 追試：脇を連続メッシュにする（2026-10-04）

従来の縫合ばねは脇に0.882 / 0.567 cm（95百分位）の隙間を残した。新たに対応する脇の23頂点ずつを3D試験用メッシュで共有させると、布同士の衝突を有効にしたまま脇の幾何学的な隙間は0 cmとなり、正面・背面の下身頃はより連続して見えた。ただし、縫う前の各片は脇上端では一致しても裾では6.04 cm離れていた。頂点を中点へ無理に移したため、下身頃の辺長変化95百分位はA/B/Cそれぞれ8.97 / 8.16 / 9.03%まで増えた。**縫い目の隙間0 cmだけを品質合格とみなさない。**

続いて、フレアを持つ型紙の各段で左右の端を共通の脇位置へ置き、増えた布幅を3Dの外向きの広がりにする配置を試した。いずれも脇の初期隙間は0 cmだが、平面型紙の辺長と初期3Dメッシュの辺長の比、布の伸縮、3方向のシルエットを同時には満たさない。

| 下裾の仮の外向き広がり | 前A/Bの初期辺長比5～95百分位 | 後Cの初期辺長比5～95百分位 | 見た目 |
| --- | --- | --- | --- |
| 3 cm | 0.896～1.006 / 0.896～1.004 | 0.957～1.010 | 前の布を約10%圧縮して配置。裾が大きく折れる |
| 6 cm | 0.934～1.020 / 0.934～1.016 | 0.985～1.024 | 前の圧縮は減るが、片側の裾が脚へ巻き付く |
| 8 cm | 0.956～1.033 / 0.953～1.028 | 0.996～1.048 | 仮の辺長・ひずみ検査は通過。しかし正面の片側裾が脚の間へ折れ込み、背面も大きく欠ける |
| 10 cm | 0.966～1.047 / 0.961～1.041 | 1.000～1.080 | 後の辺が最大8%伸び、前後の裾がさらに大きく崩れる |

飾り布も下身頃の面法線に沿って置いたが、[縫合ばねによる重ね試験](../output/endministrator_lower_shell_v1/drape_overlay_normal/pattern_panels_back.png)・[脇連続メッシュでの重ね試験](../output/endministrator_lower_shell_v1/drape_welded_overlay_normal/pattern_panels_back.png)の背面にはどちらも目立つ縮れが残る。飾り布の3D表示は依然として不承認である。

- [脇連続メッシュの正面](../output/endministrator_lower_shell_v1/drape_welded_sides/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_welded_sides/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_welded_sides/pattern_panels_back.png)
- [3 cm広がりの正面](../output/endministrator_lower_shell_v1/drape_aligned_welded_003/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_aligned_welded_003/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_aligned_welded_003/pattern_panels_back.png)
- [6 cm広がりの正面](../output/endministrator_lower_shell_v1/drape_aligned_welded_006/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_aligned_welded_006/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_aligned_welded_006/pattern_panels_back.png)
- [8 cm広がりの正面](../output/endministrator_lower_shell_v1/drape_aligned_welded_008_gate/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_aligned_welded_008_gate/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_aligned_welded_008_gate/pattern_panels_back.png)
- [10 cm広がりの正面](../output/endministrator_lower_shell_v1/drape_aligned_welded_010/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_v1/drape_aligned_welded_010/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_v1/drape_aligned_welded_010/pattern_panels_back.png)

これらは採寸胴体や市販現物に一致させた状態ではなく、布の物性も未測定である。次の3D比較では「脇が閉じる」「初期辺長比が過度にずれない」「最終変形が大きすぎない」「3方向で衣装らしく見える」を別々に確認する。数値の仮スクリーニングは素材固有の合格基準ではない。

8 cm試験は初期辺長比0.95～1.05、最終辺長変化95百分位5%以下、脇の初期隙間0.2 cm以下という仮の数値スクリーニングを通過した。しかし3方向の画像比較では明確に失敗した。これは数値ゲートを見た目や市販品質の代用にできない直接の反例であり、完成プレビューには使わない。

## 2026-10-06：型紙の辺長を基準にした再検査

従来の「最終辺長変化」は3Dの**初期配置**を基準にしていた。初期配置そのものが型紙の辺長と異なる場合、この数値が小さくても縫製可能性は示せない。最終3Dメッシュの各辺を元の2D縫い線メッシュの辺長と直接比較する項目を追加し、暫定判定にも含めた。許容窓0.95～1.05と95百分位5%は試験用の保守的な数値であり、実測素材の規格ではない。

独立した布片の確認試験でも、旧指標（初期3D配置からの変形）はA/B/Cで0.79 / 0.49 / 0.49%なのに、新指標（2D型紙からの変形）は26.83 / 26.25 / 16.91%だった。旧指標だけでは型紙と3Dの不一致を見落とすことを、別の実行経路でも確認した。

手描きの既存コート下部曲面に新しい型紙を沿わせる試験では、前A/Bの斜め方向に辺長比約0.34～0.35の箇所があった。既存モデルの見た目が良くても、それを型紙由来の布として無理に扱うことはできない。接合済み3パネルを、滑らかな上身頃裾から配置する方法で、実測ではない硬めの仮素材・採寸値から作った胴体代理・自己衝突ありを試した。

| 初期の外向き広がり（3Dモデル単位） | A/B/Cの型紙対最終辺長・絶対差95百分位 | 正面・側面・背面の所見 |
| --- | --- | --- |
| 0.20 m | 15.15 / 26.46 / 9.91% | [正面](../output/endministrator_lower_shell_flared_v2/drape_aligned_020_structured/pattern_panels_front.png)では裾の連続感は改善。ただし右前が潰れ、[側面](../output/endministrator_lower_shell_flared_v2/drape_aligned_020_structured/pattern_panels_side.png)に折れの集中、[背面](../output/endministrator_lower_shell_flared_v2/drape_aligned_020_structured/pattern_panels_back.png)に偏りが残る |
| 0.28 m | 17.66 / 14.79 / 19.66% | [正面](../output/endministrator_lower_shell_flared_v2/drape_aligned_028_structured/pattern_panels_front.png)の左右が大きく巻き上がり、[側面](../output/endministrator_lower_shell_flared_v2/drape_aligned_028_structured/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_aligned_028_structured/pattern_panels_back.png)も崩れる |

両方とも暫定幾何判定は不合格。0.28 mを通常操作として許可するコード変更は戻した。布物性・芯地・実物背面が未測定であり、市販衣装との同一条件比較はできていない。次は前パネルの片寄った折れの原因を接合位置と裁断形状の双方から調べ、仮縫いでは裾線と前開きの動きを優先して確認する。

## 2026-10-06：布メッシュの表裏と縫い線トポロジー

前身頃の折れを追う過程で、旧3D試験用メッシュの下身頃A/B/Cは面の大半が内向きだった。さらに旧三角形化には、直線の脇・裾上に面積ほぼ0の三角形が混じっていた。このまま頂点だけを結合すると脇縫いの1辺を3～4面が共有し、「隙間0 cm」でも通常の縫い目とは異なる非多様体メッシュになる。面を外向きに統一し、0面積の三角形を除去。4辺の下身頃については縫い線の各区間が必ず1面だけに接することを型紙サンプリング時に検査する。複雑な上身頃は裾の接合辺を検査するが、それ以外の曲線外周すべての品質はまだ保証していない。

試験中、別方式の「境界を必ず守る三角形化」も実装して比較した。しかし最小の三角形品質指標が約0.00001の極細面を作り、布が大きく破綻したため採用しなかった。採用した方式では下身頃の最小品質指標は約0.43、ゼロ面積の面はなく、縫い線も維持された。これは数値メッシュの品質確認で、布や衣装の製品品質認定ではない。

上身頃・下身頃・左右脇を3D試験用に完全結合したモードを加え、上辺A/B/Cの52/52/88区間、左右脇の22/22区間すべてで1辺を2面が共有することを確認した。実際の縫製では別パーツを縫うので、この結合は**シミュレーション表現**であり、型紙を一枚へ統合したものではない。

| 条件 | A/B/Cの型紙対最終辺長・絶対差95百分位 | 3方向の所見 |
| --- | --- | --- |
| 旧メッシュ、縫合ばね、硬めの仮素材 | 15.15 / 26.46 / 9.91% | 脇・裾に巻き上がりと強い非対称の折れ |
| 外向き＋0隙間、縫合ばね、硬めの仮素材 | 21.69 / 13.98 / 10.56% | 正面はやや落ち着くが片側が折れ、[側面](../output/endministrator_lower_shell_flared_v2/drape_aligned_020_outward_zero_gap/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_aligned_020_outward_zero_gap/pattern_panels_back.png)も偏る |
| ゼロ面積面除去＋完全結合、実測ではない基準布 | 13.32 / 13.28 / 9.51% | [正面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_filtered_baseline/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_filtered_baseline/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_filtered_baseline/pattern_panels_back.png)で大きな巻き上がりが減り、裾の連続性は改善。ただし初期配置の平滑さに依存し、型紙寸法の差は残る |

飾り裾を別布として重ねる試験では、下身頃への初期貼り付け時点で型紙の辺長比5～95百分位がA=0.896～1.115、B=0.848～1.112、C=0.943～1.197となった。外向きに面を修正しても[正面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_outward/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_outward/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_outward/pattern_panels_back.png)に裂けたような縮れが見える。飾り裾を含む完成プレビューは引き続き不承認。4体型の型紙出力と橋渡し用の関連テスト15件は通過したが、仮縫い・実測素材・市販現物との同条件比較は未実施である。

## 2026-10-06：飾り裾の低ひずみ配置と布計算の切り分け

別布の飾り裾A/B/Cを本体下身頃へ貼り付けるだけでは、初期配置で型紙の辺長を大きく変形させていた。上辺だけを固定し、各三角形の辺長を2D型紙へ近づけ、本体の外側に保つ暫定的な配置補正を実装した。これは**幾何学的な初期配置**で、材料の伸縮・曲げ・縫製を実測したものではない。

| 飾り裾 | 補正前の辺長比5～95百分位 | 補正後の辺長比5～95百分位 | 補正時の元配置からの移動95百分位 |
| --- | ---: | ---: | ---: |
| A | 0.896～1.115 | 0.980～1.085 | 0.63 cm |
| B | 0.848～1.112 | 0.964～1.077 | 0.64 cm |
| C | 0.943～1.197 | 0.985～1.077 | 0.98 cm |

布計算を行わずに配置だけを描いた[正面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed_static/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed_static/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed_static/pattern_panels_back.png)は、裂けたような細片が少ない。したがって初期配置だけが全原因ではない。ただし黒い重なり線が残り、布を動かしていないので完成衣装の着用イメージには使えない。

同じ配置から布・本体との衝突を計算した[正面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_overlay_relaxed/pattern_panels_back.png)には縮れと不自然な陰影が再発した。飾り裾の変位95百分位はA/B/Cで13.48 / 4.17 / 5.31 cm。次は初期の外側距離、重ね布の衝突設定、固定範囲を個別に変えて、実測可能な素材特性と照合する必要がある。静的な配置診断も動的な重ね試験も、市販品同等の確認には使わない。

## 2026-10-06：重ね裾の衝突判定と下身頃の寸法差を分離

同じ型紙、同じ48フレーム、同じ未実測の基準布で、重ね裾の自己衝突と下身頃との衝突を切り分けた。重ね裾A/B/Cの「最終3D辺長と2D型紙辺長の絶対差95百分位」は次の通り。衝突なしの数値は布の貫通を許すため、製品として有効な改善ではない。

| 重ね裾の計算条件 | A / B / C | 解釈 |
| --- | --- | --- |
| 自己衝突・下身頃衝突とも有効、表示用厚みを衝突判定より先に処理 | 150.86 / 90.39 / 157.92% | 強い縮れが発生 |
| 自己衝突だけ無効、下身頃衝突は有効 | 98.34 / 116.23 / 138.02% | 自己衝突だけが原因ではない |
| 下身頃衝突だけ無効、自己衝突は有効 | 8.64 / 7.94 / 7.74% | 下身頃との衝突が主因。ただし貫通を許す診断条件 |
| 表示用厚み・面取りより前に下身頃の衝突判定を移動し、両衝突とも有効 | 8.64 / 7.94 / 7.73% | 縮れは大きく減ったが、型紙寸法との差は残る |

最後の条件は[正面](../output/endministrator_lower_shell_flared_v2/drape_overlay_collision_before_thickness/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_overlay_collision_before_thickness/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_overlay_collision_before_thickness/pattern_panels_back.png)を確認した。鋭い破綻は減ったが、上辺を固定した布の自然な落ち方、実素材の厚み、重ね部分の非貫通性は未検証であり、完成プレビューには承認しない。[数値報告](../output/endministrator_lower_shell_flared_v2/drape_overlay_collision_before_thickness/pattern_panel_drape_report.json)でも承認フラグは偽のままである。

下身頃本体について、初期3D配置の辺を2D型紙と再照合した。A/B/Cの上辺だけなら絶対差95百分位は0.08 / 0.08 / 0.04%で、**上身頃との縫い線が主な誤差源ではない**。上辺につながる辺は12.81 / 13.38 / 7.82%、その他の辺は13.32 / 13.30 / 9.63%だった。したがって次の対象は、接合部を伸ばすことではなく、フレアを持つ下身頃を曲面へ置く写像である。

外向きの初期広がりだけを0.08～0.24 mで変え、保存済みの初期メッシュに対する**幾何計算のみ**を行った。A/Bは0.22 m付近で約12.3%、後Cは0.16 m付近で約7.5%が最小で、単一の広がり量では3枚を同時に5%以内へ収められなかった。これらは布シミュレーションや3方向の描画結果ではないため、「0.22 mで改善済み」とはみなさない。次は脇の共有頂点を保ったまま型紙辺長に近づく初期配置を試し、布計算と3方向の画像を再検査する。背面・側面は正面イラストからの推定、生地物性は未実測で、市販現物との同条件比較も未実施である。

## 2026-10-06：共有脇を保つ型紙辺長への初期配置補正

上身頃と下身頃3枚を結合した試験用メッシュについて、型紙三角形の各辺を目標長にする反復補正を追加した。上身頃は固定し、脇と腰線の共有頂点は一つのまま扱う。元の配置から最大8 cm以上離れない制限を設け、補正後に面の反転・著しい面積縮小を検査する。**型紙自体の裁断形状は変更せず**、3D布計算の初期状態だけを変える選択式モードである。胴体との非貫通や実素材の収まりを保証するものではない。

| 初期配置と布計算 | A / B / Cの型紙対最終辺長・絶対差95百分位 | 面の反転 |
| --- | ---: | ---: |
| 補正なし、両衝突有効 | 13.32 / 13.28 / 9.51% | 未集計 |
| 幾何補正、元形状への引き戻し係数0.020 | 6.09 / 6.18 / 6.22% | 0 |
| 幾何補正、引き戻し係数0.005 | 5.00 / 5.21 / 5.07% | 0 |

最後の条件では5365辺を照合し、初期配置の移動95百分位は1.04 cm。48フレームの布計算後に[正面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_paper_relaxed_stronger/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_paper_relaxed_stronger/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_fully_welded_paper_relaxed_stronger/pattern_panels_back.png)を確認した。数値は改善したが、裾の暗い不規則な折れと単純化されたシルエットは残る。重ね裾も有効にした[正面](../output/endministrator_lower_shell_flared_v2/drape_paper_relaxed_with_overlays/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_paper_relaxed_with_overlays/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_paper_relaxed_with_overlays/pattern_panels_back.png)では、重ね裾の型紙対最終辺長差はA/B/Cで8.13 / 7.32 / 7.29%。細い縦線や層の収まりが不自然な箇所もある。暫定幾何判定・完成プレビュー承認はともに偽のままにした。

型紙橋渡しの関連テスト17件は通過した。より広い3ファイル試験では24件が通過、7件はWindowsのpytest一時フォルダーに対するアクセス拒否でセットアップに失敗し、コードの合否は未確認。環境側の解消後に再実行する。次は、重ね裾の上辺固定、層間の距離と縦線の発生源を調べる。背面・側面の正解形状、材料値、製品の着用試験がないため、市販品同等とは判定しない。

## 2026-10-06：重ね裾Aの落下する孤立頂点を修復

前回の正面・側面画像で下端から伸びていた細い縦線を調べると、重ね裾Aの境界上に**布面と接続していない2頂点**があった。型紙の三角形化が、ほぼ一直線の境界上の点を飛ばして面を作る一方、飾り縁の曲線は飛ばされた点も参照していた。Blenderの布計算では、その2頂点だけがz=-5.646 m付近まで落下した。これは見た目だけの線の問題ではなく、シミュレーションメッシュの欠損である。

非四角形の飾り布に対し、飛ばされた境界点がある場合は隣接三角形を分割して布面へ接続する処理を追加した。生成時およびBlender読み込み前に、全頂点が面へ接続され、各縫い線境界の区間がちょうど1面に接することを検査する。曲線が多い上身頃に一律の境界制約を課すと既存の4体型出力が失敗したため、この厳密検査は下身頃と飾り布の試験用メッシュに適用し、上身頃の既存サンプリングとは分けた。

新たに生成した[試験用型紙メッシュ](../output/endministrator_lower_shell_flared_v2/panels_boundary_repaired.json)では飾り布A/B/Cの孤立頂点0、境界の非1面区間0。48フレームの布計算と[正面](../output/endministrator_lower_shell_flared_v2/drape_boundary_repaired_verified/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_boundary_repaired_verified/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_boundary_repaired_verified/pattern_panels_back.png)の描画を再実施し、落下した縦線は消えた。重ね裾Aの最低頂点はz=-1.168 mに戻った。数値は[再試験報告](../output/endministrator_lower_shell_flared_v2/drape_boundary_repaired_verified/pattern_panel_drape_report.json)に保存した。

一方、重ね裾Aの型紙対最終辺長差95百分位は旧8.13%から8.53%へわずかに悪化し、B/Cは7.32 / 7.29%。これは孤立頂点を正しく面へ接続した後の数値であり、旧値より実態に近い。層の重なりと折れはまだ不自然で、布の貫通・着用時の動き・実物との比較も未確認。既存の関連テスト18件は通過したが、**完成プレビュー・市販品質の合格ではない**。

## 2026-10-06：重ね裾の固定上辺を滑らかに配置

修復後の布メッシュについて型紙辺長との差を「固定上辺」「上辺に接する辺」「自由端側」に分解した。旧配置の最終3Dでは、固定上辺だけの絶対差95百分位がA/B/Cで15.10 / 15.95 / 11.18%だった。一方、自由端側は5.55 / 5.24 / 6.56%で、主な問題は上辺の各頂点をばらついた三角形法線に沿って**物理寸法換算1.1 cm（シーン内0.022 m）**押し出していたことと分かった。

試験モードで固定上辺を下身頃の滑らかな外向き方向へ**物理寸法換算0.9 cm（シーン内0.018 m）**置き、上辺から8 cmの範囲で面法線方向へ連続的に移行させた。型紙も実測生地も変更していない。両布の衝突を有効にした同じ48フレームの布計算結果は次の通り。

| 重ね裾 | 旧・固定上辺の最終差95百分位 | 新・固定上辺の最終差95百分位 | 旧→新・全辺の最終差95百分位 | 新・全辺の最大差 |
| --- | ---: | ---: | ---: | ---: |
| A | 15.10% | 3.55% | 8.53→5.54% | 13.84% |
| B | 15.95% | 3.55% | 7.32→4.95% | 17.36% |
| C | 11.18% | 4.48% | 7.29→6.73% | 18.16% |

95百分位だけでは局所的な大きい変形を隠すため、最大差も[試験報告](../output/endministrator_lower_shell_flared_v2/drape_overlay_smooth_mount_verified/pattern_panel_drape_report.json)に記録した。[正面](../output/endministrator_lower_shell_flared_v2/drape_overlay_smooth_mount_verified/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_overlay_smooth_mount_verified/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_overlay_smooth_mount_verified/pattern_panels_back.png)を旧試験と比較したところ、線の破綻は再発していないが、見た目は大きく変わらない。特に層の端の暗い折れ、全体の単純化された形、実生地の動きは残る。関連テスト18件は通過。寸法の改善だけで市販衣装と同等とは判定しない。

## 2026-10-06：採寸値から作った身体代理との接触検査

これまでの布計算は`free-hang`で、身体との接触を外していた。同じ型紙・材料仮値・初期配置で`measurement-standin`を有効にし、バスト83・ウエスト66・ヒップ91 cm等から作った胴体・脚代理を衝突対象へ加えた。これは人の3Dスキャンではなく、断面の楕円比率や高さ位置も仮定である。

下身頃1900頂点と代理表面の距離を計ると、最短7.08 cm、5百分位8.11 cm（型紙寸法への換算値）で、1 cm以内の頂点は0だった。下身頃の最終メッシュ座標は`free-hang`と完全一致し、布の型紙対辺長差もA/B/C=5.00 / 5.21 / 5.07%、重ね裾=5.54 / 4.95 / 6.73%で変わらない。[身体代理ありの正面](../output/endministrator_lower_shell_flared_v2/drape_measurement_contact_audit_v2/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_measurement_contact_audit_v2/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_measurement_contact_audit_v2/pattern_panels_back.png)もほぼ同じ見た目だった。距離は符号なしなので貫通検査ではないが、少なくともこの条件で**下身頃への身体接触は観測されていない**。ゆとりのあるコートでは接触がないこと自体を失敗とはできず、この試験だけでフィット・可動・着心地を評価することもできない。

今後の`measurement-standin`報告には下身頃の表面距離と1 cm以内の頂点数を自動記録する。真の着用比較には着用者の腰・ヒップ・太ももの断面、コートの意図したゆとり、実布の曲げと重さ、仮縫いの写真が必要。関連する型紙・代理形状のテスト20件は通過した。市販衣装との同条件の着用比較は未実施である。

## 2026-10-06：重ね裾の取付順と合印の再検査

従来の縫製説明は、下身頃を本体裾へ縫った**後で**飾り裾の上辺を仮止めする順番だった。これでは上辺の生地端をどの縫い目で始末するか曖昧になる。試作用の手順を「下身頃の脇を縫う→飾り裾を下身頃の表側上辺へ合印で仮止めする→本体裾と同じ接合線で三枚重ねを縫う」に改めた。自由端のほつれと三枚重ねの厚み・針通りは試布と仮縫いで確認し、硬質装飾をこの縫い目へ挟まない。**この取付方式も正面資料だけからの設計仮説**であり、市販品の実際の縫製方式と同一だとは断定しない。

型紙検査は、飾り裾側だけでなく下身頃側にも「重ねA/B/C」の記号と1/4・3/4合印があることを確認するよう強化した。片側の合印を除いた試験は警告を出し、通常の管理人型紙は警告なし。縫製手順の順序と三枚重ねの記述、関連する型紙・縫製テスト39件を確認した。

2D裁断形状は変更していない。48フレームの布計算を再実行して[正面](../output/endministrator_lower_shell_flared_v2/drape_layer_order_audit/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_layer_order_audit/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_layer_order_audit/pattern_panels_back.png)を比較したが、見た目も型紙対辺長差も前回とほぼ同じ。現在の3Dは飾り裾の上辺を少し離して固定する近似で、三枚重ねの縫い目・厚み・摩擦を再現しない。[報告](../output/endministrator_lower_shell_flared_v2/drape_layer_order_audit/pattern_panel_drape_report.json)にも`three_layer_seam_topologically_simulated: false`を明記した。したがって今回の手順修正を3Dによる縫製品質の証明とは扱わない。

三枚重ねの試作手順に合わせ、本体裾・下身頃・飾り裾の接合部で縫い代幅が食い違う場合も型紙検査で警告するようにした。4体型の出力テストは通過し、基準体型のA/B/Cはすべて三層とも1.0 cmで一致した。[型紙メッシュの出力](../output/endministrator_lower_shell_flared_v2/panels_seam_allowance_audit.json)にも各層の幅を記録した。これは縫い代の数値と縫い線の整合検査であり、裁断線の実測、重ね厚によるズレ、縫製可能性の実証ではない。

## 2026-10-06：飾り裾の取付クリアランスを広げた対照試験（単位訂正）

固定式プレビューの旧コードは、上辺を下身頃から**シーン内0.018 m＝型紙の物理寸法換算0.9 cm**離していた。前回の説明ではこれを1.8 cmと誤記した。シーンは型紙1 cmを0.02 mへ拡大しており、この換算を試験値にも適用する。1.3 cmの試験は縮小ではなく**0.9 cmからの拡大**である。最初の試験では上辺だけを変え、次の試験では配置補正側の最小間隔も同じ1.3 cmへ揃えた。既定値は旧条件と一致する0.9 cmへ設定した。

| 上辺の距離と配置補正 | 飾りA/B/Cの最終・型紙辺長差95百分位 | 同・最大差 | 正面・側面・背面の視覚確認 |
| --- | --- | --- | --- |
| 0.9 cm、従来 | 5.54 / 4.95 / 6.73% | 13.84 / 17.36 / 18.16% | 境目と裾の暗い折れが残る |
| 1.3 cm、配置補正は0.9 cm | 5.56 / 5.03 / 6.89% | 13.69 / 15.71 / 20.41% | 明瞭な改善なし |
| 1.3 cm、配置補正も1.3 cm | 6.39 / 5.38 / 8.33% | 14.22 / 16.71 / 20.57% | 明瞭な改善なし |

最後の条件の[正面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_13mm_coupled/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_13mm_coupled/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_13mm_coupled/pattern_panels_back.png)と[数値報告](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_13mm_coupled/pattern_panel_drape_report.json)を保存した。1.3 cmでは固定上辺そのものの辺長差もA/B/Cで5.14 / 5.14 / 6.47%となり、従来の3.55 / 3.55 / 4.48%より悪い。したがって離隔の**拡大**はこの条件では品質改善にならない。現在の飾り布は別メッシュの上辺固定であり、三枚重ねの接合はトポロジーとして存在しない。実素材の厚み・曲げも未測定である。市販衣装の完成プレビューとは扱わない。

## 2026-10-06：実際に狭めた条件と同一布計算の縫合ばね

単位訂正後、上辺と配置補正をともに0.7 cmにした48フレーム試験を実施した。A/B/Cの型紙対最終辺長差95百分位は6.05 / 5.53 / 5.96%、最大差は24.55 / 38.90 / 17.06%。[正面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_07cm/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_07cm/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_mount_clearance_07cm/pattern_panels_back.png)では継ぎ目の見た目はほぼ変わらず、Bの局所変形が大幅に悪化した。0.7 cmも既定値へ採用しない。

別の試験モードでは、本体・下身頃が共有する接合頂点と飾り裾上辺の頂点を、**同じBlender布メッシュ内の布面を持たない縫合辺**で対応付けた。A/B/Cに53 / 53 / 89本の縫合辺を作り、いずれも重複なし・布面への所属0を生成時に確認した。これは縫合ばねによる近似であり、三枚の布を同一頂点へトポロジー結合したものではない。三面が一辺を共有する非多様体メッシュは避けた。

48フレーム後の縫合頂点間の隙間95百分位はA/B/Cで0.174 / 0.176 / 0.192 cm。上辺固定式では隙間を測っていなかったため、これだけで前方式より実物に近いとは断定しない。型紙対最終辺長差95百分位は5.98 / 5.53 / 6.16%、最大差は27.17 / 23.13 / 21.62%。[正面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_springs_preflight/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_springs_preflight/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_springs_preflight/pattern_panels_back.png)では、前裾が内側へ巻いて市販衣装の写真に見られる外側への広がりから遠ざかった。[数値・縫合辺の検査報告](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_springs_preflight/pattern_panel_drape_report.json)では完成プレビュー承認を偽のままにした。縫合ばね方式は**試験モードのみ**とし、既定のプレビューへ切り替えない。実布の伸び・曲げ・摩擦、着用者形状、側面・背面の正解が未測定で、市販現物との同条件比較にも達していない。

同じ縫合ばね・型紙で、未実測の硬めの布設定`structured-trial`でも試した。縫合隙間95百分位は0.128 / 0.151 / 0.112 cm、型紙辺長の最大差は16.42 / 16.71 / 19.80%へ下がった。しかし[正面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_structured/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_structured/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_structured/pattern_panels_back.png)でも前裾の暗い折れと単純な形は残る。布設定の数値は実際のコスプレ用生地から測ったものではなく、見た目が少し整っても採用値とはしない。[数値報告](../output/endministrator_lower_shell_flared_v2/drape_shared_cloth_overlay_structured/pattern_panel_drape_report.json)に区別して保存した。

## 2026-10-06：前面の部品欠落を分離する比較

型紙由来の通常プレビューは、旧Blenderモデルに手作業で造形した明灰色の前面パネル・ラペルと、その縁取り計12オブジェクトを非表示にしている。そこで**比較専用モード**でこの12個だけを借りて表示し、下身頃の型紙、布計算、照明、カメラは同じにした。通常の[正面](../output/endministrator_lower_shell_flared_v2/drape_pattern_only_provenance/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_pattern_only_provenance/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_pattern_only_provenance/pattern_panels_back.png)と、比較用の[正面](../output/endministrator_lower_shell_flared_v2/drape_authored_front_detail_comparison_labeled/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_authored_front_detail_comparison_labeled/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_authored_front_detail_comparison_labeled/pattern_panels_back.png)を確認した。

比較用の正面では首から腰にかけての色分けとラペルが戻り、構成上の不足が分かる。一方、側面では手作業パネルが生成身頃から浮き、境界も不自然である。**見た目の一部だけ改善しても型紙と接合が伴っていない。**下身頃A/B/Cの辺長差95百分位は両条件で5.00 / 5.21 / 5.07%、飾りA/B/Cも5.54 / 4.95 / 6.73%で同一なので、布計算を改善した結果ではない。比較用[報告](../output/endministrator_lower_shell_flared_v2/drape_authored_front_detail_comparison_labeled/pattern_panel_drape_report.json)には借用した12オブジェクトの名称と`authored_front_detail_has_generated_pattern: false`を記録し、型紙完成プレビュー・市販品質の合格にはしない。次の製図対象は明灰色の前面パネルとラペルであり、生成身頃の縫い線に沿う2D輪郭・取付合印・試布での接合が必要である。背面の意匠は正面資料のみではなお推定である。

## 2026-10-06：前面明灰色パネルを型紙化し、上身頃の配置歪みを測定

生成済み前身頃の縫い線を取付辺として抜き出し、明灰色の前面パネルを左右それぞれ独立した2D部品にした。縫い線、1 cmの縫い代を付けた裁断線、3か所の合印、取付線、三角形化した試験メッシュを出力する。幅・上下端の形は**正面イラストからの暫定推定**であり、市販衣装から採寸したものではない。4採寸例で輪郭の妥当性と身頃境界への一致をテストした。小さい採寸で、ポリゴン交差の微小な誤差により取付線が20.32 cmしか抽出されない問題を修正し、元の身頃縫い線から直接取るようにした。関連テスト23件が通過。

[試験用型紙データ](../output/endministrator_lower_shell_flared_v2/panels_front_detail_trial.json)を使って48フレームの布計算と三方向描画を実施した。最初の[上身頃・旧配置の報告](../output/endministrator_lower_shell_flared_v2/drape_front_detail_pattern_trial_v3/pattern_panel_drape_report.json)では、新パネルを上身頃に投影すると型紙辺長との差95百分位が左右74.51 / 74.29%、上身頃自身も75.59 / 75.57%だった。したがって問題はパネル単独でなく、旧上身頃を手作業モデルの表面へ押し付ける配置にある。この[正面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_pattern_trial_v3/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_pattern_trial_v3/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_pattern_trial_v3/pattern_panels_back.png)は**製作可能な衣装を示す画像ではない**。

対照として、裾の接合曲線を保ちつつ紙の横・縦寸法を優先して上身頃を立ち上げる`paper-developed-trial`配置を追加した。[同条件の48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_front_detail_paper_developed_trial/pattern_panel_drape_report.json)では、上身頃の型紙辺長差95百分位は左右0.10%、新パネルの投影差は1.78%まで下がった。ただし新パネルの**最大差は19.33%**で局所的なひずみが残る。これは布を別体としてシミュレーションした結果ではなく、計算後の本体面へ0.4 cm離して投影しただけである。実際の縫製・接合・厚みは検証していない。[正面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_paper_developed_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_paper_developed_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_paper_developed_trial/pattern_panels_back.png)の視覚確認でも、襟元・袖ぐり・側面の接続、裾の折れに破綻が残る。市販品の写真に見えるラペル、異素材の切替、金具、背面ディテールにはなお届かない。`paper-developed-trial`は**既定表示へ採用しない**。身体へのフィットや実布の曲げ・摩擦は未検証であり、市販現物同等の承認は引き続き偽とする。

関連3ファイルの23件は全通過。より広い5ファイルの試験では123件が通過したが、7件はWindows上のpytest一時ディレクトリへの`PermissionError`でセットアップに失敗した。コードの合否を確認できなかった7件を成功件数へ含めない。別の作業ディレクトリを一時先に指定しても同じアクセス拒否になったため、環境側の権限解消後に再実行する。

## 2026-10-06：前面パネルの取付方式を二通り布計算で比較

上の紙寸法優先配置を共通条件に、前面パネルを独立した布メッシュとして48フレーム計算した。いずれも実際の縫い目ではなく、固定頂点による**取付方法の仮説比較**である。生地の重量・曲げ・摩擦は実測していない。

| 方法 | 固定頂点/片側 | 最終の型紙辺長差95百分位（左右） | 最大差（左右） | 三方向の確認 |
| --- | ---: | ---: | ---: | --- |
| 本体面への静的投影 | 0 | 1.78 / 1.78% | 19.33 / 19.33% | 側面で薄い別レイヤーに見える。布の挙動は未計算 |
| 片側の取付線のみ固定 | 31 | 1.88 / 1.89% | 22.10 / 22.12% | 自由端が外へ浮き、側面に黒い隙間 |
| 全周を固定するアップリケ仮説 | 77 | 3.61 / 3.68% | 19.33 / 19.33% | 自由端の浮きは減るが、細い帯の皺と硬さが残る |

片側固定の[正面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_edge_pinned_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_edge_pinned_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_edge_pinned_trial/pattern_panels_back.png)、[数値報告](../output/endministrator_lower_shell_flared_v2/drape_front_detail_edge_pinned_trial/pattern_panel_drape_report.json)。全周固定の[正面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_perimeter_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_perimeter_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_perimeter_trial/pattern_panels_back.png)、[数値報告](../output/endministrator_lower_shell_flared_v2/drape_front_detail_perimeter_trial/pattern_panel_drape_report.json)。背面は両方式でほぼ同じであり、背面パターンの改善を示さない。

片側だけを縫う想定では前面帯が市販衣装の外観からさらに離れたため不採用。全周固定は端の浮きを抑えるが、実商品がアップリケ構造か、別裁ち切替かは正面資料のみでは確定できない。どちらも縫い合わせた連続メッシュではなく、縫代の折り込み・厚み・洗濯や着用時の耐久は未検証である。次は前面の切替線とラペルを別部品に分け、実物参考に基づく縫製構造と接合寸法を確認する。商用品質の合格判定はしない。

## 2026-10-06：首ぐり縫い線に沿う独立ラペル型紙

[StarCineの女性管理人衣装の商品説明](https://starcinecollectible.com/products/arknights-maria-nearl-cosplay-costume-copy-1)はライトグレーのコート地、グレーの合皮、ダークグレーのデニム風生地、縞ニット、裏地を別素材として挙げる。[CCosplayの商品一覧](https://www.ccosplay.com/arknights-endfield-costume-endministrator-women-cosplay-suit)でもコートと襟・肩・腕・背面の付属品を別に列挙する。いずれも販売者の記載で、布の物性・実物の縫い線・品質を計測した資料ではない。この積層との差を埋める対象として、前身頃の首ぐり曲線を取付辺とする左右2枚のラペル試作を追加した。各部品には独立した縫い線、1 cm縫代の裁断線、3合印、折り位置未確定の注記がある。4体型で身頃の首ぐりとの境界一致、輪郭の妥当性、布メッシュの境界接続を検査し、関連テスト23件が通過した。

[小さいラペル](../output/endministrator_lower_shell_flared_v2/panels_front_lapel_trial.json)と、自由端を胸側へ広げた[対照型紙](../output/endministrator_lower_shell_flared_v2/panels_front_lapel_trial_v2.json)を48フレームの同じ条件で比較した。小さい試作の最終・型紙辺長差95百分位は左右10.24 / 10.27%。広げた試作は11.44 / 11.43%へ悪化し、三方向画像でも肩の小さなタブに見え、商品写真や元の正面絵の胸元を十分に再現しない。[広げた試作の正面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_chest_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_chest_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_chest_trial/pattern_panels_back.png)。

広い版の辺長差は布計算**前**から95百分位11.22%だったため、実測値のない生地剛性を上げて誤魔化さず、首ぐり15頂点を固定したまま紙の辺長に近づける初期配置補正を試した。[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_paper_relaxed_trial/pattern_panel_drape_report.json)では初期差2.38%、最終差左右2.45 / 2.54%、最大差4.01%となった。[正面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_paper_relaxed_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_paper_relaxed_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_paper_relaxed_trial/pattern_panels_back.png)を確認したが、ラペルの折返し・襟元の重なり・肩と袖ぐりの接続は依然不自然で、数値の改善ほど外観は良くない。縫製線は固定辺の代理であり、折り癖・芯地・接合部の耐久は未再現。背面資料と実物の布・付属品がないため既定の完成プレビューに採用しない。

## 2026-10-06：身体代理を有効にした上身頃の距離検査

ラペル試作と同じ紙寸法優先配置で、採寸値から生成した胴体・脚代理を衝突対象に加え、48フレームを再実行した。[計測報告](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_measured_standin_trial/pattern_panel_drape_report.json)では上身頃A/B各657頂点の胴体代理への最短距離が8.49 cm、5百分位が9.63 cm、後ろ身頃Cの最短距離が7.67 cm、5百分位が8.12 cm。下身頃1900頂点の最短距離も7.11 cmで、上・下とも1 cm以内の頂点は0だった。距離は**符号なし**で、貫通の有無を示さない。自由落下条件と身体代理あり条件の下身頃A/B/Cの95百分位変位・型紙辺長差は表示桁で同一であり、この代理は今回の布挙動を実質制約していない。[正面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_measured_standin_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_measured_standin_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_measured_standin_trial/pattern_panels_back.png)も確認した。

これはコートのゆとりが大きすぎる可能性、代理体型と衣装の位置・形が合っていない可能性、または両方を示す。採寸値だけから作った代理を実際の着用者の体型として扱わない。現条件で「身体との接触を検証済み」「フィットが良い」とは言えない。着用者の胸・肩・背幅、コートの仕上がり寸法、仮縫いの着用写真が必要である。

## 2026-10-06：上身頃の全固定を外した対照試験

従来の布計算では上身頃A/B各657頂点・背Cの1029頂点をすべて固定していた。これは上身頃が動かない展示用の条件であり、身体代理に合うかどうかの検査には不適切である。対照モード`neck-shoulder-anchor-trial`を追加し、上端から5 cm以内のA/B各21頂点・Cの77頂点だけを固定して、同じ型紙・身体代理・未実測の布設定で48フレーム計算した。型紙の裁断寸法や既定モードは変えていない。

| 条件 | 上身頃A/B/Cの身体代理までの最短距離 | 下身頃の最短距離 | 上身頃の最終対型紙辺長差95百分位 | 上身頃の同最大差 |
| --- | --- | ---: | --- | --- |
| 全固定 | 8.49 / 8.49 / 7.67 cm | 7.11 cm | 0.10 / 0.10 / 0.05% | 0.15 / 0.15 / 0.07% |
| 首・肩の上端だけ固定 | 2.42 / 1.50 / 5.27 cm | 1.50 cm | 0.71 / 0.71 / 0.80% | 28.64 / 29.66 / 2.75% |

[首・肩だけ固定した試験の正面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_upper_released_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_upper_released_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_upper_released_trial/pattern_panels_back.png)と[数値報告](../output/endministrator_lower_shell_flared_v2/drape_front_lapel_upper_released_trial/pattern_panel_drape_report.json)を保存した。前身頃が身体代理に近づいた一方、どの上身頃にも1 cm以内の接触頂点はなく、袖ぐりに大きな空きと前身頃の垂れが残る。正面では下裾の外向きの広がりも弱まり、外観は改善していない。前身頃A/Bの最大辺長差は約29%だが、長さ0.279 cmの非常に短いメッシュ辺で生じ、絶対誤差は0.080 / 0.083 cm。1 cm以上の辺では95百分位0.66 / 0.68%である。大きな割合だけを実布の深刻な伸びと解釈しない。一方、袖・肩・脇の構造的接合がモデル化されていないことと、初期配置・型紙寸法の問題は残る。距離は符号なしで、実際の人体スキャンに対するフィットでもない。したがってこの実験モードを完成プレビューへ採用しない。次は上端だけでなく袖ぐり・肩線の実際の縫合拘束と、身頃の高さ別紙寸法を検査する。

## 2026-10-06：上身頃の高さ別・紙幅監査

シミュレーションの胴体代理と同じ胸・ウエスト・腰上部の高さで、前A/B・後Cの**縫い線に囲まれた紙の水平幅**を直接測る検査を追加した。4体型で左右対称と合計値を検査し、関連25テストが通過した。基準体型（胸83・ウエスト66・腰91cm）の[監査JSON](../output/endministrator_lower_shell_flared_v2/bodice_width_audit.json)は次のとおり。

| 高さ | 前A / 前B / 後Cの紙幅 | 開いたコートの紙幅合計 | 身体代理の参照寸法 |
| --- | --- | ---: | ---: |
| 胸代理 | 26.48 / 26.48 / 42.67 cm | 95.62 cm | 83.00 cm |
| ウエスト代理 | 29.56 / 29.56 / 50.84 cm | 109.95 cm | 66.00 cm |
| 腰上部代理 | 30.18 / 30.18 / 51.35 cm | 111.70 cm | 78.50 cm |

この合計は**開いた3枚の紙幅**であって、完成服の胴回りでも着用ゆとりでもない。前開きの隙間・重なり、ダーツの縫い取り、縫代を折る効果や布の厚みを適用していない。胸からウエストへ紙幅が約14 cm増える形が、身体代理から離れる一因である可能性はあるが、実商品と同じシルエットの適正値は分からない。数値だけで紙幅を縮めず、側面・背面の資料、完成寸法、仮縫いで分量を決める。現時点で「フィット合格」は付けない。

## 2026-10-06：袖山と袖ぐりを最終型紙の境界で照合

生成済みの左右の袖型紙を、縫い線・裁断線・合印を保持したまま布メッシュとして出力した。袖山と、左右の前身頃・後ろ身頃それぞれの袖ぐりを**メッシュ上の連続した境界頂点列**としても出力し、4体型で始終点・境界長・三角形接続を検査した。これは3Dで袖を縫ったことを意味しない。[型紙と監査JSON](../output/endministrator_lower_shell_flared_v2/panels_with_sleeves_trial.json)。

基準体型では袖山の縫い線が左右とも45.770 cm。従来の採寸用計算は片腕の袖ぐり44.268 cmとして、いせ込み余りを1.502 cmと報告する。しかし**完成した前身頃の輪郭**を追うと左右各21.691 cm、後ろ身頃は片側22.205 cmで、片腕の合計は43.895 cm。実際に縫う境界に対する袖山の差は**1.875 cm**である。前身頃の計算用値22.064 cmと実輪郭21.691 cmに片側0.373 cmの差がある。計算用の割る前の前身頃と、ダーツ等を含む最終前身頃の形が一致していない可能性がある。理由を確定するまで縫製許容値を勝手に変更しない。

[48フレームの試験報告](../output/endministrator_lower_shell_flared_v2/drape_exported_sleeve_preflight_trial/pattern_panel_drape_report.json)では、袖型紙のメッシュ検査は通る一方で`pattern_sleeves_rendered: false`と記録した。[正面](../output/endministrator_lower_shell_flared_v2/drape_exported_sleeve_preflight_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_exported_sleeve_preflight_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_exported_sleeve_preflight_trial/pattern_panels_back.png)に見える袖は旧Blenderモデルから借りた造形で、生成型紙から縫合・布計算した袖ではない。3方向とも袖ぐりの空きは残り、外観改善はない。次は最終前身頃の袖ぐり長を基準に袖山のいせ込み配分を再検証し、肩・脇の接合を含む型紙由来袖の3D縫合へ進める。市販衣装のフィット・縫製・耐久の実証とは扱わない。

## 2026-10-06：袖を縫う前の肩先・脇下の隙間と胸ダーツ高さ仮説

型紙由来の身頃の袖ぐり境界を布計算後の3D頂点へ対応させ、前A/Bと後Cの肩先・脇下を測った。[通常の紙高さ配置による48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_sleeve_interface_gaps_trial/pattern_panel_drape_report.json)では、肩先の初期隙間は左右とも7.741 cm、脇下5.743 cm。48フレーム後も肩先7.718 / 7.697 cm、脇下6.341 / 5.822 cmが残った。前後の肩線・脇線はトポロジーとして縫われていない。ここへ袖山だけを引き寄せても、正常な袖付けにはならない。

前身頃の紙の裾位置は後ろより約6.04 cm低く、胸ダーツによる紙上の取り分が含まれる。現在の3Dはそのダーツを縫い閉じず、裾を揃えたまま紙の縦寸法を上へ伸ばしている。原因の切り分けとして、**型紙自体は変更せず**、前身頃の3D初期高さだけをダーツ取り分相当で短くする対照モードを実行した。[正面](../output/endministrator_lower_shell_flared_v2/drape_dart_height_proxy_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_dart_height_proxy_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_dart_height_proxy_trial/pattern_panels_back.png)・[報告](../output/endministrator_lower_shell_flared_v2/drape_dart_height_proxy_trial/pattern_panel_drape_report.json)。初期の脇下隙間は1.071 cmまで縮んだが、肩先は6.208 cm残り、布計算後の脇下も2.324 / 1.404 cm。さらに前身頃の最終対型紙辺長差95百分位は0.71%から16.11 / 16.07%へ大きく悪化し、側面・背面の引きつれも増えた。

この結果は「胸ダーツを閉じた形」を単純な垂直圧縮では代用できないことを示す。対照モードは不採用。胸ダーツの脚を実際の縫合拘束として扱い、前後の肩線・脇線を接合してから袖を付ける必要がある。背面形状・生地物性・実物の縫製構造はなお推定で、市販衣装同等とは判定しない。

## 2026-10-06：胸ダーツ・肩・脇の縫合拘束を分けて検証

基準体型Mの前身頃には左右各2本の胸ダーツがある。型紙境界の脚をBlenderの縫合ばねへ対応させると、約3.50 cm開いた各ダーツ口は48フレーム後に約0.01～0.03 cmへ近づいた。ただしダーツだけでは上身頃の前後がつながらない。[ダーツのみの報告](../output/endministrator_lower_shell_flared_v2/drape_sewn_bust_darts_trial/pattern_panel_drape_report.json)を、縫製仕上がりや胸のフィット合格と解釈しない。

肩線も型紙境界から11組ずつ対応させたが、従来の「前後とも首元固定」では肩先の初期隙間7.74 cmに対し、首側の初期隙間は**33.27 cm**だった。固定された首側は48フレーム後も33.27 cmであり、縫い線を追加しただけでは接続しない。[不採用試作の正面](../output/endministrator_lower_shell_flared_v2/drape_sewn_darts_and_shoulders_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_sewn_darts_and_shoulders_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_sewn_darts_and_shoulders_trial/pattern_panels_back.png)。10 cmを超える初期縫合ギャップをこの固定条件で拒否する前検査を追加し、Blenderで実際に33.27 cmを検出した。BlenderはPython例外でも終了コード0を返す場合があるため、例外表示と成果物の有無で成功を判定する。

上身頃の固定を背中心5頂点だけに減らすと肩線は0.07 cm以内まで閉じたが、脇下は9.52 / 14.35 cmへ開き、背面の布が崩れた。背中の首元77頂点を固定し前A/Bを自由にした対照では、肩線0.04 / 0.07 cm、脇下1.39 / 2.83 cmまで縮んだ。ただし正面で前身頃が身体前面に回らず、背面首元も不自然である。

脇線については、前身頃の生の輪郭長114.644 cmには胸ダーツの長い脚が2組含まれるため、そのまま後ろ身頃の脇線へ縫い合わせてはならない。ダーツ脚を除いた前身頃の有効な脇線は**31.457 cm**、後ろは**31.791 cm**で、差は約0.334 cm。4体型の境界頂点列と縫い線長を検査し、関連テスト28件が通過した。[更新した型紙メッシュ](../output/endministrator_lower_shell_flared_v2/panels_with_side_seams_trial.json)。この差を許す縫合対応は試験用であり、量産許容値の承認ではない。

背首帯固定・胸ダーツ・肩線に加えて脇線も縫った[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_back_band_side_sewn_trial/pattern_panel_drape_report.json)では、脇線ばねの最終ギャップ95百分位は左右0.341 / 0.340 cm、肩先は約0.02 cm、脇下は0.100 / 0.103 cmとなった。上身頃の対型紙辺長差95百分位はA/B/Cで1.58 / 1.46 / 0.82%。しかし[正面](../output/endministrator_lower_shell_flared_v2/drape_back_band_side_sewn_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_back_band_side_sewn_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_back_band_side_sewn_trial/pattern_panels_back.png)では前身頃の面積と位置、襟の皺、裾の広がりが商品写真と異なる。**縫い目間距離が縮んだことは、衣装の見た目・着用性・縫製品質の合格ではない。** 肩と脇はばねで引き寄せただけで頂点を共有する連続メッシュにもなっておらず、袖は旧造形の借用のまま。

身体寸法から首・肩の仮の目印を作る別配置も試した。[報告](../output/endministrator_lower_shell_flared_v2/drape_landmark_sewn_trial/pattern_panel_drape_report.json)では身体代理への接近は増えた一方、肩線の首側に約6 cmの隙間が残り、上身頃の型紙辺長差95百分位がA/B/Cで29.00 / 29.41 / 25.69%へ悪化した。[正面](../output/endministrator_lower_shell_flared_v2/drape_landmark_sewn_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_landmark_sewn_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_landmark_sewn_trial/pattern_panels_back.png)とも着用できるコートには見えず、不採用。目印は実測スキャンでも商品現物の寸法でもない。現時点で有望なのはダーツを除いた脇線の正しい抽出と接合検査であり、完成プレビューの更新ではない。次は前開き・背中心・襟を含む身頃の初期配置を紙の辺長を保ちながら再設計し、型紙由来の袖を接続する。

## 2026-10-06：型紙由来の左右袖を実際の布計算へ入れる試作

[袖を含む生成型紙](../output/endministrator_lower_shell_flared_v2/panels_with_sewn_sleeve_trial.json)から、左右各469頂点・818面の袖、袖山境界、左右の袖下縫い線を抽出した。4体型で境界長と袖下左右の一致を検査し、関連テスト28件が通過した。片袖の袖山45.770 cmに対して、最終身頃の前後袖ぐり境界は43.895 cmで、**1.875 cmのいせ込み差**が残る。この差を袖山の前後へ試験的に割り当て、胸ダーツ・肩線・脇線と同じBlender布メッシュへ袖を追加した。試作モードでは旧手作業モデルの袖を非表示にし、報告上の`pattern_sleeves_rendered`を真、`borrowed_source_sleeve_objects`を空としている。ただしこれは「袖付けが製作可能」と認めた意味ではない。合印の位置合わせ、縫代の厚み、袖山のいせ込み工程は未再現である。

初回の[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_trial/pattern_panel_drape_report.json)では袖山ばねの最終ギャップ95百分位は約0.3 cmだったが、袖メッシュの対型紙辺長差95百分位は左57.82%、右57.05%と大きい。[正面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_trial/pattern_panels_back.png)でも腕に沿わず垂れた。縫合ばねが近づくことと、袖が正しい立体形状になることは別である。

胴体・脚だけの代理では袖を支えられないため、上腕約30 cmから手首約17 cmへ細くなる**名目上の腕代理**を左右へ追加した。これは利用者の採寸でもスキャンでもない。左代理の面法線を外向きに揃え、袖山を固定した初期メッシュの型紙辺長緩和を行った。[布計算前の報告](../output/endministrator_lower_shell_flared_v2/sleeve_geometry_preflight_relaxed3/sleeve_initial_geometry_report.json)では袖の辺長差95百分位が57.23%から25.97%へ減った。強い緩和は面を4～23面裏返したので棄却し、面の反転がない弱い条件のみ試した。袖山への最近点を使った別の初期化は緩和前の差が96.55%へ悪化し面反転も起きたため、不採用。

弱い緩和＋腕代理の[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_relaxed_arm_trial/pattern_panel_drape_report.json)では、最終の型紙辺長差95百分位は左27.33%、右26.68%。袖山の前・後のばねギャップ95百分位はそれぞれ概ね0.26～0.31 cm、袖下は左0.178 cm・右0.456 cm。数値は初回より改善したが、[正面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_relaxed_arm_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_relaxed_arm_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_relaxed_arm_trial/pattern_panels_back.png)では袖がなお下方へ垂れ、前身頃と肩まわりの輪郭は市販衣装の形に達していない。腕代理を仮に置いた結果であり、実着用者へのフィット・貫通・耐久の合格ではない。袖山・袖下はばねで近づけただけで、身頃と共有頂点の連続縫製メッシュではない。生成型紙の袖を表示できたことは進捗だが、**完成プレビューには採用しない**。

## 2026-10-06：袖山近傍の初期配置を追加検証

実アバターとの衝突に切り替えた[対照報告](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_avatar_collision_trial/pattern_panel_drape_report.json)でも、最終の袖対型紙辺長差95百分位は左27.49%、右27.25%だった。名目腕代理での左27.33%、右26.68%と近いため、身体代理の種類だけではひずみを解決できない。これは実人体への適合検証ではない。

袖山曲線の近傍では、同じ紙の横座標から腕方向へ延ばす旧初期配置に加え、紙上で袖山へ射影した点から3D袖山接線に直交する方向へ配置する案を短距離だけ混ぜた。最近点を全袖へ適用する案は面が裏返ったが、5 cmで減衰させる案は面反転せず、[布計算前の報告](../output/endministrator_lower_shell_flared_v2/sleeve_geometry_preflight_normal_trial/sleeve_initial_geometry_report.json)で辺長差95百分位が25.97%から25.72%へ小幅に下がった。減衰を10 cmへ広げる案と強い辺長緩和は、それぞれ3面・9面の反転で棄却した。

採用した初期配置を48フレーム計算した[報告](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_normal_no_pauldron_trial/pattern_panel_drape_report.json)では、袖の最終辺長差95百分位は左26.30%、右26.31%。旧腕代理条件の左27.33%、右26.68%よりわずかに下がったが、25%超のひずみは着用衣装の検証に不適切である。旧モデルの肩当ては生成袖から離れて浮いて見えるため試作表示から除外した。[正面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_normal_no_pauldron_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_normal_no_pauldron_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_pattern_sleeves_normal_no_pauldron_trial/pattern_panels_back.png)を確認すると、袖が両側に現れた一方、身頃の前開き、肩の接続、下裾、背面の穴と皺は商品衣装に遠い。肩当てを消したのは欠品を隠すためではなく、借用部品を型紙由来の成果と誤認させないためである。完成プレビューへはなお採用しない。背面・側面は正面資料からの推定で、物性・仮縫い・摩耗は未測定。

## 2026-10-06：白いインナーが前面を占める原因の切り分け

試作の前A/B身頃の初期メッシュは胸付近で左右それぞれ約0.32～0.53 mの範囲にあり、中央のインナーが広く見える。上身頃は紙の横幅と裾の弧長から配置するが、上端の実物寸法・前開き幅・身体断面は測っていない。前身頃の狭い見え方を、裾ガイドの前開き角度だけで直せるか試した。角度を74°から50°へ狭め、布計算を48フレーム再実行した[報告](../output/endministrator_lower_shell_flared_v2/drape_front_opening_50deg_trial/pattern_panel_drape_report.json)では、前A/Bの最終対型紙辺長差95百分位が1.34/2.63%から1.79/2.90%へ悪化した。[正面](../output/endministrator_lower_shell_flared_v2/drape_front_opening_50deg_trial/pattern_panels_front.png)でも白い中心面はほぼ残り、袖が縮れて見えるため不採用。

次に脇線・裾を動かさず、前端だけを上方ほど最大0.18 m内側へ寄せた。[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_front_edge_taper_trial/pattern_panel_drape_report.json)では前A/Bの最終対型紙辺長差95百分位が**18.21/17.90%**へ急増し、[正面](../output/endministrator_lower_shell_flared_v2/drape_front_edge_taper_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_edge_taper_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_edge_taper_trial/pattern_panels_back.png)の袖も外へ張ったため、この変形も不採用。単純な位置調整では紙の長さと肩・袖付けの制約を破る。次は前開き・肩・袖ぐりを**同時に**満たす立体初期配置と、実際の衣装前開き幅の参照資料が必要。数値を良く見せるために前身頃だけを移動しない。

## 2026-10-06：可視インナーを衝突面にした対照

元の布計算は採寸値から作った胴体代理にだけ衝突させていたため、画面上の白いインナーへコートが潜る仮説を立てた。インナー表面の最近点を調べると、元のモデルの法線は**内向き**で、既知の外側点は負、中心点は正だった。生成された前A/B各657頂点と後Cの1029頂点の初期位置は、いずれもこの符号で**外側**にあり、最近点から少なくとも約0.054 m（A/B）、0.135 m（C）離れていた。よって「初期位置がインナー内部」という仮説は否定された。符号だけで閉じたソリッドへの侵入や最終フィットを検証したことにはならない。

比較用にインナーをそのまま衝突物とすると[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_sweater_collision_trial/pattern_panel_drape_report.json)で前A/B/後Cの対型紙辺長差95百分位は72.39/78.18/64.20%へ悪化した。面を反転した**非表示の衝突専用コピー**を置き、可視インナーは変更せずに再実行しても、[報告](../output/endministrator_lower_shell_flared_v2/drape_sweater_collision_outward_trial/pattern_panel_drape_report.json)では75.73/74.48/81.96%となった。基準の1.34/2.63/1.20%より著しく悪い。[正面](../output/endministrator_lower_shell_flared_v2/drape_sweater_collision_outward_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_sweater_collision_outward_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_sweater_collision_outward_trial/pattern_panels_back.png)でも身頃の激しい折れと穴がある。**どちらの衝突方式も完成表示へ採用しない。** 法線だけが原因ではなく、複数の静的衝突物、開いたメッシュ、初期距離、Clothの衝突設定などを切り分ける必要がある。この試験はインナーを寸法正確な着用物として扱う証拠ではない。

## 2026-10-06：袖山のいせ込み位置を肩先へ寄せる試験

完成した型紙の前袖ぐり21.691 cm・後袖ぐり22.205 cmに対して、袖山の前後各半分は22.885 cm。差は前1.194 cm、後0.680 cmで、合計1.875 cmである。生成時の**未分割前身頃**を使った名目差1.502 cmとは0.373 cm異なる。試作布計算はこれまで袖山の余りを両半分の全長へ比例配分していた。袖下に近い区間をより紙寸法どおりとし、肩先へ向かうほど余りを配分する単調な三次写像を試した。これは正規の合印・実布でのいせ込みが確定したという意味ではない。

[布計算前の報告](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_crown_ease_trial/sleeve_initial_geometry_report.json)では辺長差95百分位が25.72%から25.54%へわずかに下がり、面反転はなかった。しかし[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_crown_ease_trial/pattern_panel_drape_report.json)では左右の袖の最終辺長差95百分位が26.30/26.31%から**27.25/27.29%へ悪化**。前袖山ばねの隙間は約0.27から約0.25 cmへ減った一方、後袖山は約0.32から約0.35～0.38 cmへ増えた。[正面](../output/endministrator_lower_shell_flared_v2/drape_crown_ease_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_crown_ease_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_crown_ease_trial/pattern_panels_back.png)では左右の袖の角度がさらに異なり、市販衣装の袖付けに近づいたとは言えない。既定の比例配分へ戻し、肩先集中は明示的な`crown-localized`試験モードに限る。布の端の長さを合わせる方式だけでは、身頃と袖の立体初期配置を解決できない。

## 2026-10-06：前開き袖ぐりの寸法合わせを完成縫い線へ修正

生成コードは従来、前開きの袖山を**分割前の前身頃**の袖ぐりで合わせていた。実際に裁断する左右の前開きパネルを、型紙確定前後の両方で測ったところ縫い線長は変わっていないが、分割前の代理値だけが片側0.373～1.382 cm長かった。従ってダーツの後工程や3Dメッシュの取り方ではなく、袖の寸法合わせに使う入力そのものの差である。前開きパネルの袖ぐりを生成段階の輪郭で直接測り、その値を袖山目標と完成型紙の整合検査の両方へ渡すよう修正した。5種の襟形状・3体型、管理人の4体型で検査した。

| バスト | 修正前：袖山－完成袖ぐり | 修正後：袖山－完成袖ぐり |
| ---: | ---: | ---: |
| 76 cm | 2.326 cm | 1.493 cm |
| 83 cm | 1.875 cm | 1.496 cm |
| 92 cm | 2.000 cm | 1.499 cm |
| 104 cm | 2.887 cm | 1.504 cm |

[修正後のMサイズ型紙データ](../output/endministrator_lower_shell_flared_v2/panels_with_sleeve_fit_corrected.json)は完成袖ぐり43.895 cm、袖山45.391 cm、余り1.496 cm。これは現在設定したドロップショルダー用の**名目いせ込み**と一致したというデジタル寸法の改善であり、どの布でも家庭用ミシンで縫える、肩が綺麗に出る、腕を動かせるという証明ではない。布の厚み・伸びと合印の位置で仮縫い検証が要る。

新型紙で48フレーム計算した[報告](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_trial/pattern_panel_drape_report.json)では、袖の対型紙辺長差95百分位は旧26.30/26.31%から26.45/26.43%へわずかに悪化。袖山ばねギャップは前約0.26 cm、後約0.32 cmでほぼ変わらなかった。[正面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_trial/pattern_panels_back.png)では袖の方向と身頃の位置は依然として不自然。**型紙の寸法是正は採用するが、3D試作は完成プレビューへ採用しない。** 市販実物との同条件比較、背面資料、実布の仮縫いがなお必要。

## 2026-10-06：計算時間を2倍にした収束確認

袖が左右で異なる角度になる原因が48フレームでは計算途中だからかを切り分けるため、同じ修正済み型紙・身体代理・布設定で96フレームまで計算した。CLIの任意`FRAMES`引数を追加し、既定48フレームは維持した。[96フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_96f_trial/pattern_panel_drape_report.json)では、袖の対型紙辺長差95百分位が48フレーム時の左26.45/右26.43%から**左26.55/右26.51%**へ微増し、前後の袖山ばねの隙間も約0.26/0.32 cmのまま。単に計算を2倍続けても型紙長との整合は改善しなかった。

[正面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_96f_trial/pattern_panels_front.png)では片袖が下へ寄り、もう片袖が外へ残る。[側面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_96f_trial/pattern_panels_side.png)は袖と肩・胴の接続が不自然で、[背面](../output/endministrator_lower_shell_flared_v2/drape_corrected_sleeve_fit_96f_trial/pattern_panels_back.png)にも小さな布の突起と穴が残る。48フレームは一時的な見た目である可能性があっても、96フレームが完成品質へ収束した証拠はない。次は縫い合わせをばねだけで表す構造、初期立体配置、腕・肩の支持と布物性を別々に検査する。長時間計算の画像も完成プレビューへは採用しない。

### 2026-10-06：袖の初期立体配置と辺長の局所診断

修正済みMサイズ型紙を同じ身体代理・縫製設定で再検査した。袖山の紙上長45.391 cm、3D初期配置長43.625 cmに対し、前後の身頃袖ぐりは紙上21.691 / 22.205 cmと3D配置21.690 / 22.204 cmでほぼ一致する。ただし全長の一致は局所的な布ひずみを保証しない。[基準の配置診断](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_regions_v1/sleeve_initial_geometry_report.json)で、袖山縫い線65辺の辺長差95百分位は20.36%、脇下寄り48辺では70.89%、最大98.42%。特に前脇下の短い辺が約20%圧縮され、袖身頃の隣接辺が過度に伸びる。袖山を全点固定したまま内側を緩めるだけでは、この矛盾を除けない。

袖山の固定点を間引く試みは面反転を2～3面生じたため棄却した。次に、袖山への紙上最近点距離から出す3D案内と、同一紙上x列を腕方向へ伸ばす案内を、距離に応じて滑らかに混ぜた。減衰距離10 cmは1面を反転させたため棄却し、7 cmでは面反転なし。[新しい配置診断](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_nearcap_normal_trial/sleeve_initial_geometry_report.json)で初期辺長差95百分位は25.73→24.29%、脇下寄りの95百分位は70.89→61.82%、最大98.42→92.19%。袖山縫い線の20.36%は残る。

同一の48フレーム布条件で[新しい報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_normal_trial/pattern_panel_drape_report.json)の袖最終辺長差95百分位は、旧左26.45 / 右26.43%から左25.56 / 右24.79%へ改善し、最大差も左107.97 / 右97.95%から80.92 / 86.37%へ下がった。[正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_normal_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_normal_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_normal_trial/pattern_panels_back.png)を目視したが、袖は左右非対称で、肩や後ろ身頃に不自然な折れ・突起・穴が残る。数値改善のみ採用し、完成プレビューとしては不採用。特に袖山局所圧縮と脇下伸長の原因は、ばねで近づけるだけの縫い合わせと形状対応を含めて再設計が必要。布の物性、着用体、背面形状はなお推定であり、市販現物同等とは判定しない。

### 2026-10-06：自己衝突の寄与の切り分け

同じ型紙・初期配置・身体代理・48フレームで自己衝突のみ解除した[対照報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_no_self_trial/pattern_panel_drape_report.json)は、袖の最終辺長差95百分位が左24.83 / 右24.98%だった。通常の左25.56 / 右24.79%に対し片側だけ改善し、最大差は左91.51 / 右91.63%へ悪化。[正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_no_self_trial/pattern_panels_front.png)では袖が見かけ上対称に近いが、[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_no_self_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_no_self_trial/pattern_panels_back.png)には身頃と重ね裾の大きな裂け・抜けがある。見た目を整えるためだけに自己衝突を切ることはできない。

さらに袖面だけ自己衝突から外す実験も行った。[報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_sleeve_excluded_trial/pattern_panel_drape_report.json)の袖最終辺長差95百分位は左24.75 / 右25.36%、最大は91.88 / 90.92%で、通常条件より一貫して良いわけではない。[正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_sleeve_excluded_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_sleeve_excluded_trial/pattern_panels_side.png)では肩の欠け、[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_sleeve_excluded_trial/pattern_panels_back.png)では脇の黒い穴が残る。この試験モードはコードから除去し、生成プレビューには採用しない。通常条件でも前後身頃の初期肩端点間隔が7.741 cm、脇下端点間隔が5.743 cmあり、48フレーム後の収束以前に大きく引っ張られている。次は衝突の微調整ではなく、身頃の初期縫い線配置・立体接合を優先する。

### 2026-10-06：上身頃の初期縫い線を事前に近づける試験

前後の肩・脇縫い線の対応点を取り、前身頃の縫い線を背身頃側へ移動してから型紙辺長の緩和を行った。裾の頂点は固定し、面の反転または辺長差95百分位8%超の候補を棄却した。肩・脇縫い線全体の初期隙間95百分位は29.212 cmと想定以上に大きく、縫い線を完全に合わせる案は各前身頃で5面反転。反転なしで許容できたのは移動率25%のみで、隙間は21.929 cmに残った。袖の[布計算前診断](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_upper_prealign_trial/sleeve_initial_geometry_report.json)では、初期辺長差95百分位が24.29→22.35%、袖山縫い線では20.36→13.37%と数値上改善した。

しかし48フレームの[布計算報告](../output/endministrator_lower_shell_flared_v2/drape_upper_prealign_trial/pattern_panel_drape_report.json)と[正面](../output/endministrator_lower_shell_flared_v2/drape_upper_prealign_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_upper_prealign_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_upper_prealign_trial/pattern_panels_back.png)を確認すると、袖は身体の後ろへ寄り、正面の衣装シルエットがさらに悪化した。最終袖辺長差95百分位は左25.56→24.16%、右24.79→23.58%でも、外観の改善を示さない。試験コードは不採用として除去し、画像と数値のみ残した。現行の前後身頃の紙上形状、3D初期位置、縫い線対応を別々に直す必要がある。実物の背面や着用・生地データがない段階で、市販衣装と同等とは言えない。

### 2026-10-06：袖山から内側への配置補正距離を比較

型紙・体型代理・48フレームの布条件を固定し、袖山の最近点法線による初期配置補正が内側へ減衰する距離を7 / 8 / 9 cmで比較した。10 cmは以前の試験で面反転を生じたため採用しない。3条件とも9 cmまでは面反転なく布計算前検査を通過し、初期の袖型紙辺長差95百分位は[7 cm](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_nearcap_normal_trial/sleeve_initial_geometry_report.json)の24.29%から[8 cm](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_nearcap_8cm_trial/sleeve_initial_geometry_report.json)の23.24%、[9 cm](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_nearcap_9cm_trial/sleeve_initial_geometry_report.json)の21.95%へ減った。脇下寄りの95百分位も61.82%から57.56%へ減ったが、なお縫製できる初期形状とは言えない。

[9 cmの48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_trial/pattern_panel_drape_report.json)では最終の袖型紙辺長差95百分位が7 cm条件の左25.56 / 右24.79%から左23.96 / 右23.29%へ減った。最大差は左80.92→73.69%、右86.37→86.29%。[正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_trial/pattern_panels_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_trial/pattern_panels_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_trial/pattern_panels_back.png)を確認したところ、背面の一部の突起は減る一方、袖の左右差、側面の穴、前身頃がインナーより内側に入る問題は残った。初期配置の数値改善として9 cmを試作用に残すが、完成プレビューへは採用しない。旧モデルのインナーはM体型代理より大きく、現状の重ね表示自体が衣装のフィット判定を妨げるため、次の検証では衝突体・可視インナー・紙寸法を一致させる。

### 2026-10-06：借用インナーが衣装評価を隠す問題を分離

同じ試験のBlender保存データで、胸位置z=0.43の断面を調べた。借用した白いセーターの左右範囲は約±0.390 m、前後範囲は-0.431～+0.265 m。一方、M寸法の胴体代理は左右±0.300 m、前後±0.225 mで、元のセーターは代理より横幅約30%、前方向へ約20.6 cm（紙寸法換算で約10.3 cm）大きい。これが黒い前身頃を覆い隠す主因であり、「コートが生成されていない」と「別寸法のインナーが覆っている」は分けて評価する必要がある。これらはメッシュの断面値で、実物のサイズ・着用感の測定ではない。

試験スクリプトに借用インナーを非表示にした診断用の3方向画像を追加し、元の重ね表示も残した。[同条件の報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_panel_drape_report.json)と衣装だけの[正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_shell_only_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_shell_only_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_shell_only_back.png)を確認。前身頃は実際には存在するが、前開きの内側が大きく空き、側面に貫通・裂け、背面肩付近に突起が残る。よって「インナーを隠せば完成」という結論にはならない。診断画像は衣装単体の欠陥を特定するためだけのものとし、完成プレビューにはしない。

借用セーターをX=0.77、Y=0.55へ縮めた[表示だけの対照](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_panels_front_visual_inner_scaled_trial.png)、X=0.80、Y=0.70かつY=+0.06 mへ動かした[対照](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_shell_review_trial/pattern_panels_front_visual_inner_fit_trial.png)もレンダリングした。コートが画面に現れるが、これらは布計算後に別衣服だけを変形した画像であり、型紙・衝突・縫製の改善ではない。着用確認用としては不採用。

さらに生成衣装の布計算済み頂点へ1段の表示専用Subdivisionをかけ、未加工3方向画像も残すようにした。[報告](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_smoothed_review_trial/pattern_panel_drape_report.json)の[平滑化した正面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_smoothed_review_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_smoothed_review_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_nearcap_9cm_smoothed_review_trial/pattern_shell_smoothed_back.png)は面の角張りを減らすが、側面の穴・袖付け・肩の突起は修正しない。表示専用処理は布計算の辺長差や市販品同等判定に使わない。次は身頃と袖の共有していない縫い目と、インナーを覆う寸法の不整合を形状段階で解決する。

### 2026-10-06：袖山局所圧縮の原因と肩ギャップ配分の対照

生成袖山の紙上長は前半22.695 cm・後半22.695 cmで対称だが、3Dの前半最初の6辺は紙寸法の約79～80%に圧縮される。前身頃の袖ぐり自体は局所辺長比0.9998～1.0000で紙とほぼ一致した。原因は袖山を前後身頃の肩先の中点へ接続するため、**約7.74 cm離れて配置された肩先**の補正を袖ぐり全長へ線形に配分していたことである。[局所診断](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_local_armhole_diagnostic/sleeve_initial_geometry_report.json)に辺ごとの比率を記録した。紙の袖山長を単純に増減した問題ではない。

袖山上の肩補正を線形から二乗へ変える[布計算前試験](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_shoulder_quadratic_trial/sleeve_initial_geometry_report.json)では、脇下直近の比率は約0.79→0.95へ改善したが、袖山全体の辺長差95百分位は20.36→25.67%へ悪化。指数1.25の[試験](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_shoulder_power125_trial/sleeve_initial_geometry_report.json)では袖山95百分位が18.30%へ下がったものの、[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_shoulder_power125_trial/pattern_panel_drape_report.json)で左右の最終辺長差95百分位は23.16 / 23.99%と不揃い。[衣装単体正面](../output/endministrator_lower_shell_flared_v2/drape_shoulder_power125_trial/pattern_shell_smoothed_front.png)の前開きに大きな折れ、[側面](../output/endministrator_lower_shell_flared_v2/drape_shoulder_power125_trial/pattern_shell_smoothed_side.png)の袖付けに穴、[背面](../output/endministrator_lower_shell_flared_v2/drape_shoulder_power125_trial/pattern_shell_smoothed_back.png)の肩に突起が増えたため不採用。肩の中点を前寄り25%へ変更した[前検査](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_shoulder_frontbias_trial/sleeve_initial_geometry_report.json)も初期の袖辺長差95百分位21.95→27.42%へ悪化したため不採用。試験コードは線形・中点の基準へ戻した。**肩先の初期配置差を袖山側へ押しつける設計をやめ、身頃側の立体配置と縫い線を再設計する必要がある。**

### 2026-10-06：胸ダーツの取り分を前身頃の初期形状へ反映する試験

[基準の座標診断](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_shoulder_coordinates_v1/sleeve_initial_geometry_report.json)では、前肩先z=0.719 mに対して後肩先z=0.623 m、前脇下z=0.318 mに対して後脇下z=0.205 m。前身頃の裾からの紙上高さが後より約6.04 cm長いことと整合し、胸ダーツを閉じた立体配置をしないまま裾を揃えることが主因と考えられる。原寸の上身頃初期メッシュは紙に対する辺長差95百分位0.10%（前A/B）で、単純な短縮はこの利点を壊す。

前身頃の**脇寄りだけ**をダーツ取り分相当で下げる[前検査](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_upper_dart_side_v1/sleeve_initial_geometry_report.json)は、脇下の初期隙間5.74→1.02 cm、袖山初期辺長差95百分位20.36→9.40%へ改善した一方、前身頃全体の紙に対する辺長差95百分位0.10→13.95%、最大58.02%へ悪化したため不採用。

次にダーツの2本の脚を頂点対応で閉じる平面回転を試し、先端から9 cm以内の局所メッシュを紙の辺長へ緩和した。[前検査](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_dart_fold_relaxed_local_trial/sleeve_initial_geometry_report.json)では肩先隙間7.74→1.96 cm、脇下5.74→2.79 cm、袖山初期辺長差95百分位21.95→17.13%へ改善。しかし前身頃のダーツ先端周辺で紙の辺長差最大**115.41%**が残った。平面回転だけの最大148.51%からの改善にとどまり、より強い緩和でも115.41%だった。連続した紙面を切れ目のないまま折る問題を無理に平面で解いたためと判断する。

[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_dart_geometric_fold_relaxed_trial/pattern_panel_drape_report.json)の袖最終辺長差95百分位は左18.82 / 右19.05%まで下がったが、右最大102.77%、前身頃A/Bの最終最大115%超が残る。[衣装単体正面](../output/endministrator_lower_shell_flared_v2/drape_dart_geometric_fold_relaxed_trial/pattern_shell_smoothed_front.png)は袖が左右に異なる方向へ伸び、肩に大きな突起。[側面](../output/endministrator_lower_shell_flared_v2/drape_dart_geometric_fold_relaxed_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_dart_geometric_fold_relaxed_trial/pattern_shell_smoothed_back.png)も完成形に遠い。数値の一部が改善しても見た目・局所ひずみで不合格のため、これらの試験モードと平面折り関数はコードから除去した。次はダーツ周辺に実際の立体逃げを持つメッシュ、または衣服専用の縫製シミュレーターでの布配置が必要で、実布の仮縫いを代替するものではない。

### 2026-10-07：前ファスナー身頃と袖山の合印を直接照合

生成型紙を調べると、片側1枚の前ファスナー身頃でも左右対称の脇線・袖ぐり合印規則を流用していた。M体型の前パネルに脇側の印だけでなくファスナー開口側の不要な脇印があり、袖は前後の袖山3印でなく既定の2印になっていた。後ろ身頃の2本目の印も、肩方向へ0.8 cm進めるべきところを、袖側だけ脇方向へ0.8 cm戻していた。印の本数が合っていても縫合位置が異なる問題である。

前ファスナーの実際の脇下→肩先輪郭に前袖ぐり印を1本、真の脇線に脇印を1本のみ置き、袖山に前1本・後ろ2本を割り当てた。後ろの2本目は身頃と袖の両方で脇下から肩方向へ0.8 cmに統一した。[新しい型紙データと2D合印監査](../output/endministrator_lower_shell_flared_v2/panels_with_validated_notches.json)で、前A/Bの袖ぐり印は各1本、後ろの左右は各2本、袖山は各3本を縫い線の弧長で照合した。M体型の前位置は脇下から9.761 cm、後ろ2位置は9.992 / 10.792 cm。4体型の生成型紙と関連49件のテストが通過した。これは紙上の印合わせであり、いせ込み工程・実布の伸び・着用時の見た目を証明しない。

合印修正前の同一メッシュ設定による[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_sewing_notches_corrected_48f/pattern_panel_drape_report.json)と衣装単体の[正面](../output/endministrator_lower_shell_flared_v2/drape_sewing_notches_corrected_48f/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_sewing_notches_corrected_48f/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_sewing_notches_corrected_48f/pattern_shell_smoothed_back.png)を確認。合印は布の物理メッシュへまだ拘束として入力しておらず、この試作画像は直前の布形状と同じである。前開きの空き、側面の穴、背面肩の突起が残る。修正した型紙は縫製情報として有用だが、3Dの完成プレビューや市販品との同等判定へは採用しない。

### 2026-10-07：合印より脇側にいせ込みを置かない布計算の対照

型紙で照合した合印を布計算の袖山弧長写像にも使い、脇下から前印9.761 cm、後ろの肩寄り印10.792 cmまでは紙の長さを維持し、余り約1.50 cmを袖山の頂点側へ配分する`notch-anchored`対照モードを作った。無印の均等配分から切り替えると、[初期配置報告](../output/endministrator_lower_shell_flared_v2/drape_notch_anchored_48f_trial/sleeve_initial_geometry_report.json)の袖辺長差95百分位は21.95→22.56%へ悪化、袖山境界だけなら20.36→19.27%に改善した。脇下寄りの95百分位は57.56→57.52%でほぼ不変。袖山の一部だけ良くても全体のひずみは解決していない。

[48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_notch_anchored_48f_trial/pattern_panel_drape_report.json)の最終袖辺長差95百分位は左23.96→23.74%、右23.29→24.49%で左右が一貫しない。衣装単体の[正面](../output/endministrator_lower_shell_flared_v2/drape_notch_anchored_48f_trial/pattern_shell_smoothed_front.png)では袖の左右対称性と背面の[全体形](../output/endministrator_lower_shell_flared_v2/drape_notch_anchored_48f_trial/pattern_shell_smoothed_back.png)が一部改善して見えるものの、肩の裂け、[側面](../output/endministrator_lower_shell_flared_v2/drape_notch_anchored_48f_trial/pattern_shell_smoothed_side.png)の欠け、後ろ裾の折れが残る。実布のいせ込みや着用動作を模したものではなく、既定表示へは採用しない。印に忠実な仮縫い配置の比較モードとしてのみ保持する。

[総合監査](../output/endministrator_lower_shell_flared_v2/commercial_gap_audit_20261007.json)へ、この新しい型紙由来の上身頃・袖試作を旧素材感度試験とは別欄で追加した。2D合印照合は真だが、袖と身頃は共有頂点で接続せず、実測生地物性もなく、商用品質の承認は偽。市販品同梱一覧との粗い3D部品照合でも「しずく形の飾り」と「髪飾り」は不足したままである。総合監査は購入品の着用試験ではなく、商品写真との外観一致を自動認証しない。

修正後のM体型を[印刷用型紙PDF](../output/endministrator_notch_print_qa/170a216c7bd8.pdf)と[製作仕様書PDF](../output/endministrator_notch_print_qa/170a216c7bd8_specification.pdf)へ再出力した。型紙はA4・78ページ、仕様書は7ページ。Popplerで袖の該当タイル2ページと仕様書全7ページを画像化し、選んだページについて日本語ラベル、裁断線／縫い線、赤い合印、表の改行・欠けを目視した。確認範囲内に明らかな文字切れはなく、袖山の赤い合印を確認した。全78ページの位置合わせ、印刷機の100%スケール、実裁断後の合致を確認したものではない。

### 2026-10-07：通常の製作前検査にも袖付け合印の照合を追加

試作パネル出力だけが合印を検査していても、通常の型紙PDF作成経路が誤った合印を「デジタル検査通過」と扱う可能性があった。管理人（女性）の前開き身頃2枚・後ろ身頃1枚・袖2枚が揃っているか、実際の縫い線上に前1本・後ろ各2本・袖山各3本があり、脇下からの弧長で対応するかを共通の検査関数に集約し、製作前品質レポートのブロッカーに接続した。袖の前印を1 cmずらした回帰テストでは`digital_ready=False`になり、3体型の正常生成と合わせて関連46件のテストを通過した。これも**紙上での位置対応**の検査であり、実布の縫い上がり・袖の運動性を保証しない。

実布の抜けを防ぐため、仕様書の仮縫い検査票には袖山のいせ込み・波打ち・左右差を本番生地と同条件で確認する項目を追加した。チェック欄を追加しただけで試験済みにはならない。

背面・側面の定性比較として、[GameBanana上のファン制作3方向レンダー](https://gamebanana.com/mods/651648)も閲覧した。後中心に明るいグレーの長い面、黒い側面、黄色の縦方向アクセント、複数の吊り帯が見える。一方、現在の型紙由来3D試作の後ろはほぼ単色で裾に裂けや折れがある。この画像は**公式資料・実測データではない**ため寸法の根拠には採用せず、背面の切替と装飾が不足していることを見落とさないための参考に限る。市販現物の縫製構造が同じだと主張しない。

新しい[共通合印検査後のパネルデータ](../output/endministrator_lower_shell_flared_v2/panels_after_production_gate.json)で、既定の均等いせ込み条件を48フレーム再計算した。[報告](../output/endministrator_lower_shell_flared_v2/drape_production_gate_regression_48f/pattern_panel_drape_report.json)の袖の型紙辺長差95百分位は左23.96%・右23.29%で従前基準と一致し、合印の**検査追加だけで3D形状が良くなったわけではない**。[正面](../output/endministrator_lower_shell_flared_v2/drape_production_gate_regression_48f/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_production_gate_regression_48f/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_production_gate_regression_48f/pattern_shell_smoothed_back.png)を目視し、前開きが広すぎる、側面の身頃下端と裾が途切れる、後ろ肩に浮いた小片が出る問題を再確認した。引き続き完成表示へは採用しない。

### 2026-10-07：体型幅を広げた前面切替・襟・脇縫い線の検証

管理人の型紙から3D用パネルを作る経路を、バスト68〜116 cmの複数体型へ広げて実行した。従来の後ろ肩先判定は全幅の28%という閾値で、バスト96 cm・ヒップ118 cmの正常な肩線18.36 cm（全幅66 cmの27.8%）を見落としていた。肩線と袖ぐりを別に判定できる20%へ直し、輪郭と合印の対応を回帰テストで確認した。後ろ下身頃の試作幅を52 cmで頭打ちにする設定も、大きい体型で本体裾との比率が1.37倍となって接合前に止まる原因だった。接合時には実際の本体裾幅へ再製図するため、仮の頭打ちを外した。

前面の明灰色切替パネルは、初期の9.5 cm幅が小柄な体型で胸ダーツ先端のくぼみを横切り、3D用メッシュが縫い線の端点を失った。試作幅を8.5 cmにするとその体型の輪郭が閉じ、厳密境界メッシュを作れる。さらに前開き縁の検索帯が3 cmしかなく、体型によって本来約54.8 cm続く取付線のうち31.8 cmしか拾えなかった。実際のパネル内側に収まる5.5 cmまで検索し、バスト96 cm・ヒップ118 cmでは50 cm超の連続取付線を検証した。襟の推定自由端が本体輪郭の外へ最大0.12 cm²出る体型では、その小領域だけ本体輪郭で切り取り、0.5 cm²または面積0.5%を超す本当の逸脱は引き続き失敗させる。これらは試作前面パネルの形状整合であり、市販衣装の切替構造を確認したものではない。

バスト116 cm・ヒップ128 cmの上身頃では、前後脇縫い線に片側**0.95 cm**の差が残った。既定の汎用縫合警告は1.5 cmまで許容するが、この中肉ツイル想定のコートをそのまま本番裁断して良いとは判断できない。管理人専用の0.5 cm超ブロッカーを製作前品質レポートと3Dパネル出力へ追加したため、この体型は今は**未対応として止まる**。対応範囲を隠して広げず、ダーツ処理または脇線の再製図で差を実際に減らす必要がある。バスト68・72・83・96 cm等の成功ケースと拒否ケースを回帰テストに追加した。

修正後のM型紙から[3D用パネル](../output/endministrator_lower_shell_flared_v2/panels_front_detail_width85.json)を再生成し、[48フレーム布計算](../output/endministrator_lower_shell_flared_v2/drape_front_detail_width85_48f/pattern_panel_drape_report.json)と衣装単体の[正面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_width85_48f/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_width85_48f/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_front_detail_width85_48f/pattern_shell_smoothed_back.png)を確認した。前面切替の試作幅を変えても、広すぎる前開き・肩周りの裂け・裾の接続不良といった主問題は解消しない。3D試作を完成品プレビューへは昇格しない。

### 2026-10-07：背面の色切替の表示破綻を分離

参考のファン制作3方向レンダーには、後ろ中心の明灰色面と黄色の縦アクセントが見える。手作業造形の旧[背面](../output/endministrator_authored_v22/endministrator_back.png)にはその大きな色面がないため、背面**推定デザイン**として任意の `back-panel-trial` モードを追加した。最初の重ねメッシュ版は、灰色面と暗色の厚み付きシェルが交差し、裾に黒い細片が出た。法線方向へ離しても細片が残ったため、重ねメッシュ案は不採用とした。

次に同じ連続したシェルの面へ灰色素材を割り当て、縫い目と黄色アクセントを別部品にした。[正面](../output/endministrator_authored_back_integrated_trial/endministrator_front.png)・[側面](../output/endministrator_authored_back_integrated_trial/endministrator_side.png)・[背面](../output/endministrator_authored_back_integrated_trial/endministrator_back.png)の3方向を確認し、重ねメッシュ由来の裾の黒い細片は解消した。一方、色切替境界はメッシュ分割に沿った階段状で、背面構造は型紙・布計算に接続していない。[GLB](../output/endministrator_authored_back_integrated_trial/endministrator_authored_costume.glb)の構造監査は82,692三角形・14素材・19テクスチャで、スキンと関節ウェイトはなく `vrchat_certified=false`。見た目の参考試作としてのみ残し、VRC完成衣装相当や公式背面の確定形とは扱わない。

脇線は、汎用の長さ計算を実際に縫う輪郭区間の長さと照合した。バスト83 / 96 / 104 / 116 cmの順に前後差は−0.334 / +0.336 / +0.275 / +0.948 cmで、汎用計算と実区間計算は各ケースで一致した。大きい体型の0.95 cm差は縁検出の誤判定ではなく、紙上で縫う長さの差である。無理に下辺やダーツを移動して帳尻を合わせると前丈・裾・相手パネルも変わるため、現時点では自動修正せず製作前に停止する。5体型を含む[総合監査](../output/endministrator_lower_shell_flared_v2/commercial_gap_audit_20261007_extended.json)でも、バスト116 cmは `digital_ready=false`、市販品との同等性は未確認となった。関連テストは60件通過。

背面色切替の試作 `.blend` を既存の試着用リグへ通し、[静止姿勢](../output/endministrator_rigged_back_integrated_trial/endministrator_rigged_rest.png)と[腕を下げた姿勢](../output/endministrator_rigged_back_integrated_trial/endministrator_rigged_arm_pose.png)を確認した。腕は追従するが、[試着GLB](../output/endministrator_rigged_back_integrated_trial/endministrator_rigged_fitting.glb)の構造検査は衣装だけで72,908三角形・4素材・スキン1個で、動作時の貫通・Unity/VRChatの検査は未実施。追加した背面表現が軽量なVRC衣装になったと誤認しない。ソースのコート連続シェルは評価後約8,112面を占めるため、次はディテールを失わない範囲の形状整理を別試験で行う。

### 2026-10-07：身頃袖ぐりの計測終点を修正

広い体型範囲を調べる24ケースの決定的な試行で、11ケースのみが3Dパネル出力を完了した。残りは主に前身頃の裾接合線がウエストダーツで分断されること、および前後脇縫い線の長さ差による拒否であり、合印が対応しないケースも1件あった。これは無作為抽出した体型の通過率であって、一般ユーザーの成功率を表すものではない。

合印の失敗ケース（B84/W65/H95/身長148 cm）は、後ろ身頃の実際の袖ぐり長20.582 cmに対して、旧合印計算が最後の約1.10 cmの丸い部分を「脇線」と誤判定し、20.087 cmで計測を止めたため、袖山の後ろ印が約0.50 cmずれていた。脇下高さの明示的な頂点が輪郭上に一意に存在するときは、その頂点を終点にするよう修正した。改めて試行すると合印検査は通過したが、**同体型は脇線差0.79 cmで別の検査により不合格**である。合印の修正だけで全体を裁断可能と見なさない。関連の一時ファイル不要な59テストは通過した。`tests/test_notches.py` 全体は、この環境で pytest の一時ディレクトリへのアクセスが拒否されるため実行できなかった。

### 2026-10-07：ウエストダーツを閉じた後の裾接合長

従来は身頃裾の水平縫い線がダーツの口で分断されると、下身頃の接合を一律に拒否していた。管理人の構造用下身頃に限り、裾の隙間が深さ5〜20 cm・両脚差0.1 cm以内の閉じるダーツであることを輪郭上で確認し、**ダーツの口の幅を除いた水平縫い線長**へ下身頃の上辺を合わせるようにした。合印の1/4・3/4位置も口を飛ばした実際の縫い線上へ移した。たとえばB76/W54/H87では左右の前身頃裾と各下身頃上辺が28.3 / 28.3 cmで一致し、3組とも裾接合警告は出ない。B68/W47/H70の狭い後ろダーツ、B96/W67/H100の複数ダーツでも紙上の接合を確認した。単なる切れ目や脚長の違う隙間は拒否するテストを追加した。

同じ乱数固定24体型で、**紙のデジタル製作前検査**は11件通過・13件がフィット／脇線等の明示的なブロッカー・生成時例外0件となった。修正前は10件通過・12件ブロッカー・2件生成時例外であった。24体型は市販サイズ分布の標本ではない。3Dパネル試作はダーツで分割された裾のメッシュ接合に未対応のため、その24件中の出力完了数は依然11件であり、2D接合が通ったことを3D完成と混同しない。ダーツを縫い閉じた際の下身頃の面形状と実布の裾波打ちは仮縫いで確認する必要がある。

M体型の[再出力パネル](../output/endministrator_lower_shell_flared_v2/panels_hem_dart_regression.json)を同じ48フレーム布条件で計算し、[報告](../output/endministrator_lower_shell_flared_v2/drape_hem_dart_regression_48f/pattern_panel_drape_report.json)と衣装単体の[正面](../output/endministrator_lower_shell_flared_v2/drape_hem_dart_regression_48f/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_hem_dart_regression_48f/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_hem_dart_regression_48f/pattern_shell_smoothed_back.png)を確認した。Mの既存形状は変わらず、袖の最終95百分位辺長差は左右23.96 / 23.29%、肩・脇下の端点隙間も前回と同値である。前開きが大きく空く、側面に穴、背面肩に小片が浮く問題も残る。紙の縫い線修正を3D衣装品質の改善と偽らない。

### 2026-10-07：衣装試着版の部分的な軽量化対照

手作業造形の背面色切替版を骨付きGLBへ変換すると衣装単体で72,908三角形だった。細い金具・縁飾りを保護するため、1,000面を超す大きい部品だけを複製後にデシメートする任意の試験引数を追加し、元の編集用 `.blend` と既定出力を変更しないようにした。比率0.7では[GLB](../output/endministrator_rigged_back_integrated_simplify70_views_trial/endministrator_rigged_fitting.glb)が63,574三角形、0.4では[GLB](../output/endministrator_rigged_back_integrated_simplify40_views_trial/endministrator_rigged_fitting.glb)が54,244三角形。いずれもスキン1個・素材4個・テクスチャ4枚で、UV・法線・ウェイト属性は保持された。

[0.7の正面](../output/endministrator_rigged_back_integrated_simplify70_views_trial/endministrator_rigged_rest.png)・[側面](../output/endministrator_rigged_back_integrated_simplify70_views_trial/endministrator_rigged_side.png)・[背面](../output/endministrator_rigged_back_integrated_simplify70_views_trial/endministrator_rigged_back.png)・[腕下げ](../output/endministrator_rigged_back_integrated_simplify70_views_trial/endministrator_rigged_arm_pose.png)と、[0.4の正面](../output/endministrator_rigged_back_integrated_simplify40_views_trial/endministrator_rigged_rest.png)・[側面](../output/endministrator_rigged_back_integrated_simplify40_views_trial/endministrator_rigged_side.png)・[背面](../output/endministrator_rigged_back_integrated_simplify40_views_trial/endministrator_rigged_back.png)・[腕下げ](../output/endministrator_rigged_back_integrated_simplify40_views_trial/endministrator_rigged_arm_pose.png)を比較した。遠景の輪郭はおおむね保たれるが、0.4では背面裾の折れ目と前面ニットの陰影が明らかに変わる。顔・髪を加えたアバター全体の性能、袖の貫通、近接での縫製ディテールは未検証であり、いずれも既定の完成プレビューへ採用しない。これは表示負荷の対照であって、**衣装形状の品質改善ではない**。

[市販セットの部品一覧](https://cossky.com/products/arknights-endfield-the-female-endministrator-women-outfit-halloween-carnival-party-cosplay-costume)には、水滴形装飾と髪飾りも明記されている。現在の部品監査ではこの2群が不足する。名称だけ合わせたダミー部品を追加して「揃った」とは扱わず、実物写真上の位置・寸法・固定方法を確認してから形状化する。

### 2026-10-07：肩を曲面に沿わせる配置案の棄却

型紙辺長を保ったまま前後肩の初期隙間を狭める目的で、紙面から伸ばした上身頃を半径12 cmの肩円弧に沿って曲げる配置を一時的に試した。袖付け前の検査で左袖メッシュの79面が緩和後に反転し、緩和前の袖型紙辺長差95百分位も59.51%となったため、描画・製品経路へ進めず試験コードを戻した。肩の位置だけを寄せても、袖ぐりと袖山の面形状・縫い合わせ経路を同時に再設計しなければ品質は上がらない。これは失敗した配置実験であり、完成品質を示すものではない。

袖山のいせ込み分布も同じM型紙で3方式を比較した。均等配置の初期袖メッシュの型紙辺長差95百分位は21.95%、袖山境界20.36%、脇下側57.56%。合印固定では全体22.56%、袖山19.27%、脇下57.52%。肩側集中では全体22.06%、袖山16.77%、脇下57.51%。袖山だけの局所改善では脇下の大きな変形が残るため、いずれも完成表示へ昇格させない。さらに袖山から袖筒への投影補間長を既定9 cmから2・4・6・10・12 cmへ変えて予備検査した。4・6 cmでは全体が26.10・24.88%へ悪化し、2・10・12 cmではメッシュ反転が出た。既定9 cmを維持し、補間値の調整だけでは解消できないことを記録した。

短時間の袖予備検査に、シミュレーション前の肩・前後脇・胸ダーツの縫い合わせ点距離を追加した。[均等配置の記録](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_uniform_hem_dart_trial/sleeve_initial_geometry_report.json)では、肩の95百分位が左右とも33.266 cm、前後脇が5.743 cmである。布を縫い合わせる前の3D配置に無理があることを約4秒の検査で確認でき、後工程のバネ収束値だけを見て「正しい縫製形状」と誤認するのを防ぐ。型紙自体の縫い線長と、この仮配置の空間距離は異なる指標である。

### 2026-10-07：ウエストダーツ先端の再トゥルーイング

寸法20組の系統検査で、バスト116・ウエスト84・ヒップ112 cmでは後身頃の裾ダーツ2か所の脚長差が約0.107 cmになり、接合処理が例外で止まった。元の製図では脚長は等しいが、その後のウエスト絞りで先端が口の中央から約0.632 cmずれていた。接合側の脚長許容値を緩めず、身頃の変形が終わった後に、先端の移動が0.75 cm以内の場合だけ口の二等分線へ戻す処理を追加した。口・裾の座標は変えない。大きく動く異常形状は従来どおり品質検査で止める。

同じ20組を再実行すると、出力例外は1件から0件になった。6組がデジタル検査通過、14組はウエスト余裕・脇線差などの実際の未解決条件で停止した。バスト116・ウエスト84・ヒップ112 cmの例はダーツ脚が等長になって裾接合検査を通過するが、ほかに4件のブロッカーがあるため裁断可能とは表示しない。関連の非一時ファイルテストは172件通過。一時ディレクトリを使う8件はWindows側のアクセス拒否で未検証であり、テストが通った扱いにはしない。背面形状・素材の実測や仮縫いを伴わないため、市販品相当の品質証明でもない。

M体型の再出力JSONは前回とSHA-256が一致し、修正が不要な既存寸法を動かしていない。[再計算48フレーム報告](../output/endministrator_lower_shell_flared_v2/drape_waist_trued_regression_48f/pattern_panel_drape_report.json)でも袖辺長差95百分位は左右23.96 / 23.29%のまま。[正面](../output/endministrator_lower_shell_flared_v2/drape_waist_trued_regression_48f/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_waist_trued_regression_48f/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_waist_trued_regression_48f/pattern_shell_smoothed_back.png)を目視し、前開きが広すぎる、側面の穴、後ろ肩の浮きが残ることを確認した。ダーツの紙面修正を3D外観向上とは扱わない。

### 2026-10-07：肩位置拘束と型紙辺長緩和の対照を棄却

従来の垂直押し出しでは肩縫い合わせ点の初期間隔が33.266 cmあり、布を大きく引き寄せていた。体型の推定ランドマークへ前後身頃の上端を寄せ、その後で型紙辺長へ近づくようメッシュを緩和する試験を行った。最良の予備条件では反転面0、上身頃の初期型紙辺長差95百分位が前左右3.49%、後ろ6.43%、肩初期隙間約6.6〜7.0 cmになった。ただし後ろ首付近には最大63.62%の局所辺長差が残った。

48フレームの実シミュレーションでは、後ろ首を帯状に固定すると[報告](../output/endministrator_lower_shell_flared_v2/drape_landmark_relaxed_neck06_48f_trial/pattern_panel_drape_report.json)上の肩縫い目が約6 cm開いたまま、後ろ身頃の型紙辺長差95百分位が18.81%に増えた。固定を後中心の狭い点に変えると肩縫い目は約0.1 cmへ閉じたが、[報告](../output/endministrator_lower_shell_flared_v2/drape_landmark_relaxed_backcenter_48f_trial/pattern_panel_drape_report.json)の後ろ身頃11.47%、左袖26.76%に悪化した。後者の[正面](../output/endministrator_lower_shell_flared_v2/drape_landmark_relaxed_backcenter_48f_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_landmark_relaxed_backcenter_48f_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_landmark_relaxed_backcenter_48f_trial/pattern_shell_smoothed_back.png)でも、胸部が折り畳まれて袖と後ろ裾が崩れる。単に肩の初期間隔と辺長を整えるだけでは体表への適切な配置・接触・縫い合わせを同時に満たせないことが確認できたため、試験モードのコードは戻し、完成表示に使わない。これは実測アバター・生地物性による適合試験ではない。

自動監査にも上身頃の最終型紙辺長差、袖の最終型紙辺長差、肩縫い合わせの最終隙間を追加した。試作内の異常検出目安はそれぞれ95百分位8%・10%、隙間0.5 cmで、いずれも市販品質の合格基準ではない。これを超す試験は不合格理由を明示する。基準版でも袖は左右23.96 / 23.29%で目安を超え、完成品質に達していない状態を隠さない。

### 2026-10-07：市販セットのしずく形飾りを別体試作

[Cosskyの同梱一覧](https://cossky.com/products/arknights-endfield-the-female-endministrator-women-outfit-halloween-carnival-party-cosplay-costume)と[CCosplayの商品写真](https://www.ccosplay.com/arknights-endfield-costume-endministrator-women-cosplay-suit)を参照し、右の黄色い肩装飾の下に、銀色リング・短い紐・黒いしずく形の飾りを別体で作った。寸法と接続位置は画像からの**推定**であり、実物採寸ではない。[正面](../output/endministrator_authored_waterdrop_trial/endministrator_front.png)・[側面](../output/endministrator_authored_waterdrop_trial/endministrator_side.png)・[背面](../output/endministrator_authored_waterdrop_trial/endministrator_back.png)で正面から視認できることを確認した。最初の[腕下げ画像](../output/endministrator_rigged_waterdrop_trial/endministrator_rigged_arm_pose.png)から肩への追従を判断したのは誤りで、後述の骨割当修正前は胴体の骨に属していた。紐の物理的な揺れや装着強度は未検証。

[部品監査JSON](../output/endministrator_authored_waterdrop_trial/commercial_component_audit.json)は13群中12群の粗い位置・寸法条件を通過した。以前の肩パーツ監査名が実物ノード名と食い違っていた点も修正したが、これは幾何品質が向上したことを意味しない。髪飾りは頭部・髪の参照形状がないため未実装であり、名前だけのダミーは追加していない。[骨付きGLB](../output/endministrator_rigged_waterdrop_trial/endministrator_rigged_fitting.glb)は74,008三角形、スキン1個、素材4個。[監査](../output/endministrator_rigged_waterdrop_trial/rigged_audit.json)のVRChat完成認証は偽。型紙パネル試作の袖・肩・脇の不具合も残るため、こちらの造形試作で市販品同等と評価しない。

### 2026-10-07：袖山をソフト拘束へ変える案の棄却

型紙由来袖の初期配置では袖山境界の辺長差95百分位が20.36%、脇下側が57.56%と大きい。縫合線上の袖山頂点をすべて固定する代わりに、頂点の移動を最大5mmに制限し、袖山頂点1個だけを固定して他の紙辺長を緩和する試験を行った。全頂点の移動も5mmとすると初期全体95百分位が21.95→47.75%に悪化。袖山だけ5mm・他の頂点を5cmまで許す条件では左袖の三角面が1枚反転し、シミュレーション前の安全検査で中止した。Blenderの終了コードは0でも例外ログを検出したため、成功と扱わない。試験コードは撤回し、既定の袖山固定方式を維持した。袖山線の局所長差と脇下の立体配置を別々に再設計する必要がある。

同日の[寸法20組の新しい固定ストレスグリッド](../output/endministrator_lower_shell_flared_v2/size_grid_audit_20261007.json)は、15組がデジタル検査通過、5組が肩線・胸ダーツ・脇線等のブロッカー、例外は0件だった。先述の「6組通過・14組ブロッカー」とは**入力した寸法組み合わせが異なる**ため、改善率として比較しない。20組は身長・バスト・ウエスト・ヒップ・肩幅・袖丈を明示した試験値であって人口分布や量産サイズ表ではない。大きいバスト／狭い肩で胸ダーツや肩先の制約が残るものは、単なる許容値変更で通過させずブロッカーとして保持した。

### 2026-10-07：フード周辺と背面ラベルの外観試作

[市販品の接写と背面写真](https://www.ccosplay.com/arknights-endfield-costume-endministrator-women-cosplay-suit)に見える黄色いコードと背面のラベルを参考に、既存の肩装飾試作へ左右のコード・黒い先端と別体の背面レタリングを追加した。既製品のコード長・固定方法は採寸できていないため、いずれも**視覚的な推定配置**である。[正面](../output/endministrator_authored_trim_trial/endministrator_front.png)・[側面](../output/endministrator_authored_trim_trial/endministrator_side.png)・[背面](../output/endministrator_authored_trim_trial/endministrator_back.png)を確認すると、正面のコードは襟近くの細い黄色線として見え、背面ラベルは読める。最初の[骨付き版の背面](../output/endministrator_rigged_trim_trial/endministrator_rigged_back.png)にも文字は見えるが、後の調査で元シーンの文字が描画されているだけで、GLBには含まれていないと判明した。動作時のコード干渉や実物の縫製強度は未検証であり、標準プレビューにはまだ採用しない。

その骨付き版の詳細点検で、しずく飾りの4部品が「腕側」と分類されず、胴体ボーンに割り当てられていたことが判明した。分類を修正し、[骨重み監査](../output/endministrator_rigged_trim_weightaudit_trial/attachment_weight_audit.json)で4部品の右上腕重み最小値0.9469、合計560頂点を確認した。[修正前](../output/endministrator_rigged_trim_trial/endministrator_rigged_arm_pose.png)と[修正後](../output/endministrator_rigged_trim_weightaudit_trial/endministrator_rigged_arm_pose.png)の腕下げを比較すると、飾りが肩パネルとともに下内側へ移動する。修正後の[正面](../output/endministrator_rigged_trim_weightaudit_trial/endministrator_rigged_rest.png)・[側面](../output/endministrator_rigged_trim_weightaudit_trial/endministrator_rigged_side.png)・[背面](../output/endministrator_rigged_trim_weightaudit_trial/endministrator_rigged_back.png)も確認した。ただし重み付けは固定された部品の変形だけで、金具の着脱、揺れ、布との貫通を検証しない。

### 2026-10-07：背面レタリングの書き出し漏れと布試作への混入を修正

背面ラベルはBlenderの`FONT`オブジェクトで、骨付き書き出し処理が`MESH`/`CURVE`しか複製していなかったためGLBへ含まれなかった。一方、[修正前の24フレーム布試作の背面](../output/endministrator_lower_shell_flared_v2/drape_trim_armweighted_24f_trial/pattern_shell_smoothed_back.png)には、型紙由来ではない元シーンの文字が残り、見かけ上だけ「背面ディテールが生成できた」状態だった。骨付き書き出し対象と型紙専用プレビューの非表示対象に`FONT`を加えた。印刷文字を厚み付き造形にすると骨付き衣装が78,320三角形となる一方、平面印刷相当に変更すると[骨付きGLB](../output/endministrator_rigged_flatlabel_trial/endministrator_rigged_fitting.glb)は74,606三角形で、[背面画像](../output/endministrator_rigged_flatlabel_trial/endministrator_rigged_back.png)でも判読可能。[構造監査](../output/endministrator_rigged_flatlabel_trial/rigged_audit.json)はスキン1個・素材4個、VRChat完成認証は偽。

同じM型紙・24フレームで布計算も再実行した。[修正後の型紙単体の正面](../output/endministrator_lower_shell_flared_v2/drape_flatlabel_filter_24f_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_flatlabel_filter_24f_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_flatlabel_filter_24f_trial/pattern_shell_smoothed_back.png)では余分な文字が消えた。[報告JSON](../output/endministrator_lower_shell_flared_v2/drape_flatlabel_filter_24f_trial/pattern_panel_drape_report.json)の袖・パネル数値は修正前の同条件24フレームと一致し、布形状そのものは改善していない。正面の大きな開き、側面の裾の折り重なり、背面のたまりは依然として残り、市販品と同等の可視品質には達していない。

### 2026-10-07：前後脇下を共通始点へ寄せる案の棄却

紙の袖山の全長は袖ぐりと約1.50cmのいせ込み差で合うが、立体試作では前後脇下の初期位置が約5.74cm離れている。袖山両端をその中点へ完全に寄せ、10cmまたは20cmの袖山弧に分散させる試験は、左右いずれかの袖の三角面が1枚反転して開始前検査で停止した。端点を80%だけ寄せると反転は避けたものの、[予備報告](../output/endministrator_lower_shell_flared_v2/sleeve_preflight_shared_underarm80_trial/sleeve_initial_geometry_report.json)では左袖全体の辺長差95百分位が21.95→27.43%、脇下側57.56→59.34%へ悪化した。右袖は21.95→21.63%、脇下側57.56→55.88%と小幅改善にとどまる。左右の非対称な配置誤差を袖山だけへ押しつける方式は不採用とし、コードを戻した。前後身頃の脇線・肩線を同時に正しい立体位置へ置く必要がある。

### 2026-10-07：髪飾りの別体試作と寸法グリッドの脇線診断

市販セットの同梱表には髪飾りが含まれるが、従来の衣装GLBには無かった。[単独GLB](../output/endministrator_hair_accessory_trial/hair_accessory_trial.glb)を作り、7メッシュと3素材を構造検査した。[正面](../output/endministrator_hair_accessory_trial/hair_accessory_front.png)・[側面](../output/endministrator_hair_accessory_trial/hair_accessory_side.png)・[背面](../output/endministrator_hair_accessory_trial/hair_accessory_back.png)は仮の頭部球に置いた位置見本で、頭部球はGLBに入らない。留め具形状、寸法、強度、ウィッグへの固定位置は推定のため、衣装本体の13群監査は12群合格のままとし、完成品同等とは数えない。

[同じ20寸法組の脇縫い線診断](../output/endministrator_lower_shell_flared_v2/size_grid_seam_diagnostics_20261007.json)では、15組がデジタル検査通過、5組が既知のブロッカー、例外0件で、前左右と後ろ半身の縫い線長を数値で記録した。例えばバスト108/ウエスト90cmは前31.27cm・後ろ30.71cm、112/82cmは前32.23cm・後ろ31.43cm、116/84cmは前30.83cm・後ろ29.67cmで、前が0.56〜1.16cm長い。許容値を緩めたり数字を丸めて通過させていない。これらはダーツと脇線を再製図し、同じパネルの袖ぐり・裾の対応まで再検査すべき未解決ケースである。49件の関連テストは通過した。

脇縫い線の停止理由を、単なる「異なる」から、前と後ろの実測縫い線長、差の向き、再製図が必要という文へ変更した。[変更後の同じ20組](../output/endministrator_lower_shell_flared_v2/size_grid_seam_direction_20261007.json)は引き続き15組通過・5組停止・例外0件。バスト108/ウエスト90cmは前31.27cmが後ろ30.71cmより0.56cm長いと表示する。停止件数を減らしたわけではなく、制作者が不用意に後ろだけを詰めたり許容差として見逃したりしないための情報である。

同じM型紙と新しい平面文字付き造形ソースで24フレームを再計算し、**仮想布物性だけ**を`baseline`から`structured-trial`へ切り替えた。[報告](../output/endministrator_lower_shell_flared_v2/drape_seam_diagnostics_24f_trial/pattern_panel_drape_report.json)と型紙単体の[正面](../output/endministrator_lower_shell_flared_v2/drape_seam_diagnostics_24f_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_seam_diagnostics_24f_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_seam_diagnostics_24f_trial/pattern_shell_smoothed_back.png)を確認。基準材の24フレーム画像より、正面裾の巻き込みと背面中央のたまりは少なく見える一方、肩の尖りと脇側の裂けが残る。袖の対型紙辺長差95百分位は左25.72→27.37%へ悪化、右20.44→20.03%へ小幅改善で、両方とも試験目安10%を超える。見た目の一部だけで物性を選んだり、市販品と同等と宣言したりできない。実布の厚み・剛性・重量を測り、同じ素材の試験片／仮縫いと比較する必要がある。

### 2026-10-07：胸ダーツ下の紙上脇線トゥルーイング試験

大きい体型の脇縫い線差が前身頃の胸ダーツより下に残っているため、前身頃下部だけを最大1.5cmの範囲で上下し、実際の前脇縫い線長が後ろ半身に合う位置を二分探索する**明示的な試験モード**を追加した。バスト108/ウエスト90cmでは前31.267cmと後ろ30.706cmの差に対し、下部を0.561cm上げて前30.706cmに合わせた。[20体型の試験結果](../output/endministrator_lower_shell_flared_v2/size_grid_truing_applied_trial_20261007.json)はデジタル検査15→17通過、例外0件。バスト112/ウエスト82cmでも脇線差は消えた。一方、116/84cmと120/102cmは胸ダーツ不足や狭い肩幅など、別のブロッカーを残す。この時点では通常生成に有効化せず、型紙検査が通ったことを実物のフィット合格と扱わなかった。

バスト108cmの[元型紙と補正試作の前身頃重ね画像](../output/endministrator_lower_shell_flared_v2/b108_front_outline_comparison.png)では、袖ぐりとダーツ先端は重なり、裾側が上へ約0.56cm移ることを確認した。[試験用のA4型紙PDF](../output/endministrator_side_truing_b108_print_trial/eea0f337df9a.pdf)は104ページ。印刷図の前身頃タイルのうち92ページを画像化し、線・日本語ラベル・ダーツ線を目視した。全104ページの貼り合わせと実際の印刷倍率は未確認であり、裁断用として承認しない。関連13件のテストは通過した。

下裾パネルの3D用データはバスト108cmで出力でき、紙上の脇線差0.56cmを残した対照データでは、Blenderが縫い線長不一致として開始前に止まった。補正試作はそこを通過したが、続く袖配置の予備検査で左袖の面が1枚反転し、まだ布計算へ進めない。Blenderは従来、Python例外でも終了コード0を返していたため、呼出し例に`--python-exit-code 1`を加えて失敗を明確にした。同じ反転試験が終了コード1になることを確認した。バスト112cmの3D用出力は、胸ダーツとは別の**裾開きダーツ**で裾の水平線が分割され、現行の3D橋渡しが「裾辺が途切れている」と停止した。これは型紙の接合処理では閉じるダーツとして認識する構造であり、3D側にも同じ閉じ処理を実装しないまま通過させてはいけない。したがって紙上の17/20通過を3D完成率と読まない。

### 2026-10-07：大きめサイズの袖配置を折り返し計算で診断

バスト108cmの袖メッシュは、元の配置から紙辺長へ緩和すると左1面・右4面が反転した。[左袖の拒否報告](../output/endministrator_lower_shell_flared_v2/preflight_b108_rejection_report/sleeve_rejection_report.json)には面番号・紙座標・配置前後の3D座標を保存し、例外時に理由が失われないようにした。M型紙では反転0だったため、幅を変えない元ガイドだけが原因とは言い切れない。

反転4面以下に限り、緩和後の位置を元の位置へ段階的に戻し、反転が消える最初の位置で止める**診断用の折り返し**を試した。[B108の布計算前報告](../output/endministrator_lower_shell_flared_v2/preflight_b108_backtrack4_trial/sleeve_initial_geometry_report.json)では左の緩和係数0.8・右0.4、反転0。元配置の辺長差95百分位60.28/56.47%が、折り返し後34.47/41.99%となったが、商用衣装の形状としては依然として極端に大きい。M型紙は係数1.0のまま、従来の初期値25.28/19.75%で、既存条件を変えていない。

B108を24フレーム実行した[報告](../output/endministrator_lower_shell_flared_v2/drape_b108_backtracked_24f_trial/pattern_panel_drape_report.json)では、袖の最終辺長差95百分位34.72/42.52%、最大77.84/86.26%。[正面](../output/endministrator_lower_shell_flared_v2/drape_b108_backtracked_24f_trial/pattern_shell_smoothed_front.png)は袖が伸びたが襟周りが崩れ、[側面](../output/endministrator_lower_shell_flared_v2/drape_b108_backtracked_24f_trial/pattern_shell_smoothed_side.png)には大きな脇穴、[背面](../output/endministrator_lower_shell_flared_v2/drape_b108_backtracked_24f_trial/pattern_shell_smoothed_back.png)には深い肩しわと別体の裾の浮きがある。脇縫い線の紙上差をなくしても3D衣装の可視品質を満たさない。折り返しは**不正な面を減らして原因を見られるようにする道具**であり、完成プレビューや物性検証に昇格しない。

### 肩先の初期位置合わせ試験は不採用

B108では前後の肩先が初期配置で離れるため、左右の肩先を相互に近づけ、移動量を裾へ向けて減衰させる別試験を行った。これは2D型紙や通常の生成コードには適用していない。[正面](../output/endministrator_lower_shell_flared_v2/drape_b108_shoulder_outer_24f_trial/pattern_shell_smoothed_front.png)では胸元のひだ、[側面](../output/endministrator_lower_shell_flared_v2/drape_b108_shoulder_outer_24f_trial/pattern_shell_smoothed_side.png)では脇穴、[背面](../output/endministrator_lower_shell_flared_v2/drape_b108_shoulder_outer_24f_trial/pattern_shell_smoothed_back.png)では大きな斜めじわが残り、採用できない。ただし、この[24フレーム試験](../output/endministrator_lower_shell_flared_v2/drape_b108_shoulder_outer_24f_trial/pattern_panel_drape_report.json)は旧`endministrator_commercial_sewn_v4`を参照し、先述のB108基準試験は新しい`endministrator_authored_flatlabel_trial`を参照した。したがって**両者の袖歪み数値を改善・悪化の因果比較として扱わない**。同じ型紙JSONでも前者の元ソースでは袖緩和で5面が反転して事前停止し、後者では反転なく予備検査を通ることを再確認した。試験コードは撤去し、今後の全3D報告には型紙JSON・参照`.blend`・実行スクリプトのSHA-256を入れて比較条件を固定する。次は肩線全体を紙の辺長を保ったまま体表へ配置する方法が必要である。実布物性・着用時の可動域は未検証。

### 紙上脇線補正の管理人衣装への標準適用

20体型のデジタル検査を補正あり・なしの両方で再実行し、[標準生成](../output/endministrator_lower_shell_flared_v2/size_grid_default_truing_20261007.json)は17/20、[無補正の対照](../output/endministrator_lower_shell_flared_v2/size_grid_untrued_control_20261007.json)は15/20で、どちらも例外0件だった。この補正を**管理人（女性）の衣装プロジェクトに限り**通常生成へ適用した。胸ダーツ口より下のみを最大1.5cm動かし、目標の縫い線長を達成できない場合は元の型紙を保持して品質警告を残す。任意の服全体へは展開しない。診断時は `--disable-truing` で対照型紙を出せる。通常サイズを含む関連25件のテストは通過したが、裾開きダーツがあるB112の3D試験用メッシュはなお停止する。これは**紙上の縫い合わせ長の修正**であり、実布でのフィット・耐久や市販衣装との同等性は示さない。

標準生成のB108型紙を、同一の新しい参照`.blend`で再度24フレーム計算した[入力ハッシュ付き報告](../output/endministrator_lower_shell_flared_v2/drape_b108_default_trued_24f/pattern_panel_drape_report.json)では、袖の最終辺長差95百分位が左34.72%・右42.52%、最大77.84%・86.26%、形状検査も商用品質判定も不合格。正面・側面・背面の画像は先述の試験と同じ崩れで、紙の脇線を直したことを立体完成度の改善として数えない。パネル出力の `do_not_cut_or_publish_as_ready` は、紙上の脇線が揃っていても常に真とし、実布・着用の検証前に生産可と誤解させない。

### 裾ダーツを持つB112の3D入力境界を分離

以前は裾開きダーツのあるB112型紙を3D用に書き出す際、連続した水平裾がないため停止していた。現在は[ダーツ対応のパネルJSON](../output/endministrator_lower_shell_flared_v2/panels_b112_dart_aware.json)を出力し、前A/Bを各2区間・裾ダーツ各1本、後Cを3区間・裾ダーツ2本として記録する。[紙上の接合・ダーツ図](../output/endministrator_lower_shell_flared_v2/b112_hem_dart_map.png)でも緑の裾区間が赤いダーツ口をまたがず、それぞれ独立していることを目視した。各区間の縫い線長の和は、接合する下身頃上辺とA/B各35.07cm・C65.00cmで一致する。深いVを通常の非拘束三角化で塞がないよう、ダーツのある身頃に限り境界を保存する拘束三角形メッシュを使い、脚の境界頂点と縫い順を失わないようにした。関連35件のテストは通過した。

ただし、このメッシュは境界を保存する**下準備**であり、内部の面サイズは布計算用に整えていない。連続縫合・溶接モードは裾ダーツを持つ入力を明示的に拒否する。診断専用の非溶接`sewn-shell`モードには裾ダーツ両脚の縫いバネを追加したが、胸・肩・上身頃脇は開いたまま、袖も参照造形からの借用であり、完成衣装にはならない。`simulation_input_ready=false` と `do_not_cut_or_publish_as_ready=true` を維持する。

B112を同じ型紙JSON・同じ新しい参照`.blend`で24フレーム計算した[紙面展開配置の報告](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_trial/pattern_panel_drape_report.json)と[ガイド配置の報告](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_guide_trial/pattern_panel_drape_report.json)は、いずれも暫定形状判定が不合格。紙面展開配置で前Aのダーツ口は最終95百分位0.491cm、ガイド配置でも0.335cm開き、試験目安0.2cmを超える。下身頃の脇縫い目も前者で0.917/1.132cm、後者で0.950/1.675cm開く。後者の上身頃の型紙辺長差はA/B/Cいずれも悪化した。[紙面配置の正面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_trial/pattern_shell_smoothed_back.png)、[ガイド配置の正面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_guide_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_guide_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_b112_waist_dart_guide_trial/pattern_shell_smoothed_back.png)でも、上身頃と袖が分離し、脇から下裾が大きく崩れる。計算が終わったことを品質改善と読まない。両試験は同じ入力ハッシュを報告に保存しており、配置方式だけの比較として扱える。

さらに診断用の非溶接モードに胸ダーツ・肩・上身頃脇の縫いバネも付けた[24フレーム試験](../output/endministrator_lower_shell_flared_v2/drape_b112_upper_seams_trial/pattern_panel_drape_report.json)では、前Aの裾ダーツ口は0.067cmまで閉じた。肩はA/Bで0.158/0.217cm、上身頃脇は0.193/0.178cmまで寄る。ただし下身頃脇は0.669/0.940cmと大きく開き、上身頃の対型紙辺長差95百分位はA23.92%・B26.69%・C10.30%。背中は人体代用体から中央値8.94cm離れる。[正面](../output/endministrator_lower_shell_flared_v2/drape_b112_upper_seams_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_b112_upper_seams_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_b112_upper_seams_trial/pattern_shell_smoothed_back.png)で、前開きの破綻、袖の分離、裾の大きな塊を目視した。**縫い目の距離が縮んだことと、着用できる衣装形状になったことは別**である。このモードも完成プレビューに採用しない。袖は参照造形の借用で、縫製・実布・人体への適合は未検証。

下身頃の脇端を開始時に揃えるため、B112の非溶接診断モードでは各台形の横方向を縫い線区間へ再配置した。[広がり10.5cm](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_upper_seams_trial/pattern_panel_drape_report.json)は脇の初期隙間0cm・最終0.008/0.004cm、[広がり15cm](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_flare15_trial/pattern_panel_drape_report.json)は最終0.022/0.007cmで、縫い線距離は改善した。しかし前A/Bの下身頃対型紙辺長差95百分位は前者31.93/36.36%、後者29.38/34.52%まで悪化。広がり15cmの[正面](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_flare15_trial/pattern_shell_smoothed_front.png)も前裾が板状に細く垂れ、実物のコート外形にはならない。初期の紙辺長を取り戻す緩和も試したが、三角面26〜27枚の反転・潰れで事前拒否されたため緩和モードを採用しなかった。裾の縫い目だけ閉じる操作では布の余り幅を立体に配置できない。次の課題は、体表を避けながら紙辺長・裾幅・前後の体積を同時に守る初期配置である。

凹形のダーツ付き上身頃は境界に沿った拘束三角化だけだと内部の最長辺が前25.64cm・後49.73cmだったため、試験的に内部辺を最大6cmへ細分化した。[同条件24フレームの報告](../output/endministrator_lower_shell_flared_v2/drape_b112_refined6_aligned_trial/pattern_panel_drape_report.json)では脇縫い目は閉じたままだが、下身頃の辺長差はA29.38→29.33%、B34.52→34.97%、後ろ上身頃は10.61→17.60%となり、[正面](../output/endministrator_lower_shell_flared_v2/drape_b112_refined6_aligned_trial/pattern_shell_smoothed_front.png)の実物らしさも改善しない。頂点増加で計算・描画時間も約2倍になったため、細分化は既定実装から撤回した。失敗は面密度だけでなく立体初期配置と型紙構造にある。

同じB112型紙・参照モデル・配置で仮想布だけ硬めの`structured-trial`に変えた[感度試験](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_structured_trial/pattern_panel_drape_report.json)も、下身頃の辺長差はA29.38%・B34.76%・C12.03%、形状判定は不合格。[正面](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_structured_trial/pattern_shell_smoothed_front.png)では前胸の開きと脇の塊が残る。布設定の変更だけでは初期配置・型紙の問題を補えない。これは実際の生地試験値ではなく、製作素材の推奨にも使用しない。

同じ入力・仮想布を24→48フレームに延ばした[長時間試験](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_48f_trial/pattern_panel_drape_report.json)も形状判定は不合格。下身頃の対型紙辺長差95百分位はA29.38→29.47%、B34.52→34.39%、C12.01→11.99%でほぼ変わらない。背中の人体代用体からの距離中央値は11.16→15.20cmとむしろ離れた。[正面](../output/endministrator_lower_shell_flared_v2/drape_b112_aligned_48f_trial/pattern_shell_smoothed_front.png)では裾の一部は垂れ下がるが、胸の浮きと袖の分離が残る。追加フレームだけで完成衣装にはならない。

B112の借用袖を型紙由来袖へ置き換える予備検査も行ったが、右袖メッシュの6面が緩和後に反転し、[拒否報告](../output/endministrator_lower_shell_flared_v2/preflight_b112_pattern_sleeves_trial/sleeve_rejection_report.json)を残して終了コード1で停止した。見た目だけのために反転面を無視したり、借用袖を型紙完成袖として数えたりしない。袖ぐり・袖山の初期立体配置は別途再設計が必要である。

上身頃の背中が代用体から離れる原因を探るため、裾位置は固定しつつ肩へ向かうほど採寸代用体の楕円輪郭へ寄せた。直接寄せる[試験](../output/endministrator_lower_shell_flared_v2/drape_b112_torso_follow_trial/pattern_panel_drape_report.json)では背中の距離中央値が11.16→6.14cmへ減るが、後ろ上身頃の対型紙辺長差は10.61→29.92%、肩縫い目Bは0.187→0.505cmへ悪化。[55%だけ寄せた試験](../output/endministrator_lower_shell_flared_v2/drape_b112_torso_follow55_trial/pattern_panel_drape_report.json)でも後ろ上身頃18.27%、肩B0.450cmで、[側面](../output/endministrator_lower_shell_flared_v2/drape_b112_torso_follow55_trial/pattern_shell_smoothed_side.png)に大きな袖ぐり穴が残る。近づけるだけでは紙の形・肩・体表接触を両立できず、この配置コードは撤回した。実人体のスキャンにも基づかない。

市販品の素材欄も再確認した。[Cossky](https://cossky.com/products/arknights-endfield-the-female-endministrator-women-outfit-halloween-carnival-party-cosplay-costume)は合皮・糸・ニット、[CCosplay](https://www.ccosplay.com/arknights-endfield-costume-endministrator-women-cosplay-suit)はプリント生地・フェルトと記載する。同一仕様とは見なせず、いずれの実物布厚・目付・曲げ剛性・伸びも未入手である。プロジェクト内のツイルと合皮の案を「未採用の試作候補」と明記し、仮想布設定を市販品の再現値として表示しないようにした。

### 近傍100寸法のデジタル製図ストレス試験

既存20体型のそれぞれに、固定乱数でバスト・ウエスト・ヒップを±1〜2cm、袖丈・肩幅を±1cmだけ動かした計100入力を[再現可能なスクリプト](../scripts/audit_endministrator_nearby_sizes.py)で検査した。[標準脇線補正](../output/endministrator_lower_shell_flared_v2/size_grid_nearby100_20261007.json)は79/100件がデジタル検査通過、[無補正の対照](../output/endministrator_lower_shell_flared_v2/size_grid_nearby100_untrued_control_20261007.json)は72/100件で、どちらも例外0件。7件は補正により紙上の脇縫い線差が解消し、逆に通過から停止へ変わった入力は0件だった。停止21件の理由は肩幅に対する背幅不足、胸ダーツ不足、2件の最小ウエスト寸法範囲外である。停止条件を緩めず保持しており、79件を「79人に合う」「市販品相当」と読まない。この100件は人口分布ではなく、既知入力の周辺に対するソフトウェア耐性検査である。

同じ100体型を[3D入力書き出し検査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_20261007.json)に通すと、2件で前面別布パネルの三角化が縫い線端点を落として停止した。該当寸法は87/75/98/155/49/41と100/90/109/160/52/44cm。通常の三角化が境界端点を落とした場合に限り、境界保存の拘束三角化へ切り替える修正を加えた。両方のパネルで縫い線境界と上身頃への投影を検査し、[再実行](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_boundaryfix_20261007.json)は100/100件が書き出し、例外0件。元から通っていたB112の上身頃・前面別布メッシュは修正前後で同一だった。ただし51件は裾ダーツの完成3D縫合に未対応、残り49件の`simulation_input_ready`も入力形式の対応にすぎず、3D衣装品質の合格率ではない。フォールバックの大きな内部三角面は別途改善が必要である。

該当87cm体型の別布メッシュを最大辺4cmへ細分化し、[3D投影試験](../output/endministrator_lower_shell_flared_v2/drape_b87_refined_detail_trial/pattern_panel_drape_report.json)も実行した。しかし[細分化しない同条件](../output/endministrator_lower_shell_flared_v2/drape_b87_coarse_detail_control/pattern_panel_drape_report.json)に比べて、別布A/Bの対型紙辺長差95百分位は35.14/26.14%→39.26/35.35%へ悪化。[正面](../output/endministrator_lower_shell_flared_v2/drape_b87_refined_detail_trial/pattern_shell_smoothed_front.png)の見た目も市販品には遠く、細分化コードは撤回した。これは前面別布を上身頃の計算済み面へ貼るだけで、別布そのものの縫製・物理計算を行っていない。境界保持と外観品質を混同しない。

関連の広いテスト群では84件通過し、既定補正の導入で停止理由が「脇縫い線」から「胸ぐせダーツ」に変わった監査テスト1件を現状に合わせて更新した。別の10件はWindowsの`tmp_path`用ディレクトリへのアクセス拒否でテスト準備自体が失敗したため、通過として数えない。更新後の監査テスト4件は通過した。

[20体型の3D入力ストレス検査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_20261007.json)では20件ともパネル境界を書き出せたが、裾ダーツがある10件は完成衣装モードで止める。残り10件の `simulation_input_ready=true` は入力形式の対応のみを示し、プレビュー品質の合格率ではない。この結果から、裾ダーツの縫い閉じ、各裾区間の下身頃への接合、上身頃各縫い目の立体配置が未解決だと分かった。

メッシュの事前検査に、有限な座標、重複・面積ゼロの三角形、3面以上が接する辺、孤立したメッシュ島の拒否を追加した。これまでの縫い線境界頂点検査だけでは、境界が残ったまま内部の面が壊れる入力を見逃し得た。[強化後の近傍100寸法再検査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_topologycheck_20261007.json)では書き出し100/100件、入力形式対応49件、裾ダーツ未縫合51件と以前の結果を維持した。さらに型紙の縫い線輪郭面積と三角面の合計面積の差を0.5%以内に制限し、[同じ100寸法で再検査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_topologyarea_20261007.json)して結果を維持した。関連29テストが通過した。これは幾何トポロジーの安全検査であり、布の形状・着用感・市販品並みの外観を承認するものではない。

さらにパネル内部で三角面の表裏が混ざる場合も拒否するようにした。[同じ100寸法の再検査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_winding_20261007.json)は100/100件を書き出し、51件の裾ダーツ未縫合停止も維持した。面の向きが揃っていても、袖と身頃が正しく縫合できることや市販衣装並みの外観は保証しない。

この検査強化後、同じB112型紙JSON・参照Blender・24フレーム・縫い設定で[布試作を再実行](../output/endministrator_lower_shell_flared_v2/drape_b112_topologyguard_regression/pattern_panel_drape_report.json)した。前回の広がり15cm試験と型紙・参照ファイルのSHA-256が同じで、前A/B/後Cの最終紙辺長差95百分位は29.38/34.52/12.01%と一致。正面・側面・背面の描画画素もそれぞれ完全一致した。検査を厳しくしただけで形状は改善も悪化もしておらず、暫定形状判定・市販品質判定は引き続き不合格である。

[近傍100寸法の面密度監査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_meshquality_20261007.json)では、裾ダーツ未縫合の51件すべてで上身頃メッシュの三角辺が20cm超、最大49.778cmだった。これは境界を守る一方で内部を粗く三角化している試作入力であり、布計算の品質には不十分。前面別布の拘束三角化フォールバックは2寸法・左右計4パネルで、最大辺8.619cmだった。これらは型紙縫い線の保持とメッシュ品質が別の条件であることを示す。単純な内部細分化は上記のB112/B87試験でひずみと見た目を改善しなかったため、既定採用せず、立体初期配置・縫合順・面密度をセットで再設計する。

最新コードで[面積属性入りのB112型紙JSON](../output/endministrator_lower_shell_flared_v2/panels_b112_topologyguard.json)を再書き出した。追加の検査属性を除く旧JSONとの構造・頂点・三角面は完全一致。[この新入力による24フレーム布試作](../output/endministrator_lower_shell_flared_v2/drape_b112_fresh_export_regression/pattern_panel_drape_report.json)も実行し、暫定形状判定は不合格、A/B/Cの紙辺長差は29.38/34.52/12.01%で変わらなかった。レンダリング画像は見た目同一で、画素差は各色最大1階調のごく小さい描画差だった。面積検査は実行を妨げないが、未解決の布形状を改善もしない。

最後に、三角メッシュの外周と宣言された型紙外周が**全ての辺で一致するか**を追加で監査した。B87の前A/Bは実メッシュ外周に宣言外の辺が各2本、宣言されたのに境界に無い辺が各4本あった。従来の検査は指定縫い線の辺が存在するかだけを見ており、外周全体を確認していなかった。`strict_boundary=True`を直ちに使う案は「飛ばされた頂点に接する境界面が一意でない」として停止したため撤回。型紙形状を変更せず、[100寸法の最新監査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_boundarygate_20261007.json)で外周不一致70件、裾ダーツ未縫合51件、重複を除いて3D入力準備完了0件と判定し直した。従来の「49件入力形式対応」は**過大判定**であり訂正する。100件のJSON書き出し成功は維持するが、完成プレビューを提供してよい根拠にはならない。次は身頃外周の境界保存三角化を、内部面密度と布配置を悪化させずに設計し直す必要がある。

### 2026-10-07：凹部に欠けた三角面だけを補修

上記70件の停止を調べると、B87ではDelaunay三角化が身頃の小さい凹部を短い弦でまたぎ、面積約1.10cm²を覆っていなかった。既存の縫い線頂点を動かさず、欠けた多角形だけ拘束三角化し、既存メッシュへ加えてから全外周を厳密に検査した。B87の前A/Bでは各2面の補修と境界頂点の接続で外周不一致が0になった。[近傍100寸法の再監査](../output/endministrator_lower_shell_flared_v2/size_grid_3d_export_nearby100_gapfill_strict_20261007.json)は書き出し100/100、身頃外周不一致0、裾ダーツ未縫合51、3D入力形式対応49、前面別布フォールバック4面。関係65テストは通過した。未縫合裾ダーツを自動で解決したわけではない。

同じB87体型の[新しい型紙入力](../output/endministrator_lower_shell_flared_v2/panels_b87_boundary_repaired.json)で[24フレーム布試作](../output/endministrator_lower_shell_flared_v2/drape_b87_boundary_repaired_trial/pattern_panel_drape_report.json)を再計算した。旧試験と新試験の前A/B・後C下身頃の紙辺長差95百分位は30.19/36.40/12.60%→30.00/36.52/12.64%。[正面](../output/endministrator_lower_shell_flared_v2/drape_b87_boundary_repaired_trial/pattern_shell_smoothed_front.png)・[側面](../output/endministrator_lower_shell_flared_v2/drape_b87_boundary_repaired_trial/pattern_shell_smoothed_side.png)・[背面](../output/endministrator_lower_shell_flared_v2/drape_b87_boundary_repaired_trial/pattern_shell_smoothed_back.png)を確認すると、袖の分離・前開きの崩れは残る。暫定形状判定は引き続き不合格。**外周の構造修正と、完成衣装に見えることは別の課題である。**

### 2026-10-07：配置と袖肩合わせ位置の比較（いずれも完成設定に不採用）

B87の首・肩だけを固定する配置は、縫合初期隙間31.78cmが安全上限10cmを超えて布計算前に停止した。`landmark-tapered-trial`＋`back-neck-band-trial`は胴体代用体への距離中央値を前Aで8.2→4.61cm、前Bで6.76→4.21cm、後Cで8.3→4.59cmに縮めた一方、上身頃の紙辺長差95百分位を24.36/26.55/5.69%→31.25/35.26/32.47%へ悪化させ、肩の最終隙間も約7cmに開いた。後ろ中央を保持する別試験では肩隙間を0.07/0.11cmまで閉じたが、上身頃の紙辺長差は31.04/35.13/23.40%で、[正面](../output/endministrator_lower_shell_flared_v2/drape_b87_landmark_backcenter_trial/pattern_shell_smoothed_front.png)も乱れた。体への近さだけを最大化する案は採用しない。

袖山は総長44.72cm、袖ぐり総長43.21cmで一見合うが、幾何学的な頂点で二分すると前22.36cm対前袖ぐり20.46cm（+1.90cm）、後22.36cm対後袖ぐり22.75cm（−0.39cm）となり、後ろ側で縫合できない。**3D試験だけ**、頂点から3cm以内の既存頂点から前後両方のいせ込みが成立する肩合わせ位置を選ぶ処理を加えた。[B87の袖予備検査](../output/endministrator_lower_shell_flared_v2/preflight_b87_pattern_sleeves_pivot_20261007/sleeve_initial_geometry_report.json)は停止せず、[24フレーム試作](../output/endministrator_lower_shell_flared_v2/drape_b87_pattern_sleeves_pivot_trial/pattern_panel_drape_report.json)も最後まで実行した。ただし袖の対型紙辺長差95百分位は左40.02%・右39.78%、上身頃は前A/B・後Cで60.00/61.87/75.35%。[正面](../output/endministrator_lower_shell_flared_v2/drape_b87_pattern_sleeves_pivot_trial/pattern_shell_smoothed_front.png)では前が大きく開き、袖は平たく尖る。**縫合計算が完走しても市販品に近い外観・実布の着用性は不合格**。この肩位置は印刷型紙の新しい合印としてまだ反映していないため、製作用パターンには昇格しない。

上段の試験後、前後袖ぐりの実測縫い線長から同じ選択規則で**4本目の肩合わせ合印**を管理人衣装の印刷型紙にも出力した。前1本・後ろ2本の合印を維持し、肩印と3D試験メッシュの位置差が0.1cm以内か検査する。これは縫い合わせ位置を明示した改善であり、上記の約40%の袖ひずみを直したという意味ではない。いせ込みの外観と可動域は実布の仮縫いで確認する必要がある。

B87体型の試験印刷PDFを`output/pdf/endministrator_b87_shoulder_qa/`に生成し、袖山を横切るタイルR7-C3〜C5（PDFの55〜57ページ）を画像化して確認した。前1本、頂点より約1.07cm前側の肩1本、後ろ2本の赤い合印が黒い裁断線と灰色の縫い線を結び、タイル境界で欠けずに見える。縫製手順の袖山いせ込み量も、設計時の概算2.2cmではなく、完成した型紙の縫い線差約1.5cmを表示するよう修正し、再生成した4ページ目で確認した。手順書には「4本目の肩印は幾何学的頂点とは限らない」と明記した。紙への実寸印刷、全83ページの貼り合わせ、着用状態は未確認で、試験PDFを本番裁断用とは扱わない。

4本目の合印は他の印と同じ赤線だけでは前後の区別がつきにくいため、A4印刷・投影PDF・SVGのいずれも印の型紙内側に「肩」を付記した。DXFにも「肩」と、CAD環境で日本語フォントが無い場合のための`SHOULDER`を別レイヤーへ追加した。B87のA4タイル56ページ目を再レンダリングして肩印と文字の対応を確認し、DXFは再読込して左右2か所ずつのラベルを確認した。ドロップショルダー後の袖ぐり幅を通常の胸幅・背幅式に再比較する案は、意図的な5cmの肩張り出しを過大幅と誤判定して100寸法すべてを停止したため採用しない。
