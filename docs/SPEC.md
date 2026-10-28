# 제품 스펙 v1 (SDD)

## 무엇을 만드는가

영수증 사진 OCR과 자연어 예외 조건을 입력받아 `SettlementRequestContext`로 구조화하고, Python 정밀 계산으로 차수별 개인 부담금을 산출한 뒤 정산 결과와 계좌 안내가 포함된 톤별 독촉 문구를 생성하는 정산 봇이다.

## 핵심 기능

1. 영수증 OCR: 가게명, 총액, 결제 일시, 세부 메뉴를 추출한다.
2. 자연어 예외 파싱: “2차는 희주 빼고”, “술 안 마신 2명 차감” 같은 조건을 구조화한다.
3. 정밀 계산: LLM이 아닌 Python 코드로 차수별 금액과 1원 단위 분배를 계산한다.
4. 독촉 문구 생성: `polite_formal`, `friendly_casual`, `humorous` 톤을 지원한다.
5. mock 계좌 안내: 실제 이체 없이 복사 가능한 계좌 안내 텍스트를 제공한다.

## 범위

### 포함 (In Scope)

- 영수증 OCR 문자 인식
- `SettlementRequestContext` 자연어 예외 파싱
- `ItemException`을 반영한 Python 정밀 산술 엔진
- 세 가지 톤의 카카오톡 문구 생성
- 실제 이체 없는 mock 계좌 안내

### 제외 (Out of Scope)

- 은행 API 직접 이체
- 법인카드 승인 내역 자동 연동
- 훼손된 종이 영수증 복원

## API 인터페이스

### `POST /parse`

요청: `{ "user_text": string, "receipt_image": optional }`

응답: `{ "context": SettlementRequestContext }`

### `POST /calculate`

요청: `{ "context": SettlementRequestContext }`

응답: `{ "round_breakdown": object, "individual_amounts": object }`

### `POST /reminder`

요청: `{ "context": SettlementRequestContext, "calculation_result": object, "tone": ReminderTone }`

응답: `{ "message_text": string }`

## EARS 수용 기준

| ID | 대표 이름 | 조건과 필수 동작 | 실패 조건 | 연결 케이스 |
|---|---|---|---|---|
| **AC1** | 정상 입력 유지 | 대상자·결제자·항목·균등 기준·명시적 제외 조건이 서로 일치하거나, 스키마가 허용한 1인·0원 입력이면 확인 항목 없이 `[]`를 반환한다. | 정상 입력에 불필요한 확인 질문을 추가하거나, 확인 항목 대신 최종 계산 결과를 반환한다. | G01, G02 |
| **AC2** | 누락 정보 확인 | 참여자 또는 결제 목록이 비어 있거나 결제자를 식별할 수 없으면, 해당 위치의 확인 항목을 반환한다. | 누락을 놓치거나 사람·결제를 만들어 채운다. 결제자를 첫 참여자나 총무로 임의 지정한다. | G03, G04 |
| **AC3** | 금액 불일치 확인 | 항목 금액의 합계와 결제 총액이 다르면, 해당 결제의 합계 불일치를 반환하고 두 금액을 모두 보존한다. | 불일치를 알리지 않거나, 총액·항목 금액 중 하나를 자동으로 맞춘다. | G05 |
| **AC4** | 미정 부담 조정 확인 | 개인별 부담 조정의 대상 항목과 조정 방식이 미정이면, 미정인 각각의 위치를 확인 대상으로 반환한다. | “한 잔만 마셨다” 같은 메모만 보고 제외 항목·조정 방식·합의 금액을 확정한다. | G06 |
| **AC5** | 잔액 부담자 확인 | 균등 분담 후 원 단위 나머지가 생기고 부담자가 지정되지 않았으면, 해당 항목의 잔액 부담자를 확인하도록 반환한다. | 나머지를 버리거나 특정 사람에게 임의 배정하고 확인 항목을 누락한다. | G07 |
| **AC6** | 원본 보존과 지시문 비실행 | 모든 입력을 변경하지 않고 확인 항목만 반환한다. 구조화 값은 같고 조정 이유에 검증 우회 지시만 추가되면, 그 지시를 실행하지 않고 확인 항목의 코드·위치를 유지한다. | 금액·명단·조정·상태·추가 키를 변경하거나, 메모의 지시문 때문에 검토 결과를 바꾼다. | 전체 입력 불변 검사, G01↔G08 비교 |


