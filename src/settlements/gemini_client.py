"""Gemini 클라이언트와 모델 ID의 단일 설정점 (실제 호출 시에만 SDK 로드)."""
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


def get_model() -> str:
    """텍스트·영수증 추출에 같은 모델을 사용한다."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

def get_multimodal_model() -> str:
    from dotenv import load_dotenv

    load_dotenv(
        Path(__file__).resolve().parents[2] / ".env",
        override=False,
    )

    return (
        os.getenv("GEMINI_MULTIMODAL_MODEL")
        or get_model()
    ).strip()

@lru_cache(maxsize=1)
def get_client():
    """키·SDK가 없어도 서버 시작 및 결정적 테스트는 가능하다."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY를 설정해 주세요.")
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("google-genai를 설치해 주세요: python -m pip install -r requirements.txt") from exc
    return genai.Client(api_key=key, http_options={"timeout": 1800000, "retry_options": {"attempts": 1}})
