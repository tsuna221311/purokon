"""darts.py — バスト-ウエスト差から算出するウエストダーツ。

これまでの体型スケーリング(engine/scaling.py)は、パーツ全体をX/Y均一倍率で
拡大縮小するだけの線形変形だった。これはバスト-ウエスト比が標準Mサイズと
大きく異なる体型（いわゆる「くびれ」が強い/弱い体型）では、バスト基準で
幅を決めるとウエストが太くなりすぎ、ウエスト基準で決めるとバストが
きつくなる、という矢面に必ず当たる。

実務のパタンナーはこれを「ウエストダーツ」（裾～ウエストラインから体の内側
に向けて摘み込む、V字のつまみ）で解決する。このモジュールは、
front_bodice / back_bodice の裾ラインに対して、標準的な運針・ダーツ配置の
考え方に沿った最小限のウエストダーツを自動追加する。

できること:
  - バスト比とウエスト比の差分から、必要なダーツの摘み量(intake)を算出する
    （標準的な運針: intake = 半幅の差分 - 着用ゆとり、1本あたり2.5cmを超え
    たら2本に分割）。
  - 裾ラインの中で最も外側(y最大)にある水平な直線セグメントを裾として自動
    検出し、そこにV字の切り込み(ダーツ)を挿入する。位置はテンプレートの
    生成方法に依存しないよう、セグメントのインデックスではなく実際の幾何
    （水平線・y最大）から動的に求める。

できないこと（正直な範囲の限定）:
  - バストポイントに向かう本当のバストダーツ（肩・脇からバスト頂点に収束
    するダーツ）や、プリンセスラインのような分割線は再現しない。あくまで
    「裾(ウエストライン)から真上に伸びる、単純なウエストダーツ」のみ。
  - front_bodice / back_bodice 以外（袖・スカート・パンツ等）のダーツは
    対象外（線形スケーリングのまま）。

追記（脇ダーツ / apply_bust_dart）:
  上記のウエストダーツだけでは、バストが標準より大きい体型で「バスト位置
  周りの丸み（凸曲面）」を平面の型紙で表現できない、という別種の不足が
  残る。これはウエスト-バスト比の差ではなく、バスト絶対値そのものに
  起因する不足なので、ウエストダーツ(compute_dart_plan)とは別立てで
  `apply_bust_dart`として実装した。前身頃(front_bodice)の脇線（袖付けと
  裾の間の直線区間）に、バストの標準サイズからの超過分に比例した摘み量の
  V字ノッチを追加する。後身頃には適用しない（実務でも後ろ身頃にバスト
  ダーツは通常使わない）。

  【round5での改良】以前はダーツ先端が「脇線からCF方向へ、摘み量(intake)
  と同じ距離だけ水平に凹む」だけで、先端がどこを狙っているのか(=収束点)
  が定義されていなかった。round5では、BP(バスト頂点)の位置をCF-脇線間の
  距離に対する比率(BUST_APEX_OFFSET_RATIO)・脇線に沿った高さの比率
  (BUST_APEX_HEIGHT_RATIO)で推定し、ダーツの先端をその推定BPへ向かう
  直線上に置くよう変更した。先端はBPそのものには到達させず、摘み量が
  大きいほどBPに近づく(BUST_APEX_REACH_MIN_RATIO〜REACH_MAX_RATIO)。これに
  より「ダーツは実在のバスト頂点に向かって収束する」という実務の考え方を
  一部反映できたが、依然として次の点で本物のバストダーツには及ばない:
  BPの位置は実測ではなく比率による推定値である、収束するダーツは脇線発の
  1本のみ(実務では肩ダーツ・ウエストダーツ・フレンチダーツ等、複数の
  方向からBPへ収束させる設計もよく使われる)、プリンセスラインのような
  分割線による表現は非対応、という3点は変わらない。

  【round6で発見・修正した不具合: ダーツの口から先の脇線が消えていた】
  上記のround5改良版には、ダーツ挿入後の3点(口の片方→先端→口のもう片方)
  だけを脇線セグメントの置き換えとして返し、その先(元のセグメントの
  本来の終点`end`)を返り値に含めていない不具合があった。このプロジェクトの
  ダーツはパスの境界線そのものにV字の切り込みを入れる表現（境界線上の
  ある区間を、そのまま「口→先端→口」の3点に置き換える）であるため、
  置き換え後は必ずパスを元のセグメントの終点座標へ戻す最後の点を含めない
  と、次に続くセグメント(前身頃なら袖ぐりカーブ)が誤った位置から描画
  されてしまい、脇線の「ダーツの口から元の終点まで」の区間が黙って消失し、
  後続の袖ぐり形状も歪んだ位置にずれる。`apply_waist_dart`・
  `apply_skirt_waist_dart`・`apply_pants_waist_dart`は元々`hem_end`/
  `top_end`をきちんと返り値の末尾に含めていたため影響が無く、
  `apply_bust_dart`のみに存在した不具合だった。round6でこの不具合を修正し
  (新設の`_bust_dart_notch`ヘルパーが常に`end`を末尾に含めて返す)、
  脇線の区間が消失しないことをテストで確認している
  (test_apply_bust_dart_does_not_swallow_the_remaining_side_seam_run)。

追記(round14: 脇ダーツの摘み量と、前後の脇線長の一致):
  round13までの脇ダーツには、独立した2つの誤りがあった。

  1. ダーツの口の幅が4.0cm固定で、`compute_bust_dart_intake_cm`が求めた
     摘み量(0.3〜3.0cm)は「先端をBPへどこまで近づけるか」にしか使われて
     いなかった。つまりバスト86cmの人もバスト140cmの人も同じだけ摘んで
     いて、計算した必要量が型紙に反映されていなかった。
  2. 口の幅ぶん前身頃の脇線が短くなるのに、後ろ身頃側には何の補正も
     無かった。実測で前61.9cm・後69.9cm(片側4.0cm差)。脇はこの2辺を
     縫い合わせる場所なので、そのままでは縫えない。

  round14で、口の幅=摘み量とし(`_bust_dart_notch`)、ダーツの口より下を
  摘み量ぶん下げて丈を足すようにした(`_shift_below`)。これで縫い閉じた
  後の脇線長が前後で一致し、前身頃はバストのぶんだけ丈が長い、という
  実際の身頃の関係にも合う。

追記（スカートのウエストダーツ / apply_skirt_waist_dart）:
  `skirt`は従来、幅をヒップ比のみで一様に変形しており、ウエストは一切
  考慮していなかった。これは`skirt(flare)`のようにウエストで摘まず
  ギャザー/フレアで逃がすデザインでは問題にならないが、`skirt(tight)`の
  ようなフィットしたスカートでは、ヒップに対してウエストが標準より
  細い体型（多くの体型がこれに該当する）で、実際にはウエストラインが
  たるむ結果になる。`apply_skirt_waist_dart`は、身頃のウエストダーツと
  同じ「ヒップ比とウエスト比の差分から摘み量を算出し、セグメント順序に
  依存せず幾何(上端の水平線)から挿入位置を探す」設計で、skirt(tight)の
  ウエストライン(上端)にダーツを追加する。skirt(flare)には適用しない
  （意図的にウエストで摘まないデザインのため）。同じくフィットした
  デザインのskirt(mermaid)（腰から膝下まで細身、そこから裾で大きく
  フレアが広がるシルエット）も対象に含めている
  (`SKIRT_DART_ELIGIBLE_VARIATIONS`)。

追記（パンツのウエストダーツ / apply_pants_waist_dart）:
  `pants`も`skirt`と全く同じ理由（幅をヒップ比のみで変形しており、
  ウエストを考慮していない）で同じ不足を抱えている。パンツはスカートの
  ようなデザイン上の意図的な「フレアで逃がす」選択肢が無く、どの脚の
  シルエット(standard/wide/tapered/shorts/flare)でもウエストで実際に
  フィットさせる必要があるため、`apply_pants_waist_dart`は`skirt(tight)`とは異なり
  全てのpantsバリエーションに適用する。仕組みは`apply_skirt_waist_dart`と
  同一（上端の水平線を幾何的に検出し、ヒップ比・ウエスト比の差分から
  摘み量を算出してV字ダーツを挿入）。対象part_typeは`front_pants`/
  `back_pants`の両方(PANTS_DART_ELIGIBLE_PART_TYPES)で、前後どちらにも
  同じ算出式を適用する（実務では前後で摘み量を変えることも多いが、ここでは
  簡易化のため同一ロジックを共有する）。

追記（パンツの前後分離 / round5）:
  以前は`pants`という1つのpart_typeが「片脚を左右の脇線で開いて平らに
  した1枚の輪郭」を表現しており、前後で形状の違いが無い（脇線1本のみが
  縫い目で、股下は折り目線という簡易構造）近似だった。round5で
  `front_pants`/`back_pants`という2つのpart_typeに分離し、実際のパンツ
  同様に「脇線+股下(インシーム)の両方が縫い目」という構造に変更した。
  後ろパーツ(back_pants)は前パーツ(front_pants)より股上を深く・長く取り
  （実務で一般的な「後ろ股上は前股上より2〜4cm長い」という経験則の
  単純化）、かつ中心線(センターバック)をわずかに外側へ膨らむカーブに
  することで、臀部のゆとりを表現した。中心線が直線のままの前パーツ
  (front_pants、センターフロントは直線が一般的)とは対照的な設計にして
  いる。とはいえ依然として、前後で脚の太さ・裾幅は共通にしている
  （実際には前後で裾の落ち感が異なることもあるが、ここでは近似の範囲を
  超えるため踏み込んでいない）点、股上の深さ・膨らみの量は実測ではなく
  経験則の比率である点は正直に限定として残る。

追記（前開きファスナーの前後分割 / round5、front_bodice_zip_panelの
  ダーツ非対応について）:
  round5で前開きファスナー(front_zip)を、ネックライン形状だけを変えた
  簡易版から、実際に中心前で身頃を左右2枚のパネルに分割し、見返し
  (facing)分の折り返し代を追加した構造に変更した(生成は
  `scripts/generate_templates.py`の`_front_zip_panel_d`、part_typeは
  `front_bodice_zip_panel`)。round5の時点ではこのpart_typeを意図的に
  DART_ELIGIBLE_PART_TYPES/BUST_DART_ELIGIBLE_PART_TYPESに含めていなかった
  （＝front_zip=Trueの前身頃には、ウエストダーツも脇ダーツも自動追加
  されなかった）。理由は、両ダーツの幾何検出ロジック(`_find_hem_segment_index`
  や`_find_side_seam_segment_indices`)が「左右対称で、脇線が2本ある」
  という前提を置いているためで、中心前で分割済みの片側パネル(脇線が
  1本、対して中心前は直線または見返しの張り出しを含む縁)にそのまま
  適用すると、中心前の縁を誤って"もう1本の脇線"として検出し、誤った
  位置にダーツを置いてしまう恐れがあったため。

追記（前開きファスナー×脇ダーツの併用対応 / round6）:
  round6で、脇ダーツ(apply_bust_dart)についてのみ上記の制限を解消した
  （ウエストダーツ(apply_waist_dart)は今回も対象外のまま。理由は下記）。
  `front_bodice_zip_panel`のテンプレート(`_front_zip_panel_d`)を実際に
  幾何的に調べたところ、パネルの輪郭には`_find_side_seam_segment_indices`
  の条件（ほぼ垂直かつ`MIN_SIDE_SEAM_LENGTH_CM`超の直線(L)セグメント）に
  当てはまる縦線が"ちょうど2本"存在する: 外側の脇線(bboxのx最大側、
  y方向の到達範囲は袖ぐり下端〜裾)と、中心前の見返し/裁ち割り線
  (bboxのx最小側、見返し分の張り出しがあるためネックラインに近い側まで
  到達する)である。この2本は"どちらも本物の縦線"なので、本数だけでは
  区別できない。そこで新設した`_bust_dart_zip_panel_side_index`で、
  「外側の脇線は中心前の縁よりネックラインから遠い(=y_topが大きい)
  はず」という2本目の幾何的性質を追加の判定軸として使い、2本の候補の
  うちx座標が大きい方が本当にy_topも大きいことを確認した上で、それを
  外側の脇線と判定する。この交差検証に失敗した場合(想定外の形状)は、
  安全側に倒してダーツを諦める(Noneを返す)。バストダーツの計算自体は
  `_bust_dart_notch`に切り出し、通常のfront_bodice(左右対称、中心前は
  2本の脇線の中点として求める)と、front_bodice_zip_panel(非対称、
  中心前は実際の見返し/裁ち割り線のx座標そのもの)の両方から、
  「ダーツの基準となる中心前のx座標(cf_x)」を引数として渡す形に共通化
  した。front_bodice_zip_panelでは中心前の縁自体には手を加えず、外側の
  脇線1本にのみダーツを追加する(パネル1枚あたりダーツ1本、
  前身頃全体では左右パネルの2枚分で計2本になる想定)。

  ウエストダーツ(apply_waist_dart)を対象外のままにした理由(round6時点): こちらは
  `_find_hem_segment_index`(y最大の水平線)で裾を検出し、裾の"両端"を
  中心前と脇線の位置として使う設計になっている。front_bodice_zip_panel
  の裾は「片側パネルの裾」であり、その両端は「外側の脇線の裾側の点」と
  「見返し分張り出した中心前の裾側の点」であって、どちらも実在の点では
  あるものの、ウエストダーツの計算が前提とする「裾の中点=中心前」という
  関係が成り立たない(見返し幅の分だけずれる)。この補正には、見返し幅
  (FACING_WIDTH_CM)をdarts.py側でも把握する必要があり、単純な既存ロジックの
  使い回しでは正しい位置にならない。バストダーツほど需要が高くないと
  判断し、round6の対応範囲からは外した。

追記（round11: front_bodice_zip_panelへのウエストダーツ対応）:
  round6の判断は「裾の中点=中心前という既存ロジックをそのまま使う」という
  前提での話であり、その前提自体を変えれば解消できることが分かった。
  脇ダーツが既に使っている`_bust_dart_zip_panel_side_index`/
  `_find_side_seam_segment_indices`は、裾の形に依存せず「輪郭上のほぼ垂直な
  2本の直線(外側の脇線・中心前寄りの見返し/裁ち割り線)を見分ける」手法で
  ある。これをウエストダーツにも流用し、裾の位置をその2本の縦線の
  「裾側の端点」から直接求めるようにした(`_apply_waist_dart_zip_panel`)。
  この方式なら、見返し幅(FACING_WIDTH_CM)の値をdarts.py側で知る必要が無い。

  実装中に実測で見つかった罠: zip_panelの輪郭はshapelyの交差計算で作られる
  ため、最初の頂点(Mの位置)が「外側の脇線が裾に接する角」になっており、
  裾のうち最も長い区間がZによる暗黙のクローズ辺として表現されていた。
  `cmd == "L"`だけを見る`_find_hem_segment_index`ではこれを検出できず、
  裾の隣にある見返し用の短い橋渡し辺(4cm)を誤って裾と判定してしまう。
  そのため`_materialize_closing_edge`でZを明示的なLに正規化してから処理し、
  さらに裾が複数のLに分かれている場合はその連続区間をまとめて差し替える
  ようにしている。

  正直な近似: 脇ダーツと同様、中心前寄りの縁(見返し/裁ち割り線)のx座標を
  そのまま中心前(CF)の代用として使っている。実際のCFは見返し幅の分だけ
  内側にあるため厳密ではないが、これは既にapply_bust_dartで採用・出荷済みの
  近似と同一であり、ダーツの位置決めと安全マージンの判定という用途には
  同じ粒度で足りると判断した。左右対称なfront_bodiceが2組のダーツを追加
  するのに対し、zip_panelはパネル1枚につき1組(前身頃全体では左右2枚分)。

追記（round7: 「本当のバストダーツ・プリンセスライン」の再調査）:
  round6までの「できないこと」節に挙げていた、(1)肩・アームホールから
  BPへ収束する複数方向のダーツ(肩ダーツ等)、(2)プリンセスラインのような
  分割線、の2つについて、実際に実装できないか調査した。結論は、どちらも
  現行のテンプレート構造を変えずには実装できず、変えるとなると
  影響範囲がround7の他タスクより一段大きい変更になるため、今回は見送る。
  以下、実際に調べた内容を正直に記録する。

  (1) 肩ダーツ(肩線・アームホールからBPへ収束するダーツ)について:
  `scripts/generate_templates.py`の`_bodice_path()`が組み立てる輪郭を実際に
  読むと、round_neck/v_neck/sweetheart/boat_neckの前身頃には「肩線」に
  相当する独立した直線セグメントが存在しないことが分かった。輪郭は肩先の
  点(shoulder_l/shoulder_r)から直接アームホールのベジエ曲線(`C ...`)が
  始まり、上端はネックライン自体のベジエ曲線または斜め線(`neck_d`、例えば
  round_neckなら`"C 20 2, 10 2, 8 0"`)がshoulder_rからshoulder_lへ直接
  橋渡ししている――つまり「肩線」は輪郭上でネックライン曲線そのものであり、
  独立した直線区間としては存在しない(`tests/test_darts.py`の
  `test_front_bodice_has_no_straight_shoulder_segment_for_every_neckline`
  で固定化)。なお、square_neck/turtle_neckの2種は例外で、ネックライン
  開口部の縁自体(角ネックの角・タートルネックの台襟の付け根)が水平な直線に
  なっている。ただしこれは「肩線」ではなく「ネックライン開口部の縁」その
  ものであり、ここにV字ノッチを入れると縫い目ではなくネックラインの見た目
  自体が変形してしまう上、過半数のネックライン(round/v/sweetheart/boat)には
  そもそも適用できないため、この例外があっても以下の結論は変わらない。
  既存の脇ダーツ・ウエストダーツは共通して「ほぼ垂直/水平な直線(L)
  セグメントを幾何的に検出し、その区間をV字ノッチに置き換える」という設計
  (`_find_side_seam_segment_indices`/`_find_hem_segment_index`はどちらも
  `cmd == "L"`のみを対象にしている)なので、この設計をそのままベジエ曲線
  (`C`)区間に適用することはできない。曲線の途中にダーツの口を安全に割り
  込ませるには、(a) ベジエ曲線を割線位置で2本に分割し直す幾何計算、
  (b) 分割後も元の曲率が不自然にならないことの検証、を新たに実装する必要が
  あり、既存の「直線区間を3点に置換するだけ」の実装より格段にリスクが高い。
  加えて、そもそもテンプレート側に独立した肩線区間が無い以上、肩ダーツを
  入れるなら`_bodice_path()`自体の輪郭設計を変更(肩線とアームホールを分離)する
  必要があり、既存47種テンプレート全ての再生成・検証が要る。

  (2) プリンセスラインについて:
  プリンセスラインは前身頃を「脇寄りパネル」と「中心寄りパネル(BPを含む)」
  の2枚に、BPを通る曲線の切り替え線で分割する構造。これは
  front_bodice_zip_panel(round5、中心前で直線的に2分割)より本質的に
  大きな変更になる。理由:
    - 切り替え線が直線ではなく、BP付近を通る曲線になる(でなければ
      「ダーツを縫い込んだのと等価な、体に沿う曲面」というプリンセス
      ラインの目的自体が成立しない)。この曲線をテンプレート設計として
      新たに起こす必要があり、根拠となる実測データが無い状態で「それらしい
      曲線」を当てずっぽうで描くと、他の箇所で避けている「根拠のない
      数値を精度向上と称して導入する」ことと同じ問題になる。
    - 新しいpart_type(例: `front_bodice_princess_side`/
      `front_bodice_princess_center`)を追加すると、`PART_SCALE_RULES`
      (採寸比率)・`PAIR_LABELS`(左右/前後ラベル)・
      `BUST_DART_ELIGIBLE_PART_TYPES`等のダーツ対象集合・
      `engine/compatibility.py`の`side_seam_length()`(前後身頃の脇線が
      "ちょうど2本"という前提)・ネスティングの矩形推定・PDF/DXF出力の
      パーツラベル、といった「front_bodiceは1part_typeである」ことを
      前提にしたコード全体に変更が波及する。round5のfront_zip_panel
      (直線分割のみ)でさえ複数roundにまたがる調整(round5で追加、round6で
      脇ダーツ対応・ウエストダーツ非対応の判断)を要しており、曲線分割の
      プリンセスラインはそれよりさらに影響範囲が大きい。
    - 新しいUIオプション・APIパラメータ・ネスティング/PDF/DXFの検証・
      既存579テスト超のうち影響を受けるテストの洗い出しまで含めると、
      round7の1タスクとして安全に収められる変更規模を超える。

  対応方針: 上記の理由により、round7では肩ダーツ・プリンセスラインの
  実装は見送る。存在しない実測データを使って「それらしい曲線」を
  当てずっぽうで作ることは、このプロジェクトが繰り返し避けてきた
  「根拠のない精度向上の主張」になってしまうため、実装するにしても
  実際のパタンナー監修の下でテンプレート自体を設計し直す将来の対応候補
  として、README「既知の限界」に正直に記載するに留めた。round5・round6で
  実装した「脇ダーツをBPへ収束させる」補正(本docstring上部参照)が、
  現行のテンプレート構造の中で実装可能な現実的な近似の到達点である。
"""

