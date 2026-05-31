# ocr.py コード解説

---

## インポート

```python
import fitz
import numpy as np
import cv2
import os
import sys
import datetime
```

| インポート | 所属パッケージ | 役割 |
|---|---|---|
| `fitz` | PyMuPDF | PDFを開いてページを画像データに変換する |
| `np`（numpy） | numpy | 画像データを数値配列として扱う。PyMuPDFとOCRエンジンの橋渡し役 |
| `cv2` | opencv-python | OCR前の画像前処理（グレースケール・2値化・コントラスト・ノイズ除去） |
| `os` | Python標準 | ファイルパス操作・フォルダ内ファイル一覧の取得 |
| `sys` | Python標準 | 実行環境の情報（`sys.frozen`・`sys.executable`）を取得 |
| `datetime` | Python標準 | デバッグ出力フォルダ名に使う日時文字列の生成 |

OCRエンジン（`easyocr`・`paddleocr`）のimportはトップレベルではなく `init_reader()` 内で遅延importしている。選択していないエンジンのパッケージがインストールされていなくてもエラーにならないようにするため。

**なぜパッケージ名が `PyMuPDF` なのに import 名が `fitz` なのか：**  
`fitz` はMuPDFライブラリの内部名称。PyMuPDFはそのPythonバインディングのため、歴史的経緯でimport名は `fitz` のまま。

---

## 定数

### `UNPROCESSED_DIR`

```python
UNPROCESSED_DIR = os.path.join(BASE_DIR, "receipts", "unprocessed")
```

OCR対象のPDFが置かれているフォルダのパス。`BASE_DIR` を起点にすることでどこから実行しても正しいパスになる（`BASE_DIR` の詳細は `drive_connection_guide.md` 参照）。

---

### `OCR_ENGINE`

```python
OCR_ENGINE = "paddleocr"
```

使用するOCRエンジンを文字列で指定する。**この1行を変えるだけでエンジンを切り替えられる。**

| 値 | エンジン | 特徴 |
|---|---|---|
| `"easyocr"` | EasyOCR | インストールが簡単。日英対応。日本語手書き・感熱紙は精度が低い傾向 |
| `"paddleocr"` | PaddleOCR | 中国Baidu製。日本語精度がEasyOCRより高い傾向。`pip install paddleocr` で導入 |
| `"manga-ocr"` | manga-ocr | 実装済み・検証済み。領収証全体に不向き（漫画吹き出し1コマ想定のモデルのため怪文書レベルの出力になった） |
| `"tesseract"` | Tesseract | （今後対応予定）Google製。別途バイナリのインストールが必要 |

エンジンを追加するときは `init_reader()` と `run_ocr()` にそれぞれelifブロックを1つ追加するだけでよい。

---

### `ZOOM`

```python
ZOOM = 2.0
```

PDFのページを画像に変換するときの拡大倍率。`ZOOM=N` にすると解像度が `N × 72 DPI` になる。

| 値 | DPI | OCR精度 | 処理速度 |
|---|---|---|---|
| `1.0` | 72 DPI | 低い | 速い |
| `2.0` | 144 DPI | 良好（PaddleOCR推奨値） | 普通 |
| `4.0` | 288 DPI | 2.0との差は限定的 | 大幅に遅い（実測済み） |

**PaddleOCR での推奨値は 2.0**。4.0 は `max_side_limit=4000px` の制限内だが処理時間が大幅に増加し、精度の改善も限定的なため。5.0 以上では内部リサイズが発生する。

**ピクセル数の計算方法**

PDF上の座標単位は **pt（ポイント）**。1インチ = 72 pt = 25.4 mm。

```
px = pt × ZOOM
```

| 用紙 | サイズ | pt換算 | ZOOM=4.0 のピクセル数 |
|---|---|---|---|
| A4 | 210 × 297 mm | 595 × 842 pt | **2380 × 3368 px**（約800万px） |
| 典型的な領収証（A4の横÷4・縦÷2） | 52.5 × 148.5 mm | 149 × 421 pt | **595 × 1684 px**（約100万px） |

領収証1枚あたり100万ピクセル。値を上げるほどOCR精度は上がるが処理時間と使用メモリが増える。

---

### `INTERMEDIATE_DIR`

```python
INTERMEDIATE_DIR = os.path.join(BASE_DIR, "receipts", "intermediate")
```

OCR結果テキストの出力先となる親フォルダ。実際の出力先は実行ごとにタイムスタンプのサブフォルダを作って使う（例：`receipts/intermediate/20250531-143022/`）。

パイプライン経由での実行時は `pipeline.py` の `setup_session()` がセッションIDのフォルダを作成し、そのパスを `step_ocr()` から `process_pdf()` に渡す。スタンドアロン実行時は `main()` がフォルダを作成する。どちらも同じフォルダ（`receipts/intermediate/`）を使うため、スタンドアロンで生成したテキストをパイプラインの抽出ステップで処理することもできる。

