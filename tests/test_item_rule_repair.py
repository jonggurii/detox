"""Regression: three separate cafe items bundled into one rule."""
from copy import deepcopy
from settlements.parser import repair_unambiguous_item_rules, review_context


def case(amounts=(8000, 10000, 12000)):
    return {
        "participants": ["건", "종현", "민수"],
        "expenses": [{"payer_name": "종현", "total_amount": sum(amounts),
                      "items": [{"name": n, "amount": a} for n, a in zip(["아메리카노", "라떼", "디저트"], amounts)]}],
        "split_rules": [{"expense_index": 0, "item_index": 0, "method": "explicit_amount",
                         "participant_names": ["건", "종현", "민수"],
                         "individual_amounts": [{"participant_name": n, "amount": a} for n, a in zip(["건", "종현", "민수"], amounts)]}],
    }


def test_unique_amounts_repaired_without_mutation():
    data = case()
    original = deepcopy(data)
    repaired = repair_unambiguous_item_rules(data)
    assert data == original
    assert len(repaired.split_rules) == 3
    assert [r["item_index"] for r in repaired.split_rules] == [0, 1, 2]
    assert not [issue for issue in review_context(repaired) if issue.code == "rule_count"]


def test_ambiguous_equal_prices_are_not_guessed():
    data = case((8000, 8000, 12000))
    repaired = repair_unambiguous_item_rules(data)
    assert len(repaired.split_rules) == 1
    assert any(issue.code == "rule_count" for issue in review_context(repaired))


def test_other_existing_rule_is_not_overwritten():
    data = case()
    data["split_rules"].append({"expense_index": 0, "item_index": 1, "method": "equal", "participant_names": ["종현"]})
    repaired = repair_unambiguous_item_rules(data)
    assert len(repaired.split_rules) == 2
