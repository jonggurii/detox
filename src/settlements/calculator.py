from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from pydantic import BaseModel

from settlements.parser import RequestContext


class CalculationError(ValueError):
    """정산 계산 조건 위반 또는 미확정 입력 시 발생하는 예외."""


@dataclass
class Allocation:
    """항목별 개인 최종 부담 배정 결과."""

    expense_index: int
    item_index: int
    participant_name: str
    amount: int
    basis: str


@dataclass
class SettlementResult:
    """SPEC 기준 개별 송금 요청(누가 누구에게 얼마를 보내는지)."""

    from_participant: str
    to_participant: str
    amount: int

    @property
    def sender(self) -> str:
        return self.from_participant

    @property
    def receiver(self) -> str:
        return self.to_participant


# 하위 호환 별칭 유지
Transfer = SettlementResult


@dataclass
class CalculationResult:
    """정산 계산 전체 결과 묶음."""

    allocations: list[Allocation] = field(default_factory=list)
    settlements: list[SettlementResult] = field(default_factory=list)
    participant_totals: dict[str, int] = field(default_factory=dict)

    @property
    def transfers(self) -> list[SettlementResult]:
        return self.settlements

    def share_for(self, participant_name: str) -> int:
        return self.participant_totals.get(participant_name, 0)


def _as_dict(context: RequestContext | dict[str, Any]) -> dict[str, Any]:
    if isinstance(context, BaseModel):
        return context.model_dump(exclude_none=False)
    return dict(context)


def _validate_cover_graph(covers: dict[str, str], valid_participants: set[str]) -> None:
    """대신 부담의 대상자 유효성 및 순환·연쇄(chain/cycle) 여부를 검사한다."""
    for person, coverer in covers.items():
        if person not in valid_participants or coverer not in valid_participants:
            raise CalculationError(f"대신 부담 당사자({person} -> {coverer})가 기본 부담 대상자에 없습니다.")
        if person == coverer:
            raise CalculationError(f"자기 자신({person})을 대신 부담자로 지정할 수 없습니다.")
    for person, coverer in covers.items():
        if coverer in covers:
            raise CalculationError(
                f"대신 부담의 연쇄 또는 순환({person} -> {coverer} -> {covers[coverer]})은 허용하지 않습니다."
            )