---

### `SAVE_DEBUG`

```python
SAVE_DEBUG = True
```

`True` のとき、OCRに渡す前の画像（PNG）・OCR結果（TXT）・信頼度（`_scores.txt`）をセッションフォルダに保存する。精度確認が終わったら `False` にすると出力しなくなる。

---

### 前処理フラグ

```python
PREPROCESS_GRAYSCALE = False  # ①グレースケール変換
PREPROCESS_BINARIZE  = False  # ②2値化（手動しきい値）
BINARIZE_THRESHOLD   = 240    # しきい値以下のピクセルを黒にする（0〜255）
PREPROCESS_DENOISE   = False  # ③ノイズ除去
DENOISE_KERNEL       = 7      # ノイズ除去の探索範囲（奇数：3・5・7）
PREPROCESS_ERODE     = False  # ④収縮（黒領域拡張＝文字を太くする）
ERODE_KERNEL         = 2      # 拡張範囲（N×Nの正方形）
```

各フラグを `True`/`False` に切り替えることで、前処理の有無を個別に制御できる。有効にした処理はファイル名ステムに `_gray`・`_bin`・`_dn`・`_er` のように追記されるため、出力ファイルを見ただけでどの前処理が適用されたか分かる。

| フラグ | ファイル名への追記例 | 効果 |
|---|---|---|
| `PREPROCESS_GRAYSCALE` | `_gray` | 彩度を除去し白黒にする |
| `PREPROCESS_BINARIZE` | `_bin240`（しきい値を末尾に付加） | 明度を0か255の二択にする |
| `PREPROCESS_DENOISE` | `_dn7`（カーネルサイズを末尾に付加） | 2値化後の孤立したゴミ点を除去する |
| `PREPROCESS_ERODE` | `_er2`（カーネルサイズを末尾に付加） | 文字領域を周囲に広げて細い文字を太くする |

例：`receipt_page1_zoom2.0_gray_bin240_dn7.png`

> **PaddleOCR 使用時は全フラグを False に設定する**。EasyOCR での検証では前処理が精度向上に寄与したが、PaddleOCR（深層学習モデル）では前処理をするほど精度が下がることを実際に確認した。PaddleOCR にはそのまま自然な画像を渡すのが最善。

---

### 後処理フラグ

```python
POSTPROCESS_MERGE_LINES = True   # Trueで行マージを有効にする
MERGE_LINE_THRESHOLD    = 0.5    # 行判定の閾値（平均ボックス高さの何倍まで同じ行とみなすか）
```

PaddleOCR の検出モデルが1行を複数の領域に分割することがあり、余計な改行が出力に混入する問題への対処。`POSTPROCESS_MERGE_LINES=True` にすると、座標情報をもとに同じ行と判定したテキストをスペースで連結して出力する。

| フラグ | 効果 |
|---|---|
| `POSTPROCESS_MERGE_LINES = False` | 検出領域ごとに改行（デフォルト動作） |
| `POSTPROCESS_MERGE_LINES = True` | 同じ行と判定した領域をスペースで連結 |

`MERGE_LINE_THRESHOLD` は全検出ボックスの平均高さに対する割合で指定する。`0.5` なら「Y中心の差が平均高さの半分以内なら同じ行」。値を上げると判定が緩く（より多くをまとめる）、下げると厳しくなる。

PaddleOCR 使用時のみ有効（座標情報 `dt_polys` を持つエンジンが必要）。

---

## `preprocess_image()` 関数

```python
def preprocess_image(img):
    if PREPROCESS_GRAYSCALE:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    if PREPROCESS_BINARIZE:
        if img.ndim != 2:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        img = cv2.threshold(img, BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
    if PREPROCESS_DENOISE:
        img = cv2.medianBlur(img, DENOISE_KERNEL)
    return img
```

numpy配列（RGB）を受け取り、有効なフラグの処理を順番に適用して返す。

---

### `cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)`

RGB（3チャンネル・3次元配列）をグレースケール（1チャンネル・2次元配列）に変換する。

人間の目は緑に最も敏感なため、単純平均ではなく次の比率で合成する：
```
グレー値 = R × 0.299 + G × 0.587 + B × 0.114
```

EasyOCRは2次元配列（グレースケール）も3次元配列（RGB）もどちらも受け付ける。

---

### `cv2.threshold()` — 2値化

```python
retval, dst = cv2.threshold(src, thresh, maxval, type)
```

#### 引数

| 引数 | 型 | 説明 |
|---|---|---|
| `src` | numpy配列 | 入力画像。**グレースケール（2次元配列）のみ対応** |
| `thresh` | float | しきい値。Otsu法のときは自動計算されるため `0` を渡す（値は無視される） |
| `maxval` | float | しきい値を超えたピクセルに割り当てる値。通常は `255`（白） |
| `type` | int定数 | 変換方式（下記参照） |