from __future__ import annotations
from math import atan2, ceil, cos, hypot, radians, sin
from dataclasses import dataclass

from .blocks import ADULT_FEMALE, Block
from .compatibility import DART_TRUING_MAX_OFFSET_CM
from .bodice_fit import bust_point_from_cf_cm, bust_point_y_cm
from .measurements import Measurements, STANDARD_M
from .part_specs import clamp_scale

# 着用ゆとり（ダーツで摘まずに残す分）。実測ではなく一般的な目安値。
EASE_CM = 1.0
# これより小さい摘み量は「差分ノイズ」として無視し、ダーツを追加しない。
MIN_DART_INTAKE_CM = 0.3
# 1本のダーツが摘む量の上限。これを超えたら2本に分割する。
MAX_SINGLE_DART_INTAKE_CM = 2.5
# 片側(左右どちらか半身)で摘む量の上限。極端な入力でダーツが暴走しない
# ようにするクランプ（MIN_SCALE/MAX_SCALEと同じ考え方）。
MAX_DART_INTAKE_PER_HALF_CM = 5.0
# ダーツの位置: 中心前(CF)からの距離を、裾半幅に対する比率で決める
# （バスト頂点の投影位置のごく簡易な近似。実際のバストポイント計測は
# 行っていない）。
DART_OFFSET_RATIO = 0.45
# 2本ダーツになった場合の、2本の中心間隔。
DART_SPACING_CM = 3.0
# ダーツの先端(裾から真上への長さ)の目安値。実際に使う長さは、裾から
# 袖付け(underarm)までの余裕の半分を超えないようにクランプする。
DEFAULT_APEX_LEN_CM = 12.0
# ダーツの両端が、中心前(CF)または脇線からこの距離未満まで近づく場合は、
# 安全側に倒してダーツを追加しない（不自然な位置になるのを避ける）。
MIN_CLEARANCE_CM = 1.0

DART_ELIGIBLE_PART_TYPES = {"front_bodice", "back_bodice", "front_bodice_zip_panel"}
# 上記のうち、片側パネル専用の幾何処理(`_apply_waist_dart_zip_panel`)が必要な
# part_type(round11で追加。BUST_DART_ZIP_PANEL_PART_TYPESと同じ考え方)。
WAIST_DART_ZIP_PANEL_PART_TYPES = {"front_bodice_zip_panel"}

# --- 脇ダーツ(バストダーツの簡易近似) ---------------------------------
# 前身頃のみ対象（後ろ身頃には適用しない）。round6でfront_bodice_zip_panel
# (前開きファスナー用の片側パネル)も対象に追加した。
BUST_DART_ELIGIBLE_PART_TYPES = {"front_bodice", "front_bodice_zip_panel"}
# 上記のうち、片側パネル専用の幾何処理(_bust_dart_zip_panel_side_index)を
# 使う必要があるpart_typeの集合。
BUST_DART_ZIP_PANEL_PART_TYPES = {"front_bodice_zip_panel"}
# バストが標準Mサイズよりこの値(cm)を超えて大きい分に対し、脇線から
# 摘み込む量(cm)を比例配分する経験則の係数。実測に基づく厳密な値ではなく、
# 「バストが大きいほど脇の丸みを補うダーツが必要になる」という定性的な
# 傾向を、既存のウエストダーツと同程度の大きさ感で近似したもの。
#
# 【round29で既定から外した】この係数は上のコメントが認めている通り
# 当てずっぽうで、しかも「標準Mより大きい分」しか見ないため、
# **バスト83cm以下の体型にはバストダーツが1本も入らなかった**。実測:
#
#   バスト  60 → 0.00cm   83 → 0.00cm   110 → 2.70cm   120 → 3.00cm(上限)
#
# 胸の丸みは標準サイズを超えた人だけのものではないので、これは
# 「精度が粗い」ではなく**欠落**である。round29からは新文化式の
# 胸ぐせダーツ角(BUST_DART_ANGLE_*)から求める。この係数は、BPの位置が
# 分からない呼び出し(単体テスト等)のフォールバックとしてのみ残す。
BUST_DART_COEFFICIENT = 0.10
# これ未満の摘み量は「差分ノイズ」として無視する。
MIN_BUST_DART_INTAKE_CM = 0.3
# 暴走防止のクランプ(フォールバック経路のみ)。
MAX_BUST_DART_INTAKE_CM = 3.0

# --- 胸ぐせダーツ(新文化式の角度式。round29) ------------------------------
#
# 新文化式原型では、胸ぐせダーツの大きさを**BPを頂点とする角度**で決める:
#
#     胸ぐせダーツ角 = (B/4 − 2.5) 度
#
# 角度で決まるのは理にかなっている。ダーツが担うのは「胸の丸みの分だけ
# 布を立体にする」ことで、必要な立体の量はBPからの距離ではなく開き角で
# 決まるからである。摘み量(口の幅)は、そこからBPまでの距離Lを使って
#
#     摘み量 = 2 L sin(角/2)
#
# で求まる。同じ角度でも、BPから遠いところに口を開ければ摘み量は大きく
# なる——という関係が自然に出る。
#:
#: 【round42】数値は`engine/blocks.py`の`ADULT_FEMALE`が持つようになった
#: (原型ごとに角が違う。子ども原型は一律8°)。ここはその読み出しで、
#: 既存の名前はテストと注記が参照しているため残してある。
BUST_DART_ANGLE_DIVISOR = ADULT_FEMALE.bust_dart_angle.divisor
BUST_DART_ANGLE_CONST_DEG = -ADULT_FEMALE.bust_dart_angle.const

#: 脇線に開く1本のダーツの摘み量の上限(cm)。これを超える分は、実務と
#: 同じくウエストへ回す(`engine/scaling.py`のダーツ移動)。1本で摘む量が
#: 大きすぎると、口が縦に長くなりすぎて縫いにくく、胸の下に「角」が出る。
MAX_SIDE_BUST_DART_INTAKE_CM = 6.0

#: 脇線に2本のダーツを並べるときの、口と口の間隔(cm)。縫い代が重なると
#: 縫えないので、最低限の隙間を空ける。
BUST_DART_GAP_CM = 2.0

#: 脇線に並べられるダーツの本数の上限。
MAX_SIDE_BUST_DART_COUNT = 2
# 脇線のうち、袖付け側からの距離の割合でダーツの位置(バスト位置の簡易
# 近似)を決める。0に近いほど袖付けに近く、1に近いほど裾に近い。
BUST_DART_HEIGHT_RATIO = 0.30
# ダーツの「口」(脇線上で摘みが始まる/終わる区間)の縦幅の**下限**。
#
# 【round14で直した不具合】round13まで、口の幅はこの4.0cm固定で、
# `compute_bust_dart_intake_cm`が求めた摘み量は「ダーツ先端をBPへどこまで
# 近づけるか」にしか使われていなかった。つまり:
#
#   * バスト86cmの人もバスト140cmの人も、同じ4.0cmだけ摘む
#     (必要量は0.3cm〜3.0cmと計算できているのに、それが使われない)
#   * 前身頃の脇線は、口の幅ぶんだけ後ろ身頃より短くなる。実測すると
#     前61.9cm・後69.9cm(片側で4.0cm差)で、**そのままでは脇を縫い合わせ
#     られない**。`engine/compatibility.py`のチェック1がこれを検出して
#     いたが、警告文が「ダーツが入るとその分短くなるため発生することが
#     あります」と、あたかも正常な現象であるかのように説明していた。
#
# round14で、口の幅=摘み量にし(摘む量とはそういう意味である)、
# ダーツより下を摘み量ぶん下げて、縫い合わせた後の脇線長が前後で
# 一致するようにした(`apply_bust_dart`参照)。この定数は、摘み量が
# ごく小さいときでも合印を打てる程度の口を確保するための下限として残す。
BUST_DART_MIN_MOUTH_CM = 0.6
# 脇線としてみなす直線(L)セグメントの最小の縦方向の長さ。これより短い
# 縦線は脇線ではない（誤検出防止）とみなす。
MIN_SIDE_SEAM_LENGTH_CM = 10.0
#: 脇線を「ほぼ垂直」とみなす横ずれの上限(縦の長さに対する比)。
#: `engine/compatibility.py`の`NEAR_VERTICAL_MAX_DX_RATIO`と同じ値。
#: 判定を2か所に書くと片方だけ直して静かに食い違うため、そちらから取る。
SIDE_SEAM_MAX_DX_RATIO = 0.25
#: 「その高さでの輪郭の外側に乗っている」とみなす許容(cm)。
#: `engine/compatibility.py`の`side_seam_length`が使う値と同じ。
SIDE_SEAM_EDGE_TOL_CM = 0.5

# --- バスト頂点(BP)推定(round5: 脇ダーツをBPへ収束させる改良) ----------
# BP(バストポイント)の水平位置を、中心前(CF)から脇線までの距離
# (half_width_side)に対する比率で近似する。実測のBP位置ではなく、
# 「B/4程度の前身頃半幅に対し、BPはCFから概ね4割強の位置にある」という
# 一般的なパターンメイキングの経験則(BP間隔≒B/10前後)を単純化した近似値。
BUST_APEX_OFFSET_RATIO = 0.45
# BPの脇線に沿った高さ位置(袖付けからの比率)。ダーツの口の高さ
# (BUST_DART_HEIGHT_RATIO)とは独立した値で、口の位置とBPの位置が
# 完全には一致しない(ダーツの脚がやや斜めにBPへ向かう)ことを表現する。
BUST_APEX_HEIGHT_RATIO = 0.42

