from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import create_app
from settlements.parser import load_contract, validate_context_data
from settlements.workflow_store import WorkflowStore


class FakeOCR:
    def read(self, path):
        return {"text": "식사 10,000\n합계 10,000", "blocks": [], "low_score_count": 0}


def parser(calls):
    def parse(text, supplied_evidence=None):
        calls.append((text, supplied_evidence))
        return SimpleNamespace(context=validate_context_data({"participants": [], "expenses": []}),
            source_text=text, supplied_evidence=supplied_evidence, model="fake",
            prompt_version=load_contract()[2], schema_sha256=load_contract()[3], attempts=1)
    return parse


def upload(c):
    f = BytesIO()
    Image.new("RGB", (40, 40), "white").save(f, format="PNG")
    response = c.post("/api/receipts", files={"file": ("r.png", f.getvalue(), "image/png")})
    assert response.status_code == 201
    return response.json()["receipt_id"]


def body(**changes):
    return {"expected_review_revision": 0, "reviewed_by": "검수자", "image_checked": True,
        "items": [{"name": "식사", "amount": 10000}], "total_amount": 10000,
        "receipt_total_amount": 10000, "participants": ["A", "B"], "payer_name": "A",
        "split_method": "equal", **changes}


def confirm(c, sid):
    return c.post(f"/api/sessions/{sid}/confirm", json={"input_revision": 1,
        "reviewed_by": "확인자", "review_notes": "실물 영수증 및 조건 대조", "checks": {
        "source_reviewed": True, "people_resolved": True, "conditions_reviewed": True}})


@pytest.fixture
def setup(tmp_path):
    calls = []
    app = create_app(tmp_path / "data.db", parser=parser(calls), ocr=FakeOCR())
    with TestClient(app) as c:
        yield c, calls


def test_ocr_draft_works_without_llm_and_requires_separate_confirmation(setup):
    c, calls = setup
    rid = upload(c)
    response = c.post(f"/api/receipts/{rid}/draft", json=body())
    assert response.status_code == 200
    doc = response.json()
    assert doc["confirmations"] == doc["calculations"] == [] and calls == []
    sid = doc["session_id"]
    assert c.post(f"/api/sessions/{sid}/calculate", json={"confirmation_id": "missing"}).status_code == 409
    cid = confirm(c, sid).json()["confirmation_id"]
    result = c.post(f"/api/sessions/{sid}/calculate", json={"confirmation_id": cid}).json()["result"]
    assert result["participant_totals"] == {"A": 5000, "B": 5000}


@pytest.mark.parametrize("changes", [
    {"payer_name": None}, {"split_method": None}, {"total_amount": None},
    {"items": [{"name": "식사", "amount": None}]}, {"items": []},
])
def test_missing_values_are_preserved_and_block_confirmation(setup, changes):
    c, calls = setup
    rid = upload(c)
    r = c.post(f"/api/receipts/{rid}/draft", json=body(**changes))
    assert r.status_code == 200
    doc = r.json()
    exp = doc["revisions"][0]["context"]["expenses"][0]
    if "payer_name" in changes:
        assert exp["payer_name"] is None
    if "total_amount" in changes:
        assert exp["total_amount"] is None
    if "items" in changes:
        assert exp["items"] == changes["items"]
    assert confirm(c, doc["session_id"]).status_code == 409 and calls == []


def test_omitted_split_method_is_not_equal(setup):
    c, calls = setup
    rid = upload(c)
    request = body()
    del request["split_method"]
    doc = c.post(f"/api/receipts/{rid}/draft", json=request).json()
    assert doc["revisions"][0]["context"]["split_rules"][0]["method"] is None


def test_payer_outside_consumers_does_not_get_a_share(setup):
    c, _ = setup
    rid = upload(c)
    doc = c.post(f"/api/receipts/{rid}/draft", json=body(payer_name="P")).json()
    context = doc["revisions"][0]["context"]
    assert context["participants"] == ["A", "B", "P"]
    assert context["split_rules"][0]["participant_names"] == ["A", "B"]
    cid = confirm(c, doc["session_id"]).json()["confirmation_id"]
    result = c.post(f'/api/sessions/{doc["session_id"]}/calculate', json={"confirmation_id": cid}).json()["result"]
    assert sum(t["amount"] for t in result["settlements"]) == 10000
    assert all(t["to_participant"] == "P" for t in result["settlements"])


def test_printed_and_actual_totals_are_not_overwritten_to_match(setup):
    c, _ = setup
    rid = upload(c)
    doc = c.post(f"/api/receipts/{rid}/draft", json=body(receipt_total_amount=12000)).json()
    exp = doc["revisions"][0]["context"]["expenses"][0]
    assert exp["total_amount"] == 10000 and exp["receipt_total_amount"] == 12000
    assert confirm(c, doc["session_id"]).status_code == 409


def test_zero_is_preserved(setup):
    c, _ = setup
    rid = upload(c)
    doc = c.post(f"/api/receipts/{rid}/draft", json=body(items=[{"name": "무료", "amount": 0}], total_amount=0, receipt_total_amount=0)).json()
    assert doc["revisions"][0]["context"]["expenses"][0]["total_amount"] == 0
    assert "0원" in doc["supplied_evidence"]
    assert confirm(c, doc["session_id"]).status_code == 200