#### 戻り値

タプル `(retval, dst)` を返す。

| 戻り値 | 内容 |
|---|---|
| `retval` | 実際に使われたしきい値（Otsu法で「自動で選ばれた値が何だったか」を確認するときに使う） |
| `dst` | 変換後の画像（numpy配列） |

コードで `[1]` としているのは、タプルの2番目（変換後の画像）だけを取り出すため。

```python
img = cv2.threshold(...)[1]   # [1] で dst（画像）だけ取り出す
```

#### `type` の選択肢

| 定数 | 意味 |
|---|---|
| `THRESH_BINARY` | しきい値より大きい → `maxval`、以下 → `0` （文字：白、背景：黒） |
| `THRESH_BINARY_INV` | しきい値より大きい → `0`、以下 → `maxval` （文字：黒、背景：白。反転版） |
| `THRESH_TRUNC` | しきい値より大きい → しきい値に切り詰め、以下 → そのまま |
| `THRESH_TOZERO` | しきい値より大きい → そのまま、以下 → `0` |
| `THRESH_TOZERO_INV` | しきい値より大きい → `0`、以下 → そのまま |

さらに `+ cv2.THRESH_OTSU` を加えると、しきい値を自動計算（Otsu法）に切り替えられる。

**今回の選択**：

```python
cv2.threshold(img, BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
```

- `THRESH_BINARY`：しきい値**以下**のピクセル（暗い部分＝文字）→ 黒 `0`、それより明るいピクセル（背景）→ 白 `255`
- `BINARIZE_THRESHOLD`（デフォルト `220`）：値を大きくするほど「薄い文字も黒にする」。かすれた文字が消えるときは値を上げる

**なぜ自動（Otsu法）をやめて手動にしたか：**  
自動しきい値（`THRESH_OTSU`）は画像全体のピクセル分布から最適値を計算するため、かすれた文字のある領収証では文字まで白く消えてしまう問題が発生した。手動しきい値の方が「薄い文字まで確実に黒にする」制御がしやすい。

**参考：Otsu法**  
画像内の「暗いピクセル（文字）」と「明るいピクセル（背景）」の分布を分析し、両者を最も明確に分離できるしきい値を自動で求める方式。`thresh` 引数に `0` を渡し、`type` に `+ cv2.THRESH_OTSU` を追加すると有効になる。

```python
# Otsu法の例（今回は不採用）
img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
```

#### 代替：`adaptiveThreshold()`

1枚の画像内で光の当たり方が均一でない場合（右半分が暗い・影がかかっている）は、`threshold()` より `adaptiveThreshold()` の方が有効な場合がある。領域ごとに異なるしきい値を計算するため、全体を一律のしきい値で処理する `threshold()` より柔軟。

```python
# adaptiveThreshold の例（今回は未使用）
img = cv2.adaptiveThreshold(img, 255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY, 11, 2)
```

---

### `cv2.medianBlur()` — ノイズ除去

```python
img = cv2.medianBlur(img, DENOISE_KERNEL)
```

2値化後に生じる孤立した黒ピクセル（ゴミ点）を除去する。

#### 仕組み

各ピクセルの周辺 `DENOISE_KERNEL × DENOISE_KERNEL` 個のピクセルを調べ、その **中央値** で対象ピクセルを置き換える。

```
孤立したゴミ点（黒）の周囲が全部白（255）の場合：
  中央値 = 255 → ゴミ点が白（消える）

文字の中のピクセルは周囲にも黒ピクセルが連続：
  中央値 = 0 → 文字は黒のまま残る
```

#### `DENOISE_KERNEL` の選択

| 値 | 探索範囲 | 効果 | 注意 |
|---|---|---|---|
| `3` | 3×3=9ピクセル | 小さなゴミ点を除去 | 細い文字の端が欠けることがある |
| `5` | 5×5=25ピクセル | より強い除去 | 細い文字が消えるリスクが高まる |
| `7` | 7×7=49ピクセル | 強力だが破壊的 | 細い文字は消えやすい |

**奇数のみ有効**（中央値は中央のピクセルが1つ定まる奇数個でないと計算できないため）。

---

## `merge_lines_by_coord()` 関数

```python
def merge_lines_by_coord(texts, polys):
    # ① Y中心・高さ・X左端を計算
    # ② 平均高さ × MERGE_LINE_THRESHOLD を閾値とする
    # ③ Y中心でソートして行グループに振り分ける
    # ④ 各グループをX順にソートしてスペースで連結する
```

`run_ocr()` の PaddleOCR ブランチから `POSTPROCESS_MERGE_LINES=True` のときに呼ばれる。`rec_texts`（テキストリスト）と `dt_polys`（座標リスト）を受け取り、行マージ後のテキストリストを返す。

