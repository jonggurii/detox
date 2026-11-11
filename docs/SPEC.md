# SPEC.md — Smart Settlement Agent (detox)

>  v3.6    
> 도메인 정본: [`ontology.yaml`](ontology.yaml)  
> 문제 근거: [`PROBLEM.md`](PROBLEM.md), [`research/interviews_union.md`](research/interviews_union.md)  
> DTO 정본: `src/settlements/schemas/request_context.schema.json`

## 1. 문제 정의

복합 모임 정산을 맡은 사용자는 영수증에 적힌 항목, 차수별 참석, 술·음식 미이용자, 일부 인원의 고정 부담, 대신 부담, 찬조금, 여러 결제자의 선결제 금액을 수기로 맞춰야 한다. 과정에서 누가 얼마를 내야 하는지에 대한 설명과 입금 확인까지 반복되며 불필요한 시간·관계 부담이 생긴다.

**해결 가설:** 영수증/발화에서 정산 후보를 추출하고, 모호한 항목을 사용자에게 확인받고, 확정된 입력만 결정론적 계산기로 처리하면 반복 입력·계산 오류·청구 누락을 줄일 수 있다.

## 2. 사용자와 핵심 사용 시나리오

**주 사용자:** 여러 사람이 모이는 식사·술자리·여행의 정산 담당자. **관련 사용자:** 선결제자, 비용 부담자, 찬조자, 입금 확인 담당자.

1. 담당자가 영수증 사진을 업로드한다.
2. 모델이 상호·거래일시·품목·금액 후보를 추출한다. 확인 불가 값은 미확정으로 둔다.
3. 담당자가 품목을 검토/수정하고 결제자를 확인한다.
4. “2차에는 지수만 왔고 술값은 도윤을 빼고, 민수는 1만 원만 부담” 같은 자연어 조건을 입력한다.
5. 모델은 `RequestContext` 초안을 제안하고 Python 검증기가 이름·인덱스·원금·예외 충돌을 검토한다.
6. 담당자가 이슈를 해결하고 특정 입력 버전을 **명시적으로 승인**한다.
7. Python 계산기가 항목별 `Allocation`과 결제별 `SettlementResult`를 생성한다.
8. 담당자는 청구 문구 초안을 확인하고 송금 안내, 수동 입금 대조를 처리한다.

## 3. MVP 범위

### 3.1 포함 목표

- 이미지 업로드, 원본 보존, 시각/용량/MIME 유효성 검사 및 영수증 추출.
- 자연어 발화에서 참여자, 차수, 지출, 품목, 분담 규칙, 예외, 찬조를 추출.
- 영수증 인식 결과와 자연어 입력을 **분리 검토**하고, 검토된 필드만 합쳐 확정 DTO 구성.
- `RequestContext`의 JSON Schema 형식 검증 + `review_context` 의미 검증.
- 확인 이슈 표시 및 수정 이력 보존, 버전/해시 기반 명시적 승인.
- 항목별 Python 원 단위 산술, 설명 가능한 계산 근거, 합계 검증.
- 결제별 송금 요청 초안·관계별 안내 초안, 수동 입금 대조.
- SQLite 보존, 동일 요청 멱등성, 회귀/골든 테스트.

### 3.2 비포함

- 자동 은행 이체/잔액 조회/입금 조회, 카카오톡 자동 발송.
- 영수증 훼손 복원, 상점에 대한 사실 조회/자동 정정.
- 음성 실시간 통화 인터페이스(Live API), 대규모 다인 정산의 최적 상계.
- 확인하지 않은 사람/금액/예외의 자동 추정 또는 승인.

### 3.3 현재 구현과 목표의 구분

| 항목 | 관측 근거 | 상태 |
|---|---|---|
| `src/settlements/` 프로젝트 구조 | 사용자 제공 트리 | 경로 확인 |
| `request_context.schema.json` 9필드 계약 | 첨부 파일 | 문서/스키마 확인 |
| 이전 `parser.py`의 Gemini 요청 | 첨부 파일 | 구식 DTO와 모델명을 사용한 코드 확인 |
| 영수증 API·SQLite 검토/버전 처리 | 파일 경로만 전달됨 | **실제 전체 코드 확인 전** |
| `review_context` 골든 테스트 G01~G08 | 사용자 제공 설명 | **실행 결과 미검증** |
| Gemini 3.8 Flash로 영수증·자연어 추출 통합 | 사용자 선택 | **구현 목표** |
| 8개 클래스 온톨로지 정돈 | 이번 문서 | **설계 개정안** |

