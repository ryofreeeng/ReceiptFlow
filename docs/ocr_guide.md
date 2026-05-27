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
| `os` | Python標準 | ファイルパス操作・フォルダ内ファイル一覧の取得 |
| `sys` | Python標準 | 実行環境の情報（`sys.frozen`・`sys.executable`）を取得 |

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
ZOOM = 2.0
```

PDFのページを画像に変換するときの拡大倍率。

| 値 | 解像度 | OCR精度 | 処理速度 |
|---|---|---|---|
| `1.0` | 等倍（低） | 低い | 速い |
| `2.0` | 2倍（推奨） | 良好 | 普通 |
| `3.0` | 3倍（高） | より高い | 遅い |

Adobe ScanのPDFはすでに高解像度だが、`2.0` にしておくことでEasyOCRの認識精度が安定する。

---

## `pdf_to_images()` 関数

```python
def pdf_to_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = []
    mat = fitz.Matrix(ZOOM, ZOOM)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        images.append(img)
    doc.close()
    return images
```

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
def extract_text_from_images(images, reader):
    all_text = []
    for i, img in enumerate(images):
        print(f"  ページ {i + 1} をOCR中...")
        results = reader.readtext(img)
        page_text = "\n".join([result[1] for result in results])
        all_text.append(page_text)
    return "\n\n".join(all_text)
```

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
    ↓ np.frombuffer().reshape() で配列に変換
numpy配列（shape: 高さ×幅×チャンネル数）
    ↓ reader.readtext() でOCR
[(座標, テキスト, 信頼度), ...] のリスト
    ↓ テキスト部分だけを取り出して結合
str（抽出されたテキスト）
```
