# drive_connection.py 解説ガイド

---

## インポート

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import os
import sys
from dotenv import load_dotenv
```

| インポート | 所属パッケージ | 役割 |
|---|---|---|
| `Credentials` | google-auth | 保存済みトークン（token.json）を読み込む |
| `InstalledAppFlow` | google-auth-oauthlib | ブラウザを開いてOAuth認証を行う |
| `Request` | google-auth | 期限切れトークンをリフレッシュする |
| `build` | google-api-python-client | Drive APIのサービスオブジェクトを生成する |
| `MediaIoBaseDownload` | google-api-python-client | ファイルをチャンク単位でダウンロードする |
| `io` | Python標準 | メモリ上のバッファ（`BytesIO`）を使うために必要 |
| `os` | Python標準 | 環境変数の読み取り・ファイルパス操作に使う |
| `sys` | Python標準 | 実行環境の情報（`sys.frozen`・`sys.executable`）を取得するために必要 |
| `load_dotenv` | python-dotenv | `.env` ファイルを読み込んで環境変数にセットする |

---

## モジュールレベルの処理

### `load_dotenv()`

```python
load_dotenv()
```

`.env` ファイルを読み込み、中に書かれた値を環境変数としてセットする。この1行を書くことで、以降 `os.environ["キー名"]` で値が取り出せるようになる。

`.env` の内容例：
```
UNPROCESSED_FOLDER_ID=12dzXOJ96ChRTxbAuxDhWcjZ4xwNSNk2L
```

`.env` は `credentials.json` や `token.json` と同様にgitに上げない（個人情報・環境固有の設定のため）。

---

### `BASE_DIR` の決定

```python
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

以降のパス構築（ダウンロード先など）はすべて `BASE_DIR` を起点にする。こうすることで、どこから実行しても正しいプロジェクトルートを起点にできる。

**なぜ相対パス（`"receipts/unprocessed/"`）ではダメか：**  
相対パスはカレントディレクトリ（プロセスが「今いる場所」）を起点にするため、タスクスケジューラから実行すると `C:\Windows\System32` などが起点になってしまい失敗する。

**判定の仕組み：**

| 実行方法 | `sys.frozen` | 使うパス |
|---|---|---|
| `python script.py`・タスクスケジューラ（`.py`） | 存在しない → `False` | `__file__`（スクリプト自身のパス）を起点 |
| PyInstallerで変換した `.exe`・タスクスケジューラ（`.exe`） | `True` | `sys.executable`（exeのパス）を起点 |

`getattr(sys, 'frozen', False)` は `sys.frozen` 属性が存在しない場合に `False` を返す安全な書き方。通常スクリプト実行時は `sys.frozen` 自体が存在しないため `AttributeError` が起きないようにしている。

---

## 定数（グローバル変数）

### SCOPES
```python
SCOPES = ["https://www.googleapis.com/auth/drive"]
```

Googleに対して「このアプリにどの範囲のアクセスを許可するか」を宣言するリスト。

| スコープ文字列 | 意味 |
|---|---|
| `https://www.googleapis.com/auth/drive` | Driveの読み書き全権限 |
| `https://www.googleapis.com/auth/drive.readonly` | 読み取りのみ（書き込み不可） |
| `https://www.googleapis.com/auth/drive.file` | このアプリが作ったファイルのみ操作可能 |

**変更する場面：** アップロードなど書き込みが不要になった場合は `drive.readonly` に絞るとセキュリティが上がる。リストにしているのは複数のスコープを同時に指定できる設計のため。

**注意：** SCOPESを変更したら `token.json` を削除して再認証する必要がある（古いトークンはスコープが変わっても自動更新されないため）。

---

### CREDENTIALS_FILE / TOKEN_FILE

```python
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
```

| 定数 | 内容 |
|---|---|
| `CREDENTIALS_FILE` | Google Cloud Consoleからダウンロードしたクライアント認証情報。gitに上げない |
| `TOKEN_FILE` | 認証後に自動生成されるアクセストークン。gitに上げない |

---