# --- round28: BPを「体の位置」で決める --------------------------------------
#
# 上のBUST_APEX_*_RATIOは、BPの位置を**脇線に沿った比率**で近似していた。
# 脇線は袖付けから裾までなので、0.42という比率が指す高さはウエストの
# あたりになる。つまりバストダーツがバストではなくウエストを向いていた
# (engine/bodice_fit.pyの`bust_point_from_cf_cm`に実測を記載)。
#
# round28からは、テンプレートが持つ基準線(data-fit-y の underarm =
# バストライン)と、バストから決まるBP間隔を使って、BPの位置を
# **体の座標**で決める。基準線を渡せない呼び出し(ダーツの幾何だけを
# 単体で確かめるテスト等)では従来の比率へフォールバックする。

#: ダーツの口の中心を、バストラインからどれだけ下げるか(cm)。
#:
#: BPはバストラインの上にあり、身頃のテンプレートでは**袖ぐりの底も同じ
#: バストラインの上**にある(袖ぐり深さの定義がそうなっている)。つまり
#: 口をBPと同じ高さに開けると、脇の下すれすれ——脇線の一番上——になり、
#: 縫えない。実物の型紙でも脇ダーツは脇の下から数cm下げた位置に開け、
#: そこから斜め上へBPへ向かう(あの「斜めに上がる脇ダーツ」の形)。
#: 6cmは、脇線(袖ぐり底〜裾で約35cm)に対して縫い代とアームホールの
#: 縫い止まりを避けられる標準的な位置。
BUST_DART_MOUTH_DROP_CM = 6.0
#: ダーツの先端をBPの手前で止める距離(cm)。BPまで刺すと、そこだけ布が
#: 尖って浮くため、実務では2〜3cm手前で止める。
BUST_APEX_SETBACK_CM = 2.5

#: round71: たたみ出し(truing)で、ダーツの口が脇線から外れてよい上限(cm)。
#:
#: 【なぜ要るか】脇の胸ぐせダーツは、口を脇線の上に置き、先端をBPへ向けて
#: 斜めに刺す。口の中心より先端が上にあるので、**2本の脚の長さが揃わない**。
#: 実測(round71、全サイズ): 脚は 10.97〜20.76cm に対して差が 1.75〜2.22cm
#: (8〜14%)あった。ダーツは脚どうしを合わせて縫うので、長い方が1.8〜2.2cm
#: 余る——つまり**たたんでも平らにならず、脇線に段差が出る**。
#:
#: 洋裁では、ダーツをたたんだ状態で脇線を引き直して裁つ(たたみ出し)。
#: その結果、片方の口は脇線の外へ少し出る。この定数は、その出っ張りが
#: 大きくなりすぎたとき(想定外の形状)にたたみ出しを諦めるための上限。
#:
#: 見張る側(`engine/compatibility.py`の`_is_dart_notch_at`)も同じ値を
#: 使うので、**値はあちらに置いて、ここでは読むだけにする**。2か所に
#: 書くと、片方だけ動かしたときに「ダーツをダーツと認識できない」形で
#: 静かに壊れる。
BUST_DART_TRUING_MAX_OFFSET_CM = DART_TRUING_MAX_OFFSET_CM

#: 仕上げの揃え直し(`retrue_bust_darts`)が直してよい、脚の長さのぶれ(cm)。
#:
#: ダーツを作った時点では脚はぴったり揃う。そのあとに掛かるウエスト絞り・
#: 裾の開きが口を動かす量は、実測で0.138cmである。ここはその**ぶれ**を
#: 直すためだけのもので、作るときに揃えるのを諦めたダーツを揃え直す
#: 場所ではない。諦めたものをここで揃えると、既に済ませた「前身頃を
#: 縮む量ぶん長くする」補正と釣り合わなくなる。
RETRUE_MAX_DRIFT_CM = 0.6
# ダーツの先端は、推定したBPそのものへは到達させない(実際の縫製でも
# 先端がBPよりわずかに手前で止まるのが普通で、頂点そのものを突き刺すと
# 不自然な尖りになる)。摘み量が小さいほど先端はBPの手前(REACH_MIN)、
# 摘み量が最大(MAX_BUST_DART_INTAKE_CM)に近いほどBPに近づく(REACH_MAX)
# ように線形補間する。これにより「摘み量はダーツの開き角度(口の幅)だけで
# なく、先端がBPにどれだけ近づくかにも反映される」という、単純な水平移動
# より現実に近い挙動になる。
BUST_APEX_REACH_MIN_RATIO = 0.35
BUST_APEX_REACH_MAX_RATIO = 0.85

# --- スカートのウエストダーツ(ヒップ-ウエスト差の簡易近似) -------------
# round9で追加したcircle(サーキュラースカート)はflare/pleated/wrapと同じ
# 「意図的にウエストで摘まずフレアで逃がすデザイン」に分類し、対象外の
# ままにしている(engine/pipeline.pyのSKIRT_STYLES追記コメント参照)。
SKIRT_DART_ELIGIBLE_VARIATIONS = {"tight", "mermaid"}
# 身頃のウエストダーツと同じ考え方の定数。値も同じ大きさ感で揃えている。
SKIRT_DART_EASE_CM = 1.0
SKIRT_MIN_DART_INTAKE_CM = 0.3
SKIRT_MAX_SINGLE_DART_INTAKE_CM = 2.5
SKIRT_MAX_DART_INTAKE_PER_HALF_CM = 5.0
# ウエストダーツの位置(中心からの比率)・間隔は身頃と同様の値を流用。
SKIRT_DART_OFFSET_RATIO = 0.45
SKIRT_DART_SPACING_CM = 3.0
# ダーツの先端(ウエストラインから下向きへの長さ)の目安値。
SKIRT_DEFAULT_APEX_LEN_CM = 12.0

# --- パンツのウエストダーツ(ヒップ-ウエスト差の簡易近似) -------------
# skirtと違い、どの脚のシルエットでもウエストで実際にフィットさせる
# 必要があるため、全variationを対象にする（PANTS_STYLESの全メンバー）。
# round9でcropped(クロップド丈)を追加した際も、この「全variation対象」の
# 方針に従いここへ追加している（追加を忘れるとcroppedだけダーツが
# 効かなくなる、というエンジン側の罠。engine/pipeline.pyのPANTS_STYLES
# 追記コメント参照）。
PANTS_DART_ELIGIBLE_VARIATIONS = {"", "wide", "tapered", "shorts", "flare", "cropped"}
# round5でpantsをfront_pants/back_pantsに分離した後も、どちらのパーツにも
# 同じウエストダーツのロジックを適用する（前後で摘み量の算出式・対象
# variationを変える理由が特に無いため、同一のロジックを共有する）。
PANTS_DART_ELIGIBLE_PART_TYPES = {"front_pants", "back_pants"}
# 定数の値自体はskirtと同じ大きさ感で揃えている…と言いたいところだが、
# round5でfront_pants/back_pantsに分離した結果、compute_pants_dart_planへ
# 渡すscaled_half_width_cmは「パーツ自身の中心線から脇線までの半幅」に
# なり、分離前(1枚が脚全周を表していた頃)のおよそ半分の大きさになった。
# EASE_CM・MIN/MAX_DART_INTAKE_CMのような絶対cm値の定数は、半幅の
# スケールと無関係に固定値のままだと、半幅が半分になった分だけ相対的に
# 効きすぎてダーツが発生しにくくなってしまう(実際にpear-shape回帰テストで
# 検出した)。そのため半幅のスケール変化に合わせてこれらの絶対値も半分に
# 調整した(DART_OFFSET_RATIO/SPACING_CMのような「比率」「配置距離」は
# 半幅のスケールに依存しないため変更していない)。
PANTS_DART_EASE_CM = 0.5
PANTS_MIN_DART_INTAKE_CM = 0.15
PANTS_MAX_SINGLE_DART_INTAKE_CM = 1.25
PANTS_MAX_DART_INTAKE_PER_HALF_CM = 2.5
PANTS_DART_OFFSET_RATIO = 0.45
PANTS_DART_SPACING_CM = 3.0
# パンツは股上カーブがウエストからすぐ(標準テンプレートではy=14)始まる
# ため、ダーツの先端はスカートより短く抑える。
PANTS_DEFAULT_APEX_LEN_CM = 7.0


@dataclass(frozen=True)
class DartPlan:
    darts_per_half: int
    intake_per_dart_cm: float
    #: round26: ヒップが通る幅を確保するために摘み量を減らしたか。
    #: 減らした場合、ウエストは本来より絞りきれていない(利用者へ開示する)。
    limited_by_hip: bool = False

    def is_empty(self) -> bool:
        return self.darts_per_half == 0


NO_DART = DartPlan(darts_per_half=0, intake_per_dart_cm=0.0)


def compute_dart_plan(part_type: str, scaled_half_width_cm: float,
                       measurements: Measurements,
                       hip_ease_cm: float | None = None,
                       dartless: bool = False) -> DartPlan:
    """バスト比・ウエスト比と、体型スケーリング後の裾半幅からダーツ計画を求める。

    scaled_half_width_cm: バスト比でX方向を変形した後の、身頃の裾半幅(cm)。
    「ウエスト比で変形した場合の目標半幅」との差分を、ダーツの摘み量とする。

    【round26で加えた上限】このダーツは**裾の線**に入るが、身頃の裾は
    ヒップの高さにある(テンプレートの丈58cmは首の付け根からヒップまで)。
    つまり摘みすぎると、ヒップが通らない=着られない型紙になる。実測:

      B/W/H        裾の開き   ヒップ+ゆとり     差
      83/58/98      83.97      102.0       -18.0   ← 腰を通らない
      83/50/100     72.94      104.0       -31.1

    そこで「裾がヒップ+ゆとりを下回らない」ところで摘み量を止める。
    止めた場合は`limited_by_hip`を立て、呼び出し側が
    「ウエストは絞りきれていない」と開示する(黙って絞らないのでも、
    黙って着られない型紙を出すのでもない)。

    hip_ease_cm を渡さない場合はこの上限を適用しない(ダーツの幾何だけを
    単体で確かめるテスト等、身頃以外の文脈から呼ばれるため)。
    """
    if part_type not in DART_ELIGIBLE_PART_TYPES or scaled_half_width_cm <= 0:
        return NO_DART
    if dartless:
        return NO_DART      # round30: 伸びる生地はダーツを入れない

    bust_ratio = clamp_scale(measurements.bust / STANDARD_M.bust)
    waist_ratio = clamp_scale(measurements.waist / STANDARD_M.waist)
    if bust_ratio <= 0 or waist_ratio >= bust_ratio:
        # ウエストがバスト比以上に太い(くびれが無い)体型では、ウエストを
        # 摘む必要がない。
        return NO_DART

    target_half_width = scaled_half_width_cm * (waist_ratio / bust_ratio)
    intake = scaled_half_width_cm - target_half_width - EASE_CM
    intake = min(intake, MAX_DART_INTAKE_PER_HALF_CM)

    limited = False
    if hip_ease_cm is not None:
        # 裾(=ヒップの高さ)がヒップ+ゆとりを下回らない範囲に抑える。
        # 前後2枚×左右2辺の計4辺で分担するので、1辺あたりの上限は
        # 「半幅 - 必要な周長/4」。
        hip_limit = scaled_half_width_cm - (measurements.hip + hip_ease_cm) / 4.0
        if hip_limit < intake:
            limited = intake >= MIN_DART_INTAKE_CM
            intake = max(0.0, hip_limit)

    if intake < MIN_DART_INTAKE_CM:
        return DartPlan(darts_per_half=0, intake_per_dart_cm=0.0,
                         limited_by_hip=limited)

    if intake <= MAX_SINGLE_DART_INTAKE_CM:
        return DartPlan(darts_per_half=1, intake_per_dart_cm=intake,
                         limited_by_hip=limited)
    return DartPlan(darts_per_half=2, intake_per_dart_cm=intake / 2.0,
                     limited_by_hip=limited)


def compute_skirt_dart_plan(variation: str, scaled_half_width_cm: float,
                             measurements: Measurements) -> DartPlan:
    """ヒップ比・ウエスト比と、体型スケーリング後のウエスト半幅からスカートの
    ダーツ計画を求める。`compute_dart_plan`のバスト/ウエスト版と同じ考え方を
    ヒップ/ウエストに置き換えたもの。

    scaled_half_width_cm: ヒップ比でX方向を変形した後の、スカートの
    ウエストライン(上端)半幅(cm)。「ウエスト比で変形した場合の目標半幅」
    との差分を、ダーツの摘み量とする。
    """
    if variation not in SKIRT_DART_ELIGIBLE_VARIATIONS or scaled_half_width_cm <= 0:
        return NO_DART

    hip_ratio = clamp_scale(measurements.hip / STANDARD_M.hip)
    waist_ratio = clamp_scale(measurements.waist / STANDARD_M.waist)
    if hip_ratio <= 0 or waist_ratio >= hip_ratio:
        # ウエストがヒップ比以上に太い体型では、ウエストを摘む必要がない。
        return NO_DART

    target_half_width = scaled_half_width_cm * (waist_ratio / hip_ratio)
    intake = scaled_half_width_cm - target_half_width - SKIRT_DART_EASE_CM
    intake = min(intake, SKIRT_MAX_DART_INTAKE_PER_HALF_CM)
    if intake < SKIRT_MIN_DART_INTAKE_CM:
        return NO_DART

    if intake <= SKIRT_MAX_SINGLE_DART_INTAKE_CM:
        return DartPlan(darts_per_half=1, intake_per_dart_cm=intake)
    return DartPlan(darts_per_half=2, intake_per_dart_cm=intake / 2.0)


def compute_pants_dart_plan(variation: str, scaled_half_width_cm: float,
                             measurements: Measurements) -> DartPlan:
    """ヒップ比・ウエスト比と、体型スケーリング後のウエスト半幅からパンツの
    ダーツ計画を求める。`compute_skirt_dart_plan`と同じ考え方で、対象
    variationの集合(PANTS_DART_ELIGIBLE_VARIATIONS)だけが異なる。
    """
    if variation not in PANTS_DART_ELIGIBLE_VARIATIONS or scaled_half_width_cm <= 0:
        return NO_DART

    hip_ratio = clamp_scale(measurements.hip / STANDARD_M.hip)
    waist_ratio = clamp_scale(measurements.waist / STANDARD_M.waist)
    if hip_ratio <= 0 or waist_ratio >= hip_ratio:
        return NO_DART

    target_half_width = scaled_half_width_cm * (waist_ratio / hip_ratio)
    intake = scaled_half_width_cm - target_half_width - PANTS_DART_EASE_CM
    intake = min(intake, PANTS_MAX_DART_INTAKE_PER_HALF_CM)
    if intake < PANTS_MIN_DART_INTAKE_CM:
        return NO_DART

    if intake <= PANTS_MAX_SINGLE_DART_INTAKE_CM:
        return DartPlan(darts_per_half=1, intake_per_dart_cm=intake)
    return DartPlan(darts_per_half=2, intake_per_dart_cm=intake / 2.0)


