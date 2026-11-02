"""로컬 정산 웹앱.

저장 위치:
    프로젝트 최상위의 app.py

실행:
    python -m uvicorn app:app --reload
"""

from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from settlements.parser import (
    ManualInputRequired,
    OutputFormatError,
    ParseResult,
    ParserAPIError,
    ParserConfigurationError,
    ParserError,
    load_contract,
    parse_and_review,
    validate_context_data,
)
from settlements.workflow import WorkflowError, WorkflowStore
from settlements.calculator import CalculationError


ROOT = Path(__file__).resolve().parent


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParseBody(Body):
    text: str = Field(
        min_length=1,
        max_length=12000,
    )
    supplied_evidence: str | None = Field(
        default=None,
        max_length=24000,
    )


class ManualBody(Body):
    source_text: str = Field(
        min_length=1,
        max_length=12000,
    )
    context: dict


class EditBody(Body):
    input_revision: int = Field(
        ge=1,
        strict=True,
    )
    context: dict


class Checks(Body):
    source_reviewed: StrictBool
    people_resolved: StrictBool
    conditions_reviewed: StrictBool
    funding_verified: StrictBool = False


class ConfirmBody(Body):
    input_revision: int = Field(
        ge=1,
        strict=True,
    )
    reviewed_by: str = Field(
        min_length=1,
        max_length=100,
    )
    review_notes: str = Field(
        min_length=1,
        max_length=2000,
    )
    checks: Checks


class CalculateBody(Body):
    confirmation_id: str = Field(
        min_length=1,
        max_length=100,
    )