### UNPROCESSED_FOLDER_ID

```python
UNPROCESSED_FOLDER_ID = os.environ["UNPROCESSED_FOLDER_ID"]
```

Drive内の `unprocessed` フォルダのID。`.env` から読み込む。フォルダIDはDriveでフォルダを開いたときのURLの末尾：

```
https://drive.google.com/drive/folders/★ここ★
```

`os.environ["キー名"]` はキーが存在しない場合に `KeyError` を発生させる。意図的にそうしている（値がなければ起動時に即エラーにして、後から気づくより早く問題を発見するため）。

---

## `get_drive_service()` 関数

### `Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)`

保存済みの `token.json` からトークンを読み込むメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `TOKEN_FILE` | str | 読み込むトークンファイルのパス |
| `SCOPES` | list | このトークンが対応しているスコープのリスト。ファイル内のスコープと一致しているか確認するために渡す |

---

### `if not creds or not creds.valid:` の条件分岐が2段になっている理由

```python
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        ...
    else:
        ...
```

**外側の if：** トークンがそもそも存在しないか、使えない状態かを確認する。

**内側の if：** 「使えない理由」によって処理を分けている。

| 状態 | 内側の条件 | 行う処理 |
|---|---|---|
| トークンがない（初回） | `creds` が None → else へ | ブラウザを開いて認証 |
| 期限切れ・リフレッシュ可能 | `expired` かつ `refresh_token` あり | ブラウザ不要で自動更新 |
| 期限切れ・リフレッシュ不可 | どちらかが False → else へ | ブラウザを開いて再認証 |

このように分けることで、毎回ブラウザが開かずに済む。

**Q. トークンが存在していて期限も切れていない場合、内側の処理にたどり着いてしまうか？**

たどり着かない。外側の条件 `not creds or not creds.valid` が `False` になるため、ブロック全体をスキップする。「トークンあり・有効」の場合はブラウザが開く処理には一切進まない。

---

### `InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)`

`credentials.json` を使ってOAuth認証フローを準備するメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `CREDENTIALS_FILE` | str | Google Cloud Consoleからダウンロードしたファイルのパス |
| `SCOPES` | list | 要求するアクセス権限の範囲 |

---

### `flow.run_local_server(port=0)`

ブラウザを開いてユーザーにGoogleログインと許可を求めるメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `port` | int | 認証後にGoogleがリダイレクトしてくるローカルサーバーのポート番号。`0` を指定すると空いているポートを自動で選ぶ |

**変更する場面：** 特定のポートを固定したい場合は `port=8080` のように数値を指定する。ただし `0` で問題が起きることはほぼない。

**Q. このローカルサーバーはFlaskなどで立てる普通のWebサーバーと同じもの？**

別物。よくあるWebサーバーとの違い：

| | よくあるWebサーバー | 今回のローカルサーバー |
|---|---|---|
| 目的 | ブラウザにHTMLを返す | Googleからの1回のリダイレクトを受け取るだけ |
| 起動時間 | ずっと動き続ける | 認証が終わったら即終了 |
| ブラウザで見える画面 | 自分で作ったHTML | 「認証完了、このウィンドウを閉じてください」だけ |

**宅配の受け取りボックス**に近いイメージ。荷物（認証コード）が届く瞬間だけ存在して、受け取ったら閉まる。

**Q. 何がどうなってトークンが取得されてcredsに代入されるか？**

`creds = flow.run_local_server(port=0)` の1行の中で以下がすべて順番に起きている。

```
① ライブラリがポート番号（例：54321）でミニサーバーを起動
② ブラウザが自動で開き、Googleの認証ページへ
   （URLにredirect_uri=http://localhost:54321 が含まれている）
③ ユーザーがGoogleでログインして「許可」をクリック
④ Googleがブラウザを http://localhost:54321/?code=ABC123 にリダイレクト
   （ABC123は「認証コード」。まだトークンではなく引換券）
⑤ ミニサーバーがそのリクエストを受け取り、code=ABC123 を取り出す
⑥ ライブラリが内部でGoogleのサーバーに通信する
   「この引換券（ABC123）をアクセストークンに交換してください」
⑦ GoogleがアクセストークンとリフレッシュトークンをPythonに返す
⑧ ライブラリがそれをCredentialsオブジェクトにまとめてreturn
⑨ creds = ... の代入が完了する
```

