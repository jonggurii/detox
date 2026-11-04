"""임시 웹 MVP: 메모리 세션. 영속화/인증/배포는 추후 구현."""
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from settlements.parser import parse_and_review, validate_context_data, review_context, ParserError
from settlements.calculator import calculate_settlement, CalculationError
from settlements.workflow import serialize_calculation

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="복합 N빵 정산 MVP")
_sessions = {}
_lock = RLock()

class ParseBody(BaseModel):
    text: str = Field(min_length=1, max_length=12000)

class EditBody(BaseModel):
    revision: int
    context: dict

class ConfirmBody(BaseModel):
    revision: int
    reviewed_by: str = Field(min_length=1, max_length=100)


def _issues(context):
    return [i.model_dump() for i in review_context(context)]


def _get(sid):
    session = _sessions.get(sid)
    if session is None:
        raise HTTPException(404, "정산 세션을 찾을 수 없습니다.")
    return session


def _snapshot(sid, session):
    return {"session_id": sid, "revision": session["revision"],
            "context": session["context"], "issues": session["issues"],
            "confirmed": session["confirmed"]}

@app.get("/")
def home():
    return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/frontend/style.css")
def style():
    return FileResponse(ROOT / "frontend" / "style.css", media_type="text/css")

@app.get("/frontend/app.js")
def javascript():
    return FileResponse(ROOT / "frontend" / "app.js", media_type="text/javascript")

@app.post("/api/parse")
def parse(body: ParseBody):
    try:
        parsed = parse_and_review(body.text)
        context = parsed.context.model_dump(exclude_unset=True)
        issues = [i.model_dump() for i in parsed.issues]
    except (ParserError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    sid = uuid4().hex
    session = {"revision": 1, "context": context, "issues": issues,
               "confirmed": False, "source_text": body.text}
    with _lock:
        _sessions[sid] = session
    return _snapshot(sid, session)

@app.put("/api/sessions/{sid}/context")
def edit(sid: str, body: EditBody):
    with _lock:
        session = _get(sid)
        if session["revision"] != body.revision:
            raise HTTPException(409, "입력 버전이 변경됐습니다. 새로고침 후 다시 시도하세요.")
        try:
            context = validate_context_data(body.context).model_dump(exclude_unset=True)
            issues = _issues(context)
        except (ParserError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        session.update(revision=session["revision"]+1, context=context,
                       issues=issues, confirmed=False)
        return _snapshot(sid, session)

@app.post("/api/sessions/{sid}/confirm")
def confirm(sid: str, body: ConfirmBody):
    with _lock:
        session = _get(sid)
        if session["revision"] != body.revision:
            raise HTTPException(409, "확인하려는 입력 버전이 변경됐습니다.")
        session["issues"] = _issues(session["context"])
        if session["issues"]:
            raise HTTPException(409, "미해결 정산 조건이 있어 확정할 수 없습니다.")
        session["confirmed"] = True
        session["reviewed_by"] = body.reviewed_by
        return _snapshot(sid, session)

@app.post("/api/sessions/{sid}/calculate")
def calculate(sid: str):
    with _lock:
        session = _get(sid)
        if not session["confirmed"]:
            raise HTTPException(409, "먼저 정산 조건을 확인해야 합니다.")
        try:
            result = calculate_settlement(session["context"])
        except (CalculationError, ParserError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
            return serialize_calculation(result)
