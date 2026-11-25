"""G09~G25: YAML contract cases run real code paths, no skips/xfails or Gemini API.

MVP1 and MVP2 validate orchestration with controlled model stubs; actual model
quality requires separate evals live and UX tests. MVP4 validates the same JS
function used by the Expo screen; button interaction still needs a device check.
"""
from copy import deepcopy
from importlib.util import spec_from_file_location, module_from_spec
import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest
import yaml

from settlements.calculator import calculate_settlement
from settlements.parser import review_context, validate_context_data, load_contract
from settlements.receipt_reader import parse_receipt_output

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / 'tests' / 'harness' / 'golden_cases.yaml'
EXPECTED_AC = (
    {f'AC{i}' for i in range(1, 7)}
    | {f'MVP{i}' for i in range(1, 7)}
    | {f'CALC{i}' for i in range(1, 4)}
    | {f'CLAIM{i}' for i in range(1, 3)}
    | {f'EXTRACT{i}' for i in range(1, 7)}
)
TARGETS = {'calculation','api_parse','api_lifecycle','receipt_preview',
           'receipt_contract','model_contract','parser_review','local_diff'}


def load_cases():
    data = yaml.safe_load(CASES_PATH.read_text(encoding='utf-8'))
    cases = data['acceptance_cases']
    assert isinstance(cases, list) and cases, '추가 골든 케이스가 없습니다.'
    original = data['cases']
    everything = original + cases
    assert len({case['id'] for case in everything}) == len(everything), '케이스 ID 중복'
    covered = set().union(*(set(c['ac_ids']) for c in everything))
    assert covered == EXPECTED_AC, f'AC coverage mismatch: missing={sorted(EXPECTED_AC-covered)} extra={sorted(covered-EXPECTED_AC)}'
    for c in cases:
        assert c['target'] in TARGETS, c['id']
        assert c.get('category') in {'normal','boundary','prohibited'}, c['id']
        assert c.get('expected') and c.get('ac_ids') and c.get('note'), c['id']
    return cases


CASES = load_cases()


