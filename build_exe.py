"""バイナリビルドスクリプト（Windows .exe / Mac Unix バイナリ 共通）

【なぜこのスクリプトが必要か】
paddlex は起動時に importlib.metadata を使って依存パッケージの「登録証（.dist-info）」を確認する。
  例: importlib.metadata.version("opencv-contrib-python") → インストール済みかどうか調べる

PyInstaller はデフォルトでコードファイル（.py）しか梱包しない。
.dist-info（登録証フォルダ）は梱包されないため、バイナリ内で上記の確認が失敗する → DependencyError

このスクリプトは：
  1. インストール済みパッケージを確認して --copy-metadata フラグを自動生成する
  2. paddle/libs のライブラリフォルダを自動検出して --add-binary フラグを生成する
     （Windows: mklml.dll 等の DLL / Mac: liblapack.dylib 等の dylib）
  3. pyinstaller を実行してバイナリを作成する
     （Windows: dist/ReceiptFlow.exe / Mac: dist/ReceiptFlow）

os.pathsep を使っているため Windows（区切り ";"）・Mac（区切り ":"）どちらでも動く。
"""

# os: ファイルパスの操作・存在確認などに使う標準ライブラリ
#     os.path.join("a", "b") → "a/b"（OS に合わせたパス区切りで結合）
#     os.path.exists(path) → パスが存在するか True/False で返す
import os

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


# ─── --add-binary フラグの生成（paddle/libs の DLL）────────────────────────

# PaddlePaddle は実行時に paddle/libs/ 内の DLL（mklml.dll 等）を
# C言語レベルで動的にロードする。Python の import 文を使わないため
# PyInstaller の静的スキャンでは絶対に検出できない。
# --add-binary でこのフォルダごと明示的に梱包する必要がある。

import paddle  # paddle パッケージのインストール場所を特定するために import する

# os.path.dirname(paddle.__file__):
#   paddle.__file__ → paddle パッケージの __init__.py のフルパス
#                     例: C:/venv/Lib/site-packages/paddle/__init__.py
#   os.path.dirname(...) → そのファイルが入っているフォルダのパス
#                     例: C:/venv/Lib/site-packages/paddle/
# os.path.join(..., "libs") → paddle/libs フォルダのパスを作る
paddle_libs_dir = os.path.join(os.path.dirname(paddle.__file__), "libs")

binary_flags = []
if os.path.exists(paddle_libs_dir):
    # --add-binary の書式: "元のパス{区切り}配置先"
    # os.pathsep: OS に合わせた区切り文字（Windows では ";" / Mac・Linux では ":"）
    #             PyInstaller は「元のパス;配置先」の形式でバイナリの梱包先を指定する
    # "." は .exe 展開時のルートディレクトリに配置することを意味する
    #   → DLL がルートに置かれるため OS から参照できるようになる
    binary_flags.extend(["--add-binary", f"{paddle_libs_dir}{os.pathsep}."])
    print(f"Found paddle/libs: {paddle_libs_dir}")
else:
    print("paddle/libs not found, skipping --add-binary")


# ─── pyinstaller コマンドの組み立て ─────────────────────────────────────────

# cmd: subprocess.run に渡すコマンドのリスト。スペース区切りの文字列を1要素ずつ分割したもの
# 例: ["python", "-m", "PyInstaller", "--onefile", ...]
# リスト形式にすることで、スペースを含むパスが正しく1つの引数として扱われる
cmd = [
    sys.executable,     # 現在動いている Python インタープリターのフルパス
                        # pyinstaller と直接書くと別の環境のものが使われる可能性があるため
    "-m", "PyInstaller", # python -m PyInstaller: Python モジュールとして PyInstaller を実行

    "--onefile",        # すべての依存ファイルを1つのバイナリに梱包する（フォルダ方式にしない）
    "--name", "ReceiptFlow",  # 出力ファイル名（Windows: ReceiptFlow.exe / Mac: ReceiptFlow）

    "--collect-all", "paddleocr",
    # --collect-all: 指定パッケージの Python ファイル・バイナリ・データファイルをすべて梱包する
    # paddleocr は OCR モジュールを動的に読み込む設計のため、
    # 静的解析（import 文のスキャン）では検出できないモジュールが発生する
    # --collect-data（データのみ）では不足するため --collect-all が必要

    "--collect-all", "paddlex",
    # paddleocr 同様、OCR 用モジュールを動的にロードするため --collect-all が必要

    "--hidden-import", "scipy._cyutility",
    # --hidden-import: import 文が文字列・変数で書かれているため静的スキャンで検出できない
    #                  モジュールを明示的に梱包する指定
    # scipy._cyutility は paddlex が実行時に動的にロードする内部モジュール

] + copy_flags + binary_flags + [
    # + copy_flags:   上で自動生成した --copy-metadata フラグ群（登録証フォルダの梱包）
    # + binary_flags: 上で生成した --add-binary フラグ（paddle/libs DLL の梱包）
    # + []:           リスト同士の結合（Python では + でリストをつなげられる）

    "pipeline.py",      # エントリーポイント: .exe 起動時に最初に実行されるファイル
]


# ─── 実行 ────────────────────────────────────────────────────────────────────

# 実行するコマンドをログとして出力しておく（GitHub Actions のログで確認できる）
# " ".join(cmd): リストの要素をスペースで結合して1つの文字列にする
print("Running command:", " ".join(cmd))

# subprocess.run: cmd に指定したコマンドを子プロセスとして実行する
# check=True: コマンドが失敗（終了コード != 0）したときに例外を発生させる
#             これにより pyinstaller が失敗したら GitHub Actions のステップも失敗扱いになる
subprocess.run(cmd, check=True)
