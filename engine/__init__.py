"""PatternForge のコアエンジン。

サブモジュール:
  svgpath          — SVG path (d属性) の解析・変形・ポリライン化
  templates_db     — テンプレート型紙SVGのロード・検索
  part_specs       — パーツ種ごとの採寸ルール定義
  measurements     — 採寸値と標準Mサイズ
  scaling          — 採寸差分によるテンプレート変形（体型スケーリング）
  seam             — 縫い代・合印・布目線の生成
  nesting          — rectpack による2次元ネスティング（布ロス最小化）
  pdf_export       — SVG/PDF 出力（A4分割印刷対応）
  segmentation     — イラストのパーツ領域抽出（SAM連携／簡易フォールバック）
  part_classifier  — パーツ種判定（Claude API連携／簡易フォールバック）
  pipeline         — 上記全体をつなぐエンドツーエンドの生成フロー
"""