## 4. 도메인과 입력 계약

### 4.1 핵심 도메인

`Participant`, `SettlementSession`, `Expense`, `Item`, `SplitRule`, `ItemException`, `Allocation`, `SettlementResult`의 **8개 클래스**가 정본이다. 예전의 `SettlementRound`, `RoundParticipation`, `Receipt`, `Contribution`, `ContributionAllocation`, `PaymentRecord`, `ReminderMessage`는 독립 클래스가 아니라 `SettlementSession.rounds`, `Expense.receipt/subsidy`, `SettlementResult.payment_checks/reminder` 하위 구조로 표현한다. 상세 속성은 온톨로지 YAML을 따른다.

### 4.2 RequestContext — 9필드 DTO

```json
{
  "participants": ["민수", "지수"],
  "rounds": [{"round_number": 1, "participant_names": ["민수", "지수"]}],
  "expenses": [{
    "round_number": 1,
    "payer_name": "민수",
    "total_amount": 20000,
    "items": [{"name": "식사", "amount": 20000}]
  }],
  "split_rules": [{
    "expense_index": 0,
    "item_index": 0,
    "method": "equal",
    "participant_names": ["민수", "지수"],
    "remainder_payer_name": "민수"
  }],
  "exceptions": [],
  "contributions": [],
  "tone": "정중하게",
  "relationship": "동기",
  "reminder_handling": "개인 메시지 초안만"
}
```

이 입력은 **가상 예시**다. 실제 속성의 required/optional/null/enum은 별도 스키마가 우선한다. 최상위 필수 필드는 `participants`, `expenses`이며 다른 필드는 생략 가능하다. `expense_index`와 `item_index`는 0-based다. **JSON Schema 통과는 계산 허용을 뜻하지 않는다**. `null`·빈 배열·다른 이름 표기·근거 부족은 `review_context`의 확인 대상일 수 있다.

### 4.3 영수증 추출 DTO(제안)

```json
{
  "merchant_name": null,
  "transaction_date": null,
  "transaction_time": null,
  "total_amount": 20000,
  "items": [{"name": "식사", "quantity": null, "unit_price": null, "total_price": 20000}],
  "uncertain_fields": [],
  "notes": []
}
```

영수증 DTO는 **모델 출력 중간 산출물**이며 `RequestContext` 또는 확정 `Expense`와 동일하지 않다. 원본 이미지·원본 바이트·정규화 이미지·추출물·사용자 수정본의 연결을 보존한다. 실제 기존 `receipt_fields.py`·`receipt_draft.py` 계약을 본 뒤 필드를 확정한다.

## 5. 시스템 동작과 API 명세

### 5.1 처리 경계

```text
영수증 이미지  ─→ Gemini(영수증 추출 프롬프트) ─→ 영수증 후보 JSON ─┐
                                                               ├─→ 스키마/의미 검증 ─→ 검토/수정 ─→ 승인
자연어 발화   ─→ Gemini(정산 파싱 프롬프트) ─→ RequestContext  ──┘                                  │
                                                                                                    ↓
                                                                                        Python 정산 엔진
                                                                                                    ↓
                                                                                 Allocation / SettlementResult
                                                                                                    ↓
                                                                                         송금 안내·수동 대조
```

**같은 모델 사용 ≠ 같은 프롬프트/같은 JSON 구조.** 역할을 분리해 품목·사람·차수의 교차 혼동을 줄인다. 영수증에 결제자 이름이 나타나지 않으면 사용자 발화 또는 확인으로만 결제자를 확정한다.

### 5.2 Gemini 공통 호출부(구현 목표)

