import os
import json
from google import genai
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 1. 환경변수 로드
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ .env 파일에서 GEMINI_API_KEY를 찾을 수 없습니다.")

client = genai.Client(api_key=api_key)

# 2. Pydantic 스키마 정의
class ItemException(BaseModel):
    item_name: str = Field(description="제외되는 항목 이름 (예: 술값)")
    amount: int = Field(description="해당 항목 총 금액")
    excluded_members_count: int = Field(description="해당 항목을 이용하지 않은 인원수")

class RoundInfo(BaseModel):
    round: int = Field(description="차수 번호")
    total_cost: int = Field(description="해당 차수 전체 금액")
    excluded_members: list[str] = Field(default_factory=list, description="차수 전체 참여 제외자 이름")
    exceptions: list[ItemException] = Field(default_factory=list, description="특정 항목 제외 조건")

class SettlementRequestContext(BaseModel):
    total_participants_count: int = Field(description="모임 전체 인원수")
    rounds_info: list[RoundInfo] = Field(default_factory=list)
    reminder_tone: str | None = Field(default="friendly_casual")

# [단계 1] LLM 파싱 (생각하기: 사용자 입력 해석)
def parse_input(text: str) -> SettlementRequestContext:
    prompt = f"""
    너는 N빵 정산 봇의 자연어 파서다.
    사용자의 정산 발화에서 전체 인원, 차수별 금액, 전체 제외자, 특정 항목(술값 등) 미이용자 정보를 추출해 JSON으로 응답하라.

    [입력문]
    {text}
    """
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": SettlementRequestContext,
        }
    )
    raw_json = json.loads(response.text)
    return SettlementRequestContext(**raw_json)

# [단계 2] Python 정밀 계산 (생각하기: 1원 단위 N빵 계산)
def calculate_settlement(context: SettlementRequestContext):
    total_members = context.total_participants_count
    summary_text = ""
    
    print("\n" + "="*50)
    print("📊 [정산 엔진 계산 결과]")
    print("="*50)

    for r in context.rounds_info:
        active_count = total_members - len(r.excluded_members)
        print(f"[ {r.round}차 정산 ] (총 {r.total_cost:,}원 / 전체 참여 {active_count}명)")
        
        if r.exceptions:
            base_cost = r.total_cost
            for ex in r.exceptions:
                base_cost -= ex.amount
                non_drinkers = ex.excluded_members_count
                drinkers = active_count - non_drinkers
                
                drink_per_person = ex.amount // drinkers if drinkers > 0 else 0
                common_per_person = base_cost // active_count if active_count > 0 else 0
                
                print(f" • {ex.item_name} 마신 사람 1인당: {common_per_person + drink_per_person:,}원")
                print(f" • {ex.item_name} 안 마신 사람({non_drinkers}명) 1인당: {common_per_person:,}원")
                summary_text += f"{r.round}차: 마신사람 {common_per_person + drink_per_person}원 / 안마신사람 {common_per_person}원\n"
        else:
            price_per_person = r.total_cost // active_count if active_count > 0 else 0
            excluded_str = f" (제외: {', '.join(r.excluded_members)})" if r.excluded_members else ""
            print(f" • 1인당 금액{excluded_str}: {price_per_person:,}원")
            summary_text += f"{r.round}차: 1인당 {price_per_person}원\n"
            
    print("="*50)
    return summary_text

# [단계 3] LLM 대답 생성 (말하기: 카톡 독촉 문구 출력)
def generate_response(user_text: str, calc_summary: str, tone: str):
    prompt = f"""
    너는 N빵 정산 독촉 챗봇이다.
    사용자의 원본 요청과 정확히 계산된 정산 결과를 바탕으로 카카오톡으로 전송할 정산 안내 메시지를 작성하라.

    - 사용자 요청: {user_text}
    - 계산 결과: {calc_summary}
    - 톤앤매너: {tone}

    계좌번호 작성 안내([은행] [계좌번호])와 정산 내역을 깔끔하게 포함해라.
    """
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )
    return response.text

# --- 실시간 대화 루프 ---
if __name__ == "__main__":
    print("🤖 N빵 정산 봇이 준비되었습니다! (종료하려면 'exit' 입력)")
    
    while True:
        user_input = input("\n나: ")
        
        if user_input.strip().lower() in ["exit", "종료", "q"]:
            print("정산 봇을 종료합니다.")
            break
            
        if not user_input.strip():
            continue

        try:
            # 1. 자연어 파싱 (해석)
            parsed_data = parse_input(user_input)
            
            # 2. 정확한 N빵 계산
            calc_result = calculate_settlement(parsed_data)
            
            # 3. 계산된 결과를 바탕으로 최종 대답 생성
            bot_reply = generate_response(user_input, calc_result, parsed_data.reminder_tone)
            
            print(f"\n💬 정산 봇:\n{bot_reply}")
            
        except Exception as e:
            print(f"\n❌ 처리 중 오류 발생: {e}")