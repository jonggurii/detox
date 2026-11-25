import json
from types import SimpleNamespace
import pytest
from settlements.gemini_client import generation_limits
from settlements.parser import parse_and_review, ParserAPIError, ManualInputRequired
from test_parser import FakeClient, valid_context

class ProviderError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(str(code))

def test_quota_does_not_retry():
    client = FakeClient([ProviderError(429)])
    with pytest.raises(ParserAPIError):
        parse_and_review('정산', client=client, model='gemini-3-flash-preview')
    assert len(client.requests) == 1

def test_fallback_and_format_share_call_budget(monkeypatch):
    monkeypatch.setenv('GEMINI_FALLBACK_MODEL', 'gemini-3.1-flash-lite')
    client = FakeClient([ProviderError(503), 'invalid JSON'])
    with pytest.raises(ParserAPIError):
        parse_and_review('정산', client=client, model='gemini-3-flash-preview')
    assert len(client.requests) == 2

def test_missing_rule_goes_to_review():
    data = valid_context(); data['split_rules'] = []
    client = FakeClient([json.dumps(data)])
    result = parse_and_review('정산', client=client, model='gemini-3-flash-preview')
    assert result.status == 'needs_clarification'
    assert len(client.requests) == 1

def test_max_tokens_not_retried():
    client = FakeClient([])
    def generate(**kwargs):
        client.requests.append(kwargs)
        return SimpleNamespace(text='{}', candidates=[SimpleNamespace(finish_reason='MAX_TOKENS')])
    client.generate_content = generate
    with pytest.raises(ManualInputRequired):
        parse_and_review('정산', client=client, model='gemini-3-flash-preview')
    assert len(client.requests) == 1

def test_limits():
    assert generation_limits('gemini-3.5-flash')['max_output_tokens'] == 8192
    assert generation_limits('gemini-3-flash-preview', receipt=True)['thinking_config']['thinking_level'] == 'minimal'
