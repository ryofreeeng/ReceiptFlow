# PDFを画像に変換するライブラリ。パッケージ名はPyMuPDFだがimport名はfitz
import fitz
# 画像データを数値配列として扱うライブラリ。PyMuPDFの出力をOCRエンジンが読める形式に変換するために使う
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

# --- OCRエンジンの選択 ---
# この1行を変えるだけでエンジンを切り替えられる
# "easyocr"  : EasyOCR（日英対応・ローカル実行）
# "paddleocr": PaddleOCR（日英対応・ローカル実行・EasyOCRより精度が高い傾向）
# "manga-ocr": manga-ocr（日本語特化・実装済み）
#              ※検証済み：領収証全体を1つのテキストブロックとして読むため怪文書レベルの結果になった
#              　漫画の吹き出し1コマ分を想定したモデルのため全ページ入力には不向き
# "tesseract": 今後対応予定
OCR_ENGINE = "paddleocr"

# PDFを画像に変換するときの拡大倍率。値が大きいほど高解像度になりOCR精度が上がるが処理が遅くなる
# PaddleOCRは内部で前処理を行うため、EasyOCR時の8.0より低い値で十分。4.0以上にすると max_side_limit(4000px) を超える
ZOOM = 2.0

# Trueにするとページ画像とOCRテキストをセッションフォルダに保存する。精度確認が終わったらFalseにする
SAVE_DEBUG = True

# --- 前処理フラグ（Trueで有効・Falseで無効。1つずつ試して効果を確認する） ---
# ①グレースケール変換：カラー→白黒にして文字と背景の境界を単純化する
PREPROCESS_GRAYSCALE = False
# ②2値化：各ピクセルを完全な黒か白の二択に変換する。グレースケール済みの画像に適用する
#   BINARIZE_THRESHOLDの値以下のピクセル（暗い部分＝文字）を黒（0）、それより明るい部分を白（255）にする
#   値を大きくするほどかすれた文字も黒になる（0〜255。小さいほど厳しく、大きいほど緩い）
PREPROCESS_BINARIZE = False
BINARIZE_THRESHOLD = 240
# ③ノイズ除去：2値化で生じた小さなゴミ点（孤立した黒ピクセル）を取り除く
#   medianBlur：注目ピクセルの周辺DENOISE_KERNEL×DENOISE_KERNEL個の値の中央値で置き換える
#   孤立したゴミ点は周辺が白（255）に囲まれているため中央値が255になり消える
#   値は奇数のみ有効（3・5・7）。大きいほど効果が強いが文字も削れてくる
PREPROCESS_DENOISE = False
DENOISE_KERNEL = 7
# ④収縮（cv2.erode）：黒領域（文字）を広げて細い文字を太くする
#   名前が「収縮」なのは「白背景を収縮させる＝黒文字が広がる」という意味
#   ※「膨張」と呼ぶ場合もあるが、OpenCVのcv2.erode()を使う点に注意
#     cv2.dilate()は白を広げる（文字が細くなる）ためここでは使わない
#   ERODE_KERNELはカーネルサイズ（N×Nの正方形で広がる範囲を決める）
PREPROCESS_ERODE = False
ERODE_KERNEL = 2

# --- 後処理フラグ ---
# Trueにすると、同じ行と判定した検出領域のテキストをスペースで連結して出力する
# PaddleOCR使用時のみ有効（座標情報を持つエンジンが必要）
POSTPROCESS_MERGE_LINES = True
# 行判定の閾値。検出ボックスの平均高さに対する割合で指定する
# 0.5 = 平均高さの半分以内のY距離なら同じ行とみなす。値を上げると判定が緩くなる
MERGE_LINE_THRESHOLD = 0.5

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
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    if PREPROCESS_BINARIZE:
        # グレースケール画像の各ピクセルを「完全な黒（0）」か「完全な白（255）」の二択に変換する
        # BINARIZE_THRESHOLD以下のピクセル（暗い部分＝文字）→黒（0）
        # BINARIZE_THRESHOLDより明るいピクセル（背景）→白（255）
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


