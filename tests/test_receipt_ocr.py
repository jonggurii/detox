"""기존 PaddleOCR 테스트를 영수증 Gemini 추출 계약 검사로 전환(검수·안전조건 유지)."""
from io import BytesIO
from types import SimpleNamespace
import json

import pytest
from PIL import Image
from settlements.receipt_reader import (
    MAX_BYTES, GeminiReceiptReader, ReceiptExtractionError,
    parse_receipt_output, prepare_image,
)


def photo(format="PNG"):
    stream = BytesIO()
    Image.new("RGB", (120, 120), "white").save(stream, format=format)
    return stream.getvalue()


def response(items=None, total=10000, raw_lines=None, notes=None):
    return json.dumps({"items": items if items is not None else [{"name": "식사", "amount": 10000}],
        "total_amount": total, "raw_lines": raw_lines if raw_lines is not None else ["식사 10,000"],
        "notes": notes or []}, ensure_ascii=False)


class FakeClient:
    def __init__(self, text):
        self.text = text
        self.requests = []
        self.models = self

    def generate_content(self, **kwargs):
        self.requests.append(kwargs)
        if isinstance(self.text, Exception):
            raise self.text
        return SimpleNamespace(text=self.text)


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


def test_structured_image_extraction_uses_multimodal_model(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_MULTIMODAL_MODEL", "gemini-3-flash-preview")
    client = FakeClient(response())
    result = GeminiReceiptReader(client=client).extract_bytes(photo())
    assert result["items"] == [{"name": "식사", "amount": 10000}]
    assert result["total_amount"] == 10000
    assert result["low_score_count"] == 0  # Gemini는 OCR 인식 점수를 제공하지 않음
    assert client.requests[0]["model"] == "gemini-3-flash-preview"
    assert client.requests[0]["config"]["response_mime_type"] == "application/json"
    assert "response_json_schema" in client.requests[0]["config"]


def test_mismatched_total_is_warning_not_changed():
    result = parse_receipt_output(response(total=11000))
    assert result["items"][0]["amount"] == 10000
    assert result["total_amount"] == 11000
    assert any("다릅니다" in warning for warning in result["warnings"])


def test_unknown_amount_is_null_and_requires_review():
    data = parse_receipt_output(response(items=[{"name": "맥주", "amount": None}], total=None))
    assert data["items"][0]["amount"] is None
    assert data["total_amount"] is None
    assert data["warnings"]


@pytest.mark.parametrize("invalid", [
    "not JSON", "{}", response(items=[{"name": "소주", "amount": True}]),
    response(items=[{"name": "소주", "amount": -1}]),
    response(items=[{"name": "소주", "amount": 1.1}]),
])
def test_invalid_output_fails_closed(invalid):
    with pytest.raises(ReceiptExtractionError):
        parse_receipt_output(invalid)


def test_provider_failure_is_safe_message():
    client = FakeClient(RuntimeError("private API secret goes here"))
    with pytest.raises(ReceiptExtractionError) as exc:
        GeminiReceiptReader(client=client).extract_bytes(photo())
    assert "private API secret" not in str(exc.value)
