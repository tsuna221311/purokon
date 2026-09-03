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
from dataclasses import dataclass

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
BUST_DART_COEFFICIENT = 0.10
# これ未満の摘み量は「差分ノイズ」として無視する。
MIN_BUST_DART_INTAKE_CM = 0.3
# 暴走防止のクランプ。
MAX_BUST_DART_INTAKE_CM = 3.0
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

    def is_empty(self) -> bool:
        return self.darts_per_half == 0


NO_DART = DartPlan(darts_per_half=0, intake_per_dart_cm=0.0)


def compute_dart_plan(part_type: str, scaled_half_width_cm: float,
                       measurements: Measurements) -> DartPlan:
    """バスト比・ウエスト比と、体型スケーリング後の裾半幅からダーツ計画を求める。

    scaled_half_width_cm: バスト比でX方向を変形した後の、身頃の裾半幅(cm)。
    「ウエスト比で変形した場合の目標半幅」との差分を、ダーツの摘み量とする。
    """
    if part_type not in DART_ELIGIBLE_PART_TYPES or scaled_half_width_cm <= 0:
        return NO_DART

    bust_ratio = clamp_scale(measurements.bust / STANDARD_M.bust)
    waist_ratio = clamp_scale(measurements.waist / STANDARD_M.waist)
    if bust_ratio <= 0 or waist_ratio >= bust_ratio:
        # ウエストがバスト比以上に太い(くびれが無い)体型では、ウエストを
        # 摘む必要がない。
        return NO_DART

    target_half_width = scaled_half_width_cm * (waist_ratio / bust_ratio)
    intake = scaled_half_width_cm - target_half_width - EASE_CM
    intake = min(intake, MAX_DART_INTAKE_PER_HALF_CM)
    if intake < MIN_DART_INTAKE_CM:
        return NO_DART

    if intake <= MAX_SINGLE_DART_INTAKE_CM:
        return DartPlan(darts_per_half=1, intake_per_dart_cm=intake)
    return DartPlan(darts_per_half=2, intake_per_dart_cm=intake / 2.0)


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
                      measurements: Measurements) -> tuple[list, int]:
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
        return _apply_waist_dart_zip_panel(segments, measurements)

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

    plan = compute_dart_plan(part_type, half_width, measurements)
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


def _apply_waist_dart_zip_panel(segments: list, measurements: Measurements) -> tuple[list, int]:
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

    plan = compute_dart_plan("front_bodice_zip_panel", half_width, measurements)
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


def _find_side_seam_segment_indices(segments: list) -> list[int]:
    """脇線（袖付け〜裾の間にある、ほぼ垂直な直線(L)セグメント）を探す。

    `_find_hem_segment_index`と同じ考え方で、セグメントの並び順や描画方向
    (上→下/下→上)に依存せず、幾何(「ほぼ垂直かつ十分に長い直線」)から
    動的に探す。前身頃には左右2本の脇線があるはずなので、2本以外が
    見つかった場合は呼び出し側で安全側に倒す。
    """
    positions = _segment_start_positions(segments)
    found: list[int] = []
    for i, (cmd, nums) in enumerate(segments):
        if cmd != "L":
            continue
        start = positions[i]
        end = (nums[0], nums[1])
        if (abs(start[0] - end[0]) < 1e-6
                and abs(start[1] - end[1]) > MIN_SIDE_SEAM_LENGTH_CM):
            found.append(i)
    return found


def _bust_dart_notch(start: tuple[float, float], end: tuple[float, float],
                      cf_x: float, intake: float) -> list[tuple[str, list[float]]] | None:
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
    y_top = min(start[1], end[1])
    y_bottom = max(start[1], end[1])
    seam_len = y_bottom - y_top
    # 口の幅は摘み量そのもの(round14。それ以前は4.0cm固定だった)。
    mouth = max(intake, BUST_DART_MIN_MOUTH_CM)
    half_mouth = mouth / 2.0
    if seam_len < 2 * MIN_CLEARANCE_CM + mouth:
        return None  # ダーツの口を安全に置けるだけの縦の余裕が無い

    y_apex = y_top + seam_len * BUST_DART_HEIGHT_RATIO
    y_apex = min(max(y_apex, y_top + MIN_CLEARANCE_CM + half_mouth),
                 y_bottom - MIN_CLEARANCE_CM - half_mouth)
    y_mouth_a = y_apex - half_mouth
    y_mouth_b = y_apex + half_mouth

    # BP(バスト頂点)の推定位置。x0がある側(cf_xより左右どちらか)へ
    # ミラーして求める。half_width_sideはCF-脇線間の距離。
    half_width_side = abs(cf_x - x0)
    sign = -1.0 if x0 < cf_x else 1.0
    bp_x = cf_x + sign * half_width_side * BUST_APEX_OFFSET_RATIO
    bp_y = y_top + seam_len * BUST_APEX_HEIGHT_RATIO
    bp_y = min(max(bp_y, y_top + MIN_CLEARANCE_CM), y_bottom - MIN_CLEARANCE_CM)

    # ダーツの先端は、脇線の口の中心(x0, y_apex)からBPへ向かう直線上の、
    # 摘み量に応じた位置(reach_ratio)に置く。BPそのものには到達させない。
    reach_ratio = BUST_APEX_REACH_MIN_RATIO + (
        BUST_APEX_REACH_MAX_RATIO - BUST_APEX_REACH_MIN_RATIO
    ) * min(1.0, intake / MAX_BUST_DART_INTAKE_CM)
    tip_x = x0 + reach_ratio * (bp_x - x0)
    tip_y = y_apex + reach_ratio * (bp_y - y_apex)
    tip_y = min(max(tip_y, y_top + MIN_CLEARANCE_CM), y_bottom - MIN_CLEARANCE_CM)

    # 元の描画方向(start->end)を保つよう、y座標がstartに近い側から
    # 順に3点を並べ、最後に必ず元の終点(end)へ戻す。
    if start[1] <= end[1]:
        ordered = [(x0, y_mouth_a), (tip_x, tip_y), (x0, y_mouth_b), end]
    else:
        ordered = [(x0, y_mouth_b), (tip_x, tip_y), (x0, y_mouth_a), end]
    return [("L", [x, y]) for x, y in ordered]


