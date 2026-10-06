# 衣装3Dプレビューの品質基準

## Style3D AI Garment 連携の準備状況

Style3D Studio の AI Garment は、正面画像からデザイン案・型紙・縫製関係・3D衣装を生成する機能として案内されている。ただし試用権限の有効化が必要であり、Formaの既存の簡易3D生成とは別の外部エンジンである。

`python scripts/probe_style3d_mcp.py` は、ローカルの Style3D MCP（既定 `http://127.0.0.1:57281/mcp`）に接続し、実際に公開されているツール名と入力スキーマを読み取る。画像を送信せず、生成ツールも実行しない。Style3D が未導入・MCP未起動なら `connected: false` として終了する。ポートを変更した場合は `--url http://127.0.0.1:<port>/mcp` を指定する。ローカル以外のURLは拒否する。

実機で生成ツールと入力スキーマを確認するまでは、画像→衣装生成を Forma が実行できるとは表示しない。試用権限、有料プラン、外部GPU利用料金の条件も確認してから実行する。Style3D 出力も、GLBの構造検査に加えて制作対象のアバター上で手直し・動作確認が必要であり、出力された時点で「VRC完成衣装」と認定しない。

参考：[Style3D の MCP 設定](https://help.style3d.com/studio/en/1f8f/6ef76)、[AI Garment の利用手順](https://help.style3d.com/studio/en/c4905/c2c8/7cd2/b61b)。

## 現状の区別

- 画像からの自動生成は、丈・大まかなシルエット・小物位置を検討するための**試着ラフ**である。
- 衣装GLBの読み込みは、別途制作した衣装メッシュを同じ画面で確認するための機能である。GLBを読み込んだだけでVRChat対応になるわけではない。
- 正面画像しかない衣装の背面・袖裏・布の重なりは推定であり、正確な再現を保証しない。

## VRC向け衣装として必要な検査

1. 正面・側面・背面の形状が資料と一致し、袖ぐり・襟・見返し・裏地・裾の接続が破綻していないこと。
2. アバターの骨格と衣装のウェイトが一致し、肩・肘・股・膝の動作で貫通や極端な伸びがないこと。
3. UV展開、色、法線、粗さ、金属度などの素材データが実際の布・樹脂・金具ごとに整理されていること。
4. 生地の厚さ、縫い目、ファスナー、留め具、小物の取付位置が近接表示でも成立すること。
5. 対象プラットフォームで三角形数、マテリアルスロット、テクスチャメモリ、スキンメッシュ数を計測すること。
6. Blenderでの確認だけで終わらず、最終的にUnityとVRChat SDKで表示・動作・パフォーマンスを検証すること。

FormaのGLB検査は三角形数・UV・PBR材質・テクスチャ・スキンメッシュを数える**一次検査**である。形状の美しさ、骨ウェイト、ライセンス、VRChatでの動作を自動認定しない。

## Blenderからプレビューする場合

衣装はアバターと同じ原点・向き・単位で配置し、テクスチャを含む単体の `.glb` として書き出す。Formaの「衣装GLBを読み込む」で選択すると、自動生成ラフと差し替えて360度確認できる。骨追従はこのプレビューでは保証しないため、アニメーション検査は制作元のリグとUnityで行う。

管理人の衣装をVRC相当まで制作するには、背面・側面の確認可能な資料、素体に合わせた骨・ウェイト、動作検査が必要である。今回の背面・側面は推定設計であり、見えない部分を推定しただけで「原作完全再現」や「VRC対応」と表示しない。

## 管理人専用Blenderアセット（推定設計）

`scripts/build_endministrator_garment.py` で、提供された女性管理人の正面画像を主資料にした衣装を作成した。コートの開いた外殻・左右の前身頃・ニット・曲げた袖・黄の肩パネル・襟・フード・金具・背面ハーネスを別メッシュとし、布・樹脂・金属で材質を分けている。コートの前開きと裾は身頃から連続した面で作り、厚みを付けている。正面確認で灰色の前身頃が裾まで続く問題を確認し、腰で終わる仕立てへ変更した。下部は暗いコートを見せ、裾の広がりと布のうねりを増やし、左右の裾角も連続シェル内で非対称にした。その後、ニット身頃の密度、袖の布量と皺、二重の袖口、曲面の黄色い肩パネル、腰周囲へ広がるコートの裾を調整した。足元には甲と靴底を分けた試着用の黒い靴を加えた。腹部ポケットの追加メッシュは、軽量化後に生地と重なる破綻が出たため採用していない。背面のフード、ハーネス、裾の処理は正面からは確認できないため、**衣装構造に基づく推定**である。

参照した[公式の戦闘デモ](https://www.youtube.com/watch?v=T3do8NpXWg8)では、高い襟、開いた長衣、明るい内衣、片側の黄の肩装飾と、おおまかな後ろ姿・動作を確認した。ただし映像は動きが速く、背面の縫い目や小物取付位置を特定できない。外販のコスプレ画像は構造の補助資料とし、公式設定と同一視していない。

- 編集元：`assets/endministrator/endministrator_authored_costume.blend`
- プレビュー用：`web/static/models/endministrator_authored_costume.glb`
- 三方向レンダリング：`output/endministrator_authored_v22/endministrator_front.png`、`endministrator_side.png`、`endministrator_back.png`
- 再生成：`blender -b -t 4 --python scripts/build_endministrator_garment.py -- output/endministrator_authored`

編集用の部品分割GLBは63,778三角形、102メッシュ、12材質、15テクスチャで、**スキンは0**。形状・部品を手直しするためのマスターであり、そのままVRChatに持ち込む軽量版ではない。

### 骨付き検証版（次の段階）

`scripts/rig_endministrator_garment.py` は上記の編集元を読み、布10材質を512pxタイルのカラー／法線アトラスにまとめる。厚手の布・ニットと、ナイロン・靴は反射の違う2材質に分け、黄の塗装材と金属材を残した。`web/static/models/endministrator_rigged_fitting.glb` のglTF構造検査では、メッシュ1体、骨10本を持つスキン1個、材質／描画プリミティブ4個、28,999三角形、テクスチャ4枚。Blenderで腕を下げた[変形テスト画像](../output/endministrator_rigged_v21/endministrator_rigged_arm_pose.png)も出力した。

編集元は `assets/endministrator/endministrator_rigged_fitting.blend`。単体GLBには骨とウェイトがあり、検証ページでは標準VRMと衣装の腕角度を簡易同期できる。ただしHumanoid骨格への完全なリターゲットではない。GLBローダーは材質プリミティブごとに4個のSkinnedMeshとして表示するため、Formaの画面には「スキンメッシュ4」と出る。Unityで1個のSkinnedMeshRendererにまとまるかは未検証。28,999三角形は**衣装単体**の数字であり、アバターの頭・体・髪・小物を足したVRChat全体の性能ランクではない。[VRChatの現行基準](https://creators.vrchat.com/avatars/avatar-performance-ranking-system/)では三角形・材質スロット・スキンメッシュなどをアバター全体で評価する。

検証ページでは衣装単体と付属のCC0試着用VRMを切り替えられる。管理人専用衣装の表示中だけ、付属VRMのサンプル靴と体の材質を非表示にし、顔・髪と衣装を表示する。腕を下げた際、この汎用VRMの手が衣装袖口に届かず、宙に浮いて見えるためである。ユーザーが読み込んだVRMにはこの処理を適用しない。これは表示上の措置であり、任意のアバターへ衣装が適合する証拠ではない。

残る必須作業は、実際に使うアバター骨格へのリターゲット、肩／肘／脚の大きな動作・しゃがみでの貫通確認、背面意匠の資料照合、Unity Humanoid設定とVRChat SDKでの性能・見え方検査。したがって骨付き検証版も「VRC完成衣装」とは呼ばない。

## 公開3D衣装の調査結果（2026-10-02）

| 配布元 | 権利・構造 | 採用判断 |
| --- | --- | --- |
| [ShimaeWorkShopのコート＋素体](https://booth.pm/ja/items/2083525) | 作者がCC0と明記。衣装単体のFBX、UV・テクスチャ、Humanoid構成の骨を含み、コートは約18,810三角形。 | 形状と制作方式は最も有望。ただし無料取得でもBOOTHログインが必要なため、現時点では未取得・未組込み。 |
| [voloskyscapeのハイカラー長衣](https://blendswap.com/blend/27971) | 作者オリジナル、CC BY。Blender元データあり、約242,508面。 | 襟と長衣の形状は有望。ただしBlendSwap/Sketchfabともログインが必要で、全体の軽量化・リグ化も必要。未取得・未組込み。 |
| [3DAssets.devのSable Scout](https://3dassets.dev/assets/hero-shooter-harbour-payload-hero-sable-idle-7ba4d063) | CC0、直接GLB取得可、7,840三角形。ただし一体化された静止ポーズで、骨格とスキンウェイトがない。 | 実物を確認。コートは単純化され、管理人の衣装やVRC向け可動衣装の基準を満たさないため採用しない。 |
| [OverScore Proxy](https://opengameart.org/content/overscore-proxy-modular-low-poly-female-character-creation-set) | CC0、Blenderファイルを直接取得可。多数の服パーツを含むが、作者自身がローポリ・未リグ・UVなし・テクスチャなしと記載。 | 衣装制作の練習用には使えるが、この品質目標の完成素材には使わない。 |

無料・CC0・ダウンロード可能というだけで「VRC品質」と判断しない。管理人の衣装に必要なハイカラー、開いた長い裾、左右非対称の肩装飾、袖と身頃の接続、UV/PBR、リグ・ウェイトを個別に検査する。上の候補は実装済み素材ではなく、採用検討の記録である。

参考： [VRChat公式のアバター制作手順](https://creators.vrchat.com/avatars/creating-your-first-avatar/)・[パフォーマンス指標](https://creators.vrchat.com/avatars/avatar-performance-ranking-system/)・[Blender 5.2のglTF書き出し](https://docs.blender.org/manual/en/5.2/addons/scene_gltf2.html)。
