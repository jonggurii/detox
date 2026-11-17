"""복합 정산 자동화: 외부 찬조, 중복 제외, 잔액, 송금 보존."""
from copy import deepcopy

from settlements.calculator import calculate_settlement
from settlements.parser import review_context
from settlements.workflow_store import review


def sample():
    return {
        "participants": ["건", "종현", "종원", "민수", "지훈", "수빈"],
        "expenses": [
            {"payer_name": "건", "total_amount": 240000, "items": [
                {"name": "고기", "amount": 150000},
                {"name": "술", "amount": 60000},
                {"name": "추가", "amount": 30000},
            ]},
            {"payer_name": "민수", "total_amount": 150000, "items": [
                {"name": "안주", "amount": 80000},
                {"name": "술", "amount": 50000},
                {"name": "추가 술", "amount": 20000},
            ]},
            {"payer_name": "종현", "total_amount": 30000, "items": [
                {"name": "아메리카노", "amount": 8000},
                {"name": "라떼", "amount": 10000},
                {"name": "디저트", "amount": 12000},
            ]},
        ],
        "split_rules": [
            {"expense_index": 0, "item_index": 0, "method": "equal", "participant_names": ["건", "종현", "종원", "민수", "지훈", "수빈"]},
            {"expense_index": 0, "item_index": 1, "method": "equal", "participant_names": ["건", "종현", "종원", "민수", "지훈", "수빈"]},
            {"expense_index": 0, "item_index": 2, "method": "equal", "participant_names": ["종현", "종원", "수빈"]},
            {"expense_index": 1, "item_index": 0, "method": "equal", "participant_names": ["건", "종현", "민수", "지훈", "수빈"]},
            {"expense_index": 1, "item_index": 1, "method": "equal", "participant_names": ["건", "종현", "민수", "지훈", "수빈"]},
            {"expense_index": 1, "item_index": 2, "method": "equal", "participant_names": ["건", "종현", "민수"]},
            *[{
                "expense_index": 2, "item_index": i, "method": "explicit_amount",
                "participant_names": [name],
                "individual_amounts": [{"participant_name": name, "amount": amount}],
            } for i, (name, amount) in enumerate([("건", 8000), ("종현", 10000), ("민수", 12000)])],
        ],
        "exceptions": [
            {"expense_index": ei, "item_index": ii, "kind": "exclude", "participant_name": name, "reason": "미참여"}
            for ei, ii, name in [(0, 1, "수빈"), (0, 1, "종원"), (1, 1, "수빈"), (1, 2, "지훈"), (1, 2, "수빈")]
        ],
        "contributions": [{
            "amount": 50000, "contributor_name": "동아리 회장님", "expense_index": 0,
            "funding_note": "회장님 5만원 찬조 - 실제 수령 여부는 담당자가 별도 확인",
            "uses": [{"amount": 50000, "item_index": 0}],
        }],
    }


def test_full_complex_case_without_manual_fixes():
    data = sample()
    before = deepcopy(data)
    assert review_context(data) == []
    clean, issues = review(data)
    assert issues == []
    assert len(clean["exceptions"]) == 3
    assert data == before
    result = calculate_settlement(data)
    assert result.contribution_amount == 50000
    assert sum(result.participant_totals.values()) == 370000
    assert result.participant_totals == {
        "건": 74834, "종현": 86834, "종원": 26667,
        "민수": 78833, "지훈": 60166, "수빈": 42666,
    }
    assert sum(t.amount for t in result.settlements) == 293167
    assert all(t.from_participant != "동아리 회장님" for t in result.settlements)


def test_nonexclude_outside_rule_still_rejected():
    data = sample()
    data["exceptions"] = [{
        "expense_index": 1, "item_index": 2,
        "kind": "fixed_amount", "participant_name": "지훈",
        "fixed_amount": 0, "reason": "합의 금액",
    }]
    assert any(issue.code == "exception_outside_rule" for issue in review_context(data))


def test_explicit_remainder_payer_overrides_default():
    data = sample()
    data["split_rules"][0]["remainder_payer_name"] = "건"
    data["split_rules"][5]["remainder_payer_name"] = "건"
    result = calculate_settlement(data)
    assert result.participant_totals["건"] == 74838
    assert sum(result.participant_totals.values()) == 370000
