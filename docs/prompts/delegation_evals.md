# 4단계 Evals 러너 위임 및 검증 기록 — 모아정산

- 평가 범위: `docs/SPEC.md`의 MVP1·MVP2·AC2~6·EXTRACT1~6
- 판정 기준: 팀 검토 전 **초안** `evals/EVAL_DESIGN.md`, `evals/evalset.jsonl`
- 작성자 구분: 케이스·합격선·절대 규칙 기대값은 **사람 최종 확인 대상**. 러너는 이 기준을 실행하는 도구다.

## 1. 러너 위임 목표 (작업 프롬프트 기록)

> `evals/run_evals.py`를 구현한다. `evalset.jsonl`에서 케이스를 읽어 `kind=text`는 `settlements.parser.parse_and_review`, `kind=receipt`는 `GeminiReceiptReader`를 사용한다. 출력은 JSON Schema/영수증 추출 계약을 검사하고, 각 `expect` 키마다 실제 값을 채점한다. 지원하지 않는 키는 통과 취급하지 않고 오류로 처리한다. 케이스 ID에 따라 정답을 분기하지 않는다. 저장 출력 모드는 사람이 만든 출력으로 하니스만 검증하며 실제 Gemini 점수로 표시하지 않는다. 실행 결과를 매번 새 JSON과 CSV 이력 한 줄로 기록한다. 실패·예외도 분모에 포함한다. 원본 골든 케이스와 기존 테스트는 수정하지 않는다. 팀의 승인 없이 수용 기준·정답을 낮추지 않는다.

## 2. 사용한 입력·경계

- 읽기 전용 기준: `docs/SPEC.md`, `tests/harness/golden_cases.yaml`, `evals/EVAL_DESIGN.md`, `evals/evalset.jsonl`
- 변경 범위: `evals/` 신규 파일, `tests/test_evals_runner.py` 신규 검증 파일, 문서의 평가 실행 설명.
- 구현 경계: 이미지 생성/금액 계산은 평가 러너가 하지 않는다. `stored`는 실제 `review_context()`/`parse_receipt_output()`을 실행하고, `live`는 원제품 추출 함수를 호출한다.

## 3. 실행 및 결함 주입 결과

아래 검사는 저장 출력의 사본에 **일부러 오답을 넣어** 수행한다. 원래 케이스·골든 기대값을 바꾸지 않는다.

| 주입한 결함(시험 코드) | 검출 기준 | 실제 결과 |
|---|---|---|
| T01 결제 총액 84,000→1원(`test_amount_corruption_is_detected`) | 잘못된 `expenses`/허용되지 않은 금액 검사 실패 | 검출: pytest 통과 |
| T25 인젝션 입력에 허구 참여자 `해커` 추가 (`test_injection_added_fictitious_person_is_detected`) | 허용되지 않은 인물 검사 실패 | 검출: pytest 통과 |
| T14 결제자 미상 대신 임의 `민수` 지정 (`test_clarification_bypass_is_detected`) | 필수 확인 이슈 누락 검사 실패 | 검출: pytest 통과 |
| R04 영수증 총액을 품목합계 68,000원으로 몰래 수정 (`test_receipt_mismatch_silencing_is_detected`) | 원본 70,000원 불일치 및 경고 누락 검사 실패 | 검출: pytest 통과 |
| T01 스키마 외 `invented_field` 삽입 (`test_invalid_fixture_schema_is_not_silently_skipped`) | 스키마 거부, 실패·분모 유지 | 검출: pytest 통과 |
| 미지원 판정 키 추가 (`test_unsupported_expect_key_rejected`) | 케이스 로더에서 `ValueError` | 검출: pytest 통과 |

실제 실행 명령:

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/test_evals_runner.py -q
python evals/run_evals.py --mode stored --change "저장 출력 하니스 검증"
```

**관측 결과:** 신규 러너 검증 `8 passed`, 저장 출력 `35/35 PASS`(실제 모델 정확도 아님). 여기의 수치들은 컨테이너에서 실행한 검사이며, SDK를 이용한 실제 API 호출 결과가 아니다.

## 4. 최초 검증 회차·기준 변경 기록

1. 최초 하니스 실행: `32/35` 통과. 실패는 T08(합의 금액 5,000원 허용값 누락), T09(확정 찬조금 조합의 확인 상태 예상과 구현 처리 불일치), T18(실제 검토 이슈 코드 `receipt_mismatch` 오기)였다.
2. **사람 승인 전 작성 중인 평가 초안**을 실제 `review_context()` 계약과 대조해 수정했다. T08에는 원문에 있던 5,000원을 허용값에 추가하고, T09의 정책상 추가 확인 이슈가 없음을 확인했으며, T18의 공식 이슈 키로 정정했다.
3. 재실행: `35/35` 저장 출력 기준선; 결함 주입 6종 검출. 위 수정은 **초안 정비**이며, 이미 팀 승인을 받아 고정한 정답을 모델에 맞춰 바꾼 행동이 아니다. 팀 승인 후에는 모델 성능 향상을 위해 기준을 바꾸지 않는다.
4. 검수 시 Git diff로 기존 `tests/harness/golden_cases.yaml`과 기존 테스트의 무단 변경 여부를 확인한다.

## 5. 미완료 / 추가 확인

- Gemini 라이브 최초 베이스라인은 API 키를 설정한 실행 환경에서 수행해야 한다.
- 합성 영수증 4개만으로 실물 영수증 품질을 보증하지 않는다.
- 합격선/금지 행동 기대값은 팀원이 직접 확인하고 승인해야 평가의 공식 기준이 된다.
- 첫 live 결과에 실패가 있으면 원문·실제 출력·판정을 사람이 분석하고 범주별 건수로 기록한다.
