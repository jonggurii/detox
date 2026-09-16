import os
from pathlib import Path

from google import genai
from dotenv import load_dotenv
from google.genai import types

PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("❌ .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")

client = genai.Client(api_key=api_key)
prompt_path = PROJECT_ROOT / "src" / "detox" / "prompts" / "parse_query.md"
system_prompt = prompt_path.read_text(encoding="utf-8")
chat = client.chats.create(
    model="gemini-3.6-flash",
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.2,
    ),
)

print("=== N빵 정산 봇 테스트 (종료: 'exit' 입력) ===")

while True:
    try:
        user_input = input("\n나: ")
    except (EOFError, KeyboardInterrupt):
        print("\n정산 봇을 종료합니다.")
        break
    if user_input.strip().lower() in ["exit", "종료", "q"]:
        print("정산 봇을 종료합니다.")
        break
    if not user_input.strip():
        continue

    try:
        response = chat.send_message(user_input)
        print(f"\n정산 봇: {response.text}")
    except Exception as e:
        print(f"\n❌ 호출 에러: {e}")