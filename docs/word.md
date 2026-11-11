# word.md — Smart Settlement Agent (detox) 도메인 용어집

> **문서 버전: v3.6  
 
> **문서 상태:** 설계 용어집. 실제 코드 구현·테스트 성공을 증명하지 않음.  
> **도메인 의미 정본:** [`ontology.yaml`](ontology.yaml)  
> **도메인 설명:** [`ontology.md`](ontology.md)  
> **기능 및 수용 기준:** [`SPEC.md`](SPEC.md)  
> **개발 지침:** [`../AGENTS.md`](../AGENTS.md)  
> **실행 입력 스키마 정본:** `src/settlements/schemas/request_context.schema.json`

## 1. 문서 목적과 사용 규칙

`word.md`는 팀원, 발표자, 설계 문서 작성자 및 AI 코딩 에이전트가 동일한 용어를 같은 의미로 사용하도록 정리한 **공유 용어집(Ubiquitous Language)**이다. 이 문서는 별도의 데이터 모델이 아니며, 구현 중 실제 필드의 허용 값·필수 여부가 필요한 경우에는 입력 JSON Schema를, 핵심 업무 개념과 관계가 필요한 경우에는 `ontology.yaml`을 우선한다.

- **정산을 계산한다**는 것은 검토·확정된 입력을 Python 산술 엔진에 넣어 개인별 비용 부담과 송금 요청을 산출한다는 뜻이다.
- **추출한다**는 것은 이미지·발화에서 관찰 또는 명시된 정보의 후보를 구조화한다는 뜻이며, 해당 후보를 사실로 확정한다는 뜻이 아니다.
- **검토한다**는 것은 빠진 정보, 충돌, 계산 불가 조건을 찾는다는 뜻이며, 임의의 값을 채워 넣는 행위가 아니다.
- **승인한다**는 것은 사용자가 특정 `input_revision` 및 `context_sha256`에 연결된 입력을 명시적으로 확정한다는 뜻이다.
- 본 문서의 `Participant` 등 **8개는 도메인 클래스**이고, `RequestContext`, `ReviewIssue`, 영수증 추출 JSON은 **입력·검증·전달 구조**다.
- 사용자 발화의 사람·금액·차수·예외는 근거 없이 추론하거나 자동 보정하지 않는다.

## 2. 서비스 및 업무 용어

| 권장 용어 | 영문/코드 표현 | 정의 | 혼동 방지 |
|---|---|---|---|
| 스마트 정산 | Smart Settlement | 영수증과 자연어 조건을 받아 다자간 비용 분담을 지원하는 시스템 | 은행 자동 송금을 뜻하지 않음 |
| N빵 | Equal Split | 특정 항목에 대해 정해진 부담 대상자에게 같은 기본 금액을 배분하는 방식 | 모든 참석자에게 무조건 1/N이 아님 |
| 복합 정산 | Complex Settlement | 차수, 결제자, 품목, 분담 대상, 찬조, 예외 등이 섞인 정산 | 하나의 총액만 나누는 계산과 구별 |
| 차수 | Round | 모임의 1차·2차 등 시간·장소상 구분 단위 | 참석 차수와 소비 항목은 서로 다름 |
| 참석 정보 | Attendance | 해당 차수에 참여하거나 중간에 합류·이탈한 사실과 메모 | 참석 여부만으로 품목 부담 여부를 확정할 수 없음 |
| 결제/선결제 | Payment by Payer | 한 명이 지출 금액을 먼저 낸 사실 | 최종 소비 부담과 다름 |
| 비용 항목 | Item | 서로 다른 분담 규칙을 적용할 수 있는 최소 비용 단위 | 영수증의 인쇄 줄과 항상 일대일이 아님 |
| 정산 담당자 | Settlement Operator | 원본·조건을 검토하고 승인·입금 대조하는 사람 | 반드시 결제자일 필요 없음 |
| 소비 부담액 | Allocation Amount | 개인이 최종적으로 부담하는 항목별 비용 | 실제 송금해야 하는 금액과 구별 |
| 송금 요청액 | Settlement Request Amount | 선결제자에게 다른 사람이 보내야 하는 금액 | 계산된 소비 몫과 항상 같지 않음 |
| 송금 안내 초안 | Reminder Draft | 확정 금액·참여자·확인 계좌로 구성한 안내 문구 | 실제 발송 완료가 아님 |
| 수동 입금 대조 | Manual Payment Reconciliation | 운영자가 실입금 증빙과 송금 요청을 확인하는 절차 | 은행 API를 통한 자동 확인 아님 |