### 行グループ化の仕組み

```
dt_polys[i] = [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]  ← 検出領域の4頂点

Y中心  = (min(y) + max(y)) / 2
Y高さ  = max(y) - min(y)
X左端  = min(x)
```

```
全領域をY中心でソート（上から下）
    ↓
先頭を「現在の行グループ」とする
    ↓ 次の領域を見る
  Y中心の差 ≤ 平均高さ × MERGE_LINE_THRESHOLD？
    Yes → 同じ行グループに追加
    No  → 新しい行グループを開始
    ↓
各グループをX左端でソート → スペースで連結
```

### 注意点

- PaddleOCR の `dt_polys` が空のとき（まれに発生）はマージをスキップして `rec_texts` をそのまま返す
- 閾値が大きすぎると異なる行が1行にまとめられてしまう。`0.5` が基本値

---

## `init_reader()` 関数

```python
def init_reader():
    if OCR_ENGINE == "easyocr":
        import easyocr
        return easyocr.Reader(['ja', 'en'])
    elif OCR_ENGINE == "paddleocr":
        from paddleocr import PaddleOCR
        return PaddleOCR(use_textline_orientation=True, lang='japan')
    elif OCR_ENGINE == "manga-ocr":
        from manga_ocr import MangaOcr
        return MangaOcr()
    else:
        raise ValueError(f"未対応のOCRエンジン: {OCR_ENGINE!r}")
```

`OCR_ENGINE` の値に応じてOCRエンジンを初期化して返す。`main()` から1回だけ呼ばれる。

**なぜimportをここに書いているか：**  
トップレベルに `import easyocr` を書くと、EasyOCRが未インストールの環境ではスクリプト起動時点でエラーになる。`init_reader()` 内に書くことで「使うエンジンのパッケージだけが必要」になる（遅延import）。

### PaddleOCR の初期化オプション

```python
PaddleOCR(use_textline_orientation=True, lang='japan')
```

| 引数 | 値 | 意味 |
|---|---|---|
| `use_textline_orientation` | `True` | テキスト行の向き（0°/180°）を検出する。旧パラメータ `use_angle_cls` は非推奨になったため変更 |
| `lang` | `'japan'` | 日本語モデルを使う。`'en'` にすると英語専用モデルになる |

初回実行時は言語モデルを自動ダウンロードする（数百MB）。2回目以降はキャッシュを使うため即時起動する。

---

## `run_ocr()` 関数

```python
def run_ocr(reader, img):
    # 戻り値: (texts, debug_pairs) のタプル
    if OCR_ENGINE == "easyocr":
        results = reader.readtext(img)
        texts = [r[1] for r in results]
        debug_pairs = [(r[1], r[2]) for r in results]
        return texts, debug_pairs
    elif OCR_ENGINE == "paddleocr":
        ocr_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img
        results = list(reader.predict(ocr_img))
        if not results:
            return [], None
        raw_texts = results[0].get('rec_texts', [])
        scores    = results[0].get('rec_scores', [])
        polys     = results[0].get('dt_polys', [])
        debug_pairs = list(zip(raw_texts, scores)) if scores else None
        if POSTPROCESS_MERGE_LINES and polys:
            return merge_lines_by_coord(raw_texts, polys), debug_pairs
        return raw_texts, debug_pairs
    elif OCR_ENGINE == "manga-ocr":
        from PIL import Image
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        pil_img = Image.fromarray(img)
        result = reader(pil_img)
        return [result], None
    return [], None
```

`OCR_ENGINE` の差異を吸収して、テキストリストと信頼度ペアリストを **まとめて** 返す。`extract_text_from_images()` はこの関数しか呼ばないため、エンジンを追加しても呼び出し側のコードは変わらない。

---

### 戻り値がタプルになった理由

以前は `return texts` だけで「テキストのリスト」を1つ返していた。今回から信頼度情報も一緒に返す必要が出てきたため、2つの値をまとめて返す形に変えた。

```python
return texts, debug_pairs  # Pythonではカンマで並べるだけでタプルになる
```

Pythonでは `return A, B` と書くと自動的に `(A, B)` のタプルとして返される。C#の `ValueTuple` や `out` 引数に相当する。

---

### `debug_pairs` の中身

| エンジン | `debug_pairs` の中身 |
|---|---|
| EasyOCR | `[(テキスト, 信頼度), ...]` — 各検出領域のペア |
| PaddleOCR | `[(テキスト, 信頼度), ...]` — **行マージ前**の生検出データ |
| manga-ocr | `None` — 信頼度を返さないエンジン |

