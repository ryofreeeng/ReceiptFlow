# ReceiptFlow.exe 使い方ガイド

## 必要なもの

| ファイル | 取得方法 |
|---|---|
| `ReceiptFlow.exe` | GitHub Releases からダウンロード |
| `credentials.json` | Google Cloud Console で発行（下記参照） |
| `.env` | 自分で作成（下記参照） |
| `config.toml` | GitHub リポジトリからダウンロード |

---

## Step 0：フォルダ構成を作る

**`.exe` と同じフォルダに以下のファイルを置く。** パスが合っていないと起動しても処理に失敗する。

```
任意のフォルダ/
├── ReceiptFlow.exe     ← ダウンロードした exe
├── credentials.json   ← Google Cloud Console から取得したもの
├── .env               ← 自分で作成する（下記参照）
├── config.toml        ← リポジトリからダウンロードしたもの
└── receipts/
    └── unprocessed/   ← Adobe Scan の PDF をここに置く（フォルダは起動時に自動生成）
```

`output/`・`logs/`・`receipts/intermediate/` 等のフォルダは初回起動時に自動で作成される。

---

## Step 1：credentials.json を用意する

初回のみ必要。Google Drive APIへの接続に使う認証ファイル。

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセスしてログイン
2. プロジェクトを作成（例：`ReceiptFlow`）
3. 「APIとサービス」→「ライブラリ」→「Google Drive API」を有効化
4. 「APIとサービス」→「OAuth同意画面」を設定（User Type：外部、テストユーザーに自分のメールを追加）
5. 「APIとサービス」→「認証情報」→「OAuthクライアントID」を作成（種類：デスクトップアプリ）
6. JSON をダウンロードして `credentials.json` にリネームし、`.exe` と同じフォルダに置く

---

## Step 2：.env ファイルを作る

Google Drive の各フォルダIDを設定するファイル。テキストエディタで作成する。

```
# Drive の unprocessed フォルダID（PDFのダウンロード元）
UNPROCESSED_FOLDER_ID=（DriveのURLの末尾ID）

# Drive の processed フォルダID（処理済みPDFの移動先）
PROCESSED_FOLDER_ID=（DriveのURLの末尾ID）

# Drive の renamed フォルダID（日付リネーム済みPDFのアップロード先）
RENAMED_FOLDER_ID=（DriveのURLの末尾ID）
```

フォルダIDはGoogleドライブでフォルダを開いたときのURLの末尾：
```
https://drive.google.com/drive/folders/★ここがID★
```

Driveにあらかじめ `unprocessed`・`processed`・`renamed` の3フォルダを作成してIDを取得する。

---

## Step 3：ReceiptFlow.exe を実行する

`.exe` をダブルクリックするとコマンドウィンドウが開く。

### 初回実行時

1. ブラウザが自動で起動する
2. Googleアカウントでログインして「許可」をクリック
3. ブラウザに「認証完了」と表示されたら閉じる
4. `token.json` が自動生成され、次回以降はブラウザが開かなくなる

> `このアプリはGoogleによって確認されていません` と表示されたら「詳細」→「（アプリ名）に移動」をクリックして進む。

### モード選択

起動すると以下の選択画面が表示される：

```
実行するパターンを選択してください：
  1: 全処理（ダウンロード → OCR → 抽出・Excel出力）
  2: ダウンロード ＋ OCR
  3: OCR ＋ 抽出・Excel出力
  4: ダウンロードのみ
  5: OCR のみ
  6: 抽出・Excel出力のみ

番号を入力（1〜6）:
```

| モード | 用途 |
|---|---|
| 1 | 通常の全処理（Drive からダウンロードして最後まで一気に実行） |
| 3 | PDF を手動で `receipts/unprocessed/` に置いてある場合（Drive 不使用） |
| 6 | OCR 済みテキストから Excel 出力だけやり直したい場合 |

### 出力結果

- **Excel ファイル** → `output/対面領収証の帳簿_yyyymmdd-HHmmss記帳.xlsx`
- **リネーム済み PDF** → `receipts/renamed/YYYY-MM-DD_対面領収書.pdf`
- **Drive の renamed フォルダ** → リネーム済み PDF がアップロードされる

### 終了方法

処理完了後に `Enterキーを押して終了してください...` と表示されるので、Enter を押すとウィンドウが閉じる。

---

## OCR 初回実行時の注意

PaddleOCR の認識モデルを初回のみダウンロードする（数百MB、数分〜十数分かかる）。

```
PaddleOCRを初期化中...
Creating model: ('PP-OCRv5_server_det', None, None)
...
```

と表示されたまましばらく待つ。2回目以降は高速に起動する。

以下の警告は**無視して問題ない**：

```
UserWarning: No ccache found.
```
