import pytest
from fastapi.testclient import TestClient

from app import create_app
from settlements.parser import (
    ManualInputRequired,
    ParseResult,
    ParserAPIError,
    ParserConfigurationError,
    load_contract,
    review_context,
    validate_context_data,
)


def parsed(text, supplied_evidence=None):
    context = validate_context_data({"participants": [], "expenses": []})
    return ParseResult(
        context=context,
        issues=review_context(context),
        status="needs_clarification",
        source_text=text,
        supplied_evidence=supplied_evidence,
        model="mock",
        prompt_version=load_contract()[2],
        schema_sha256=load_contract()[3],
        attempts=1,
    )


def test_legacy_parse_returns_review_envelope_without_creating_session(tmp_path):
    calls = []

    def spy(text, supplied_evidence=None):
        calls.append((text, supplied_evidence))
        return parsed(text, supplied_evidence)

    with TestClient(create_app(tmp_path / "legacy.sqlite3", parser=spy)) as client:
        response = client.post("/parse", json={
            "text": "결제자를 아직 모릅니다.",
            "supplied_evidence": "영수증 근거",
        })
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "needs_clarification"
        assert result["context"] == {"participants": [], "expenses": []}
        assert result["issues"]
        assert result["supplied_evidence"] == "영수증 근거"
        assert result["model"] == "mock"
        assert calls == [("결제자를 아직 모릅니다.", "영수증 근거")]
        assert client.get("/api/sessions").json() == []


def test_web_session_preserves_evidence_with_one_parse_call(tmp_path):
    calls = []

    def spy(text, supplied_evidence=None):
        calls.append((text, supplied_evidence))
        return parsed(text, supplied_evidence)

    with TestClient(create_app(tmp_path / "web.sqlite3", parser=spy)) as client:
        response = client.post("/api/sessions", json={
            "text": "정산 입력",
            "supplied_evidence": "영수증 원문",
        })
        assert response.status_code == 200
        document = response.json()
        assert document["supplied_evidence"] == "영수증 원문"
        assert calls == [("정산 입력", "영수증 원문")]
        reopened = client.get("/api/sessions/" + document["session_id"]).json()
        assert reopened["supplied_evidence"] == "영수증 원문"


@pytest.mark.parametrize("error,status,code", [
    (ManualInputRequired("직접 입력 필요"), 422, "manual_input_required"),
    (ParserAPIError("upstream detail"), 503, "parser_unavailable"),
    (ParserConfigurationError("configuration detail"), 503, "parser_unavailable"),
])
def test_legacy_parse_error_contract(tmp_path, error, status, code):
    def broken(text):
        raise error

    with TestClient(create_app(tmp_path / "errors.sqlite3", parser=broken)) as client:
        response = client.post("/parse", json={"text": "입력"})
        assert response.status_code == status
        assert response.json()["detail"]["code"] == code
        if status == 503:
            assert "detail" not in response.json()["detail"]
            assert str(error) not in response.text


def test_whitespace_input_does_not_call_model(tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("빈 입력으로 모델을 호출하면 안 됩니다.")

    with TestClient(create_app(tmp_path / "empty.sqlite3", parser=forbidden)) as client:
        response = client.post("/parse", json={"text": "   "})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_input"


@pytest.mark.parametrize("body", [
    {"text": ""},
    {"text": "정산", "unknown": True},
    {"text": "정산", "supplied_evidence": "x" * 24001},
])
def test_invalid_request_rejected_before_model(tmp_path, body):
    def forbidden(*args, **kwargs):
        raise AssertionError("잘못된 요청으로 모델을 호출하면 안 됩니다.")

    with TestClient(create_app(tmp_path / "invalid.sqlite3", parser=forbidden)) as client:
        assert client.post("/parse", json=body).status_code == 422
