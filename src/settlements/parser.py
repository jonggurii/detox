import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# ==========================================
# 1. Pydantic 스키마 정의 (통합 단일화)
# ==========================================
class ItemException(BaseModel):
    item_name: str = Field(description="제외되는 항목 이름 (예: 술값, 고기값)")
    amount: int = Field(ge=0, description="해당 항목 총 금액")
    excluded_members_count: int = Field(ge=1, description="해당 항목을 이용하지 않은 인원수")

class RoundInfo(BaseModel):
    round: int = Field(ge=1, description="차수 번호 (1부터 시작)")
    total_cost: int = Field(ge=0, description="해당 차수 전체 결제 금액")
    excluded_members: list[str] = Field(default_factory=list, description="차수 전체 미참석자 이름 목록")
    exceptions: list[ItemException] = Field(default_factory=list, description="특정 항목 제외 내역")

class SettlementRequestContext(BaseModel):
    total_participants_count: int = Field(ge=1, description="모임 전체 참여 인원수")
    rounds_info: list[RoundInfo] = Field(default_factory=list, description="차수별 정산 정보")
    reminder_tone: str = Field(default="friendly_casual", description="독촉/정산 안내 톤앤매너")

# GenAI 클라이언트 초기화 (싱글톤)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 토큰 낭비를 줄인 압축 프롬프트 (스키마는 response_schema가 강제하므로 제외)
SYSTEM_INSTRUCTION = """
너는 N빵 정산 자연어 파서다.
사용자 발화에서 [전체 인원수, 차수별 금액, 차수 전체 불참자, 특정 품목(술값 등) 미이용자] 정보를 추출하라.
- 원문에 언급되지 않은 금액이나 인원은 임의로 추정하거나 계산하지 마라.
- 'n만원'은 정수(예: 150000)로 변환하라.
- 특정 품목 미이용자는 exceptions 배열에 매핑하라.
"""

# ==========================================
# 2. LLM 비동기 파싱 (FastAPI 최적화)
# ==========================================
async def parse_settlement_query_async(text: str) -> SettlementRequestContext:
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",  # 또는 gemini-1.5-flash (공식 모델명 확인 권장)
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=SettlementRequestContext,
            temperature=0.0,  # 정보 추출의 일관성을 위해 0.0 고정 (환각 및 토큰 낭비 방지)
        )
    )
    
    # response.parsed를 통해 json.loads() 및 Pydantic 재직렬화 오버헤드 제거
    return response.parsed

# 동기 호출 호환 유지
def parse_settlement_query(text: str) -> SettlementRequestContext:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=SettlementRequestContext,
            temperature=0.0,
        )
    )
    return response.parsed

parse_settlement_request = parse_settlement_query