def create_app(db_path=None, parser=None):
    app = FastAPI(
        title="모아정산",
        version="0.1.0",
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "localhost",
            "127.0.0.1",
            "testserver",
        ],
    )

    store = WorkflowStore(
        db_path or ROOT / "data" / "settlements.sqlite3"
    )

    parse = parser or parse_and_review

    # --------------------------------------------------
    # 공통 요청 검사
    # --------------------------------------------------

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")

        if request.method in {"POST", "PATCH", "DELETE"} and origin:
            expected_origin = str(request.base_url).rstrip("/")

            if origin.rstrip("/") != expected_origin:
                return JSONResponse(
                    {
                        "detail": "다른 주소에서 보낸 변경 요청입니다."
                    },
                    status_code=403,
                )

        return await call_next(request)

    # --------------------------------------------------
    # 공통 오류 처리
    # --------------------------------------------------

    @app.exception_handler(WorkflowError)
    async def workflow_error(request, exc):
        return JSONResponse(
            {"detail": str(exc)},
            status_code=409,
        )

    @app.exception_handler(OutputFormatError)
    async def format_error(request, exc):
        return JSONResponse(
            {
                "detail": "입력 형식을 확인해 주세요.",
                "issues": str(exc),
            },
            status_code=422,
        )

    @app.exception_handler(CalculationError)
    async def calculation_error(request, exc):
        return JSONResponse(
            {"detail": str(exc)},
            status_code=422,
        )

    @app.exception_handler(ManualInputRequired)
    async def manual_required(request, exc):
        return JSONResponse(
            {
                "detail": (
                    "추출 형식을 확인하지 못했습니다. "
                    "직접 입력을 이용해 주세요."
                )
            },
            status_code=422,
        )

    @app.exception_handler(ParserError)
    async def parser_error(request, exc):
        return JSONResponse(
            {
                "detail": (
                    "AI 호출을 완료하지 못했습니다. "
                    "서버의 모델·키 설정을 확인하거나 "
                    "직접 입력해 주세요."
                )
            },
            status_code=503,
        )

    # --------------------------------------------------
    # 공통 내부 함수
    # --------------------------------------------------

    def require_session(sid):
        try:
            return store.view(sid)
        except WorkflowError as exc:
            raise HTTPException(
                status_code=404,
                detail="정산을 찾지 못했습니다.",
            ) from exc

    def extract(body: ParseBody):
        # ParseResult 전체를 반환한다.
        # context뿐 아니라 issues, status, 추출 정보도 포함한다.
        if not body.text.strip():
            raise ValueError("정산 내용을 입력해 주세요.")

        if body.supplied_evidence is None:
            return parse(body.text)

        return parse(
            body.text,
            supplied_evidence=body.supplied_evidence,
        )

    # --------------------------------------------------
    # 팀원 코드의 추출·검토 API
    # 결과만 반환하며 정산 세션은 저장하지 않는다.
    # --------------------------------------------------

    @app.post("/parse", response_model=ParseResult)
    def parse_request(body: ParseBody):
        try:
            return extract(body)

        except ManualInputRequired as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "manual_input_required",
                    "message": str(exc),
                },
            ) from exc

        except (
            ParserAPIError,
            ParserConfigurationError,
        ) as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "parser_unavailable",
                },
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_input",
                },
            ) from exc

    # --------------------------------------------------
    # 웹 화면과 입력 스키마
    # --------------------------------------------------

    @app.get("/")
    def home():
        return FileResponse(
            ROOT / "frontend" / "index.html"
        )

    @app.get("/api/schema")
    def schema():
        return load_contract()[1]

    # --------------------------------------------------
    # 저장한 정산 목록
    # --------------------------------------------------

    @app.get("/api/sessions")
    def sessions():
        with closing(sqlite3.connect(store.path)) as db:
            rows = db.execute(
                """
                SELECT document
                FROM sessions
                ORDER BY rowid DESC
                LIMIT 100
                """
            ).fetchall()

        items = []

        for row in rows:
            doc = json.loads(row[0])
            rev = doc["revisions"][-1]

            items.append(
                {
                    "session_id": doc["session_id"],
                    "title": doc["source_text"][:60],
                    "input_revision": rev["input_revision"],
                    "created_at": rev["created_at"],
                }
            )

        return items

    # --------------------------------------------------
    # 자연어 입력으로 새 정산 생성
    # 한 번 추출한 결과를 저장한다.
    # --------------------------------------------------

    @app.post("/api/sessions")
    def new_session(body: ParseBody):
        if not body.text.strip():
            raise HTTPException(
                status_code=422,
                detail="정산 내용을 입력해 주세요.",
            )

        sid = store.start(extract(body))
        return store.view(sid)

    # --------------------------------------------------
    # Gemini 없이 직접 입력으로 정산 생성
    # --------------------------------------------------

    @app.post("/api/sessions/manual")
    def manual_session(body: ManualBody):
        contract = load_contract()

        parsed = SimpleNamespace(
            context=validate_context_data(body.context),
            source_text=body.source_text,
            supplied_evidence=None,
            model="manual",
            prompt_version=contract[2],
            schema_sha256=contract[3],
            attempts=0,
        )

        return store.view(store.start(parsed))

    # --------------------------------------------------
    # 저장한 정산 조회
    # --------------------------------------------------

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        return require_session(sid)

    # --------------------------------------------------
    # 조건 수정 및 새 버전 저장
    # --------------------------------------------------

    @app.patch("/api/sessions/{sid}/context")
    def edit_session(sid: str, body: EditBody):
        require_session(sid)

        store.revise(
            sid,
            body.input_revision,
            body.context,
        )

        return store.view(sid)

    # --------------------------------------------------
    # 사용자 확인
    # --------------------------------------------------

    @app.post("/api/sessions/{sid}/confirm")
    def confirm_session(sid: str, body: ConfirmBody):
        require_session(sid)

        return store.confirm(
            sid,
            body.input_revision,
            reviewed_by=body.reviewed_by,
            review_notes=body.review_notes,
            checks=body.checks.model_dump(),
        )

    # --------------------------------------------------
    # 확인한 버전으로 계산
    # --------------------------------------------------

    @app.post("/api/sessions/{sid}/calculate")
    def calculate_session(sid: str, body: CalculateBody):
        require_session(sid)

        return store.calculate(
            sid,
            body.confirmation_id,
        )

    return app


app = create_app(os.getenv("SETTLEMENT_DB_PATH"))