import pytest

from settlements.calculator import CalculationError, calculate_settlement
from settlements.parser import review_context


def test_rounding_after_cover_transfer():
    context = {
        "participants": ["A", "B", "C"],
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": 10001,
                "items": [
                    {"name": "식사비", "amount": 10001}
                ],
            }
        ],
        "split_rules": [
            {
                "expense_index": 0,
                "item_index": 0,
                "method": "equal",
                "participant_names": ["A", "B", "C"],
                "remainder_payer_name": "C",
            }
        ],
        "exceptions": [
            {
                "expense_index": 0,
                "item_index": 0,
                "participant_name": "A",
                "kind": "covered_by_other",
                "covered_by_name": "B",
                "reason": "B가 A의 소비 몫을 대신 부담하기로 합의했다.",
            }
        ],
    }

    result = calculate_settlement(context)

    assert result.participant_totals == {
        "A": 0,
        "B": 6667,
        "C": 3334,
    }
    assert sum(result.participant_totals.values()) == 10001

    transfers = {(t.from_participant, t.to_participant): t.amount for t in result.settlements}
    assert transfers == {
        ("B", "A"): 6667,
        ("C", "A"): 3334,
    }


def test_no_remainder_needed_when_cover_resolves_fraction():
    """A·B가 1원을 균등 분담하되 B가 A의 몫까지 대신 부담하면 최종 몫은 B=1원이므로 잔액 부담자가 불필요하다."""
    context = {
        "participants": ["A", "B"],
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": 1,
                "items": [{"name": "테스트항목", "amount": 1}],
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
        "exceptions": [
            {
                "expense_index": 0,
                "item_index": 0,
                "participant_name": "A",
                "kind": "covered_by_other",
                "covered_by_name": "B",
                "reason": "B가 A의 몫을 대신 부담",
            }
        ],
    }

    assert review_context(context) == []
    result = calculate_settlement(context)
    assert result.participant_totals == {"A": 0, "B": 1}


def test_reject_remainder_payer_who_transferred_all_share():
    """자기 몫을 전부 다른 사람에게 넘긴 사람(A)을 잔액 부담자로 지정하면 거부해야 한다."""
    context = {
        "participants": ["A", "B", "C"],
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": 10001,
                "items": [{"name": "식사비", "amount": 10001}],
            }
        ],
        "split_rules": [
            {
                "expense_index": 0,
                "item_index": 0,
                "method": "equal",
                "participant_names": ["A", "B", "C"],
                "remainder_payer_name": "A",
            }
        ],
        "exceptions": [
            {
                "expense_index": 0,
                "item_index": 0,
                "participant_name": "A",
                "kind": "covered_by_other",
                "covered_by_name": "B",
                "reason": "B가 A의 소비 몫을 대신 부담하기로 합의했다.",
            }
        ],
    }

    issues = review_context(context)
    assert any(
        issue.code == "invalid_remainder_payer"
        and issue.path == "expenses[0].items[0]"
        for issue in issues
    ), [
        issue.model_dump()
        for issue in issues
    ]

    with pytest.raises(CalculationError):
        calculate_settlement(context)