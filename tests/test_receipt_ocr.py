from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from settlements.receipt_ocr import (
    MAX_BYTES, OCRError, PaddleReceiptOCR, decode_results, prepare_image,
)


def photo(format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (120, 120), "white").save(buffer, format=format)
    return buffer.getvalue()


def test_image_bytes_validated_instead_of_extension():
    assert prepare_image(photo()).mode == "RGB"
    with pytest.raises(ValueError):
        prepare_image(b"fake image")
    with pytest.raises(ValueError):
        prepare_image(photo("GIF"))


def test_oversize_bytes_rejected():
    with pytest.raises(ValueError):
        prepare_image(b"a" * (MAX_BYTES + 1))


def test_transparent_background_becomes_white():
    stream = BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(stream, format="PNG")
    assert prepare_image(stream.getvalue()).getpixel((0, 0)) == (255, 255, 255)


def test_keep_low_scores_and_group_receipt_columns():
    result = SimpleNamespace(json={"res": {
        "rec_texts": ["10,000", "김치찌개", "합계 10,000"],
        "rec_scores": [0.40, 0.99, 0.98],
        "rec_boxes": [[100, 12, 140, 32], [0, 10, 80, 30], [0, 50, 130, 70]],
    }})
    actual = decode_results([result])
    assert actual["text"] == "김치찌개  10,000\n합계 10,000"
    assert actual["low_score_count"] == 1
    assert actual["blocks"][0]["score"] == 0.40


def test_incompatible_output_is_not_silently_truncated():
    with pytest.raises(OCRError):
        decode_results([SimpleNamespace(json={"rec_texts": ["누락 금액"], "rec_scores": [], "rec_boxes": []})])


def test_ocr_predict_called_without_dropping_low_score_text():
    calls = []
    engine = PaddleReceiptOCR()
    engine._engine = SimpleNamespace(predict=lambda **kwargs: calls.append(kwargs) or [])
    assert engine.read("receipt.png")["text"] == ""
    assert calls == [{"input": "receipt.png", "text_rec_score_thresh": 0.0}]
