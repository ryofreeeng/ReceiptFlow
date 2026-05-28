# PDFを画像に変換するライブラリ。パッケージ名はPyMuPDFだがimport名はfitz
import fitz
# 画像から文字を認識するOCRライブラリ
import easyocr
# 画像データを数値配列として扱うライブラリ。PyMuPDFの出力をEasyOCRが読める形式に変換するために使う
import numpy as np
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
ZOOM = 4.0

# Trueにするとページ画像とOCRテキストをセッションフォルダに保存する。精度確認が終わったらFalseにする
SAVE_DEBUG = True


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
