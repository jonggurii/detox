# `review_context()` 결함 주입 검증 — 강의 5·90 보완

> 2026-11-25, 격리된 프로젝트 작업본에서 `scripts/verify_golden_mutations.py`를 실행한 결과다. 로컬·GitHub 최종 브랜치에도 동일하게 재실행해야 해당 커밋의 증거로 사용할 수 있다. **실패 로그는 통과로 꾸미지 않는다.**

## 대상 및 실험 기록

- 실제 대상 구현: `src/settlements/parser.py`의 `review_context` 항목 합계 비교 검사(원본 약 756~760행).
- 골든 입력·판정: `tests/harness/golden_cases.yaml`의 **G01~G08**, `tests/test_context_review_golden.py`.
- 결함 M1: 임시 복사본에서 `sum(item["amount"] for item in items) != expense["total_amount"]` 판정을 `False`로 대체하여 `item_sum_mismatch` 검사를 무력화.
- 결과: `G05 item_total_mismatch` **1 failed, 나머지 7 passed**. 합계 불일치 검출 실패를 골든이 잡음.
- 결함 M2: 임시 복사본의 검토 함수에 `injected_false_positive` 허위 확인 문제를 추가.
- 결과: G01~G08 **8 failed**. 정상 입력의 허위 경고도 골든이 잡음.
- 원복: 원본 구현으로 다시 실행하여 **G01~G08 8 passed** 확인.
- 2026-11-25 확장 골든: 새 **G09~G25**를 별도 대상 함수 검증으로 추가하며 기존 M1·M2의 기대값을 변경하지 않음.

## 재현

```powershell
$env:PYTHONPATH="src"
python scripts/verify_golden_mutations.py
python -m pytest tests/test_context_review_golden.py tests/test_mvp_acceptance_golden.py -q
```

> 결함을 실제 GitHub main에 주입하지 않는다. 스크립트가 임시 복사본에만 결함을 만들고 복원한다. 이 기록은 **합성 결함 주입**의 증거이지 실제 사용자 피해 사례가 아니다.

기존 상세 기록(존재하는 경우): [`delegation_context_review.md`](delegation_context_review.md).