def _mouth_span(rep: list) -> tuple[float, float]:
    """`_bust_dart_notch`が返した4点から、(口の下端y, 口の幅) を取り出す。

    repは [口の一方, ダーツ先端, 口のもう一方, 元の終点] の順。先端のyは
    口の範囲外に出ることがある(先端はBPへ向かって斜めに伸びるため)ので、
    脇線上の2点(インデックス0と2)だけを見る。
    """
    y_a, y_b = rep[0][1][1], rep[2][1][1]
    return max(y_a, y_b), abs(y_b - y_a)


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
    candidates = _find_side_seam_segment_indices(segments)
    if len(candidates) != 2:
        return None

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


def apply_bust_dart(part_type: str, segments: list,
                     measurements: Measurements) -> tuple[list, int]:
    """前身頃の脇線に、バスト超過分に応じた脇ダーツ(V字ノッチ)を追加する。

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
    """
    if part_type not in BUST_DART_ELIGIBLE_PART_TYPES:
        return segments, 0

    intake = compute_bust_dart_intake_cm(measurements)
    if intake <= 0:
        return segments, 0

    positions = _segment_start_positions(segments)

    if part_type in BUST_DART_ZIP_PANEL_PART_TYPES:
        candidates = _find_side_seam_segment_indices(segments)
        side_idx = _bust_dart_zip_panel_side_index(segments)
        if side_idx is None:
            return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。

        other_idx = candidates[0] if candidates[1] == side_idx else candidates[1]
        cf_x = segments[other_idx][1][0]

        start = positions[side_idx]
        end = (segments[side_idx][1][0], segments[side_idx][1][1])
        rep = _bust_dart_notch(start, end, cf_x, intake)
        if rep is None:
            return segments, 0

        # ダーツの口より下を摘み量ぶん下げ、縫い合わせた後の脇線長が
        # 後ろ身頃と一致するようにする(_mouth_span/_shift_below参照)。
        threshold, mouth = _mouth_span(rep)
        shifted = _shift_below(segments, threshold, mouth)
        rep = _shift_notch_end(rep, threshold, mouth)
        new_segments = shifted[:side_idx] + rep + shifted[side_idx + 1:]
        return new_segments, 1

    side_indices = _find_side_seam_segment_indices(segments)
    if len(side_indices) != 2:
        return segments, 0  # 想定外の形状。安全側に倒してダーツを諦める。

    side_xs = [segments[i][1][0] for i in side_indices]
    center_x = sum(side_xs) / len(side_xs)

    replacements: dict[int, list] = {}
    for idx in side_indices:
        start = positions[idx]
        end = (segments[idx][1][0], segments[idx][1][1])
        rep = _bust_dart_notch(start, end, center_x, intake)
        if rep is None:
            return segments, 0  # 片側でも安全に置けなければ、両方諦める。
        replacements[idx] = rep

    # 左右のダーツは同じ高さ・同じ口の幅で作られるので、どちらか一方から
    # 口の下端と幅を取れば足りる。その下をまるごと摘み量ぶん下げて、
    # 縫い合わせた後の脇線長を後ろ身頃と一致させる(_shift_below参照)。
    threshold, mouth = _mouth_span(replacements[side_indices[0]])
    new_segments = _shift_below(segments, threshold, mouth)
    # インデックスが後ろの方から差し替えることで、前方のインデックスが
    # ずれない(挿入によって後続セグメントの位置がシフトするのを避ける)。
    for idx in sorted(replacements, reverse=True):
        rep = _shift_notch_end(replacements[idx], threshold, mouth)
        new_segments = new_segments[:idx] + rep + new_segments[idx + 1:]

    return new_segments, len(replacements)


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
