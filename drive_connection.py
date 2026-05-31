# google-auth パッケージ。保存済みトークン（token.json）を読み込む
from google.oauth2.credentials import Credentials
# google-auth-oauthlib パッケージ。ブラウザを開いてOAuth認証を行う
from google_auth_oauthlib.flow import InstalledAppFlow
# google-auth パッケージ。期限切れトークンをリフレッシュする
from google.auth.transport.requests import Request
# google-api-python-client パッケージ。Drive APIのサービスオブジェクトを生成する
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import os
import sys
from dotenv import load_dotenv

# .envファイルを読み込んで環境変数にセットする
load_dotenv()

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# アクセス許可の範囲。"drive"はDrive全体の読み書きを意味する
SCOPES = ["https://www.googleapis.com/auth/drive"]
# Google Cloud Consoleからダウンロードした認証情報ファイル
CREDENTIALS_FILE = "credentials.json"
# 認証後に自動生成されるトークン保存ファイル（次回以降ブラウザ不要になる）
TOKEN_FILE = "token.json"
# 取得対象フォルダのID（.envから読み込む）
UNPROCESSED_FOLDER_ID = os.environ["UNPROCESSED_FOLDER_ID"]
# 処理済みファイルの移動先フォルダID（.envから読み込む）
PROCESSED_FOLDER_ID = os.environ["PROCESSED_FOLDER_ID"]
# 日付リネーム済みPDFのアップロード先フォルダID（.envから読み込む）
RENAMED_FOLDER_ID = os.environ["RENAMED_FOLDER_ID"]


def get_drive_service():
    """Drive APIに接続するためのサービスオブジェクトを返す"""
    creds = None

    # token.jsonが既に存在する場合（2回目以降の実行）は読み込む
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # トークンがない、または無効な場合は再認証する
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # トークンが期限切れだが、リフレッシュトークンがある場合は静かに更新
            creds.refresh(Request())
        else:
            # 初回実行：ブラウザを開いてGoogleアカウントでログイン・許可を求める
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # 次回以降ブラウザ不要になるようトークンをファイルに保存
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    # 認証済み情報を使ってDrive APIサービスオブジェクトを生成して返す
    return build("drive", "v3", credentials=creds)


def list_unprocessed_files(service):
    """Drive の unprocessed フォルダ内の PDF 一覧を返す。
    trashed=false で削除済みファイルを除外する。
    戻り値: [{"id": ..., "name": ...}, ...] のリスト"""
    results = service.files().list(
        q=(f"'{UNPROCESSED_FOLDER_ID}' in parents"
           " and mimeType='application/pdf'"
           " and trashed=false"),
        fields="files(id, name)"
    ).execute()
    return results.get("files", [])


def download_file(service, file_info, local_dir):
    """Drive から PDF 1件をローカルにダウンロードする。

    file_info: {"id": ..., "name": ...} の辞書（list_unprocessed_files の戻り値の要素）
    local_dir: ローカルの保存先フォルダパス
    """
    save_path = os.path.join(local_dir, file_info["name"])
    # ファイルの内容をバイト列として取得するリクエストを作成する
    request = service.files().get_media(fileId=file_info["id"])
    # io.BytesIO はメモリ上のバッファ（一時的な書き込み先）
    buffer = io.BytesIO()
    # MediaIoBaseDownload がバッファにチャンク単位で書き込む
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    # バッファの内容をローカルファイルに書き出す
    with open(save_path, "wb") as out:
        out.write(buffer.getvalue())
    print(f"  ダウンロード完了: {file_info['name']}")


def upload_file(service, local_path, folder_id, file_name):
    """ローカルファイルを指定した Drive フォルダにアップロードする。

    local_path: アップロードするファイルのローカルパス
    folder_id : アップロード先の Drive フォルダID
    file_name : Drive 上でのファイル名
    """
    file_metadata = {
        "name": file_name,
        "parents": [folder_id],
    }
    # MediaFileUpload はローカルファイルをチャンク単位でアップロードするクラス
    media = MediaFileUpload(local_path, mimetype="application/pdf")
    service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    print(f"  [アップロード] Drive renamed: {file_name}")


def move_to_processed_on_drive(service, file_name):
    """Drive 上で PDF を unprocessed から processed フォルダに移動する。

    Drive API に「移動」操作はない。親フォルダを変更することで移動を実現する：
      addParents で processed フォルダを追加し、
      removeParents で unprocessed フォルダを削除する。
    """
    # unprocessed フォルダ内で file_name に一致するファイルの ID を取得する
    results = service.files().list(
        q=(f"'{UNPROCESSED_FOLDER_ID}' in parents"
           f" and name='{file_name}'"
           " and trashed=false"),
        fields="files(id)"
    ).execute()
    files = results.get("files", [])
    if not files:
        raise FileNotFoundError(f"Drive の unprocessed に '{file_name}' が見つかりません")

    file_id = files[0]["id"]
    service.files().update(
        fileId=file_id,
        addParents=PROCESSED_FOLDER_ID,
        removeParents=UNPROCESSED_FOLDER_ID,
        fields="id, parents"
    ).execute()
    print(f"  [移動] Drive: {file_name} → processed/")


def main():
    print("Google Drive APIに接続中...")
    service = get_drive_service()

    files = list_unprocessed_files(service)

    if not files:
        print("unprocessedフォルダにPDFが見つかりませんでした。")
        return

    unprocessed_dir = os.path.join(BASE_DIR, "receipts", "unprocessed")
    print(f"\n接続成功！{len(files)}件のPDFをダウンロードします...")
    for file_info in files:
        download_file(service, file_info, unprocessed_dir)


if __name__ == "__main__":
    main()