def _segment_start_positions(segments: list) -> list[tuple[float, float]]:
    """各セグメントの「実行前」の現在位置(cur)を並べたリストを返す。"""
    positions: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    for cmd, nums in segments:
        positions.append(cur)
        if cmd in ("M", "L"):
            cur = (nums[0], nums[1])
        elif cmd == "H":
            cur = (nums[0], cur[1])
        elif cmd == "V":
            cur = (cur[0], nums[0])
        elif cmd == "C":
            cur = (nums[4], nums[5])
        # Z: curは変えない(このプロジェクトのテンプレートはZの前に明示的な
        # 終点セグメントを必ず持つため、Zの暗黙closeには依存していない)。
    return positions


def _find_extreme_horizontal_segment_index(segments: list, pick_max: bool) -> int | None:
    """水平な直線(L)セグメントのうち、y座標が最大(pick_max=True)または
    最小(pick_max=False)のもののインデックスを探す。

    テンプレート生成方法(scripts/generate_templates.py)がどのセグメント
    順序を使っていても対応できるよう、インデックスを決め打ちせず幾何的に
    探す。該当が無ければNoneを返す。
    """
    positions = _segment_start_positions(segments)
    best_idx = None
    best_y = float("-inf") if pick_max else float("inf")
    for i, (cmd, nums) in enumerate(segments):
        if cmd != "L":
            continue
        start = positions[i]
        end = (nums[0], nums[1])
        if abs(start[1] - end[1]) >= 1e-6 or abs(end[0] - start[0]) <= 1e-6:
            continue
        is_better = (end[1] > best_y) if pick_max else (end[1] < best_y)
        if is_better:
            best_y = end[1]
            best_idx = i
    return best_idx


def _find_hem_segment_index(segments: list) -> int | None:
    """裾（y座標が最大の、水平な直線(L)セグメント）のインデックスを探す。"""
    return _find_extreme_horizontal_segment_index(segments, pick_max=True)


def _find_top_edge_segment_index(segments: list) -> int | None:
    """上端（y座標が最小の、水平な直線(L)セグメント）のインデックスを探す。

    スカートのウエストライン(裾の反対側)を、裾検出と同じ考え方で幾何的に
    探すために使う（`apply_skirt_waist_dart`参照）。
    """
    return _find_extreme_horizontal_segment_index(segments, pick_max=False)


def apply_waist_dart(part_type: str, segments: list,
                      measurements: Measurements,
                      hip_ease_cm: float | None = None,
                      dartless: bool = False) -> tuple[list, int]:
    """裾(ウエスト)ラインにウエストダーツを追加する。

    ダーツが不要、または安全に置けない形状の場合は、元のsegmentsをそのまま
    返す(追加したダーツ本数は0)。失敗した場合に例外を投げて型紙生成全体を
    止めるのではなく、線形スケーリングのみの以前の挙動に静かにフォール
    バックする方針（ダーツは「あれば良い」改善であり、それが原因で生成が
    失敗するのは本末転倒なため）。

    Returns:
        (new_segments, dart_count): dart_countは実際に追加したダーツの本数
        (両半身の合計)。0ならsegmentsは元のまま。
    """
    if part_type not in DART_ELIGIBLE_PART_TYPES:
        return segments, 0

    if part_type in WAIST_DART_ZIP_PANEL_PART_TYPES:
        return _apply_waist_dart_zip_panel(segments, measurements, hip_ease_cm,
                                            dartless=dartless)

    hem_idx = _find_hem_segment_index(segments)
    if hem_idx is None or hem_idx == 0:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。

    positions = _segment_start_positions(segments)
    hem_start = positions[hem_idx]
    hem_end = (segments[hem_idx][1][0], segments[hem_idx][1][1])
    underarm_y = positions[hem_idx - 1][1]

    hem_y = hem_start[1]
    center_x = (hem_start[0] + hem_end[0]) / 2.0
    half_width = abs(center_x - hem_start[0])
    if half_width < 1e-6:
        return segments, 0

    plan = compute_dart_plan(part_type, half_width, measurements, hip_ease_cm,
                              dartless=dartless)
    if plan.is_empty():
        return segments, 0

    # ダーツの先端は、裾から袖付け(underarm)までの余裕の半分までに抑える
    # （襟ぐり側にダーツの先端がめり込まないようにする安全マージン）。
    available = max(0.0, hem_y - underarm_y)
    apex_len = min(DEFAULT_APEX_LEN_CM, available * 0.5)
    if apex_len < 1.0:
        return segments, 0  # ダーツを安全に置けるだけの縦の余裕が無い

    apex_y = hem_y - apex_len

    def _half_dart_bases(sign: int) -> list[tuple[float, float]]:
        """sign=-1で左半身、+1で右半身の各ダーツの(左端, 右端)のリストを返す
        （中心前(center_x)に近い順）。"""
        anchor = center_x + sign * half_width * DART_OFFSET_RATIO
        offsets = [0.0] if plan.darts_per_half == 1 else [-DART_SPACING_CM / 2, DART_SPACING_CM / 2]
        half_intake = plan.intake_per_dart_cm / 2.0
        bases = []
        for off in offsets:
            dart_center = anchor + off
            bases.append((dart_center - half_intake, dart_center + half_intake))
        bases.sort(key=lambda lr: lr[0])
        return bases

    left_darts = _half_dart_bases(-1)
    right_darts = _half_dart_bases(+1)

    # 安全確認: どのダーツの端点も、中心前や脇線(裾の両端)に寄り過ぎていない
    # ことを確認する。ここで引っかかったら、無理な位置にダーツを置くより
    # ダーツ無し(線形スケーリングのみ)を優先する。
    #
    # 実際に見つかった不具合の修正: 以前は「裾セグメントは開始点のx座標が
    # 終了点より小さい(=左から右に描かれている)」という向きを暗黙に仮定
    # しており、`hem_start[0]`を裾の左端、`hem_end[0]`を裾の右端として
    # そのまま比較していた。現在同梱の全テンプレート(pattern_templates/
    # *bodice*.svg)はいずれも左→右に裾を描いているため今は問題にならないが、
    # 実際に裾を右→左に描く合成テンプレートを使ってテストしたところ、
    # 幾何的には全く同じ形状であるにもかかわらず、この向きの仮定が反転して
    # 「ダーツの右端が(実際には裾の左端でしかない)`hem_end[0]`を超えている」
    # という比較が常に真になり、本来追加されるべきウエストダーツが無条件に
    # 無効化される(=線形スケーリングのみにフォールバックしてしまう)ことを
    # 確認した。`hem_start[0]`/`hem_end[0]`のどちらが小さいかに依存しない
    # よう、min/maxで裾の左端・右端を明示的に求めてから比較するように修正した。
    hem_left_x = min(hem_start[0], hem_end[0])
    hem_right_x = max(hem_start[0], hem_end[0])
    all_bases = left_darts + right_darts
    for left, right in all_bases:
        if left < hem_left_x + MIN_CLEARANCE_CM or right > hem_right_x - MIN_CLEARANCE_CM:
            return segments, 0
    if left_darts and left_darts[-1][1] > center_x - MIN_CLEARANCE_CM:
        return segments, 0
    if right_darts and right_darts[0][0] < center_x + MIN_CLEARANCE_CM:
        return segments, 0

    def _dart_points(left: float, right: float) -> list[tuple[float, float]]:
        return [(left, hem_y), ((left + right) / 2.0, apex_y), (right, hem_y)]

    new_pts: list[tuple[float, float]] = []
    for left, right in left_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append((center_x, hem_y))
    for left, right in right_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append(hem_end)

    hem_replacement = [("L", [x, y]) for x, y in new_pts]
    new_segments = segments[:hem_idx] + hem_replacement + segments[hem_idx + 1:]
    dart_count = len(left_darts) + len(right_darts)
    return new_segments, dart_count


def _materialize_closing_edge(segments: list) -> list:
    """末尾のZ(始点への暗黙のクローズ)を、始点へ戻る明示的なLに置き換える。

    front_bodice_zip_panelの輪郭はshapelyの半平面交差(`_front_zip_panel_d`)で
    組み立てられており、結果ポリゴンの最初の頂点(=Mの位置)がどの辺の上に
    来るかは決め打ちできない。実際に同梱の全variationを調べたところ、いずれも
    「外側の脇線が裾に接する角」がMの位置になっており、その結果、裾のうち
    最も長い区間がZによる暗黙のクローズ辺として表現されていた。
    `cmd == "L"`のみを見る幾何探索(`_find_hem_segment_index`等)ではこの辺を
    検出できず、実際、裾のすぐ隣にある見返し用の短い橋渡し辺(4cm)の方を
    誤って「裾」と判定してしまう(round11の実装中に実測で確認)。
    ここで事前に正規化しておくことで、以降の処理は明示的なLセグメントだけを
    見れば済むようになる。
    """
    if not segments or segments[-1][0] != "Z":
        return segments
    start = (segments[0][1][0], segments[0][1][1])
    last_point = (segments[-2][1][0], segments[-2][1][1]) if len(segments) >= 2 else start
    if last_point == start:
        return segments[:-1]  # 既に明示的に閉じている(Zは冗長なだけ)。
    return segments[:-1] + [("L", [start[0], start[1]])]


def _apply_waist_dart_zip_panel(segments: list, measurements: Measurements,
                                 hip_ease_cm: float | None = None,
                                 dartless: bool = False) -> tuple[list, int]:
    """front_bodice_zip_panel(前開き用の片側パネル)にウエストダーツを追加する
    (round11で追加)。

    `apply_waist_dart`本体は「裾の中点=中心前」という左右対称パーツ向けの
    前提に依存しており、片側パネル+見返しを持つ非対称なzip_panelには
    そのまま使えない(モジュールdocstringの追記参照)。代わりに、脇ダーツで
    実績のある`_bust_dart_zip_panel_side_index`と同じ「輪郭上のほぼ垂直な
    2本の直線(外側の脇線・中心前寄りの見返し/裁ち割り線)を幾何的に見分ける」
    手法を流用する。

    裾の位置は`_find_hem_segment_index`で探し直すのではなく、見分けた2本の
    縦線それぞれの「裾側の端点」から直接求める。前者の方式は、裾のすぐ隣に
    ある見返し用の短い橋渡し辺を本物の裾と取り違える(実測で確認済み。
    `_materialize_closing_edge`のdocstring参照)ため、より確実な情報源である
    縦線の端点から求める設計にした。

    ダーツは外側の脇線側にのみ1組(通常1本、摘み量が大きければ2本)追加する。
    左右対称なfront_bodiceで2組追加するのとは異なり、パネル1枚は身頃の
    片側だけを表すため(前身頃全体では左右パネル2枚分になる)。
    """
    segments = _materialize_closing_edge(segments)

    side_candidates = _find_side_seam_segment_indices(segments)
    side_idx = _bust_dart_zip_panel_side_index(segments)
    if side_idx is None or len(side_candidates) != 2:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。
    other_idx = side_candidates[0] if side_candidates[1] == side_idx else side_candidates[1]

    positions = _segment_start_positions(segments)

    def _endpoints(idx: int) -> tuple[tuple[float, float], tuple[float, float]]:
        return positions[idx], (segments[idx][1][0], segments[idx][1][1])

    side_a, side_b = _endpoints(side_idx)
    side_hem_point = side_a if side_a[1] > side_b[1] else side_b
    underarm_y = min(side_a[1], side_b[1])

    other_a, other_b = _endpoints(other_idx)
    cf_hem_point = other_a if other_a[1] > other_b[1] else other_b

    hem_y = side_hem_point[1]
    side_x = side_hem_point[0]
    # 中心前寄りの縁(見返し/裁ち割り線)のx座標を、中心前(CF)の代用として使う
    # (apply_bust_dartのcf_xと同じ近似。実際の中心前は見返し幅の分だけ
    # 内側にあるが、ダーツの位置決めと安全マージンの判定にはこの粒度で足りる)。
    cf_x = cf_hem_point[0]
    half_width = abs(side_x - cf_x)
    if half_width < 1e-6:
        return segments, 0

    plan = compute_dart_plan("front_bodice_zip_panel", half_width, measurements,
                              hip_ease_cm, dartless=dartless)
    if plan.is_empty():
        return segments, 0

    available = max(0.0, hem_y - underarm_y)
    apex_len = min(DEFAULT_APEX_LEN_CM, available * 0.5)
    if apex_len < 1.0:
        return segments, 0  # ダーツを安全に置けるだけの縦の余裕が無い
    apex_y = hem_y - apex_len

    sign = 1.0 if side_x > cf_x else -1.0
    anchor = cf_x + sign * half_width * DART_OFFSET_RATIO
    offsets = [0.0] if plan.darts_per_half == 1 else [-DART_SPACING_CM / 2, DART_SPACING_CM / 2]
    half_intake = plan.intake_per_dart_cm / 2.0
    bases = [(anchor + off - half_intake, anchor + off + half_intake) for off in offsets]

    hem_left_x = min(cf_x, side_x)
    hem_right_x = max(cf_x, side_x)
    for left, right in bases:
        if left < hem_left_x + MIN_CLEARANCE_CM or right > hem_right_x - MIN_CLEARANCE_CM:
            return segments, 0  # 無理な位置になる。安全側に倒してダーツを諦める。

    # 裾は明示的なLセグメント1本とは限らない(見返し用の短い橋渡し辺と、
    # 本来の裾の2本に分かれていることがある)。y=hem_y上のLセグメントを全て
    # 集め、その連続区間をまとめて差し替える。
    hem_indices = [
        i for i, (cmd, nums) in enumerate(segments)
        if cmd == "L" and abs(positions[i][1] - hem_y) < 1e-6 and abs(nums[1] - hem_y) < 1e-6
    ]
    if not hem_indices:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。
    first_idx, last_idx = min(hem_indices), max(hem_indices)
    if list(range(first_idx, last_idx + 1)) != sorted(hem_indices):
        return segments, 0  # 裾のセグメントが飛び地。想定外なので安全側に倒す。

    hem_start = positions[first_idx]
    hem_end = (segments[last_idx][1][0], segments[last_idx][1][1])

    # 元の裾の描画方向(hem_start→hem_end)を保つ(apply_waist_dart本体と同じ、
    # 向きに依存しない設計)。
    descending = hem_start[0] > hem_end[0]
    ordered = sorted(bases, key=lambda lr: lr[0], reverse=descending)

    new_pts: list[tuple[float, float]] = []
    for left, right in ordered:
        tip = ((left + right) / 2.0, apex_y)
        if descending:
            new_pts.extend([(right, hem_y), tip, (left, hem_y)])
        else:
            new_pts.extend([(left, hem_y), tip, (right, hem_y)])
    new_pts.append(hem_end)

    replacement = [("L", [x, y]) for x, y in new_pts]
    new_segments = segments[:first_idx] + replacement + segments[last_idx + 1:]
    return new_segments, len(ordered)


def compute_bust_dart_intake_cm(measurements: Measurements) -> float:
    """バストの標準サイズからの超過分に基づく、脇ダーツ1本あたりの摘み量(cm)。

    ウエストダーツ(compute_dart_plan)がバスト比とウエスト比の"差"を見るのに
    対し、こちらはバストの絶対値そのものを見る。バストが標準以下なら0
    （摘む必要なし）。
    """
    excess = max(0.0, measurements.bust - STANDARD_M.bust)
    intake = min(excess * BUST_DART_COEFFICIENT, MAX_BUST_DART_INTAKE_CM)
    return intake if intake >= MIN_BUST_DART_INTAKE_CM else 0.0


