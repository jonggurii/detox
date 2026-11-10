from copy import deepcopy

import pytest

from settlements.calculator import (
    CalculationError,
    calculate_settlement,
)
from settlements.parser import review_context


def sample(amount=10001, names=None, remainder="C"):
    names = ["A", "B", "C"] if names is None else names

    rule = {
        "expense_index": 0,
        "item_index": 0,
        "method": "equal",
        "participant_names": list(names),
    }

    if remainder is not None:
        rule["remainder_payer_name"] = remainder

    return {
        "participants": list(names),
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": amount,
                "items": [
                    {
                        "name": "식사비",
                        "amount": amount,
                    }
                ],
            }
        ],
        "split_rules": [rule],
        "exceptions": [
            {
                "expense_index": 0,
                "item_index": 0,
                "participant_name": "A",
                "kind": "covered_by_other",
                "covered_by_name": "B",
                "reason": "B가 A 몫을 대신 부담",
            }
        ],
    }


def test_rounding_after_cover_transfer():
    context = sample()
    original = deepcopy(context)

    result = calculate_settlement(context)

    assert result.participant_totals == {
        "A": 0,
        "B": 6667,
        "C": 3334,
    }
    assert sum(result.participant_totals.values()) == 10001

    assert [
        (
            transfer.from_participant,
            transfer.to_participant,
            transfer.amount,
        )
        for transfer in result.settlements
    ] == [
        ("B", "A", 6667),
        ("C", "A", 3334),
    ]

    assert context == original


def test_no_remainder_needed_when_cover_resolves_fraction():
    context = sample(
        amount=1,
        names=["A", "B"],
        remainder=None,
    )

    assert review_context(context) == []

    result = calculate_settlement(context)

    assert result.participant_totals == {
        "A": 0,
        "B": 1,
    }


def test_reject_remainder_payer_who_transferred_all_share():
    context = sample(remainder="A")

    issues = review_context(context)

    assert any(
        issue.code == "invalid_remainder_payer"
        for issue in issues
    )

    with pytest.raises(CalculationError):
        calculate_settlement(context)