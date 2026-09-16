from pydantic import BaseModel, Field

from detox.parser import parse_settlement_request

try:
    from fastapi import FastAPI
except ImportError as error:
    raise RuntimeError(
        "FastAPI가 필요합니다. `pip install -r requirements.txt`를 실행하세요."
    ) from error


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, description="사용자의 정산 요청 발화")


app = FastAPI(title="N빵 정산 봇 API", version="1.0.0")


@app.post("/parse")
def parse_request(request: ParseRequest):
    return parse_settlement_request(request.text)