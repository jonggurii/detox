# SPEC.md — 모아정산 | 복합 N빵 정산 MVP

> 문서 버전: **3.7 **
> 프로젝트: 2026학년도 2학기 아주대학교 AI 캡스톤디자인 · 11조 Detox
> 서비스: **모아정산** (저장소: https://github.com/jonggurii/detox)
> 도메인 정본: [`ontology.yaml`](ontology.yaml) v3.6 / 문제 근거: [`PROBLEM.md`](PROBLEM.md), [`research/interviews_union.md`](research/interviews_union.md)
> 입력 DTO 정본: `src/settlements/schemas/request_context.schema.json` / 사용자 실행 안내: [`../README.md`](../README.md)

## 1. 문제 (왜 만드는가)

모임의 정산 담당자는 여러 차수의 참석 변화, 사람별 소비 항목, 술값 제외, 찬조금과 대신 부담을 반영하면서 결제자·청구액을 맞추기 위해 메모장과 계산기를 오가며 반복 계산한다. 또한 정산 근거를 설명하고 송금을 재안내하는 부담을 겪는다. 이 문제는 인터뷰 로그 6·7·12·15·17·18·19·20에서 관찰됐다.

**해결 가설:** 자연어·영수증에서 정산 조건의 *후보*를 추출하고, 사용자가 이를 확인·수정한 뒤 Python 계산기로 원 단위 부담액과 결제자별 송금액을 계산하면 반복 입력·재계산 및 잘못된 청구를 줄일 수 있다. 효과가 이미 입증되었다는 뜻은 아니다.

## 2. 타깃 사용자와 대표 작업

- **주 사용자:** 모임/회식/여행에서 비용을 먼저 내거나 여러 사람의 지출을 모아 정산하는 대학생·직장인 총무.
- **관련 사용자:** 선결제자, 부담자, 찬조자, 송금 안내를 받는 사람.
- **비대상:** 법인 회계·세무 처리, 자동 은행 이체/거래 조회, 자동 카카오톡 발송.
- **핵심 흐름:** 입력 방식 선택 → 정산 자료 입력 → (AI인 경우) 추출 후보 검토 → 누락·충돌 수정 → 승인 → 계산/송금 내역 확인 → 사용자에 의한 실제 송금·입금 대조.

## 3. MVP 핵심 기능과 범위

### 3.1  **MVP 대상**

| ID | 사용자 기능 | 구현 경로/범위 | 
|---|---|---|---|
| **MVP1** | 자연어 AI 정산 | Gemini가 문장에서 `RequestContext` 후보 생성 → 의미 검토 → 사용자 확인 → Python 계산 |
| **MVP2** | 영수증 이미지 + 추가 설명 | JPG/PNG 이미지에서 항목·금액 후보 추출 → 사진과 대조·수정 → 정산 조건 확인; 사진만으로 소비자 임의 확정 금지 | 
| **MVP3** | 직접 N분의 1 | 참여자·결제자·총지출액 입력 → `equal` 규칙 구성 → 검토/승인 → Python 계산 | 
| **MVP4** | 직접 차액 정산 | 모바일 UI에서 송금자·수취인·송금액을 지정하고 합계 검증 후 송금 목록 구성 |
| **MVP5** | 정산 조건 검토·승인 | 누락/불일치 이슈 표시, 수정 이력과 입력 버전 확인, 확인 ID 없는 계산 차단 | 
| **MVP6** | 개인별 부담액·송금 결과 | 항목별 부담액, 참여자별 합계, 결제자에게 보낼 금액 확인·공유용 문구 사용 | 

**구현 경계:** `MVP4`는 현재 `mobile/src/app/index.tsx`에서 `AsyncStorage`에 **기기 로컬** 저장되는 송금 목록이다. 백엔드 `RequestContext`의 비용 항목 분할이나 `POST /api/sessions/{sid}/calculate`로 계산된 결과가 아니며, 서버와 자동 동기화되지 않는다. **차액 정산의 `송금 총액`은 전체 식사비가 아니라 개별 송금액의 합**이다. 여러 결제자 간 순채무 최적 상계와 혼동하지 않는다.

**모델·OCR 정책:** `GEMINI_MODEL=gemini-3.5-flash`를 텍스트·이미지 추출 공통 기본 모델명으로 사용한다. `google-genai` SDK, `src/settlements/gemini_client.py`의 공통 설정과 `receipt_reader.py`의 이미지 구조화 추출을 사용하며 실제 원격 모델 접근/성능은 유효한 키를 사용한 별도 실측이 필요하다.

### 3.2 후속 범위 

- 은행 자동 이체, 실거래 자동 조회·검증, 실제 카카오톡/문자 자동 발송.
- 서비스 간/기기 간 차액 정산 동기화, 서버 기반 차액 정산 청구 관리 및 송금 관계의 자동 상계 최적화.
- 보안이 검증된 공개 다중 사용자 운영, Render 무료 인스턴스의 영구 데이터 보존 보증.
- 자동 결제, 영수증 훼손 복원, 실시간 음성 Live API, 사람/금액/찬조 적용 비율의 무근거 자동 추측.
- 입금 대조·관계별 재안내 기능의 완전한 서버 측 상태 관리와 자동 발송. 모바일의 로컬 입금 체크·안내 초안 UI와 구분한다.

### 3.3 실제 구현·검증 상태 

| 구분 | 확인한 근거 | 판정 |
|---|---|---|
| 자연어 파싱·검토 | `src/settlements/parser.py`, 스키마, `tests/test_parser.py`, 기존 골든 테스트 | 코드/결정적 테스트 존재; |
| 영수증 이미지 추출 | `receipt_reader.py`, `receipt_api.py`, `backend/multimodal_router.py`, `tests/test_multimodal_integration.py` | API 경로와 모의 이미지 추출 검증; |
| Python 정산 | `calculator.py`, `allocation_math.py`, 정산·회귀 테스트 | 결정적 계산 구현/검사 존재 |
| 검토·승인·수정 | `workflow_store.py`, `tests/test_web_api.py` | 버전/승인 ID/반복 계산 경로 테스트 존재 |
| 직접 N분의 1 | 모바일 입력 화면 + 서버 `/api/sessions/manual` | 코드 경로 존재; 배포 APK 화면 체험 별도 확인 |
| 직접 차액 정산 | 모바일 `createDiff()`, `diffValid`, `AsyncStorage` |
| Evals | `evals/EVAL_DESIGN.md`, `evals/evalset.jsonl`(35케이스), `evals/run_evals.py`, `evals/results/` | 

`pytest` 통과는 실제 Gemini 서버 응답 품질이나 Render/Expo 배포 버전의 정상 동작을 증명하지 않는다. 배포 상태/앱 화면은 평가 전 실제 기기에서 확인한다.

## 4. 도메인·데이터 계약

### 4.1 정본 온톨로지

현행 `docs/ontology.yaml` **v3.6의 8개 핵심 클래스**를 유지한다.

`Participant`, `SettlementSession`, `Expense`, `Item`, `SplitRule`, `ItemException`, `Allocation`, `SettlementResult`.

차수/참석·영수증·찬조·입금/재안내는 현행 YAML의 하위 구조로 표현한다. 기존 v3.3의 15개 클래스 문서와 혼동하지 않는다. **`RequestContext`는 도메인 클래스가 아니라 사용자 확인 전의 입력 DTO**다.

### 4.2 자연어 입력 `RequestContext`

최상위 키는 `participants`, `rounds`, `expenses`, `split_rules`, `exceptions`, `contributions`, `tone`, `relationship`, `reminder_handling`의 **9개**다. 필수 최상위 키는 `participants`, `expenses`; 나머지 생략/`null` 허용 여부는 JSON Schema가 정본이다.

- `Expense.total_amount`는 결제 한 건의 원래 총액, `Item.amount`는 그 안의 항목 전체 금액이다.
- `split_rules[].method`: `equal` 또는 `explicit_amount`; `exceptions[].kind`: `exclude`, `fixed_amount`, `covered_by_other`.
- `expense_index`·`item_index`는 해당 추출 결과 배열의 **0-based 위치**이지 영구 ID가 아니다.
- `contributions`의 적용 대상/금액을 짐작하지 않고 확인 질문으로 남긴다.
- `reminder_handling`은 스키마의 `undecided`, `personal_follow_up`, `external_service_only`를 따른다. 계산 결과나 실제 발송 여부가 아니다.
- 이름이 같은 사람, “나”, 호칭, 중도 합류·이탈의 부담 범위는 임의로 결정하지 않는다.

**정상 입력 예시(시나리오 1의 의미를 표현한 후보):**

```json
{
  "participants": ["민수", "지훈", "영희"],
  "expenses": [{"payer_name": "민수", "total_amount": 84000, "items": [{"name": "식사비", "amount": 60000}, {"name": "술값", "amount": 24000}]}],
  "split_rules": [
    {"expense_index": 0, "item_index": 0, "method": "equal", "participant_names": ["민수", "지훈", "영희"]},
    {"expense_index": 0, "item_index": 1, "method": "equal", "participant_names": ["민수", "지훈", "영희"]}
  ],
  "exceptions": [{"expense_index": 0, "item_index": 1, "participant_name": "영희", "kind": "exclude", "reason": "영희는 술을 마시지 않았다"}]
}
```

이 예시는 **사용자가 확인한 정확한 조건을 코드에 전달하는 경우의 테스트 데이터**이지 Gemini가 실제로 위 JSON을 출력했다는 증거가 아니다.

### 4.3 영수증 추출 계약

`receipt_reader.py`의 현재 모델 응답 JSON은 `items[{name,amount}]`, `total_amount`, `raw_lines[]`, `notes[]`이며, `name`과 `amount`/총액은 모를 때 `null`을 허용한다. 로컬 파서는 결과를 추가 검증하여 `warnings[]`를 구성한다.

- 영수증 업로드는 JPG/PNG 정지 이미지, 최대 10MB, 1,200만 화소로 제한.
- 영수증에 없는 **사람·차수·메뉴 소비자·송금 관계는 추정하지 않음**.
- 품목 합계와 영수증 총액이 다르면 자동으로 차액을 채워 넣지 않고 확인 경고를 출력.
- 원본 이미지, 모델 추출 후보, 사용자가 수정한 내용은 별도 기록으로 취급.
- 영수증 JSON과 정산 `RequestContext`는 다른 계약이다. 영수증 이미지가 정확하더라도 자연어의 소비 조건 확인이 필요하다.

### 4.4 계산·송금 자료의 구분

`Allocation`은 각 항목의 사람별 소비 부담액이고, `SettlementResult`는 **해당 지출을 먼저 결제한 사람에게 보낼 금액**이다. 결제자 본인의 부담액은 전체 계산에 포함하되 본인에게 송금하라는 요청은 만들지 않는다. 직접 차액 정산의 `direct_transfers`는 모바일 로컬 표현이며 현행 `RequestContext`의 서버 입력 필드가 아니다.

## 5. 인터페이스와 처리 흐름

### 5.1 AI 및 직접 균등 정산의 공통 처리 경계

```text
자연어 문장 ── Gemini 문장 파싱 ───┐
                                 ├─→ RequestContext 후보 → 스키마/의미 검토 → 사용자 수정·승인
영수증 이미지 ─ Gemini 이미지 추출 ──┘                              │
    └─ 이미지 사실 검수 및 정산 조건 별도 확인                      ↓
                                                     Python 원 단위 계산
                                                              ↓
                                             Allocation / SettlementResult
```

**직접 N분의 1**은 Gemini 없이 사용자가 `RequestContext`를 구성한 후 같은 승인·계산 경로를 이용한다. **직접 차액 정산**은 별도 모바일 로컬 경로에서 사용자 지정 송금 목록을 표시한다.

### 5.2 실제 구현 HTTP API (루트 `app.py` 기준)

| 메서드·경로 | 역할 | 구분 |
|---|---|---|
| `POST /parse` | 텍스트·선택적 근거 파싱과 확인 이슈 반환; 세션 저장 없음 | 구현 |
| `POST /api/sessions` | AI 입력에서 검토용 세션 생성 | 구현 |
| `POST /api/sessions/manual` | 사용자가 구성한 DTO로 검토용 세션 생성 | 구현 |
| `GET /api/sessions`, `GET /api/sessions/{sid}` | 세션 목록/상세 | 구현 |
| `PATCH /api/sessions/{sid}/context` | 지정 입력 버전 수정 | 구현 |
| `POST /api/sessions/{sid}/confirm` | 검토 기록 확인 후 승인 | 구현 |
| `POST /api/sessions/{sid}/calculate` | `confirmation_id`로 Python 계산 | 구현 |
| `POST /api/receipts` | 영수증 이미지 업로드 및 Gemini 항목 후보 추출 | 구현 |
| `POST /api/receipts/{rid}/review`, `POST /api/receipts/{rid}/draft`, `POST /api/receipts/{rid}/ai` | 영수증 검수·직접 입력·AI 조건 적용 | 구현 |
| `GET /api/receipts/{rid}`, `GET /api/receipts/{rid}/image`, `GET /receipts/new` | 영수증 상태·이미지·웹 검수 화면 | 구현 |
| `GET /api/receipts/{rid}/handoff`, `POST /api/receipts/{rid}/session`, `GET /api/sessions/{sid}/receipt` | 검토 근거 인계·레거시 세션 연결·원본 영수증 역참조 | 구현 |
| `POST /api/receipts/multimodal-preview` | 사진/설명 입력에서 **검토 후보만** 반환 | 구현 |
| `POST /api/receipts/multimodal-confirm` | 사용자 검수 근거를 문장 파서에 전달 | 구현 |
| `POST /api/sessions/multimodal` | 레거시 호환: 자동 확정 없이 미리보기 | 구현 |
| `GET /api/schema`, `GET /` | 입력 스키마, 웹 시작 화면 | 구현 |

**주의:** 이 표는 저장소 코드에 라우트가 있다는 뜻이며 배포 서버의 현재 실행 버전과 동일하다는 보증이 아니다. `GET /health`나 자동 송금 API는 확인된 구현 인터페이스로 표기하지 않는다.

### 5.3 오류·승인 계약

- 스키마/필수 조건 미충족은 422 또는 검토 이슈를 반환하며 잘못된 값을 추측해 고치지 않는다.
- 세션 버전 충돌, 미해결 조건으로 승인 시도, 이전 `confirmation_id` 사용은 409로 차단한다.
- SDK/모델 장애로 파싱에 실패하면 오류를 반환하고 사용자가 직접 입력할 수 있도록 한다.
- 같은 `confirmation_id`를 다시 계산하면 기존 계산 결과를 재사용하며 중복 청구를 만들지 않는다.
- 송금액 안내는 확인된 계산 결과만 사용하고 실제 송금은 실행하지 않는다.

## 6. 수용 기준(AC) — MVP와 후속의 명시적 구분

**원칙:** 기존 AC1~AC6 및 골든 G01~G08의 기대값은 변경하지 않는다. 아래 `MVP` 열이 `예`인 수용 기준만 **이번 중간평가의 MVP 포함 AC**다. 나머지는 후속 목표로 관리한다. 모든 금액은 가상 예시이며 실제 API 모델 출력의 정확도를 보증하지 않는다.

### 6.1 기존 검토 기능 — 모두 **MVP 대상**

| AC | EARS 조건과 동작 | 판정 기준 | MVP |
|---|---|---|---|
| **AC1** | 정상/최소 입력이 주어지면 시스템은 불필요한 확인 이슈를 생성하지 않는다. | G01/G02 `expect_issue_count=0`, 전체 `(code,path)=[]` | **예** |
| **AC2** | 참여자·결제 정보 또는 결제자 정보가 없으면 시스템은 확인 항목을 반환한다. | G03/G04 이슈 코드·경로 정확히 일치 | **예** |
| **AC3** | 결제 총액과 항목 합계가 다르면 시스템은 원본을 그대로 두고 `item_sum_mismatch`를 반환한다. | G05 | **예** |
| **AC4** | 항목 예외 연결이나 방식이 불명확하면 시스템은 임의 적용 없이 확인을 요청한다. | G06 | **예** |
| **AC5** | 균등 분할에 1원 단위 잔액이 남는데 귀속 대상이 없으면 시스템은 `unresolved_rounding`을 반환한다. | G07 | **예** |
| **AC6** | 확인 요청 또는 공격성 문구가 들어오면 시스템은 입력을 변경하지 않고 지시문을 데이터로 취급한다. | G01~G08 입력 불변, G08 인젝션 | **예** |

### 6.2 네 가지 체험 경로 — **MVP 대상**

| AC | EARS 조건과 동작 | 관측 가능한 기대 결과 | MVP |
|---|---|---|---|
| **MVP1** | 사용자가 자연어로 사람·결제·항목·분담 조건을 입력하면 시스템은 구조화 후보와 확인 문제를 보여 준다. | 8.1의 84,000원 예시에서 정확한 조건이 확인되면 3인 부담액이 32,000/32,000/20,000원 | **예** |
| **MVP2** | 사용자가 영수증과 조건 설명을 업로드하면 시스템은 이미지 항목·금액 후보를 보여주고 수정/검토를 요구한다. | 업로드 직후 자동 최종 정산/송금 없음; 누락·합계 불일치 시 확인 경고 | **예** |
| **MVP3** | 사용자가 90,000원, 3명, 민수 결제의 직접 균등 정산을 확인하면 Python 계산기가 분담한다. | 각 30,000원, 지훈·영희 → 민수 각 30,000원 | **예** |
| **MVP4** | 사용자가 직접 송금 지시 20,000원+15,000원을 입력하면 모바일 화면은 합계가 35,000원일 때만 로컬 정산 목록을 만든다. | 지훈→민수 20,000원, 영희→민수 15,000원; 불일치·자기 자신에게 송금이면 생성 차단 | **예(로컬)** |
| **MVP5** | 사용자가 수정 전 또는 승인 없이 계산을 시도하면 시스템은 실행을 차단한다. | 검토 조건 승인 기록과 버전이 맞을 때만 계산; 재계산 멱등 | **예** |
| **MVP6** | 계산된 정산이 있으면 시스템은 개인별 부담액과 송금자를 보여 주고 공유용 안내를 제공한다. | 결제자 자기 청구/0원 송금 요청 없음; 자동 계좌이체 없음 | **예** |

### 6.3 정산의 불변 규칙 — **MVP 대상**

| AC | 판정 가능한 규칙 | MVP |
|---|---|---|
| **CALC1** | 확정 찬조 공제 → 항목 제외/합의 몫 → 기본 분배 → 대신 부담 → 원 단위 잔액 귀속; 항목·결제·청구 합계에서 1원 오류 없음 | **예** |
| **CALC2** | 찬조자라는 이유만으로 소비 대상 제외하지 않고 확정된 항목별 찬조액만 공제 | **예** |
| **CALC3** | 미지정 원 단위 잔액을 몰래 버리거나 반올림하지 않고 확인 이슈로 계산 차단 | **예** |
| **CLAIM1** | 실제 결제자가 수취인이며 결제자 자기 자신·0원 대상 송금 요청 금지 | **예** |
| **CLAIM2** | 동일 승인 반복 계산 시 중복 청구 없음, 수정 시 과거 승인 ID 사용 차단 | **예** |
| **EXTRACT1** | 근거 없는 사람·금액·항목을 추측하지 않고 불명확하면 확인 대상으로 둠 | **예** |
| **EXTRACT2** | 텍스트·영수증은 같은 `GEMINI_MODEL` 설정 사용, 서로 다른 프롬프트/출력 스키마 사용 | **예** |
| **EXTRACT3** | 영수증/문장 추출 후보는 사용자 승인 전 계산·송금 요청으로 확정하지 않음 | **예** |
| **EXTRACT4** | 영수증/텍스트 속 지시문이 정책이나 합계 계산을 변경하지 못함 | **예** |
| **EXTRACT5** | 원문·검토 수정본·입력 버전이 구분되고 무단 덮어쓰기 금지 | **예** |
| **EXTRACT6** | API 장애·JSON 형식 실패·합계 불일치를 정상 추출 성공으로 둔갑시키지 않음 | **예** |

### 6.4 **후속 AC — 중간평가 MVP 제외**

| AC | 후속 완료 기준 | MVP |
|---|---|---|
| **PAY1** | 서버에서 수동 대조 확인한 입금만 완료액에 합산 | **아니오** |
| **PAY2** | 동일 실제 입금의 청구별 매핑 합이 실제 입금액을 초과하지 않음 | **아니오** |
| **NOTICE1** | 계좌가 확인된 경우만 이를 포함하고 관계·말투별 재안내의 서버 기록을 관리 | **아니오** |
| **SYNC1** | 직접 차액 정산의 서버 저장과 타 기기에서 동기화/복원 | **아니오** |
| **TRANSFER1** | 은행 이체 및 메신저 실제 자동 발송 | **아니오/제품 범위 밖** |

## 7. 골든 테스트와 Evals 연결

### 7.1 결정 층 — 골든/회귀 테스트

- 원본: `tests/harness/golden_cases.yaml` G01~G08 (정상·경계·금지 행동, AC1~AC6).
- 하니스: `tests/test_context_review_golden.py`가 YAML을 읽고 `(code,path)`, 건수, 원본 불변 여부를 판정.
- 계산: `tests/test_calculator.py`, `test_calculator_basic.py`, `test_calculator_regression.py`, `test_complex_settlement_improvements.py` 등.
- API/검수: `tests/test_web_api.py`, `test_receipt_api.py`, `test_multimodal_integration.py` 등.
- **검증 공백:** `MVP4` 직접 차액 정산은 모바일 로컬 코드 경로만 확인했다. 해당 화면을 누르는 자동 테스트 또는 현장 시연 증거가 아직 없음. 이 부분을 4단계 검증 보완 대상으로 둔다.
- 결함 주입 기록: `docs/prompts/delegation_<기능>.md`에 실제 주입 결함·실패 케이스·원복 후 결과를 남겨야 한다. 작성/실행되지 않은 기록을 생성했다고 주장하지 않는다.

### 7.2 통계 층 — 강의 7 Evals **4단계 구축 현황**

4단계에서 `evals/EVAL_DESIGN.md`, `evals/evalset.jsonl` **35개(자연어 31, 합성 영수증 4)**, `evals/run_evals.py`, `evals/results/<run_id>.json`, `evals/results/history.csv`, `docs/prompts/delegation_evals.md`를 마련했다. 저장 출력(`--mode stored`) 35건은 **채점기 검증 결과로, Gemini 실측 점수가 아니다**. 실제 모델 평가는 환경에 API 키를 설정하고 `--mode live`로 실행해야 한다. 현재 구조화 정산 추출은 코드로 판정 가능하므로 judge는 사용하지 않으며, `judge_prompt.md`와 사람 라벨은 주관적 문구 평가를 도입할 때 작성한다.

| 평가 지표 | 평가 단위·방법 | 연결 AC | 성격 |
|---|---|---|---|
| 핵심 정산 필드 일치율 | 참가자·원금·품목·분담 대상·예외가 **모두** 근거와 맞는 케이스 비율, 코드 채점 | MVP1, EXTRACT1 | 능력 지표 |
| 영수증 필드 정확성 | 사람의 정답 레이블이 있는 이미지의 품목/금액 일치, 코드 채점 | MVP2, EXTRACT1·6 | 능력 지표 |
| JSON/DTO 형식 준수율 | JSON Schema 통과 비율, 코드 채점 | AC1~6, EXTRACT2 | 절대 제약 |
| 확인 요청 적중률 | 누락·모호·충돌 입력에서 계산 없이 확인 항목 반환한 비율, 코드 채점 | AC2~5, MVP5 | 안전 제약 |
| 금액/사람 환각 건수 | 근거 없는 사람·원금·예외 또는 규칙 무시 지시를 실행한 건수 | AC6, EXTRACT1·4 | 절대 제약 |
| 최종 부담/송금 금액 정확성 | *정답 구조화 입력*으로 계산한 결과의 원화 정수 정확성 | CALC1~3, CLAIM1 | 결정적 검사(골든) |

**2026-11-17 확정 목표: 핵심 추출 정확도 90% 이상.** `text_case_pass_rate`와 `receipt_case_pass_rate`를 각각 평가하며, 영수증은 실물 사진 평가셋을 확대하기 전까지 최종 통과 판정을 보류한다. 안전 절대 규칙(인젝션·임의 청구)은 0건 위반, 형식/확정 차단은 100% 충족을 목표로 한다. 평가 케이스 기대값 및 그 외 기준은 팀의 검토 대상이다. **Gemini 라이브 베이스라인은 아직 측정하지 않았으므로 90% 달성 여부는 미확인**이다.

평가 데이터는 정상 요청 외에 적어도 **두 가지 이상**의 경계·실패 범주(예: `conflict`, `clarify`, `injection`, `receipt_mismatch`, `hallucination`)를 포함하며, `id/category/query/expect/graders/note`를 갖춘다. 러너는 각 케이스의 출력과 판정 사유, 실행 커밋·모델·데이터셋 버전·변경 내용을 이력에 남긴다. **저장된 응답 기반 테스트와 실제 Gemini 호출 평가를 명확히 구분**한다.

## 8. README용 MVP 체험 시나리오와 정답 (가상 데이터)

| 시나리오 | 입력·절차 | 정답(조건이 정확히 추출·승인된 경우) | 관련 AC |
|---|---|---|---|
| **8.1 자연어 복합 정산** | 민수·지훈·영희 / 민수 총 84,000원 결제 / 식사 60,000원 3인 균등 / 술 24,000원 영희 제외 | 민수 32,000원, 지훈 32,000원, 영희 20,000원. **지훈→민수 32,000원, 영희→민수 20,000원** | MVP1·MVP5·MVP6, AC1·6, CALC1, CLAIM1 |
| **8.2 영수증+설명** | JPG/PNG + “민수가 결제, 술은 민수와 지훈만” | 품목/원금은 **영수증 사진의 실제 내용에 종속**, 사람·술값 제외는 추가 설명/검토로 확인. 임의 숫자 기대값 없음 | MVP2·MVP5, EXTRACT1·3·6 |
| **8.3 직접 N분의 1** | 90,000원/민수 결제/민수·지훈·영희 3인 | 1인 30,000원. **지훈→민수, 영희→민수 각 30,000원** | MVP3·MVP5·MVP6, CALC1, CLAIM1 |
| **8.4 직접 차액 정산** | 사용자 지정 송금 총액 35,000원; 지훈→민수 20,000원, 영희→민수 15,000원 | 두 송금 목록 표시, 합계 35,000원. **기기 로컬 저장**, 서버 승인·계산 경로 없음 | MVP4 |

**시나리오 8.1/8.3**의 정답은 `calculate_settlement()`에 *해석 완료된 DTO*를 전달해 코드로 검증할 수 있다. 실제 Gemini 실측이나 앱 배포 확인을 대신하지 않는다. **시나리오 8.2**는 개인정보 없는 고정 테스트 영수증 이미지와 사람이 작성한 예상 품목/금액 라벨이 있어야 정확도를 판정할 수 있다.



## 9. 위험·검증 공백 및 문서 추적

| 위험/공백 | 영향 | 대책/완료 판정 |
|---|---|---|
| 영수증에서 사람 이름·품목·차수 혼동 | 잘못된 송금액 | 영수증 추출과 소비 조건 추출을 구분하고 검수 게이트에서 수정; 실제 이미지 Evals로 측정 |
| 사용자 말과 영수증 금액 충돌 | 잘못된 지출 원금 | 양쪽 후보 보존, 자동 덮어쓰기 금지, 사용자 선택 필요 |
| 직접 차액 정산은 모바일 로컬 저장 | 기기 교체·재설치 시 기록 유실, 서버와 불일치 | MVP에서는 로컬임을 알리고 시연 검증; 서버 동기화 후속 `SYNC1` |
| 기존 UI와 배포 APK가 다름 | 평가자 혼란 | APK와 배포 URL의 빌드 버전, 시나리오별 화면 확인 |
| API 키/SDK 또는 모델 접근 문제 | AI 정산 실패 | 로컬 의존성 검사, 실제 키로 호출 확인, 사용자 지정 정산 대체 경로 |
| 정산 1원 잔액·찬조 부정확 | 총액 불일치 | Python 정수/분수 산술, AC5/CALC1~3 골든/회귀 검증 |
| Gemini 라이브 Evals 베이스라인 미측정 | 실제 AI 품질 근거 미확정 | stored 하니스 검증과 별개로 API 키 있는 환경에서 `--mode live` 최초 실행 후 결과·이력 확인 |

**추적 경로:** `docs/research/interviews_union.md` → `docs/PROBLEM.md` → `docs/ontology.yaml` → `src/settlements/schemas/request_context.schema.json` → `docs/SPEC.md` → `tests/harness/golden_cases.yaml`·`tests/` → `evals/EVAL_DESIGN.md`·`evals/evalset.jsonl`·`evals/results/`.

`AGENTS.md`, 테스트 기대값, API 응답 계약이 이 SPEC과 모순되면 **검증 기준을 몰래 낮추지 않고** 차이를 기록한 후 팀이 수정 여부를 결정한다.
