"""확인된 조건용 순수 계산기.

확인 ID·입력 버전·실제 찬조 전달 검증은 앱의 책임이다.
이 함수는 확인 기록을 생성하거나 돈을 송금하지 않는다.
"""
from collections import defaultdict
from dataclasses import dataclass

from .allocation_math import item_shares


class CalculationError(ValueError):
    pass


@dataclass(frozen=True)
class Allocation:
    expense_index: int
    item_index: int
    participant_name: str
    amount: int
    basis: str

    @property
    def reason(self):
        return self.basis


@dataclass(frozen=True)
class SettlementResult:
    expense_index: int
    from_participant: str
    to_participant: str
    amount: int

    @property
    def debtor_name(self):
        return self.from_participant

    @property
    def payer_name(self):
        return self.to_participant

    @property
    def sender(self):
        return self.from_participant

    @property
    def receiver(self):
        return self.to_participant


Transfer = SettlementResult


@dataclass(frozen=True)
class CalculationResult:
    allocations: tuple[Allocation, ...]
    settlements: tuple[SettlementResult, ...]
    participant_totals: dict[str, int]
    contribution_amount: int

    @property
    def transfers(self):
        return self.settlements

    def share_for(self, name):
        return self.participant_totals.get(name, 0)


def calculate_settlement(context):
    # 지연 import로 초기화 순환을 방지한다.
    from .parser import (
        OutputFormatError,
        review_context,
        validate_context_data,
    )

    raw = (
        context.model_dump(exclude_unset=True)
        if hasattr(context, "model_dump")
        else context
    )

    try:
        data = validate_context_data(raw).model_dump(
            exclude_unset=True
        )
        issues = review_context(data)
    except OutputFormatError as exc:
        raise CalculationError(
            f"입력 스키마 위반: {exc}"
        ) from exc

    if issues:
        raise CalculationError(
            "; ".join(
                f"{issue.code}@{issue.path}: {issue.question}"
                for issue in issues
            )
        )

    rules = {
        (rule["expense_index"], rule["item_index"]): rule
        for rule in data["split_rules"]
    }
    adjustments = defaultdict(list)
    contributions = defaultdict(int)

    for exception in data.get("exceptions", []):
        key = (
            exception["expense_index"],
            exception["item_index"],
        )
        adjustments[key].append(exception)

    for contribution in data.get("contributions", []):
        for use in contribution["uses"]:
            key = (
                contribution["expense_index"],
                use["item_index"],
            )
            contributions[key] += use["amount"]

    allocations = []
    settlements = []
    totals = dict.fromkeys(data["participants"], 0)

    for ei, expense in enumerate(data["expenses"]):
        expense_totals = defaultdict(int)
        contribution_total = 0

        for ii, item in enumerate(expense["items"]):
            key = ei, ii
            rule = rules[key]
            applied = contributions[key]

            shares, exact, remainder = item_shares(
                item["amount"] - applied,
                rule,
                adjustments[key],
            )
            contribution_total += applied

            for name, amount in shares.items():
                basis = (
                    f"원금={item['amount']}; "
                    f"찬조={applied}; "
                    f"방식={rule['method']}; "
                    f"조정={adjustments[key]!r}; "
                    f"이전후정확한몫={exact[name]}; "
                    f"잔액={remainder}; "
                    f"잔액부담자={rule.get('remainder_payer_name')}; "
                    f"최종={amount}"
                )

                # 기존 Allocation 출력 계약과 동일하게 0원은 생략한다.
                # participant_totals에는 0원을 유지한다.
                if amount:
                    allocations.append(Allocation(
                        expense_index=ei,
                        item_index=ii,
                        participant_name=name,
                        amount=amount,
                        basis=basis,
                    ))

                totals[name] += amount
                expense_totals[name] += amount

        payer = expense["payer_name"]

        requests = [
            SettlementResult(
                expense_index=ei,
                from_participant=name,
                to_participant=payer,
                amount=amount,
            )
            for name, amount in sorted(expense_totals.items())
            if name != payer and amount > 0
        ]

        if (
            sum(request.amount for request in requests)
            + expense_totals[payer]
            + contribution_total
            != expense["total_amount"]
        ):
            raise CalculationError(
                "결제별 송금 요청 합계 검증 실패"
            )

        settlements.extend(requests)

    return CalculationResult(
        allocations=tuple(allocations),
        settlements=tuple(settlements),
        participant_totals=totals,
        contribution_amount=sum(contributions.values()),
    )