def merge_lines_by_coord(texts, polys):
    """座標情報をもとに同じ行と判定したテキストを連結して返す。
    各検出領域のY中心を計算し、MERGE_LINE_THRESHOLD以内のものを同じ行としてまとめる。
    同じ行の中ではX左端でソートしてスペースで連結する。
    戻り値は行ごとのテキスト文字列のリスト。"""
    if not texts or not polys:
        return texts

    # ① 各検出領域のY中心・Y高さ・X左端を計算してテキストとまとめる
    regions = []
    for text, poly in zip(texts, polys):
        ys = [p[1] for p in poly]
        xs = [p[0] for p in poly]
        y_center = (min(ys) + max(ys)) / 2
        y_height = max(ys) - min(ys)
        x_left = min(xs)
        regions.append((y_center, y_height, x_left, text))

    # ② 閾値を算出する（全ボックスの平均高さ × MERGE_LINE_THRESHOLD）
    avg_height = sum(r[1] for r in regions) / len(regions)
    threshold = avg_height * MERGE_LINE_THRESHOLD

    # ③ Y中心でソートして行グループに振り分ける
    regions.sort(key=lambda r: r[0])
    line_groups = []   # 各要素は [(x_left, text), ...] のリスト
    for y_center, _, x_left, text in regions:
        if line_groups and abs(y_center - line_groups[-1][0]) <= threshold:
            # 直前のグループのY中心と比較して閾値内なら同じ行に追加
            line_groups[-1][1].append((x_left, text))
        else:
            # 新しい行グループを開始する。先頭にY中心代表値を保持する
            line_groups.append([y_center, [(x_left, text)]])

    # ④ 各グループをX順にソートしてスペースで連結する
    merged = []
    for _, items in line_groups:
        items.sort(key=lambda r: r[0])
        merged.append(" ".join(text for _, text in items))

    return merged


def init_reader():
    """OCR_ENGINEの設定に応じてOCRエンジンを初期化して返す。
    新しいエンジンを追加するときはここにelifブロックを1つ足す。"""
    if OCR_ENGINE == "easyocr":
        import easyocr
        print("EasyOCRを初期化中...")
        # 初回実行時はモデルファイルをダウンロードするため数分かかる
        return easyocr.Reader(['ja', 'en'])
    elif OCR_ENGINE == "paddleocr":
        from paddleocr import PaddleOCR
        print("PaddleOCRを初期化中...")
        # use_textline_orientation=True：テキスト行の向き（0°/180°）を検出する
        # ※旧パラメータ use_angle_cls は非推奨になったため use_textline_orientation を使う
        # lang='japan'：日本語モデルを使う（初回実行時にモデルをダウンロードする）
        return PaddleOCR(use_textline_orientation=True, lang='japan')
    elif OCR_ENGINE == "manga-ocr":
        from manga_ocr import MangaOcr
        print("manga-ocrを初期化中...")
        # 初回実行時はモデルファイルをダウンロードするため数分かかる
        return MangaOcr()
    else:
        raise ValueError(f"未対応のOCRエンジン: {OCR_ENGINE!r}。'easyocr' / 'paddleocr' / 'manga-ocr' を指定してください")


