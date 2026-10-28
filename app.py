from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from settlements.parser import parse_settlement_query_async

class ParseRequest(BaseModel):
    text: str = Field(min_length=1, description="사용자의 정산 요청 발화")

app = FastAPI(title="N빵 정산 봇 API", version="1.0.0")

@app.post("/parse")
async def parse_request(request: ParseRequest):
    try:
        # 비동기 호출로 동시 요청 처리 성능 극대화
        result = await parse_settlement_query_async(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파싱 실패: {str(e)}")