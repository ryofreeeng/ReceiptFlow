import os
import sys
import tomllib
import re
import datetime

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# OCR デバッグ出力の親フォルダ（セッション選択の対象）
DEBUG_DIR = os.path.join(BASE_DIR, "receipts", "debug")

# Excel 出力先フォルダ
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 設定ファイルのパス（勘定科目・要チェック店舗リストを管理する）
CONFIG_PATH = os.path.join(BASE_DIR, "config.toml")


# ------------------------------------------------------------------ #
# 設定
# ------------------------------------------------------------------ #

def load_config():
    """config.toml から設定を読み込んで返す。
    ファイルが存在しない場合はデフォルト値を返す。"""
    default = {
        "debit_account": "消耗品費",
        "credit_account": "事業主借",
        "check_stores": [],
        "item_keywords": [],
        "item_max": 2,
        "item_exclude_words": ["割引", "%", "％", "レジ袋", "買物袋", "買い物袋", "有料レ"]
    }
    if not os.path.exists(CONFIG_PATH):
        return default
    # tomllib はバイナリモード（"rb"）でファイルを開く必要がある
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


# ------------------------------------------------------------------ #
# 日付抽出の内部実装
# ------------------------------------------------------------------ #

# 元号ごとに「元年 = 西暦何年か」を引くためのオフセット値
# 例：令和1年 = 2018 + 1 = 2019年
_ERA_OFFSETS = {
    '令和': 2018,
    '平成': 1988,
    '昭和': 1925,
}

# --- パターンごとの変換関数（先頭 _ はモジュール内部用の慣習） ---
# m は re.search() が返すマッチオブジェクト。m.group(番号) で各キャプチャグループを取り出す

def _conv_era_kanji(m):
    """和暦漢字（令和7年5月26日）→ datetime.date に変換する"""
    year = _ERA_OFFSETS[m.group(1)] + int(m.group(2))
    return datetime.date(year, int(m.group(3)), int(m.group(4)))

def _conv_western_kanji(m):
    """西暦漢字（2025年05月26日）→ datetime.date に変換する。OCR誤読 O→0 を補正する"""
    year = int(m.group(1).replace('O', '0').replace('o', '0'))
    return datetime.date(year, int(m.group(2)), int(m.group(3)))

def _conv_era_roman(m):
    """英字和暦（R7.5.26）→ datetime.date に変換する。R は令和として処理する"""
    year = _ERA_OFFSETS['令和'] + int(m.group(1))
    return datetime.date(year, int(m.group(2)), int(m.group(3)))

def _conv_western_slash(m):
    """西暦スラッシュ（2025/05/26）→ datetime.date に変換する。OCR誤読 O→0 を補正する"""
    year = int(m.group(1).replace('O', '0').replace('o', '0'))
    return datetime.date(year, int(m.group(2)), int(m.group(3)))

def _conv_western_dot(m):
    """西暦ドット（2025.05.26）→ datetime.date に変換する。OCR誤読 O→0 を補正する"""
    year = int(m.group(1).replace('O', '0').replace('o', '0'))
    return datetime.date(year, int(m.group(2)), int(m.group(3)))

# パターンと変換関数のペアリスト
# ルール：「含む文字の種類が多いもの（漢字・英字あり）」を先に置く
# 理由：数字だけのパターンは漢字・英字を含む行にも部分マッチし得るため
_DATE_PATTERNS = [
    (r'(令和|平成|昭和)(\d+)年(\d+)月(\d+)日',       _conv_era_kanji),
    (r'([12][0O]\d{2})年(\d{1,2})月(\d{1,2})日',     _conv_western_kanji),
    (r'R(\d{1,2})\.(\d{1,2})\.(\d{1,2})',            _conv_era_roman),
    (r'([12][0O]\d{2})[/／](\d{1,2})[/／](\d{1,2})', _conv_western_slash),
    (r'([12][0O]\d{2})\.(\d{1,2})\.(\d{1,2})',       _conv_western_dot),
]


# ------------------------------------------------------------------ #
# 情報抽出
# ------------------------------------------------------------------ #

def extract_date(text):
    """OCRテキストから日付を抽出して 'YYYY-MM-DD' 形式の文字列で返す。
    複数の書式（西暦・和暦・スラッシュ区切りなど）に対応する。
    抽出できなかった場合は None を返す。"""
    for line in text.splitlines():           # 1行ずつ処理する
        for pattern, converter in _DATE_PATTERNS:
            m = re.search(pattern, line)     # 行のどこにあっても見つける
            if m:
                try:
                    return str(converter(m)) # datetime.date → "2025-05-26" 形式の文字列
                except (ValueError, KeyError):
                    continue                 # 無効な値（月=13など）はスキップして次のパターンへ
    return None


