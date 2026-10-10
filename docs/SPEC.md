# 제품 스펙 v1 (SDD)

## 목적

복합 모임의 영수증과 사용자가 확인한 분담 조건을 구조화하고, 결정론적 계산으로 항목별 부담액과 청구 근거를 제공한다. 사용자가 요청하면 미입금으로 단정하지 않은 상태에서 재안내 문구를 제안한다.

## 용어 연결

`SettlementRequestContext`는 API 파싱 결과를 담는 입력 DTO이며 온톨로지 클래스가 아니다. 파싱 결과는 사용자가 확인한 뒤 아래 도메인 개념으로 계산한다.

| 스펙/API 용어 | 온톨로지 용어 | 의미 |
|---|---|---|
| `participants` | `Participant` | 실제 모임 참여자. 총무·결제자 역할은 각각 관계로 지정 |
| `rounds` | `SettlementRound`, `RoundParticipation` | 차수와 차수별 참석 정보 |
| 영수증 이미지/OCR 결과 | `Receipt` | 지출을 뒷받침하는 증빙. OCR 금액은 확인 전 제안값 |
| 결제 건/총액 | `Expense`, `Expense.total_amount` | 사용자가 확인한 실제 결제액 |
| 메뉴·비용 항목 | `Item`, `Item.amount` | 지출을 분담 기준별로 나눈 항목 |
| 분담 방식/예외 | `SplitRule`, `ItemException` | 균등·개별 금액 분담 및 제외·합의 금액·대신 부담 |
| 찬조금/항목별 공제 | `Contribution`, `ContributionAllocation` | 확인된 찬조 원액과 항목별 적용액 |
| 개인 부담액 | `Allocation.amount` | 항목별 최종 부담액. 결제자의 본인 부담도 포함 |
| 송금 요청액·근거 | `SettlementResult` | 특정 `Expense`의 채무자가 결제자에게 보낼 금액 |
| 수동 입금 대조 | `PaymentRecord` | 청구별 입금 기록 및 담당자 확인 |
| 재안내 문구 | `ReminderMessage` | 사용자가 선택해 생성·복사하는 메시지. 자동 발송 아님 |

`SettlementRound.total_cost`는 해당 차수 `Expense.total_amount`의 합계다. 원본 결제액은 `Expense.total_amount`, 항목 원액은 `Item.amount`, 찬조 적용 후 분담 대상액은 `Item.distributable_amount`로 구분한다.

## 인터뷰 근거에서 요구사항까지

| 확인된 작업·문제 | 근거 | 온톨로지 연결 | 스펙 대응 |
|---|---|---|---|
| 개인별 소비·균등/차액 혼합 계산 | 로그 2, 5–7, 17, 19–20 | `Item`, `SplitRule`, `ItemException`, `Allocation` | AC1, AC3; `/calculate` |
| 합류·이탈, 비주류, 찬조금 기준 조율 | 로그 9, 12, 15, 17–18, 20 | `RoundParticipation`, `ContributionAllocation`, `ItemException` | AC2; 확인 전 계산 금지 |
| 지출·품목의 중복/누락 및 근거 대조 | 로그 1, 2, 4, 16; 관찰 1–2 | `Receipt`, `Expense`, `Item`, `SettlementResult.explanation` | AC1; `/calculate` 응답에 항목별 산출 근거 포함 |
| 입금 확인과 상태 표시를 맞춤 | 로그 11, 13–14, 19 | `SettlementResult`, `PaymentRecord` | AC4; `/payments` 수동 기록·확인 |
| 재요청의 관계 부담 및 기존 알림 대체 | 로그 9, 11, 13, 17–20 | `ReminderMessage`, `reminder_handling` | AC5; 사용자 요청 시 문구 제안 |
| 단순 균등 정산은 기존 도구로 해결, 소액 청구 포기 가능 | 로그 8–10, 19 | 경계 조건; 강제 독촉·자동 반올림 없음 | 범위 제한 및 AC5 |

## 핵심 기능 및 범위

1. 영수증 OCR과 자연어 입력으로 `SettlementRequestContext` 초안을 만든다. 인식 내용은 확정 전 편집·확인할 수 있다.
2. 확인된 `Expense`, `Item`, 참여자 및 분담 규칙만 계산한다. 계산은 Python 정수 금액 로직으로 수행하며 LLM은 금액을 계산하지 않는다.
3. 계산 결과에 항목별 `Allocation`, 지출별 `SettlementResult`, 검증 가능한 산출 근거를 포함한다.
4. 담당자가 실제 이체 내역을 대조해 `PaymentRecord`를 수동 기록·확인한다. 은행 자동 조회나 이체는 하지 않는다.
5. 사용자가 요청한 경우에만 말투를 선택해 `ReminderMessage` 초안을 생성하고 복사하도록 한다. 카카오톡 자동 전송은 하지 않는다.