def root_app():
    """Load project root app.py, not tests/app.py from pytest's import path."""
    spec = spec_from_file_location('moa_acceptance_app', ROOT / 'app.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_app


def base_context():
    return {
        'participants':['A','B','C'],
        'expenses':[{'payer_name':'A','total_amount':30000,'items':[{'name':'식사','amount':30000}]}],
        'split_rules':[{'expense_index':0,'item_index':0,'method':'equal','participant_names':['A','B','C']}],
    }


def api_client(monkeypatch, tmp_path, *, context=None):
    from types import SimpleNamespace
    monkeypatch.setenv('SETTLEMENT_TRACE_PATH', str(tmp_path/'trace.jsonl'))
    ctx=context or base_context()
    def fake_parser(text, supplied_evidence=None):
        return SimpleNamespace(context=validate_context_data(ctx),source_text=text,
            supplied_evidence=supplied_evidence,model='golden-stub',
            prompt_version=load_contract()[2],schema_sha256=load_contract()[3],attempts=0)
    return TestClient(root_app()(tmp_path/'golden.sqlite3', parser=fake_parser))


def start(client, context=None):
    r=client.post('/api/sessions/manual',json={'source_text':'골든 가상 입력', 'context':context or base_context()})
    assert r.status_code==200,r.text
    return r.json()['session_id']


def confirm(client,sid):
    body={'input_revision':1,'reviewed_by':'가상 검토자','review_notes':'정답 검토',
          'checks':{'source_reviewed':True,'people_resolved':True,'conditions_reviewed':True,'funding_verified':True}}
    return client.post(f'/api/sessions/{sid}/confirm',json=body)


def run_case(case,monkeypatch,tmp_path):
    target=case['target']
    expected=case['expected']
    if target=='calculation':
        ctx=deepcopy(case['context'])
        original=json.dumps(ctx,ensure_ascii=False,sort_keys=True)
        result=calculate_settlement(ctx)
        actual=result.participant_totals
        assert actual==expected['totals'],(case['id'],actual,expected['totals'])
        if 'total' in expected:
            assert sum(actual.values())==expected['total']
        if 'transfers' in expected:
            transfers=sorted((t.from_participant,t.to_participant,t.amount) for t in result.settlements)
            goals=sorted((t['from'],t['to'],t['amount']) for t in expected['transfers'])
            assert transfers==goals,(case['id'],transfers,goals)
        if expected.get('no_self_or_zero'):
            assert all(t.from_participant!=t.to_participant and t.amount>0 for t in result.settlements)
        assert json.dumps(ctx,ensure_ascii=False,sort_keys=True)==original
        return

    if target=='api_parse':
        with api_client(monkeypatch,tmp_path,context=case['context']) as client:
            r=client.post('/api/sessions',json={'text':'영희는 술값 제외, 총 84000원 가상 사례'})
            assert r.status_code==200,r.text
            doc=r.json()
            c=doc['revisions'][-1]['context']
            assert c['participants']==expected['participants']
            assert c['expenses'][0]['total_amount']==expected['expense_amount']
            assert len(doc['calculations'])==0, '파싱 즉시 계산되면 안 됩니다.'
        return

    if target=='api_lifecycle':
        with api_client(monkeypatch,tmp_path) as client:
            sid=start(client)
            mode=case['mode']
            if mode=='reject_unconfirmed':
                r=client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':'not-approved'})
                assert r.status_code==expected['status']
            elif mode=='calculated_results':
                approved=confirm(client,sid)
                assert approved.status_code==200,approved.text
                r=client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':approved.json()['confirmation_id']})
                assert r.status_code==200,r.text
                out=r.json()['result']
                assert out['participant_totals']==expected['totals']
                amounts=sorted(t['amount'] for t in out['settlements'])
                assert amounts==sorted(expected['transfer_amounts'])
            elif mode=='repeat_calculate':
                approved=confirm(client,sid)
                assert approved.status_code==200,approved.text
                endpoint=f'/api/sessions/{sid}/calculate'
                payload={'confirmation_id':approved.json()['confirmation_id']}
                first=client.post(endpoint,json=payload).json()
                second=client.post(endpoint,json=payload).json()
                doc=client.get(f'/api/sessions/{sid}').json()
                assert (first['calculation_id']==second['calculation_id']) is expected['same_calculation_id']
                assert len(doc['calculations'])==expected['calculation_count']
            elif mode=='reject_old_approval':
                approved=confirm(client,sid)
                assert approved.status_code==200,approved.text
                edited=base_context()
                edited['expenses'][0]['total_amount']=60000
                edited['expenses'][0]['items'][0]['amount']=60000
                changed=client.patch(f'/api/sessions/{sid}/context',json={'input_revision':1,'context':edited})
                assert changed.status_code==200,changed.text
                assert changed.json()['revisions'][-1]['input_revision']==expected['input_revision']
                old=client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':approved.json()['confirmation_id']})
                assert old.status_code==expected['status']
            else:
                raise AssertionError(f'알 수 없는 API 모드: {mode}')
        return

    if target=='receipt_preview':
        from backend import multimodal_router
        class FakeGeminiReceiptReader:
            def extract_bytes(self,raw):
                assert raw==case['input']['file_data'].encode('utf-8')
                return {'items':[{'name':'식사','amount':30000}], 'total_amount':30000, 'warnings':[]}
        monkeypatch.setattr(multimodal_router,'GeminiReceiptReader',FakeGeminiReceiptReader)
        with api_client(monkeypatch,tmp_path) as client:
            response=client.post('/api/receipts/multimodal-preview',
                data={'text':case['input']['text']},
                files={'file':('receipt.jpg',case['input']['file_data'].encode('utf-8'),'image/jpeg')})
            assert response.status_code==200,response.text
            result=response.json()
            assert result['total_amount']==expected['total_amount']
            assert result['review_required'] is expected['review_required']
            assert result['original_text']==expected['original_text']
            sessions=client.get('/api/sessions')
            assert sessions.status_code==200
            assert len(sessions.json())==expected['session_count']
        return

    if target=='receipt_contract':
        result=parse_receipt_output(json.dumps(case['input'],ensure_ascii=False))
        assert result['total_amount']==expected['total_amount']
        if 'first_item_amount' in expected:
            assert result['items'][0]['amount']==expected['first_item_amount']
        if 'warning_contains' in expected:
            assert any(expected['warning_contains'] in w for w in result['warnings']),result['warnings']
        return

    if target=='model_contract':
        from settlements import parser,receipt_reader,gemini_client
        # EXTRACT2: text and receipt choose independent model settings.
        assert parser.get_model is gemini_client.get_model
        assert receipt_reader.get_multimodal_model is gemini_client.get_multimodal_model
        assert (parser.get_model is not receipt_reader.get_multimodal_model) is expected['separate_model_settings']
        assert (parser.DEFAULT_PROMPT_PATH != receipt_reader.PROMPT_PATH) is expected['different_prompts']
        assert (parser.load_contract()[1] != receipt_reader.RECEIPT_SCHEMA) is expected['different_schemas']
        return

    if target=='parser_review':
        ctx=deepcopy(case['context'])
        before=json.dumps(ctx,ensure_ascii=False,sort_keys=True)
        issues=review_context(ctx)
        assert len(issues)==expected['issue_count'],[i.model_dump() for i in issues]
        assert (json.dumps(ctx,ensure_ascii=False,sort_keys=True)==before) is expected['unchanged']
        return

    if target=='local_diff':
        # The code imported by mobile/src/app/index.tsx, not an independent Python port.
        script=(
            "import {validateDirectTransfers} from "
            + json.dumps((ROOT/'mobile/src/utils/directTransfers.mjs').as_uri()) + ";\n"
            + "console.log(JSON.stringify(validateDirectTransfers(" +
                json.dumps(case['input']['total']) + "," +
                json.dumps(case['input']['people']) + "," +
                json.dumps(case['input']['transfers']) + ")));"
        )
        result=subprocess.run(['node','--input-type=module','-e',script],
                              check=True,text=True,encoding='utf-8',capture_output=True,timeout=10)
        actual=json.loads(result.stdout.strip())
        assert actual['valid'] is expected['valid']
        assert actual['sum']==expected['sum']
        assert [t['from_participant'] for t in actual['transfers']]==expected['from_list']
        assert [t['to_participant'] for t in actual['transfers']]==expected['to_list']
        # Prohibited variants must be rejected by the exact same JS routine.
        for invalid in [
            {'total':'36000','people':case['input']['people'],'rows':case['input']['transfers']},
            {'total':'35000','people':case['input']['people'],'rows':[{'from':'민수','to':'민수','amount':'35000'}]},
            {'total':'35000','people':case['input']['people'],'rows':[{'from':'외부','to':'민수','amount':'35000'}]},
        ]:
            program=("import {validateDirectTransfers as check} from " +
                     json.dumps((ROOT/'mobile/src/utils/directTransfers.mjs').as_uri()) + ";" +
                     "console.log(JSON.stringify(check(" + json.dumps(invalid['total']) + "," +
                     json.dumps(invalid['people']) + "," + json.dumps(invalid['rows']) + ")));" )
            output=subprocess.run(['node','--input-type=module','-e',program],
                                  check=True,text=True,encoding='utf-8',capture_output=True,timeout=10)
            assert json.loads(output.stdout)['valid'] is False
        return

    raise AssertionError(f'Unknown golden target {target}')


@pytest.mark.parametrize('case',CASES,ids=[case['id']+':'+case['name'] for case in CASES])
def test_acceptance_golden(case,monkeypatch,tmp_path):
    run_case(case,monkeypatch,tmp_path)
