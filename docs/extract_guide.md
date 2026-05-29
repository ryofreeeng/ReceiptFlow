# extract.py コード解説

---

## インポート

```python
import os
import sys
import json
import re
import datetime
```

| インポート | 所属パッケージ | 役割 |
|---|---|---|
| `os` | Python標準 | ファイルパス操作・フォルダ内ファイル一覧の取得 |
| `sys` | Python標準 | `sys.frozen`・`sys.executable` で実行環境（スクリプト or exe）を判定する |
| `json` | Python標準 | `config.json` を読み込んで Python の辞書に変換する |
| `re` | Python標準 | 正規表現によるパターンマッチ。`re.search()` で文字列の中から日付を探す |
| `datetime` | Python標準 | 日付を表す `datetime.date` 型を作る。`datetime.date(2025, 5, 26)` のように使う |

### Python機能の種別早見表

「標準」「組み込み」「サードパーティ」の3種類があり、`pip install` が必要かどうかが違う。

| 種別 | 意味 | `pip install` | 例 |
|---|---|---|---|
| **組み込み（built-in）** | `import` なしでいつでも使える | 不要 | `int()`, `str()`, `len()`, `any()`, `all()`, `enumerate()`, `sorted()`, `print()`, `input()` / 文字列メソッド `.split()`, `.replace()`, `.strip()`, `.isdigit()` など |
| **標準ライブラリ** | `import` は必要だが Python 付属 | 不要 | `re`（正規表現）, `os`（ファイル操作）, `sys`（実行環境）, `json`（JSON読み書き）, `datetime`（日付） |
| **サードパーティ** | 別途インストールが必要 | **必要** | `openpyxl`（Excel読み書き・未実装） |

→ このファイルで登場する `re.search()`・`os.path.join()`・`datetime.date()` はすべて「標準ライブラリ」。  
→ `int()`・`str()`・`any()`・文字列メソッドはすべて「組み込み」。

---

## パス定数

```python
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG_DIR  = os.path.join(BASE_DIR, "receipts", "debug")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
```

### `sys.frozen` とは

`getattr(sys, 'frozen', False)` は「`sys` という変数の `frozen` という属性を読む。なければ `False` を返す」という意味。  
PyInstaller などで exe に固めた場合、`sys.frozen` が `True` になる。  
→ exe 実行時は `sys.executable`（exe ファイルのパス）を、スクリプト実行時は `__file__`（`.py` ファイルのパス）を使って、どちらでも正しいプロジェクトルートを取得する。  
詳細は `test_drive_connection_guide.md` の `BASE_DIR` の項を参照。

### `DEBUG_DIR`

`ocr.py` がデバッグ出力を保存するフォルダ（`receipts/debug/`）。  
`extract.py` はここにあるセッションフォルダを読み込む。

### `CONFIG_PATH`

勘定科目・要チェック店舗リストを管理する設定ファイルのパス。

---

## `load_config()`

```python
def load_config():
    default = {
        "debit_account": "消耗品費",
        "credit_account": "事業主借",
        "check_stores": []
    }
    return default
```

**現状**：常にデフォルト値を返すだけのスタブ（仮実装）。  
**今後の実装予定**：`CONFIG_PATH` の `config.json` を `json.load()` で読み込み、存在しない場合はデフォルト値を返す。

### 戻り値の型

Python の辞書（C# でいう `Dictionary<string, object>`）。  
呼び出し元では `config["debit_account"]` のようにキー名で値を取り出す。

---

## 日付抽出の実装

### 全体の設計

「パターンのリストを優先順に試し、最初にマッチしたものを返す」という構造になっている。  
パターンごとに変換方法が異なるため、変換関数もセットで持つ。

---

### `_ERA_OFFSETS`（定数の辞書）

```python
_ERA_OFFSETS = {
    '令和': 2018,
    '平成': 1988,
    '昭和': 1925,
}
```

元号から西暦に変換するためのオフセット値。  
**計算式**：`西暦年 = オフセット + 元号の年数`  
例：令和7年 → 2018 + 7 = 2025年

`_` で始まる名前はモジュール内部用という Python の慣習。外部から使わない定数・関数に付ける（C# の `private` に相当）。

---

### `_conv_*` 変換関数群

