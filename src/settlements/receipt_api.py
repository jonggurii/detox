"""로컬 단일 프로세스용 영수증 업로드 → 사람 검수 → 기존 LLM/정산 연결."""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4
import json
import sqlite3
import time

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .parser import load_contract, validate_context_data
from .receipt_ocr import MAX_BYTES, OCRError, PaddleReceiptOCR, prepare_image
from .receipt_fields import extract_receipt_fields
from .receipt_draft import ReceiptDraftInput, manual_context, reviewed_evidence, condition_text


class ReceiptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_text: str = Field(min_length=1, max_length=24000)
    reviewed_by: str = Field(min_length=1, max_length=100)
    image_checked: StrictBool
    text: str = Field(min_length=1, max_length=12000)
    mode: Literal["llm", "manual"] = "llm"


class ReceiptAIInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_review_revision: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1, max_length=12000)


def receipt_router(store, parse, root, ocr=None):
    router = APIRouter()
    engine = ocr if ocr is not None else PaddleReceiptOCR()
    directory = Path(store.path).parent / "receipts"
    directory.mkdir(parents=True, exist_ok=True)
    upload_lock, parse_lock = Lock(), Lock()
    last_call = [float("-inf")]
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
        db.commit()

    def save(doc, new=False):
        with closing(sqlite3.connect(store.path)) as db:
            value = json.dumps(doc, ensure_ascii=False, allow_nan=False)
            if new:
                db.execute("INSERT INTO receipts VALUES (?, ?)", (doc["receipt_id"], value))
            else:
                db.execute("UPDATE receipts SET document = ? WHERE id = ?", (value, doc["receipt_id"]))
            db.commit()

    def get(rid):
        with closing(sqlite3.connect(store.path)) as db:
            row = db.execute("SELECT document FROM receipts WHERE id = ?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "영수증을 찾지 못했습니다.")
        doc = json.loads(row[0])
        doc.setdefault("review_revision", 0)
        if "fields" not in doc:
            doc["fields"] = extract_receipt_fields(doc.get("ocr") or {})
        return doc

    def request_key(value):
        return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def save_in(db, doc):
        db.execute("UPDATE receipts SET document = ? WHERE id = ?",
                   (json.dumps(doc, ensure_ascii=False, allow_nan=False), doc["receipt_id"]))

    def read_in(db, rid):
        row = db.execute("SELECT document FROM receipts WHERE id = ?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(404, "영수증을 찾지 못했습니다.")
        return json.loads(row[0])

    def review_value(body):
        try:
            evidence = reviewed_evidence(body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {**body.content(), "reviewed_text": evidence,
                "reviewed_at": datetime.now(timezone.utc).isoformat()}

    def check_version(doc, expected):
        if doc.get("review_revision", 0) != expected:
            raise HTTPException(409, "다른 화면에서 영수증이 수정됐습니다. 새로 불러와 대조해 주세요.")

    def manual_parsed(body, evidence):
        contract = load_contract()
        return SimpleNamespace(context=validate_context_data(manual_context(body)),
            source_text=condition_text(body), supplied_evidence=evidence, model="manual",
            prompt_version=contract[2], schema_sha256=contract[3], attempts=0)

    def commit_session(rid, parsed, key, expected, review=None):
        with closing(sqlite3.connect(store.path, timeout=10)) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc = read_in(db, rid)
                if doc["session_id"]:
                    if doc["request_key"] != key:
                        raise HTTPException(409, "이미 연결한 영수증입니다. 연결한 정산에서 수정해 주세요.")
                    sid = doc["session_id"]
                else:
                    check_version(doc, expected)
                    if review is not None:
                        doc["review"] = review
                        doc["review_revision"] = expected + 1
                    sid = store.start(parsed, connection=db)
                    doc.update(session_id=sid, request_key=key)
                    save_in(db, doc)
        return store.view(sid)

    @router.post("/api/receipts/{rid}/draft")
    def manual_draft(rid: str, body: ReceiptDraftInput):
        review = review_value(body)
        parsed = manual_parsed(body, review["reviewed_text"])
        return commit_session(rid, parsed, request_key({"mode": "manual", **body.content()}),
                              body.expected_review_revision, review)

    @router.post("/api/receipts/{rid}/review")
    def prepare_ai(rid: str, body: ReceiptDraftInput):
        review = review_value(body)
        key = request_key(body.content())
        with closing(sqlite3.connect(store.path, timeout=10)) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                doc = read_in(db, rid)
                if doc["session_id"]:
                    raise HTTPException(409, "이미 연결한 영수증입니다. 연결한 정산에서 수정해 주세요.")
                if doc.get("review_key") != key:
                    check_version(doc, body.expected_review_revision)
                    doc.update(review=review, review_key=key,
                               review_revision=body.expected_review_revision + 1)
                    save_in(db, doc)
        return {"receipt_id": rid, "review_revision": doc["review_revision"],
                "evidence": doc["review"]["reviewed_text"], "hint": condition_text(body)}

    @router.get("/api/receipts/{rid}/handoff")
    def ai_handoff(rid: str):
        doc = get(rid)
        if not doc.get("review_key"):
            raise HTTPException(409, "영수증 입력 화면에서 먼저 검수해 주세요.")
        review = doc["review"]
        data = {k: review[k] for k in ReceiptDraftInput.model_fields if k in review}
        return {"receipt_id": rid, "review_revision": doc["review_revision"],
                "evidence": review["reviewed_text"], "hint": condition_text(ReceiptDraftInput(**data))}

    @router.post("/api/receipts/{rid}/ai")
    def apply_ai(rid: str, body: ReceiptAIInput):
        if not body.text.strip():
            raise HTTPException(422, "정산 조건을 입력해 주세요.")
        if not parse_lock.acquire(blocking=False):
            raise HTTPException(429, "다른 AI 추출을 처리 중입니다.")
        try:
            doc = get(rid)
            check_version(doc, body.expected_review_revision)
            if not doc.get("review_key"):
                raise HTTPException(409, "영수증 검수가 필요합니다.")
            key = request_key({"mode": "llm", "review_key": doc["review_key"], "text": body.text})
            if doc["session_id"]:
                if doc["request_key"] != key:
                    raise HTTPException(409, "이미 연결한 영수증입니다.")
                return store.view(doc["session_id"])
            if time.monotonic() - last_call[0] < 10:
                raise HTTPException(429, "AI 재호출은 10초 후 가능합니다.")
            last_call[0] = time.monotonic()
            parsed = parse(body.text, supplied_evidence=doc["review"]["reviewed_text"])
            return commit_session(rid, parsed, key, body.expected_review_revision)
        finally:
            parse_lock.release()

    @router.get("/receipts/new")
    def page():
        return FileResponse(Path(root) / "frontend" / "receipt.html")

    @router.post("/api/receipts", status_code=201)
    def upload(file: UploadFile = File(...)):
        if not upload_lock.acquire(blocking=False):
            raise HTTPException(429, "다른 영수증을 읽는 중입니다. 잠시 후 다시 시도해 주세요.")
        try:
            try:
                raw = file.file.read(MAX_BYTES + 1)
                image = prepare_image(raw)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            rid = uuid4().hex
            folder = directory / rid
            folder.mkdir()
            (folder / "original.bin").write_bytes(raw)
            image.save(folder / "image.png")
            warning = None
            try:
                output = engine.read(folder / "image.png")
            except OCRError as exc:
                warning = str(exc)
                output = {"text": "", "blocks": [], "low_score_count": 0}
            if not output["text"] and not warning:
                warning = "글자를 찾지 못했습니다. 선명한 사진을 올리거나 직접 입력해 주세요."
            doc = {"receipt_id": rid, "created_at": datetime.now(timezone.utc).isoformat(),
                   "image_sha256": sha256(raw).hexdigest(), "ocr": output,
                   "fields": extract_receipt_fields(output), "review_revision": 0,
                   "warning": warning, "review": None, "request_key": None, "session_id": None}
            save(doc, new=True)
            return doc
        finally:
            file.file.close()
            upload_lock.release()

    @router.get("/api/receipts/{rid}")
    def read(rid: str):
        return get(rid)

    @router.get("/api/receipts/{rid}/image")
    def image(rid: str):
        doc = get(rid)
        return FileResponse(directory / doc["receipt_id"] / "image.png", media_type="image/png")

    @router.post("/api/receipts/{rid}/session")
    def start_session(rid: str, body: ReceiptInput):
        # 기존 클라이언트용 경로. 새 화면은 /draft 또는 검수 후 /ai를 사용한다.
        if not body.image_checked or not all(v.strip() for v in
                (body.reviewed_text, body.reviewed_by, body.text)):
            raise HTTPException(422, "영수증 대조 확인과 담당자·텍스트·정산 조건을 입력해 주세요.")
        if not parse_lock.acquire(blocking=False):
            raise HTTPException(429, "다른 추출을 처리 중입니다. 잠시 후 다시 시도해 주세요.")
        try:
            doc = get(rid)
            if doc.get("review_key"):
                raise HTTPException(409, "검수 화면의 정산하기 또는 AI 적용 버튼을 이용해 주세요.")
            key = sha256(json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if doc["session_id"]:
                if doc["request_key"] != key:
                    raise HTTPException(409, "이미 연결한 영수증입니다. 정산 화면에서 조건을 수정하거나 새 영수증으로 시작해 주세요.")
                return store.view(doc["session_id"])
            if body.mode == "llm" and time.monotonic() - last_call[0] < 10:
                raise HTTPException(429, "AI 재호출 간격은 10초입니다. 잠시 후 다시 시도하거나 직접 입력해 주세요.")
            # 실패하더라도 원본 OCR과 사람이 수정한 근거는 각각 보관한다.
            expected = doc.get("review_revision", 0)
            with closing(sqlite3.connect(store.path, timeout=10)) as db:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    current = read_in(db, rid)
                    check_version(current, expected)
                    if current["session_id"]:
                        raise HTTPException(409, "이미 연결한 영수증입니다.")
                    current["review"] = {**body.model_dump(), "reviewed_at": datetime.now(timezone.utc).isoformat()}
                    current["review_revision"] = expected + 1
                    save_in(db, current)
            if body.mode == "llm":
                last_call[0] = time.monotonic()
                parsed = parse(body.text, supplied_evidence=body.reviewed_text)
            else:
                contract = load_contract()
                parsed = SimpleNamespace(context=validate_context_data({"participants": [], "expenses": []}),
                    source_text=body.text, supplied_evidence=body.reviewed_text, model="manual",
                    prompt_version=contract[2], schema_sha256=contract[3], attempts=0)
            # start()는 검토할 초안만 만든다. 확인/계산은 기존 workflow의 별도 단계다.
            return commit_session(rid, parsed, key, expected + 1)
        finally:
            parse_lock.release()

    @router.get("/api/sessions/{sid}/receipt")
    def session_receipt(sid: str):
        with closing(sqlite3.connect(store.path)) as db:
            rows = db.execute("SELECT document FROM receipts").fetchall()
        for (value,) in rows:
            doc = json.loads(value)
            if doc["session_id"] == sid:
                return {"receipt_id": doc["receipt_id"], "review": doc["review"]}
        return None

    return router
