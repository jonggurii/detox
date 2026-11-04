from io import BytesIO
from types import SimpleNamespace
import sqlite3
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import create_app
from settlements.parser import ParserAPIError, load_contract, validate_context_data
from settlements.receipt_ocr import OCRError


def context():
    return {"participants": ["A", "B"], "expenses": [{"payer_name": "A", "total_amount": 10000,
            "receipt_total_amount": 10000, "items": [{"name": "식사", "amount": 10000}]}],
            "split_rules": [{"expense_index": 0, "item_index": 0, "method": "equal", "participant_names": ["A", "B"]}]}


def make_parser(calls, data=None, fail=False):
    def parse(text, supplied_evidence=None):
        calls.append((text, supplied_evidence))
        if fail:
            raise ParserAPIError("private provider error")
        return SimpleNamespace(context=validate_context_data(data or context()), source_text=text,
            supplied_evidence=supplied_evidence, model="fake", prompt_version=load_contract()[2],
            schema_sha256=load_contract()[3], attempts=1)
    return parse


class FakeOCR:
    def read(self, path):
        return {"text": "식사 1O,OOO\n합계 10,000", "blocks": [], "low_score_count": 1}


def upload(client):
    data = BytesIO()
    Image.new("RGB", (100, 100), "white").save(data, format="PNG")
    r = client.post("/api/receipts", files={"file": ("../../receipt.png", data.getvalue(), "image/png")})
    assert r.status_code == 201
    return r.json()["receipt_id"]


def body(**extra):
    return {"reviewed_text": "식사 10,000\n합계 10,000", "reviewed_by": "담당자", "image_checked": True,
            "text": "A가 결제했고 A와 B가 모든 항목을 균등 분담. 예외·찬조금 없음.", **extra}


def confirmation(client, sid, revision=1):
    return client.post(f"/api/sessions/{sid}/confirm", json={"input_revision": revision,
        "reviewed_by": "담당자", "review_notes": "영수증과 조건 대조", "checks": {
        "source_reviewed": True, "people_resolved": True, "conditions_reviewed": True}})


def test_upload_does_not_call_llm_or_create_settlement(tmp_path):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls), ocr=FakeOCR())) as c:
        rid = upload(c)
        assert calls == [] and c.get("/api/sessions").json() == []
        assert c.get(f"/api/receipts/{rid}/image").headers["content-type"] == "image/png"
        assert c.get("/receipts/new").status_code == 200
        assert (tmp_path / "receipts" / rid / "original.bin").exists()


@pytest.mark.parametrize("change", [{"image_checked": False}, {"image_checked": "true"},
    {"reviewed_text": " "}, {"reviewed_by": " "}, {"text": " "}, {"reviewed_text": "a" * 24001}])
def test_review_gate_blocks_llm(tmp_path, change):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls), ocr=FakeOCR())) as c:
        rid = upload(c)
        assert c.post(f"/api/receipts/{rid}/session", json=body(**change)).status_code == 422
        assert calls == []


def test_corrected_evidence_then_confirmed_calculation_and_edit_invalidation(tmp_path):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls), ocr=FakeOCR())) as c:
        rid = upload(c)
        doc = c.post(f"/api/receipts/{rid}/session", json=body()).json()
        sid = doc["session_id"]
        assert calls == [(body()["text"], body()["reviewed_text"])]
        receipt = c.get(f"/api/receipts/{rid}").json()
        assert "1O,OOO" in receipt["ocr"]["text"] and "10,000" in receipt["review"]["reviewed_text"]
        assert doc["supplied_evidence"] == body()["reviewed_text"]
        assert doc["confirmations"] == [] and doc["calculations"] == []
        assert c.get(f"/api/sessions/{sid}/receipt").json()["receipt_id"] == rid
        assert c.post(f"/api/sessions/{sid}/calculate", json={"confirmation_id": "fake"}).status_code == 409
        cid = confirmation(c, sid).json()["confirmation_id"]
        result = c.post(f"/api/sessions/{sid}/calculate", json={"confirmation_id": cid}).json()["result"]
        assert result["participant_totals"] == {"A": 5000, "B": 5000}
        assert sum(t["amount"] for t in result["settlements"]) == 5000
        c.patch(f"/api/sessions/{sid}/context", json={"input_revision": 1, "context": context()})
        assert c.post(f"/api/sessions/{sid}/calculate", json={"confirmation_id": cid}).status_code == 409


def test_repeat_submit_reuses_session_and_changed_evidence_is_blocked(tmp_path):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls), ocr=FakeOCR())) as c:
        rid = upload(c)
        url = f"/api/receipts/{rid}/session"
        first = c.post(url, json=body()).json()
        assert c.post(url, json=body()).json()["session_id"] == first["session_id"]
        assert c.post(url, json=body(reviewed_text="변경한 원문")).status_code == 409
        assert len(calls) == 1


def test_llm_failure_keeps_review_and_allows_manual_without_another_call(tmp_path):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls, fail=True), ocr=FakeOCR())) as c:
        rid = upload(c)
        url = f"/api/receipts/{rid}/session"
        r = c.post(url, json=body())
        assert r.status_code == 503 and "private provider" not in r.text
        assert c.get(f"/api/receipts/{rid}").json()["review"]["reviewed_text"] == body()["reviewed_text"]
        assert c.post(url, json=body()).status_code == 429
        manual = c.post(url, json=body(mode="manual")).json()
        assert manual["parse_metadata"]["model"] == "manual" and len(calls) == 1
        assert confirmation(c, manual["session_id"]).status_code == 409


def test_total_mismatch_remains_unconfirmed(tmp_path):
    data = context()
    data["expenses"][0]["items"][0]["amount"] = 9000
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser([], data), ocr=FakeOCR())) as c:
        rid = upload(c)
        doc = c.post(f"/api/receipts/{rid}/session", json=body()).json()
        assert doc["revisions"][0]["issues"]
        assert confirmation(c, doc["session_id"]).status_code == 409


def test_payer_is_not_filled_by_receipt_route(tmp_path):
    data = context()
    data["expenses"][0]["payer_name"] = None
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser([], data), ocr=FakeOCR())) as c:
        rid = upload(c)
        doc = c.post(f"/api/receipts/{rid}/session", json=body()).json()
        assert doc["revisions"][0]["context"]["expenses"][0]["payer_name"] is None
        assert confirmation(c, doc["session_id"]).status_code == 409


def test_ocr_failure_keeps_image_for_manual_reading(tmp_path):
    def fail(_):
        raise OCRError("OCR 설치를 확인해 주세요.")
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser([]), ocr=SimpleNamespace(read=fail))) as c:
        rid = upload(c)
        assert c.get(f"/api/receipts/{rid}").json()["warning"]
        assert c.get(f"/api/receipts/{rid}/image").status_code == 200
        assert c.post(f"/api/receipts/{rid}/session", json=body(mode="manual")).status_code == 200


def test_invalid_image_and_missing_receipt_do_not_call_llm(tmp_path):
    calls = []
    with TestClient(create_app(tmp_path / "test.db", parser=make_parser(calls), ocr=FakeOCR())) as c:
        assert c.post("/api/receipts", files={"file": ("bad.png", b"hello", "image/png")}).status_code == 422
        assert c.get("/api/receipts/missing/image").status_code == 404
        assert calls == []