- 설정: `GEMINI_API_KEY` (비밀), `GEMINI_MODEL` (기본 계획값 `gemini-3.8-flash`).
- Python SDK: `google-genai`의 단일 클라이언트/모델 설정.
- 영수증: 이미지 바이트 + 전용 프롬프트 + 제한된 구조화 JSON. 이미지 전처리/검사는 지속.
- 발화: 원문 + 전용 프롬프트 + 구조화 JSON. 프로젝트의 Draft 7 스키마 전체를 API가 직접 받아들이지 못할 경우, 모델용 축약 출력 스키마와 **로컬 전체 Draft 7 검증**을 구분한다.
- API 호출 실패, 빈 응답, JSON 파싱 실패, 타입 오류, 필드 누락은 **인식 실패/재검토 상태**로 처리한다. 금액을 0으로 채워 성공 처리하지 않는다.
- 원문에 없는 사람·항목·금액·차수·예외를 창작하지 않으며 추출 근거·불확실성을 유지한다.

### 5.3 API 및 계산 인터페이스

**현재 확인 가능한 로컬 인터페이스(사용자 제공 명세):**

```python
settlements.calculator.calculate_settlement(context: dict) -> CalculationResult
```

위 선언은 제공된 스펙상 인터페이스이며 실제 코드의 정확한 시그니처/반환형은 `calculator.py` 검토 후 확인한다.

**후속 HTTP API 계약:**

| 기능 | 메서드와 경로 | 요청 요지 | 반환/주의 |
|---|---|---|---|
| 영수증 등록/추출 | `POST /api/receipts` (제안) | 이미지 파일 | `receipt_id`, `status=review_required`, 추출 필드 |
| 정산 발화 파싱 | `POST /api/parse` (제안) | `text`, 선택적 `session_id` | DTO 초안, 확인 이슈 |
| 입력 검토 | 기존 `review_context(context)` | `RequestContext` | `ReviewIssue[]` (입력 불변) |
| 검토 수정/승인 | `POST /api/sessions/{sid}/confirm` (제안) | `input_revision`, 수정본/검토 근거 | `confirmation_id`, `context_sha256` |
| 계산 | `POST /api/sessions/{sid}/calculate` (후속 계약) | `{"confirmation_id": "..."}` | 해당 확정 버전의 `CalculationResult`; 멱등 |

**중요:** 경로는 실제 `receipt_api.py`/`app.py`를 받기 전의 **제안**이다. 기존 라우트가 존재하면 이를 우선 보존하고 하위호환을 검토한다.

### 5.4 계산 결과(JSON 직렬화 계약)

```json
{
  "calculation_id": "calc_example_001",
  "input_revision": 1,
  "allocations": [
    {
      "expense_index": 0,
      "item_index": 0,
      "participant_name": "민수",
      "amount": 10000,
      "basis": "원금=20000; 찬조=0; 방식=equal; 대상=민수,지수; 최종=10000"
    },
    {
      "expense_index": 0,
      "item_index": 0,
      "participant_name": "지수",
      "amount": 10000,
      "basis": "원금=20000; 찬조=0; 방식=equal; 대상=민수,지수; 최종=10000"
    }
  ],
  "settlement_results": [
    {
      "expense_index": 0,
      "from_participant": "지수",
      "to_participant": "민수",
      "amount": 10000,
      "basis": "1차 식사 20000원 중 지수 부담분",
      "request_status": "draft",
      "payment_status": "unconfirmed"
    }
  ],
  "participant_totals": {"민수": 10000, "지수": 10000},
  "validation": {
    "item_totals_match": true,
    "expense_totals_match": true,
    "contribution_totals_match": true,
    "request_totals_match": true
  }
}
```

**예시는 수치가 일치하는 단순 사례**다. `participant_totals`는 개인별 소비 부담 합계이지 송금액 합계가 아니다. 결제자 본인 부담은 `allocations`에 나타나더라도 `settlement_results`에는 나타나지 않는다. 입력이 미확정이거나 검증식이 깨지면 계산·청구 확정을 허용하지 않는다.

#### 4대 무결성 판정식

1. **`item_totals_match`**: 각 `Item`별로 `sum(Allocation.amount) + sum(confirmed_item_subsidy.amount) == Item.amount`.
2. **`expense_totals_match`**: 각 `Expense`별로 `sum(Item.amount) == Expense.total_amount`.
3. **`contribution_totals_match`**: 각 확정 찬조에 대해 `sum(uses.amount) == subsidy.amount`; 항목 찬조 총합은 항목 원금을 초과할 수 없음.
4. **`request_totals_match`**: 각 결제별로 `sum(SettlementResult.amount) + payer_own_allocation + confirmed_subsidy == Expense.total_amount` (본 스펙의 찬조 적용/자금 귀속 정책에 따름).

