import os
import sys
import datetime
import shutil
import traceback
import tomllib

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# フォルダパス定数
UNPROCESSED_DIR  = os.path.join(BASE_DIR, "receipts", "unprocessed")
PROCESSED_DIR    = os.path.join(BASE_DIR, "receipts", "processed")
INTERMEDIATE_DIR = os.path.join(BASE_DIR, "receipts", "intermediate")
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
# 実行ステップ
# ------------------------------------------------------------------ #

def step_download(session_id, log_dir, config):
    """Step 1：Google Drive の unprocessed フォルダから PDF をローカルにダウンロードする。

    呼び出す関数（drive_connection.py に追加が必要）：
      - get_drive_service() ... 既存。Drive API の認証・接続
      - list_unprocessed_files(service) ... 未実装。Driveのunprocessedフォルダ内のPDF一覧を返す
      - download_file(service, file_info, local_dir) ... 未実装。PDF を1件ダウンロードする
    """
    print("\n[Step 1] ダウンロード開始")
    # from drive_connection import get_drive_service, list_unprocessed_files, download_file
    #
    # --- フェーズごとに独立した try で囲む ---
    # → どのフェーズで失敗したかを文字列で直接指定できる（context 変数は不要）
    #
    # try:
    #     service = get_drive_service()
    # except Exception as e:
    #     _log_error(log_dir, "step_download", "Drive認証", e)
    #     return  # 認証失敗は続行不可
    #
    # try:
    #     files = list_unprocessed_files(service)
    # except Exception as e:
    #     _log_error(log_dir, "step_download", "ファイル一覧取得", e)
    #     return  # 一覧取得失敗は続行不可
    #
    # --- ダウンロードフェーズ（1件失敗しても残りのファイルを続ける）---
    # for file_info in files:
    #     try:
    #         download_file(service, file_info, UNPROCESSED_DIR)
    #         print(f"  [成功] ダウンロード: {file_info['name']}")
    #     except Exception as e:
    #         _log_error(log_dir, "step_download", f"ダウンロード: {file_info['name']}", e)
    print("[Step 1] ダウンロード完了（未実装）")


def step_ocr(session_id, log_dir, config):
    """Step 2：unprocessed フォルダの PDF を OCR 処理してテキストを intermediate フォルダに出力する。

    呼び出す関数（ocr.py に追加が必要）：
      - list_pdfs(unprocessed_dir) ... 未実装。unprocessedフォルダ内のPDFパス一覧を返す
      - process_pdf(pdf_path, session_dir) ... 未実装。PDF 1件をOCRしてテキストを出力する
    """
    print("\n[Step 2] OCR 処理開始")
    # from ocr import list_pdfs, process_pdf
    #
    # try:
    #     pdfs = list_pdfs(UNPROCESSED_DIR)
    # except Exception as e:
    #     _log_error(log_dir, "step_ocr", "PDFファイル一覧取得", e)
    #     return  # 一覧取得失敗は続行不可
    #
    # session_dir = os.path.join(INTERMEDIATE_DIR, session_id)
    # os.makedirs(session_dir, exist_ok=True)   # exist_ok=True のため基本的に失敗しない
    #
    # --- OCRフェーズ（1件失敗しても残りのPDFを続ける）---
    # for pdf_path in pdfs:
    #     try:
    #         process_pdf(pdf_path, session_dir)
    #         print(f"  [成功] OCR: {os.path.basename(pdf_path)}")
    #     except Exception as e:
    #         _log_error(log_dir, "step_ocr", f"OCR処理: {os.path.basename(pdf_path)}", e)
    print("[Step 2] OCR 処理完了（未実装）")


def step_extract(session_id, log_dir, config):
    """Step 3：intermediate フォルダのテキストから情報を抽出して Excel に書き出す。
    Excel 書き込み成功後にローカルと Drive の PDF を処理済みフォルダへ移動する。

    呼び出す関数：
      - extract.py の load_ocr_texts()・build_record()・write_to_excel() ... 既存
      - move_local_to_processed(pdf_name) ... このファイルに実装（下記）
      - drive_connection.py の move_to_processed_on_drive() ... 未実装
    """
    print("\n[Step 3] 情報抽出・Excel 出力開始")
    # from extract import load_ocr_texts, build_record, write_to_excel
    #
    # try:
    #     session_dir = os.path.join(INTERMEDIATE_DIR, session_id)
    #     texts = load_ocr_texts(session_dir)
    # except Exception as e:
    #     _log_error(log_dir, "step_extract", "テキストファイル読み込み", e)
    #     return  # 読み込み失敗は続行不可
    #
    # --- 層1：1ファイルごとの情報抽出（失敗しても次のファイルへ進む）---
    # records = []
    # succeeded_pdf_names = []
    # for filename, text in texts.items():
    #     try:
    #         record = build_record(filename, text, config)
    #         records.append(record)
    #         succeeded_pdf_names.append(filename.replace(".txt", ".pdf"))
    #     except Exception as e:
    #         _log_error(log_dir, "step_extract", f"情報抽出: {filename}", e)
    #
    # --- 層2a：Excel書き込み（失敗したらファイル移動には進まない）---
    # try:
    #     write_to_excel(records, OUTPUT_DIR, config)
    # except Exception as e:
    #     _log_error(log_dir, "step_extract", "Excel書き込み", e)
    #     return  # ファイル移動には進まない
    #
    # --- 層2b：ファイル移動（Excelが成功した場合のみ実行）---
    # for pdf_name in succeeded_pdf_names:
    #     # ローカル移動と Drive 移動はそれぞれ独立して try する
    #     # （一方が失敗しても他方を試みる）
    #     try:
    #         move_local_to_processed(pdf_name)
    #     except Exception as e:
    #         _log_error(log_dir, "step_extract", f"ローカル移動: {pdf_name}", e)
    #     try:
    #         move_drive_to_processed(pdf_name, log_dir)
    #     except Exception as e:
    #         _log_error(log_dir, "step_extract", f"Drive移動: {pdf_name}", e)
    print("[Step 3] 情報抽出・Excel 出力完了（未実装）")


# ------------------------------------------------------------------ #
# ファイル移動
# ------------------------------------------------------------------ #

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
    """処理済み PDF を Drive の unprocessed から processed に移動する。

    呼び出す関数（drive_connection.py に追加が必要）：
      - move_to_processed_on_drive(service, file_name, log_dir) ... 未実装
    """
    # from drive_connection import get_drive_service, move_to_processed_on_drive
    # service = get_drive_service()
    # move_to_processed_on_drive(service, pdf_name, log_dir)
    print(f"  [移動] Drive: {pdf_name} → processed/（未実装）")


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