```python
def _conv_era_kanji(m):
    year = _ERA_OFFSETS[m.group(1)] + int(m.group(2))
    return datetime.date(year, int(m.group(3)), int(m.group(4)))
```

**`m.group(番号)` とは**：正規表現の `(...)` で囲まれた部分（キャプチャグループ）を取り出すメソッド。  
番号は左から数えた順番。`m.group(0)` はマッチした文字列全体。

例：パターン `(令和|平成)(\d+)年(\d+)月(\d+)日` が `令和7年5月26日` にマッチしたとき：
- `m.group(1)` → `"令和"`
- `m.group(2)` → `"7"`
- `m.group(3)` → `"5"`
- `m.group(4)` → `"26"`

**`datetime.date(年, 月, 日)` とは**：Python 標準の日付型を作る。  
`str(datetime.date(2025, 5, 26))` → `"2025-05-26"` という文字列に変換できる。

**`O→0 の補正**：西暦系の変換関数では `m.group(1).replace('O', '0')` でマッチした年部分のみを補正する。  
テキスト全体は書き換えない（副作用を避けるため）。

---

### `_DATE_PATTERNS`（パターンと変換関数のペアリスト）

```python
_DATE_PATTERNS = [
    (r'(令和|平成|昭和)(\d+)年(\d+)月(\d+)日',       _conv_era_kanji),
    (r'([12][0O]\d{2})年(\d{1,2})月(\d{1,2})日',     _conv_western_kanji),
    (r'R(\d{1,2})\.(\d{1,2})\.(\d{1,2})',            _conv_era_roman),
    (r'([12][0O]\d{2})[/／](\d{1,2})[/／](\d{1,2})', _conv_western_slash),
    (r'([12][0O]\d{2})\.(\d{1,2})\.(\d{1,2})',       _conv_western_dot),
]
```

**並び順のルール**：「含む文字の種類が多いもの（漢字・英字あり）」を先に置く。  
数字だけのパターンを先にすると、漢字や英字を含む行の数字部分に誤ってマッチし得るため。

**正規表現の読み方（抜粋）**：

| 記法 | 意味 | 例 |
|---|---|---|
| `(令和\|平成\|昭和)` | どれか1つにマッチ（\| は「または」） | `令和` or `平成` |
| `\d+` | 数字が1文字以上 | `7`, `26`, `365` |
| `\d{1,2}` | 数字が1〜2文字 | `5`, `26` |
| `[12][0O]\d{2}` | 西暦年（O→0の誤読を許容） | `2025`, `2O25` |
| `[/／]` | 半角または全角スラッシュ | `/` or `／` |
| `r'...'` | 生文字列（raw string）。`\` をエスケープとして解釈しない | `\d` を `\\d` と書かなくてよい |

**リストに関数を入れられる理由**：Python では関数はただの値（整数や文字列と同じ）。  
`_conv_era_kanji` と書くと「関数を呼び出す」のではなく「関数への参照」を取り出す。  
`()` を付けると呼び出し、付けないと参照。C# の `Func<Match, DateTime> converter = ConvertEraKanji;` に相当。

---

### `extract_date(text)`（実装済み）

```python
def extract_date(text):
    for line in text.splitlines():
        for pattern, converter in _DATE_PATTERNS:
            m = re.search(pattern, line)
            if m:
                try:
                    return str(converter(m))
                except (ValueError, KeyError):
                    continue
    return None
