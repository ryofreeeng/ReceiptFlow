# PDFを画像に変換するライブラリ。パッケージ名はPyMuPDFだがimport名はfitz
import fitz
# 画像から文字を認識するOCRライブラリ
import easyocr
# 画像データを数値配列として扱うライブラリ。PyMuPDFの出力をEasyOCRが読める形式に変換するために使う
import numpy as np
# 画像前処理ライブラリ（グレースケール変換・2値化・コントラスト強調・ノイズ除去に使う）
import cv2
import os
import sys
import datetime

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# OCR対象のPDFが置かれているフォルダ
UNPROCESSED_DIR = os.path.join(BASE_DIR, "receipts", "unprocessed")

# デバッグ出力の親フォルダ。実行ごとにこの下にサブフォルダが作られる
DEBUG_DIR = os.path.join(BASE_DIR, "receipts", "debug")

# PDFを画像に変換するときの拡大倍率。値が大きいほど高解像度になりOCR精度が上がるが処理が遅くなる
# 2.0→3.0→4.0 と上げながらOCR結果と画像を目視で比較して最適値を探す
ZOOM = 8.0

# Trueにするとページ画像とOCRテキストをセッションフォルダに保存する。精度確認が終わったらFalseにする
SAVE_DEBUG = True

# --- 前処理フラグ（Trueで有効・Falseで無効。1つずつ試して効果を確認する） ---
# ①グレースケール変換：カラー→白黒にして文字と背景の境界を単純化する
PREPROCESS_GRAYSCALE = True
# ②2値化：各ピクセルを完全な黒か白の二択に変換する。グレースケール済みの画像に適用する
#   BINARIZE_THRESHOLDの値以下のピクセル（暗い部分＝文字）を黒（0）、それより明るい部分を白（255）にする
#   値を大きくするほどかすれた文字も黒になる（0〜255。小さいほど厳しく、大きいほど緩い）
PREPROCESS_BINARIZE = True
BINARIZE_THRESHOLD = 250
# ③ノイズ除去：2値化で生じた小さなゴミ点（孤立した黒ピクセル）を取り除く
#   medianBlur：注目ピクセルの周辺DENOISE_KERNEL×DENOISE_KERNEL個の値の中央値で置き換える
#   孤立したゴミ点は周辺が白（255）に囲まれているため中央値が255になり消える
#   値は奇数のみ有効（3・5・7）。大きいほど効果が強いが文字も削れてくる
PREPROCESS_DENOISE = True
DENOISE_KERNEL = 7
# ④収縮（cv2.erode）：黒領域（文字）を広げて細い文字を太くする
#   名前が「収縮」なのは「白背景を収縮させる＝黒文字が広がる」という意味
#   ※「膨張」と呼ぶ場合もあるが、OpenCVのcv2.erode()を使う点に注意
#     cv2.dilate()は白を広げる（文字が細くなる）ためここでは使わない
#   ERODE_KERNELはカーネルサイズ（N×Nの正方形で広がる範囲を決める）
PREPROCESS_ERODE = False
ERODE_KERNEL = 2

# --- シャープニング（cv2.filter2D）は使用しない ---
# シャープニングは0〜255のグレースケール値のエッジ勾配を強調する処理。
# 2値化後はピクセルが0か255の二択になっており中間的な勾配が存在しないため
# シャープニングを適用しても効果がない。2値化の前に適用する意義はあるが、
# 今回は2値化で十分な境界明確化ができているため省略する。


def preprocess_image(img):
    """numpy配列（RGB）に前処理を適用して返す。
    各フラグがTrueのとき、その処理を順番に適用する。
    処理を追加するときはここに elif ブロックを足していく。"""
    if PREPROCESS_GRAYSCALE:
        # RGB（3チャンネル）→グレースケール（1チャンネル）に変換する
        # cv2.COLOR_RGB2GRAY：R・G・Bの輝度を人間の目の感度に合わせた比率で合成して1値にする
        # EasyOCRはグレースケール（2次元配列）もRGB（3次元配列）もどちらも受け付ける
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    if PREPROCESS_BINARIZE:
        # グレースケール画像の各ピクセルを「完全な黒（0）」か「完全な白（255）」の二択に変換する
        # BINARIZE_THRESHOLD以下のピクセル（暗い部分＝文字）→黒（0）
        # BINARIZE_THRESHOLDより明るいピクセル（背景）→白（255）
        # 値を上げるほど「薄い文字も黒にする」ようになる。まず180で試して調整する
        if img.ndim != 2:
            # 2値化はグレースケール（2次元配列）にのみ適用できる。RGBのままなら先にグレースケール化する
            img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        img = cv2.threshold(img, BINARIZE_THRESHOLD, 255, cv2.THRESH_BINARY)[1]

    if PREPROCESS_DENOISE:
        # 孤立した小さなゴミ点を除去する
        # medianBlur：対象ピクセルの周辺DENOISE_KERNEL×DENOISE_KERNELの範囲の中央値で置き換える
        # 2値化後の孤立ゴミ点は周囲が白（255）ばかりのため中央値→255（白）になり消える
        # 文字は周囲にも黒ピクセルが連続しているため中央値→0（黒）のまま残る
        img = cv2.medianBlur(img, DENOISE_KERNEL)

    if PREPROCESS_ERODE:
        # 黒領域（文字）を周囲に広げて細い文字を太くする
        # np.ones()でERODE_KERNEL×ERODE_KERNELの全1カーネルを作る
        # cv2.erode()は各ピクセルをカーネル範囲の最小値（黒=0）で置き換える
        # → 黒ピクセルの隣にある白ピクセルが黒になる → 文字が太くなる
        kernel = np.ones((ERODE_KERNEL, ERODE_KERNEL), np.uint8)
        img = cv2.erode(img, kernel, iterations=1)
    return img


