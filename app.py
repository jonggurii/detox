from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from settlements.parser import (
    ManualInputRequired,
    ParseResult,
    ParserAPIError,
    ParserConfigurationError,
    parse_settlement_query_async,
)


app = FastAPI(
    title="정산 입력 검토 API",
    version="1.1.0",
)


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        max_length=12000,
    )
    supplied_evidence: str | None = Field(
        default=None,
        max_length=24000,
    )


@app.post("/parse", response_model=ParseResult)
async def parse_request(request: ParseRequest):
    try:
        return await parse_settlement_query_async(
            request.text,
            supplied_evidence=request.supplied_evidence,
        )

    except ManualInputRequired as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "manual_input_required",
                "message": str(exc),
            },
        ) from exc

    except (ParserAPIError, ParserConfigurationError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "parser_unavailable"},
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_input"},
        ) from exc