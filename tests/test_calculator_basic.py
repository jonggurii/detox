from copy import deepcopy

import pytest

from settlements.calculator import (
    CalculationError,
    calculate_settlement,
)


def context(amount=30000):
    # 참여자 목록과 부담 대상자 목록은 서로 다른 리스트다.
    return {
        "participants": ["A", "B", "C"],
        "expenses": [
            {
                "payer_name": "A",
                "total_amount": amount,
                "items": [
                    {"name": "식사", "amount": amount}
                ],
            }
        ],
        "split_rules": [
            {
                "expense_index": 0,
                "item_index": 0,
                "method": "equal",
                "participant_names": ["A", "B", "C"],
            }
        ],
    }


def adjustment(name, kind, **fields):
    return {
        "expense_index": 0,
        "item_index": 0,
        "participant_name": name,
        "kind": kind,
        "reason": "사용자 합의",
        **fields,
    }


def checked(data):
    """정상 계산의 공통 불변 조건을 검사한다."""
    before = deepcopy(data)
    result = calculate_settlement(data)

    assert data == before

    for ei, expense in enumerate(data["expenses"]):
        contributions = sum(
            contribution["amount"]
            for contribution in data.get("contributions", [])
            if contribution["expense_index"] == ei
        )

        # 항목별 부담액 + 항목별 찬조 적용액 = 항목 원금
        for ii, item in enumerate(expense["items"]):
            applied = sum(
                use["amount"]
                for contribution in data.get("contributions", [])
                if contribution["expense_index"] == ei
                for use in contribution["uses"]
                if use["item_index"] == ii
            )

            allocated = sum(
                allocation.amount
                for allocation in result.allocations
                if (
                    allocation.expense_index,
                    allocation.item_index,
                ) == (ei, ii)
            )

            assert allocated + applied == item["amount"]

        own = sum(
            allocation.amount
            for allocation in result.allocations
            if allocation.expense_index == ei
            and allocation.participant_name == expense["payer_name"]
        )

        transfers = [
            transfer
            for transfer in result.settlements
            if transfer.expense_index == ei
        ]

        # 해당 결제의 실제 결제자에게 송금해야 한다.
        assert all(
            transfer.to_participant == expense["payer_name"]
            for transfer in transfers
        )

        # 본인 송금과 0원 청구를 만들지 않는다.
        assert all(
            transfer.from_participant != transfer.to_participant
            and transfer.amount > 0
            for transfer in transfers
        )

        # 송금 요청 + 결제자 본인 몫 + 찬조금 = 결제 원금
        assert (
            sum(transfer.amount for transfer in transfers)
            + own
            + contributions
            == expense["total_amount"]
        )

    for name, total in result.participant_totals.items():
        assert total == sum(
            allocation.amount
            for allocation in result.allocations
            if allocation.participant_name == name
        )

    assert result.contribution_amount == sum(
        contribution["amount"]
        for contribution in data.get("contributions", [])
    )

    return result


def test_equal_split():
    result = checked(context())

    assert result.participant_totals == {
        "A": 10000,
        "B": 10000,
        "C": 10000,
    }

    assert [
        (
            transfer.from_participant,
            transfer.to_participant,
            transfer.amount,
        )
        for transfer in result.settlements
    ] == [
        ("B", "A", 10000),
        ("C", "A", 10000),
    ]


def test_single_person_zero():
    data = context(0)
    data["participants"] = ["A"]
    data["split_rules"][0]["participant_names"] = ["A"]

    result = checked(data)

    assert result.participant_totals == {"A": 0}
    assert not result.settlements


def test_equal_remainder():
    data = context(10000)

    with pytest.raises(
        CalculationError,
        match="unresolved_rounding",
    ):
        calculate_settlement(data)

    data["split_rules"][0]["remainder_payer_name"] = "C"

    assert checked(data).participant_totals == {
        "A": 3333,
        "B": 3333,
        "C": 3334,
    }


def test_fixed_and_excluded():
    data = context()

    data["exceptions"] = [
        adjustment(
            "A",
            "fixed_amount",
            fixed_amount=5000,
        ),
        adjustment("C", "exclude"),
    ]

    assert checked(data).participant_totals == {
        "A": 5000,
        "B": 25000,
        "C": 0,
    }


def test_explicit_amounts_with_consistent_exceptions():
    data = context()

    data["split_rules"][0].update(
        method="explicit_amount",
        individual_amounts=[
            {"participant_name": "A", "amount": 5000},
            {"participant_name": "B", "amount": 25000},
            {"participant_name": "C", "amount": 0},
        ],
    )

    data["exceptions"] = [
        adjustment(
            "A",
            "fixed_amount",
            fixed_amount=5000,
        ),
        adjustment("C", "exclude"),
    ]

    assert checked(data).participant_totals == {
        "A": 5000,
        "B": 25000,
        "C": 0,
    }