def pdf_to_images(pdf_path, session_dir):
    """PDFの各ページをnumpy配列に変換して返す。
    SAVE_DEBUG=True のとき、session_dir に PNG を保存する。
    戻り値は (numpy配列, ファイル名ステム) のタプルのリスト。
    ステムを返すことで、テキスト保存時に画像と同じ名前を使えるようにしている。"""
    doc = fitz.open(pdf_path)
    results = []

    # fitz.Matrixは画像の変換行列。(ZOOM, ZOOM)で縦横それぞれZOOM倍に拡大する
    mat = fitz.Matrix(ZOOM, ZOOM)

    # ファイル名のプレフィックスとしてPDFのファイル名（拡張子なし）を使う
    basename = os.path.splitext(os.path.basename(pdf_path))[0]

    for i, page in enumerate(doc):
        # get_pixmap()でページをピクセルデータ（RGB）に変換する
        pix = page.get_pixmap(matrix=mat)

        # 画像とテキストの両方で使うファイル名ステムを決める（拡張子なし）
        stem = f"{basename}_page{i + 1}_zoom{ZOOM}"

        if SAVE_DEBUG:
            # numpy変換やOCR処理の前に、PyMuPDFが生成した画像をそのままPNGで保存する
            # pix.save()はfitz.Pixmapが持つ保存メソッドで、Pillowなど追加ライブラリ不要
            img_path = os.path.join(session_dir, f"{stem}.png")
            pix.save(img_path)
            print(f"  画像を保存: {img_path}")

        # pix.samplesはRGBのバイト列。numpy配列に変換して(高さ, 幅, チャンネル数)の形にする
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

        # 前処理を適用する。どのフラグが有効かと設定値をステム名に追記して区別できるようにする
        # _gray      ：grayscale（グレースケール変換）の略。設定値なし
        # _bin{値}   ：binarization（2値化）の略。しきい値を末尾に付ける（例：_bin220）
        # _dn{値}    ：denoise（ノイズ除去）の略。カーネルサイズを末尾に付ける（例：_dn3）
        # _er{値}    ：erode（収縮＝黒領域拡張）の略。カーネルサイズを末尾に付ける（例：_er2）
        img = preprocess_image(img)
        if PREPROCESS_GRAYSCALE:
            stem += "_gray"
        if PREPROCESS_BINARIZE:
            stem += f"_bin{BINARIZE_THRESHOLD}"
        if PREPROCESS_DENOISE:
            stem += f"_dn{DENOISE_KERNEL}"
        if PREPROCESS_ERODE:
            stem += f"_er{ERODE_KERNEL}"

        if SAVE_DEBUG:
            # 前処理後の画像を保存する。元画像（pix.save）とは別ファイルになる
            # cv2.imwrite()はグレースケール（2次元配列）もRGB（3次元配列）も保存できる
            cv2.imwrite(os.path.join(session_dir, f"{stem}.png"), img)
            print(f"  前処理後画像を保存: {stem}.png")

        results.append((img, stem))

    doc.close()
    return results


def extract_text_from_images(images_with_stems, reader, session_dir):
    """(numpy配列, ステム) のリストを受け取り、全ページのOCR結果テキストを結合して返す。
    SAVE_DEBUG=True のとき、ページごとのテキストを画像と同じ名前のtxtファイルに保存する。"""
    all_text = []

    for i, (img, stem) in enumerate(images_with_stems):
        print(f"  ページ {i + 1} をOCR中...")

        # reader.readtext()は画像を受け取り、認識した文字のリストを返す
        # 各要素は (座標, テキスト, 信頼度) のタプル
        results = reader.readtext(img)

        # テキスト部分（インデックス1）だけを取り出して結合する
        page_text = "\n".join([result[1] for result in results])
        all_text.append(page_text)

        if SAVE_DEBUG:
            # 画像と同じ名前（ステム）でテキストファイルを保存する
            txt_path = os.path.join(session_dir, f"{stem}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(page_text)
            print(f"  テキストを保存: {txt_path}")

    return "\n\n".join(all_text)


def main():
    # EasyOCRのReaderを初期化する。日本語('ja')と英語('en')を指定
    # 初回実行時はモデルファイルをダウンロードするため数分かかる
    print("EasyOCRを初期化中...")
    reader = easyocr.Reader(['ja', 'en'])

    # SAVE_DEBUG=True のとき、実行ごとに「zoom値_日時」のフォルダを作成する
    # 複数回試したときに上書きされず、倍率や時刻ごとに結果を比較できる
    if SAVE_DEBUG:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(DEBUG_DIR, f"zoom{ZOOM}_{timestamp}")
        os.makedirs(session_dir, exist_ok=True)
        print(f"デバッグ出力先: {session_dir}")
    else:
        session_dir = None

    # unprocessedフォルダ内のPDFファイルを一覧取得する
    pdf_files = [f for f in os.listdir(UNPROCESSED_DIR) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print("unprocessedフォルダにPDFが見つかりませんでした。")
        return

    print(f"\n{len(pdf_files)}件のPDFを処理します...\n")

    for filename in pdf_files:
        pdf_path = os.path.join(UNPROCESSED_DIR, filename)
        print(f"処理中: {filename}")

        # PDFの各ページを画像に変換する。戻り値は (numpy配列, ステム) のリスト
        images_with_stems = pdf_to_images(pdf_path, session_dir)
        print(f"  {len(images_with_stems)}ページを画像に変換しました")

        # 全ページのテキストを抽出する
        text = extract_text_from_images(images_with_stems, reader, session_dir)

        print(f"\n--- {filename} の抽出テキスト ---")
        print(text)
        print("-" * 40 + "\n")


if __name__ == "__main__":
    main()
