import json
from types import SimpleNamespace

import pytest

from settlements.parser import (
    ManualInputRequired,
    OutputFormatError,
    ParserAPIError,
    RequestContext,
    parse_and_review,
    parse_settlement_request,
    validate_context_data,
)


def valid_context():
    return {
        "participants": ["A", "B"],
        "rounds": [
            {
                "round_number": 1,
                "participant_names": ["A", "B"],
            }
        ],
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": 10000,
                "round_number": 1,
                "items": [
                    {"name": "식사", "amount": 10000}
                ],
            }
        ],
        "split_rules": [
            {
                "expense_index": 0,
                "item_index": 0,
                "method": "equal",
                "participant_names": ["A", "B"],
            }
        ],
    }


class FakeClient:
    def __init__(self, responses):
        self.models = self
        self.responses = iter(responses)
        self.requests = []

    def generate_content(self, **kwargs):
        self.requests.append(kwargs)
        response = next(self.responses)

        if isinstance(response, Exception):
            raise response

        return SimpleNamespace(
            text=response,
            candidates=[
                SimpleNamespace(finish_reason="STOP")
            ],
        )


def test_parse_settlement_request_validates_gemini_json():
    expected = valid_context()
    client = FakeClient([json.dumps(expected)])

    result = parse_settlement_request(
        "A가 식사비를 결제했어",
        client=client,
        model="mock-model",
    )

    assert isinstance(result, RequestContext)
    assert result.model_dump() == expected
    assert len(client.requests) == 1

    config = client.requests[0]["config"]

    assert config["temperature"] == 0
    assert config["response_mime_type"] == "application/json"
    assert "response_json_schema" in config


def test_parse_settlement_request_rejects_invalid_round():
    data = valid_context()
    data["rounds"][0]["round_number"] = 0

    client = FakeClient([
        json.dumps(data),
        json.dumps(data),
    ])

    with pytest.raises(ManualInputRequired):
        parse_settlement_request(
            "차수 정보",
            client=client,
            model="mock-model",
        )

    # 최초 호출 + 형식 오류 재시도 1회
    assert len(client.requests) == 2


def test_format_error_retries_once():
    client = FakeClient([
        "not JSON",
        json.dumps(valid_context()),
    ])

    result = parse_and_review(
        "정산 요청",
        client=client,
        model="mock-model",
    )

    assert result.attempts == 2
    assert result.status == "needs_confirmation"
    assert result.issues == []
    assert result.source_text == "정산 요청"
    assert len(client.requests) == 2


def test_missing_payer_asks_without_retry():
    data = valid_context()
    data["expenses"][0]["payer_name"] = None

    client = FakeClient([json.dumps(data)])

    result = parse_and_review(
        "결제자는 아직 몰라",
        client=client,
        model="mock-model",
    )

    assert result.status == "needs_clarification"
    assert any(
        issue.code == "unresolved_person"
        and issue.path == "expenses[0].payer_name"
        for issue in result.issues
    )

    assert result.context.expenses[0]["payer_name"] is None

    # 정보 부족은 모델 재시도 대상이 아니다.
    assert len(client.requests) == 1


def test_api_error_is_not_retried():
    client = FakeClient([
        RuntimeError("mock API failure")
    ])

    with pytest.raises(ParserAPIError):
        parse_and_review(
            "정산 요청",
            client=client,
            model="mock-model",
        )

    assert len(client.requests) == 1


@pytest.mark.parametrize(
    "data",
    [
        {},
        {
            "participants": [],
            "expenses": [],
            "tone": None,
        },
        {
            "participants": [],
            "expenses": [],
            "per_person_amount": 1000,
        },
    ],
)
def test_invalid_schema_is_rejected(data):
    with pytest.raises(OutputFormatError):
        validate_context_data(data)