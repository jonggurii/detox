# 제품 스펙 v1 (SDD)

**1. 문제**

모임의 정산 담당자는 개인별 소비·참여 시점·찬조금 등 서로 다른 분담 조건을 반영하고 지출·청구·입금 기록을 맞추기 위해 여러 도구에서 계산과 대조를 반복하며, 그 과정에서 중복·누락 확인과 정산 근거 설명·재요청에 추가 시간과 부담을 들인다.

**2. 타깃 사용자**

최근 1개월 이내 모임·여행 등에서 지출을 취합하고, 개인별 부담액 산정·정산 안내·입금 확인을 직접 담당한 사람. 특히 소비 항목·참여 시점·찬조금 등의 차이를 반영해야 하는 정산 담당자. 
비대상 : 정산을 관리하지 않고 안내받은 금액만 송금하는 참여자. 다만 내역 확인·안내 수신의 대상에는 포함. 기업의 공식 회계·세무·경비 승인, 판매대금 관리, 전문적인 채권 회수 업무

**3. 핵심 기능(한 문장)**

자연어 요청 + 메모/OCR 등의 기록 자료 첨부 -> 사용자가 제시한 **조건에 맞는 정확한 개인별 부담액과 송금 요청 금액** 산출 -> 청구별 확인 상태 관리 -> 정산 마무리

**4. 범위**

- 포함 : 자연어 -> RequestContext 파싱, 사용자가 제시한 분담 조건에 기반한 정산, 정산 참여자들이 납득할 수 있는 정산 근거 제공, 청구별 확인 상태 관리
- 비포함 : 은행 API 자동 이체 및 자동 입금 조회, 카카오톡 자동 발송, 훼손된 영수증 복원

**5. 인터페이스**

- `POST /parse` - body : `{ "user_text": string, "receipt_image": optional }` → `{ "context": SettlementRequestContext, "needs_confirmation": boolean, "clarification_question": optional }`


- `POST /calculate` - body : `{ "context": SettlementRequestContext }` → `{ "round_breakdown": [...], "allocations": [...], "settlement_results": [...], "validation": {...} }`

- `POST /payments` - `{ "result_id": string, "amount": integer, "method": "settlement_service" | "bank_transfer" }`

- `POST /payments/{payment_record_id}/confirm`

- 요청: `{ "checked_by": participant_id }`
- 담당자가 실제 입금 내역을 확인했을 때만 해당 `PaymentRecord`를 `confirmed`로 바꾼다. 확인 금액 합계가 청구액을 초과하면 확정하지 않고 검토 오류를 반환한다.

- `POST /reminder`- body : `{ "result_ids": string[], "tone": string }` → `{ "message_text": string }`

## EARS 수용 기준

- AC1 [상시 적용] : 시스템은 계산 확정 시 합계식, 항목당 유효 규칙 1개, 항목·참여자당 최종 부담액 1개를 검증한다. 
- AC2 [이벤트 기반] : 사용자가 정산 발화를 입력하면, 시스템은 스키마에 맞는 RequestContext, 원문, 검토 결과를 반환한다. 언급하지 않은 사람·금액·계좌·말투를 추가하지 않는다.
- AC3 [이벤트 기반] : 송금 요청을 생성하면, 시스템은 결제·보낼 사람·받을 사람별 유효 요청을 하나만 만들고 해당 결제의 그 사람 부담액 전체를 근거로 연결한다.
- AC4 [상태 기반] : 찬조금이 있으면, 시스템은 항목별 적용 합계·대상 결제·찬조자·전달 또는 충당 확인을 검증한 뒤에만 반영한다.
- AC5 [예외 대응] : 모델 응답이 JSON·자료형·허용값 검증에 실패하면, 시스템은 1회만 재시도하고 재실패 시 수동 입력을 안내한다.
- AC6 [이벤트 기반] : 입력 금액이나 규칙을 수정하면, 시스템은 이전 버전과 변경 근거를 보존하고 확인을 무효화한다.