"""로컬 정산 웹앱. 실행: python -m uvicorn app:app --reload"""
from pathlib import Path
from types import SimpleNamespace
from contextlib import closing
import json
import os
import sqlite3
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from settlements.parser import (
    ManualInputRequired, OutputFormatError, ParserError, ParseResult,
    ParserAPIError, ParserConfigurationError,
    load_contract, parse_and_review, validate_context_data,
)
from settlements.workflow_store import WorkflowError, WorkflowStore
from settlements.calculator import CalculationError
from settlements.receipt_api import receipt_router

from backend.multimodal_router import make_multimodal_router

from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger("uvicorn.error")


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParseBody(Body):
    text: str = Field(min_length=1, max_length=12000)
    supplied_evidence: str | None = Field(default=None, max_length=24000)


class ManualBody(Body):
    source_text: str = Field(min_length=1, max_length=12000)
    context: dict


class EditBody(Body):
    input_revision: int = Field(ge=1, strict=True)
    context: dict


class Checks(Body):
    source_reviewed: StrictBool
    people_resolved: StrictBool
    conditions_reviewed: StrictBool
    funding_verified: StrictBool = False


class ConfirmBody(Body):
    input_revision: int = Field(ge=1, strict=True)
    reviewed_by: str = Field(min_length=1, max_length=100)
    review_notes: str = Field(min_length=1, max_length=2000)
    checks: Checks


class CalculateBody(Body):
    confirmation_id: str = Field(min_length=1, max_length=100)


def create_app(db_path=None, parser=None, ocr=None):
    app = FastAPI(title="모아정산", version="0.1.0")
    allowed_hosts = [
    "localhost",
    "127.0.0.1",
    "testserver",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8081",
            "http://127.0.0.1:8081",
            "http://172.16.51.140:8081",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    dev_host = os.getenv("SETTLEMENT_DEV_HOST")
    if dev_host:
        allowed_hosts.append(dev_host)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "localhost",
            "127.0.0.1",
            "172.16.51.140",
        ],
    )
    store = WorkflowStore(db_path or ROOT / "data" / "settlements.sqlite3")
    parse = parser or parse_and_review

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PATCH", "DELETE"} and origin:
            if origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "다른 주소에서 보낸 변경 요청입니다."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(WorkflowError)
    async def workflow_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(OutputFormatError)
    async def format_error(request, exc):
        return JSONResponse({"detail": "입력 형식을 확인해 주세요.", "issues": str(exc)}, status_code=422)

    @app.exception_handler(CalculationError)
    async def calculation_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(ManualInputRequired)
    async def manual_required(request, exc):
        return JSONResponse({"detail": "추출 형식을 확인하지 못했습니다. 직접 입력을 이용해 주세요."}, status_code=422)

    @app.exception_handler(ParserError)
    async def parser_error(request: Request, exc: ParserError):
        logger.error(
            "Parser failed: endpoint=%s, type=%s, message=%s",
            request.url.path,
            type(exc).__name__,
            str(exc),
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "AI 분석에 실패했습니다. "
                    "입력한 내용은 유지되며 잠시 후 재시도할 수 있습니다."
                ),
                "code": "parser_unavailable",
                "error_type": type(exc).__name__,
            },
        )

    def require_session(sid):
        try:
            return store.view(sid)
        except WorkflowError as exc:
            raise HTTPException(404, "정산을 찾지 못했습니다.") from exc

    def extract(body: ParseBody):
        # parse_and_review는 context와 issues를 포함한 ParseResult를 반환한다.
        # 근거가 없으면 기존 단일 인자 파서와도 호환된다.
        if not body.text.strip():
            raise ValueError("정산 내용을 입력해 주세요.")
        if body.supplied_evidence is None:
            return parse(body.text)
        return parse(body.text, supplied_evidence=body.supplied_evidence)

    @app.post("/parse", response_model=ParseResult)
    def parse_request(body: ParseBody):
        # 팀원의 추출·검토 API: 결과만 반환하며 세션은 저장하지 않는다.
        try:
            return extract(body)
        except ManualInputRequired as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "manual_input_required", "message": str(exc)},
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

    @app.get("/")
    def home():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/api/schema")
    def schema():
        return load_contract()[1]

    @app.get("/api/sessions")
    def sessions():
        with closing(sqlite3.connect(store.path)) as db:
            rows = db.execute("SELECT document FROM sessions ORDER BY rowid DESC LIMIT 100").fetchall()
        items = []
        for row in rows:
            doc = json.loads(row[0])
            rev = doc["revisions"][-1]
            items.append({"session_id": doc["session_id"], "title": doc["source_text"][:60],
                          "input_revision": rev["input_revision"], "created_at": rev["created_at"]})
        return items

    @app.post("/api/sessions")
    def new_session(body: ParseBody):
        if not body.text.strip():
            raise HTTPException(422, "정산 내용을 입력해 주세요.")
        sid = store.start(extract(body))
        return store.view(sid)

    @app.post("/api/sessions/manual")
    def manual_session(body: ManualBody):
        contract = load_contract()
        parsed = SimpleNamespace(context=validate_context_data(body.context),
                                 source_text=body.source_text, supplied_evidence=None,
                                 model="manual", prompt_version=contract[2],
                                 schema_sha256=contract[3], attempts=0)
        return store.view(store.start(parsed))

    @app.get("/api/sessions/{sid}")
    def get_session(sid: str):
        return require_session(sid)

    @app.patch("/api/sessions/{sid}/context")
    def edit_session(sid: str, body: EditBody):
        require_session(sid)
        store.revise(sid, body.input_revision, body.context)
        return store.view(sid)

    @app.post("/api/sessions/{sid}/confirm")
    def confirm_session(sid: str, body: ConfirmBody):
        require_session(sid)
        return store.confirm(sid, body.input_revision, reviewed_by=body.reviewed_by,
                             review_notes=body.review_notes, checks=body.checks.model_dump())

    @app.post("/api/sessions/{sid}/calculate")
    def calculate_session(sid: str, body: CalculateBody):
        require_session(sid)
        return store.calculate(sid, body.confirmation_id)

    # 기존 영수증 라우터
    app.include_router(receipt_router(store, parse, ROOT, ocr=ocr))

    # Gemini 멀티모달 라우터
    from backend.multimodal_router import make_multimodal_router

    multimodal_router = make_multimodal_router(app)

    print("[DEBUG] app type:", type(app))
    print("[DEBUG] app.router type:", type(app.router))
    print("[DEBUG] app.include_router:", app.include_router)
    print("[DEBUG] routes before:", len(app.routes))

    app.include_router(multimodal_router)

    print("[DEBUG] routes after:", len(app.routes))
    print("[DEBUG] app.routes is app.router.routes:",
          app.routes is app.router.routes)

    for route in app.routes:
        print(
            "[APP ROUTE]",
            getattr(route, "path", None),
            getattr(route, "methods", None),
            type(route).__name__
        )

    return app



app = create_app(os.getenv("SETTLEMENT_DB_PATH"))


