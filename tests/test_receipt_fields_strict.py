import pytest
from settlements.receipt_fields import extract_receipt_fields, parse_amount


def extract(text):
    return extract_receipt_fields({"text": text})


@pytest.mark.parametrize("source,amount", [("0", 0), ("1", 1), ("50", 50), ("10,000원", 10000), ("12000", 12000)])
def test_valid_integer_amounts_including_zero(source, amount):
    assert parse_amount(source) == amount


@pytest.mark.parametrize("source", ["-1,000", "12.50", "1,00", "1e3", "True", "1 000", "9" * 5000, "9007199254740992"])
def test_invalid_amount_is_never_repaired_to_another_value(source):
    assert parse_amount(source) is None


def test_no_receipt_total_is_inferred_from_items():
    actual = extract("김치찌개 10,000\n제육볶음 12,000")
    assert [i["amount"] for i in actual["items"]] == [10000, 12000]
    assert actual["total_amount"] is None


@pytest.mark.parametrize("label", ["합계:22,000원", "합 계 22,000", "합계\n22,000", "현금 결제금액 22,000"])
def test_explicit_receipt_total_variants(label):
    assert extract(label)["total_amount"] == 22000


def test_conflicting_totals_do_not_choose_last_candidate():
    result = extract("합계 22,000\n결제금액 20,000")
    assert result["total_amount"] is None
    assert [c["amount"] for c in result["total_candidates"]] == [22000, 20000]


def test_numbers_on_total_line_are_not_concatenated():
    assert extract("합계 1 10000")["total_amount"] is None


def test_zero_amount_and_brand_number_are_preserved():
    result = extract("7번가피자 20,000\n무료서비스 0\n합계 20,000")
    assert result["items"][0]["name"] == "7번가피자"
    assert result["items"][1]["amount"] == 0


def test_tax_card_and_metadata_are_not_additional_items():
    result = extract("김치찌개 10,000\n부가세 909\nVAT 909\n신용카드 10,000\n사업자 123-45-67890\nTEL 031-123-4567\n소계 10,000\n합계 10,000")
    assert [(i["name"], i["amount"]) for i in result["items"]] == [("김치찌개", 10000)]


def test_discount_negative_and_foreign_lines_are_retained_for_review():
    lines = ["할인 1,000", "취소 -2,000", "품목 -3,000", "상품 USD 100", "커피 12.50"]
    result = extract("\n".join(lines))
    assert result["items"] == []
    assert result["unparsed_lines"] == lines


def test_amount_column_requires_header_for_multiple_numeric_columns():
    assert extract("삼겹살 15,000 2 30,000")["items"] == []
    result = extract("상품명 단가 수량 금액\n삼겹살 15,000 2 30,000\n합계 30,000")
    assert result["items"][0]["amount"] == 30000


def test_column_order_is_read_from_header():
    result = extract("상품명 금액 수량\n음료 3,000 2")
    assert result["items"][0]["amount"] == 3000


def test_ocr_wrong_digit_is_not_hidden_in_item_name():
    assert extract("상품명 단가 수량 금액\n삼겹살 15,OOO 2 30,000")["items"] == []


def test_label_does_not_attach_to_distant_numbers_across_metadata():
    result = extract("합계\nTEL 031-123-4567\n22000")
    assert result["total_amount"] is None and result["items"] == []


@pytest.mark.parametrize("scale", [1, 10])
def test_line_grouping_uses_relative_height(scale):
    blocks = [{"text": "김치찌개", "box": [0, 0, 50, 10]},
              {"text": "10,000", "box": [60, 1, 100, 11]},
              {"text": "합계", "box": [0, 13, 50, 23]},
              {"text": "10,000", "box": [60, 13, 100, 23]}]
    for b in blocks:
        b["box"] = [n * scale for n in b["box"]]
    result = extract_receipt_fields({"blocks": blocks})
    assert result["items"][0]["amount"] == result["total_amount"] == 10000


def test_bad_and_missing_boxes_fall_back_without_crashing():
    result = extract_receipt_fields({"text": "식사 1000\n합계 1000", "blocks": [None, {"text": "식사", "box": [[None]]}]})
    assert result["total_amount"] == 1000


@pytest.mark.parametrize("text", ["식사 10,000 원\n합계 10,000 원", "식사 ₩10,000\n합계 ₩10,000"])
def test_won_symbol_and_separated_currency_suffix(text):
    result = extract(text)
    assert result["items"][0]["amount"] == 10000
    assert result["total_amount"] == 10000