PaddleOCR で `POSTPROCESS_MERGE_LINES=True` のとき、テキストは行マージ済みになるが、信頼度は **マージ前の生検出領域ごと** のスコアのまま。マージすると複数の検出領域が1行にまとまるため、テキストとスコアの個数が一致しなくなる。信頼度ファイルに「行マージ前の生検出データ」と注記しているのはこのため。

---

### `[(r[1], r[2]) for r in results]` — タプルを要素とするリスト内包表記

```python
debug_pairs = [(r[1], r[2]) for r in results]
```

リスト内包表記（`[式 for 変数 in リスト]`）の各要素をタプルにした形。

EasyOCRの戻り値 `results` は `(座標, テキスト, 信頼度)` のタプルが並んだリスト：
```
results = [
    ([[x1,y1],...], "〇〇スーパー", 0.987),
    ([[x1,y1],...], "2025年05月",   0.923),
    ...
]
```

これを `(テキスト, 信頼度)` のペアだけのリストに変換している：
```
debug_pairs = [
    ("〇〇スーパー", 0.987),
    ("2025年05月",   0.923),
    ...
]
```

`r[1]` は「2番目（テキスト）」、`r[2]` は「3番目（信頼度）」。

---

### `zip()` — 2つのリストを1対1でペアにする

```python
debug_pairs = list(zip(raw_texts, scores))
```

`zip(A, B)` は2つのリストの対応する要素をペアにする関数。C#の `A.Zip(B)` と同じ。

```python
raw_texts = ["〇〇スーパー", "2025年05月", "弁当"]
scores    = [0.987,         0.923,        0.945]

list(zip(raw_texts, scores))
# → [("〇〇スーパー", 0.987), ("2025年05月", 0.923), ("弁当", 0.945)]
```

**なぜ `list()` で包むか：**  
`zip()` 単体は「ジェネレータ」を返す。ジェネレータは要素を1つずつ取り出す仕組みで、一度使い切ると空になる。`list()` で包むことで普通のリストに変換し、何度でも参照できるようになる。

**`if scores else None` の部分：**

```python
debug_pairs = list(zip(raw_texts, scores)) if scores else None
```

「`scores` が空でなければ zip する、空なら `None` にする」という **三項演算子**。Pythonの三項演算子は `真のときの値 if 条件 else 偽のときの値` という語順になる（C#の `条件 ? 真 : 偽` と逆順なので注意）。

---

### 各エンジンの戻り値の違い

**EasyOCR の戻り値：**

```python
results = reader.readtext(img)
# 戻り値: [(座標, テキスト, 信頼度), ...]
# 例: [([[x1,y1],...], "お茶", 0.95), ...]
# → r[1] でテキスト、r[2] で信頼度を取り出す
```

**PaddleOCR の戻り値：**

```python
results = list(reader.predict(img))
# predict() はジェネレータを返す。list() で消費して全結果を取得する
# 旧API: reader.ocr(img, cls=True) → 新API: reader.predict(img)
#
# results[0] は辞書。主なキー（実際に確認済み）：
#   'rec_texts'  : 認識テキストのリスト
#   'rec_scores' : 各テキストの信頼度スコア   ← 今回追加で取得
#   'dt_polys'   : 検出した文字領域の座標
#   'textline_orientation_angles' : 各行の角度
```

**なぜPaddleOCRの画像をBGRに変換するか：**  
PyMuPDFが出力するのはRGBのnumpy配列。前処理でグレースケール（2次元配列）に変換した場合、PaddleOCRがBGR（3次元配列）を期待しているためエラーになる。`cv2.COLOR_GRAY2BGR` でグレースケール→BGRに戻してからOCRに渡す。PaddleOCR使用時は前処理フラグを全てFalseにするため実際にはこの変換は発生しないが、将来的な設定変更に備えて残している。

---

## `pdf_to_images()` 関数

```python
def pdf_to_images(pdf_path, session_dir):
    doc = fitz.open(pdf_path)
    results = []
    mat = fitz.Matrix(ZOOM, ZOOM)
    basename = os.path.splitext(os.path.basename(pdf_path))[0]
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        stem = f"{basename}_page{i + 1}_zoom{ZOOM}"
        if SAVE_DEBUG:
            pix.save(os.path.join(session_dir, f"{stem}.png"))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        img = preprocess_image(img)
        if PREPROCESS_GRAYSCALE: stem += "_gray"
        if PREPROCESS_BINARIZE:  stem += "_bin"
        if PREPROCESS_DENOISE:   stem += "_dn"
        if SAVE_DEBUG:
            cv2.imwrite(os.path.join(session_dir, f"{stem}.png"), img)
        results.append((img, stem))
    doc.close()
    return results
```

**変更点（元の実装との違い）：**