# 合計金額を示すキーワード（実際の表記 + OCR誤読バリアントを含む）
_AMOUNT_KEYWORDS  = ["合計", "信計", "取引金額", "金额", "金額", "お会計", "TOTAL", "Total", "言十"]

# 合計ではなく小計・税額などを示すキーワード（誤マッチを防ぐために除外する）
# 「小言十」は「小計」の OCR 誤読（計 → 言十）
_EXCLUDE_KEYWORDS = ["小計", "小言十", "税抜", "消費税", "内税", "外税", "品名", "内訳"]


def _to_int(s):
    """数字文字列（カンマ混じり・OCR誤読 O 含む）を整数に変換する。変換できなければ None。"""
    s = s.replace('O', '0').replace('o', '0')
    s = re.sub(r'[,，]', '', s)   # 半角・全角カンマを除去
    try:
        v = int(s)
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_amount(line):
    """1行から金額を取り出して整数で返す。見つからなければ None。

    優先順：
      1. ¥ または ￥ またはバックスラッシュのいずれかの直後の数字（最も確実）
      2. ¥ なし：行内の数字列を先頭から順に試し、10 以上の最初のものを返す
         （品目数などの 1〜2 桁を除外するため）
    """
    # ¥ または ￥ または \ の直後の数字を優先
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


def extract_amount(text):
    """OCRテキストから合計金額を抽出して整数で返す。
    合計・信計・TOTALなどのキーワードの後に続く数字を探す。
    キーワード行に数字がない場合は次の行も確認する（行マージが効かない場合の保険）。
    抽出できなかった場合は None を返す。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # 小計・消費税など合計ではない行をスキップ
        if any(ex in line for ex in _EXCLUDE_KEYWORDS):
            continue
        if any(kw in line for kw in _AMOUNT_KEYWORDS):
            # フェーズ1：同じ行から金額を探す
            amount = _parse_amount(line)
            if amount is not None:
                return amount
            # フェーズ2：行マージが効かず別行になった場合の保険として次の行を確認する
            if i + 1 < len(lines):
                amount = _parse_amount(lines[i + 1])
                if amount is not None:
                    return amount
    return None


# 行末の品目価格パターン：
#   [半角/全角スペース1つ以上] [¥￥任意] [数字とカンマ] [外軽任意]
# キャプチャグループ1 = スペース直前の最後の非空白文字確認用ではなく品目名境界として使う
_ITEM_PRICE_RE = re.compile(
    r'^(.+?)'           # グループ1：品目名部分（1文字以上、最短マッチ）
    r'[　 ]+'           # 半角/全角スペース1つ以上（品目名と価格の区切り）
    r'([¥￥]?)'        # グループ2：円マーク（任意）
    r'([\dO,，]{1,9})'  # グループ3：数字とカンマの並び
    r'[　 ]?'           # 数字と外・軽の間のスペース（任意）
    r'([外軽]?)$'       # グループ4：外・軽サフィックス（任意）
)


def _is_item_price_valid(item_name, digits_raw):
    """価格パターンにマッチした各部分が品目行として有効かを検証する。
    無効と判断した場合は False を返す。"""
    # 桁数チェック（カンマを除いて5桁以下）
    digits_only = re.sub(r'[,，]', '', digits_raw).replace('O', '0').replace('o', '0')
    if not digits_only.isdigit() or len(digits_only) > 5:
        return False

    # 品目名の末尾1文字がコロン → 時刻（15:30 など）
    last_char = item_name.rstrip()[-1] if item_name.rstrip() else ''
    if last_char in (':', '：'):
        return False

    # 品目名の末尾1文字がハイフン → 電話番号や割引（090-1234-5678 など）
    # 「ー」は日本語の長音符（コーヒー・ビールなど）なので除外しない
    if last_char in ('-', '－'):
        return False

    return True


def extract_items(text, config):
    """OCRテキストから品目名を抽出してリストで返す（最大 _ITEM_MAX 件）。

    Phase 1：除外キーワード行で打ち切りながら品目候補を収集する。
    Phase 2：config["item_keywords"] に部分一致するものを優先し、
             _ITEM_MAX 件になるまで非マッチ品目で補う。
    抽出できなかった場合は空リストを返す。
    """
    keywords      = config.get("item_keywords", [])
    item_max      = config.get("item_max", 2)
    exclude_words = config.get("item_exclude_words", [])

    # --- Phase 1：候補リストを作る ---
    candidates = []
    for line in text.splitlines():
        # 小計・合計・税などの行が出た時点で品目の記載は終わりと判断して打ち切る
        if any(ex in line for ex in _EXCLUDE_KEYWORDS) or any(kw in line for kw in _AMOUNT_KEYWORDS):
            break

        # 割引・袋代など除外ワードを含む行はスキップ
        if any(w in line for w in exclude_words):
            continue

        m = _ITEM_PRICE_RE.match(line)
        if not m:
            continue

        item_name, _, digits_raw, _ = m.group(1), m.group(2), m.group(3), m.group(4)

        # 価格部分の妥当性チェック（桁数・コロン・ハイフン）
        if not _is_item_price_valid(item_name, digits_raw):
            continue

        # 品目名の前後の空白を除去して候補リストに追加
        candidates.append(item_name.strip())

    # --- Phase 2：キーワード優先で最大 _ITEM_MAX 件を選ぶ ---
    selected = []
    non_kw = []   # キーワード非マッチのバッファ（補欠用）

    for item in candidates:
        if any(kw in item for kw in keywords):
            selected.append(item)
            if len(selected) >= item_max:
                return selected   # キーワードマッチが揃った時点で確定
        else:
            non_kw.append(item)

    # キーワードマッチが item_max 未満の場合は非マッチ品目で補う
    for item in non_kw:
        if len(selected) >= item_max:
            break
        selected.append(item)

    return selected


def extract_store_name(text):
    """OCRテキストの先頭から空行を除いた最初の2行を返す。
    店舗名はレシートの冒頭に記載されることが多いため先頭2行を対象とする。
    テキストが空の場合は None を返す。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    return "\n".join(lines[:2])


