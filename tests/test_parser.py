import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from detox.parser import parse_settlement_request
from detox.schemas.detox_context import SettlementRequestContext


class ParserTests(unittest.TestCase):
    def test_parse_settlement_request_validates_anthropic_json(self):
        response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    text=json.dumps(
                        {
                            "total_rounds": 2,
                            "payer_name": None,
                            "rounds_info": [
                                {"round": 1, "cost": 100000, "excluded_members": []},
                                {
                                    "round": 2,
                                    "cost": 50000,
                                    "excluded_members": ["민수", "철수"],
                                },
                            ],
                            "reminder_tone": "humorous",
                        }
                    )
                )
            ]
        )

        class FakeMessages:
            def create(self, **kwargs):
                self.last_request = kwargs
                return response

        messages = FakeMessages()

        class FakeAnthropic:
            def __init__(self, api_key):
                self.messages = messages
                if api_key != "test-key":
                    raise AssertionError("unexpected API key")

        fake_module = types.SimpleNamespace(Anthropic=FakeAnthropic)
        with patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False
        ), patch.dict(sys.modules, {"anthropic": fake_module}):
            result = parse_settlement_request("1차와 2차 정산을 해줘")

        self.assertIsInstance(result, SettlementRequestContext)
        self.assertEqual(result.total_rounds, 2)
        self.assertEqual(result.rounds_info[1].excluded_members, ["민수", "철수"])
        self.assertEqual(messages.last_request["temperature"], 0.0)

    def test_parse_settlement_request_rejects_invalid_round(self):
        response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    text='{"total_rounds":1,"rounds_info":[{"round":0,"cost":100}]}'
                )
            ]
        )

        class FakeAnthropic:
            def __init__(self, api_key):
                self.messages = SimpleNamespace(
                    create=lambda **kwargs: response
                )

        fake_module = types.SimpleNamespace(Anthropic=FakeAnthropic)
        with patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=False
        ), patch.dict(sys.modules, {"anthropic": fake_module}):
            with self.assertRaisesRegex(ValueError, "온톨로지 스키마 위반"):
                parse_settlement_request("차수 정보")


if __name__ == "__main__":
    unittest.main()