def test_contribution_preserves_payer_own_share():
    data = context()
    data["participants"].append("D")

    # 찬조자 추가가 기본 부담 대상자를 변경하면 안 된다.
    assert data["split_rules"][0]["participant_names"] == [
        "A", "B", "C"
    ]

    data["contributions"] = [
        {
            "expense_index": 0,
            "contributor_name": "D",
            "amount": 6000,
            "funding_note": "담당자가 전달·충당 확인",
            "uses": [
                {"item_index": 0, "amount": 6000}
            ],
        }
    ]

    result = checked(data)

    assert result.participant_totals == {
        "A": 8000,
        "B": 8000,
        "C": 8000,
        "D": 0,
    }
    assert result.contribution_amount == 6000

    assert sum(
        transfer.amount
        for transfer in result.settlements
    ) == 16000

    assert (
        16000
        + result.participant_totals["A"]
        + 6000
        == 30000
    )


def test_multiple_payers_are_not_netted():
    data = context(300)

    data["expenses"].append(
        {
            "payer_name": "B",
            "total_amount": 600,
            "items": [
                {"name": "추가 식사", "amount": 600}
            ],
        }
    )
    data["split_rules"].append(
        {
            "expense_index": 1,
            "item_index": 0,
            "method": "equal",
            "participant_names": ["A", "B", "C"],
        }
    )

    result = checked(data)

    assert result.participant_totals == {
        "A": 300,
        "B": 300,
        "C": 300,
    }

    assert [
        (
            transfer.expense_index,
            transfer.from_participant,
            transfer.to_participant,
            transfer.amount,
        )
        for transfer in result.settlements
    ] == [
        (0, "B", "A", 100),
        (0, "C", "A", 100),
        (1, "A", "B", 200),
        (1, "C", "B", 200),
    ]


def test_exclusion_applies_only_to_target_item():
    data = context(120000)

    data["expenses"][0]["items"] = [
        {"name": "식사", "amount": 90000},
        {"name": "술", "amount": 30000},
    ]

    data["split_rules"].append(
        {
            "expense_index": 0,
            "item_index": 1,
            "method": "equal",
            "participant_names": ["A", "B", "C"],
        }
    )

    data["exceptions"] = [
        {
            **adjustment("A", "exclude"),
            "item_index": 1,
        }
    ]

    result = checked(data)

    assert result.participant_totals == {
        "A": 30000,
        "B": 45000,
        "C": 45000,
    }

    assert sum(
        allocation.amount
        for allocation in result.allocations
        if allocation.item_index == 1
        and allocation.participant_name == "A"
    ) == 0


@pytest.mark.parametrize(
    "fault,code",
    [
        ("total", "item_sum_mismatch"),
        ("duplicate_rule", "rule_count"),
        ("bad_reference", "unresolved_expense"),
        ("duplicate_person", "ambiguous_person"),
        ("duplicate_adjustment", "duplicate_adjustment"),
        ("cycle", "cover_chain_or_cycle"),
        ("explicit_sum", "individual_sum_mismatch"),
        ("contribution_sum", "contribution_sum_mismatch"),
    ],
)
def test_invalid_inputs_are_rejected_without_mutation(fault, code):
    data = context()

    if fault == "total":
        data["expenses"][0]["total_amount"] += 1

    elif fault == "duplicate_rule":
        data["split_rules"].append(
            deepcopy(data["split_rules"][0])
        )

    elif fault == "bad_reference":
        data["exceptions"] = [
            {
                **adjustment("A", "exclude"),
                "expense_index": 9,
            }
        ]

    elif fault == "duplicate_person":
        data["participants"].append("A")

    elif fault == "duplicate_adjustment":
        data["exceptions"] = [
            adjustment("A", "exclude"),
            adjustment("A", "exclude"),
        ]

    elif fault == "cycle":
        data["exceptions"] = [
            adjustment(
                "A",
                "covered_by_other",
                covered_by_name="B",
            ),
            adjustment(
                "B",
                "covered_by_other",
                covered_by_name="A",
            ),
        ]

    elif fault == "explicit_sum":
        data["split_rules"][0].update(
            method="explicit_amount",
            individual_amounts=[
                {"participant_name": person, "amount": 1}
                for person in ["A", "B", "C"]
            ],
        )

    elif fault == "contribution_sum":
        data["contributions"] = [
            {
                "expense_index": 0,
                "contributor_name": "A",
                "amount": 6000,
                "funding_note": "확인",
                "uses": [
                    {"item_index": 0, "amount": 5000}
                ],
            }
        ]

    before = deepcopy(data)

    with pytest.raises(CalculationError, match=code):
        calculate_settlement(data)

    assert data == before


    