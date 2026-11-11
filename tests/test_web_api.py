from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import create_app
from settlements.parser import load_contract, validate_context_data, ManualInputRequired


def data():
    return {'participants':['A','B','C'], 'expenses':[{'payer_name':'A','total_amount':30000,'items':[{'name':'식사','amount':30000}]}], 'split_rules':[{'expense_index':0,'item_index':0,'method':'equal','participant_names':['A','B','C']}]}


def fake_parse(text):
    return SimpleNamespace(context=validate_context_data(data()),source_text=text,supplied_evidence=None,
                           model='mock',prompt_version=load_contract()[2],schema_sha256=load_contract()[3],attempts=1)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'app.sqlite3',parser=fake_parse)) as c:
        yield c


def start(client, ctx=None):
    response=client.post('/api/sessions/manual',json={'source_text':'테스트','context':ctx or data()})
    assert response.status_code==200
    return response.json()['session_id']


def confirm(client,sid,rev=1,funding=True):
    return client.post(f'/api/sessions/{sid}/confirm',json={'input_revision':rev,'reviewed_by':'담당자','review_notes':'조건 대조', 'checks':{'source_reviewed':True,'people_resolved':True,'conditions_reviewed':True,'funding_verified':funding}})


def test_serves_frontend(client):
    r=client.get('/')
    assert r.status_code==200 and '모아정산' in r.text


def test_schema_served_without_credentials(client):
    r=client.get('/api/schema')
    assert set(r.json()['required'])=={'participants','expenses'}
    assert 'GEMINI_API_KEY' not in r.text


def test_parse_creates_session(client):
    r=client.post('/api/sessions',json={'text':'정산 문장'})
    assert r.status_code==200 and r.json()['parse_metadata']['model']=='mock'


def test_manual_save_list_reopen(client):
    sid=start(client)
    assert client.get('/api/sessions').json()[0]['session_id']==sid
    assert client.get(f'/api/sessions/{sid}').json()['revisions'][0]['context']==data()


def test_confirm_then_calculate(client):
    sid=start(client);cid=confirm(client,sid).json()['confirmation_id']
    r=client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':cid})
    assert r.status_code==200
    assert r.json()['result']['participant_totals']=={'A':10000,'B':10000,'C':10000}


def test_unconfirmed_calculation_blocked(client):
    sid=start(client)
    assert client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':'wrong'}).status_code==409


def test_edit_invalidates_confirmation(client):
    sid=start(client);cid=confirm(client,sid).json()['confirmation_id']
    ctx=data();ctx['expenses'][0]['total_amount']=60000;ctx['expenses'][0]['items'][0]['amount']=60000
    r=client.patch(f'/api/sessions/{sid}/context',json={'input_revision':1,'context':ctx})
    assert r.status_code==200 and r.json()['revisions'][-1]['input_revision']==2
    assert client.post(f'/api/sessions/{sid}/calculate',json={'confirmation_id':cid}).status_code==409


def test_old_revision_write_blocked(client):
    sid=start(client);body={'input_revision':1,'context':data()}
    assert client.patch(f'/api/sessions/{sid}/context',json=body).status_code==200
    assert client.patch(f'/api/sessions/{sid}/context',json=body).status_code==409


def test_clarification_blocks_confirm(client):
    ctx=data();ctx['expenses'][0]['payer_name']=None
    sid=start(client,ctx)
    assert confirm(client,sid).status_code==409


def test_repeat_calculation_reuses_record(client):
    sid=start(client);cid=confirm(client,sid).json()['confirmation_id'];body={'confirmation_id':cid}
    first=client.post(f'/api/sessions/{sid}/calculate',json=body).json()
    second=client.post(f'/api/sessions/{sid}/calculate',json=body).json()
    assert first['calculation_id']==second['calculation_id']


def test_funding_requires_explicit_check(client):
    ctx=data();ctx['contributions']=[{'expense_index':0,'contributor_name':'A','amount':6000,'funding_note':'미전달','uses':[{'item_index':0,'amount':6000}]}]
    sid=start(client,ctx)
    assert confirm(client,sid,funding=False).status_code==409


def test_cross_origin_blocked(client):
    r=client.post('/api/sessions',json={'text':'정산'},headers={'Origin':'https://example.com'})
    assert r.status_code==403


def test_invalid_shape_and_missing_session(client):
    assert client.post('/api/sessions/manual',json={'source_text':'test','context':{}}).status_code==422
    assert client.get('/api/sessions/missing').status_code==404


def test_manual_fallback_error_is_clear(tmp_path):
    def broken(text):raise ManualInputRequired('invalid')
    with TestClient(create_app(tmp_path/'fallback.sqlite3',parser=broken)) as c:
        r=c.post('/api/sessions',json={'text':'test'})
        assert r.status_code==422 and '직접 입력' in r.json()['detail']