- 引数に `session_dir`（デバッグ出力先フォルダ）を追加
- 戻り値が `images`（numpy配列のリスト）から `results`（`(numpy配列, ステム)` のタプルのリスト）に変わった。ステムを一緒に返すことで、テキスト保存時に画像と同じファイル名を使える
- `SAVE_DEBUG=True` のとき、前処理前の元画像（`pix.save()`）と前処理後の画像（`cv2.imwrite()`）の両方を保存する

### `fitz.open(pdf_path)`

PDFファイルを開いてドキュメントオブジェクトを返す。C#の `File.Open()` に近い役割。

### `fitz.Matrix(ZOOM, ZOOM)`

画像の変換行列を作る。`(ZOOM, ZOOM)` は「X方向にZOOM倍、Y方向にZOOM倍」を意味する。行列と聞くと難しく聞こえるが、ここでは「拡大倍率の設定」として扱えばよい。

### `page.get_pixmap(matrix=mat)`

ページを指定した倍率でピクセルデータ（RGB）に変換する。`pix` オブジェクトには次のプロパティがある：

| プロパティ | 内容 |
|---|---|
| `pix.samples` | RGBのバイト列（生の画像データ） |
| `pix.width` | 画像の幅（ピクセル） |
| `pix.height` | 画像の高さ（ピクセル） |
| `pix.n` | チャンネル数（RGBなら3、RGBAなら4） |

### `np.frombuffer(...).reshape(...)`

```python
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
```

**2段階の処理をしている：**

1. `np.frombuffer(pix.samples, dtype=np.uint8)`  
   バイト列を「0〜255の整数が並んだ1次元配列」に変換する。`dtype=np.uint8` は「符号なし8ビット整数（0〜255）」の意味。

2. `.reshape(pix.height, pix.width, pix.n)`  
   1次元配列を「(高さ, 幅, チャンネル数)」の3次元配列に並べ替える。EasyOCRはこの形式を期待している。

```
frombuffer前: [R, G, B, R, G, B, R, G, B, ...]  ← 1次元
reshape後:    [[[R, G, B], [R, G, B], ...],       ← 3次元（高さ × 幅 × チャンネル）
               [[R, G, B], [R, G, B], ...], ...]
```

### `doc.close()`

開いたPDFファイルを閉じる。C#の `Dispose()` と同じ役割。メモリを解放するために必要。`with` 構文でも書けるが今回は明示的に呼んでいる。

---

## `extract_text_from_images()` 関数

```python
def extract_text_from_images(images_with_stems, reader, session_dir):
    all_text = []
    for i, (img, stem) in enumerate(images_with_stems):
        print(f"  ページ {i + 1} をOCR中...")
        texts, debug_pairs = run_ocr(reader, img)
        page_text = "\n".join(texts)
        all_text.append(page_text)
        if SAVE_DEBUG:
            txt_path = os.path.join(session_dir, f"{stem}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(page_text)
            print(f"  テキストを保存: {txt_path}")
            if debug_pairs:
                scores_path = os.path.join(session_dir, f"{stem}_scores.txt")
                with open(scores_path, "w", encoding="utf-8") as f:
                    note = "（行マージ前の生検出データ）" if POSTPROCESS_MERGE_LINES and OCR_ENGINE == "paddleocr" else ""
                    f.write(f"検出領域ごとの信頼度{note}:\n")
                    for j, (text, score) in enumerate(debug_pairs, 1):
                        f.write(f"  {j:3d}: {score:.3f} - {text}\n")
                    avg = sum(s for _, s in debug_pairs) / len(debug_pairs)
                    f.write(f"\n平均信頼度: {avg:.3f}\n")
                print(f"  信頼度を保存: {scores_path}")
    return "\n\n".join(all_text)
```

- OCR処理を `run_ocr(reader, img)` に委譲しているため、エンジンを追加・変更してもこの関数は変更不要
- `SAVE_DEBUG=True` のとき、テキスト（`.txt`）・信頼度（`_scores.txt`）・画像（`.png`）を同じフォルダに保存する
- 信頼度ファイルは `debug_pairs` が `None` のエンジン（manga-ocr）では保存しない

---

### `texts, debug_pairs = run_ocr(reader, img)` — タプルのアンパック

```python
texts, debug_pairs = run_ocr(reader, img)
```

`run_ocr()` が `(texts, debug_pairs)` のタプルを返すので、それを2つの変数に同時に代入している。Pythonではこれを **アンパック（分解）** と呼ぶ。

```python
# タプルのアンパック
a, b = (1, 2)   # a = 1、b = 2

# 戻り値がタプルの場合も同じ
texts, debug_pairs = run_ocr(...)
# run_ocr() が return texts, debug_pairs と書いて返したものを
# 呼び出し側で texts と debug_pairs に分けて受け取れる
```

アンパックせずに受け取ることも可能（その場合は `result = run_ocr(...)` として `result[0]`・`result[1]` で参照する）。

---

### `enumerate(debug_pairs, 1)` — 開始番号を指定したインデックス付き列挙

