import os
import sys
import datetime
import shutil
import traceback
import tomllib
import re
import fitz

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# フォルダパス定数
UNPROCESSED_DIR  = os.path.join(BASE_DIR, "receipts", "unprocessed")
PROCESSED_DIR    = os.path.join(BASE_DIR, "receipts", "processed")
INTERMEDIATE_DIR = os.path.join(BASE_DIR, "receipts", "intermediate")
RENAMED_DIR      = os.path.join(BASE_DIR, "receipts", "renamed")
OUTPUT_DIR       = os.path.join(BASE_DIR, "output")
LOG_DIR          = os.path.join(BASE_DIR, "logs")
CONFIG_PATH      = os.path.join(BASE_DIR, "config.toml")


# ------------------------------------------------------------------ #
# 設定読み込み
# ------------------------------------------------------------------ #

def load_config():
    """config.toml を読み込んで返す。ファイルがなければデフォルト値を返す。"""
    default = {
        "debit_account": "消耗品費",
        "credit_account": "事業主借",
        "check_stores": [],
        "item_keywords": [],
        "item_max": 2,
        "item_exclude_words": ["割引", "%", "％", "レジ袋", "買物袋", "買い物袋", "有料レ"],
        "sort_mode": "new_only"
    }
    if not os.path.exists(CONFIG_PATH):
        return default
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


# ------------------------------------------------------------------ #
# セッション管理
# ------------------------------------------------------------------ #

