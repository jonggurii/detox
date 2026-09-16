import os
from google import genai
from dotenv import load_dotenv

# 1. .env 파일 로드
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("❌ .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")

# 2. Gemini 클라이언트 생성
client = genai.Client(api_key=api_key)
chat = client.chats.create(model="gemini-3.6-flash")

print("=== N빵 정산 봇 API 테스트 시작 (종료하려면 'exit' 입력) ===")

# 3. 키보드로 입력받아 대화하는 무한 루프
while True:
    user_input = input("\n나: ")
    
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