```

**`text.splitlines()` とは**：文字列を改行で分割してリストにする。  
`\n`・`\r\n` など改行の種類を問わず分割する。C# の `text.Split('\n')` に相当。

**`re.search(pattern, line)` とは**：行のどこにあってもパターンを探す。  
マッチした場合はマッチオブジェクト（`m`）を返し、なければ `None` を返す。  
`if m:` は `None` を「偽」として扱うため「マッチしたとき」の条件になる。

**`except (ValueError, KeyError):` とは**：2種類の例外をまとめて受け取る書き方。  
- `ValueError`：`datetime.date(2025, 13, 1)` のような無効な日付値（月=13 など）で発生する
- `KeyError`：`_ERA_OFFSETS["明治"]` のように辞書にないキーを参照したときに発生する（未対応の元号への保険）
- `continue` は「このパターンを諦めて次のパターンへ進む」という意味

**`str(converter(m))` とは**（組み込み）：変換関数の戻り値（`datetime.date` オブジェクト）を文字列に変換する。  
`str(datetime.date(2025, 5, 26))` → `"2025-05-26"` になる。  
`datetime.date` は Python の `__str__` という特殊メソッドが `"YYYY-MM-DD"` 形式を返すよう設計されているため、`str()` を通すだけでこの形式になる。  
C# の `date.ToString("yyyy-MM-dd")` に相当（ただし書式を指定しなくてよいのが違い）。

## 合計金額抽出の実装

### `_AMOUNT_KEYWORDS` / `_EXCLUDE_KEYWORDS`

```python
_AMOUNT_KEYWORDS  = ["合計", "信計", "取引金額", "金额", "金額", "お会計", "TOTAL", "Total", "言十"]
_EXCLUDE_KEYWORDS = ["小計", "小言十", "税抜", "消費税", "内税", "外税", "品名", "内訳"]
```

**`_AMOUNT_KEYWORDS`**：実際のレシートに書かれている表記 ＋ OCR 誤読バリアントを含む。  
- `信計`・`取引金額`・`金額` はレシートに実際に書いてある表記
- `言十` は `計`（= `言` ＋ `十` の構造の漢字）が OCR で分解されて読まれたもの

**`_EXCLUDE_KEYWORDS`**：小計・消費税など合計ではない行を除外するためのリスト。  
- `小言十` は `小計` の OCR 誤読（`計` → `言十`）

---

### `_to_int(s)`

```python
def _to_int(s):
    s = s.replace('O', '0').replace('o', '0')
    s = re.sub(r'[,，]', '', s)
    try:
        v = int(s)
        return v if v > 0 else None
    except ValueError:
        return None
```

**役割**：`"1,580"` や `"1O580"` のような汚れた数字文字列を整数に変換する共通処理。

**`.replace(置換前, 置換後)` とは**（組み込み・文字列メソッド）：文字列内の特定の文字列を別の文字列に置き換えた新しい文字列を返す（元の文字列は変えない）。  
`"1O580".replace('O', '0')` → `"10580"`。  
C# の `string.Replace()` と同じ。  
正規表現を使う `re.sub()` と違い、固定文字列の単純置換に使う。

**`re.sub(r'[,，]', '', s)` とは**（標準ライブラリ `re`）：半角カンマ `,` と全角カンマ `，` をまとめて除去する。  
`re.sub(パターン, 置換後, 対象)` は C# の `Regex.Replace(対象, パターン, 置換後)` に相当。  
引数の順番が C# と逆なので注意（Python は「パターン→置換後→対象」、C# は「対象→パターン→置換後」）。

**`int(s)` とは**（組み込み）：文字列を整数に変換する関数。変換できない文字が含まれると `ValueError` を発生させる。  
C# の `int.Parse(s)` に相当（失敗したとき例外を投げるのも同じ）。

---

### `_parse_amount(line)`

```python
def _parse_amount(line):
    # ¥ ￥ \ の直後の数字を優先
    m = re.search(r'[¥￥\\]\s*([\dO,，]+)', line)
    if m:
        val = _to_int(m.group(1))
        if val is not None:
            return val
    # ¥ なし：行内の全数字列を探し、10 以上の最初のものを返す
    for m in re.finditer(r'[\dO,，]+', line):
        val = _to_int(m.group())
        if val is not None and val >= 10:
            return val
    return None