def setup_session():
    """実行セッションのタイムスタンプを生成してログフォルダを作成する。
    戻り値: (セッションID文字列, ログフォルダのパス)"""
    session_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = os.path.join(LOG_DIR, session_id)
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(INTERMEDIATE_DIR, exist_ok=True)
    os.makedirs(RENAMED_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return session_id, log_dir


# ------------------------------------------------------------------ #
# エラーログ出力
# ------------------------------------------------------------------ #

def _log_error(log_dir, step_name, context, exc):
    """エラー情報（スタックトレース込み）をログファイルに追記し、コンソールには要約のみ表示する。

    log_dir   : セッションごとのログフォルダ（setup_session が返すパス）
    step_name : "step_download" / "step_ocr" / "step_extract" など
    context   : ステップ内のどのフェーズで失敗したか（例："Drive認証", "OCR: receipt.pdf"）
    exc       : 発生した例外オブジェクト（except ブロックの e）

    ログファイルには traceback.format_exc() の全文を書く。
    traceback.format_exc() は「現在の except ブロック内」で呼ぶと、
    ファイル名・行番号・例外の型・メッセージをすべて含む文字列を返す。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(log_dir, f"{step_name}.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] [{context}]\n")
        f.write(traceback.format_exc())   # スタックトレース全文をファイルに書く
    # コンソールには1行の要約のみ表示する
    print(f"  [失敗] {context}: {exc}")
    print(f"         詳細 → {log_path}")


# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #

def _has_ocr_texts(session_dir):
    """セッションフォルダに処理対象の OCR テキストファイルが存在するか確認する。
    _scores.txt（信頼度ファイル）は対象外。"""
    if not os.path.exists(session_dir):
        return False
    return any(
        f.endswith(".txt") and not f.endswith("_scores.txt")
        for f in os.listdir(session_dir)
    )


# ------------------------------------------------------------------ #
# 実行ステップ
# ------------------------------------------------------------------ #

def step_download(session_id, log_dir, config):
    """Step 1：Google Drive の unprocessed フォルダから PDF をローカルにダウンロードする。"""
    from drive_connection import get_drive_service, list_unprocessed_files, download_file

    print("\n[Step 1] ダウンロード開始")

    try:
        service = get_drive_service()
    except Exception as e:
        _log_error(log_dir, "step_download", "Drive認証", e)
        return

    try:
        files = list_unprocessed_files(service)
    except Exception as e:
        _log_error(log_dir, "step_download", "ファイル一覧取得", e)
        return

    if not files:
        print("  unprocessed フォルダに PDF が見つかりませんでした。")
        return

    print(f"  {len(files)}件の PDF をダウンロードします...")
    for file_info in files:
        try:
            download_file(service, file_info, UNPROCESSED_DIR)
        except Exception as e:
            _log_error(log_dir, "step_download", f"ダウンロード: {file_info['name']}", e)

    print("[Step 1] ダウンロード完了")


def step_ocr(session_id, log_dir, config):
    """Step 2：unprocessed フォルダの PDF を OCR 処理してテキストを intermediate フォルダに出力する。

    呼び出す関数（ocr.py に追加が必要）：
      - list_pdfs(unprocessed_dir) ... 未実装。unprocessedフォルダ内のPDFパス一覧を返す
      - process_pdf(pdf_path, session_dir) ... 未実装。PDF 1件をOCRしてテキストを出力する
    """
    from ocr import init_reader, list_pdfs, process_pdf

    print("\n[Step 2] OCR 処理開始")

    # --- 準備フェーズ ---
    try:
        reader = init_reader()
    except Exception as e:
        _log_error(log_dir, "step_ocr", "OCRエンジン初期化", e)
        return

    try:
        pdfs = list_pdfs(UNPROCESSED_DIR)
    except Exception as e:
        _log_error(log_dir, "step_ocr", "PDFファイル一覧取得", e)
        return

    if not pdfs:
        print("  unprocessedフォルダにPDFが見つかりませんでした。")
        return

    session_dir = os.path.join(INTERMEDIATE_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # --- OCRフェーズ（1件失敗しても残りのPDFを続ける）---
    print(f"\n  {len(pdfs)}件のPDFを処理します...")
    for pdf_path in pdfs:
        try:
            process_pdf(pdf_path, session_dir, reader)
            print(f"  [成功] OCR: {os.path.basename(pdf_path)}")
        except Exception as e:
            _log_error(log_dir, "step_ocr", f"OCR処理: {os.path.basename(pdf_path)}", e)

    print("[Step 2] OCR 処理完了")


def step_extract(session_id, log_dir, config):
    """Step 3：intermediate フォルダのテキストから情報を抽出して Excel に書き出す。
    Excel 書き込み成功後にローカルと Drive の PDF を処理済みフォルダへ移動する。

    呼び出す関数：
      - extract.py の load_ocr_texts()・build_record()・write_to_excel() ... 既存
      - move_local_to_processed(pdf_name) ... このファイルに実装（下記）
      - drive_connection.py の move_to_processed_on_drive() ... 未実装
    """
    from extract import load_ocr_texts, build_record, write_to_excel, select_session

    print("\n[Step 3] 情報抽出・Excel 出力開始")

    # --- セッション選択 ---
    # OCR が直前に動いた場合（モード1・3）は今回のセッションフォルダを使う。
    # テキストがない場合（モード6：抽出のみ）はユーザーに選択させる。
    session_dir = os.path.join(INTERMEDIATE_DIR, session_id)
    if not _has_ocr_texts(session_dir):
        print("  今回のセッションに OCR テキストがありません。処理するセッションを選択してください。")
        session_dir = select_session(INTERMEDIATE_DIR)
        if session_dir is None:
            print("  [中断] セッションが選択されませんでした。")
            return

    # --- テキスト読み込み ---
    try:
        texts = load_ocr_texts(session_dir)
    except Exception as e:
        _log_error(log_dir, "step_extract", "テキストファイル読み込み", e)
        return

    # --- 層1：1ファイルごとの情報抽出（失敗しても次のファイルへ進む）---
    records = []
    succeeded_pdf_names = []
    seen_pdf_names = set()  # 重複排除用（マルチページPDF対応）
    for filename, text in texts.items():
        try:
            record = build_record(filename, text, config)
            records.append(record)
            # txtファイル名から元のPDF名を復元する
            # "_page{数字}" 以降（zoom値・前処理フラグを含む）を切り捨てる
            stem = os.path.splitext(filename)[0]
            pdf_name = re.sub(r'_page\d+.*', '', stem) + ".pdf"
            if pdf_name not in seen_pdf_names:
                seen_pdf_names.add(pdf_name)
                succeeded_pdf_names.append(pdf_name)
        except Exception as e:
            _log_error(log_dir, "step_extract", f"情報抽出: {filename}", e)

    # --- 層2a：Excel書き込み（失敗したらファイル移動には進まない）---
    try:
        write_to_excel(records, OUTPUT_DIR, config)
    except Exception as e:
        _log_error(log_dir, "step_extract", "Excel書き込み", e)
        return

    # --- 層2b-1：日付リネームコピー（ファイル移動前に実行・UNPROCESSED_DIR から読む）---
    # レコードごと＝ページごとに1件のPDFを生成してローカルと Drive に保存する
    for record in records:
        try:
            stem = os.path.splitext(record["filename"])[0]
            page_match = re.search(r'_page(\d+)', stem)
            page_index = int(page_match.group(1)) - 1 if page_match else 0
            copy_page_as_pdf(record["source_pdf"], page_index, record["date"], RENAMED_DIR)
        except Exception as e:
            _log_error(log_dir, "step_extract", f"PDFリネーム: {record['filename']}", e)
            continue  # ローカル保存が失敗したら Drive アップロードもスキップ

        # ローカル保存が成功した場合のみ Drive にアップロードする
        try:
            # 保存されたファイル名を特定する（連番付きの場合もあるため RENAMED_DIR から最新を探す）
            base_name = f"{record['date']}_対面領収書" if record["date"] else "日付不明_対面領収書"
            renamed_files = sorted([
                f for f in os.listdir(RENAMED_DIR)
                if f.startswith(base_name) and f.endswith(".pdf")
            ])
            if renamed_files:
                latest = os.path.join(RENAMED_DIR, renamed_files[-1])
                upload_renamed_to_drive(latest)
        except Exception as e:
            _log_error(log_dir, "step_extract", f"Drive アップロード: {record['filename']}", e)

    # --- 層2b-2：ファイル移動（元PDFごとに1回）---
    for pdf_name in succeeded_pdf_names:
        # ローカル移動と Drive 移動はそれぞれ独立して try する
        # （一方が失敗しても他方を試みる）
        try:
            move_local_to_processed(pdf_name)
        except Exception as e:
            _log_error(log_dir, "step_extract", f"ローカル移動: {pdf_name}", e)
        try:
            move_drive_to_processed(pdf_name, log_dir)
        except Exception as e:
            _log_error(log_dir, "step_extract", f"Drive移動: {pdf_name}", e)

    print("[Step 3] 情報抽出・Excel 出力完了")


# ------------------------------------------------------------------ #
# ファイル移動
# ------------------------------------------------------------------ #

def copy_page_as_pdf(pdf_name, page_index, date_str, renamed_dir):
    """元PDFの指定ページを1枚の単独PDFとして renamed_dir に保存する。
    同名ファイルが既にある場合は連番サフィックスを付ける。

    pdf_name   : 元PDFのファイル名（UNPROCESSED_DIR 内に存在する）
    page_index : 抽出するページ番号（0始まり）
    date_str   : 領収書から読み取った日付文字列（"YYYY-MM-DD"、読取失敗時は None）
    renamed_dir: 保存先フォルダパス
    """
    src_path = os.path.join(UNPROCESSED_DIR, pdf_name)
    base_name = f"{date_str}_対面領収書" if date_str else "日付不明_対面領収書"
    dst_path = os.path.join(renamed_dir, f"{base_name}.pdf")

    # 同名ファイルが既にある場合は _2, _3 ... と連番にする
    if os.path.exists(dst_path):
        n = 2
        while os.path.exists(os.path.join(renamed_dir, f"{base_name}_{n}.pdf")):
            n += 1
        dst_path = os.path.join(renamed_dir, f"{base_name}_{n}.pdf")

    # 元PDFを開き、指定ページだけの新しいPDFを作成して保存する
    src_doc = fitz.open(src_path)
    dst_doc = fitz.open()
    dst_doc.insert_pdf(src_doc, from_page=page_index, to_page=page_index)
    dst_doc.save(dst_path)
    dst_doc.close()
    src_doc.close()
    print(f"  [保存] renamed: {os.path.basename(dst_path)}")


def move_local_to_processed(pdf_name):
    """処理済み PDF をローカルの unprocessed から processed に移動する。
    同名ファイルが processed に存在する場合は連番サフィックスを付ける。"""
    src = os.path.join(UNPROCESSED_DIR, pdf_name)
    dst = os.path.join(PROCESSED_DIR, pdf_name)

    # 同名ファイルが既にある場合は _2, _3 ... と連番にする
    if os.path.exists(dst):
        base, ext = os.path.splitext(pdf_name)
        n = 2
        while os.path.exists(os.path.join(PROCESSED_DIR, f"{base}_{n}{ext}")):
            n += 1
        dst = os.path.join(PROCESSED_DIR, f"{base}_{n}{ext}")

    shutil.move(src, dst)
    print(f"  [移動] ローカル: {pdf_name} → processed/")


def move_drive_to_processed(pdf_name, log_dir):
    """処理済み PDF を Drive の unprocessed から processed に移動する。"""
    from drive_connection import get_drive_service, move_to_processed_on_drive
    service = get_drive_service()
    move_to_processed_on_drive(service, pdf_name)


def upload_renamed_to_drive(local_pdf_path):
    """日付リネーム済み PDF を Drive の renamed フォルダにアップロードする。"""
    from drive_connection import get_drive_service, upload_file, RENAMED_FOLDER_ID
    service = get_drive_service()
    file_name = os.path.basename(local_pdf_path)
    upload_file(service, local_pdf_path, RENAMED_FOLDER_ID, file_name)


# ------------------------------------------------------------------ #
# 実行モード選択
# ------------------------------------------------------------------ #

def select_mode():
    """実行するパターンをユーザーに選択させて番号を返す。
    有効な番号が入力されるまで何度でも再入力を促す。"""
    print("\n実行するパターンを選択してください：")
    print("  1: 全処理（ダウンロード → OCR → 抽出・Excel出力）")
    print("  2: ダウンロード ＋ OCR")
    print("  3: OCR ＋ 抽出・Excel出力")
    print("  4: ダウンロードのみ")
    print("  5: OCR のみ")
    print("  6: 抽出・Excel出力のみ")

    while True:
        try:
            mode = int(input("\n番号を入力（1〜6）: "))
        except ValueError:
            print("数字を入力してください。もう一度試してください。")
            continue
        if mode not in range(1, 7):
            print("1〜6 の番号を入力してください。もう一度試してください。")
            continue
        return mode


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main():
    log_dir = None
    try:
        # --- 初期化フェーズ（失敗したら後続ステップを実行できないため終了）---
        config = load_config()
        session_id, log_dir = setup_session()

        print(f"\nReceiptFlow を起動しました（セッション: {session_id}）")
        print(f"ログ出力先: {log_dir}")

        mode = select_mode()

        # --- ステップごとに独立した try で囲む ---
        # 1つのステップで予期しないエラーが起きても、後続ステップを続行できる。
        # ステップ内部で処理しきれなかった例外だけがここに伝わる。
        if mode in [1, 2, 4]:
            try:
                step_download(session_id, log_dir, config)
            except Exception as e:
                _log_error(log_dir, "step_download", "予期しないエラー", e)

        if mode in [1, 2, 3, 5]:
            try:
                step_ocr(session_id, log_dir, config)
            except Exception as e:
                _log_error(log_dir, "step_ocr", "予期しないエラー", e)

        if mode in [1, 3, 6]:
            try:
                step_extract(session_id, log_dir, config)
            except Exception as e:
                _log_error(log_dir, "step_extract", "予期しないエラー", e)

        print(f"\nすべての処理が完了しました。")

    except Exception as e:
        # log_dir が確定していない初期化段階のエラー
        if log_dir:
            _log_error(log_dir, "main", "初期化エラー", e)
        else:
            # ログフォルダ自体がまだ存在しないため、コンソールにスタックトレースを直接出す
            print(f"\n初期化エラー: {e}")
            traceback.print_exc()

    finally:
        # .exe 実行時はウィンドウが即座に閉じるため、終了前に必ず待機する
        input("\nEnterキーを押して終了してください...")


if __name__ == "__main__":
    main()
