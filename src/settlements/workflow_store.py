"""웹 요청 사이에 정산 초안·확인·계산 버전을 보존하는 저장 모듈.

SQLite에 원문, 모든 입력 버전, 확인 기록, 계산 미리보기를 보존한다.
은행 송금·메시지 발송·입금 완료 처리는 하지 않는다.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
from uuid import uuid4

from .calculator import CalculationError, calculate_settlement
from .parser import ParserError, load_contract, parse_and_review, review_context, validate_context_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class WorkflowError(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return sha256(encode(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def remove_redundant_exclusions(data):
    """기본 분담 대상에 없는 사람의 exclude만 제거한다. 원본은 수정하지 않는다."""
    from copy import deepcopy

    clean = deepcopy(data)
    rules = {}
    for rule in clean.get("split_rules", []):
        key = (rule.get("expense_index"), rule.get("item_index"))
        rules.setdefault(key, []).append(rule)
    filtered = []
    for ex in clean.get("exceptions", []):
        key = (ex.get("expense_index"), ex.get("item_index"))
        candidates = rules.get(key, [])
        if (
            ex.get("kind") == "exclude"
            and len(candidates) == 1
            and isinstance(candidates[0].get("participant_names"), list)
            and ex.get("participant_name") not in candidates[0]["participant_names"]
            and ex.get("participant_name") in clean.get("participants", [])
        ):
            continue
        filtered.append(ex)
    if "exceptions" in clean:
        clean["exceptions"] = filtered
    return clean


def review(data):
    schema = load_contract()[1]
    clean = validate_context_data(data, schema=schema).model_dump(exclude_unset=True)
    clean = remove_redundant_exclusions(clean)
    issues = [issue.model_dump() for issue in review_context(clean, schema=schema)]
    return clean, issues


class WorkflowStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
            db.commit()

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self, session_id):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT document FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if row is None:
                    raise WorkflowError("존재하지 않는 세션입니다.")
                document = json.loads(row[0])
                yield document
                db.execute("UPDATE sessions SET document = ? WHERE id = ?", (encode(document), session_id))
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _revision(self, data, number):
        clean, issues = review(data)
        return {"input_revision": number, "context": clean, "issues": issues,
                "context_sha256": digest(clean), "schema_sha256": load_contract()[3],
                "created_at": now()}

    def start(self, parsed, *, connection=None):
        session_id = uuid4().hex
        revision = self._revision(parsed.context.model_dump(exclude_unset=True), 1)
        if parsed.schema_sha256 != revision["schema_sha256"]:
            raise WorkflowError("추출에 사용한 스키마와 현재 스키마가 다릅니다.")
        document = {
            "session_id": session_id,
            "source_text": parsed.source_text,
            "supplied_evidence": parsed.supplied_evidence,
            "parse_metadata": {key: getattr(parsed, key) for key in
                               ("model", "prompt_version", "schema_sha256", "attempts")},
            "revisions": [revision], "confirmations": [], "calculations": [],
        }
        if connection is not None:
            # 영수증과 정산 초안을 같은 트랜잭션에서 저장할 때 사용한다.
            connection.execute("INSERT INTO sessions VALUES (?, ?)", (session_id, encode(document)))
        else:
            with self._connection() as db:
                db.execute("INSERT INTO sessions VALUES (?, ?)", (session_id, encode(document)))
                db.commit()
        return session_id

    def view(self, session_id):
        with self._connection() as db:
            row = db.execute("SELECT document FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise WorkflowError("존재하지 않는 세션입니다.")
        return json.loads(row[0])

    def revise(self, session_id, expected_revision, edited_context):
        with self._transaction(session_id) as doc:
            current = doc["revisions"][-1]
            if current["input_revision"] != expected_revision:
                raise WorkflowError("입력 버전이 변경됐습니다. 최신 내용을 다시 확인해 주세요.")
            revision = self._revision(edited_context, expected_revision + 1)
            doc["revisions"].append(revision)
            # 과거 확인·계산은 삭제하지 않는다. 버전 불일치로 재사용을 막는다.
            return revision

    def confirm(self, session_id, expected_revision, *, reviewed_by, review_notes, checks):
        if not isinstance(reviewed_by, str) or not reviewed_by.strip():
            raise WorkflowError("확인 담당자를 입력해 주세요.")
        if not isinstance(review_notes, str) or not review_notes.strip():
            raise WorkflowError("원문·조건 확인 근거를 기록해 주세요.")
        if not isinstance(checks, dict):
            raise WorkflowError("확인 항목이 필요합니다.")
        with self._transaction(session_id) as doc:
            revision = doc["revisions"][-1]
            if revision["input_revision"] != expected_revision:
                raise WorkflowError("이전 버전은 확인할 수 없습니다.")
            self._check_revision(revision)
            required = {"source_reviewed", "people_resolved", "conditions_reviewed"}
            if revision["context"].get("contributions"):
                required.add("funding_verified")
            if any(checks.get(key) is not True for key in required):
                raise WorkflowError("원문·실제 인물·분담 조건·필요한 찬조 자금 확인을 완료해 주세요.")
            _, issues = review(revision["context"])
            if issues:
                raise WorkflowError(encode(issues))
            for record in doc["confirmations"]:
                if record["input_revision"] == expected_revision:
                    return record
            record = {
                "confirmation_id": uuid4().hex, "input_revision": expected_revision,
                "context_sha256": revision["context_sha256"],
                "reviewed_by": reviewed_by.strip(), "review_notes": review_notes.strip(),
                "checks": {key: True for key in sorted(required)}, "confirmed_at": now(),
            }
            doc["confirmations"].append(record)
            return record

    def _check_revision(self, revision):
        if digest(revision["context"]) != revision["context_sha256"]:
            raise WorkflowError("저장된 입력의 해시가 일치하지 않습니다.")
        if revision["schema_sha256"] != load_contract()[3]:
            raise WorkflowError("스키마가 바뀌었습니다. 새 입력 버전으로 검토해 주세요.")

    def calculate(self, session_id, confirmation_id):
        with self._transaction(session_id) as doc:
            record = next((c for c in doc["confirmations"]
                           if c["confirmation_id"] == confirmation_id), None)
            if record is None:
                raise WorkflowError("이 세션의 유효한 확인 기록이 아닙니다.")
            revision = doc["revisions"][-1]
            self._check_revision(revision)
            if (record["input_revision"] != revision["input_revision"]
                    or record["context_sha256"] != revision["context_sha256"]):
                raise WorkflowError("확인 이후 입력이 변경됐습니다. 다시 확인해 주세요.")
            for saved in doc["calculations"]:
                if saved["confirmation_id"] == confirmation_id:
                    return saved
            result = calculate_settlement(revision["context"])
            saved = {
                "calculation_id": uuid4().hex, "confirmation_id": confirmation_id,
                "input_revision": revision["input_revision"], "status": "preview",
                "created_at": now(), "result": asdict(result),
            }
            doc["calculations"].append(saved)
            return saved


