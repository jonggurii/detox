"""운영 app.py의 영수증 경로 연결과 멀티모달 검수 게이트 회귀 검사."""
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class FakeImageReader:
    def read(self, path):
        return self.extract_bytes(Path(path).read_bytes())

    def extract_bytes(self, raw):
        from settlements.receipt_reader import prepare_image
        prepare_image(raw)
        return {"items": [{"name": "식사", "amount": 8000}], "total_amount": 8000,
                "text": "식사 8,000", "blocks": [], "low_score_count": 0,
                "warnings": [], "model": "fake-gemini"}


def image_bytes():
    output = BytesIO()
    Image.new("RGB", (30, 30), "white").save(output, "PNG")
    return output.getvalue()


def production_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLEMENT_DB_PATH", str(tmp_path / "bootstrap.db"))
    spec = spec_from_file_location("detox_production_app_for_tests", ROOT / "app.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_application_registers_receipt_upload_and_image(tmp_path, monkeypatch):
    app_module = production_app(tmp_path, monkeypatch)
    calls = []
    def parser(text, **kwargs):
        calls.append(text)
        raise AssertionError("이미지만 업로드할 때 정산 파서를 호출해서는 안 됩니다")
    app = app_module.create_app(tmp_path / "service.db", parser=parser, ocr=FakeImageReader())
    with TestClient(app) as client:
        assert client.get("/receipts/new").status_code == 200
        response = client.post("/api/receipts", files={"file": ("r.png", image_bytes(), "image/png")})
        assert response.status_code == 201
        receipt = response.json()
        assert receipt["fields"]["items"] == [{"name": "식사", "amount": 8000}]
        assert client.get(f"/api/receipts/{receipt['receipt_id']}/image").status_code == 200
        assert client.get("/api/sessions").json() == [] and not calls


def test_multimodal_legacy_endpoint_requires_review(tmp_path, monkeypatch):
    from backend import multimodal_router
    monkeypatch.setattr(multimodal_router, "GeminiReceiptReader", FakeImageReader)
    app_module = production_app(tmp_path, monkeypatch)
    app = app_module.create_app(tmp_path / "service.db", ocr=FakeImageReader())
    with TestClient(app) as client:
        preview = client.post("/api/sessions/multimodal", data={"text": "민수가 먹음"},
            files={"file": ("r.png", image_bytes(), "image/png")})
        assert preview.status_code == 200
        assert preview.json()["review_required"] is True
        assert preview.json()["items"][0]["amount"] == 8000
        assert client.get("/api/sessions").json() == []
        bad = client.post("/api/receipts/multimodal-preview", files={"file": ("r.png", b"not image", "image/png")})
        assert bad.status_code == 422