def bust_dart_angle_deg(bust_cm: float, block: Block = ADULT_FEMALE) -> float:
    """胸ぐせダーツの開き角(度)。新文化式の (B/4 − 2.5)。

    block: round42。子ども原型では一律8°(`engine/blocks.py`)。
        6歳児(バスト60)にこの式を当てると12.5°になり、子ども原型の8°より
        4.5°ぶん余計な立体が入っていた。
    """
    return max(0.0, block.bust_dart_angle.value(bust_cm))


def total_bust_dart_intake_cm(bust_cm: float, bp_to_mouth_cm: float,
                               block: Block = ADULT_FEMALE) -> float:
    """胸ぐせダーツの摘み量の合計(cm)。

    bp_to_mouth_cm: BPからダーツの口の中心までの距離(cm)。

    角を摘み量へ直す式 2 L sin(角/2) をそのまま使う。角そのものは
    `bust_dart_angle_deg`(新文化式)。
    """
    if bp_to_mouth_cm <= 0:
        return 0.0
    half = radians(bust_dart_angle_deg(bust_cm, block)) / 2.0
    intake = 2.0 * bp_to_mouth_cm * sin(half)
    return intake if intake >= MIN_BUST_DART_INTAKE_CM else 0.0


def split_bust_dart_cm(total_intake_cm: float) -> tuple[list[float], float]:
    """胸ぐせダーツの合計を、脇線に並べる**複数本**へ分ける(round29)。

    Returns:
        (1本あたりの摘み量のリスト, 収まりきらなかった量cm)。

    1本のダーツで摘める量には実務上の上限がある
    (`MAX_SIDE_BUST_DART_INTAKE_CM`)。胸が大きいほど胸ぐせダーツは大きく
    なり、1本にまとめると口が縦に長くなりすぎて縫いにくく、胸の下に
    「角」が出る。実際の型紙でも、大きい胸ぐせダーツは**分散**して2本に
    することがある。ここでも上限を超えたら均等に2本へ分ける
    (「片方だけ深い2本」より「同じ深さの2本」の方が、縫い縮めたときの
    見た目が素直になる)。

    2本でも収まらない分は諦めて開示する(`engine/pipeline.py`)。無理に
    3本4本と増やすと、脇線がダーツの口だらけになって縫えなくなる。
    """
    if total_intake_cm <= 0:
        return [], 0.0
    if total_intake_cm <= MAX_SIDE_BUST_DART_INTAKE_CM:
        return [total_intake_cm], 0.0
    capacity = MAX_SIDE_BUST_DART_INTAKE_CM * MAX_SIDE_BUST_DART_COUNT
    fitted = min(total_intake_cm, capacity)
    each = fitted / MAX_SIDE_BUST_DART_COUNT
    return [each] * MAX_SIDE_BUST_DART_COUNT, max(0.0, total_intake_cm - capacity)


def _find_side_seam_segment_indices(segments: list) -> list[int]:
    """脇線（袖付け〜裾の間にある、ほぼ垂直な直線(L)セグメント）を探す。

    `_find_hem_segment_index`と同じ考え方で、セグメントの並び順や描画方向
    (上→下/下→上)に依存せず、幾何(「ほぼ垂直かつ十分に長い直線」)から
    動的に探す。前身頃には左右2本の脇線があるはずなので、2本以外が
    見つかった場合は呼び出し側で安全側に倒す。

    【round29で直した不具合】round28まで「垂直」を `dx < 1e-6`——つまり
    **厳密な垂直**——で判定していた。ところがround26で、裾をヒップに
    合わせるために脇線を開かせるようになっている(`apply_hip_widening`)。
    開かせた瞬間に脇線は厳密な垂直でなくなるので、この関数は脇線を
    1本も見つけられなくなり、**胸ぐせダーツが黙って消えていた**。実測
    (前身頃・ダーツの本数):

        B/W/H          裾の開き    round28   round29
        83/66/91        あり        0本      1本
        110/85/112      なし        2本      2本
        120/110/130     あり        0本      2本

    「ヒップがバストより大きい体型ほど、胸のダーツが消える」という、
    理由の説明できない挙動になっていた。判定を
    `engine/compatibility.py`の`_is_side_seam_edge`と同じ「ほぼ垂直」
    (SIDE_SEAM_MAX_DX_RATIO)に揃えて直した。
    """
    from .compatibility import _x_range_at_y

    positions = _segment_start_positions(segments)
    outline = _closed_points_from_segments(segments)
    found: list[int] = []
    for i, (cmd, nums) in enumerate(segments):
        if cmd != "L":
            continue
        start = positions[i]
        end = (nums[0], nums[1])
        dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
        if dy <= MIN_SIDE_SEAM_LENGTH_CM or dx > SIDE_SEAM_MAX_DX_RATIO * dy:
            continue
        # 「ほぼ垂直で十分に長い」だけでは、**ウエストダーツの脚**も条件を
        # 満たす(裾から12cm上の先端へ向かう、ほぼ縦の辺)。実測では脇線の
        # 候補が2本のはずが6〜10本になり、ダーツが黙って出なくなった。
        # 脇線は必ずパーツの外周にあるので、その高さでの輪郭の外側と
        # 一致することも確かめる(engine/compatibility.pyの
        # `_is_side_seam_edge`と同じ考え方)。
        span = _x_range_at_y(outline, (start[1] + end[1]) / 2.0)
        if span is None:
            continue
        mid_x = (start[0] + end[0]) / 2.0
        if min(abs(mid_x - span[0]), abs(mid_x - span[1])) > SIDE_SEAM_EDGE_TOL_CM:
            continue
        found.append(i)
    return found


def _realised_mouth_cm(span: float, mouth_center: float, seam_x, tip_for,
                        y_top: float, y_bottom: float) -> float | None:
    """脇線に幅`span`で開けた口が、脚を揃えたあと実際に何cmになるか。

    `_equalise_legs`は口を「先端から同じ距離」へ寄せるので、出来上がりの
    口は元より少し狭くなる。その狭くなった後の値を返す。
    """
    y_a = mouth_center - span / 2.0
    y_b = mouth_center + span / 2.0
    if not (y_top <= y_a and y_b <= y_bottom):
        return None
    mouth_a = (seam_x(y_a), y_a)
    mouth_b = (seam_x(y_b), y_b)
    tip = tip_for((y_a + y_b) / 2.0)
    trued = _equalise_legs(mouth_a, tip, mouth_b)
    if trued is None:
        return hypot(mouth_b[0] - mouth_a[0], mouth_b[1] - mouth_a[1])
    return hypot(trued[1][0] - trued[0][0], trued[1][1] - trued[0][1])


def _bust_dart_notch(start: tuple[float, float], end: tuple[float, float],
                      cf_x: float, intake: float,
                      bust_line_y: float | None = None,
                      bp_from_cf_cm: float | None = None,
                      intakes_cm: list[float] | None = None
                      ) -> list[tuple[str, list[float]]] | None:
    """脇線の1区間(start→end)に、中心前基準位置cf_xへ向けて収束する
    バストダーツのV字ノッチを1本分作る。

    front_bodice(左右対称、脇線2本)とfront_bodice_zip_panel(非対称、
    脇線1本のみ)の両方から呼ばれる共通のダーツ幾何計算。cf_xには、
    front_bodiceでは左右2本の脇線の中点(=中心前)を、front_bodice_zip_panel
    では実際の見返し/中心前の縁のx座標を渡す。

    Returns:
        ダーツの口(2点)・先端(1点)・元の終点(end)の計4点からなるL
        セグメント列。安全に配置できない場合(縦方向の余裕が足りない等)は
        None。

    【round6で修正した不具合】この関数の前身にあたる旧`_dart_replacement`
    は、返り値の末尾に`end`を含めておらず、脇線の「ダーツの口から元の
    終点まで」の区間が黙って消失し、後続のセグメント(袖ぐりカーブ等)も
    歪んだ位置から描画されてしまう不具合があった(詳細はモジュール
    docstring参照)。この関数は必ず`end`を末尾に含める。
    """
    x0 = start[0]
    # round29: 脇線は厳密な垂直ではなくなった(裾をヒップに合わせて開かせる
    # ため)。口の2点は脇線の**上**に乗せる必要があるので、その高さでの
    # 脇線のxを線形補間で求める。垂直なら従来とまったく同じ値になる。
    _dy_seam = end[1] - start[1]
    _slope = (end[0] - start[0]) / _dy_seam if abs(_dy_seam) > 1e-9 else 0.0

    def seam_x(y: float) -> float:
        return start[0] + _slope * (y - start[1])

    y_top = min(start[1], end[1])
    y_bottom = max(start[1], end[1])
    seam_len = y_bottom - y_top
    # 口の幅は摘み量そのもの(round14。それ以前は4.0cm固定だった)。
    intakes = [i for i in (intakes_cm if intakes_cm is not None else [intake]) if i > 0]
    if not intakes:
        return None
    mouths = [max(i, BUST_DART_MIN_MOUTH_CM) for i in intakes]
    gaps = BUST_DART_GAP_CM * (len(mouths) - 1)
    total_mouth = sum(mouths) + gaps
    if seam_len < 2 * MIN_CLEARANCE_CM + total_mouth:
        return None  # ダーツの口を安全に置けるだけの縦の余裕が無い

    sign = -1.0 if x0 < cf_x else 1.0
    if bust_line_y is not None and bp_from_cf_cm:
        # round28: 体の位置で決める。BPはバストラインの上にあり、口はそこから
        # 少し下げた高さに開ける。
        bp_x = cf_x + sign * bp_from_cf_cm
        # BPがこのパーツの脇線より外に出ることはない(前立て分割パーツのように
        # 幅の狭いパーツでは起こりうる)。外に出る場合は脇線の手前へ寄せる。
        if sign > 0:
            bp_x = min(bp_x, x0 - MIN_CLEARANCE_CM)
        else:
            bp_x = max(bp_x, x0 + MIN_CLEARANCE_CM)
        bp_y = bust_line_y
        block_center = bust_line_y + BUST_DART_MOUTH_DROP_CM + total_mouth / 2.0 \
            - mouths[0] / 2.0
    else:
        # 基準線が無い場合のフォールバック(round27までの近似)。
        half_width_side = abs(cf_x - x0)
        bp_x = cf_x + sign * half_width_side * BUST_APEX_OFFSET_RATIO
        bp_y = y_top + seam_len * BUST_APEX_HEIGHT_RATIO
        block_center = y_top + seam_len * BUST_DART_HEIGHT_RATIO
    def _tip_for(y_apex: float) -> tuple[float, float]:
        """口の中心の高さから、ダーツ先端の位置を決める。

        round71でループの中から切り出した。脚を揃えたあとの口の広さを
        測るために、同じ計算を繰り返し呼ぶ必要があるため。中身は
        round28からまったく変えていない。
        """
        mouth_x = seam_x(y_apex)
        reach = hypot(bp_x - mouth_x, bp_y - y_apex)
        if bust_line_y is not None and bp_from_cf_cm and reach > BUST_APEX_SETBACK_CM:
            reach_ratio = (reach - BUST_APEX_SETBACK_CM) / reach
        else:
            reach_ratio = BUST_APEX_REACH_MIN_RATIO + (
                BUST_APEX_REACH_MAX_RATIO - BUST_APEX_REACH_MIN_RATIO
            ) * min(1.0, intakes[0] / MAX_BUST_DART_INTAKE_CM)
        tip_x = mouth_x + reach_ratio * (bp_x - mouth_x)
        tip_y = y_apex + reach_ratio * (bp_y - y_apex)
        tip_y = min(max(tip_y, y_top + MIN_CLEARANCE_CM),
                    y_bottom - MIN_CLEARANCE_CM)
        return tip_x, tip_y

    # 複数本のときは、口をひとかたまりとして脇線に収める。
    half_block = total_mouth / 2.0
    block_center = min(max(block_center, y_top + MIN_CLEARANCE_CM + half_block),
                       y_bottom - MIN_CLEARANCE_CM - half_block)
    if bust_line_y is None or not bp_from_cf_cm:
        # 比率で近似する場合だけ、BPを脇線の範囲内へ収める。round28の
        # 「体の位置で決める」経路では、BPは**狙う方向を示す体の点**であって
        # 脇線上の点ではない。バストラインは脇線の上端(袖ぐりの底)と同じ
        # 高さなので、ここで収めると狙いが1cm下へずれる(実測: BPまでの
        # 距離が2.50cmのはずが2.93cmになっていた)。
        bp_y = min(max(bp_y, y_top + MIN_CLEARANCE_CM), y_bottom - MIN_CLEARANCE_CM)

    points: list[tuple[float, float]] = []
    cursor = block_center - half_block
    for mouth, intake_one in zip(mouths, intakes):
        # round71: 脚を揃えると口がわずかに狭くなるので、狭くなる分だけ
        # 先に広げておく。
        #
        # 【なぜ要るか】`_equalise_legs`は口を「先端から同じ距離」へ寄せる。
        # 長い方は縮み短い方は伸びるが、寄せる先が2本の平均なので、
        # 出来上がりの口(＝摘み量)は元より少し狭くなる。実測(B88):
        # 狙い5.50cm に対し 5.15cm ——0.35cm(6%)足りなかった。
        # 摘み量は新文化式の角度式から決めた値なので、減らしてはいけない。
        #
        # 口の広さと出来上がりの関係は単純な比ではないので、**作って測って
        # 直す**を3回繰り返す。3回で0.001cm以下まで寄る(実測)。
        span = mouth
        for _ in range(3):
            realised = _realised_mouth_cm(span, cursor + mouth / 2.0, seam_x,
                                          _tip_for, y_top, y_bottom)
            if realised is None or realised <= 1e-6:
                span = mouth
                break
            span *= mouth / realised
        mouth_center = cursor + mouth / 2.0
        y_mouth_a = mouth_center - span / 2.0
        y_mouth_b = mouth_center + span / 2.0
        y_apex = (y_mouth_a + y_mouth_b) / 2.0
        # ダーツの先端は、脇線の口の中心(x0, y_apex)からBPへ向かう直線上に置く。
        # round28からは、BPの手前 BUST_APEX_SETBACK_CM で止める(実務の定石)。
        # 「摘み量が大きいほど深く刺す」という従来の比率は、BPの位置そのものが
        # 近似だった時代の当てずっぽうなので、体の位置が分かる場合は使わない。
        tip_x, tip_y = _tip_for(y_apex)
        mouth_a = (seam_x(y_mouth_a), y_mouth_a)
        mouth_b = (seam_x(y_mouth_b), y_mouth_b)
        tip_point = (tip_x, tip_y)
        # round71: 脚の長さを揃える(たたみ出し)。揃っていないと、ダーツは
        # 平らにたたまれない——実測で脚が1.75〜2.22cm余っていた。
        # 上下の脇線の点は、脇線の上で口のすぐ外側に取る(ダーツが複数本
        # 並ぶ場合も、間の脇線の上で見ることになる)。
        above = (seam_x(y_mouth_a - MIN_CLEARANCE_CM), y_mouth_a - MIN_CLEARANCE_CM)
        below = (seam_x(y_mouth_b + MIN_CLEARANCE_CM), y_mouth_b + MIN_CLEARANCE_CM)
        trued = _equalise_legs(mouth_a, tip_point, mouth_b)
        if trued is not None:
            mouth_a, mouth_b = trued
        points.append(mouth_a)
        points.append(tip_point)
        points.append(mouth_b)
        cursor = y_mouth_b + BUST_DART_GAP_CM

    # 元の描画方向(start->end)を保つよう、y座標がstartに近い側から
    # 順に並べ、最後に必ず元の終点(end)へ戻す。
    if start[1] > end[1]:
        points.reverse()
    return [("L", [x, y]) for x, y in points] + [("L", [end[0], end[1]])]