## 3. 핵심 도메인 클래스 — 8개

| 클래스 | 권장 한국어 | 주요 속성 | 업무 역할 | 기존 개념과의 관계 |
|---|---|---|---|---|
| `Participant` | 참여자 | `participant_id`, `name`, `bank_account`(선택) | 사람 식별 및 결제·부담·찬조 역할 구분 | 동일 이름이더라도 자동 동일인 취급 금지 |
| `SettlementSession` | 정산 세션 | `session_id`, `status`, `rounds`, `input_revision` | 참여자·차수·지출과 확인 버전 관리 | `SettlementRound`, `RoundParticipation`의 독립 클래스 제거 |
| `Expense` | 결제 내역 | `expense_id`, `total_amount`, `payer`, `items`, `receipt`, `subsidy` | 결제자 1명의 한 건 지출과 증빙·찬조 묶음 | `Receipt`, `Contribution`, `ContributionAllocation` 흡수 |
| `Item` | 비용 항목 | `item_id`, `expense_id`, `name`, `amount` | 품목별 분담/제외를 적용할 계산 단위 | 한 영수증의 여러 줄을 합치거나 분리 가능 |
| `SplitRule` | 분담 규칙 | `rule_id`, `item_id`, `method`, `participant_ids`, `remainder_payer` | 기본 부담 대상과 금액 배분 방식 | `ItemException`과 별도 |
| `ItemException` | 개인별 부담 조정 | `adjustment_id`, `item_id`, `participant`, `kind` | 특정 사람·항목의 제외/고정액/대신 부담 | 참석 기록만으로 생성 금지 |
| `Allocation` | 항목별 개인 부담액 | `allocation_id`, `item_id`, `participant`, `amount`, `basis` | Python 계산 결과로 최종 소비 몫 표시 | LLM 추출값이 아닌 파생 결과 |
| `SettlementResult` | 송금 요청 내역 | `result_id`, `expense_id`, `sender`, `receiver`, `amount` | 실제 결제자 기준 송금 요청과 대조·안내 | `PaymentRecord`, `ReminderMessage` 흡수 |

### 3.1 도메인 클래스 간 핵심 관계

- 하나의 `SettlementSession`은 여러 `Participant` 및 `Expense`를 포함할 수 있다.
- 하나의 `Expense`는 **한 명의 `payer`**와 여러 `Item`을 가질 수 있다.
- 하나의 확정 `Item`에는 원칙적으로 하나의 유효 `SplitRule`이 적용되며, 여러 `ItemException`이 추가될 수 있다.
- `Allocation`은 **항목 × 참여자 × 계산 버전** 수준의 최종 부담액이다.
- `SettlementResult`는 **지출 건별**로 수취인인 `Expense.payer`와 송금자를 연결한다.

### 3.2 흡수된 이전 클래스 — 삭제가 아닌 구조 이동

| 이전 클래스 | v3.6 위치 | 유지해야 하는 정보 |
|---|---|---|
| `SettlementRound` | `SettlementSession.rounds[]` | 차수 번호, 참석 명단/인원 메모 |
| `RoundParticipation` | `SettlementSession.rounds[].attendance[]` | 합류·이탈 등 개별 참석 메모 |
| `Receipt` | `Expense.receipt` | 원본 이미지, 전처리 이미지, 인식 결과 및 수정 버전 |
| `Contribution` | `Expense.subsidy[]` | 찬조자, 총액, 확인 상태 |
| `ContributionAllocation` | `Expense.subsidy[].uses[]` | 찬조금의 항목별 적용액 |
| `PaymentRecord` | `SettlementResult.payment_checks[]` | 원거래 식별자, 확인 금액, 대조 여부 |
| `ReminderMessage` | `SettlementResult.reminder[]` | 말투, 관계, 초안, 발송 상태 |