④で受け取るコードがいきなりトークンではなく「引換券」になっているのは、OAuth2.0というセキュリティ設計の仕様で、トークンを直接URLに載せないようにしているため。⑥の通信（コード→トークンの交換）もライブラリが内部でやってくれている。

---

### `open(TOKEN_FILE, "w")` でのトークン保存

```python
with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())
```

`open()` の引数の意味：

| 引数 | 意味 |
|---|---|
| `TOKEN_FILE` | 書き込むファイルのパス（`"token.json"`） |
| `"w"` | 書き込みモード（write）。ファイルが既にあれば上書き、なければ新規作成 |

他のモード（参考）：

| モード | 意味 |
|---|---|
| `"r"` | 読み込みのみ |
| `"a"` | 追記（既存内容を消さない） |
| `"rb"` | バイナリ読み込み（画像・PDFを読む時に使う） |
| `"wb"` | バイナリ書き込み（画像・PDFを保存する時に使う） |

`with` 構文を使っているのは、処理が終わったら自動でファイルを閉じるため。C#の `using` と同じ役割。

---

### `build("drive", "v3", credentials=creds)`

Drive APIに接続するサービスオブジェクトを生成するメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `"drive"` | str | 使用するGoogleサービスの名前 |
| `"v3"` | str | APIのバージョン。Drive APIはv3が現在の最新 |
| `credentials` | Credentials | 認証情報オブジェクト |

**変更する場面：** GoogleがAPIの新バージョン（v4等）をリリースしたら `"v4"` に変える。ただし現時点ではv3が最新。

---

## `main()` 関数

### `service.files().list(q=..., fields=...)`

```python
results = service.files().list(
    q=f"'{UNPROCESSED_FOLDER_ID}' in parents and mimeType='application/pdf'",
    fields="files(id, name, mimeType)"
).execute()
```

Driveのファイル一覧を取得するAPIメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `q` | str | 絞り込み条件。SQLの `WHERE` 句に相当する |
| `fields` | str | レスポンスに含めるフィールドを絞る指定。省略するとすべての情報が返ってきて通信量が増える |

**`q` パラメータの書き方：**

| 条件の書き方 | 意味 |
|---|---|
| `'フォルダID' in parents` | 指定フォルダの直下にあるファイル |
| `mimeType='application/pdf'` | PDFだけに絞る |
| `and` でつなぐ | 両方の条件を同時に満たすもの |

**`mimeType` の主な値：**

| mimeType の値 | 意味 |
|---|---|
| `application/pdf` | PDF |
| `image/jpeg` | JPEG画像 |
| `application/vnd.google-apps.folder` | Driveのフォルダ |
| `application/vnd.google-apps.spreadsheet` | Googleスプレッドシート |

**他に指定できる主なフィールド：**

| フィールド名 | 意味 |
|---|---|
| `id` | DriveファイルのユニークID（API操作に必須） |
| `name` | ファイル名 |
| `mimeType` | ファイルの種類 |
| `size` | ファイルサイズ（バイト） |
| `createdTime` | 作成日時 |
| `modifiedTime` | 最終更新日時 |
| `parents` | 入っているフォルダのID |
| `webViewLink` | ブラウザで開くURL |

**件数が多い場合（ページネーション）：**

Drive APIは一度に最大1000件まで。それ以上ある場合は `nextPageToken` を使って繰り返し取得する。本アプリでは特定フォルダ内のPDFだけを対象にするため、件数が問題になることはほぼない。

```python
# 全件取得する場合の書き方（参考）
all_files = []
page_token = None
while True:
    results = service.files().list(
        q=f"'{UNPROCESSED_FOLDER_ID}' in parents and mimeType='application/pdf'",
        pageSize=1000,
        fields="nextPageToken, files(id, name, mimeType)",
        pageToken=page_token
    ).execute()
    all_files.extend(results.get("files", []))
    page_token = results.get("nextPageToken")
    if not page_token:
        break
```