def calculate_settlement(context: RequestContext | dict[str, Any]) -> CalculationResult:
    """
    SPEC 5.4 순서에 따라 정밀 정산을 수행한다:
    1. 찬조금 공제
    2. Fraction으로 개인별 정확한 소비 몫 계산 (exclude / fixed_amount 또는 explicit_amount)
    3. covered_by_other를 적용해 정확한 Fraction 몫을 이전
    4. 최종 몫의 정수 부분을 구함
    5. 남은 원 단위 금액을 확인된 유효 부담자(remainder_payer_name)에게 배정
    6. 합계 검증 후 Allocation 및 송금 요청(SettlementResult) 생성
    """
    data = _as_dict(context)
    participants: list[str] = data.get("participants") or []
    expenses: list[dict[str, Any]] = data.get("expenses") or []
    split_rules: list[dict[str, Any]] = data.get("split_rules") or []
    exceptions: list[dict[str, Any]] = data.get("exceptions") or []
    contributions: list[dict[str, Any]] = data.get("contributions") or []

    if not participants or not expenses:
        raise CalculationError("참여자(participants)와 결제 내역(expenses)이 필요합니다.")

    participant_set = set(participants)

    # 1. 찬조금 검증 및 항목별 찬조금 매핑
    item_contributions: dict[tuple[int, int], int] = {}
    for c_idx, contrib in enumerate(contributions):
        if not contrib.get("funding_note"):
            raise CalculationError(f"찬조금[{c_idx}]의 funding_note가 누락되었습니다.")
        exp_idx = contrib.get("expense_index")
        c_amount = contrib.get("amount")
        uses = contrib.get("uses") or []

        if exp_idx is None or not (0 <= exp_idx < len(expenses)):
            raise CalculationError(f"찬조금[{c_idx}]의 expense_index가 유효하지 않습니다.")
        if c_amount is None or c_amount <= 0:
            raise CalculationError(f"찬조금[{c_idx}]의 금액이 유효하지 않습니다.")
        if not uses:
            raise CalculationError(f"찬조금[{c_idx}]의 항목별 적용 내역(uses)이 없습니다.")

        use_sum = 0
        for use in uses:
            u_item_idx = use.get("item_index")
            u_amt = use.get("amount")
            if u_item_idx is None or u_amt is None or u_amt <= 0:
                raise CalculationError(f"찬조금[{c_idx}]의 uses 항목이 유효하지 않습니다.")
            exp_items = expenses[exp_idx].get("items") or []
            if not (0 <= u_item_idx < len(exp_items)):
                raise CalculationError(f"찬조금[{c_idx}]의 item_index({u_item_idx})가 범위를 벗어났습니다.")
            use_sum += u_amt
            key = (exp_idx, u_item_idx)
            item_contributions[key] = item_contributions.get(key, 0) + u_amt

        if use_sum != c_amount:
            raise CalculationError(
                f"찬조금[{c_idx}] 총액({c_amount})과 항목별 적용액 합계({use_sum})가 일치하지 않습니다."
            )

    # 예외 및 분담 규칙 인덱싱
    rules_by_item: dict[tuple[int, int], dict[str, Any]] = {}
    for rule in split_rules:
        e_idx = rule.get("expense_index")
        i_idx = rule.get("item_index")
        if e_idx is None or i_idx is None:
            raise CalculationError("분담 규칙에 expense_index 또는 item_index가 누락되었습니다.")
        key = (e_idx, i_idx)
        if key in rules_by_item:
            raise CalculationError(f"항목 {key}에 중복된 분담 규칙이 존재합니다.")
        rules_by_item[key] = rule

    exceptions_by_item: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ex in exceptions:
        e_idx = ex.get("expense_index")
        i_idx = ex.get("item_index")
        if e_idx is None or i_idx is None or ex.get("kind") is None or not ex.get("participant_name"):
            raise CalculationError("예외 조건에 미정(null) 필드가 남아 있습니다.")
        exceptions_by_item.setdefault((e_idx, i_idx), []).append(ex)

    allocations: list[Allocation] = []
    participant_totals: dict[str, int] = {p: 0 for p in participants}
    # 결제별 (payer, participant) 청구 집계를 위한 누적 테이블
    net_balances: dict[str, int] = {p: 0 for p in participants}

    # 결제 및 항목 순회 계산
    for e_idx, exp in enumerate(expenses):
        payer = exp.get("payer_name")
        total_amount = exp.get("total_amount")
        items = exp.get("items") or []

        if not payer or payer not in participant_set:
            raise CalculationError(f"결제[{e_idx}]의 결제자({payer})가 유효하지 않습니다.")
        if total_amount is None or total_amount < 0 or not items:
            raise CalculationError(f"결제[{e_idx}]의 총액 또는 항목 목록이 유효하지 않습니다.")

        item_amount_sum = 0
        expense_allocated_sum = 0
        expense_contrib_sum = 0

        for i_idx, item in enumerate(items):
            item_amt = item.get("amount")
            if item_amt is None or item_amt < 0 or not item.get("name"):
                raise CalculationError(f"결제[{e_idx}] 항목[{i_idx}]의 이름 또는 금액이 유효하지 않습니다.")
            item_amount_sum += item_amt

            key = (e_idx, i_idx)
            rule = rules_by_item.get(key)
            if not rule:
                raise CalculationError(f"결제[{e_idx}] 항목[{i_idx}]에 연결된 분담 규칙이 없습니다.")

            method = rule.get("method")
            rule_participants: list[str] = rule.get("participant_names") or []
            if method not in ("equal", "explicit_amount") or not rule_participants:
                raise CalculationError(f"항목 {key}의 분담 방식 또는 대상자 명단이 유효하지 않습니다.")
            if any(p not in participant_set for p in rule_participants):
                raise CalculationError(f"항목 {key}의 분담 대상자 중 전체 참여자 명단에 없는 사람이 있습니다.")

            contrib_deduction = item_contributions.get(key, 0)
            net_item_amount = item_amt - contrib_deduction
            if net_item_amount < 0:
                raise CalculationError(f"항목 {key}의 찬조금 공제액이 항목 원금을 초과합니다.")

            ex_list = exceptions_by_item.get(key, [])
            excluded: set[str] = set()
            fixed_map: dict[str, int] = {}
            covers: dict[str, str] = {}

            for ex in ex_list:
                p_name = ex["participant_name"]
                kind = ex["kind"]
                if p_name not in rule_participants:
                    raise CalculationError(f"항목 {key}의 예외 대상자({p_name})가 기본 부담 대상자에 없습니다.")
                if kind == "exclude":
                    if p_name in fixed_map or p_name in excluded:
                        raise CalculationError(f"항목 {key}에서 {p_name}에 중복·충돌 조정이 있습니다.")
                    excluded.add(p_name)
                elif kind == "fixed_amount":
                    f_amt = ex.get("fixed_amount")
                    if f_amt is None or f_amt < 0 or p_name in excluded or p_name in fixed_map:
                        raise CalculationError(f"항목 {key}에서 {p_name}의 fixed_amount가 유효하지 않거나 충돌합니다.")
                    fixed_map[p_name] = f_amt
                elif kind == "covered_by_other":
                    c_name = ex.get("covered_by_name")
                    if not c_name or p_name in covers:
                        raise CalculationError(f"항목 {key}에서 {p_name}의 covered_by_other 설정이 유효하지 않습니다.")
                    covers[p_name] = c_name

            _validate_cover_graph(covers, set(rule_participants))

            # Step 1: Fraction으로 개인별 정확한 소비 몫 계산
            exact_shares: dict[str, Fraction] = {p: Fraction(0) for p in rule_participants}
            if method == "explicit_amount":
                if excluded or fixed_map:
                    raise CalculationError(
                        f"항목 {key}: explicit_amount 방식에서는 exclude/fixed_amount 예외를 중복 적용하지 않습니다."
                    )
                indiv_list = rule.get("individual_amounts") or []
                if not indiv_list:
                    raise CalculationError(f"항목 {key}: explicit_amount에 individual_amounts가 없습니다.")
                indiv_sum = 0
                for entry in indiv_list:
                    ip_name = entry.get("participant_name")
                    ip_amt = entry.get("amount")
                    if not ip_name or ip_name not in exact_shares or ip_amt is None or ip_amt < 0:
                        raise CalculationError(f"항목 {key}: individual_amounts 항목이 유효하지 않습니다.")
                    exact_shares[ip_name] = Fraction(ip_amt, 1)
                    indiv_sum += ip_amt
                if indiv_sum != net_item_amount:
                    raise CalculationError(
                        f"항목 {key}: 개인별 지정 금액 합계({indiv_sum})가 배분 대상 금액({net_item_amount})과 다릅니다."
                    )
            else:
                # method == "equal"
                for p in excluded:
                    exact_shares[p] = Fraction(0)
                for p, f_amt in fixed_map.items():
                    exact_shares[p] = Fraction(f_amt, 1)

                remaining = [
                    p for p in rule_participants if p not in excluded and p not in fixed_map
                ]
                remainder_amount = net_item_amount - sum(fixed_map.values())
                if remainder_amount < 0:
                    raise CalculationError(f"항목 {key}: 고정 합의액 합계가 배분 대상 금액을 초과합니다.")
                if remainder_amount > 0 and not remaining:
                    raise CalculationError(f"항목 {key}: 잔여 금액({remainder_amount})을 나눌 인원이 없습니다.")
                if remaining:
                    unit_fraction = Fraction(remainder_amount, len(remaining))
                    for p in remaining:
                        exact_shares[p] = unit_fraction

            # Step 2: covered_by_other를 적용해 정확한 몫(Fraction)을 이전
            covered_from_map: dict[str, list[tuple[str, Fraction]]] = {p: [] for p in rule_participants}
            for person, coverer in covers.items():
                transferred = exact_shares[person]
                exact_shares[coverer] += transferred
                exact_shares[person] = Fraction(0)
                covered_from_map[coverer].append((person, transferred))

            # Step 3: 최종 몫의 정수 부분을 구한다
            shares: dict[str, int] = {p: int(exact_shares[p]) for p in rule_participants}

            # Step 4: 남은 원 단위 금액을 확인된 유효 부담자에게 배정한다
            remainder = net_item_amount - sum(shares.values())
            remainder_payer = rule.get("remainder_payer_name")
            if remainder > 0:
                if not remainder_payer:
                    raise CalculationError(
                        f"항목 {key}: 원 단위 잔액({remainder}원)이 발생했으나 remainder_payer_name이 없습니다."
                    )
                if remainder_payer not in rule_participants or remainder_payer in excluded:
                    raise CalculationError(
                        f"항목 {key}: 잔액 부담자({remainder_payer})가 유효한 부담 대상자가 아닙니다."
                    )
                if remainder_payer in covers:
                    raise CalculationError(
                        f"항목 {key}: 잔액 부담자({remainder_payer})가 본인 몫을 타인에게 이전했으므로 잔액을 부담할 수 없습니다."
                    )
                if remainder_payer in fixed_map and not covered_from_map[remainder_payer]:
                    raise CalculationError(
                        f"항목 {key}: 잔액 부담자({remainder_payer})의 고정 합의 금액을 변경할 수 없습니다."
                    )
                shares[remainder_payer] += remainder

            # Step 5: 합계 검증 후 상세 근거와 함께 Allocation 생성
            allocated_item_sum = sum(shares.values())
            if allocated_item_sum + contrib_deduction != item_amt:
                raise CalculationError(
                    f"항목 {key}: 부담액 합계({allocated_item_sum}) + 찬조 적용액({contrib_deduction}) != 항목 원금({item_amt})"
                )

            for p in rule_participants:
                basis_parts = [
                    f"{method}; item={i_idx}",
                    f"raw={item_amt}",
                    f"contrib={contrib_deduction}",
                ]
                if p in excluded:
                    basis_parts.append("adjustment=exclude")
                elif p in fixed_map:
                    basis_parts.append(f"adjustment=fixed_amount({fixed_map[p]})")
                if p in covers:
                    basis_parts.append(f"covered_by={covers[p]}")
                if covered_from_map[p]:
                    covered_names = ",".join(src for src, _ in covered_from_map[p])
                    basis_parts.append(f"covers_for={covered_names}")
                if remainder > 0 and p == remainder_payer:
                    basis_parts.append(f"remainder=+{remainder}")

                allocations.append(
                    Allocation(
                        expense_index=e_idx,
                        item_index=i_idx,
                        participant_name=p,
                        amount=shares[p],
                        basis="; ".join(basis_parts),
                    )
                )
                participant_totals[p] += shares[p]
                net_balances[p] -= shares[p]

            expense_allocated_sum += allocated_item_sum
            expense_contrib_sum += contrib_deduction

        if item_amount_sum != total_amount:
            raise CalculationError(
                f"결제[{e_idx}] 총액({total_amount})과 항목 금액 합계({item_amount_sum})가 일치하지 않습니다."
            )
        if expense_allocated_sum + expense_contrib_sum != total_amount:
            raise CalculationError(
                f"결제[{e_idx}] 배분 합계({expense_allocated_sum}) + 찬조금({expense_contrib_sum}) != 결제 총액({total_amount})"
            )

        # 선결제자가 실제로 지불한 순수 금액(찬조금 제외분)을 잔액에 반영
        net_balances[payer] += total_amount - expense_contrib_sum

    # 송금 요청(SettlementResult) 생성 (결제자 본인 및 최종 부담액 0원인 사람 제외)
    debtors = [[p, -bal] for p, bal in net_balances.items() if bal < 0]
    creditors = [[p, bal] for p, bal in net_balances.items() if bal > 0]

    settlements: list[SettlementResult] = []
    d_idx = 0
    c_idx = 0
    while d_idx < len(debtors) and c_idx < len(creditors):
        debtor, debt_amt = debtors[d_idx]
        creditor, cred_amt = creditors[c_idx]
        transfer_amt = min(debt_amt, cred_amt)
        if transfer_amt > 0:
            settlements.append(
                SettlementResult(
                    from_participant=debtor,
                    to_participant=creditor,
                    amount=transfer_amt,
                )
            )
        debtors[d_idx][1] -= transfer_amt
        creditors[c_idx][1] -= transfer_amt
        if debtors[d_idx][1] == 0:
            d_idx += 1
        if creditors[c_idx][1] == 0:
            c_idx += 1

    return CalculationResult(
        allocations=allocations,
        settlements=settlements,
        participant_totals=participant_totals,
    )