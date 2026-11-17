#!/usr/bin/env python3
"""Gemini Python SDK 설치 상태 확인 (API 요청과 과금 없음)."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
import os


def main() -> int:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    try:
        installed = version("google-genai")
    except PackageNotFoundError:
        print("[FAIL] google-genai 패키지가 이 Python 환경에 설치되지 않았습니다.")
        print("  설치: python -m pip install -r requirements.txt")
        return 1

    print(f"google-genai version: {installed}")
    try:
        from google import genai  # noqa: F401
    except ImportError as exc:
        print(f"[FAIL] SDK import 실패: {exc}")
        print("  현재 Python과 pip가 같은 환경인지 확인해 주세요.")
        return 1

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    except ImportError:
        print("[WARN] python-dotenv 미설치: .env를 읽지 못했습니다.")

    print("[PASS] from google import genai")
    print("API key:", "configured" if os.getenv("GEMINI_API_KEY", "").strip() else "not configured")
    print("이 검사는 실제 API 호출/모델 접근을 검증하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
