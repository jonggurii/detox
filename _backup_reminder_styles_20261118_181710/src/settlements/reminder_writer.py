"""확정 정산 숫자는 코드로 고정하고 Gemini는 안내 문장만 작성한다.

모델에 이름, 정산명, 금액, 계좌 등 개인/금융 정보를 보내지 않는다.
모델 장애나 부적절한 출력은 템플릿으로 복구하며 자동 발송은 수행하지 않는다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json
import logging
import re

from .gemini_client import get_model

LOG = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).with_name("prompts") / "reminder_message.md"
TONES = {"friend": "친근한 친구 사이", "senior": "존댓말로 정중하게", "junior": "친근하고 부담스럽지 않게"}
BODY_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def _client():
    # 영수증/자연어와 동일한 API 키를 사용하되, 독촉 화면은 15초 안에 폴백한다.
    import os
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Gemini API 키가 없습니다")
    from google import genai
    return genai.Client(api_key=key, http_options={"timeout": 15000, "retry_options": {"attempts": 1}})


def _safe_body(raw: str, *, from_name: str, to_name: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("문자열이 아닌 응답")
    body = " ".join(raw.split())
    if not 12 <= len(body) <= 170:
        raise ValueError("문구 길이가 범위를 벗어남")
    # 문구 본문은 무금액·무실명이어야 한다. 유일한 송금 정보는 코드가 만든 머리말.
    if (re.search(r"[0-9０-９]|[₩$€]|https?://|www\.|@|[\r\n]", body, re.I)
        or any(word in body for word in ("계좌", "은행", "입금 계좌", "만원", "원", "송금 링크", "이체 링크"))
        or from_name in body or to_name in body):
        raise ValueError("금액·이름·연락처 등 금지 내용 포함")
    if re.search(r"(?:일|이|삼|사|오|육|칠|팔|구|십|백|천|만|억){2,}\s*(?:원|만원)", body):
        raise ValueError("한글 금액 추정치 포함")
    return body


def _fallback_body(tone: str, repeat: bool) -> str:
    if tone == "senior":
        return ("정산 내역을 다시 안내드립니다. 이미 송금하셨다면 양해 부탁드리며, 확인 후 알려주시면 감사하겠습니다."
                if repeat else "정산 내역을 안내드립니다. 편하실 때 확인해 주시면 감사하겠습니다.")
    if tone == "junior":
        return ("정산 내역 다시 한번 확인 부탁해! 이미 보냈다면 알려줘. 고마워 😊"
                if repeat else "정산 내역 확인하고 편할 때 보내주면 돼! 고마워 😊")
    return ("정산 내역 다시 알려줘! 이미 보냈다면 말해줘. 고마워 🙏"
            if repeat else "정산 내역 나왔어! 확인하고 편할 때 보내주면 고마워 😊")


def compose_message(*, title: str, from_name: str, to_name: str, amount: int, body: str) -> str:
    """머리말은 모델이 아닌 코드가 구성한다. 외부 발송은 하지 않는다."""
    clean_title = " ".join(title.split())[:80] or "모아정산"
    return f"[{clean_title}] 송금 안내\n{from_name} → {to_name}: {amount:,}원\n\n{body}"


def generate_reminder(*, title: str, from_name: str, to_name: str, amount: int,
                      tone: str, repeat: bool, client=None) -> dict:
    if tone not in TONES or type(amount) is not int or amount <= 0 or amount > 10**12:
        raise ValueError("안내 조건이 올바르지 않습니다")
    if not from_name.strip() or not to_name.strip() or from_name == to_name:
        raise ValueError("송금자와 수취인을 확인해 주세요")

    source, body = "template", _fallback_body(tone, repeat)
    try:
        # 신뢰할 수 없는 사용자 입력은 프롬프트에 넣지 않는다.
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
        prompt = f"{base_prompt}\n관계: {TONES[tone]}\n안내 유형: {'재안내' if repeat else '첫 안내'}"
        model_response = (client or _client()).models.generate_content(
            model=get_model(),
            contents=prompt,
            config={"temperature": 0.65, "max_output_tokens": 300,
                    "response_mime_type": "application/json", "response_json_schema": BODY_SCHEMA},
        )
        parsed = json.loads(model_response.text or "")
        if not isinstance(parsed, dict) or set(parsed) != {"message"}:
            raise ValueError("JSON 응답 형태 오류")
        body = _safe_body(parsed["message"], from_name=from_name, to_name=to_name)
        source = "gemini"
    except Exception as exc:
        # 503/504, SDK 미설치, 잘못된 JSON, 안전성 검증 실패 모두 기존 문구로 복구한다.
        LOG.warning("Reminder generation fallback: %s", type(exc).__name__)
    return {"message": compose_message(title=title, from_name=from_name, to_name=to_name,
                                       amount=amount, body=body),
            "source": source, "model": get_model() if source == "gemini" else None}
