
"""Gemini 파싱 → 사용자 검토 → 정산 계산 통합 실행."""

import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from .parser import (
    parse_and_review,
    review_context,
    validate_context_data,
    ParserError,
)
from .calculator import (
    calculate_settlement,
    CalculationError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def show_context(context):
    print("\n===== Gemini 구조화 결과 =====")
    print(json.dumps(
        context,
        ensure_ascii=False,
        indent=2,
    ))


def show_issues(issues):
    print("\n===== 입력 검토 결과 =====")

    if not issues:
        print("자동 검토에서 확인 항목이 발견되지 않았습니다.")
        return

    for issue in issues:
        print(
            f"[{issue.code}] "
            f"{issue.path}: {issue.question}"
        )


def confirm_context(context):
    """사용자가 검토·수정한 JSON을 확인한다."""

    while True:
        answer = input(
            "\n조건이 정확합니까? "
            "[y=확인 / e=JSON 수정 / n=취소]: "
        ).strip().lower()

        if answer == "n":
            return None

        if answer == "e":
            print(
                "수정할 JSON 파일 경로를 입력하세요.\n"
                "현재 구조화 결과를 파일에 복사해 "
                "수정한 뒤 경로를 입력하면 됩니다."
            )
            path = input("JSON 파일 경로: ").strip().strip('"')

            try:
                edited = json.loads(
                    Path(path).read_text(encoding="utf-8")
                )
                context = validate_context_data(
                    edited
                ).model_dump(exclude_unset=True)

                show_context(context)

            except Exception as exc:
                print(f"수정 JSON 검증 실패: {exc}")

            continue

        if answer == "y":
            issues = review_context(context)

            if issues:
                show_issues(issues)
                print("미해결 조건이 있어 계산할 수 없습니다.")
                continue

            return context

        print("y, e, n 중 하나를 입력해 주세요.")


def serialize_calculation(result):
    """dataclass 계산 결과를 JSON으로 변환한다."""

    return {
        "allocations": [
            asdict(a) for a in result.allocations
        ],
        "settlement_preview": [
            asdict(s) for s in result.settlements
        ],
        "participant_totals": result.participant_totals,
        "contribution_amount": result.contribution_amount,
    }


def run_workflow():
    print("=" * 55)
    print("복합 N빵 정산 통합 MVP")
    print("=" * 55)

    user_text = input("\n정산 내용을 입력하세요: ").strip()

    if not user_text:
        print("입력이 비어 있습니다.")
        return

    start = time.perf_counter()

    try:
        print("\nGemini 파싱 중...", flush=True)

        parsed = parse_and_review(user_text)

        context = parsed.context.model_dump(
            exclude_unset=True
        )

        show_context(context)
        show_issues(parsed.issues)

        print(f"\n파싱 상태: {parsed.status}")
        print(f"사용 모델: {parsed.model}")

        confirmed = confirm_context(context)

        if confirmed is None:
            print("정산을 취소했습니다.")
            return

        print("\n정산 계산 중...")

        result = calculate_settlement(confirmed)

        output = serialize_calculation(result)

        print("\n===== 최종 계산 결과 =====")
        print(json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ))

        print("\n===== 개인별 총 부담액 =====")
        for name, amount in result.participant_totals.items():
            print(f"{name}: {amount:,}원")

        print("\n===== 송금 요청 미리보기 =====")
        if not result.settlements:
            print("송금 요청 없음")

        for transfer in result.settlements:
            print(
                f"{transfer.from_participant} → "
                f"{transfer.to_participant}: "
                f"{transfer.amount:,}원"
            )

        print(
            f"\n전체 소요 시간: "
            f"{time.perf_counter() - start:.2f}초"
        )

    except (ParserError, CalculationError, ValueError) as exc:
        print(f"\n처리 실패: {exc}")


if __name__ == "__main__":
    run_workflow()
