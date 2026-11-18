
"""확정 정산 숫자는 코드로 고정하고 Gemini는 안내 문장만 작성한다.

모델에 이름, 정산명, 금액, 계좌 등 개인/금융 정보를 보내지 않는다.
모델 장애나 부적절한 출력은 템플릿으로 복구하며 자동 발송은 수행하지 않는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json
import logging
import os
import re

from .gemini_client import get_model


LOG = logging.getLogger(__name__)
<<<<<<< HEAD
PROMPT_PATH = Path(__file__).with_name("prompts") / "reminder_message.md"
TONES = {"friend": "친근한 친구 사이", "senior": "존댓말로 정중하게", "junior": "친근하고 부담스럽지 않게"}
=======

PROMPT_PATH = (
    Path(__file__).with_name("prompts") / "reminder_message.md"
)

TONES = {
    "friend": "친근한 친구 사이",
    "senior": "존댓말로 정중하게",
    "junior": "친근하고 부담스럽지 않게",
}

>>>>>>> e388c64beb66363b3c29b8ec350da46b08eaa61c
STYLE_OPTIONS = {
    "friend": {
        "warm": "다정하게: 따뜻하고 편안한 반말로, 상대에게 부담을 주지 않고 요청",
        "playful": "장난스럽게: 가볍고 재치 있는 친구 말투, 비꼬거나 압박하지 않기",
        "firm": "단호하게: 무례하지 않되 짧고 명확하게 송금 확인 요청",
    },
    "senior": {
        "polite": "공손하게: 기본 존댓말, 예의를 지키며 정중히 요청",
        "gentle": "부드럽게: 따뜻하고 친근한 존댓말, 감사의 느낌 포함",
        "formal": "격식 있게: 공식적인 안내 문체, 군더더기 없이 간결하게",
    },
    "junior": {
        "friendly": "친근하게: 밝고 편안한 반말로 가볍게 요청",
        "considerate": "배려 있게: 상대 사정을 존중하며 부담 없이 확인 부탁",
        "clear": "깔끔하게: 핵심을 짧고 분명하게 정리하는 반말",
    },
}
DEFAULT_STYLE = {"friend": "warm", "senior": "polite", "junior": "friendly"}

BODY_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"}
    },
    "required": ["message"],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def _client():
    """Gemini API 클라이언트를 생성한다."""

    from dotenv import load_dotenv

    load_dotenv(
        Path(__file__).resolve().parents[2] / ".env",
        override=False,
    )

    key = os.getenv("GEMINI_API_KEY", "").strip()

    if not key:
        raise RuntimeError("Gemini API 키가 없습니다")

    from google import genai

    return genai.Client(
    api_key=key,
    http_options={
        "timeout": 60000,
        "retry_options": {"attempts": 1},
    },
)


def _safe_body(
    raw: str,
    *,
    from_name: str,
    to_name: str,
) -> str:
    """Gemini가 생성한 문구의 안전성을 검사한다."""

    if not isinstance(raw, str):
        raise ValueError("문자열이 아닌 응답")

    body = " ".join(raw.split())

    if not 12 <= len(body) <= 170:
        raise ValueError("문구 길이가 범위를 벗어남")

    if (
        re.search(
            r"[0-9０-９]|[₩$€]|https?://|www\.|@|[\r\n]",
            body,
            re.I,
        )
        or any(
            word in body
            for word in (
                "계좌",
                "은행",
                "입금 계좌",
                "만원",
                "원",
                "송금 링크",
                "이체 링크",
            )
        )
        or from_name in body
        or to_name in body
    ):
        raise ValueError(
            "금액·이름·연락처 등 금지 내용 포함"
        )

    if re.search(
        r"(?:일|이|삼|사|오|육|칠|팔|구|십|백|천|만|억){2,}\s*(?:원|만원)",
        body,
    ):
        raise ValueError("한글 금액 추정치 포함")

    return body


def _fallback_body(tone: str, repeat: bool, style: str | None = None) -> str:
    """Deterministic, style-specific fallback when Gemini is unavailable."""
    style = style or DEFAULT_STYLE[tone]
    first = {
        "warm": "정산 내역 나왔어! 확인하고 편할 때 보내주면 고마워 😊",
        "playful": "우리 즐거운 모임 정산도 마무리하자! 확인하고 편할 때 부탁해 😄",
        "firm": "정산 내역을 확인하고 송금 부탁해. 확인되면 알려줘.",
        "polite": "정산 내역을 안내드립니다. 편하실 때 확인해 주시면 감사하겠습니다.",
        "gentle": "지난 모임 정산 내역 안내드려요. 시간 되실 때 편하게 확인 부탁드립니다 😊",
        "formal": "정산 내역을 전달드립니다. 확인 후 송금해 주시기 바랍니다. 감사합니다.",
        "friendly": "정산 내역 확인하고 편할 때 보내주면 돼! 고마워 😊",
        "considerate": "정산 내역 안내하려고 연락했어. 부담 갖지 말고 편할 때 확인 부탁해!",
        "clear": "정산 내역 확인 부탁해. 송금 후 알려주면 고마워!",
    }
    again = {
        "warm": "정산 내역 다시 알려줘! 이미 보냈다면 말해줘. 고마워 🙏",
        "playful": "정산 알림 한 번 더 살짝 남겨! 이미 보냈다면 알려줘 😄",
        "firm": "정산 내역을 다시 확인 부탁해. 이미 송금했다면 알려줘.",
        "polite": "정산 내역을 다시 안내드립니다. 이미 송금하셨다면 양해 부탁드리며, 확인 후 알려주시면 감사하겠습니다.",
        "gentle": "정산 내역 확인 차 다시 연락드려요. 이미 보내셨다면 양해 부탁드립니다 😊",
        "formal": "정산 내역 재안내드립니다. 이미 송금하셨다면 본 안내는 양해 부탁드립니다.",
        "friendly": "정산 내역 다시 한번 확인 부탁해! 이미 보냈다면 알려줘. 고마워 😊",
        "considerate": "혹시 정산 확인할 시간이 없었을까 봐 다시 남겨! 이미 보냈다면 알려줘.",
        "clear": "정산 내역 재확인 부탁해. 이미 송금했다면 알려줘.",
    }
    return (again if repeat else first)[style]


def compose_message(
    *,
    title: str,
    from_name: str,
    to_name: str,
    amount: int,
    body: str,
) -> str:
    """확정된 정산 정보와 안내 문구를 결합한다."""

    clean_title = " ".join(title.split())[:80] or "모아정산"

    return (
        f"[{clean_title}] 송금 안내\n"
        f"{from_name} → {to_name}: {amount:,}원\n\n"
        f"{body}"
    )


<<<<<<< HEAD
def generate_reminder(*, title: str, from_name: str, to_name: str, amount: int,
                      tone: str, repeat: bool, client=None, style: str | None = None) -> dict:
    if tone not in TONES or type(amount) is not int or amount <= 0 or amount > 10**12:
=======
def generate_reminder(
    *,
    title: str,
    from_name: str,
    to_name: str,
    amount: int,
    tone: str,
    repeat: bool,
    client=None,
    style: str | None = None,
) -> dict:
    """Gemini 안내 문구를 생성하고 검증한다."""

    # 1. 입력값 검증
    if (
        tone not in TONES
        or type(amount) is not int
        or amount <= 0
        or amount > 10**12
    ):
>>>>>>> e388c64beb66363b3c29b8ec350da46b08eaa61c
        raise ValueError("안내 조건이 올바르지 않습니다")

<<<<<<< HEAD
=======
    if (
        not from_name.strip()
        or not to_name.strip()
        or from_name == to_name
    ):
        raise ValueError(
            "송금자와 수취인을 확인해 주세요"
        )

>>>>>>> e388c64beb66363b3c29b8ec350da46b08eaa61c
    # Preserve clients that only send relationship, without a sub-style.
    style = style or DEFAULT_STYLE[tone]
    if style not in STYLE_OPTIONS[tone]:
        raise ValueError("선택한 관계와 세부 말투가 일치하지 않습니다")

<<<<<<< HEAD
    source, body = "template", _fallback_body(tone, repeat, style)
    try:
        # 신뢰할 수 없는 사용자 입력은 프롬프트에 넣지 않는다.
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
        prompt = f"{base_prompt}\n관계: {TONES[tone]}\n안내 유형: {'재안내' if repeat else '첫 안내'}"
        prompt += f"\n세부 말투: {STYLE_OPTIONS[tone][style]}"
        model_response = (client or _client()).models.generate_content(
=======
    # 2. Gemini 오류 시 사용할 기본 문구
    source = "template"
    body = _fallback_body(tone, repeat, style)

    # 환경변수로 디버그 출력 제어
    debug = os.getenv("REMINDER_DEBUG", "0") == "1"

    try:
        # 3. 프롬프트 로딩
        base_prompt = PROMPT_PATH.read_text(
            encoding="utf-8"
        )

        prompt = (
            f"{base_prompt}\n"
            f"관계: {TONES[tone]}\n"
            f"안내 유형: {'재안내' if repeat else '첫 안내'}"
        )

        # 4. 실제 Gemini API 호출
        prompt += f"\n세부 말투: {STYLE_OPTIONS[tone][style]}"
        model_response = (
            client or _client()
        ).models.generate_content(
>>>>>>> e388c64beb66363b3c29b8ec350da46b08eaa61c
            model=get_model(),
            contents=prompt,
            
            config={
    "temperature": 0.65,
    "max_output_tokens": 1024,
    "thinking_config": {
        "thinking_level": "minimal"
    },
    "response_mime_type": "application/json",
    "response_json_schema": BODY_SCHEMA,
},
        )

        # 5. Gemini 응답 디버그
        if debug:
            print("\n===== GEMINI DEBUG =====")
            print("MODEL:", get_model())

            raw_text = model_response.text
            print("RAW RESPONSE:", repr(raw_text))

            candidates = model_response.candidates or []

            for i, candidate in enumerate(candidates):
                print(
                    f"CANDIDATE {i} FINISH REASON:",
                    getattr(candidate, "finish_reason", None),
                )

            print(
                "PROMPT FEEDBACK:",
                getattr(model_response, "prompt_feedback", None),
            )
            print("========================\n")

        # 6. 응답 유효성 검사
        raw_text = model_response.text

        if not raw_text or not raw_text.strip():
            raise ValueError("Gemini 응답이 비어 있습니다")

        parsed = json.loads(raw_text)

        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"message"}
        ):
            raise ValueError("JSON 응답 형태 오류")

        # 7. 생성 문구 안전성 검증
        body = _safe_body(
            parsed["message"],
            from_name=from_name,
            to_name=to_name,
        )

        source = "gemini"

    except Exception as exc:
        # 8. 오류 발생 시 기본 템플릿 사용
        LOG.warning(
            "Reminder generation fallback: %s",
            type(exc).__name__,
        )

        if debug:
            print("\n===== GEMINI ERROR =====")
            print("ERROR TYPE:", type(exc).__name__)
            print("ERROR MESSAGE:", str(exc))
            print("========================\n")

    # 9. 최종 안내 문구 반환
    return {
        "message": compose_message(
            title=title,
            from_name=from_name,
            to_name=to_name,
            amount=amount,
            body=body,
        ),
        "source": source,
        "model": (
            get_model()
            if source == "gemini"
            else None
        ),
    }