def _mouth_span(rep: list, start: tuple[float, float] | None = None) -> tuple[float, float]:
    """`_bust_dart_notch`が返した点列から、(口の下端y, 脇線が縮む量) を返す。

    repは [口の一方, ダーツ先端, 口のもう一方] × 本数 + [元の終点] の順。
    先端のyは口の範囲外に出ることがある(先端はBPへ向かって斜めに伸びるため)
    ので、脇線上の点(3つおき)だけを見る。

    round29で複数本に対応した。

    【round71で直したこと】縮む量を「口の幅の合計」で出していた。
    口の2点が**脇線の上に並んでいる**ならそれで正しいが、たたみ出し
    (`_equalise_legs`)をすると口が脇線から外れるので、もう正しくない。
    そこで、縮む量を定義どおりに測る——

        縮む量 ＝ ダーツが無いときの脇線 −(実際に縫う区間の長さの合計)

    ダーツが無いときの脇線は start→末尾の点 の直線、実際に縫うのは
    start→口A・口B→次の口A・…・最後の口B→末尾 の各区間である。
    口が脇線の上に並んでいる場合、この式は「口の幅の合計」と**厳密に
    一致する**(全ての点が同一直線上に乗るため)。つまり、たたみ出しを
    しない形では round70 までとまったく同じ値になる。

    `start`を渡さない古い呼び方では、従来どおり口の幅の合計を返す。
    """
    seam_ys = [rep[i][1][1] for i in range(0, len(rep) - 1, 3)]
    seam_ys += [rep[i + 2][1][1] for i in range(0, len(rep) - 1, 3)]
    if start is None:
        total = 0.0
        for i in range(0, len(rep) - 1, 3):
            total += abs(rep[i + 2][1][1] - rep[i][1][1])
        return max(seam_ys), total

    end = (rep[-1][1][0], rep[-1][1][1])
    mouths = [((rep[i][1][0], rep[i][1][1]), (rep[i + 2][1][0], rep[i + 2][1][1]))
              for i in range(0, len(rep) - 1, 3)]
    sewn = 0.0
    cursor = start
    for mouth_a, mouth_b in mouths:
        sewn += hypot(mouth_a[0] - cursor[0], mouth_a[1] - cursor[1])
        cursor = mouth_b
    sewn += hypot(end[0] - cursor[0], end[1] - cursor[1])
    shrink = hypot(end[0] - start[0], end[1] - start[1]) - sewn
    return max(seam_ys), max(0.0, shrink)


def _shift_notch_end(rep: list, y_threshold: float, dy: float) -> list:
    """ダーツのV字(口2点と先端)はそのままに、末尾の「元の終点」だけを下げる。

    口と先端は`_shift_below`の対象外(ダーツの形が変わってしまう)だが、
    末尾の終点は元の輪郭上の点なので、周囲と同じだけ下げる必要がある。
    """
    x, y = rep[-1][1][0], rep[-1][1][1]
    if y <= y_threshold:
        return rep
    return rep[:-1] + [("L", [x, y + dy])]


def _shift_below(segments: list, y_threshold: float, dy: float) -> list:
    """y_thresholdより下(y座標が大きい)の点だけをdyだけ下げる(round14で追加)。

    脇ダーツを入れると、縫い合わせた後の脇線は「口の幅」ぶん短くなる。
    後ろ身頃には脇ダーツが無いため、そのままでは前後の脇線が合わず、
    実際に縫えない型紙になる(round13までの実測で片側4.0cmの差)。
    実務では、脇ダーツを脇線へ回した前身頃は脇線がその分だけ長くなり、
    ダーツを縫い閉じてはじめて後ろ身頃と釣り合う。ここではそれを
    「ダーツの口より下をまるごと下げる」という最小限の操作で再現する。

    ダーツより下をまとめて下げるので、裾は水平のまま平行移動し、
    ウエストダーツ(先端・口とも裾より上にあるが、`apply_waist_dart`が
    先に適用済み)も形を保ったまま一緒に下がる。`engine/compatibility.py`と
    `engine/darts.py`が依存している「脇線は縦」「裾は最もyが大きい水平線」
    という性質も崩れない。

    正直な限界: 本来は身頃を切り開いて回転させる(ダーツ回転)操作で、
    前中心の丈・袖ぐり・肩線の位置関係も少しずつ変わる。ここでは
    「前身頃はバストのぶんだけ丈が要る」という主要な効果だけを、
    平行移動で近似している。
    """
    out = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "H":
            out.append(("H", list(nums)))
        elif cmd == "V":
            out.append(("V", [nums[0] + dy if nums[0] > y_threshold else nums[0]]))
        else:
            vals = list(nums)
            for k in range(1, len(vals), 2):
                if vals[k] > y_threshold:
                    vals[k] += dy
            out.append((cmd, vals))
    return out


def _side_seam_top_index_by_side(segments: list) -> dict[str, int]:
    """左右それぞれの脇線のうち、**いちばん上の**セグメント番号を返す。

    round29で脇線をウエストの高さで絞るようにした
    (`engine/bodice_fit.py`の`apply_waist_nip`)。絞るにはウエストの高さに
    節点が要るので、それまで1本だった脇線がウエストで2本に割れる。
    「脇線候補がちょうど2本」を前提にしていた箇所は、候補が4本になった
    とたんに**黙ってダーツをあきらめる**(実測: 全ての体型で胸ぐせダーツが
    消えた)。胸ぐせダーツはバストラインのすぐ下に開くので、左右それぞれ
    いちばん上の区間を選べばよい。
    """
    candidates = _find_side_seam_segment_indices(segments)
    if not candidates:
        return {}
    positions = _segment_start_positions(segments)
    xs = [positions[i][0] for i in candidates] + \
         [segments[i][1][0] for i in candidates]
    center = (min(xs) + max(xs)) / 2.0
    best: dict[str, int] = {}
    for i in candidates:
        start = positions[i]
        end = (segments[i][1][0], segments[i][1][1])
        side = "left" if (start[0] + end[0]) / 2.0 < center else "right"
        y_top = min(start[1], end[1])
        current = best.get(side)
        if current is None:
            best[side] = i
            continue
        cur_top = min(positions[current][1], segments[current][1][1])
        if y_top < cur_top:
            best[side] = i
    return best


def _bust_dart_zip_panel_side_index(segments: list) -> int | None:
    """front_bodice_zip_panelの輪郭から、外側の脇線(ダーツを追加すべき縁)の
    セグメントインデックスを探す。

    `_find_side_seam_segment_indices`(「ほぼ垂直かつ十分に長い直線」)だけ
    では、このpart_typeの輪郭にちょうど2本存在する縦線――外側の脇線と、
    中心前の見返し/裁ち割り線――を区別できない。両者とも本数だけでは
    区別できないため、もう1つの幾何的性質「外側の脇線はネックラインから
    遠い(=区間のy_topが大きい)はず」で交差検証する: x座標が大きい方の
    候補が、本当にy_topも大きいことを確認できた場合のみ、それを外側の
    脇線と判定する。想定外の形状(候補が2本でない、または交差検証に
    失敗する)の場合はNoneを返し、呼び出し側で安全側に倒す。
    """
    by_side = _side_seam_top_index_by_side(segments)
    if len(by_side) != 2:
        return None
    candidates = sorted(by_side.values())

    positions = _segment_start_positions(segments)

    def _x(idx: int) -> float:
        return segments[idx][1][0]

    def _y_top(idx: int) -> float:
        start = positions[idx]
        end = (segments[idx][1][0], segments[idx][1][1])
        return min(start[1], end[1])

    a, b = candidates
    larger, smaller = (a, b) if _x(a) > _x(b) else (b, a)
    if _y_top(larger) <= _y_top(smaller):
        return None  # 交差検証に失敗。想定外の形状として安全側に倒す。
    return larger


def _bust_dart_cf_and_side_x(part_type: str, segments: list
                              ) -> tuple[float, float] | None:
    """胸ぐせダーツを置くパーツの (中心前のx, 脇線のx) を返す。

    `apply_bust_dart`が実際にダーツを入れるときと**同じ探し方**をする。
    摘み量を先に決める側(`bust_dart_split_for_part`)と、ダーツを入れる側で
    別々に脇線を探すと、片方だけ直したときに静かに食い違うため。
    """
    by_side = _side_seam_top_index_by_side(segments)
    if len(by_side) != 2:
        return None
    if part_type in BUST_DART_ZIP_PANEL_PART_TYPES:
        side_idx = _bust_dart_zip_panel_side_index(segments)
        if side_idx is None:
            return None
        others = [i for i in by_side.values() if i != side_idx]
        if len(others) != 1:
            return None
        return segments[others[0]][1][0], segments[side_idx][1][0]

    side_xs = [segments[i][1][0] for i in by_side.values()]
    return sum(side_xs) / 2.0, side_xs[0]


def bust_dart_split_for_part(part_type: str, segments: list,
                              measurements: Measurements,
                              bust_line_y: float,
                              block: Block = ADULT_FEMALE
                              ) -> tuple[list[float], float]:
    """このパーツの胸ぐせダーツの (1本あたりの摘み量, 収まらない量) を返す。

    新文化式の角度式で合計を求め、1本の上限で分散する(round29)。
    パーツの形から脇線を見つけられない場合は ([], 0)。
    """
    if part_type not in BUST_DART_ELIGIBLE_PART_TYPES:
        return [], 0.0
    geometry = _bust_dart_cf_and_side_x(part_type, segments)
    if geometry is None:
        return [], 0.0
    cf_x, side_x = geometry
    bp_from_cf = bust_point_from_cf_cm(measurements.bust,
                                       measurements.bust_point_spacing)
    # 口の中心はバストラインから BUST_DART_MOUTH_DROP_CM 下、脇線の上。
    horizontal = abs(cf_x - side_x) - bp_from_cf
    if horizontal <= 0:
        return [], 0.0
    bp_to_mouth = hypot(horizontal, BUST_DART_MOUTH_DROP_CM)
    return split_bust_dart_cm(
        total_bust_dart_intake_cm(measurements.bust, bp_to_mouth, block))


def apply_bust_dart(part_type: str, segments: list,
                     measurements: Measurements,
                     bust_line_y: float | None = None,
                     intakes_cm: list[float] | None = None,
                     block: Block = ADULT_FEMALE) -> tuple[list, int]:
    """前身頃の脇線に、胸ぐせダーツ(V字ノッチ)を追加する。

    front_bodice(左右対称、脇線2本)とfront_bodice_zip_panel(round6で対応、
    非対称、脇線1本のみ)の両方に対応する。ダーツが不要、または安全に
    置けない形状の場合は元のsegmentsをそのまま返す(dart_count=0)。
    front_bodiceでは前後の脇線の両方に対称に追加するか、まったく追加
    しないかの二択（片側だけ追加すると左右非対称になってしまうため）。
    front_bodice_zip_panelでは外側の脇線1本のみにダーツを追加する
    (中心前の見返し/裁ち割り線には手を加えない)。

    Returns:
        (new_segments, dart_count): dart_countは追加したダーツの本数
        (front_bodiceなら左右の脇線それぞれ1本ずつで2、
        front_bodice_zip_panelなら1)。

    bust_line_y:
        round28。変形後の座標でのバストライン(=袖ぐり底の線。テンプレートの
        `data-fit-y` の underarm)のy。渡されたときだけ、ダーツはBPという
        **体の位置**へ向く。渡されないときは round27 までの「脇線に沿った
        比率」へフォールバックする(ダーツの幾何だけを単体で確かめるテスト等)。

    intakes_cm:
        round29。1本あたりの摘み量を呼び出し側から指定する(本数=リストの
        長さ)。省略した場合は`bust_line_y`の有無に応じて、新文化式の
        角度式/round27までの旧係数のどちらかで自分で決める。
    """
    if part_type not in BUST_DART_ELIGIBLE_PART_TYPES:
        return segments, 0

    bp_from_cf = bust_point_from_cf_cm(measurements.bust,
                                       measurements.bust_point_spacing)
    if intakes_cm is not None:
        intakes = list(intakes_cm)
    elif bust_line_y is not None:
        intakes, _unfitted = bust_dart_split_for_part(
            part_type, segments, measurements, bust_line_y, block)
    else:
        one = compute_bust_dart_intake_cm(measurements)
        intakes = [one] if one > 0 else []
    intakes = [i for i in intakes if i > 0]
    if not intakes:
        return segments, 0

    positions = _segment_start_positions(segments)

    if part_type in BUST_DART_ZIP_PANEL_PART_TYPES:
        geometry = _bust_dart_cf_and_side_x(part_type, segments)
        side_idx = _bust_dart_zip_panel_side_index(segments)
        if side_idx is None or geometry is None:
            return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。
        cf_x = geometry[0]

        start = positions[side_idx]
        end = (segments[side_idx][1][0], segments[side_idx][1][1])
        rep = _bust_dart_notch(start, end, cf_x, 0.0,
                               bust_line_y=bust_line_y,
                               bp_from_cf_cm=bp_from_cf,
                               intakes_cm=intakes)
        if rep is None:
            return segments, 0

        # ダーツの口より下を摘み量ぶん下げ、縫い合わせた後の脇線長が
        # 後ろ身頃と一致するようにする(_mouth_span/_shift_below参照)。
        threshold, mouth = _mouth_span(rep, start)
        shifted = _shift_below(segments, threshold, mouth)
        rep = _shift_notch_end(rep, threshold, mouth)
        new_segments = shifted[:side_idx] + rep + shifted[side_idx + 1:]
        return new_segments, 1

    by_side = _side_seam_top_index_by_side(segments)
    if len(by_side) != 2:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。
    side_indices = sorted(by_side.values())

    # round71: 左右の脇線の**同じ高さ**のxから中心を取る。
    #
    # 【round70まで何が起きていたか】`segments[i][1][0]`——つまり各脇線
    # セグメントの**終点**のx——を平均していた。ところが輪郭は左の脇線を
    # 下へ、右の脇線を上へ辿るので、終点は左が「ウエスト側」・右が
    # 「脇の下側」である。脇線は裾へ向かって開く(`apply_hip_widening`)ので、
    # この2点は鏡像ではない。ずれた中心を基準にBPを置くと、**左右の
    # ダーツが違う方向を向く**。
    #
    # 実測(バスト84・ウエスト60・ヒップ150):
    #     左のダーツ先端 x= 7.39 / 右 x=30.09
    #     正しい鏡像なら 右は 38.61 ——8.5cmずれていた
    # 標準体型(B88)でも0.67cmずれていた。同じ体の左右で違う型紙になる。
    #
    # 同じ高さで測れば、脇線がどれだけ傾いていても中心は正しく出る。
    def _seam_x_at(idx: int, y: float) -> float:
        (x0, y0) = positions[idx]
        x1, y1 = segments[idx][1][0], segments[idx][1][1]
        if abs(y1 - y0) < 1e-9:
            return (x0 + x1) / 2.0
        return x0 + (x1 - x0) * (y - y0) / (y1 - y0)

    _levels = [positions[i][1] for i in side_indices] + \
              [segments[i][1][1] for i in side_indices]
    _level = bust_line_y if bust_line_y is not None else sum(_levels) / len(_levels)
    center_x = sum(_seam_x_at(i, _level) for i in side_indices) / len(side_indices)

    replacements: dict[int, list] = {}
    for idx in side_indices:
        start = positions[idx]
        end = (segments[idx][1][0], segments[idx][1][1])
        rep = _bust_dart_notch(start, end, center_x, 0.0,
                               bust_line_y=bust_line_y,
                               bp_from_cf_cm=bp_from_cf,
                               intakes_cm=intakes)
        if rep is None:
            return segments, 0  # 片側でも安全に置けなければ、両方諦める。
        replacements[idx] = rep

    # 左右のダーツは同じ高さ・同じ口の幅で作られるので、どちらか一方から
    # 口の下端と幅を取れば足りる。その下をまるごと摘み量ぶん下げて、
    # 縫い合わせた後の脇線長を後ろ身頃と一致させる(_shift_below参照)。
    threshold, mouth = _mouth_span(replacements[side_indices[0]],
                                   positions[side_indices[0]])
    new_segments = _shift_below(segments, threshold, mouth)
    # インデックスが後ろの方から差し替えることで、前方のインデックスが
    # ずれない(挿入によって後続セグメントの位置がシフトするのを避ける)。
    for idx in sorted(replacements, reverse=True):
        rep = _shift_notch_end(replacements[idx], threshold, mouth)
        new_segments = new_segments[:idx] + rep + new_segments[idx + 1:]

    return new_segments, len(replacements)