이 구조 이동은 **온톨로지 설계 변경**을 뜻한다. 기존 Python 모듈이나 SQLite 테이블을 이미 변경했다는 의미는 아니다.

## 4. 분담 방식·예외·찬조 용어

### 4.1 기본 분담 규칙 (`SplitRule`)

| 코드 값 | 한국어 | 정확한 의미 | 주의 사항 |
|---|---|---|---|
| `equal` | 균등 분담 | 해당 항목의 남은 분담 가능 금액을 **확정된 대상자**에게 동일하게 분할 | 대상자 수를 전체 참석자 수로 자동 결정하지 않음 |
| `explicit_amount` | 명시 금액 분담 | 특정 사람의 몫을 사용자가 지정한 금액으로 분담 | 명시되지 않은 사람/남는 금액의 처리 정책은 검토 필요 |
| `remainder_payer_name` | 잔액 부담자 | 원 단위 분할 시 남는 잔액을 최종 부담하도록 확인된 사람 | 사람이 미정인데 잔액이 발생하면 `unresolved_rounding` |
| `participant_names` | 기본 분담 대상 | 예외를 적용하기 전 항목 비용을 나눌 사람 명단 | 차수 참석자 전원을 자동 복사하면 안 됨 |

### 4.2 항목별 개인 부담 조정 (`ItemException`)

| `kind` | 한국어 | 계산상 의미 | 잘못된 해석 |
|---|---|---|---|
| `exclude` | 부담 제외 | 해당 **항목**에서 해당 사람의 소비 부담을 0원으로 처리하고 기본 분담 후보에서 제외 | 모임 전체 비용이나 다른 차수에서도 자동 제외 |
| `fixed_amount` | 합의 부담액 고정 | 해당 사람의 최종 소비 몫을 지정 금액으로 확정 | 기본 몫에 더하거나 뺄 **차액**으로 해석 |
| `covered_by_other` | 대신 부담 | 한 사람의 원 소비 몫을 지정한 다른 사람에게 이전 | 두 사람에게 똑같은 몫을 중복 청구 |

`fixed_amount=10000`은 **최종 소비 몫이 10,000원**이라는 뜻이다. `+10,000원`의 추가 부담이나 `-10,000원`의 할인과 다르다. `covered_by_other`의 대신 부담자(`covered_by_name`)는 꼭 그 영수증의 선결제자일 필요가 없다.

### 4.3 찬조금 (`subsidy`, `contributions`)

- **찬조자 (`contributor_name`)**: 정산 원금을 지원하는 사람. 자신이 비용을 소비했는지와 별개다.
- **찬조 총액 (`amount`)**: 지원하기로 확정된 총액. 단순 약속인지 실제 수령했는지는 확인해야 한다.
- **찬조 적용액 (`uses[].amount`)**: 특정 비용 항목에 반영되는 금액. 전체 찬조액과 각 적용액 합계가 같아야 한다.
- **찬조 우선 공제**: Python 계산 시 확정 찬조 적용액을 항목 원금에서 우선 공제한 뒤 남은 금액을 나눈다.
- **찬조 ≠ 제외**: 찬조금을 낸 사람을 기본 분담 대상에서 자동 제외하지 않는다.
- **찬조 적용 ≠ 은행 이체 완료**: 비용 분담상 차감과 실제 자금 지급/수령은 구분한다.

## 5. 입력·추출·검토·승인 용어