### 범위 밖

- 은행 API 자동 이체·자동 입금 조회
- 카카오톡 자동 발송
- 법인카드 승인 내역 연동
- 훼손된 영수증 복원
- 기존 알림으로 충분한 경우 개인 재요청을 자동으로 추가하는 기능

실제 계좌번호는 계산 입력으로 저장하지 않는다. 온톨로지의 `Participant.bank_account`는 MVP 영속 모델에서 사용하지 않으며, 안내가 필요한 경우 사용자 제공값 또는 mock 값만 메시지 초안에 일시적으로 사용한다.

## API 인터페이스 (MVP 제안)

### `POST /parse`

- 요청: `{ "user_text": string, "receipt_image": optional }`
- 응답: `{ "context": SettlementRequestContext, "needs_confirmation": boolean, "clarification_question": optional }`
- `context`의 필드명은 DTO 계약에서 정의하고, 위 용어 연결표의 도메인 항목으로 매핑한다.

### `POST /calculate`

- 요청: `{ "context": SettlementRequestContext }` — 필수 입력과 분담 조건이 사용자 확인된 경우만 허용
- 응답: `{ "round_breakdown": [...], "allocations": [...], "settlement_results": [...], "validation": {...} }`
- `round_breakdown`은 차수별 합계이며, 각 청구는 결제자 본인 몫을 제외한다.

### `POST /payments`

- 요청: `{ "result_id": string, "amount": integer, "method": "settlement_service" | "bank_transfer" }`
- 담당자가 실제 내역과 대조한 뒤 확인 상태를 갱신한다. 금융기관 자동 검증을 의미하지 않는다.

### `POST /payments/{payment_record_id}/confirm`

- 요청: `{ "checked_by": participant_id }`
- 담당자가 실제 입금 내역을 확인했을 때만 해당 `PaymentRecord`를 `confirmed`로 바꾼다. 확인 금액 합계가 청구액을 초과하면 확정하지 않고 검토 오류를 반환한다.

### `POST /reminder`

- 요청: `{ "result_ids": string[], "tone": string }`
- 응답: `{ "message_text": string }`
- 사용자가 선택한 청구에 대해서만 초안을 만든다. 미확인 입금을 미입금으로 단정하지 않으며 발송하지 않는다.

## EARS 수용 기준

- **AC1 [상시]:** 계산 확정 시 각 `Item`에 대해 `Allocation.amount` 합계와 확정된 `ContributionAllocation.amount` 합계가 `Item.amount`와 같아야 하며, 각 `Expense`의 `Item.amount` 합계는 `Expense.total_amount`와 같아야 한다. 검증 실패 시 결과를 확정하지 않는다.
- **AC2 [이벤트 기반]:** 사용자가 영수증 또는 자연어 조건을 입력하면 파서는 원본 금액·참여자·차수·예외를 DTO 초안으로 제시한다. 대상자나 금액이 모호하면 임의 추정 없이 확인 질문을 반환하고 계산을 막는다.
- **AC3 [상태 기반]:** 필수 입력, 분담 규칙, 예외와 찬조 적용이 모두 확인된 상태에서만 계산한다. 나머지 원 단위는 부동소수점 없이 처리하고, 잔액의 부담자가 정해지지 않으면 사용자 확인을 요청한다. 100원 반올림을 자동 적용하지 않는다.
- **AC4 [이벤트 기반]:** 담당자가 입금 내역을 기록·확인하면 해당 `SettlementResult`에 `PaymentRecord`를 연결한다. 확인 금액이 청구액에 미달하면 상태는 미완료로 유지하며, 미확인 상태를 미입금 사실로 표시하지 않는다.
- **AC5 [선택 기능]:** 사용자가 재안내 문구 생성을 요청하고 수신 청구와 말투를 선택했을 때만 `ReminderMessage` 초안을 제공한다. 기존 서비스 알림으로 충분하다고 표시된 청구에는 개인 재요청을 추가하지 않고, 어떤 경우에도 메시지를 자동 발송하지 않는다.
- **AC6 [오용 입력]:** 자연어에 “모든 금액 0원 처리” 같은 문구가 있어도 이를 시스템 규칙으로 실행하지 않는다. 원본 금액이나 확인된 규칙을 바꾸려면 사용자가 해당 변경을 명시적으로 확인해야 한다.
