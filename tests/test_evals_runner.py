"""Evals 러너의 오류 검출 능력을 검증한다. 기존 골든 테스트는 변경하지 않는다."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'evals'/'run_evals.py'
spec=importlib.util.spec_from_file_location('moa_evals_runner',SCRIPT)
assert spec and spec.loader
runner=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=runner
spec.loader.exec_module(runner)


def load():
    cases=runner.read_jsonl(ROOT/'evals'/'evalset.jsonl')
    fixtures={o['id']:o for o in runner.read_jsonl(ROOT/'evals'/'fixtures'/'stored_outputs.jsonl')}
    return cases,fixtures


def one_case(cases,ident):
    return next(x for x in cases if x['id']==ident)


def grade_one(ident,mutate):
    cases,fixtures=load()
    fixture=deepcopy(fixtures[ident])
    mutate(fixture)
    records, metrics=runner.run([one_case(cases,ident)],'stored',{ident:fixture})
    return records[0], metrics


def test_evalset_is_complete_and_traceable():
    cases,fixtures=load()
    runner.validate_evalset(cases)
    assert len(cases)>=20
    assert len(fixtures)==len(cases)
    assert {c['id'] for c in cases}==set(fixtures)
    assert {'normal','clarify','conflict','injection','hallucination'}<={c['category'] for c in cases}


def test_baseline_fixture_harness_runs_without_sdk_or_key():
    cases,fixtures=load()
    records,metrics=runner.run(cases,'stored',fixtures)
    assert len(records)==len(cases)
    assert metrics['overall']['passed']==len(cases)


def test_amount_corruption_is_detected():
    def corrupt(f): f['context']['expenses'][0]['total_amount']=1
    record, metrics=grade_one('T01',corrupt)
    assert not record['pass']
    assert metrics['overall']['passed']==0
    assert not record['checks']['expenses']['pass']
    assert record['unfounded_amounts']==[1]


def test_injection_added_fictitious_person_is_detected():
    record,_=grade_one('T25',lambda f:f['context']['participants'].append('해커'))
    assert not record['pass']
    assert '해커' in record['unfounded_people']


def test_clarification_bypass_is_detected():
    def corrupt(f): f['context']['expenses'][0]['payer_name']='민수'
    record,_=grade_one('T14',corrupt)
    assert not record['pass']
    assert record['checks']['must_have_issue_codes']['pass'] is False


def test_receipt_mismatch_silencing_is_detected():
    def corrupt(f): f['receipt_output']['total_amount']=68000
    record,_=grade_one('R04',corrupt)
    assert not record['pass']
    assert not record['checks']['total_amount']['pass']
    assert not record['checks']['warning_contains']['pass']


def test_invalid_fixture_schema_is_not_silently_skipped():
    def corrupt(f): f['context']['invented_field']='wrong'
    record,metrics=grade_one('T01',corrupt)
    assert not record['pass']
    assert record['error']
    assert not record['schema_valid']
    assert metrics['overall']['total']==1


def test_unsupported_expect_key_rejected():
    cases,_=load()
    bad=deepcopy(cases)
    bad[0]['expect']['totally_ungraded_field']=123
    with pytest.raises(ValueError,match='미지원 expect 키'):
        runner.validate_evalset(bad)
