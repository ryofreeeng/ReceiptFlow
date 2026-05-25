# test_drive_connection.py 解説ガイド

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

`creds = flow.run_local_server(port=0)` の1行の中で以下がすべて順番に起きている。呼び出し側から見ると「1行書いたらトークンが返ってくる」だけで、内部の流れは以下：

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

### `service.files().list(pageSize=10, fields="files(id, name, mimeType)")`

Driveのファイル一覧を取得するAPIメソッド。

| 引数 | 型 | 意味 |
|---|---|---|
| `pageSize` | int | 一度に取得するファイルの最大件数。最大値は1000 |
| `fields` | str | レスポンスに含めるフィールドを絞る指定。省略するとすべての情報が返ってきて通信量が増える |

**Q. `mimeType` とは何か？他に指定できるフィールドは？**

`mimeType` はファイルの種類を表す文字列。拡張子と似た役割だが、より正確な分類ができる。

| mimeType の値 | 意味 |
|---|---|
| `application/pdf` | PDF |
| `image/jpeg` | JPEG画像 |
| `application/vnd.google-apps.folder` | Driveのフォルダ |
| `application/vnd.google-apps.spreadsheet` | Googleスプレッドシート |

今後PDFだけを対象にフィルタリングするときに使う：
```python
q="mimeType='application/pdf'"
```

他に指定できる主なフィールド：

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

追加例：`fields="files(id, name, mimeType, createdTime)"` のようにカンマで追加する。

---

### pageSize=10 の理由と、件数が多い場合の対処

現在 `pageSize=10` にしているのは**接続テスト用のため**。一覧が取れれば十分なので最小限にしている。

**実際に全件取得したい場合：** Drive APIはページネーション（分割取得）方式を採用している。一度に1000件が上限なので、それ以上ある場合は `nextPageToken` を使って繰り返し取得する必要がある。

```python
# 全件取得する場合の書き方（参考）
all_files = []
page_token = None

while True:
    results = service.files().list(
        pageSize=1000,
        fields="nextPageToken, files(id, name, mimeType)",
        pageToken=page_token
    ).execute()
    all_files.extend(results.get("files", []))
    page_token = results.get("nextPageToken")
    if not page_token:  # 次のページがなくなったら終了
        break
```

本番の処理では特定フォルダ内のPDFだけを対象にするため、件数が問題になることはほぼない。

---

### `results.get("files", [])`

辞書から値を取り出すPythonの組み込みメソッド。

| 引数 | 意味 |
|---|---|
| `"files"` | 取り出すキー名 |
| `[]` | キーが存在しなかった場合のデフォルト値。`[]`（空リスト）を返すことでその後の `for` 文がエラーにならない |

`results["files"]` と書いても同じだが、キーがない場合に `KeyError` が発生するリスクがある。`.get()` を使うとデフォルト値で安全に処理できる。

**Q. レスポンスに含まれる他のキー名は？**

`results` の辞書には最大4つのキーが含まれる：

| キー名 | 意味 | 常に存在するか |
|---|---|---|
| `files` | ファイルのリスト | 常にある（空の場合もある） |
| `nextPageToken` | 次ページ取得用トークン | 次ページがある時だけ |
| `kind` | 常に `"drive#fileList"` という文字列 | 常にある |
| `incompleteSearch` | 検索結果が不完全な場合に `True` | 稀にある |

実用上で使うのは `files` と `nextPageToken` の2つ。`nextPageToken` が存在する場合は全件取得できていないので、上記のページネーション処理が必要になる。