| 용어 | 코드/구조 | 정의 | 처리 원칙 |
|---|---|---|---|
| 영수증 원본 | `original.bin`, 원본 이미지 | 업로드 당시 파일 바이트 | 모델 재호출과 별개로 보존; 민감정보 보호 |
| 정규화 이미지 | `image.png`, `prepare_image()` 등 | 인식할 수 있도록 형식·회전 등을 점검한 이미지 | OCR 엔진 제거 여부와 무관하게 검증 유지 |
| 영수증 인식 | Receipt Extraction | 보이는 상호·일시·품목·금액을 이미지에서 읽어 구조화 | 결제자 이름·차수·제외자를 임의 창작 금지 |
| 자연어 정산 파싱 | Natural-language Parsing | 사용자 발화의 사람·결제·분담·예외 표현을 DTO로 추출 | 금액의 최종 산술 계산 금지 |
| 입력 DTO | `RequestContext` | 검토 전 정산 후보의 9필드 JSON 구조 | 도메인 엔티티가 아님 |
| 스키마 검증 | JSON Schema Validation | 타입·허용값·필수 필드·구조 검사 | 업무적 사실 확인과 별개 |
| 의미 검토 | `review_context(context)` | 빠진 사람·항목·금액 충돌 및 계산 차단 조건 검사 | 입력 객체를 수정하지 않음 |
| 확인 이슈 | `ReviewIssue` | 사용자 확인이 필요한 코드·경로·메시지 단위 | 이슈 부재가 모델 정답률 100%를 뜻하지 않음 |
| 사용자 승인 | Confirmation | 사람이 특정 입력 버전을 확정하는 행위 | 승인 이전 계산/청구 확정 금지 |
| 입력 리비전 | `input_revision` | 검토/수정에 따른 입력의 버전 | 바뀌면 이전 승인 효력 재검토 |
| 입력 해시 | `context_sha256` | 정규화된 확정 입력을 식별하기 위한 해시 | 원본 영수증 파일 해시와 구별 |
| 승인 식별자 | `confirmation_id` | 확정 입력 버전에 연결된 승인 ID | 같은 승인 재계산은 중복 청구 금지 |
| 모델 추출물 | Extraction Candidate | Gemini가 구조화한 잠정 값 | 검토 완료 데이터 덮어쓰기 금지 |

### 5.1 `RequestContext` — 9개 최상위 필드

| 필드 | 의미 | 도메인 매핑 | 주의 사항 |
|---|---|---|---|
| `participants` | 발화에 명시된 이름·호칭 목록 | `Participant` | 비어 있거나 불완전할 수 있음; 필수 키 |
| `rounds` | 차수 및 참석 메모 | `SettlementSession.rounds` | 참석은 소비 부담과 다름 |
| `expenses` | 결제자·총액·세부 항목 후보 | `Expense`, `Item` | 비어 있거나 미확정일 수 있음; 필수 키 |
| `split_rules` | 항목별 기본 분담 방식과 대상 | `SplitRule` | 불명확하면 `null`/확인 이슈 |
| `exceptions` | 개인별 제외/고정액/대신 부담 | `ItemException` | 대상 품목 및 조정 방식 확인 |
| `contributions` | 찬조 총액과 항목별 적용 | `Expense.subsidy[]` | 적용처·금액 임의 추론 금지 |
| `tone` | 송금 안내 말투 | `SettlementResult.reminder.tone` | 관계만 보고 자동 추론하지 않음 |
| `relationship` | 안내 대상자 사이 관계 | `SettlementResult.reminder.relationship` | 명시되지 않으면 생략 |
| `reminder_handling` | 미납 재안내 처리 방식 | `SettlementResult.reminder.handling` | 허용 enum은 아래 기준 준수 |

**스키마 주의:** 필수 **최상위 키**는 `participants`, `expenses` 두 개다. 키가 존재하더라도 배열이 비어 있으면 실제 계산에 필요한 정보가 충분하지 않을 수 있다. 단, G02처럼 골든 테스트에서 허용한 1인·0원 최소 조건을 임의로 거부하지 않는다.

### 5.2 인덱스·ID·이름 구분

- `expense_index`: `RequestContext.expenses` 배열 내 **0부터 시작하는 인덱스**. 영구 저장 ID인 `expense_id`와 다르다.
- `item_index`: 해당 `expenses[i].items` 내 **0부터 시작하는 인덱스**. 영구 저장 ID인 `item_id`와 다르다.
- `participant_name`: 입력 발화의 이름·호칭으로, 도메인 식별자인 `participant_id`와 다르다. 동명이인은 확인 필요.
- `payer_name`: 발화/입력 DTO에서 사용한 결제자 이름. 도메인 `Expense.payer` 참조로 연결할 때 유효 인물인지 검증한다.
- `covered_by_name`: `covered_by_other` 예외에서 대신 부담자로 지정된 사람의 입력 이름.
- `null`: 모름/미확정. **0원, 전체 참여, 승인, 빈 문자열**의 동의어가 아니다.

### 5.3 `reminder_handling` 스키마 허용값

