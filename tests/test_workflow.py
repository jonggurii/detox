from types import SimpleNamespace
import json
import sqlite3
import pytest

from settlements.parser import OutputFormatError, load_contract, validate_context_data
from settlements.workflow import WorkflowError, WorkflowStore


def context(amount=30000):
    return {"participants": ["A", "B", "C"],
            "expenses": [{"payer_name": "A", "total_amount": amount,
                          "items": [{"name": "식사", "amount": amount}]}],
            "split_rules": [{"expense_index": 0, "item_index": 0, "method": "equal",
                             "participant_names": ["A", "B", "C"]}]}


def parsed(data):
    return SimpleNamespace(context=validate_context_data(data), source_text="테스트 원문",
                           supplied_evidence=None, model="mock-model", prompt_version=1,
                           schema_sha256=load_contract()[3], attempts=1)


def confirm(store, sid, revision=1, **overrides):
    args = {"reviewed_by": "담당자", "review_notes": "원문·실제 사람·조건 대조",
            "checks": {"source_reviewed": True, "people_resolved": True,
                       "conditions_reviewed": True, "funding_verified": True}}
    args.update(overrides)
    return store.confirm(sid, revision, **args)


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(tmp_path / "workflow.sqlite3")


def test_clarify_edit_confirm_calculate(store):
    data = context()
    data["expenses"][0]["payer_name"] = None
    sid = store.start(parsed(data))
    with pytest.raises(WorkflowError):
        confirm(store, sid)
    assert store.view(sid)["confirmations"] == []
    store.revise(sid, 1, context())
    record = confirm(store, sid, 2)
    result = store.calculate(sid, record["confirmation_id"])
    assert result["input_revision"] == 2
    assert result["result"]["participant_totals"] == {"A": 10000, "B": 10000, "C": 10000}
    doc = store.view(sid)
    assert doc["source_text"] == "테스트 원문"
    assert doc["revisions"][0]["context"]["expenses"][0]["payer_name"] is None


def test_reject_unconfirmed_calculation(store):
    sid = store.start(parsed(context()))
    with pytest.raises(WorkflowError):
        store.calculate(sid, "invented-id")


def test_edit_invalidates_old_confirmation_and_preview(store):
    sid = store.start(parsed(context()))
    old = confirm(store, sid)
    store.calculate(sid, old["confirmation_id"])
    store.revise(sid, 1, context(60000))
    with pytest.raises(WorkflowError):
        store.calculate(sid, old["confirmation_id"])
    new = confirm(store, sid, 2)
    assert store.calculate(sid, new["confirmation_id"])["result"]["participant_totals"]["A"] == 20000
    assert len(store.view(sid)["calculations"]) == 2


def test_stale_revision_is_rejected(store):
    sid = store.start(parsed(context()))
    store.revise(sid, 1, context(60000))
    with pytest.raises(WorkflowError):
        store.revise(sid, 1, context())
    with pytest.raises(WorkflowError):
        confirm(store, sid, 1)
    assert len(store.view(sid)["revisions"]) == 2


def test_repeated_confirmation_and_calculation_are_idempotent(store):
    sid = store.start(parsed(context()))
    record = confirm(store, sid)
    assert confirm(store, sid)["confirmation_id"] == record["confirmation_id"]
    first = store.calculate(sid, record["confirmation_id"])
    second = store.calculate(sid, record["confirmation_id"])
    assert first["calculation_id"] == second["calculation_id"]
    assert len(store.view(sid)["calculations"]) == 1


def test_reopen_preserves_records(store):
    sid = store.start(parsed(context()))
    record = confirm(store, sid)
    reopened = WorkflowStore(store.path)
    assert reopened.calculate(sid, record["confirmation_id"])["input_revision"] == 1
    assert reopened.view(sid)["confirmations"][0]["reviewed_by"] == "담당자"


def test_funding_note_is_not_confirmation(store):
    data = context()
    data["contributions"] = [{"expense_index": 0, "contributor_name": "A", "amount": 6000,
                              "funding_note": "아직 전달하지 않았음",
                              "uses": [{"item_index": 0, "amount": 6000}]}]
    sid = store.start(parsed(data))
    with pytest.raises(WorkflowError):
        confirm(store, sid, checks={"source_reviewed": True, "people_resolved": True,
                                   "conditions_reviewed": True, "funding_verified": False})
    assert not store.view(sid)["confirmations"]


def test_cross_session_confirmation_is_rejected(store):
    first = store.start(parsed(context()))
    second = store.start(parsed(context()))
    record = confirm(store, first)
    with pytest.raises(WorkflowError):
        store.calculate(second, record["confirmation_id"])


def test_bad_edit_does_not_change_stored_data(store):
    sid = store.start(parsed(context()))
    before = store.view(sid)
    with pytest.raises(OutputFormatError):
        store.revise(sid, 1, {})
    assert store.view(sid) == before


def test_changed_context_hash_is_rejected(store):
    sid = store.start(parsed(context()))
    record = confirm(store, sid)
    doc = store.view(sid)
    doc["revisions"][-1]["context"]["expenses"][0]["payer_name"] = "B"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE sessions SET document=? WHERE id=?", (json.dumps(doc), sid))
    with pytest.raises(WorkflowError):
        store.calculate(sid, record["confirmation_id"])


def test_returned_data_is_detached_from_storage(store):
    sid = store.start(parsed(context()))
    record = confirm(store, sid)
    doc = store.view(sid)
    doc["revisions"][-1]["context"]["expenses"][0]["payer_name"] = "B"
    assert store.calculate(sid, record["confirmation_id"])["result"]["settlements"][0]["to_participant"] == "A"


@pytest.mark.parametrize("key", ["source_reviewed", "people_resolved", "conditions_reviewed"])
def test_explicit_review_checks_are_required(store, key):
    sid = store.start(parsed(context()))
    checks = {"source_reviewed": True, "people_resolved": True, "conditions_reviewed": True}
    checks[key] = "true"
    with pytest.raises(WorkflowError):
        confirm(store, sid, checks=checks)
