"""PaddleOCR 3.3.x: 한국어 영수증을 읽고 원래 인식 점수를 보존한다."""
from io import BytesIO
from threading import Lock
import json
import math

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000
LOW_SCORE = 0.85  # 프로젝트 검수 기준. 정답 확률이 아니다.


class OCRError(RuntimeError):
    pass


def prepare_image(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("10MB 이하 JPG 또는 PNG 파일을 선택해 주세요.")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"JPEG", "PNG"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError("정지 이미지 JPG·PNG만 지원합니다.")
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("이미지를 1,200만 화소 이하로 줄여 주세요.")
            # 휴대폰 회전 정보 반영, 투명 영역은 흰색으로 합성.
            image = ImageOps.exif_transpose(image).convert("RGBA")
            canvas = Image.new("RGBA", image.size, "white")
            canvas.alpha_composite(image)
            return canvas.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("정상적인 이미지 파일을 읽지 못했습니다.") from exc


def decode_results(results):
    blocks = []
    for result in results:
        data = result.json
        if isinstance(data, str):
            data = json.loads(data)
        data = data.get("res", data)
        texts, scores, boxes = data["rec_texts"], data["rec_scores"], data["rec_boxes"]
        if not len(texts) == len(scores) == len(boxes):
            raise OCRError("OCR 결과의 글자·점수·위치 개수가 다릅니다.")
        for text, score, box in zip(texts, scores, boxes):
            score = float(score)
            box = [float(v) for v in box]
            if len(box) != 4 or not all(math.isfinite(v) for v in [score, *box]):
                raise OCRError("OCR 결과에 올바르지 않은 위치나 점수가 있습니다.")
            if str(text).strip():
                blocks.append({"text": str(text), "score": score, "box": box,
                               "needs_review": score < LOW_SCORE})
    # 같은 줄의 품목/수량/금액을 좌→우로 묶는다. 원래 블록은 별도 보존한다.
    rows = []
    for block in sorted(blocks, key=lambda b: ((b["box"][1] + b["box"][3]) / 2, b["box"][0])):
        x1, y1, x2, y2 = block["box"]
        center, height = (y1 + y2) / 2, max(y2 - y1, 1)
        if rows and abs(rows[-1]["y"] - center) <= 0.45 * min(rows[-1]["h"], height):
            rows[-1]["blocks"].append(block)
        else:
            rows.append({"y": center, "h": height, "blocks": [block]})
    text = "\n".join("  ".join(b["text"] for b in sorted(r["blocks"], key=lambda b: b["box"][0]))
                     for r in rows)
    return {"text": text, "blocks": blocks,
            "low_score_count": sum(b["needs_review"] for b in blocks)}


class PaddleReceiptOCR:
    def __init__(self):
        self._engine = None
        self._lock = Lock()

    def read(self, image_path):
        # 하나의 엔진을 여러 요청에서 동시에 실행하지 않는다.
        with self._lock:
            try:
                if self._engine is None:
                    from paddleocr import PaddleOCR
                    self._engine = PaddleOCR(
                        # 두 모델명을 지정했으므로 lang/ocr_version을 중복 지정하지 않는다.
                        text_detection_model_name="PP-OCRv5_server_det",
                        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                        device="cpu",
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                    )
                return decode_results(self._engine.predict(
                    input=str(image_path), text_rec_score_thresh=0.0,
                ))
            except OCRError:
                raise
            except Exception as exc:
                raise OCRError("OCR 실행 실패: 설치·모델 다운로드 상태를 확인하거나 직접 입력해 주세요.") from exc
