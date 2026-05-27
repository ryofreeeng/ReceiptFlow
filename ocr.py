# PDFを画像に変換するライブラリ。パッケージ名はPyMuPDFだがimport名はfitz
import fitz
# 画像から文字を認識するOCRライブラリ
import easyocr
# 画像データを数値配列として扱うライブラリ。PyMuPDFの出力をEasyOCRが読める形式に変換するために使う
import numpy as np
import os
import sys

# スクリプト・exe どちらの実行方法でも正しいプロジェクトルートを取得する
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# OCR対象のPDFが置かれているフォルダ
UNPROCESSED_DIR = os.path.join(BASE_DIR, "receipts", "unprocessed")

# PDFを画像に変換するときの拡大倍率。値が大きいほど高解像度になりOCR精度が上がるが処理が遅くなる
ZOOM = 2.0


def pdf_to_images(pdf_path):
    """PDFの各ページをnumpy配列の画像リストに変換して返す"""
    doc = fitz.open(pdf_path)
    images = []

    # fitz.Matrixは画像の変換行列。(ZOOM, ZOOM)で縦横それぞれZOOM倍に拡大する
    mat = fitz.Matrix(ZOOM, ZOOM)

    for page in doc:
        # get_pixmap()でページをピクセルデータ（RGB）に変換する
        pix = page.get_pixmap(matrix=mat)

        # pix.samplesはRGBのバイト列。numpy配列に変換して(高さ, 幅, チャンネル数)の形にする
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        images.append(img)

    doc.close()
    return images


def extract_text_from_images(images, reader):
    """画像リストを受け取り、全ページのOCR結果テキストを結合して返す"""
    all_text = []

    for i, img in enumerate(images):
        print(f"  ページ {i + 1} をOCR中...")

        # reader.readtext()は画像を受け取り、認識した文字のリストを返す
        # 各要素は (座標, テキスト, 信頼度) のタプル
        results = reader.readtext(img)

        # テキスト部分（インデックス1）だけを取り出して結合する
        page_text = "\n".join([result[1] for result in results])
        all_text.append(page_text)

    return "\n\n".join(all_text)


def main():
    # EasyOCRのReaderを初期化する。日本語('ja')と英語('en')を指定
    # 初回実行時はモデルファイルをダウンロードするため数分かかる
    print("EasyOCRを初期化中...")
    reader = easyocr.Reader(['ja', 'en'])

    # unprocessedフォルダ内のPDFファイルを一覧取得する
    pdf_files = [f for f in os.listdir(UNPROCESSED_DIR) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print("unprocessedフォルダにPDFが見つかりませんでした。")
        return

    print(f"\n{len(pdf_files)}件のPDFを処理します...\n")

    for filename in pdf_files:
        pdf_path = os.path.join(UNPROCESSED_DIR, filename)
        print(f"処理中: {filename}")

        # PDFの各ページを画像に変換する
        images = pdf_to_images(pdf_path)
        print(f"  {len(images)}ページを画像に変換しました")

        # 全ページのテキストを抽出する
        text = extract_text_from_images(images, reader)

        print(f"\n--- {filename} の抽出テキスト ---")
        print(text)
        print("-" * 40 + "\n")


if __name__ == "__main__":
    main()
