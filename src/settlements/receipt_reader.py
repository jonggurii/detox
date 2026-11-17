"""Gemini 3.5 Flash 영수증 이미지 추출. 결과는 확정값이 아닌 사용자 검수 후보."""
from io import BytesIO
from pathlib import Path
import json

from PIL import Image, ImageOps, UnidentifiedImageError
from .gemini_client import get_client, get_model

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_AMOUNT = 2**53 - 1


class ReceiptExtractionError(RuntimeError):
    """영수증 인식 실패. 원본은 보관하고 사용자가 직접 입력할 수 있다."""


def prepare_image(raw: bytes) -> Image.Image:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("10MB 이하 JPG 또는 PNG 파일을 선택해 주세요.")
    try:
        with Image.open(BytesIO(raw)) as original:
            if original.format not in {"JPEG", "PNG"} or getattr(original, "n_frames", 1) != 1:
                raise ValueError("정지 이미지 JPG·PNG만 지원합니다.")
            if original.width * original.height > MAX_PIXELS:
                raise ValueError("이미지를 1,200만 화소 이하로 줄여 주세요.")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            canvas = Image.new("RGBA", image.size, "white")
            canvas.alpha_composite(image)
            return canvas.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("정상적인 이미지 파일을 읽지 못했습니다.") from exc


# SDK 구조화 출력과 동일한 계약으로 로컬에서도 엄격하게 검증한다.
RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": ["string", "null"]},
            "amount": {"type": ["integer", "null"]},
        }, "required": ["name", "amount"], "additionalProperties": False}},
        "total_amount": {"type": ["integer", "null"]},
        "raw_lines": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["items", "total_amount", "raw_lines", "notes"],
    "additionalProperties": False,
}

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "receipt_extraction.md"
PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
PROMPT_VERSION = 1


def _money(value):
    if value is None:
        return None
    if type(value) is not int or not (0 <= value <= MAX_AMOUNT):
        raise ReceiptExtractionError("영수증 금액 형식을 검증하지 못했습니다.")
    return value


def parse_receipt_output(text: str) -> dict:
    try:
        obj = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ReceiptExtractionError("모델이 올바른 JSON을 반환하지 않았습니다.") from exc
    if not isinstance(obj, dict) or set(obj) != set(RECEIPT_SCHEMA["required"]):
        raise ReceiptExtractionError("영수증 출력 필드가 올바르지 않습니다.")
    raw_items, lines, notes = obj["items"], obj["raw_lines"], obj["notes"]
    if not isinstance(raw_items, list) or len(raw_items) > 100:
        raise ReceiptExtractionError("영수증 항목 수가 올바르지 않습니다.")
    if not isinstance(lines, list) or len(lines) > 100 or not all(isinstance(s, str) and len(s) <= 300 for s in lines):
        raise ReceiptExtractionError("영수증 원문 후보가 올바르지 않습니다.")
    if not isinstance(notes, list) or len(notes) > 30 or not all(isinstance(s, str) and len(s) <= 500 for s in notes):
        raise ReceiptExtractionError("영수증 검토 메모가 올바르지 않습니다.")
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict) or set(raw) != {"name", "amount"}:
            raise ReceiptExtractionError("영수증 품목 필드가 올바르지 않습니다.")
        name = raw["name"]
        if name is not None and (not isinstance(name, str) or len(name) > 200):
            raise ReceiptExtractionError("영수증 품목명이 올바르지 않습니다.")
        items.append({"name": name.strip() or None if isinstance(name, str) else None,
                      "amount": _money(raw["amount"])})
    total = _money(obj["total_amount"])
    warnings = list(notes)
    if any(item["name"] is None or item["amount"] is None for item in items):
        warnings.append("일부 품목·금액이 불명확하므로 사진과 대조해 주세요.")
    if total is None:
        warnings.append("결제 총액을 확정하지 않았습니다. 사진을 확인해 입력해 주세요.")
    if total is not None and items and all(i["amount"] is not None for i in items):
        if sum(i["amount"] for i in items) != total:
            warnings.append("품목 합계와 영수증 총액이 다릅니다. 할인·누락·수량을 확인해 주세요.")
    return {"text": "\n".join(lines), "blocks": [], "low_score_count": 0,
            "items": items, "total_amount": total, "raw_lines": lines,
            "notes": notes, "warnings": list(dict.fromkeys(warnings)), "model": get_model(),
            "prompt_version": PROMPT_VERSION}


class GeminiReceiptReader:
    def __init__(self, client=None):
        self.client = client

    def read(self, image_path: str | Path) -> dict:
        return self.extract_bytes(Path(image_path).read_bytes())

    def extract_bytes(self, raw: bytes) -> dict:
        # 이미지 내용 자체 검증: 파일명·Content-Type을 신뢰하지 않는다.
        image = prepare_image(raw)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        try:
            if self.client is None:
                from google.genai import types
                part = types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/png")
            else:
                # 오프라인 가짜 클라이언트 테스트는 SDK 설치 없이 실행 가능.
                part = {"inline_data": {"data": buffer.getvalue(), "mime_type": "image/png"}}
            response = (self.client or get_client()).models.generate_content(
                model=get_model(),
                contents=[part, PROMPT],
                config={"temperature": 0, "response_mime_type": "application/json",
                        "response_json_schema": RECEIPT_SCHEMA},
            )
        except Exception as exc:
            # API 키와 제공자 응답 본문을 사용자에게 노출하지 않는다.
            raise ReceiptExtractionError("Gemini 영수증 인식에 실패했습니다. 직접 입력해 주세요.") from exc
        return parse_receipt_output(getattr(response, "text", None))