def run_ocr(reader, img):
    """OCR_ENGINEの設定に応じて画像からテキスト文字列のリストと信頼度情報を返す。
    新しいエンジンを追加するときはここにelifブロックを1つ足す。
    戻り値: (texts, debug_pairs) のタプル。
    - texts      : 最終的なテキストリスト（PaddleOCRで行マージ有効な場合はマージ済み）
    - debug_pairs: [(テキスト, 信頼度), ...] の生検出データ。信頼度を持たないエンジンはNone"""
    if OCR_ENGINE == "easyocr":
        # readtext()の戻り値は [(座標, テキスト, 信頼度), ...] のリスト
        results = reader.readtext(img)
        texts = [r[1] for r in results]
        debug_pairs = [(r[1], r[2]) for r in results]
        return texts, debug_pairs
    elif OCR_ENGINE == "paddleocr":
        # PaddleOCRはBGR形式のnumpy配列を期待する。グレースケール（2次元）の場合はBGRに変換する
        ocr_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img
        # predict()はジェネレータを返す。list()で消費して全結果を取得する
        # 旧API: reader.ocr(img, cls=True) → 新API: reader.predict(img)
        # （向き検出は初期化時の use_textline_orientation=True で制御するため cls 引数は不要）
        results = list(reader.predict(ocr_img))
        if not results:
            return [], None
        # predict()の戻り値は辞書のリスト。rec_texts キーにテキスト文字列のリストが入っている
        # その他のキー：rec_scores（信頼度）、dt_polys（検出座標）、rec_polys など
        raw_texts = results[0].get('rec_texts', [])
        scores    = results[0].get('rec_scores', [])
        polys     = results[0].get('dt_polys', [])
        # 行マージ前の生検出データを保持する（マージ後はテキストとスコアの対応が崩れるため）
        debug_pairs = list(zip(raw_texts, scores)) if scores else None
        if POSTPROCESS_MERGE_LINES and polys:
            # 座標情報をもとに同じ行のテキストを連結する
            return merge_lines_by_coord(raw_texts, polys), debug_pairs
        return raw_texts, debug_pairs
    elif OCR_ENGINE == "manga-ocr":
        from PIL import Image
        # manga-ocrはPIL Imageを期待する。numpy配列（RGB）から変換する
        # グレースケール（2次元配列）の場合はRGBに戻してから変換する
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        pil_img = Image.fromarray(img)
        # reader(image)で画像全体を1つの文字列として返す（テキスト検出は行わない）
        # 戻り値は文字列1つ。run_ocr()の戻り値はリストなのでリストに包む
        result = reader(pil_img)
        return [result], None
    return [], None


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

        # run_ocr()がエンジンの差異を吸収して、テキスト文字列のリストと信頼度ペアを返す
        texts, debug_pairs = run_ocr(reader, img)
        page_text = "\n".join(texts)
        all_text.append(page_text)

        if SAVE_DEBUG:
            # 画像と同じ名前（ステム）でテキストファイルを保存する
            txt_path = os.path.join(session_dir, f"{stem}.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(page_text)
            print(f"  テキストを保存: {txt_path}")

            # 信頼度ファイルを保存する（エンジンが信頼度を返す場合のみ）
            if debug_pairs:
                scores_path = os.path.join(session_dir, f"{stem}_scores.txt")
                with open(scores_path, "w", encoding="utf-8") as f:
                    # PaddleOCRで行マージ有効のとき、スコアはマージ前の生検出データ
                    note = "（行マージ前の生検出データ）" if POSTPROCESS_MERGE_LINES and OCR_ENGINE == "paddleocr" else ""
                    f.write(f"検出領域ごとの信頼度{note}:\n")
                    for j, (text, score) in enumerate(debug_pairs, 1):
                        f.write(f"  {j:3d}: {score:.3f} - {text}\n")
                    avg = sum(s for _, s in debug_pairs) / len(debug_pairs)
                    f.write(f"\n平均信頼度: {avg:.3f}\n")
                print(f"  信頼度を保存: {scores_path}")

    return "\n\n".join(all_text)


def main():
    # OCR_ENGINEの設定に応じたエンジンを初期化する
    reader = init_reader()

    # SAVE_DEBUG=True のとき、実行ごとに「エンジン名_zoom値_日時」のフォルダを作成する
    # エンジン名も含めることで、EasyOCRとPaddleOCRの結果を並べて比較できる
    if SAVE_DEBUG:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(DEBUG_DIR, f"{OCR_ENGINE}_zoom{ZOOM}_{timestamp}")
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
