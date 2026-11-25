"""Gemini 독촉문구: 숫자는 서버/로컬 확정 데이터로 고정하며 LLM은 본문만 작성."""
import json
from types import SimpleNamespace

import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

# tests/app.py는 테스트 하니스 전용 앱이므로, 실제 루트 app.py를 독립 이름으로 연다.
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('detox_production_app_for_reminders', ROOT / 'app.py')
ACTUAL_APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTUAL_APP)
create_app = ACTUAL_APP.create_app
from settlements.reminder_writer import generate_reminder


class ModelStub:
    def __init__(self, message=None, error=None):
        self.calls = []
        self.message = message
        self.error = error
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.message)


def context():
    return {
        "participants": ["민수", "지훈", "영희"],
        "expenses": [{"payer_name": "민수", "total_amount": 90000,
                      "items": [{"name": "식사비", "amount": 90000}]}],
        "split_rules": [{"expense_index": 0, "item_index": 0, "method": "equal",
                         "participant_names": ["민수", "지훈", "영희"]}],
    }


def make_session(client, ctx=None):
    r = client.post('/api/sessions/manual', json={'source_text': '직접 정산', 'context': ctx or context()})
    assert r.status_code == 200, r.text
    sid = r.json()['session_id']
    c = client.post(f'/api/sessions/{sid}/confirm', json={
        'input_revision': 1, 'reviewed_by': '담당자', 'review_notes': '모든 조건 확인',
        'checks': {'source_reviewed': True, 'people_resolved': True, 'conditions_reviewed': True},
    })
    assert c.status_code == 200, c.text
    calc = client.post(f'/api/sessions/{sid}/calculate', json={'confirmation_id': c.json()['confirmation_id']})
    assert calc.status_code == 200, calc.text
    return sid, calc.json()['calculation_id']


def body(sid, cid):
    return {'session_id': sid, 'calculation_id': cid, 'from_participant': '지훈',
            'to_participant': '민수', 'title': '11조 회식', 'tone': 'friend', 'repeat': False}


def test_model_sees_no_person_or_money_and_server_locks_header(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    model = ModelStub(json.dumps({'message': '정산 내용 확인 부탁해! 편할 때 보내주면 고맙겠어.'}, ensure_ascii=False))
    monkeypatch.setattr('settlements.reminder_writer._client', lambda: model)
    with TestClient(create_app(tmp_path/'reminders.sqlite3')) as client:
        sid, cid = make_session(client)
        r = client.post('/api/reminders/generate', json=body(sid, cid))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['source'] == 'gemini'
        assert data['amount_source'] == 'confirmed_calculation'
        assert '지훈 → 민수: 30,000원' in data['message']
        prompt = model.calls[0]['contents']
        assert all(word not in prompt for word in ('지훈', '민수', '30,000', '11조 회식'))
        assert model.calls[0]['model'] == 'gemini-3-flash-preview'


def test_spurious_amount_and_name_are_rejected():
    for bad in ('이번에는 100,000원 보내줘.', '지훈님이 다른 사람에게 보내세요.',
                'https://example.com 에서 확인해 주세요.'):
        model = ModelStub(json.dumps({'message': bad}, ensure_ascii=False))
        result = generate_reminder(title='테스트', from_name='지훈', to_name='민수',
                                   amount=30000, tone='senior', repeat=True, client=model)
        assert result['source'] == 'template'
        assert '30,000원' in result['message']
        assert bad not in result['message']


def test_503_504_and_malformed_json_fallback():
    for stub in (ModelStub(error=RuntimeError('503 UNAVAILABLE')),
                 ModelStub(error=TimeoutError('504 DEADLINE_EXCEEDED')),
                 ModelStub('not-json')):
        result = generate_reminder(title='회식', from_name='지훈', to_name='민수', amount=10000,
                                   tone='friend', repeat=False, client=stub)
        assert result['source'] == 'template'
        assert result['model'] is None
        assert '10,000원' in result['message']


def test_server_rejects_wrong_calculation_and_unconfirmed_pair(tmp_path):
    with TestClient(create_app(tmp_path/'reminders.sqlite3')) as client:
        sid, cid = make_session(client)
        assert client.post('/api/reminders/generate', json=body(sid, 'fake')).status_code == 409
        wrong = {**body(sid, cid), 'to_participant': '영희'}
        assert client.post('/api/reminders/generate', json=wrong).status_code == 422
        wrong_amount = {**body(sid, cid), 'local_amount': 10}
        assert client.post('/api/reminders/generate', json=wrong_amount).status_code == 422
        assert client.post('/api/reminders/generate', json={**body(sid, cid), 'from_participant': '민수'}).status_code == 422


def test_stale_calculation_and_external_only_are_blocked(tmp_path):
    with TestClient(create_app(tmp_path/'reminders.sqlite3')) as client:
        sid, cid = make_session(client)
        assert client.patch(f'/api/sessions/{sid}/context', json={
            'input_revision': 1, 'context': context(),
        }).status_code == 200
        assert client.post('/api/reminders/generate', json=body(sid, cid)).status_code == 409

        ctx = context()
        ctx['reminder_handling'] = 'external_service_only'
        sid2, cid2 = make_session(client, ctx)
        assert client.post('/api/reminders/generate', json=body(sid2, cid2)).status_code == 409


def test_local_diff_no_server_persistence(monkeypatch, tmp_path):
    model = ModelStub(json.dumps({'message': '정산 내용을 확인해 주면 고마워! 이미 보냈다면 알려줘.'}, ensure_ascii=False))
    monkeypatch.setattr('settlements.reminder_writer._client', lambda: model)
    with TestClient(create_app(tmp_path/'reminders.sqlite3')) as client:
        r = client.post('/api/reminders/generate', json={
            'session_id': 'local-diff-123', 'from_participant': '영희',
            'to_participant': '민수', 'local_amount': 15000, 'title': '차액 정산',
            'tone': 'junior', 'repeat': True,
        })
        assert r.status_code == 200, r.text
        assert '영희 → 민수: 15,000원' in r.json()['message']
        assert r.json()['amount_source'] == 'local_manual'
        assert client.get('/api/sessions').json() == []
        assert client.post('/api/reminders/generate', json={
            'session_id': 'local-diff-123', 'from_participant': '영희',
            'to_participant': '민수', 'local_amount': -15000,
        }).status_code == 422
        assert client.post('/api/reminders/generate', json={
            'session_id': 'local-diff-123', 'from_participant': '영희',
            'to_participant': '민수',
        }).status_code == 422


def test_basic_rate_limit_on_public_reminder_api(tmp_path, monkeypatch):
    model = ModelStub(json.dumps({'message': '정산 내용 확인 부탁해! 편할 때 보내줘도 괜찮아.'}, ensure_ascii=False))
    monkeypatch.setattr('settlements.reminder_writer._client', lambda: model)
    with TestClient(create_app(tmp_path/'ratelimit.sqlite3')) as client:
        payload = {'session_id': 'local-diff-123', 'from_participant': '영희',
                   'to_participant': '민수', 'local_amount': 15000, 'tone': 'friend'}
        assert all(client.post('/api/reminders/generate', json=payload).status_code == 200
                   for _ in range(12))
        assert client.post('/api/reminders/generate', json=payload).status_code == 429