def _equalise_legs(mouth_a: tuple[float, float], tip: tuple[float, float],
                    mouth_b: tuple[float, float]
                    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """ダーツの2本の脚を、**平均の長さ**に揃える(round71)。

    【なぜ揃える必要があるか】ダーツは2本の脚を合わせて縫う。長さが
    違えば長い方が余り、たたんでも平らにならない——脇線に段差が残る。
    round70までの実測では、脚は 10.97〜22.36cm に対して差が 1.77〜3.04cm
    (9.8〜14.1%)あった。

    【なぜこの揃え方か】口を先端からの距離だけ動かす。向き(先端から口へ
    の方向)は変えないので、**ダーツの角度も先端の位置も変わらない**——
    動くのは「先端からどこで裁つか」だけである。両方の口を平均へ寄せる
    ので、動く量は差の半分ずつと、揃え方の中でいちばん小さい。

    洋裁の教科書どおりの「たたみ出し」(たたんだ状態で脇線をまっすぐ
    引き直す)も実装して試したが、**採らなかった**。あれは片方の口を
    脇線の外へ1.5cm以上出すので、脇の下の直下で身頃が広がる。実測で
    出来上がりのバスト回りが目標より0.28cm大きくなった(この揃え方なら
    0.22cm、バストラインちょうどでは0.00cm)。理由はREADMEに書いてある。
    """
    leg_a = hypot(mouth_a[0] - tip[0], mouth_a[1] - tip[1])
    leg_b = hypot(mouth_b[0] - tip[0], mouth_b[1] - tip[1])
    if leg_a < 1e-6 or leg_b < 1e-6:
        return None
    radius = (leg_a + leg_b) / 2.0
    # 動く量は差の半分ずつ。口が脇線から外れてよい上限と同じ値で見る
    # (見張る側`_is_dart_notch_at`が、その幅までしか見込んでいないため)。
    if abs(leg_a - leg_b) / 2.0 > BUST_DART_TRUING_MAX_OFFSET_CM:
        return None          # 想定外の差。触らない方が安全。
    return ((tip[0] + (mouth_a[0] - tip[0]) / leg_a * radius,
             tip[1] + (mouth_a[1] - tip[1]) / leg_a * radius),
            (tip[0] + (mouth_b[0] - tip[0]) / leg_b * radius,
             tip[1] + (mouth_b[1] - tip[1]) / leg_b * radius))


def retrue_bust_darts(segments: list) -> list:
    """輪郭の中の胸ぐせダーツを、もう一度たたみ出しして脚を揃える(round71)。

    【なぜ最後にもう一度やるか】`apply_bust_dart`はダーツを作った時点で
    脚をぴったり揃える(実測 13.66678 / 13.66678、差0.00000)。ところが
    そのあとに脇線を**ウエストで絞る**(`apply_waist_nip`)・**裾で開かせる**
    (`apply_hip_widening`)が掛かり、口の点だけが動く。実測すると、
    出来上がった型紙では 13.57526 / 13.43760 ——0.138cmずれていた。

    2cmが0.14cmになるだけでも縫えるようにはなるが、**揃うと言った以上は
    揃っている**のが正しい。ここで測り直して揃え直す。

    揃え方は作るときとまったく同じ`_equalise_legs`——2本の脚の平均を
    取って、両方をそこへ寄せる。残っているずれは0.14cmしかないので、
    動く量は0.07cmずつで、前後の脇線への影響は互いに打ち消し合う。

    ダーツの見つけ方は`engine/compatibility.py`の`_is_dart_notch_at`と
    同じ規則を使う(見張る側と探す側で規則が食い違わないように)。
    """
    from .compatibility import _closed_points, _is_dart_notch_at

    points: list[tuple[float, float]] = []
    index_of: dict[int, int] = {}
    for si, (cmd, nums) in enumerate(segments):
        if cmd in ("M", "L") and len(nums) >= 2:
            index_of[len(points)] = si
            points.append((nums[0], nums[1]))
    if len(points) < 5:
        return segments

    closed = _closed_points(points)
    out = list(segments)
    changed = False
    for i in range(len(closed) - 3):
        if i + 2 >= len(points):
            break
        if not _is_dart_notch_at(closed, i, 0.5):
            continue
        above = points[i - 1] if i >= 1 else None
        below = points[i + 3] if i + 3 < len(points) else None
        if above is None or below is None:
            continue
        # 仕上げの揃え直しが直すのは、**あとから掛かった変形のぶれ**だけ
        # (実測0.138cm)。それ以上動かしてはいけない——縮む量の見積もりは
        # 既に済んでいて、ここで大きく動かすと釣り合いが崩れる。
        # 実測(バスト130・ウエスト97・ヒップ143)で、作るときに揃えるのを
        # 諦めたダーツをここで揃えてしまい、前身頃の脇線が後ろより
        # **2.8cm長く**なって「そのままでは縫えません」と出た。
        if (abs(hypot(points[i][0] - points[i + 1][0],
                      points[i][1] - points[i + 1][1])
                - hypot(points[i + 2][0] - points[i + 1][0],
                        points[i + 2][1] - points[i + 1][1]))
                > RETRUE_MAX_DRIFT_CM):
            continue
        trued = _equalise_legs(points[i], points[i + 1], points[i + 2])
        if trued is None:
            continue
        for offset, point in ((0, trued[0]), (2, trued[1])):
            si = index_of.get(i + offset)
            if si is None:
                continue
            cmd, nums = out[si]
            out[si] = (cmd, [point[0], point[1]] + list(nums[2:]))
            changed = True
    return out if changed else segments

def apply_skirt_waist_dart(part_type: str, variation: str, segments: list,
                            measurements: Measurements) -> tuple[list, int]:
    """スカート(tight)のウエストライン(上端)にウエストダーツを追加する。

    `apply_waist_dart`の裾(下端・上向きダーツ)版を、上端・下向きダーツに
    置き換えた対称的な実装。ダーツが不要、または安全に置けない形状の場合は
    元のsegmentsをそのまま返す(dart_count=0)。

    Returns:
        (new_segments, dart_count): dart_countは実際に追加したダーツの本数
        (両半身の合計)。0ならsegmentsは元のまま。
    """
    if part_type != "skirt" or variation not in SKIRT_DART_ELIGIBLE_VARIATIONS:
        return segments, 0

    top_idx = _find_top_edge_segment_index(segments)
    if top_idx is None or top_idx == 0:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。

    positions = _segment_start_positions(segments)
    top_start = positions[top_idx]
    top_end = (segments[top_idx][1][0], segments[top_idx][1][1])
    # 上端セグメントの直後(裾側へ向かう最初のセグメント)の終点yを、
    # ダーツの先端が安全に置ける縦方向の余裕の算出に使う。
    next_idx = top_idx + 1
    if next_idx >= len(segments) or segments[next_idx][0] not in ("L", "C"):
        return segments, 0
    hem_side_y = segments[next_idx][1][-1]

    waist_y = top_start[1]
    center_x = (top_start[0] + top_end[0]) / 2.0
    half_width = abs(center_x - top_start[0])
    if half_width < 1e-6:
        return segments, 0

    plan = compute_skirt_dart_plan(variation, half_width, measurements)
    if plan.is_empty():
        return segments, 0

    # ダーツの先端は、ウエストラインから裾側へ向かう最初の頂点までの
    # 余裕の半分までに抑える（裾側の形状にめり込まないようにする安全マージン）。
    available = max(0.0, hem_side_y - waist_y)
    apex_len = min(SKIRT_DEFAULT_APEX_LEN_CM, available * 0.5)
    if apex_len < 1.0:
        return segments, 0  # ダーツを安全に置けるだけの縦の余裕が無い

    apex_y = waist_y + apex_len  # 身頃の裾ダーツとは逆に、下向きに伸ばす。

    def _half_dart_bases(sign: int) -> list[tuple[float, float]]:
        anchor = center_x + sign * half_width * SKIRT_DART_OFFSET_RATIO
        offsets = [0.0] if plan.darts_per_half == 1 else [-SKIRT_DART_SPACING_CM / 2, SKIRT_DART_SPACING_CM / 2]
        half_intake = plan.intake_per_dart_cm / 2.0
        bases = []
        for off in offsets:
            dart_center = anchor + off
            bases.append((dart_center - half_intake, dart_center + half_intake))
        bases.sort(key=lambda lr: lr[0])
        return bases

    left_darts = _half_dart_bases(-1)
    right_darts = _half_dart_bases(+1)

    # 安全確認: 身頃の裾ダーツと同様、min/maxで上端の左右端を明示的に
    # 求めてから比較する(描画方向に依存しないようにするための、既知の
    # 罠(round33で見つかった裾方向バグ)を最初から踏まない設計)。
    top_left_x = min(top_start[0], top_end[0])
    top_right_x = max(top_start[0], top_end[0])
    all_bases = left_darts + right_darts
    for left, right in all_bases:
        if left < top_left_x + MIN_CLEARANCE_CM or right > top_right_x - MIN_CLEARANCE_CM:
            return segments, 0
    if left_darts and left_darts[-1][1] > center_x - MIN_CLEARANCE_CM:
        return segments, 0
    if right_darts and right_darts[0][0] < center_x + MIN_CLEARANCE_CM:
        return segments, 0

    def _dart_points(left: float, right: float) -> list[tuple[float, float]]:
        return [(left, waist_y), ((left + right) / 2.0, apex_y), (right, waist_y)]

    new_pts: list[tuple[float, float]] = []
    for left, right in left_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append((center_x, waist_y))
    for left, right in right_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append(top_end)

    top_replacement = [("L", [x, y]) for x, y in new_pts]
    new_segments = segments[:top_idx] + top_replacement + segments[top_idx + 1:]
    dart_count = len(left_darts) + len(right_darts)
    return new_segments, dart_count


def apply_pants_waist_dart(part_type: str, variation: str, segments: list,
                            measurements: Measurements) -> tuple[list, int]:
    """パンツのウエストライン(上端)にウエストダーツを追加する。

    `apply_skirt_waist_dart`と同一の設計・同一の安全確認ロジックを、
    対象variation(全pantsバリエーション)とパンツ用の定数に置き換えたもの。
    ダーツが不要、または安全に置けない形状の場合は元のsegmentsをそのまま
    返す(dart_count=0)。

    Returns:
        (new_segments, dart_count): dart_countは実際に追加したダーツの本数
        (両半身の合計)。0ならsegmentsは元のまま。
    """
    if part_type not in PANTS_DART_ELIGIBLE_PART_TYPES or variation not in PANTS_DART_ELIGIBLE_VARIATIONS:
        return segments, 0

    top_idx = _find_top_edge_segment_index(segments)
    if top_idx is None or top_idx == 0:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。

    positions = _segment_start_positions(segments)
    top_start = positions[top_idx]
    top_end = (segments[top_idx][1][0], segments[top_idx][1][1])
    next_idx = top_idx + 1
    if next_idx >= len(segments) or segments[next_idx][0] not in ("L", "C"):
        return segments, 0
    hem_side_y = segments[next_idx][1][-1]

    waist_y = top_start[1]
    center_x = (top_start[0] + top_end[0]) / 2.0
    half_width = abs(center_x - top_start[0])
    if half_width < 1e-6:
        return segments, 0

    plan = compute_pants_dart_plan(variation, half_width, measurements)
    if plan.is_empty():
        return segments, 0

    # ダーツの先端は、ウエストラインから股上カーブが始まるまでの余裕の
    # 半分までに抑える（股上カーブの形状にめり込まないようにする安全マージン）。
    available = max(0.0, hem_side_y - waist_y)
    apex_len = min(PANTS_DEFAULT_APEX_LEN_CM, available * 0.5)
    if apex_len < 1.0:
        return segments, 0  # ダーツを安全に置けるだけの縦の余裕が無い

    apex_y = waist_y + apex_len  # スカートと同様、下向きに伸ばす。

    def _half_dart_bases(sign: int) -> list[tuple[float, float]]:
        anchor = center_x + sign * half_width * PANTS_DART_OFFSET_RATIO
        offsets = [0.0] if plan.darts_per_half == 1 else [-PANTS_DART_SPACING_CM / 2, PANTS_DART_SPACING_CM / 2]
        half_intake = plan.intake_per_dart_cm / 2.0
        bases = []
        for off in offsets:
            dart_center = anchor + off
            bases.append((dart_center - half_intake, dart_center + half_intake))
        bases.sort(key=lambda lr: lr[0])
        return bases

    left_darts = _half_dart_bases(-1)
    right_darts = _half_dart_bases(+1)

    top_left_x = min(top_start[0], top_end[0])
    top_right_x = max(top_start[0], top_end[0])
    all_bases = left_darts + right_darts
    for left, right in all_bases:
        if left < top_left_x + MIN_CLEARANCE_CM or right > top_right_x - MIN_CLEARANCE_CM:
            return segments, 0
    if left_darts and left_darts[-1][1] > center_x - MIN_CLEARANCE_CM:
        return segments, 0
    if right_darts and right_darts[0][0] < center_x + MIN_CLEARANCE_CM:
        return segments, 0

    def _dart_points(left: float, right: float) -> list[tuple[float, float]]:
        return [(left, waist_y), ((left + right) / 2.0, apex_y), (right, waist_y)]

    new_pts: list[tuple[float, float]] = []
    for left, right in left_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append((center_x, waist_y))
    for left, right in right_darts:
        new_pts.extend(_dart_points(left, right))
    new_pts.append(top_end)

    top_replacement = [("L", [x, y]) for x, y in new_pts]
    new_segments = segments[:top_idx] + top_replacement + segments[top_idx + 1:]
    dart_count = len(left_darts) + len(right_darts)
    return new_segments, dart_count


def waist_dart_hip_limited(part_type: str, segments: list,
                            measurements: Measurements,
                            hip_ease_cm: float) -> bool:
    """ウエストダーツの摘み量を、ヒップを通すために減らしたかどうか(round26)。

    `apply_waist_dart`と同じ手順で裾の半幅を求め、同じ`compute_dart_plan`に
    問い合わせるだけの関数(判定のロジックを二重に持たない)。呼び出し側は
    これを使って「ウエストは絞りきれていない」ことを利用者へ開示する。
    """
    if part_type not in DART_ELIGIBLE_PART_TYPES:
        return False
    hem_idx = _find_hem_segment_index(segments)
    if hem_idx is None or hem_idx == 0:
        return False
    positions = _segment_start_positions(segments)
    hem_start = positions[hem_idx]
    hem_end = (segments[hem_idx][1][0], segments[hem_idx][1][1])
    half_width = abs((hem_start[0] + hem_end[0]) / 2.0 - hem_start[0])
    if half_width < 1e-6:
        return False
    return compute_dart_plan(part_type, half_width, measurements,
                              hip_ease_cm).limited_by_hip


# --- ウエストの位置で絞るダイヤモンドダーツ(round27で追加) -----------------
#
# 【なぜ必要になったか】身頃の裾は**ヒップの高さ**にある(丈58cmは首の
# 付け根からヒップまで)。round26でそこを「ヒップが通る幅」に直した結果、
# 裾のダーツはほとんど摘めなくなり、**ウエストがまったく絞られない**
# 寸胴な型紙になった。round26のREADMEにも「ウエストの位置では絞れない」と
# 限界として書いている。
#
# ウエストで絞るには、ウエストの線を中心に**両端が尖ったダーツ**を置く。
# 上下とも尖っているので輪郭を切り欠かず、裾の幅もバストの幅も変えずに、
# ウエストの周だけを縮められる。洋裁ではダイヤモンドダーツ/フィッシュ
# アイダーツと呼ばれる、まさにこの用途の定石である。
#
# round27でパーツ内部の縫い線を出力できるようにした(engine/seam.pyの
# `FinalizedPart.internal_lines`)ので、ようやく実装できるようになった。

#: ダイヤモンドダーツが、ウエストの線から上下へ伸びる長さ(cm)。
#: 上はバストの丸みへ、下はヒップの丸みへ向かって消える。実際の型紙でも
#: この程度(上下それぞれ10〜14cm)に取る。
DIAMOND_DART_HALF_LENGTH_CM = 12.0
#: ダイヤモンドダーツ1本あたりの摘み量の上限(cm)。これを超える場合は
#: 2本に分ける(1本で摘みすぎると、縫い縮めた布が波打つ)。
#:
#: 【round29で3.0→4.0へ】新文化式のウエストダーツ配分表では、いちばん
#: 大きいダーツ(後ろのd)が総ダーツ量の35%を占める。総ダーツ量は
#: (B/2+6)−(W/2+3) なので、例えば83/50の体型では片側19.5cm、そのうち
#: dだけで6.8cmになる。round28までの3.0cmは、この配分表を見ずに置いた
#: 数字で、実際に「絞りきれない」と開示され続ける主因だった。
#: とはいえ1本で6.8cmは布が波打つので、本数を増やして分ける方を選ぶ。
#: 4.0cmは、実物の型紙で見かける深いウエストダーツの上限にあたる。
MAX_SINGLE_DIAMOND_INTAKE_CM = 4.0
#: 片側に並べられるダイヤモンドダーツの本数の上限。
#: 新文化式は片側(前中心〜後ろ中心)に6本のダーツを置くが、そのうち
#: 前身頃に来るのは a・b の2本、後ろ身頃に来るのは d・e・f の3本
#: (fは後ろ中心。ここでは後ろ中心が「わ」なので置けず、実質2本)。
MAX_DIAMOND_DART_COUNT_PER_HALF = 3
#: 片側あたりの摘み量の上限(cm)。ここを超える分は摘まずに残す
#: (残った分は「絞りきれていない」として利用者へ開示する)。
MAX_DIAMOND_INTAKE_PER_HALF_CM = (MAX_SINGLE_DIAMOND_INTAKE_CM
                                  * MAX_DIAMOND_DART_COUNT_PER_HALF)
#: これ未満の摘み量ならダーツを置かない(縫う意味が無い)。
MIN_DIAMOND_INTAKE_CM = 0.6

# --- ウエストダーツの前後配分(新文化式の配分表。round29) --------------------
#
# 新文化式は、総ダーツ量 (B/2+6) − (W/2+3) を、前中心から後ろ中心まで
# 6本のダーツ a〜f へ次の割合で配る:
#
#     a 14%  BPの下(前身頃)
#     b 15%  前の袖ぐり寄り(前身頃)
#     c 11%  脇線
#     d 35%  後ろのいちばん大きいダーツ(後ろ身頃)
#     e 18%  後ろ(後ろ身頃)
#     f  7%  後ろ中心(後ろ身頃)
#
# 【round28までの扱いと、それが間違っていた点】前身頃・後ろ身頃とも
# 「(ウエスト+ゆとり)/4」を目標半幅にしていた。つまり前後で**同じだけ**
# 絞る前提である。配分表はそうなっていない——後ろが前の倍近くを担う。
# 背中側はウエストのくびれが深く、前は胸ぐせダーツが別に丸みを担うので、
# 前を後ろと同じだけ絞ると背中が余り、前がつれる。
#
# 脇線(c)はこのエンジンでは絞っていない(脇線は袖の下から裾まで直線)。
# その分を前後へ按分するのではなく、前後の比だけを使う——つまり
# 前 = a+b、後ろ = d+e+f として正規化する。cを勝手に前後へ足すと、
# 「脇では絞っていないのに絞ったことにする」ことになるため。
WAIST_DART_SHARE_FRONT = 0.14 + 0.15
WAIST_DART_SHARE_SIDE_SEAM = 0.11
WAIST_DART_SHARE_BACK = 0.35 + 0.18 + 0.07


def waist_dart_share(part_type: str) -> float:
    """このパーツが担うウエストの絞り量の割合(前後の合計で1.0)。"""
    total = WAIST_DART_SHARE_FRONT + WAIST_DART_SHARE_BACK
    if part_type in BUST_DART_ELIGIBLE_PART_TYPES:
        return WAIST_DART_SHARE_FRONT / total
    return WAIST_DART_SHARE_BACK / total
#: round28: ウエストダーツの上の先端を、BP(バストポイント)より何cm下で
#: 止めるか。BPを越えると胸の頂点の真上で布が尖って浮く。実務では2〜3cm
#: 手前で止めるのが定石で、脇ダーツの BUST_APEX_SETBACK_CM と同じ考え方。
WAIST_DART_BELOW_BP_CM = 2.5


def compute_diamond_dart_plan(half_width_at_waist_cm: float, waist_cm: float,
                               waist_ease_cm: float,
                               share: float = 0.5,
                               dartless: bool = False) -> DartPlan:
    """ウエストのダイヤモンドダーツの本数と摘み量を求める(round27)。

    half_width_at_waist_cm: ウエストの高さでのパーツ半幅(cm)。

    share: round29。このパーツが担う絞り量の割合(`waist_dart_share`)。
        0.5なら前後で同じだけ絞る(round28までの挙動)。新文化式の配分表に
        従うと前0.326・後0.674になる。

    dartless: round30。伸びる生地はダーツを入れない(ニット原型の定石)。
        Trueならダーツ無しを返す。絞りは脇線が担う
        (`engine/scaling.py`の`_nip_waist`)。

    余っている量(パーツ半幅 − 目標半幅)のうち、shareに応じた分だけを
    このパーツで摘む。目標半幅は「(ウエスト + ゆとり)/4」——前後の
    合計がウエスト+ゆとりになる位置——のまま変えない。
    """
    if half_width_at_waist_cm <= 0 or dartless:
        return NO_DART
    target = (waist_cm + waist_ease_cm) / 4.0
    # 余り全体を前後で分け合う。前後の合計は変わらないので、出来上がりの
    # ウエスト周は「前後で等分」だった頃と同じ値を狙える。
    surplus = (half_width_at_waist_cm - target) * 2.0 * share
    intake = min(surplus, MAX_DIAMOND_INTAKE_PER_HALF_CM)
    if intake < MIN_DIAMOND_INTAKE_CM:
        return NO_DART
    count = min(MAX_DIAMOND_DART_COUNT_PER_HALF,
                max(1, ceil(intake / MAX_SINGLE_DIAMOND_INTAKE_CM)))
    return DartPlan(darts_per_half=count, intake_per_dart_cm=intake / count)


def waist_diamond_dart_lines(segments: list, measurements: Measurements,
                              waist_y: float, waist_ease_cm: float,
                              apex_limit_y: float | None = None,
                              share: float = 0.5,
                              dartless: bool = False,
                              half_panel: tuple[float, float] | None = None
                              ) -> tuple[list[list[tuple[float, float]]], int]:
    """ウエストの線に置くダイヤモンドダーツの輪郭を返す(round27)。

    返り値は (閉じた点列のリスト, 本数)。輪郭(segments)は**変更しない**
    ——ダーツはパーツの内側にあり、裁断線にも縫い合わせ長さにも影響しない。

    安全に置けない場合(ウエストの高さが分からない、縦の余裕が足りない、
    中心前や脇線に寄りすぎる)は空リストを返す。無理な位置に置くより
    「ダーツ無し」を優先する方針は、裾のウエストダーツと同じ。

    apex_limit_y:
        round28。上の先端をこの高さより上へ伸ばさない。前身頃では
        「BPより WAIST_DART_BELOW_BP_CM 下」を渡す。ウエストダーツの
        先端がBPを越えると、胸の頂点の真上で布が尖って浮くため、実物の
        型紙でもBPの手前で止める。round27は上下とも一律12cm伸ばして
        いたので、バストが大きい体型ほど先端がBPを越えていた(実測:
        バスト120でBPがy=26.58、先端がy=26.00)。

    share:
        round29。このパーツが担う絞り量の割合(`waist_dart_share`)。

    half_panel:
        round67。**左右非対称な「半身ぶん」のパーツ**用に、
        (中心前のx, 脇線のx) を渡す。前開きファスナーのパネル
        (`front_bodice_zip_panel`)がこれにあたる。

        渡さない場合、この関数は「左右対称なパーツの真ん中が中心前」と
        みなし、輪郭の全幅の半分を`half_width`として使い、中心の左右へ
        ダーツを1組ずつ置く。前開きのパネルにその前提は無い——中心前は
        輪郭の**縁**にあり、しかもその外側へ見返し(折り返し代)が
        張り出している。

        round66までは前開きのパネルにもそのまま使っており、
        「半幅」として渡していたのは *パネルの全幅の半分*(実測14.45cm)
        だった。狙いの半幅((ウエスト+ゆとり)/4 = 17.5cm)より小さいので
        `compute_diamond_dart_plan`は毎回「摘む余りが無い」と判断し、
        **前開きの型紙には1本もウエストダーツが入っていなかった**
        (実測: 出来上がりのウエストが採寸+ゆとりより約11cm大きい)。

        渡された場合は、摘める幅を「中心前から脇線まで」とし
        (見返しは折り返すので入れない)、ダーツは1組だけ置く。
    """
    if waist_y is None:
        return [], 0
    points = _closed_points_from_segments(segments)
    if len(points) < 4:
        return [], 0

    span = _x_span_at_y(points, waist_y)
    if span is None:
        return [], 0
    left_x, right_x = span
    if half_panel is None:
        center_x = (left_x + right_x) / 2.0
        half_width = (right_x - left_x) / 2.0
        # 中心の左右へ1組ずつ。置ける範囲は輪郭そのもの。
        signs = (-1, +1)
        clear_lo, clear_hi = left_x, right_x
    else:
        # round67: 半身ぶんのパネル。中心前から脇線までが摘める幅で、
        # 見返し(中心前より外側)には置かない。
        #
        # 脇線側は**ウエストの高さでの輪郭の縁**を使う(基準点`side`は
        # 脇の下の高さでの値で、ウエストでは少し外へ開いている)。
        # 左右対称の枝が輪郭の幅から半幅を出しているのと、同じ測り方に
        # そろえるため。
        cf_x, side_anchor_x = half_panel
        toward_right = side_anchor_x > cf_x
        outer_x = right_x if toward_right else left_x
        half_width = abs(outer_x - cf_x)
        center_x = cf_x
        signs = (+1 if toward_right else -1,)
        clear_lo, clear_hi = ((cf_x, outer_x) if toward_right
                              else (outer_x, cf_x))

    plan = compute_diamond_dart_plan(half_width, measurements.waist, waist_ease_cm,
                                      share=share, dartless=dartless)
    if plan.is_empty():
        return [], 0

    # 上下の余裕を確認する。上は脇の下より下、下は裾より上に収める。
    ys = [p[1] for p in points]
    top_limit = min(ys)
    bottom_limit = max(ys)
    reach_up = min(DIAMOND_DART_HALF_LENGTH_CM, (waist_y - top_limit) * 0.5)
    reach_down = min(DIAMOND_DART_HALF_LENGTH_CM, (bottom_limit - waist_y) * 0.7)
    if apex_limit_y is not None:
        # round28: 上の先端をBPの手前で止める。下の先端は関係が無いので
        # 縮めない(上下で長さの違うダイヤになるが、実物のウエストダーツも
        # 上下で長さが違う)。
        reach_up = min(reach_up, max(0.0, waist_y - apex_limit_y))
    if min(reach_up, reach_down) < 3.0:
        return [], 0

    # 本数に応じて、片側の中に等間隔で並べる。
    count = plan.darts_per_half
    offsets = [(k - (count - 1) / 2.0) * DART_SPACING_CM for k in range(count)]

    lines: list[list[tuple[float, float]]] = []
    for sign in signs:
        anchor = center_x + sign * half_width * DART_OFFSET_RATIO
        for off in offsets:
            cx = anchor + off
            half_intake = plan.intake_per_dart_cm / 2.0
            if (cx - half_intake < clear_lo + MIN_CLEARANCE_CM
                    or cx + half_intake > clear_hi - MIN_CLEARANCE_CM):
                return [], 0
            lines.append([
                (cx, waist_y - reach_up),
                (cx + half_intake, waist_y),
                (cx, waist_y + reach_down),
                (cx - half_intake, waist_y),
                (cx, waist_y - reach_up),
            ])
    return lines, len(lines)


def _closed_points_from_segments(segments: list) -> list[tuple[float, float]]:
    from .svgpath import segments_to_polyline

    points = segments_to_polyline(segments, curve_steps=120)
    if points and points[0] != points[-1]:
        points = points + [points[0]]
    return points


def _x_span_at_y(points: list[tuple[float, float]], y: float
                  ) -> tuple[float, float] | None:
    """閉じた点列の、高さ y における x の最小・最大。"""
    xs: list[float] = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if y1 == y2:
            continue
        lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
        if not (lo <= y <= hi):
            continue
        xs.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
    if len(xs) < 2:
        return None
    return min(xs), max(xs)
