# ocr.py コード解説

---

## インポート

```python
import fitz
import easyocr
import numpy as np
import os
import sys
```

| インポート | 所属パッケージ | 役割 |
|---|---|---|
| `fitz` | PyMuPDF | PDFを開いてページを画像データに変換する |
| `easyocr` | easyocr | 画像から文字を認識する（OCR） |
| `np`（numpy） | numpy | 画像データを数値配列として扱う。PyMuPDFとEasyOCRの橋渡し役 |
| `cv2` | opencv-python | OCR前の画像前処理（グレースケール・2値化・コントラスト・ノイズ除去） |
| `os` | Python標準 | ファイルパス操作・フォルダ内ファイル一覧の取得 |
| `sys` | Python標準 | 実行環境の情報（`sys.frozen`・`sys.executable`）を取得 |
| `datetime` | Python標準 | デバッグ出力フォルダ名に使う日時文字列の生成 |

**なぜパッケージ名が `PyMuPDF` なのに import 名が `fitz` なのか：**  
`fitz` はMuPDFライブラリの内部名称。PyMuPDFはそのPythonバインディングのため、歴史的経緯でimport名は `fitz` のまま。

---

## 定数

### `UNPROCESSED_DIR`

```python
UNPROCESSED_DIR = os.path.join(BASE_DIR, "receipts", "unprocessed")
```

OCR対象のPDFが置かれているフォルダのパス。`BASE_DIR` を起点にすることでどこから実行しても正しいパスになる（`BASE_DIR` の詳細は `test_drive_connection_guide.md` 参照）。

---

### `ZOOM`

```python
ZOOM = 4.0
```

PDFのページを画像に変換するときの拡大倍率。`ZOOM=N` にすると解像度が `N × 72 DPI` になる。

| 値 | DPI | OCR精度 | 処理速度 |
|---|---|---|---|
| `1.0` | 72 DPI | 低い | 速い |
| `2.0` | 144 DPI | 普通 | 普通 |
| `4.0` | 288 DPI | 良好 | 遅い |

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

### `DEBUG_DIR`

```python
DEBUG_DIR = os.path.join(BASE_DIR, "receipts", "debug")
```

デバッグ出力の親フォルダ。実際の出力先は `main()` が実行ごとに `zoom値_日時` のサブフォルダを作って使う。

---

### `SAVE_DEBUG`

```python
SAVE_DEBUG = True
```

`True` のとき、OCRに渡す前の画像（PNG）とOCR結果（TXT）をセッションフォルダに保存する。精度確認が終わったら `False` にすると出力しなくなる。

---

### 前処理フラグ

```python
PREPROCESS_GRAYSCALE = True   # ①グレースケール変換
PREPROCESS_BINARIZE  = True   # ②2値化（手動しきい値）
BINARIZE_THRESHOLD   = 220    # しきい値以下のピクセルを黒にする（0〜255）
PREPROCESS_DENOISE   = True   # ③ノイズ除去
DENOISE_KERNEL       = 3      # ノイズ除去の探索範囲（奇数：3・5・7）
```

各フラグを `True`/`False` に切り替えることで、前処理の有無を個別に制御できる。有効にした処理はファイル名ステムに `_gray`・`_bin`・`_dn` のように追記されるため、出力ファイルを見ただけどの前処理が適用されたか分かる。

| フラグ | ファイル名への追記例 | 効果 |
|---|---|---|
| `PREPROCESS_GRAYSCALE` | `_gray` | 彩度を除去し白黒にする |
| `PREPROCESS_BINARIZE` | `_bin220`（しきい値を末尾に付加） | 明度を0か255の二択にする |
| `PREPROCESS_DENOISE` | `_dn3`（カーネルサイズを末尾に付加） | 2値化後の孤立したゴミ点を除去する |

例：`receipt_page1_zoom4.0_gray_bin220_dn3.png`

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
        results = reader.readtext(img)
        page_text = "\n".join([result[1] for result in results])
        all_text.append(page_text)
        if SAVE_DEBUG:
            with open(os.path.join(session_dir, f"{stem}.txt"), "w", encoding="utf-8") as f:
                f.write(page_text)
    return "\n\n".join(all_text)
```

**変更点（元の実装との違い）：**

- 引数が `images`（numpy配列のリスト）から `images_with_stems`（`(numpy配列, ステム)` のタプルのリスト）に変わった
- `SAVE_DEBUG=True` のとき、ページごとのテキストを `{stem}.txt` として保存する。画像と同じステムを使うため対応が一目で分かる

### `reader.readtext(img)`

EasyOCRが画像を解析してテキストを認識するメソッド。戻り値はリストで、各要素は次のタプル：

```python
(座標, テキスト, 信頼度)
# 例：([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "お茶", 0.95)
```

| 要素 | 型 | 内容 |
|---|---|---|
| インデックス0 | リスト | テキストが見つかった領域の4頂点の座標 |
| インデックス1 | str | 認識されたテキスト文字列 |
| インデックス2 | float | 認識の信頼度（0〜1。1が最も確実） |

### `[result[1] for result in results]`

リスト内包表記。`results` の各要素（タプル）からインデックス1（テキスト文字列）だけを取り出して新しいリストを作る。C#の `results.Select(r => r[1]).ToList()` と同じ意味。

### `"\n".join(...)` と `"\n\n".join(...)`

| コード | 意味 |
|---|---|
| `"\n".join(list)` | リストの要素を改行でつなぐ（同一ページ内のテキスト） |
| `"\n\n".join(list)` | リストの要素を空行でつなぐ（ページ間の区切り） |

---

## `main()` 関数

### `easyocr.Reader(['ja', 'en'])`

EasyOCRの認識エンジンを初期化する。`['ja', 'en']` は「日本語と英語を認識する」という設定。

- **初回実行時**：認識モデルのファイルをインターネットからダウンロードする（数百MB・数分かかる）
- **2回目以降**：ダウンロード済みのモデルを使うため即時起動する

他にも方式はあるが、今回は日本語の領収証を対象にしているため `'ja'` は必須。

### `[f for f in os.listdir(UNPROCESSED_DIR) if f.lower().endswith(".pdf")]`

フォルダ内のファイルを一覧取得し、拡張子が `.pdf` のものだけを絞り込む。

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
    └─ [PREPROCESS_DENOISE]   cv2.medianBlur() でノイズ除去（孤立ゴミ点を消す）
    ├─→ [SAVE_DEBUG] cv2.imwrite() で前処理後画像（PNG）を保存
    ↓ reader.readtext() でOCR
[(座標, テキスト, 信頼度), ...] のリスト
    ├─→ [SAVE_DEBUG] テキストを .txt ファイルに保存
    ↓ テキスト部分だけを取り出して結合
str（抽出されたテキスト）
```

`[SAVE_DEBUG]`・`[PREPROCESS_*]` は対応するフラグが `True` のときのみ実行されるステップ。