---

### `results.get("files", [])`

辞書から値を取り出すPythonの組み込みメソッド。

| 引数 | 意味 |
|---|---|
| `"files"` | 取り出すキー名 |
| `[]` | キーが存在しなかった場合のデフォルト値。`[]`（空リスト）を返すことでその後の `for` 文がエラーにならない |

`results["files"]` と書いても同じだが、キーがない場合に `KeyError` が発生するリスクがある。`.get()` を使うとデフォルト値で安全に処理できる。

**レスポンス辞書に含まれる主なキー：**

| キー名 | 意味 | 常に存在するか |
|---|---|---|
| `files` | ファイルのリスト | 常にある（空の場合もある） |
| `nextPageToken` | 次ページ取得用トークン | 次ページがある時だけ |
| `kind` | 常に `"drive#fileList"` という文字列 | 常にある |
| `incompleteSearch` | 検索結果が不完全な場合に `True` | 稀にある |

---

## PDFダウンロード処理

### `service.files().get_media(fileId=f["id"])`

指定したファイルIDのファイル内容（バイト列）を取得するリクエストを作成するメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `fileId` | str | ダウンロードするファイルのID。`files().list()` で取得した `id` を使う |

**注意：** このメソッドはリクエストを作成するだけで、この時点ではまだダウンロードが始まっていない。実際のダウンロードは `downloader.next_chunk()` を呼ぶときに発生する。

---

### `io.BytesIO()`

Pythonの標準ライブラリ `io` が提供するメモリ上のバッファ（一時的な書き込み先）。

通常のファイル書き込みはディスクに書くが、`BytesIO` はメモリ上に書く。ダウンロードしたバイト列をいったんここに貯めてから、まとめてディスクに書き出す。

```
Driveのサーバー
    ↓ チャンク単位で転送
io.BytesIO（メモリ上のバッファ）
    ↓ getvalue() でまとめて取り出す
receipts/unprocessed/xxx.pdf（ディスク上のファイル）
```

C#の `MemoryStream` と同じ役割。

---

### `MediaIoBaseDownload(buffer, request)` と `downloader.next_chunk()`

```python
downloader = MediaIoBaseDownload(buffer, request)
done = False
while not done:
    _, done = downloader.next_chunk()
```

`MediaIoBaseDownload` は「バッファにチャンク単位で書き込む」役割を持つオブジェクト。

`next_chunk()` は1チャンク分をダウンロードしてバッファに書き込み、`(進捗情報, 完了フラグ)` のタプルを返す。`done` が `True` になるまでループして全体をダウンロードする。

`_` はPythonの慣習で「使わない変数」を意味する。今回は進捗情報（`MediaDownloadProgress` オブジェクト）を使わないため `_` で受け取って捨てている。

---

### `open(save_path, "wb")` でのファイル保存

```python
with open(save_path, "wb") as out:
    out.write(buffer.getvalue())
```

| 引数 | 意味 |
|---|---|
| `save_path` | 保存先のパス（`receipts/unprocessed/ファイル名`） |
| `"wb"` | バイナリ書き込みモード（write binary）。PDFなどのバイナリファイルを保存するときに使う |

`"w"` はテキストモードで、文字コード変換が入るためバイナリファイルが壊れる。PDFや画像を保存するときは必ず `"wb"` を使う。

`buffer.getvalue()` はバッファに溜めたバイト列全体を取り出すメソッド。

---

### `os.path.join(BASE_DIR, "receipts", "unprocessed", f["name"])`

OSに合わせたファイルパスを組み立てる関数。Mac/Linuxでは `/` で、Windowsでは `\` で区切られたパスを返す。

`BASE_DIR` を先頭に渡すことで、スクリプト・exe・タスクスケジューラのどこから実行しても正しい保存先が組み立てられる。文字列結合でも書けるが `os.path.join` を使うと移植性が高まる。
