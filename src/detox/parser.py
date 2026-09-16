import os
import json
from google import genai
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# 1. 예외 항목 스키마 정의
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

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Step 1: LLM 파싱
def parse_settlement_query(text: str) -> SettlementRequestContext:
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

# Step 2: 정밀 N빵 계산 엔진
def calculate_settlement(context: SettlementRequestContext):
    total_members = context.total_participants_count
    
    print("\n" + "="*50)
    print("📊 [정산 엔진 계산 결과] (Python 정밀 계산)")
    print("="*50)

    for r in context.rounds_info:
        active_count = total_members - len(r.excluded_members)
        print(f"\n[ {r.round}차 정산 ] (총 {r.total_cost:,}원 / 전체 참여 {active_count}명)")
        
        # 특정 항목 제외(예: 술값) 처리
        if r.exceptions:
            base_cost = r.total_cost
            for ex in r.exceptions:
                base_cost -= ex.amount
                non_drinkers = ex.excluded_members_count
                drinkers = active_count - non_drinkers
                
                drink_per_person = ex.amount // drinkers if drinkers > 0 else 0
                common_per_person = base_cost // active_count if active_count > 0 else 0
                
                print(f" • {ex.item_name} ({ex.amount:,}원): {drinkers}명이 분담 ➔ 1인당 +{drink_per_person:,}원")
                print(f" • 공통 금액 ({base_cost:,}원): {active_count}명이 분담 ➔ 1인당 {common_per_person:,}원")
                print(f" 👉 {ex.item_name} 마신 사람 1인당: {common_per_person + drink_per_person:,}원")
                print(f" 👉 {ex.item_name} 안 마신 사람({non_drinkers}명) 1인당: {common_per_person:,}원")
        else:
            price_per_person = r.total_cost // active_count if active_count > 0 else 0
            excluded_str = f" (제외: {', '.join(r.excluded_members)})" if r.excluded_members else ""
            print(f" 👉 1인당 금액{excluded_str}: {price_per_person:,}원")
            
    print("="*50)

if __name__ == "__main__":
    sample_speech = "5명이서 1차 술과 고기를 먹어 15만원 나왔지만 술을 안먹는사람이 2명이있어 술값은 5만원 그리고 2차에서 희주만빠진 4명이서노래방으로 15만원을 썻어"
    print(f"🗣️ 사용자 입력: \"{sample_speech}\"")
    
    parsed_context = parse_settlement_query(sample_speech)
    calculate_settlement(parsed_context)