| 값 | 의미 |
|---|---|
| `undecided` | 처리 방식이 명시적으로 미정임 |
| `personal_follow_up` | 담당자가 개인적으로 재안내 |
| `external_service_only` | 기존 서비스의 알림만 사용 |

발화에 처리 방식이 없으면 필드를 **생략**한다. `"개인 메시지 초안만"`과 같은 설명용 한국어 문자열은 스키마 enum을 만족하지 않으므로 실제 DTO에 그대로 쓰지 않는다.

## 6. 금액·정산 결과·무결성 용어

| 용어 | 필드/검증 | 정의 |
|---|---|---|
| 항목 원금 | `Item.amount` | 항목 전체 결제 금액(원) |
| 지출 총액 | `Expense.total_amount` | 결제자가 실제 선결제한 한 건 금액(원) |
| 최종 소비 몫 | `Allocation.amount` | 찬조·제외·고정액·대신 부담·잔액 배정 후 개인에게 귀속된 항목 부담액(원) |
| 계산 근거 | `Allocation.basis` | 금액 생성 규칙을 추적할 수 있는 설명 |
| 원 단위 잔액 | Remainder | 정수 원 배분 후 남는 비용. 지정 부담자에게 전액 귀속 |
| 결제자 본인 부담액 | Payer Own Allocation | 결제자가 소비 몫으로 부담하는 총액. 자신에게 송금하지 않음 |
| 송금자 | `SettlementResult.sender` | 결제자에게 돈을 보내야 하는 사람 |
| 수취인 | `SettlementResult.receiver` | 해당 지출의 실제 `payer` |
| 청구 상태 | `request_status` | 요청 초안/요청됨/취소 등 청구의 진행 단계 |
| 입금 상태 | `payment_status` | 미확인/부분 확인/확인 등 수동 대조 상태 |
| 원거래 식별자 | `source_transfer_ref` | 실제 이체 거래 한 건의 식별 값 |
| 매핑 금액 | `mapped_amount` | 실거래 금액 중 특정 요청과 연결해 확인한 금액 |

### 6.1 4대 계산 무결성 판정식

1. **`item_totals_match`**: 항목별 `Σ Allocation.amount + Σ 확정 찬조 적용액 = Item.amount`.
2. **`expense_totals_match`**: 지출별 `Σ Item.amount = Expense.total_amount`.
3. **`contribution_totals_match`**: 찬조별 `Σ uses[].amount = 찬조 총액`; 항목별 찬조금은 원금을 초과할 수 없음.
4. **`request_totals_match`**: 지출별 `Σ 비결제자 송금 요청액 + 결제자 본인 소비 부담액 + 확정 찬조 적용액 = Expense.total_amount`.

4번은 현 SPEC의 **찬조가 분담 원금을 줄이고 수취 결제자에게 그만큼 충당된다는 정산 모델**을 전제로 한다. 은행 입금 완료를 직접 증명하는 식은 아니다.

### 6.2 계산 순서: 반드시 고정

**[확정 찬조 우선 공제] → [제외자 처리] → [고정 소비 몫 배정 / 나머지 기본 분할] → [대신 부담 이전] → [원 단위 절사·잔액 귀속]**

이 순서는 `SPEC CALC1~3`의 설계 규칙이다. 계산은 **Python 정수 산술**로 수행하고, Gemini에게 산술 결과를 확정하도록 맡기지 않는다.

## 7. 상태 및 코드 값 표준

### 7.1 정산 세션 `status`

| 값 | 의미 |
|---|---|
| `draft` | 아직 입력을 작성하는 단계 |
| `review_required` | 확인/수정이 필요한 상태 |
| `confirmed` | 입력 승인 완료 상태 |
| `calculated` | 승인 입력을 계산한 상태 |
| `requested` | 송금 요청이 생성/전달된 상태 |
| `completed` | 정산 업무가 완료 처리된 상태 |
| `cancelled` | 취소 처리된 상태 |

### 7.2 송금 요청·입금 상태

- `request_status`: `draft`, `requested`, `cancelled`.
- `payment_status`: `unconfirmed`, `partially_confirmed`, `confirmed`.
- 요청이 생성되었더라도 실제 이체가 확인되었다는 뜻은 아니다.
- 입금이 미확인인 것은 **실제로 입금하지 않았다는 증거가 아니다**.

