"""Windows .exe ビルドスクリプト

【なぜこのスクリプトが必要か】
paddlex は起動時に importlib.metadata を使って依存パッケージの「登録証（.dist-info）」を確認する。
  例: importlib.metadata.version("opencv-contrib-python") → インストール済みかどうか調べる

PyInstaller はデフォルトでコードファイル（.py）しか梱包しない。
.dist-info（登録証フォルダ）は梱包されないため、.exe 内で上記の確認が失敗する → DependencyError

このスクリプトは：
  1. インストール済みパッケージを確認して --copy-metadata フラグを自動生成する
  2. pyinstaller を実行して .exe を作成する
"""

# subprocess: Python スクリプトの中から別のコマンド（pyinstaller 等）を実行するための標準ライブラリ
#             Pythonでいう「シェルコマンドを呼び出す窓口」
import subprocess

# sys: 今動いている Python インタープリター自体の情報を取得するための標準ライブラリ
#      sys.executable → 現在の Python のパス（例: C:/venv/Scripts/python.exe）
import sys

# importlib.metadata: pip でインストールしたパッケージの登録証（.dist-info）を読むための標準ライブラリ
#                     importlib.metadata.version("requests") → "2.31.0" のようにバージョンを返す
#                     インストールされていない場合は PackageNotFoundError を送出する
import importlib.metadata


# ─── 対象パッケージ一覧 ──────────────────────────────────────────────────────

# paddlex が importlib.metadata で登録証を確認するパッケージの一覧
# （paddlex[ocr] の依存パッケージ + paddleocr・paddlex 本体）
# GitHub Actions の Runner にインストールされていないパッケージは後続の try/except で自動スキップする
TARGET_PACKAGES = [
    "paddleocr", "paddlex",          # OCR メイン・マネージャー
    "einops",                        # テンソル演算ユーティリティ
    "ftfy",                          # テキスト修復
    "imagesize",                     # 画像サイズ取得
    "jinja2",                        # テンプレートエンジン
    "lxml",                          # XML/HTML パーサー
    "opencv-contrib-python",         # 画像処理（OpenCV）
    "openpyxl",                      # Excel 操作
    "pyclipper",                     # ポリゴンクリッピング
    "pypdfium2",                     # PDF 処理
    "regex",                         # 高機能正規表現
    "scikit-learn",                  # 機械学習ユーティリティ
    "scipy",                         # 科学計算
    "sentencepiece",                 # テキスト分割
    "shapely",                       # 幾何演算
    "tiktoken",                      # トークナイザー
    "tokenizers",                    # テキストトークナイザー
    "beautifulsoup4",                # HTML パーサー
    "safetensors",                   # モデルウェイト形式
    "premailer",                     # CSS インライン化
    "python-bidi",                   # 双方向テキスト処理
    "latex2mathml",                  # LaTeX → MathML 変換
]


# ─── --copy-metadata フラグの自動生成 ────────────────────────────────────────

# copy_flags: pyinstaller コマンドに渡す --copy-metadata フラグのリスト
# 例: ["--copy-metadata", "paddleocr", "--copy-metadata", "paddlex", ...]
copy_flags = []

for pkg in TARGET_PACKAGES:
    # try/except: Python の例外処理。C# の try/catch と同じ
    try:
        # importlib.metadata.version(pkg): pkg の登録証を探してバージョン文字列を返す
        # インストール済みなら成功（バージョン文字列が返る）
        # インストールされていなければ PackageNotFoundError が発生して except に飛ぶ
        importlib.metadata.version(pkg)

        # extend: リストに複数要素を追加する（append は1要素だけ追加）
        # "--copy-metadata" と pkg を1セットとして copy_flags に追加する
        copy_flags.extend(["--copy-metadata", pkg])

    except importlib.metadata.PackageNotFoundError:
        # インストールされていないパッケージは無視してループを続ける
        # pass: 何もしないという明示的な指示（C# の空ブロック {} に相当）
        pass


# ─── pyinstaller コマンドの組み立て ─────────────────────────────────────────

# cmd: subprocess.run に渡すコマンドのリスト。スペース区切りの文字列を1要素ずつ分割したもの
# 例: ["python", "-m", "PyInstaller", "--onefile", ...]
# リスト形式にすることで、スペースを含むパスが正しく1つの引数として扱われる
cmd = [
    sys.executable,     # 現在動いている Python インタープリターのフルパス
                        # pyinstaller と直接書くと別の環境のものが使われる可能性があるため
    "-m", "PyInstaller", # python -m PyInstaller: Python モジュールとして PyInstaller を実行

    "--onefile",        # すべての依存ファイルを1つの .exe に梱包する（フォルダ方式にしない）
    "--name", "ReceiptFlow",  # 出力ファイル名（ReceiptFlow.exe になる）

    "--collect-all", "paddleocr",
    # --collect-all: 指定パッケージの Python ファイル・バイナリ・データファイルをすべて梱包する
    # paddleocr は OCR モジュールを動的に読み込む設計のため、
    # 静的解析（import 文のスキャン）では検出できないモジュールが発生する
    # --collect-data（データのみ）では不足するため --collect-all が必要

    "--collect-all", "paddlex",
    # paddleocr 同様、OCR 用モジュールを動的にロードするため --collect-all が必要

] + copy_flags + [
    # + copy_flags: 上で自動生成した --copy-metadata フラグ群をここに展開する
    # + []: リスト同士の結合（Python では + でリストをつなげられる）

    "pipeline.py",      # エントリーポイント: .exe 起動時に最初に実行されるファイル
]


# ─── 実行 ────────────────────────────────────────────────────────────────────

# 実行するコマンドをログとして出力しておく（デバッグ・確認用）
# " ".join(cmd): リストの要素をスペースで結合して1つの文字列にする
print("実行コマンド:", " ".join(cmd))

# subprocess.run: cmd に指定したコマンドを子プロセスとして実行する
# check=True: コマンドが失敗（終了コード != 0）したときに例外を発生させる
#             これにより pyinstaller が失敗したら GitHub Actions のステップも失敗扱いになる
subprocess.run(cmd, check=True)
