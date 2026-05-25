# google-auth パッケージ。保存済みトークン（token.json）を読み込む
from google.oauth2.credentials import Credentials
# google-auth-oauthlib パッケージ。ブラウザを開いてOAuth認証を行う
from google_auth_oauthlib.flow import InstalledAppFlow
# google-auth パッケージ。期限切れトークンをリフレッシュする
from google.auth.transport.requests import Request
# google-api-python-client パッケージ。Drive APIのサービスオブジェクトを生成する
from googleapiclient.discovery import build
import os

# アクセス許可の範囲。"drive"はDrive全体の読み書きを意味する
SCOPES = ["https://www.googleapis.com/auth/drive"]
# Google Cloud Consoleからダウンロードした認証情報ファイル
CREDENTIALS_FILE = "credentials.json"
# 認証後に自動生成されるトークン保存ファイル（次回以降ブラウザ不要になる）
TOKEN_FILE = "token.json"


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


def main():
    print("Google Drive APIに接続中...")
    service = get_drive_service()

    # Drive APIを呼び出してファイル一覧を取得する（最大10件）
    # fields: 取得する情報を絞る（id・名前・種類のみ）
    results = service.files().list(
        pageSize=10,
        fields="files(id, name, mimeType)"
    ).execute()

    # レスポンスから "files" キーの中身を取り出す（なければ空リスト）
    files = results.get("files", [])

    if not files:
        print("ファイルが見つかりませんでした。")
        return

    print(f"\n接続成功！ファイル一覧（最大10件）:")
    for f in files:
        print(f"  {f['name']}  ({f['mimeType']})")


if __name__ == "__main__":
    main()