### 7.3 주요 검토 이슈 코드

| 코드 | 검토 의미 | 수용 기준 |
|---|---|---|
| `missing_participants` | 정산에 필요한 참여자 정보 부족 | AC2 |
| `missing_expenses` | 결제 내역 정보 부족 | AC2 |
| `unresolved_person` | 결제자 또는 대상 인물 식별 불가 | AC2 |
| `item_sum_mismatch` | 항목 합계와 결제 총액이 다름 | AC3 |
| 조정 관련 이슈 | 항목/예외 방식·대상 불명확 | AC4; **정확한 코드명은 테스트 정본 준수** |
| `unresolved_rounding` | 원 단위 잔액 부담자 미정 | AC5 |

**AC1:** 정상 골든 케이스 G01/G02에서는 `(code, path)` 전체 목록이 정확히 `[]`이고 `issue_count == 0`이어야 한다. **AC6:** 검토 함수는 입력을 바꾸지 않으며, `reason` 등에 삽입된 공격 문장을 실행하지 않는다. 골든 테스트 G01~G08의 실제 기대 경로와 메시지는 `tests/harness/golden_cases.yaml`이 정본이다.

## 8. AI 모델·파일·모듈 용어

| 용어/파일 | 역할 | 주의 사항 |
|---|---|---|
| Gemini Flash | 영수증 이미지/자연어 후보 추출 모델 | 모델 설정 통합은 **설계 방향**이며 실제 연동 완료 아님 |
| `GEMINI_MODEL` | 두 추출 경로에서 공통 사용하려는 모델 환경변수 | 계획값 `gemini-3.8-flash`는 실제 API 이용 가능 여부 검증 필요 |
| `GEMINI_API_KEY` | 외부 모델 호출 인증 비밀값 | `.env`/환경변수에서만 로드, 커밋·로그 금지 |
| `gemini_client.py` | 공통 Gemini 호출부(추가 예정) | 실제 파일은 아직 확인되지 않음 |
| `parser.py` | 자연어 → `RequestContext` 추출 및 입력 검토 연계 | `review_context`와 골든 테스트 호환성 유지 |
| `receipt_ocr.py` | 기존 영수증 인식 경로 | Gemini 대체 전 기존 호출 인터페이스 확인 필요 |
| `receipt_reader.py` | Gemini 이미지 인식 어댑터(추가 예정) | 모델 인식은 검토 전 후보일 뿐 |
| `receipt_fields.py` | 영수증 필드 검증/정규화 | 보이지 않는 금액 자동 생성 금지 |
| `receipt_draft.py` | 영수증에서 정산 초안을 구성하는 처리 | 모델 후보와 확정 입력을 분리 |
| `receipt_api.py` | 이미지 업로드 및 검토 API | 기존 API 계약·원본 저장·오류 처리 보존 |
| `calculator.py` / `allocation_math.py` | Python 정산 계산 | 단위 원 정수 계산·4대 검증식 담당 |
| `workflow.py` / `workflow_store.py` | 검토/승인/버전·SQLite 상태 | 원자적 저장·멱등·수정 버전 보호 |
| `request_context.schema.json` | 9필드 DTO의 타입·enum·null 계약 | 온톨로지 YAML과는 역할이 다름 |
| `tests/harness/golden_cases.yaml` | 검토 함수 골든 사례와 기대 결과 | 성공시키려고 테스트 기대값을 임의 변경 금지 |

### 8.1 권장 처리 흐름

```text
원본 영수증 이미지 ─┐
                 ├─ Gemini Flash (입력별 프롬프트/출력 구조 분리)
자연어 정산 발화 ───┘
                   ↓
          잠정 추출 데이터(JSON)
                   ↓
       JSON Schema + 의미 검토
                   ↓
         사용자 수정 및 명시 승인
                   ↓
       Python 결정론적 정산 계산
                   ↓
       Allocation / SettlementResult
                   ↓
        송금 안내 초안 / 수동 입금 대조
```

