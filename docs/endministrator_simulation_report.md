# 管理人衣装：背面・側面と布落ちの感度試験

実行日: 2026-10-04。入力は利用者が提供した正面イラストと、そこから手作業で推定した衣装モデルである。側面・背面は公式の寸法確定図ではない。この3D衣装は前回出力した2D型紙を縫い合わせて復元したものでもない。Blender 5.2で、コート外殻の布メッシュを代替アバターの胴体へ36フレーム落とし、柔らかめ・中間・硬めの3組の**未実測**パラメータで比較した。これは素材感度試験であって、特定の市販生地の再現や着用試験ではない。

Blenderの[布の物性設定](https://docs.blender.org/manual/en/latest/physics/cloth/settings/physical_properties.html)には質量・伸び・せん断・曲げの係数があり、[衝突設定](https://docs.blender.org/manual/en/latest/physics/cloth/settings/collisions.html)には布同士の自己衝突がある。今回は比較実験として前者を変えたが、現物試験から係数へ校正しておらず、後者の自己衝突は計算時間を抑えるため無効にした。

| 仮定 | 平均頂点移動 | 移動の95パーセンタイル | 裾幅／初期裾幅 | 辺長変化の絶対値・95パーセンタイル |
| --- | ---: | ---: | ---: | ---: |
| 柔らかめ | 7.62cm | 27.88cm | 0.995 | 12.27% |
| 中間 | 6.58cm | 23.20cm | 0.915 | 11.92% |
| 硬め | 6.29cm | 21.72cm | 0.946 | 10.85% |

辺長変化は**数値モデル内の変形量**であり、布や縫い目の破断率ではない。代替アバターから12mm以内の頂点は順に269/260/282個だったが、これは最近傍面への距離であって貫通判定ではない。自己衝突は無効。上半身をピン留めした静止姿勢のみを解いた。

## 画像で確認した問題

- [側面・柔らかめ](../output/endministrator_material_study/soft/soft_side.png)、[側面・中間](../output/endministrator_material_study/baseline/baseline_side.png)、[側面・硬め](../output/endministrator_material_study/stiff/stiff_side.png): コートの裾フレアが重力で内側へ寄り、前回の静止モデルにあった側面シルエットを保てない。硬めにしても別裁ちパネルと硬質装飾の関係は改善しない。
- [背面・柔らかめ](../output/endministrator_material_study/soft/soft_back.png)、[背面・中間](../output/endministrator_material_study/baseline/baseline_back.png)、[背面・硬め](../output/endministrator_material_study/stiff/stiff_back.png): 背面の左右フレアと垂れ装飾の位置関係が素材の仮定で変わる。背面図が無いため、どれが正解かは選べない。
- [正面・柔らかめ](../output/endministrator_material_study/soft/soft_front.png)、[正面・中間](../output/endministrator_material_study/baseline/baseline_front.png)、[正面・硬め](../output/endministrator_material_study/stiff/stiff_front.png): 布が動いても見返し、白い縁取り、金具、背面ストラップは元の位置に残る。現行の「表地を動かし装飾は静止」の構造では、縫い付け位置・補強・荷重を評価できない。

## この結果からの設計判断

1. 市販衣装に近い裾形状を保ちたいなら、生地を硬くするだけでは足りない。パネルの裁断線・接合位置、芯地の範囲、裾の重り／支持を独立した設計値として決め、再シミュレーションする。
2. 見返し・縁取り・垂れストラップ・硬質小物の固定点を布メッシュの頂点または縫い線に結び、衣装と一緒に動かす。今回の画像は固定方法が未実装であることを露呈した。
3. 試作生地の面密度、厚み、縦横・バイアス方向の伸び、曲げ、摩擦を測る。測定値無しでこの3条件から素材を選定しない。
4. 着用者の体型・腕上げ・歩行・着座を入れた動的フィット、装飾の着脱反復、縫い目や接着の引張・疲労は**未検証**。特に耐久性の合格判定は実物試験なしに出さない。

各条件の入力値・計算値は `output/endministrator_material_study/<条件>/simulation_report.json`、編集できるBlenderファイルと正面／側面／背面PNGも同じフォルダにある。再実行は `scripts/simulate_endministrator_fit.py` をBlenderのバックグラウンドモードで `-- 出力先 soft|baseline|stiff` として呼ぶ。
