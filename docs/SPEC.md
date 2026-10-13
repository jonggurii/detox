# 제품 스펙 v2 (SDD)

**1. 문제**

모임의 정산 담당자는 개인별 소비·참여 시점·찬조금 등 서로 다른 분담 조건을 반영하고 지출·청구·입금 기록을 맞추기 위해 여러 도구에서 계산과 대조를 반복하며, 그 과정에서 중복·누락 확인과 정산 근거 설명·재요청에 추가 시간과 부담을 들인다. (상세: `PROBLEM.md`)

**2. 타깃 사용자**

최근 1개월 이내 모임·여행 등에서 지출을 취합하고, 개인별 부담액 산정·정산 안내·입금 확인을 직접 담당한 사람. 특히 소비 항목·참여 시점·찬조금 등의 차이를 반영해야 하는 정산 담당자.
현재 직접 조작 기능의 우선 대상이 아닌 역할 : 안내받은 내역을 확인하고 송금만 하는 참여자.
비대상 업무 : 기업의 공식 회계·세무·경비 승인, 판매대금 관리, 전문적인 채권 회수 업무.

**3. 핵심 기능(한 문장)**

자연어 요청 + 메모 텍스트 등의 기록 자료 첨부 (or OCR를 활용한 영수증 이미지) -> 요청과 자료를 토대로 정산 조건 추출 -> 사용자 확인 및 필요 시 수정 -> 사용자가 확인한 **분담 조건에 맞는 정확한 개인별 부담액과 송금 요청 금액** 산출 -> 청구별 확인 상태 관리 -> 정산 마무리

**4. 범위**

- 포함 : 자연어 -> RequestContext 파싱, 사용자가 제시한 분담 조건에 기반한 정산, 정산 참여자들이 납득할 수 있는 정산 근거 제공, 청구별 확인 상태 관리
- 비포함 : 은행 API 자동 이체 및 자동 입금 조회, 카카오톡 자동 발송, 훼손된 영수증 복원

**5. 인터페이스**

> 정산 조건 추출

- `POST /parse` - body : { "user_text"?: string, "receipt_image"?: file } → { "context": RequestContext | null, "needs_clarification": boolean, "clarification_questions": [...], "needs_confirmation": true }

자연어·메모·영수증 이미지에서 정산 조건을 추출한다. 불명확한 정보는 질문으로 확인하고, 사용자가 결과를 검토·수정한다. 이미지 첨부 시 multipart/form-data를 사용하며 텍스트와 이미지 중 하나 이상을 입력한다.

> 개인별 금액 계산

- `POST /calculate` - body: { "session_id": string, "context_version": integer } → { "calculation_id": string, "allocations": [...], "settlement_preview": [...], "validation": {...} }

저장된 해당 버전의 분담 조건으로 개인별 부담액·송금액·산출 근거를 미리 계산한다. 미확정 조건이나 금액 검증 오류가 있으면 확인을 요구한다. 계산 미리보기와 실제 청구 확정은 구분한다.

> 정산 안내문 생성

- `POST /settlement_notices` - body: { "session_id": string, "result_ids": string[] } → { "notice_id": string, "message_text": string }

사용자가 확정한 청구의 금액·수취자·산출 근거를 담은 안내문을 생성한다. 사용자가 외부 메신저로 전달하며, 문구 생성만으로 실제 전달 완료로 처리하지 않는다.

> 입금 대조 확인

- `POST /payments/{payment_record_id}/confirm` - body: { "checked_by": participant_id } → { "result_id": string, "confirmed_amount": integer, "remaining_amount": integer, "payment_status": string, "session_status": string }

담당자가 실제 입금 내역과 대조한 기록을 확인 처리하고 청구 상태를 갱신한다. 확인액이 청구액보다 작으면 미완료로 유지하고, 같으면 입금 확인 완료로 처리하며, 초과하면 검토를 요구한다. 은행 자동 조회는 수행하지 않는다.

> 정산 재안내 문구 생성

- `POST /reminder` — body: { "result_ids": string[], "tone"?: string, "relationship"?: string } → { "reminder_id": string, "recipient_id": string, "message_text": string } 

동일 송금자·수취자의 입금 미확인 청구에 대해 확인된 잔액과 사용자가 선택한 말투·관계를 반영한 재안내 문구를 생성한다. 입금 미확인을 실제 미입금으로 단정하지 않고, 이미 입금 확인이 완료된 청구는 대상에서 제외한다.

> 모임 정산 내역 조회

- `GET /sessions/{session_id}` → { "context": RequestContext, "settlement_results": [...], "payment_records": [...], "session_status": string }

저장된 모임의 분담 조건·청구·입금 기록과 진행 상태를 다시 확인한다. 지출 검토와 계산·청구 누락 점검을 마치고 모든 유효 청구의 입금이 확인된 경우에만 정산 완료로 표시한다.    