찬조자가 결제자에게 실제 송금해야 하는 흐름을 별도로 모델링해야 한다면 위 4번 식을 그대로 금융 정산 완료 조건으로 확대 해석해서는 안 된다. 현 단계는 **소비 부담 분배/수취 결제자에 대한 청구** 모델이다.

### 5.5 계산 순서

1. **찬조 공제:** 승인된 항목별 찬조금을 원금에서 먼저 뺀다.
2. **제외 처리:** `exclude` 소비자를 분담 대상에서 제외하고 그 항목 소비 몫을 0으로 둔다.
3. **고정 몫/기본 분할:** `fixed_amount`는 해당 인원의 **소비 몫**을 확정한다. 남은 금액은 `equal` 또는 `explicit_amount`대로 배분한다.
4. **대신 부담 이전:** `covered_by_other`는 원래 소비 몫을 대신 부담자에게 이전한다. 총액은 바꾸지 않는다.
5. **원 단위 잔액 귀속:** 정수 원으로 절사한 나머지를 지정 `remainder_payer_name`에게 전액 배정한다. 지정이 없고 나머지가 있다면 계산하지 않는다.

반올림·암묵적 1/N·예외 임의 보정·부동소수점 오차를 금지한다. 동일 항목에 배타적인 조정이 중복되거나 대신 부담 순환이 발생하면 `ReviewIssue`로 확인한다.

### 5.6 상태·저장·승인

- **원본:** 이미지 원본 바이트/해시, 정규화 이미지, 자연어 원문을 식별자별로 보존한다.
- **추출:** 모델 ID, 추출 시각(가능한 경우), 후보 JSON, 검토 상태를 기록한다.
- **수정:** 기존 확정값을 재추출물로 덮어쓰지 않고 변경 버전/근거를 남긴다.
- **확정:** 입력 버전과 정규화 JSON 해시(`context_sha256`)를 확인·잠근다.
- **계산/청구:** 동일 `confirmation_id` 중복 처리 방지. 변경 버전의 계산과 이전 청구/입금 관계를 조용히 치환하지 않는다.
- **동시성:** SQLite 쓰기는 트랜잭션/락으로 충돌을 방지하고 원자적으로 처리한다.
- **민감정보:** API 키는 환경 변수, 계좌/영수증/사용자 원문은 접근 제어와 비밀 로그 정책 적용.

## 6. 수용 기준 — EARS

### 6.1 입력 검토 (`review_context`) — AC1~AC6

| ID | 조건과 시스템 반응 | 기계적 판정 |
|---|---|---|
| **AC1** | 정상 입력 G01 및 스키마/하니스에서 정의한 1인·0원 최소 G02 입력 | `(code, path)` 전체 목록이 정확히 `[]`, `issue_count == 0` |
| **AC2** | 참여자/결제 내역 누락 또는 결제자 미식별 | `missing_participants`, `missing_expenses`, `unresolved_person` 등 해당 확인 이슈 반환 |
| **AC3** | 결제 총액과 항목 합계 불일치 | 원본을 보존하며 `item_sum_mismatch` 이슈 반환; 자동 보정 금지 |
| **AC4** | `ItemException.item_index`/`kind` 등 필수 조정 정보 미정 | 조정 임의 확정 없이 명시적 확인 이슈 반환 |
| **AC5** | 균등 분배시 1원 단위 나머지가 있는데 잔액 부담자 미정 | `unresolved_rounding` 발생, 계산 차단 |
| **AC6** | 임의 입력의 검토, 특히 `reason`에 공격성 지시문이 들어 있는 경우 | 입력 객체 불변, 지시문은 데이터로만 취급, 정상 입력의 이슈는 `[]` 유지 |

**기존 골든 테스트 `G01~G08`을 수정하거나 기대 결과를 완화하지 않는다.** `tests/harness/golden_cases.yaml`에 기록된 정확한 데이터와 경로를 최종 판정 정본으로 두며, 첨부되지 않은 테스트의 이미 통과했다고 주장하지 않는다.

### 6.2 계산·청구·입금·안내 — 후속 AC