```python
for j, (text, score) in enumerate(debug_pairs, 1):
```

通常の `enumerate(list)` は `(0, 要素)` から始まるが、`enumerate(list, 1)` と第2引数を指定すると `(1, 要素)` から始まる。

```python
pairs = [("A", 0.9), ("B", 0.8)]

# 通常（0始まり）
for j, item in enumerate(pairs):
    print(j, item)  # 0 ("A", 0.9)、1 ("B", 0.8)

# start=1 を指定（1始まり）
for j, item in enumerate(pairs, 1):
    print(j, item)  # 1 ("A", 0.9)、2 ("B", 0.8)
```

ファイルに書くとき「1番目から始まる番号」の方が人間には自然なので `1` を指定している。

---

### `for j, (text, score) in enumerate(debug_pairs, 1)` — ネストしたアンパック

`debug_pairs` の各要素は `(テキスト, 信頼度)` のタプル。`enumerate()` を通すと `(番号, (テキスト, 信頼度))` になる。

`for j, (text, score) in ...` と書くことで、`enumerate` の `(番号, タプル)` をさらに分解して `j`・`text`・`score` の3変数にまとめて受け取れる。

```python
debug_pairs = [("〇〇スーパー", 0.987), ("弁当", 0.923)]

for j, (text, score) in enumerate(debug_pairs, 1):
    # 1回目: j=1, text="〇〇スーパー", score=0.987
    # 2回目: j=2, text="弁当",         score=0.923
    print(j, text, score)
```

分解せずに書くと次のように長くなる（同じ意味）：

```python
for j, pair in enumerate(debug_pairs, 1):
    text  = pair[0]
    score = pair[1]
```

---

### f文字列のフォーマット指定子

```python
f.write(f"  {j:3d}: {score:.3f} - {text}\n")
```

f文字列の `{}` の中に `:` を付けると、**表示形式を指定**できる。

| 書き方 | 意味 | 例 |
|---|---|---|
| `{j:3d}` | 整数を幅3桁・右寄せで表示（足りない分は空白で埋める） | `1` → `"  1"`、`10` → `" 10"`、`100` → `"100"` |
| `{score:.3f}` | 小数点3桁の浮動小数点で表示（4桁目を四捨五入） | `0.987654` → `"0.988"` |
| `{text}` | 指定なし（そのまま文字列として展開） | `"〇〇スーパー"` → `"〇〇スーパー"` |

`{j:3d}` の `d` は decimal（10進整数）の意味。`3` は最低幅（数字が1桁でも3文字分のスペースを確保する）。これにより出力が縦に揃う：

```
    1: 0.987 - 〇〇スーパー
    2: 0.923 - 2025年05月
   10: 0.911 - 弁当
```

`{score:.3f}` の `.3` は「小数点以下3桁」、`f` は float（浮動小数点数）の意味。

---

### `sum(s for _, s in debug_pairs)` — ジェネレータ式と `_`

```python
avg = sum(s for _, s in debug_pairs) / len(debug_pairs)
```

2つの書き方を組み合わせている。

**① `_` で不要な変数を捨てる：**

```python
for _, s in debug_pairs:
    # _ はテキスト（今回は使わない）、s はスコア
```

Pythonでは、使わない変数に `_` という名前を付けるのが慣習。`for (text, score) in ...` と書いて `text` を使わない場合、`for (_, score) in ...` と書けば「この変数は意図的に無視している」と伝わる。

**② ジェネレータ式 `(式 for 変数 in リスト)`：**

```python
sum(s for _, s in debug_pairs)
```

リスト内包表記 `[s for _, s in debug_pairs]` は `[0.987, 0.923, ...]` のリストを作ってから `sum()` に渡す。ジェネレータ式 `(s for _, s in debug_pairs)` は要素を1つずつ `sum()` に渡すため、リスト全体を一度にメモリに載せない。今回の規模では差はないが、大量データのときにメモリ節約になる書き方。

`sum(...)` の引数に直接渡す場合は外側の `()` を省略できる（Pythonの特別ルール）：

```python
sum(s for _, s in debug_pairs)    # OK（省略形）
sum((s for _, s in debug_pairs))  # 同じ意味（省略前）
```

---

### `"\n".join(...)` と `"\n\n".join(...)`

| コード | 意味 |
|---|---|
| `"\n".join(list)` | リストの要素を改行でつなぐ（同一ページ内のテキスト） |
| `"\n\n".join(list)` | リストの要素を空行でつなぐ（ページ間の区切り） |

---

## `main()` 関数

## `list_pdfs(unprocessed_dir)` 関数

指定フォルダ内の PDF ファイルのパス一覧を返す。

```python
def list_pdfs(unprocessed_dir):
    return [
        os.path.join(unprocessed_dir, f)
        for f in sorted(os.listdir(unprocessed_dir))
        if f.lower().endswith(".pdf")
    ]
```

