"""Live request trace must be a single, privacy-safe JSONL entry per API request."""
import json

from fastapi.testclient import TestClient
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

root_app = Path(__file__).resolve().parents[1] / 'app.py'
spec = spec_from_file_location('moa_root_trace_app', root_app)
module = module_from_spec(spec)
spec.loader.exec_module(module)
create_app = module.create_app


def test_trace_records_sanitized_success_and_failure(monkeypatch, tmp_path):
    trace_path = tmp_path / 'traces' / 'trace.jsonl'
    monkeypatch.setenv('SETTLEMENT_TRACE_PATH', str(trace_path))
    with TestClient(create_app(tmp_path / 'trace.sqlite3')) as client:
        ok = client.get('/api/schema')
        assert ok.status_code == 200
        assert ok.headers['X-Request-ID'].startswith('q-')
        # This name is private input content, and must not appear in a trace.
        bad = client.post('/api/sessions', json={'text': ''})
        assert bad.status_code == 422
        assert bad.headers['X-Request-ID'].startswith('q-')
    content = trace_path.read_text(encoding='utf-8')
    events = [json.loads(line) for line in content.splitlines()]
    assert len(events) == 2
    assert {event['output']['status_code'] for event in events} == {200, 422}
    assert all(event['route'].startswith('/api/') for event in events)
    assert all('latency_ms' in event and 'commit' in event and 'model' in event for event in events)
    assert 'GEMINI_API_KEY' not in content


def test_trace_never_records_url_session_id(monkeypatch, tmp_path):
    trace_path = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('SETTLEMENT_TRACE_PATH', str(trace_path))
    with TestClient(create_app(tmp_path / 'trace.sqlite3')) as client:
        response = client.get('/api/sessions/private-session-123')
        assert response.status_code == 404
    content = trace_path.read_text(encoding='utf-8')
    assert 'private-session-123' not in content
    event = json.loads(content.strip())
    assert event['route'] == '/api/sessions/{sid}'