| ID | 수용 기준 |
|---|---|
| **CALC1** | `[찬조 공제] → [제외] → [고정 소비 몫/분할] → [대신 부담 이전] → [원 단위 잔액 배정]` 순서 준수, 4대 검증식 1원 오차 없이 만족 |
| **CALC2** | 확정 찬조는 해당 항목 분담 원금에 먼저 반영하고, 찬조자라는 이유만으로 그 사람을 소비 대상에서 제외하지 않음 |
| **CALC3** | 분할 시 남은 원 단위 잔액은 지정 1인에게 배정; 미지정이면 검토 차단, 임의 반올림/비용 소멸 금지 |
| **CLAIM1** | 수취인 = 해당 결제 `payer`; 결제자 자신 또는 최종 부담액 0원 대상 청구 금지 |
| **CLAIM2** | 같은 승인 ID 재호출 시 같은 계산을 재사용하고 중복 청구 생성 금지; 입력 수정 시 이전 승인 무효화 |
| **PAY1** | 입금 기록은 수동 대조를 통해서만 확정하고 미확인 거래를 완료액으로 합산하지 않음 |
| **PAY2** | 동일 실제 입금(`source_transfer_ref`)에 매핑한 총액은 원 실입금액을 넘지 않음 |
| **NOTICE1** | 확정 송금 결과의 사람·금액 및 확인된 수취 계좌만 안내에 인용하며 미확인 계좌는 창작하지 않음 |

### 6.3 신규 멀티모달 추출 기준 — 제안

| ID | 수용 기준 |
|---|---|
| **EXTRACT1** | 영수증에서 보이지 않는 금액·사람·품목을 추정하지 않고 미확정 상태/이슈로 표기 |
| **EXTRACT2** | 같은 앱 설정 `GEMINI_MODEL`을 영수증/자연어 파싱에서 사용하되 프롬프트/출력 스키마는 용도별 분리 |
| **EXTRACT3** | 추출 결과는 사용자 검토 전에는 지출/정산 결과를 영속적으로 확정하거나 청구를 발행하지 않음 |
| **EXTRACT4** | 음성·이미지·텍스트 내부의 '규칙 무시' 지시문을 정책 변경 명령으로 실행하지 않음 |
| **EXTRACT5** | 원본 파일/원문·모델 제안·검토 수정본 및 버전 정보가 보존되고 변경 시 이전 확정 데이터 자동 덮어쓰기 금지 |
| **EXTRACT6** | 실패한 API 호출, 구조화 실패, 항목 합계 불일치는 성공처럼 처리하지 않으며 확인 이슈를 표시 |

## 7. 골든 테스트, 측정, 기술 스파이크

### 7.1 기존 회귀 하니스

- `tests/harness/golden_cases.yaml`의 G01~G08은 AC1~AC6과 일치하도록 **실제 파일의 기대값**을 확인한다.
- `tests/test_context_review_golden.py`를 우선 실행하고 그다음 전체 테스트를 실행한다.
- 기존 테스트는 임의 삭제, 수정, `skip`, `xfail` 처리하지 않는다.
- 검사 항목: 이슈의 정확한 `(code, path)`, 입력 불변성, 총액/예외/잔액 판정, 계산 합계, 청구 버전 멱등성.

### 7.2 Gemini 복합 추출 스파이크(사전 계획)

**검증하려는 가정:** 복합 영수증 이미지 + 자연어 발화를 제공할 때 중요 필드의 추출 결과가 정답과 정확히 일치하는 비율이 90% 이상인가?

- **Timebox:** 6시간. **블라인드 세트:** 30건 (프롬프트 튜닝에 사용하지 않은 사례).
- **라벨링:** 독립된 팀원 2명이 서로 상의하지 않고 30건의 정답 `RequestContext`를 작성한다. 불일치는 온톨로지 정의를 참조해 합의한다.
- **정답 불가능:** 발화가 지나치게 모호하여 합의할 수 없으면 사례를 교체하고 30건을 유지하되, 교체 건수와 이유를 보고한다.
- **완벽 일치:** `participants`, `expenses[].items`, `split_rules[].participant_names`, `exceptions` 핵심 필드가 **모두** 정답과 같아야 해당 사례를 1건 성공으로 센다. 사람 누락·품목 총액 오류·제외자 오지정은 실패다.
- **사전 합격선:** **27/30건 이상** (90.0% 이상).
- **기록:** 테스트 날짜, 모델의 정확한 ID, 입력 이미지/발화 익명화 식별자, 정답/예측 JSON, 불일치 유형, 결과 로그.