```

**役割**：1行から金額数値を取り出して整数で返す。

**優先順序の設計理由**：

1. `¥/￥/\` の直後を優先する  
   → `合計 3品目 ¥1,580` のような行で `3`（品目数）ではなく `1580` を取れる

2. `¥` がない行では `>= 10` の数字を返す  
   → `3`（品目数）や `8`（税率）などの1桁数値を誤って金額として返さないようにする

**`re.finditer()` とは**：行内の全マッチを順番に返すイテレータ。  
`re.search()` が最初の1件しか返さないのに対し、`finditer()` は全件を返す。  
C# でいう `Regex.Matches()` に相当。

---

### `extract_amount(text)`（実装済み）

```python
def extract_amount(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(ex in line for ex in _EXCLUDE_KEYWORDS):
            continue
        if any(kw in line for kw in _AMOUNT_KEYWORDS):
            amount = _parse_amount(line)
            if amount is not None:
                return amount
            if i + 1 < len(lines):
                amount = _parse_amount(lines[i + 1])
                if amount is not None:
                    return amount
    return None
```

**`any(kw in line for kw in _AMOUNT_KEYWORDS)` とは**：  
リストの中に1つでも条件を満たすものがあれば `True` を返す。  
C# でいう `_AMOUNT_KEYWORDS.Any(kw => line.Contains(kw))` に相当。  
`all()` は全部が条件を満たすときに `True`（C# の `All()`）。

**フェーズ2（次の行を見る）の設計理由**：  
フォントサイズの違いにより OCR の検出モデルが「合計」と「¥1,580」を別領域として検出し、  
行マージ後も別行になることがある。その場合の保険として直後の行も確認する。

## 品目名抽出の実装

### `_ITEM_MAX`・`_ITEM_EXCLUDE_WORDS`・`_ITEM_PRICE_RE`

```python
_ITEM_MAX = 2

_ITEM_EXCLUDE_WORDS = ["割引", "%", "％", "レジ袋", "買物袋", "買い物袋", "有料レ"]

_ITEM_PRICE_RE = re.compile(
    r'^(.+?)'           # グループ1：品目名部分（1文字以上、最短マッチ）
    r'[　 ]+'           # 半角/全角スペース1つ以上（品目名と価格の区切り）
    r'([¥￥]?)'        # グループ2：円マーク（任意）
    r'([\dO,，]{1,9})'  # グループ3：数字とカンマの並び
    r'[　 ]?'           # 数字と外・軽の間のスペース（任意）
    r'([外軽]?)$'       # グループ4：外・軽サフィックス（任意）
)
```

**`_ITEM_MAX = 2`**：採用する品目名の最大件数を定数にしている。  
数値をコードに直接書く（マジックナンバー）と後で変更が難しいため、定数として名前をつける。  
C# でいう `const int ItemMax = 2;` に相当。

**`_ITEM_EXCLUDE_WORDS`**：レシートに含まれるが経費計上に不要な行を除外するためのリスト。  
割引（マイナス金額）・袋代などが対象。`"有料レ"` は `"有料レジ袋"` の OCR 誤読バリアント。

**`re.compile()` とは**（標準ライブラリ `re`）：正規表現パターンをあらかじめコンパイル（解析・最適化）して「正規表現オブジェクト」に変換する。  
`re.search(パターン, 行)` と毎回書く代わりに、1回コンパイルしておけば繰り返し使うとき速くなる。  
また長いパターンを複数の raw 文字列に分けて書ける（Python が自動で連結する）のも利点。  
C# でいう `new Regex(pattern)` に相当。

```python
# コンパイルせずに毎回書く書き方（短いパターンなら問題ない）
re.search(r'\d+', line)

# コンパイルして使う書き方（長いパターン・繰り返し使う場合）
MY_RE = re.compile(r'\d+')
MY_RE.search(line)   # ← オブジェクト.search() で呼び出す
MY_RE.match(line)    # ← オブジェクト.match() で呼び出す
```

**`.match()` と `.search()` の違い**：

| メソッド | マッチ位置 | C# の対応 |
|---|---|---|
| `.search(line)` | 行の**どこにでも**マッチ | `Regex.Match(text, pattern)` |
| `.match(line)` | 行の**先頭から**マッチ（`^` と同じ）| `Regex.Match(text, pattern)` の Position=0 |

`_ITEM_PRICE_RE` はパターンが `^` で始まるため `.match()` を使う。  
`^` がある時点で「行頭から」を要求しているので `.search()` でも結果は同じだが、  
意図を明確にするため先頭マッチには `.match()` を使うのが慣習。

**`_ITEM_PRICE_RE` の正規表現**：「品目名 ＋ スペース ＋ 価格」の構造を1行まとめてマッチさせる。

| 部分 | 内容 | 例 |
|---|---|---|
| `^(.+?)` | 行頭から始まる品目名（最短マッチ） | `卵`、`生クリーム` |
| `[　 ]+` | 半角・全角スペース1つ以上 | 品目と価格の区切り |
| `([¥￥]?)` | 円マーク（ある場合もない場合も） | `¥` または空 |
| `([\dO,，]{1,9})` | 数字・O・カンマの組み合わせ（1〜9文字） | `210`、`1,580`、`21O` |
| `[　 ]?` | 外・軽の前のスペース（任意） | `¥210 軽` の空白 |
| `([外軽]?)$` | 軽減税率（軽）・税抜（外）のサフィックス（任意） | `軽`、`外` または空 |

**`(.+?)` の「最短マッチ」とは**：`?` を量詞の直後に付けると「できるだけ短くマッチさせる」という意味になる。  
最長マッチ（デフォルト）だと品目名がスペースを飲み込みすぎて境界がずれることがある。

---

### `_is_item_price_valid(item_name, digits_raw)`

```python
def _is_item_price_valid(item_name, digits_raw):
    digits_only = re.sub(r'[,，]', '', digits_raw).replace('O', '0').replace('o', '0')
    if not digits_only.isdigit() or len(digits_only) > 5:
        return False

    last_char = item_name.rstrip()[-1] if item_name.rstrip() else ''
    if last_char in (':', '：'):
        return False
    if last_char in ('-', '－'):
        return False

    return True
```

**役割**：正規表現にマッチした行が本当に品目行かを追加検証する。

**`.rstrip()` とは**（組み込み・文字列メソッド）：文字列の**末尾**の空白（スペース・タブ）を除去した文字列を返す（元の文字列は変えない）。  
`.strip()` は先頭と末尾の両方、`.rstrip()` は末尾のみ（Right strip）、`.lstrip()` は先頭のみ。  
C# の `TrimEnd()` に相当（`.strip()` は `Trim()`）。

**`[-1]` とは**（組み込み）：文字列やリストの**最後の要素**を取り出すインデックス。  
`"コーヒー"[-1]` → `"ー"`、`"合計"[-1]` → `"計"` のように動く。  
C# の `str[str.Length - 1]` と同じ意味。

**`item_name.rstrip()[-1] if item_name.rstrip() else ''` とは**（組み込み・三項演算子）：  
Python の三項演算子は `値A if 条件 else 値B` という語順で書く。  
「`item_name.rstrip()` が空文字でなければ `[-1]`、空文字なら `''`」という意味。  
空文字に `[-1]` をするとエラー（`IndexError`）になるため、空チェックを先に行っている。  
C# の `条件 ? 値A : 値B` と同じ仕組みだが **語順が逆**なので注意。

**`last_char in (':', '：')` とは**（組み込み）：`in` でタプル（`(...)` で作る順序付きコレクション）の中に含まれるかを判定する。  
`last_char == ':' or last_char == '：'` と書いても同じだが、候補が複数あるときは `in (...)` のほうが短く書ける。  
C# でいう `new[] { ':', '：' }.Contains(lastChar)` に相当。

**検証内容**：

| 条件 | 理由 |
|---|---|
| 数字が5桁以下 | 6桁以上は合計金額や電話番号の一部の可能性が高い |
| 品目名末尾がコロンでない | `15:30` などの時刻を除外するため |
| 品目名末尾がハイフンでない | `090-1234` などの電話番号途中を除外するため |

**なぜ「ー」（長音符）はハイフン扱いしないか**：  
「コーヒー」「ビール」のように品目名の末尾が長音符で終わることがあるため。  
ASCIIの `-`（U+002D）と全角 `-`（U+FF0D）のみをハイフンとして扱う。

---

### `extract_items(text, config)`（実装済み）

```python
def extract_items(text, config):
    keywords = config.get("item_keywords", [])

    # --- Phase 1：候補リストを作る ---
    candidates = []
    for line in text.splitlines():
        if any(ex in line for ex in _EXCLUDE_KEYWORDS) or any(kw in line for kw in _AMOUNT_KEYWORDS):
            break
        if any(w in line for w in _ITEM_EXCLUDE_WORDS):
            continue
        m = _ITEM_PRICE_RE.match(line)
        if not m:
            continue
        item_name, _, digits_raw, _ = m.group(1), m.group(2), m.group(3), m.group(4)
        if not _is_item_price_valid(item_name, digits_raw):
            continue
        candidates.append(item_name.strip())

    # --- Phase 2：キーワード優先で最大 _ITEM_MAX 件を選ぶ ---
    selected = []
    non_kw = []

    for item in candidates:
        if any(kw in item for kw in keywords):
            selected.append(item)
            if len(selected) >= _ITEM_MAX:
                return selected
        else:
            non_kw.append(item)

    for item in non_kw:
        if len(selected) >= _ITEM_MAX:
            break
        selected.append(item)

    return selected
```

**役割**：OCRテキストから品目名を抽出して最大 `_ITEM_MAX`（2）件のリストで返す。

**`item_name, _, digits_raw, _ = m.group(1), m.group(2), m.group(3), m.group(4)` とは**：  
右辺の4つの値を左辺の4つの変数に同時に代入する（**アンパック代入**）。  
`_`（アンダースコア）は「この値は使わない」という慣習的な捨て変数名。  
グループ2（円マーク）とグループ4（外・軽）は取り出せるが `extract_items` では使わないため `_` に代入して捨てている。  
C# では捨て変数を `_` で表す `out _` に近い。

```python
# アンパック代入のイメージ（C# のタプル分解と同じ）
a, b, c = (1, 2, 3)   # a=1, b=2, c=3
a, _, c = (1, 2, 3)   # a=1, 2は捨て, c=3
```

**`.append(要素)` とは**（組み込み・リストメソッド）：リストの末尾に1件追加する。  
C# の `list.Add(item)` に相当。

**`.strip()` とは**（組み込み・文字列メソッド）：文字列の先頭・末尾の空白を除去する。  
正規表現が拾った品目名に前後の空白が残っていることがあるため除去している。  
C# の `Trim()` に相当。

**Phase 1 の打ち切り条件**：  
`_EXCLUDE_KEYWORDS`（小計・消費税など）または `_AMOUNT_KEYWORDS`（合計・TOTALなど）を含む行が出た時点で `break` する。  
→ 小計行・合計行より下に品目は来ないため。

**`break` と `continue` の違い**（組み込み）：

| キーワード | 動作 | C# の対応 |
|---|---|---|
| `break` | ループ全体をその場で終了する | `break;` と同じ |
| `continue` | 今の1回だけスキップして次のループへ進む | `continue;` と同じ |

このコードでの使い分け：合計行が出たら「もう後ろに品目は来ない」ので `break`（ループ終了）。  
割引行は「この行だけ飛ばせばいい」ので `continue`（次の行へ）。

**Phase 2 のキーワード優先ロジック**：

```
candidates（Phase1で収集した品目候補）を順番に見ていく
  ├ config["item_keywords"] に部分一致 → selected に追加（_ITEM_MAX に達したら即返す）
  └ 非マッチ → non_kw（補欠リスト）に保留

selected が _ITEM_MAX 未満なら non_kw の先頭から補充
```

例：`item_keywords = ["クリーム", "みつ"]`、`candidates = ["卵", "生クリーム", "はちみつ"]` の場合：
- 卵 → non_kw へ
- 生クリーム → selected へ（"クリーム" に部分一致）
- はちみつ → selected へ（"みつ" に部分一致）→ `_ITEM_MAX` 到達、即返す
- 結果：`["生クリーム", "はちみつ"]`

**`config.get("item_keywords", [])` とは**：  
辞書の `get(キー, デフォルト値)` は、キーが存在しない場合にデフォルト値を返す。  
`config["item_keywords"]` と違い、キーがなくても `KeyError` を起こさない。

## 情報抽出関数（スタブ）

### `extract_store_name(text)`

```python
def extract_store_name(text):
    return None
```

**役割**：OCRテキストから店舗名を返す。  
**今後の実装予定**：レシートの先頭数行（通常1〜3行目）に店舗名が来ることが多いため、その範囲を候補とする。

---

## `needs_review(store_name, check_stores)`

```python
def needs_review(store_name, check_stores):
    return False
```

**役割**：店舗名が要チェックリストに含まれるかを `True`/`False` で返す。  
`store_name` が `None` の場合は `False` を返す（`None` をリストと比較するとエラーになるため）。

**今後の実装予定**：`store_name in check_stores` または部分一致で判定する。

---

## `build_record(filename, text, config)`

```python
def build_record(filename, text, config):
    store = extract_store_name(text)
    items = extract_items(text, config)

    if items:
        summary = "、".join(items) + "など"
    else:
        summary = store or "（品目不明）"

    amount = extract_amount(text)

    review = needs_review(store, config["check_stores"])
    if amount is not None and amount < 100:
        review = True

    return {
        "filename":       filename,
        "date":           extract_date(text),
        "summary":        summary,
        "debit_account":  config["debit_account"],
        "debit_amount":   amount,
        "credit_account": config["credit_account"],
        "credit_amount":  amount,
        "needs_review":   review,
    }
```

**役割**：1枚分の OCR テキストから各抽出関数を呼び出し、1件分の仕訳データをまとめた辞書にして返す。

**`amount < 100` で `review = True` にする理由**：  
OCR のスペース混入により `"2,243"` が `"2 243"` のように分割されると、`_parse_amount()` が `2` を返してしまう。  
100 円未満はほぼあり得ないため、フラグを立てて後で確認できるようにしている。

### `"、".join(items)` とは

C# でいう `string.Join("、", items)` と同じ。  
`["卵", "生クリーム"]` → `"卵、生クリーム"` に変換する。

### `store or "（品目不明）"` とは

Python では `None or "代わりの値"` と書くと、左辺が `None`・空文字・`False` のときに右辺を返す。  
C# でいう `store ?? "（品目不明）"` と同じ。

### 戻り値（辞書）の構造

| キー | 内容 |
|---|---|
| `filename` | 元のテキストファイル名（どのレシートかの追跡用） |
| `date` | 抽出した日付（`None` の場合はセルが空欄になる） |
| `summary` | 摘要（品目名の結合 or 店舗名 or 「品目不明」） |
| `debit_account` | 借方科目（`config.json` の値） |
| `debit_amount` | 借方金額（合計金額） |
| `credit_account` | 貸方科目（`config.json` の値） |
| `credit_amount` | 貸方金額（合計金額と同じ値） |
| `needs_review` | 要チェックフラグ（`True`/`False`） |

---

## `write_to_excel(records, output_path)`

```python
def write_to_excel(records, output_path):
    pass
```

**現状**：`pass`（何もしない）のスタブ。  
`pass` は「中身のない関数・ブロック」をエラーにせず定義するためのキーワード。C# の `{}` に相当。

**今後の実装予定**：`openpyxl` ライブラリで Excel ファイルを作成する。  
列順：日付 / 摘要 / 借方科目 / 借方金額 / 貸方科目 / 貸方金額 / 要チェック

---

## `select_debug_session()`

```python
def select_debug_session():
    if not os.path.exists(DEBUG_DIR):
        print(f"デバッグフォルダが見つかりません: {DEBUG_DIR}")
        return None

    sessions = sorted(
        d for d in os.listdir(DEBUG_DIR)
        if os.path.isdir(os.path.join(DEBUG_DIR, d))
    )

    if not sessions:
        print("デバッグフォルダにセッションが見つかりませんでした。")
        return None

    print("処理するセッションを選択してください：")
    for i, session in enumerate(sessions, 1):
        print(f"  {i}: {session}")

    try:
        choice = int(input("番号を入力: "))
        if not (1 <= choice <= len(sessions)):
            print("無効な番号です。")
            return None
    except ValueError:
        print("数字を入力してください。")
        return None

    return os.path.join(DEBUG_DIR, sessions[choice - 1])
```

**役割**：`receipts/debug/` 内のセッションフォルダを一覧表示してユーザーに番号を選ばせ、選択したフォルダの絶対パスを返す。  
`ocr.py` を実行するたびにセッションフォルダが作られるため、複数ある中から選べるようにしている。

### `sorted(d for d in os.listdir(...) if ...)` とは

**ジェネレータ式**（`(式 for 変数 in リスト if 条件)`）でフィルタリングしながら `sorted()` に渡している。  
リスト内包表記 `[...]` と似ているが、`(...)` と書くことで1件ずつ処理するジェネレータになる（メモリ節約）。  
今回は `sorted()` がまとめて受け取るため、実質的な違いはほぼない。

処理の流れ：
1. `os.listdir(DEBUG_DIR)` → フォルダ内のファイル名・フォルダ名をリストで取得
2. `if os.path.isdir(...)` → サブフォルダのみに絞る（`.txt` ファイルなどを除外）
3. `sorted(...)` → 名前順に並べる（日時名のフォルダなので時系列順になる）

### `enumerate(sessions, 1)` とは

`enumerate(リスト, 開始番号)` でインデックス付きループができる。第2引数 `1` で「1から数える」を指定。  
C# でいう `for (int i = 1; i <= sessions.Count; i++)` に相当。

### `try / except ValueError` とは

`int(input(...))` は入力が数字でない場合（例：「abc」）に `ValueError` という例外を発生させる。  
`try` ブロック内でエラーが起きると `except ValueError` の中に飛ぶ。  
C# の `try { ... } catch (FormatException) { ... }` に相当。

---

## `load_ocr_texts(session_dir)`

```python
def load_ocr_texts(session_dir):
    texts = {}
    for filename in sorted(os.listdir(session_dir)):
        if filename.endswith(".txt") and not filename.endswith("_scores.txt"):
            filepath = os.path.join(session_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                texts[filename] = f.read()
    return texts
```

**役割**：選択されたセッションフォルダから OCR 結果のテキストファイルだけを読み込み、  
`{ファイル名: テキスト内容}` という辞書で返す。

### なぜ `_scores.txt` を除外するのか

同じフォルダには信頼度ファイル（`_scores.txt`）もある。これは `ocr.py` が出力したデバッグ用ファイルで、  
OCR テキスト本文ではないため除外する。

### `filename.endswith(".txt") and not filename.endswith("_scores.txt")` とは

`and not` で「`.txt` で終わるが `_scores.txt` では終わらない」という条件を作っている。  
C# でいう `filename.EndsWith(".txt") && !filename.EndsWith("_scores.txt")` と同じ。

### `with open(...) as f:` とは

ファイルを開いて `f` という名前で扱う。`with` ブロックを抜けると自動でファイルが閉じられる。  
C# の `using (var f = File.Open(...))` に相当。

---

## `main()`

```python
def main():
    session_dir = select_debug_session()
    if not session_dir:
        return

    print(f"\n選択されたセッション: {os.path.basename(session_dir)}\n")

    config = load_config()

    ocr_texts = load_ocr_texts(session_dir)
    if not ocr_texts:
        print("テキストファイルが見つかりませんでした。")
        return

    print(f"{len(ocr_texts)}件のテキストを読み込みました。\n")

    records = []
    for filename, text in ocr_texts.items():
        print(f"処理中: {filename}")
        record = build_record(filename, text, config)
        records.append(record)
        print(f"  日付:     {record['date']}")
        print(f"  摘要:     {record['summary']}")
        print(f"  合計金額: {record['debit_amount']}")
        print(f"  要チェック: {record['needs_review']}")
        print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "expenses.xlsx")
    write_to_excel(records, output_path)
    print(f"出力完了（予定）: {output_path}")
```

**役割**：処理全体の流れを制御するエントリーポイント。

### `if not session_dir: return` とは

`select_debug_session()` がキャンセル（`None`）を返した場合に早期終了する。  
`None` は Python では「偽」とみなされるため `if not None:` が `True` になる。  
C# でいう `if (sessionDir == null) return;` に相当。

### `ocr_texts.items()` とは

辞書の「キーと値のペア」を順に取り出すメソッド。  
`for filename, text in ocr_texts.items():` で、ファイル名と内容を同時に受け取れる。  
C# でいう `foreach (var (key, value) in dict)` に相当。

### `os.makedirs(OUTPUT_DIR, exist_ok=True)` とは

出力先フォルダが存在しない場合に作成する。  
`exist_ok=True` は「すでに存在しても OK（エラーにしない）」という意味。  
これがないと、フォルダが存在するときに例外が発生する。

### `if __name__ == "__main__":` とは

```python
if __name__ == "__main__":
    main()
```

このファイルを直接 `python extract.py` で実行したときだけ `main()` が呼ばれる。  
別のファイルから `import extract` した場合は `main()` は自動では実行されない。  
`ocr.py` でも同じパターンが使われている（`test_drive_connection_guide.md` 参照）。