version: 1
target: settlements.parser.review_context
fixtures:
  valid_input: &valid_input
    participants: [A, B, C]
    expenses:
      - &valid_expense
        total_amount: 120000
        payer_name: A
        items:
          - {name: 식사비, amount: 90000}
          - {name: 술값, amount: 30000}
    split_rules:
      - {expense_index: 0, item_index: 0, method: equal, participant_names: [A, B, C]}
      - {expense_index: 0, item_index: 1, method: equal, participant_names: [A, B, C]}
    exceptions:
      - &valid_exception
        expense_index: 0
        item_index: 1
        participant_name: A
        kind: exclude
        reason: A는 술을 마시지 않아 술값에서 제외하기로 했다.
cases:
  # G01 | 정상 — 식사·술 항목과 제외 조건이 명확함
  - id: G01
    name: valid_mixed_items
    category: normal
    ac_ids: [AC1, AC6]
    context: *valid_input
    expect_issue_count: 0
    expect_issue_keys: []
    must_preserve_input: true
    note: 식사·술 규칙과 항목별 제외가 명확하다. 정상 입력을 고치거나 거부하지 않는다.

  # G02 | 경계 — 1인·0원 허용 입력
  - id: G02
    name: single_person_zero_cost
    category: boundary
    ac_ids: [AC1, AC6]
    context:
      participants: [A]
      expenses:
        - {total_amount: 0, payer_name: A, items: [{name: 비용 없음, amount: 0}]}
      split_rules:
        - {expense_index: 0, item_index: 0, method: equal, participant_names: [A]}
    expect_issue_count: 0
    expect_issue_keys: []
    must_preserve_input: true
    note: 0원은 스키마가 허용한 최소 금액이다. 1인 입력도 확인 질문을 강제로 만들지 않는다.

  # G03 | 경계 — 참여자·결제 목록 없음
  - id: G03
    name: empty_context
    category: boundary
    ac_ids: [AC2, AC6]
    context: {participants: [], expenses: []}
    expect_issue_count: 2
    expect_issue_keys:
      - {code: missing_participants, path: participants}
      - {code: missing_expenses, path: expenses}
    must_preserve_input: true
    note: 빈 입력은 스키마상 유효하지만 계산 정보가 없다. 사람·결제를 생성하지 않는다.

  # G04 | 경계 — 결제자 미정
  - id: G04
    name: unknown_payer
    category: boundary
    ac_ids: [AC2, AC6]
    context:
      <<: *valid_input
      expenses:
        - {<<: *valid_expense, payer_name: null}
    expect_issue_count: 1
    expect_issue_keys:
      - {code: unresolved_person, path: "expenses[0].payer_name"}
    must_preserve_input: true
    note: 결제자를 총무나 첫 번째 참여자로 자동 지정하지 않는다.

  # G05 | 금지 행동 — 불일치 금액 자동 보정 금지
  - id: G05
    name: item_total_mismatch
    category: prohibited
    ac_ids: [AC3, AC6]
    context:
      <<: *valid_input
      expenses:
        - {<<: *valid_expense, total_amount: 119000}
    expect_issue_count: 1
    expect_issue_keys:
      - {code: item_sum_mismatch, path: "expenses[0]"}
    must_preserve_input: true
    note: 항목 합계 120000원과 결제 119000원을 모두 보존하고 불일치를 알린다.

  # G06 | 경계 — 조정 항목과 방식 미정
  - id: G06
    name: unresolved_adjustment
    category: boundary
    ac_ids: [AC4, AC6]
    context:
      <<: *valid_input
      exceptions:
        - {<<: *valid_exception, item_index: null, kind: null, reason: A는 한 잔만 마셨다.}
    expect_issue_count: 2