제공된 문안에는 **26/30건(86.7%)이라는 실행 결과**가 기재되어 있지만, 원본 평가 데이터나 실행 로그가 첨부되지 않았으므로 본 스펙에서는 **주장된 과거 결과(검증 전)**로 구분한다. 이 수치가 실제 결과로 확인되면 합격선 미달로 판정하고, **영수증 화면 검수 → 별도 자연어 조건 입력 → 근거 연결/검토**의 단계 분리안을 채택한다. 단계 분리 자체는 데이터 검증 여부와 무관하게 안전한 기본 설계로 사용한다.

## 8. 저장소 경로와 운영

```text
detox-main/
├─ AGENTS.md
├─ docs/
│  ├─ ontology.yaml
│  ├─ ontology.md
│  ├─ SPEC.md
│  ├─ PROBLEM.md
│  └─ research/interviews_union.md
├─ src/settlements/
│  ├─ parser.py
│  ├─ receipt_api.py
│  ├─ receipt_ocr.py
│  ├─ receipt_fields.py
│  ├─ receipt_draft.py
│  ├─ calculator.py
│  ├─ allocation_math.py
│  ├─ workflow.py
│  ├─ workflow_store.py
│  ├─ prompts/parse_query.md
│  └─ schemas/request_context.schema.json
└─ tests/
   ├─ test_context_review_golden.py
   └─ harness/golden_cases.yaml
```

**추가/교체 예정:** `src/settlements/gemini_client.py`, `src/settlements/receipt_reader.py`, `src/settlements/prompts/receipt_extraction.md`. 기존 `receipt_ocr.py`는 참조 관계와 테스트 확인 후 교체/호환 래퍼 유지 여부를 결정한다. 프로젝트 트리에서 `app.py`, `requirements-web.txt`, `requirements-ocr.txt`가 `tests/` 아래에 표시되어 있어 현재 파일의 실제 위치를 확인한 후 실행 명령을 확정한다.

PowerShell **저장소 루트에서** 실행하는 표준 검증 명령(의존성/경로가 준비된 후):

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_context_review_golden.py -v
python -m pytest tests -v
```

실행 서버 진입점은 `app.py`의 실제 위치에 따라 `uvicorn app:app` 또는 `uvicorn tests.app:app` 등으로 달라지므로 코드 확인 전 고정하지 않는다. `.env`의 실제 값 및 영수증/계좌 데이터는 커밋하지 않는다.

## 9. 위험과 의사결정 원칙

| 위험 | 영향 | 완화 |
|---|---|---|
| 이미지에서 사람 이름과 품목/차수 혼동 | 잘못된 부담자 청구 | 영수증/발화 분리 추출, 근거·미확정 표시, 사용자 검토 |
| JSON Schema는 통과하지만 의미상 잘못된 데이터 | 조용한 오계산 | `review_context`·골든 테스트·승인 게이트 |
| Gemini API의 출력 스키마 지원 차이 | 런타임 구조화 실패 | 모델용 지원 스키마와 로컬 Draft 7 검증 분리 |
| 1원 잔액 또는 찬조 배정 누락 | 합계 불일치 | Python 정수 연산, CALC1~3 및 4대 합계식 |
| 재추출/재계산으로 이전 승인·청구 덮어쓰기 | 중복 청구/입금 추적 오류 | 버전/해시/멱등 키, 트랜잭션 |
| 테스트 결과의 근거 부족 | 제품 완성도 오판 | 실패 로그·원본 테스트 데이터·실행 명령 기록 |

## 10. 추적 관계

`docs/research/interviews_union.md` → `docs/PROBLEM.md` → `docs/ontology.yaml` (개념 정본) → `src/settlements/schemas/request_context.schema.json` (입력 계약) → `docs/SPEC.md` (수용 기준) → `tests/harness/golden_cases.yaml` + `tests/test_context_review_golden.py` (실행 검증).

실제 구현과 문서가 충돌하면 **기존 테스트를 약화시키지 말고** DTO 계약·온톨로지·수용 기준의 충돌 지점을 명시하여 수정안을 검토한다.