戻り値はフルパスのリスト（例：`["/path/to/receipts/unprocessed/receipt.pdf", ...]`）。

- `sorted()` でファイル名順に並べる（処理順を安定させるため）
- `.lower()` で `.PDF` など大文字拡張子も拾う
- `os.path.join()` でフルパスに変換する（後続の `process_pdf()` がパスを受け取るため）

`pipeline.py` の `step_ocr()` と `main()` の両方から呼ばれる。

---

## `process_pdf(pdf_path, session_dir, reader)` 関数

PDF 1件を OCR 処理してテキストを session_dir に保存する。

```python
def process_pdf(pdf_path, session_dir, reader):
    filename = os.path.basename(pdf_path)
    images_with_stems = pdf_to_images(pdf_path, session_dir)
    text = extract_text_from_images(images_with_stems, reader, session_dir)
    print(text)
```

| 引数 | 内容 |
|---|---|
| `pdf_path` | 処理対象 PDF のフルパス |
| `session_dir` | テキスト・画像の保存先フォルダ（`None` なら保存しない） |
| `reader` | `init_reader()` が返す OCR エンジンオブジェクト |

**`reader` を引数で受け取る理由：**  
PaddleOCR はモデルのロードに数秒〜十数秒かかる。1ファイルごとに初期化すると10枚処理で10倍の時間がかかる。そのため呼び出し元（`step_ocr()` または `main()`）で1回だけ初期化して使い回す設計にしている。

---

## `main()` 関数（スタンドアロン実行）

### `init_reader()`

`OCR_ENGINE` の設定に応じたエンジンを初期化して返す。`main()` で1回だけ呼び出し、以降は全PDFの処理に同じオブジェクトを使い回す（毎回初期化するとモデルのロードが繰り返されるため）。詳細は `init_reader()` のセクション参照。

### `list_pdfs(UNPROCESSED_DIR)`

PDF パス一覧を取得する。詳細は `list_pdfs()` のセクション参照。

### `[f for f in os.listdir(UNPROCESSED_DIR) if f.lower().endswith(".pdf")]` ※旧コード参考

以前の `main()` では直接フォルダを検索していたが、現在は `list_pdfs()` に切り出されている。

- `os.listdir(dir)` はフォルダ内のファイル名リストを返す
- `.lower()` は大文字小文字を統一する（`.PDF` にも対応するため）
- `.endswith(".pdf")` は文字列が `.pdf` で終わるかを判定する

---

## データの変換の流れ（まとめ）

```
PDFファイル（.pdf）
    ↓ fitz.open() でドキュメントとして読み込む
fitz.Document オブジェクト
    ↓ page.get_pixmap() でページを画像化
fitz.Pixmap（バイト列 pix.samples）
    ├─→ [SAVE_DEBUG] pix.save() で元画像（PNG）を保存
    ↓ np.frombuffer().reshape() で配列に変換
numpy配列・RGB（shape: 高さ×幅×3）
    ↓ preprocess_image() で前処理
    ├─ [PREPROCESS_GRAYSCALE] cv2.cvtColor() でグレースケール化（高さ×幅）
    ├─ [PREPROCESS_BINARIZE]  cv2.threshold() で2値化（高さ×幅・白黒のみ）
    ├─ [PREPROCESS_DENOISE]   cv2.medianBlur() でノイズ除去（孤立ゴミ点を消す）
    └─ [PREPROCESS_ERODE]     cv2.erode() で黒領域を拡張（文字を太くする）
    ├─→ [SAVE_DEBUG] cv2.imwrite() で前処理後画像（PNG）を保存
    ↓ run_ocr() でOCR（OCR_ENGINEの設定でエンジンを切り替え）
    ├─ [easyocr]   reader.readtext()  → [(座標, テキスト, 信頼度), ...]
    └─ [paddleocr] reader.predict()   → [{'rec_texts': [...], 'rec_scores': [...], 'dt_polys': [...], ...}]
    ↓ run_ocr() 内でエンジンの差異を吸収し (texts, debug_pairs) のタプルで返す
    ├─ texts      : テキスト文字列のリスト ["行1", "行2", ...]
    └─ debug_pairs: 信頼度ペアのリスト [("行1", 0.987), ...]  ※manga-ocrはNone
    ├─→ [SAVE_DEBUG] texts を .txt ファイルに保存
    ├─→ [SAVE_DEBUG, debug_pairsがNoneでない] debug_pairs を _scores.txt に保存
    │       内容: 検出領域ごとの「テキスト + 信頼度」+ 平均信頼度
    ↓ textsを改行で結合
str（抽出されたテキスト）
```

`[SAVE_DEBUG]`・`[PREPROCESS_*]` は対応するフラグが `True` のときのみ実行されるステップ。