def needs_review(store_name, check_stores):
    """店舗名（先頭2行）に要チェックリストの店舗名が含まれるかを判定して返す。
    check_stores の各文字列が store_name に部分一致するかで判定する。
    store_name が None の場合は False を返す。"""
    if store_name is None:
        return False
    return any(store in store_name for store in check_stores)


def build_record(filename, text, config):
    """1枚分の OCR テキストから抽出情報をまとめた辞書を返す。
    各抽出関数を呼び出してまとめる役割だけを持つ。"""
    store = extract_store_name(text)
    items = extract_items(text, config)

    # 品目リストを「卵、生クリームなど」の形式に整形する
    if items:
        summary = "、".join(items) + "など"
    else:
        summary = store or "（品目不明）"

    amount = extract_amount(text)

    # 店舗名が要チェックリストに含まれる、または金額が100円未満（OCRのスペース混入等で抽出失敗の疑い）
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
        "credit_amount":  amount,               # 借り方と同じ金額を使う
        "needs_review":   review,
    }


# ------------------------------------------------------------------ #
# Excel 出力
# ------------------------------------------------------------------ #

def write_to_excel(records, output_path):
    """抽出情報のリストを Excel ファイルに書き出す。
    列構成：日付 / 摘要 / 借方科目 / 借方金額 / 貸方科目 / 貸方金額 / 要チェック"""
    pass


# ------------------------------------------------------------------ #
# セッション選択・テキスト読み込み
# ------------------------------------------------------------------ #

def select_debug_session():
    """DEBUG_DIR 内のセッションフォルダを一覧表示してユーザーに選択させる。
    選択されたフォルダの絶対パスを返す。キャンセルされた場合は None を返す。"""
    if not os.path.exists(DEBUG_DIR):
        print(f"デバッグフォルダが見つかりません: {DEBUG_DIR}")
        return None

    # サブフォルダのみを対象とする
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


def load_ocr_texts(session_dir):
    """セッションフォルダから OCR 結果テキストファイルを読み込んで返す。
    _scores.txt は信頼度ファイルのため除外する。
    戻り値: {ファイル名: テキスト内容} の辞書"""
    texts = {}
    for filename in sorted(os.listdir(session_dir)):
        # 信頼度ファイルを除外し、テキストファイルのみ対象にする
        if filename.endswith(".txt") and not filename.endswith("_scores.txt"):
            filepath = os.path.join(session_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                texts[filename] = f.read()
    return texts


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main():
    # セッションフォルダをユーザーに選択してもらう
    session_dir = select_debug_session()
    if not session_dir:
        return

    print(f"\n選択されたセッション: {os.path.basename(session_dir)}\n")

    # 設定ファイルを読み込む
    config = load_config()

    # OCR テキストファイルを読み込む
    ocr_texts = load_ocr_texts(session_dir)
    if not ocr_texts:
        print("テキストファイルが見つかりませんでした。")
        return

    print(f"{len(ocr_texts)}件のテキストを読み込みました。\n")

    # 各テキストから情報を抽出する
    records = []
    for filename, text in ocr_texts.items():
        print(f"処理中: {filename}")
        record = build_record(filename, text, config)
        records.append(record)
        # 現時点では抽出結果を画面に表示するだけ
        print(f"  日付:     {record['date']}")
        print(f"  摘要:     {record['summary']}")
        print(f"  合計金額: {record['debit_amount']}")
        print(f"  要チェック: {record['needs_review']}")
        print()

    # Excel に書き出す
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "expenses.xlsx")
    write_to_excel(records, output_path)
    print(f"出力完了（予定）: {output_path}")


if __name__ == "__main__":
    main()
