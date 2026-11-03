# FastAPI + HTML/CSS/JS 웹 MVP

## 실행 (Windows PowerShell)
```powershell
cd C:\Users\Maehwa\detox
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

브라우저에서 http://127.0.0.1:8000 접속. 루트 `.env`의 `GEMINI_API_KEY`, `GEMINI_MODEL` 필요.

## API
- `POST /api/parse` : `{ "text": "..." }`
- `PUT /api/sessions/{sid}/context` : `{ "revision": 1, "context": {...} }`
- `POST /api/sessions/{sid}/confirm` : `{ "revision": 2, "reviewed_by": "총무" }`
- `POST /api/sessions/{sid}/calculate`

## 주의
- 기존 `app.py`는 `app_legacy.py`로 백업됨. 기존 `parser.py`, `calculator.py`, `workflow.py`는 변경하지 않음.
- 세션은 메모리에만 보관. 재시작 시 삭제. 단일 프로세스 로컬 데모 전용. 인증/영속화/감사 기록 미구현.
- `issues=[]`도 원문과 일치한다는 보증은 아니므로 사용자가 반드시 확인해야 함.
- 변경한 `parse_query.md`는 이 ZIP에 자동 반영되지 않으므로 로컬 최신 파일을 유지해야 함.