@pytest.mark.parametrize("changes", [
    {"total_amount": True}, {"total_amount": "10000"}, {"total_amount": 10000.0},
    {"total_amount": -1}, {"total_amount": 9007199254740992},
    {"items": [{"name": "식사", "amount": False}]}, {"items": [{"name": "식사", "amount": 1.5}]},
    {"image_checked": False}, {"image_checked": "true"}, {"reviewed_by": " "},
    {"participants": ["A", " A "]}, {"participants": ["A", " "]},
    {"reviewed_text": "client-injected evidence"},
])
def test_invalid_inputs_rejected_before_creating_any_session(setup, changes):
    c, calls = setup
    rid = upload(c)
    assert c.post(f"/api/receipts/{rid}/draft", json=body(**changes)).status_code == 422
    assert c.get("/api/sessions").json() == [] and calls == []


def test_repeat_manual_request_is_idempotent_and_different_request_is_blocked(setup):
    c, _ = setup
    rid = upload(c)
    url = f"/api/receipts/{rid}/draft"
    first = c.post(url, json=body()).json()
    assert c.post(url, json=body()).json()["session_id"] == first["session_id"]
    assert c.post(url, json=body(total_amount=9000)).status_code == 409
    assert len(c.get("/api/sessions").json()) == 1


def test_ai_handoff_has_no_api_call_and_uses_server_reviewed_evidence(setup):
    c, calls = setup
    rid = upload(c)
    prepared = c.post(f"/api/receipts/{rid}/review", json=body()).json()
    assert calls == []
    assert c.get(f"/api/receipts/{rid}/handoff").json() == prepared
    result = c.post(f"/api/receipts/{rid}/ai", json={"expected_review_revision": 1, "text": "사용자 조건"})
    assert result.status_code == 200
    assert calls == [("사용자 조건", prepared["evidence"])]
    assert c.get(f'/api/sessions/{result.json()["session_id"]}/receipt').json()["receipt_id"] == rid
    assert c.post(f"/api/receipts/{rid}/ai", json={"expected_review_revision": 1, "text": "사용자 조건"}).json()["session_id"] == result.json()["session_id"]
    assert len(calls) == 1


def test_saved_empty_items_and_unknown_total_do_not_fall_back_to_ocr(setup):
    c, _ = setup
    rid = upload(c)
    c.post(f"/api/receipts/{rid}/review", json=body(items=[], total_amount=None, receipt_total_amount=None))
    saved = c.get(f"/api/receipts/{rid}").json()
    assert saved["fields"]["items"] and saved["review"]["items"] == []
    assert saved["review"]["total_amount"] is None


def test_stale_review_cannot_overwrite_or_call_ai(setup):
    c, calls = setup
    rid = upload(c)
    c.post(f"/api/receipts/{rid}/review", json=body())
    assert c.post(f"/api/receipts/{rid}/review", json=body(total_amount=9000)).status_code == 409
    assert c.post(f"/api/receipts/{rid}/review", json=body(expected_review_revision=1, total_amount=9000)).status_code == 200
    assert c.post(f"/api/receipts/{rid}/ai", json={"expected_review_revision": 1, "text": "조건"}).status_code == 409
    assert calls == []


def test_stale_ai_completion_does_not_create_session(tmp_path):
    entered, release = Event(), Event()
    calls = []
    base_parse = parser(calls)
    def slow(text, supplied_evidence=None):
        entered.set()
        assert release.wait(5)
        return base_parse(text, supplied_evidence)
    app = create_app(tmp_path / "data.db", parser=slow, ocr=FakeOCR())
    with TestClient(app) as c, ThreadPoolExecutor() as pool:
        rid = upload(c)
        c.post(f"/api/receipts/{rid}/review", json=body())
        future = pool.submit(c.post, f"/api/receipts/{rid}/ai", json={"expected_review_revision": 1, "text": "조건"})
        try:
            assert entered.wait(3)
            assert c.post(f"/api/receipts/{rid}/review", json=body(expected_review_revision=1, total_amount=9000)).status_code == 200
        finally:
            release.set()
        assert future.result(timeout=5).status_code == 409
        assert c.get("/api/sessions").json() == []


def test_two_instances_cannot_create_duplicate_receipt_sessions(tmp_path):
    path = tmp_path / "data.db"
    with TestClient(create_app(path, parser=parser([]), ocr=FakeOCR())) as first, TestClient(create_app(path, parser=parser([]), ocr=FakeOCR())) as second, ThreadPoolExecutor() as pool:
        rid = upload(first)
        futures = [pool.submit(c.post, f"/api/receipts/{rid}/draft", json=body()) for c in (first, second)]
        results = [f.result(timeout=5) for f in futures]
        assert [r.status_code for r in results] == [200, 200]
        assert results[0].json()["session_id"] == results[1].json()["session_id"]
        assert len(first.get("/api/sessions").json()) == 1


def test_save_failure_rolls_back_session_and_receipt_together(tmp_path, monkeypatch):
    original = WorkflowStore.start
    def fail_after_insert(self, parsed, **kwargs):
        original(self, parsed, **kwargs)
        raise RuntimeError("simulated storage failure")
    app = create_app(tmp_path / "data.db", parser=parser([]), ocr=FakeOCR())
    with TestClient(app, raise_server_exceptions=False) as c:
        rid = upload(c)
        monkeypatch.setattr(WorkflowStore, "start", fail_after_insert)
        assert c.post(f"/api/receipts/{rid}/draft", json=body()).status_code == 500
        assert c.get("/api/sessions").json() == []
        assert c.get(f"/api/receipts/{rid}").json()["session_id"] is None
        monkeypatch.setattr(WorkflowStore, "start", original)
        assert c.post(f"/api/receipts/{rid}/draft", json=body()).status_code == 200