동일한 Gemini 모델을 사용하더라도 **영수증 추출과 자연어 파싱에 같은 프롬프트 또는 같은 출력 스키마를 강제하지 않는다**. 원본 영수증 이미지나 사용자 승인 완료 값은 재추출 과정에서 덮어쓰지 않는다.

## 9. 혼동 방지 사례 (가상 예시)

### 사례 A: 차수 참석과 술값 제외

- 발화: “2차에는 민수, 지수, 도윤이 있었는데 도윤은 술을 안 마셨어.”
- **확실한 사실:** 2차 참석에 세 사람이 언급됨; 도윤이 술을 마시지 않았다는 서술이 존재함.
- **확인 필요:** 술값 부담에서 도윤을 **제외하자는 명시적 정산 합의**인지 여부, 항목·금액·결제자 및 분담 대상자.
- **금지:** 참석자 3명이라는 이유로 술값을 3등분하거나, 반대로 마시지 않았다는 설명만으로 전체 2차 비용에서 도윤을 제외함.

### 사례 B: `fixed_amount`와 선결제

- 발화: “민수가 식사비 6만 원을 냈고 지수는 식사비 만 원만 부담하기로 했어.”
- **결제:** 민수 = `payer`, 지출 원금 = 60,000원.
- **예외:** 지수의 해당 식사 `fixed_amount`는 10,000원이라는 **소비 몫**이다.
- **확인 필요:** 나머지 50,000원을 어떤 사람에게 어떤 규칙으로 배분할지.
- **금지:** 지수에게 기본 분담액에 10,000원을 추가 청구하거나, 지수의 10,000원을 전체 지출에서 무조건 없애는 처리.

### 사례 C: 찬조와 송금

- 발화: “식사비 5만 원 중 만 원은 선배가 찬조해 주기로 했어.”
- **추출:** 식사 원금 50,000원 및 찬조 약속 10,000원 후보.
- **확인 필요:** 찬조자·대상 항목·수령/충당 상태·나머지 40,000원의 분담 대상과 규칙.
- **금지:** 찬조자가 식사를 하지 않았다고 추론하거나, 약속만으로 실제 입금 완료 처리.

### 사례 D: 영수증 인식과 자연어 인물 연결

- 영수증에 “맥주 18,000원”이 보이지만 사람 이름은 없고, 발화에 “민수는 술 안 먹었어”가 있음.
- **인식 단계:** 품목·금액 추출 후보와 발화 근거를 각각 보존.
- **검토 단계:** 실제로 맥주 품목에서 민수가 제외되어야 하는지 사용자에게 확인.
- **금지:** 영수증에서 특정 개인이 술을 소비한 것처럼 창작하거나 자동 승인.

## 10. 문서/구현 간 우선순위와 변경 절차

1. **용어의 뜻과 관계:** `docs/ontology.yaml` 정본 → `docs/ontology.md` 설명 → 이 `word.md`의 쉬운 풀이.
2. **요구사항 및 수용 기준:** `docs/SPEC.md`.
3. **개발·테스트 변경 규칙:** 루트 `AGENTS.md`.
4. **DTO 필드, required/enum/null:** `src/settlements/schemas/request_context.schema.json`.
5. **실제 API 및 코드 동작:** 해당 소스 파일과 실행된 테스트·로그. 설계 문서만으로 구현 여부를 단정하지 않는다.
6. **회귀 검증:** `tests/harness/golden_cases.yaml` 및 관련 테스트 파일은 기대 결과를 임의로 수정하지 않는다.

온톨로지 속성명과 DTO 필드명이 다를 경우(예: `Expense.payer` vs `expenses[].payer_name`, `Expense.subsidy` vs `contributions`, `SplitRule.remainder_payer` vs `remainder_payer_name`)는 **의미 매핑**을 수행한다. 이름만 다르다는 이유로 JSON Schema 필드명을 독단적으로 바꾸지 않는다.

---

**검증 상태:** 이 용어집은 제공된 `ontology.yaml`, `ontology.md`, `SPEC.md`, `AGENTS.md` 및 첨부된 `request_context.schema.json`을 기준으로 작성했다. Gemini 모델의 현재 사용 가능 여부, 실제 SQLite 상태, G01~G08 및 전체 회귀 테스트 통과 여부는 별도 실행·검증이 필요하다.
