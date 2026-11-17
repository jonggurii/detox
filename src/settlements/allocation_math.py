"""순수 산술: 저장·청구 생성·LLM 호출 없이 항목의 몫을 검증한다."""
from fractions import Fraction


class AllocationInputError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def item_shares(net, rule, exceptions):
    """스키마·참조 검증 이후 호출한다. 입력을 변경하지 않는다."""
    def fail(code, message):
        raise AllocationInputError(code, message)

    members = rule["participant_names"]
    excluded, fixed, covers = set(), {}, {}

    for ex in exceptions:
        name = ex["participant_name"]
        if ex["kind"] == "exclude":
            excluded.add(name)
        elif ex["kind"] == "fixed_amount":
            fixed[name] = ex["fixed_amount"]
        elif ex["kind"] == "covered_by_other":
            covers[name] = ex["covered_by_name"]

    for name, coverer in covers.items():
        if coverer not in members:
            fail(
                "coverer_outside_rule",
                "대신 부담자를 해당 항목의 기본 부담 대상자로 확인해 주세요.",
            )
        if coverer in excluded:
            fail(
                "conflicting_adjustment",
                "부담 제외 대상에게 대신 부담을 이전할 수 없습니다. "
                "조건을 다시 확인해 주세요.",
            )

    if set(covers) & set(covers.values()):
        fail(
            "cover_chain_or_cycle",
            "대신 부담의 연쇄·순환을 해소해 주세요.",
        )

    exact = {name: Fraction(0) for name in members}

    if rule["method"] == "explicit_amount":
        exact.update({
            row["participant_name"]: Fraction(row["amount"])
            for row in rule["individual_amounts"]
        })

        if sum(exact.values()) != net:
            fail(
                "individual_sum_mismatch",
                "개인별 소비 몫 합계가 찬조 차감 후 금액과 다릅니다.",
            )

        if (
            any(exact[p] != 0 for p in excluded)
            or any(exact[p] != value for p, value in fixed.items())
        ):
            fail(
                "individual_adjustment_mismatch",
                "명시 금액과 제외·합의 소비 몫이 충돌합니다.",
            )
    else:
        exact.update({
            person: Fraction(amount)
            for person, amount in fixed.items()
        })

        remaining = [
            person for person in members
            if person not in excluded and person not in fixed
        ]
        available = net - sum(fixed.values())

        if available < 0:
            fail(
                "fixed_amounts_exceed_available",
                "합의 소비 몫 합계가 배분 금액을 넘습니다.",
            )
        if available and not remaining:
            fail(
                "no_remaining_payer",
                "남은 금액을 부담할 사람이 없습니다.",
            )
        if remaining:
            exact.update({
                person: Fraction(available, len(remaining))
                for person in remaining
            })

    # 정수 처리 전에 정확한 소비 몫을 이전한다.
    for name, coverer in covers.items():
        exact[coverer] += exact[name]
        exact[name] = Fraction(0)

    shares = {
        person: int(value)
        for person, value in exact.items()
    }
    remainder = net - sum(shares.values())
    original_remainder = remainder

    if remainder:
        payer = rule.get("remainder_payer_name")

        if not payer:
            # 명시적 부담자가 없으면 유효한 분담자 순서대로 1원씩 분배한다.
            # 고정 합의액과 다른 사람에게 이전한 몫은 변경하지 않는다.
            eligible = [
                name for name in members
                if name not in excluded
                and name not in covers
                and (name not in fixed or name in covers.values())
            ]
            if not eligible:
                fail(
                    "unresolved_rounding",
                    "원 단위 나머지를 배분할 유효한 부담자가 없습니다.",
                )
            for index in range(remainder):
                shares[eligible[index % len(eligible)]] += 1
            remainder = 0
        elif payer in covers:
            fail(
                "invalid_remainder_payer",
                "잔액 부담자가 본인 몫을 다른 사람에게 이전했습니다.",
            )
        if payer and (payer not in members or payer in excluded):
            fail(
                "invalid_remainder_payer",
                "잔액 부담자가 유효한 부담 대상이 아닙니다.",
            )
        if payer and payer in fixed and payer not in covers.values():
            fail(
                "invalid_remainder_payer",
                "고정 합의액에 잔액을 더하려면 새 합의가 필요합니다.",
            )

        if payer:
            shares[payer] += remainder

    if sum(shares.values()) != net:
        fail(
            "allocation_sum_mismatch",
            "항목별 부담액 합계가 배분 금액과 다릅니다.",
        )

    return shares, exact, original_remainder