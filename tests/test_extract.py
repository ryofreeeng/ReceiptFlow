import sys
import os
# tests/ フォルダの1段上（ReceiptFlow/）を検索パスに追加して extract.py を import できるようにする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extract import extract_date, extract_amount, extract_items, extract_store_name, needs_review


# ─── extract_date ────────────────────────────────────────────────

def test_extract_date_western_kanji():
    """西暦漢字形式（2025年05月26日）を正しく読めるか"""
    text = "〇〇スーパー\n2025年05月26日\n合計 648円"
    assert extract_date(text) == "2025-05-26"

def test_extract_date_slash():
    """スラッシュ形式（2025/05/26）を正しく読めるか"""
    text = "領収証\n2025/05/26\n合計 1000円"
    assert extract_date(text) == "2025-05-26"

def test_extract_date_dot():
    """ドット形式（2025.05.26）を正しく読めるか"""
    text = "領収証\n2025.05.26\n合計 1000円"
    assert extract_date(text) == "2025-05-26"

def test_extract_date_reiwa_kanji():
    """和暦漢字（令和7年5月26日）を正しく読めるか"""
    text = "令和7年5月26日\n合計 500円"
    assert extract_date(text) == "2025-05-26"

def test_extract_date_reiwa_roman():
    """英字和暦（R7.5.26）を正しく読めるか"""
    text = "R7.5.26\n合計 500円"
    assert extract_date(text) == "2025-05-26"

def test_extract_date_not_found():
    """日付がない場合は None を返すか"""
    text = "合計 500円"
    assert extract_date(text) is None

def test_extract_date_ocr_typo():
    """OCR誤読 O→0 の自動補正が効くか（2O25年 → 2025年）"""
    text = "2O25年05月26日\n合計 648円"
    assert extract_date(text) == "2025-05-26"


# ─── extract_amount ──────────────────────────────────────────────

def test_extract_amount_gokei():
    """「合計」キーワードの行から金額を取れるか"""
    text = "お茶 108円\n弁当 540円\n合計 648円"
    assert extract_amount(text) == 648

def test_extract_amount_total():
    """「TOTAL」キーワードの行から金額を取れるか"""
    text = "coffee 400\nTOTAL 400"
    assert extract_amount(text) == 400

def test_extract_amount_yen_mark():
    """¥マーク付きの金額（¥1,580）を正しく読めるか"""
    text = "合計 ¥1,580"
    assert extract_amount(text) == 1580

def test_extract_amount_next_line():
    """キーワード行に数字がなく次の行に金額がある場合（行マージ失敗の保険）"""
    text = "合計\n1000"
    assert extract_amount(text) == 1000

def test_extract_amount_skip_shoukei():
    """小計行は無視して合計だけを取れるか"""
    text = "小計 500円\n消費税 50円\n合計 550円"
    assert extract_amount(text) == 550

def test_extract_amount_not_found():
    """合計キーワードがない場合は None を返すか"""
    text = "ありがとうございました"
    assert extract_amount(text) is None


# ─── extract_store_name ──────────────────────────────────────────

def test_extract_store_name_two_lines():
    """先頭の空行を除いた最初の2行を返すか"""
    text = "\n〇〇スーパー\n新宿店\n2025年05月26日"
    assert extract_store_name(text) == "〇〇スーパー\n新宿店"

def test_extract_store_name_single_line():
    """行が1行しかない場合はその1行だけ返すか"""
    text = "コンビニA"
    assert extract_store_name(text) == "コンビニA"

def test_extract_store_name_empty():
    """空テキストは None を返すか"""
    assert extract_store_name("") is None


# ─── needs_review ────────────────────────────────────────────────

def test_needs_review_match():
    """check_stores の文字列が店名に部分一致するときは True を返すか"""
    assert needs_review("〇〇スーパー新宿店", ["〇〇スーパー"]) is True

def test_needs_review_no_match():
    """一致しない場合は False を返すか"""
    assert needs_review("コンビニA", ["〇〇スーパー"]) is False

def test_needs_review_empty_list():
    """check_stores が空リストのときは False を返すか"""
    assert needs_review("どんな店", []) is False

def test_needs_review_none_store():
    """store_name が None のときは False を返すか"""
    assert needs_review(None, ["〇〇スーパー"]) is False


# ─── extract_items ────────────────────────────────────────────────

def test_extract_items_basic():
    """品目名を最大2件取れるか"""
    config = {"item_keywords": [], "item_max": 2, "item_exclude_words": []}
    text = "お茶 108\n弁当 540\n合計 648"
    result = extract_items(text, config)
    assert "お茶" in result
    assert "弁当" in result

def test_extract_items_keyword_priority():
    """item_keywords に一致する品目を優先して選ぶか"""
    config = {"item_keywords": ["弁当"], "item_max": 1, "item_exclude_words": []}
    text = "お茶 108\n弁当 540\n合計 648"
    result = extract_items(text, config)
    assert result == ["弁当"]

def test_extract_items_exclude():
    """item_exclude_words に含まれる行はスキップされるか"""
    config = {"item_keywords": [], "item_max": 2, "item_exclude_words": ["割引"]}
    text = "お茶 108\n割引 -10\n弁当 540\n合計 638"
    result = extract_items(text, config)
    assert "割引" not in result

def test_extract_items_empty():
    """品目が1件も検出されない場合は空リストを返すか"""
    config = {"item_keywords": [], "item_max": 2, "item_exclude_words": []}
    text = "ありがとうございました\n合計 500"
    result = extract_items(text, config)
    assert result == []
