# SPEC.md — 모아정산 | 복합 N빵 정산 MVP

> 문서 버전: **3.7**
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

### 3.1  MVP 대상

| ID | 사용자 기능 | 구현 경로/범위 |
| :--- | :--- | :--- |
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
| :--- | :--- | :--- |
| 자연어 파싱·검토 | `src/settlements/parser.py`, 스키마, `tests/test_parser.py`, 기존 골든 테스트 | 코드/결정적 테스트 존재; |
| 영수증 이미지 추출 | `receipt_reader.py`, `receipt_api.py`, `backend/multimodal_router.py`, `tests/test_multimodal_integration.py` | API 경로와 모의 이미지 추출 검증; |
| Python 정산 | `calculator.py`, `allocation_math.py`, 정산·회귀 테스트 | 결정적 계산 구현/검사 존재 |
| 검토·승인·수정 | `workflow_store.py`, `tests/test_web_api.py` | 버전/승인 ID/반복 계산 경로 테스트 존재 |
| 직접 N분의 1 | 모바일 입력 화면 + 서버 `/api/sessions/manual` | 코드 경로 존재; 배포 APK 화면 체험 별도 확인 |
| 직접 차액 정산 | 모바일 `createDiff()`, `diffValid`, `AsyncStorage` | 로컬 경로 존재; |
| Evals | `evals/EVAL_DESIGN.md`, `evals/evalset.jsonl`(35케이스), `evals/run_evals.py`, `evals/results/` | 평가 프레임워크 존재; |

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
