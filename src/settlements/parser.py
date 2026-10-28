from __future__ import annotations

from fractions import Fraction
import json
import os
from pathlib import Path
import re
from typing import Any, Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schemas" / "request_context.schema.json"
PROMPT_PATH = BASE_DIR / "prompts" / "parse_query.md"

SHORT_SCHEMA_GUIDE = (
    "응답은 response_json_schema로 전달된 RequestContext(최상위 9필드 계약) "
    "규격을 엄격히 따르는 단일 JSON 객체여야 한다."
)


# ==========================================
# 1. 9필드 RequestContext Pydantic 스키마
# ==========================================
class Attendance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_name: str | None = Field(default=None, min_length=1)
    note: str = Field(min_length=1)


class Round(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_number: int | None = Field(default=None, ge=1)
    participant_count: int | None = Field(default=None, ge=1)
    participant_names: list[str] | None = None
    attendance: list[Attendance] | None = None
    source_note: str | None = Field(default=None, min_length=1)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    amount: int | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, min_length=1)
    occurrence_note: str | None = Field(default=None, min_length=1)


class Expense(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_amount: int | None = Field(default=None, ge=0)
    payer_name: str | None = Field(default=None, min_length=1)
    round_number: int | None = Field(default=None, ge=1)
    description: str | None = Field(default=None, min_length=1)
    items: list[Item] | None = None
    receipt_total_amount: int | None = Field(default=None, ge=0)
    source_note: str | None = Field(default=None, min_length=1)


class IndividualAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_name: str | None = Field(default=None, min_length=1)
    amount: int | None = Field(default=None, ge=0)


class SplitRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_index: int | None = Field(default=None, ge=0)
    item_index: int | None = Field(default=None, ge=0)
    method: Literal["equal", "explicit_amount"] | None = None
    participant_names: list[str] | None = None
    individual_amounts: list[IndividualAmount] | None = None
    remainder_payer_name: str | None = Field(default=None, min_length=1)
    basis_note: str | None = Field(default=None, min_length=1)


class ItemException(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_index: int | None = Field(default=None, ge=0)
    item_index: int | None = Field(default=None, ge=0)
    participant_name: str | None = Field(default=None, min_length=1)
    kind: Literal["exclude", "fixed_amount", "covered_by_other"] | None = None
    fixed_amount: int | None = Field(default=None, ge=0)
    covered_by_name: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)


class ContributionUse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_index: int | None = Field(default=None, ge=0)
    amount: int | None = Field(default=None, ge=1)
    basis_note: str | None = Field(default=None, min_length=1)


class Contribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_index: int | None = Field(default=None, ge=0)
    contributor_name: str | None = Field(default=None, min_length=1)
    amount: int | None = Field(default=None, ge=1)
    uses: list[ContributionUse] | None = None
    funding_note: str | None = Field(default=None, min_length=1)


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participants: list[str] = Field(default_factory=list)
    rounds: list[Round] | None = None
    expenses: list[Expense] = Field(default_factory=list)
    split_rules: list[SplitRule] | None = None
    exceptions: list[ItemException] | None = None
    contributions: list[Contribution] | None = None
    tone: str | None = Field(default=None, min_length=1)
    relationship: str | None = Field(default=None, min_length=1)
    reminder_handling: (
        Literal["undecided", "personal_follow_up", "external_service_only"] | None
    ) = None


# 하위 호환 별칭 유지
SettlementRequestContext = RequestContext


# ==========================================
# 2. 프롬프트 및 스키마 로더
# ==========================================
def load_contract(
    prompt_path: Path = PROMPT_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> tuple[str, dict[str, Any], int]:
    """parse_query.md의 전송 마커 구간과 request_context.schema.json을 읽는다."""
    raw_md = prompt_path.read_text(encoding="utf-8")

    version_match = re.search(r"^\|\s*prompt_version\s*\|\s*(\d+)\s*\|", raw_md, re.MULTILINE)
    if not version_match:
        raise ValueError("프롬프트 문서에서 '| prompt_version | N |' 표를 찾을 수 없습니다.")
    prompt_version = int(version_match.group(1))

    start_marker = "<!-- prompt:start -->"
    end_marker = "<!-- prompt:end -->"
    if start_marker not in raw_md or end_marker not in raw_md:
        raise ValueError("프롬프트 문서에서 <!-- prompt:start --> 또는 <!-- prompt:end --> 마커를 찾을 수 없습니다.")

    system_prompt = raw_md.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
    system_prompt = system_prompt.replace("{output_schema}", SHORT_SCHEMA_GUIDE)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return system_prompt, schema, prompt_version


def parse_settlement_query(text: str, model: str = "gemini-2.5-flash") -> RequestContext:
    system_prompt, schema, _ = load_contract()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    response = client.models.generate_content(
        model=model,
        contents=text,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
            "temperature": 0.0,
        },
    )
    raw_data = json.loads(response.text)
    return RequestContext.model_validate(raw_data)


parse_settlement_request = parse_settlement_query


# ==========================================
# 3. 의미 검증 및 확인 항목 도출 (review_context)
# ==========================================
def _to_dict(context: RequestContext | dict[str, Any]) -> dict[str, Any]:
    if isinstance(context, BaseModel):
        return context.model_dump(exclude_none=False)
    return dict(context)


def review_context(context: RequestContext | dict[str, Any]) -> list[str]:
    """
    RequestContext의 의미 검증을 수행하고 사용자 확인이 필요한 항목 목록을 반환한다.
    계산 결과나 송금 요청은 생성하지 않는다.
    """
    data = _to_dict(context)
    issues: list[str] = []

    participants = data.get("participants") or []
    expenses = data.get("expenses") or []
    split_rules = data.get("split_rules") or []
    exceptions = data.get("exceptions") or []
    contributions = data.get("contributions") or []

    if not participants:
        issues.append("참여자 명단(participants)이 비어 있습니다.")
    if not expenses:
        issues.append("결제 내역(expenses)이 비어 있습니다.")

    # 찬조금 검증 및 항목별 찬조 적용액 집계
    item_contributions: dict[tuple[int, int], int] = {}
    for c_idx, contrib in enumerate(contributions):
        exp_idx = contrib.get("expense_index")
        amount = contrib.get("amount")
        uses = contrib.get("uses") or []

        if exp_idx is None or not (0 <= exp_idx < len(expenses)):
            issues.append(f"찬조금[{c_idx}]의 대상 결제(expense_index)가 미정이거나 범위를 벗어났습니다.")
        if amount is None:
            issues.append(f"찬조금[{c_idx}]의 총액(amount)이 미정입니다.")
        if not contrib.get("funding_note"):
            issues.append(f"찬조금[{c_idx}]의 전달·충당 방식(funding_note) 확인이 필요합니다.")
        if not uses:
            issues.append(f"찬조금[{c_idx}]을 어느 항목에 얼마 적용할지(uses) 확인이 필요합니다.")
        else:
            use_sum = 0
            for u_idx, use in enumerate(uses):
                u_item_idx = use.get("item_index")
                u_amount = use.get("amount")
                if u_item_idx is None or u_amount is None:
                    issues.append(f"찬조금[{c_idx}]의 적용 내역[{u_idx}]에 미정 값이 있습니다.")
                else:
                    use_sum += u_amount
                    if exp_idx is not None:
                        key = (exp_idx, u_item_idx)
                        item_contributions[key] = item_contributions.get(key, 0) + u_amount
            if amount is not None and use_sum != amount:
                issues.append(f"찬조금[{c_idx}] 총액({amount})과 항목별 적용 합계({use_sum})가 일치하지 않습니다.")

    # 결제 및 항목 합계 검사
    for e_idx, exp in enumerate(expenses):
        total_amount = exp.get("total_amount")
        payer_name = exp.get("payer_name")
        items = exp.get("items") or []

        if total_amount is None:
            issues.append(f"결제[{e_idx}]의 총액(total_amount)이 미정입니다.")
        if not payer_name:
            issues.append(f"결제[{e_idx}]의 결제자(payer_name)가 미정입니다.")
        if not items:
            issues.append(f"결제[{e_idx}]의 세부 항목(items)이 없습니다.")
        else:
            item_sum = 0
            for i_idx, item in enumerate(items):
                if item.get("name") is None or item.get("amount") is None:
                    issues.append(f"결제[{e_idx}] 항목[{i_idx}]의 이름 또는 금액이 미정입니다.")
                else:
                    item_sum += item["amount"]
            if total_amount is not None and all(i.get("amount") is not None for i in items):
                if item_sum != total_amount:
                    issues.append(f"결제[{e_idx}] 총액({total_amount})과 항목 금액 합계({item_sum})가 불일치합니다.")

    # 예외(exceptions) 검증 및 인덱싱
    item_exceptions: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ex_idx, ex in enumerate(exceptions):
        exp_idx = ex.get("expense_index")
        item_idx = ex.get("item_index")
        kind = ex.get("kind")
        p_name = ex.get("participant_name")

        if exp_idx is None or item_idx is None:
            issues.append(f"예외[{ex_idx}]의 대상 결제/항목 인덱스가 미정입니다.")
            continue
        if not (0 <= exp_idx < len(expenses)):
            issues.append(f"예외[{ex_idx}]의 expense_index({exp_idx})가 범위를 벗어났습니다.")
            continue
        exp_items = expenses[exp_idx].get("items") or []
        if not (0 <= item_idx < len(exp_items)):
            issues.append(f"예외[{ex_idx}]의 item_index({item_idx})가 범위를 벗어났습니다.")
            continue
        if not p_name or kind is None:
            issues.append(f"예외[{ex_idx}]의 대상자 또는 조정 방식(kind)이 미정입니다.")
            continue
        if kind == "fixed_amount" and ex.get("fixed_amount") is None:
            issues.append(f"예외[{ex_idx}]의 합의 소비 몫(fixed_amount)이 미정입니다.")
        if kind == "covered_by_other" and not ex.get("covered_by_name"):
            issues.append(f"예외[{ex_idx}]의 대신 부담자(covered_by_name)가 미정입니다.")

        item_exceptions.setdefault((exp_idx, item_idx), []).append(ex)

    # 분담 규칙(split_rules) 및 SPEC 5.4 순서에 따른 잔액 검사
    for r_idx, rule in enumerate(split_rules):
        exp_idx = rule.get("expense_index")
        item_idx = rule.get("item_index")
        method = rule.get("method")
        rule_participants = rule.get("participant_names")

        if exp_idx is None or item_idx is None:
            issues.append(f"분담 규칙[{r_idx}]의 대상 결제/항목 인덱스가 미정입니다.")
            continue
        if not (0 <= exp_idx < len(expenses)):
            issues.append(f"분담 규칙[{r_idx}]의 expense_index({exp_idx})가 범위를 벗어났습니다.")
            continue
        exp_items = expenses[exp_idx].get("items") or []
        if not (0 <= item_idx < len(exp_items)):
            issues.append(f"분담 규칙[{r_idx}]의 item_index({item_idx})가 범위를 벗어났습니다.")
            continue
        if method is None or not rule_participants:
            issues.append(f"분담 규칙[{r_idx}]의 방식(method) 또는 기본 부담 대상자(participant_names)가 미정입니다.")
            continue

        item_amount = exp_items[item_idx].get("amount")
        if item_amount is None:
            continue

        net_item_amount = item_amount - item_contributions.get((exp_idx, item_idx), 0)
        ex_list = item_exceptions.get((exp_idx, item_idx), [])

        if method == "equal":
            excluded = {
                ex["participant_name"]
                for ex in ex_list
                if ex.get("kind") == "exclude" and ex.get("participant_name")
            }
            fixed_map = {
                ex["participant_name"]: ex["fixed_amount"]
                for ex in ex_list
                if ex.get("kind") == "fixed_amount"
                and ex.get("participant_name")
                and ex.get("fixed_amount") is not None
            }
            covers = {
                ex["participant_name"]: ex["covered_by_name"]
                for ex in ex_list
                if ex.get("kind") == "covered_by_other"
                and ex.get("participant_name")
                and ex.get("covered_by_name")
            }

            remaining_people = [
                p for p in rule_participants if p not in excluded and p not in fixed_map
            ]
            remainder_amount = net_item_amount - sum(fixed_map.values())

            if remainder_amount < 0:
                issues.append(f"분담 규칙[{r_idx}]의 고정 부담액 합계가 배분할 항목 금액을 초과합니다.")
                continue
            if remainder_amount > 0 and not remaining_people:
                issues.append(f"분담 규칙[{r_idx}]에서 남은 금액({remainder_amount})을 균등 분담할 인원이 없습니다.")
                continue

            # 1. Fraction으로 개인별 정확한 소비 몫 계산
            exact_shares: dict[str, Fraction] = {p: Fraction(0) for p in rule_participants}
            for p, f_amt in fixed_map.items():
                exact_shares[p] = Fraction(f_amt, 1)
            if remaining_people:
                equal_share = Fraction(remainder_amount, len(remaining_people))
                for p in remaining_people:
                    exact_shares[p] = equal_share

            # 2. 대신 부담(covered_by_other)을 먼저 이전
            for target_p, coverer_p in covers.items():
                if target_p in exact_shares and coverer_p in exact_shares:
                    exact_shares[coverer_p] += exact_shares[target_p]
                    exact_shares[target_p] = Fraction(0)

            # 3. 최종 몫의 정수 부분 합산 후 원 단위 잔액 발생 여부 확인
            int_sum = sum(int(share) for share in exact_shares.values())
            rounding_remainder = net_item_amount - int_sum
            remainder_payer = rule.get("remainder_payer_name")

            if rounding_remainder > 0:
                if not remainder_payer:
                    issues.append(
                        f"분담 규칙[{r_idx}]에서 원 단위 잔액({rounding_remainder}원)이 발생하므로 "
                        "잔액 부담자(remainder_payer_name) 지정이 필요합니다."
                    )
                else:
                    # 지정한 잔액 부담자가 실제로 잔액을 부담할 수 있는 유효 대상인지 검사
                    if remainder_payer not in rule_participants or remainder_payer in excluded:
                        issues.append(
                            f"분담 규칙[{r_idx}]의 잔액 부담자({remainder_payer})가 유효한 부담 대상자가 아닙니다."
                        )
                    elif remainder_payer in covers:
                        issues.append(
                            f"분담 규칙[{r_idx}]의 잔액 부담자({remainder_payer})는 본인 몫을 다른 사람에게 이전했으므로 잔액을 부담할 수 없습니다."
                        )
                    elif remainder_payer in fixed_map and remainder_payer not in covers.values():
                        issues.append(
                            f"분담 규칙[{r_idx}]의 잔액 부담자({remainder_payer})는 고정 금액 합의자이므로 잔액을 추가 배정할 수 없습니다."
                        )

    return issues