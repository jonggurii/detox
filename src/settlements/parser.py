"""추출, 로컬 스키마 검증, 입력 검토. 사용자 확인은 별도 단계다."""
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
import asyncio
import json
import os
import re

from jsonschema import Draft7Validator
from jsonschema.validators import extend
from pydantic import BaseModel, ConfigDict, Field, model_serializer


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = BASE_DIR / "schemas" / "request_context.schema.json"
DEFAULT_PROMPT_PATH = BASE_DIR / "prompts" / "parse_query.md"

CONTEXT_FIELDS = {
    "participants",
    "rounds",
    "expenses",
    "split_rules",
    "exceptions",
    "contributions",
    "tone",
    "relationship",
    "reminder_handling",
}

ContextValidator = extend(
    Draft7Validator,
    type_checker=Draft7Validator.TYPE_CHECKER.redefine(
        "integer",
        lambda checker, value: type(value) is int,
    ),
)


class ParserError(RuntimeError):
    pass


class ParserConfigurationError(ParserError):
    pass


class ParserAPIError(ParserError):
    pass


class OutputFormatError(ParserError):
    pass


class ManualInputRequired(ParserError):
    pass


class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    participants: list[str]
    expenses: list[dict[str, Any]]

    rounds: list[dict[str, Any]] | None = None
    split_rules: list[dict[str, Any]] | None = None
    exceptions: list[dict[str, Any]] | None = None
    contributions: list[dict[str, Any]] | None = None
    tone: str | None = None
    relationship: str | None = None
    reminder_handling: str | None = None

    @model_serializer(mode="wrap")
    def serialize_present_fields(self, handler):
        # 생략된 선택 필드를 null로 추가하지 않는다.
        # 중첩 레코드에 명시된 null은 보존한다.
        return {
            key: value
            for key, value in handler(self).items()
            if key in self.model_fields_set
        }


SettlementRequestContext = RequestContext


class ReviewIssue(BaseModel):
    code: str
    path: str
    question: str


class ParseResult(BaseModel):
    context: RequestContext
    issues: list[ReviewIssue]
    status: Literal["needs_clarification", "needs_confirmation"]
    source_text: str = Field(repr=False)
    supplied_evidence: str | None = Field(default=None, repr=False)
    prompt_version: int
    schema_sha256: str
    model: str
    attempts: int


@lru_cache(maxsize=1)
def _schema():
    schema = json.loads(
        DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8")
    )
    Draft7Validator.check_schema(schema)

    if set(schema.get("properties", {})) != CONTEXT_FIELDS:
        raise ParserConfigurationError(
            "9필드 RequestContext 스키마가 필요합니다."
        )

    return schema


def validate_context_data(data, *, schema=None):
    active = _schema() if schema is None else schema
    errors = list(ContextValidator(active).iter_errors(data))

    if errors:
        # 원문 값 대신 위치와 위반 규칙만 오류에 포함한다.
        details = [
            {
                "path": list(error.absolute_path),
                "rule": error.validator,
            }
            for error in errors[:8]
        ]
        raise OutputFormatError(
            json.dumps(details, ensure_ascii=False)
        )

    return RequestContext.model_validate(data)


@lru_cache(maxsize=1)
def load_contract():
    document = DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")

    starts = list(re.finditer(
        r"(?m)^<!-- prompt:start -->[ \t]*$",
        document,
    ))
    ends = list(re.finditer(
        r"(?m)^<!-- prompt:end -->[ \t]*$",
        document,
    ))

    if (
        len(starts) != 1
        or len(ends) != 1
        or starts[0].end() >= ends[0].start()
    ):
        raise ParserConfigurationError(
            "독립된 줄의 전송 마커 한 쌍이 필요합니다."
        )

    version = re.search(
        r"(?m)^\|\s*prompt_version\s*\|\s*(\d+)\s*\|",
        document[:starts[0].start()],
    )
    prompt = document[
        starts[0].end():ends[0].start()
    ].strip()

    if not version or prompt.count("{output_schema}") != 1:
        raise ParserConfigurationError(
            "prompt_version과 스키마 자리 한 개가 필요합니다."
        )

    prompt = prompt.replace(
        "{output_schema}",
        "response_json_schema의 RequestContext 계약을 따르세요.",
    )

    schema = _schema()
    digest = sha256(
        json.dumps(
            schema,
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()

    return prompt, schema, int(version.group(1)), digest


@lru_cache(maxsize=1)
def _client():
    # 검토 함수만 사용할 때 Gemini SDK나 API 키가 필요하지 않다.
    from dotenv import load_dotenv
    from google import genai

    load_dotenv(override=False)

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ParserConfigurationError(
            "GEMINI_API_KEY를 설정해 주세요."
        )

    return genai.Client(api_key=key)


def _generation_schema(schema):
    """정본 스키마의 API용 사본을 만든다.

    현재 프로젝트의 내부 definitions 참조를 펼친다.
    원본 파일은 수정하지 않고 사후 검증에 사용한다.
    """
    def expand(node):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            return expand(schema["definitions"][name])

        result = {
            key: value
            for key, value in node.items()
            if key not in {
                "$schema",
                "$comment",
                "definitions",
                "minLength",
            }
        }

        if "properties" in result:
            result["properties"] = {
                key: expand(value)
                for key, value in result["properties"].items()
            }

        if "items" in result:
            result["items"] = expand(result["items"])

        if None in result.get("enum", []):
            return {
                "anyOf": [
                    {
                        "type": "string",
                        "enum": [
                            value
                            for value in result["enum"]
                            if value is not None
                        ],
                    },
                    {"type": "null"},
                ],
                "description": result.get("description", ""),
            }

        return result

    return expand(schema)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OutputFormatError("JSON 중복 키")
        result[key] = value
    return result


def _reject_number(value):
    raise OutputFormatError(
        "정수 이외의 숫자는 허용하지 않습니다."
    )


def parse_and_review(
    text,
    *,
    supplied_evidence=None,
    model=None,
    client=None,
):
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > 12000
    ):
        raise ValueError(
            "발화는 공백이 아닌 1~12000자 문자열이어야 합니다."
        )

    if supplied_evidence is not None and (
        not isinstance(supplied_evidence, str)
        or len(supplied_evidence) > 24000
    ):
        raise ValueError(
            "근거는 24000자 이하 문자열이어야 합니다."
        )

    prompt, schema, version, digest = load_contract()

    if client is None:
        client = _client()

    selected = model or os.getenv("GEMINI_MODEL", "").strip()
    if not selected:
        raise ParserConfigurationError(
            "GEMINI_MODEL을 설정해 주세요."
        )

    contents = json.dumps(
        {
            "user_text": text,
            "supplied_evidence": supplied_evidence,
        },
        ensure_ascii=False,
    )

    feedback = ""

    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=selected,
                contents=contents,
                config={
                    "system_instruction": prompt + feedback,
                    "response_mime_type": "application/json",
                    "response_json_schema": _generation_schema(schema),
                    "temperature": 0,
                },
            )
        except Exception as exc:
            # API 오류를 형식 오류처럼 반복 호출하지 않는다.
            raise ParserAPIError(
                "모델 호출에 실패했습니다."
            ) from exc

        candidates = getattr(response, "candidates", None) or []
        finish = (
            getattr(candidates[0], "finish_reason", None)
            if candidates
            else None
        )
        finish = getattr(finish, "name", finish)

        if finish == "MAX_TOKENS":
            feedback = (
                "\n이전 응답이 잘렸습니다. "
                "설명 없이 완전한 JSON 객체만 반환하세요."
            )
            continue

        if finish != "STOP":
            raise ParserAPIError(
                "모델이 정상 완료 응답을 반환하지 않았습니다."
            )

        try:
            data = json.loads(
                response.text or "",
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            )
            context = validate_context_data(
                data,
                schema=schema,
            )
        except (json.JSONDecodeError, OutputFormatError):
            feedback = (
                "\n이전 응답이 JSON 또는 스키마 검사에 실패했습니다. "
                "같은 원문의 조건만 사용해 형식을 바로잡으세요."
            )
            continue

        issues = review_context(context, schema=schema)

        return ParseResult(
            context=context,
            issues=issues,
            status=(
                "needs_clarification"
                if issues
                else "needs_confirmation"
            ),
            source_text=text,
            supplied_evidence=supplied_evidence,
            prompt_version=version,
            schema_sha256=digest,
            model=selected,
            attempts=attempt,
        )

    raise ManualInputRequired(
        "응답 형식이 두 번 실패했습니다. 수동 입력으로 전환해 주세요."
    )


async def parse_settlement_query_async(text, **kwargs):
    return await asyncio.to_thread(
        parse_and_review,
        text,
        **kwargs,
    )


def parse_settlement_query(text, **kwargs):
    return parse_and_review(text, **kwargs).context


parse_settlement_request = parse_settlement_query


def review_context(
    context: RequestContext | dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> list[ReviewIssue]:
    """입력의 누락·참조·합계·충돌을 검사한다.

    빈 목록은 사용자 확인 완료를 뜻하지 않는다.
    원문 누락, 실제 신원, 찬조 전달 여부는 별도 확인이 필요하다.
    """
    data = (
        context.model_dump()
        if isinstance(context, RequestContext)
        else context
    )
    validate_context_data(data, schema=schema)

    issues: list[ReviewIssue] = []

    def add(code, path, question):
        issues.append(ReviewIssue(
            code=code,
            path=path,
            question=question,
        ))

    names = Counter(data["participants"])
    expenses = data["expenses"]

    if not names:
        add(
            "missing_participants",
            "participants",
            "이 정산에 관련된 사람들의 이름을 알려 주세요.",
        )
    if any(count > 1 for count in names.values()):
        add(
            "ambiguous_person",
            "participants",
            "중복된 이름이 같은 사람인지 동명이인인지 확인해 주세요.",
        )
    if any(not name.strip() for name in names):
        add(
            "blank_person",
            "participants",
            "공백으로 된 참여자 이름을 확인해 주세요.",
        )
    if not expenses:
        add(
            "missing_expenses",
            "expenses",
            "각 결제의 결제자·총액·비용 항목을 알려 주세요.",
        )

    def person(name, path):
        if not name or not name.strip() or names[name] != 1:
            add(
                "unresolved_person",
                path,
                "이 기록의 사람을 참여자 목록에서 명확하게 확인해 주세요.",
            )

    def target(record, path, item=True):
        ei = record.get("expense_index")
        if ei is None or not 0 <= ei < len(expenses):
            add(
                "unresolved_expense",
                path + ".expense_index",
                "이 조건이 어느 결제에 적용되는지 확인해 주세요.",
            )
            return None

        if not item:
            return ei

        ii = record.get("item_index")
        if (
            ii is None
            or not 0 <= ii < len(expenses[ei].get("items", []))
        ):
            add(
                "unresolved_item",
                path + ".item_index",
                "이 조건이 해당 결제의 어느 항목에 적용되는지 확인해 주세요.",
            )
            return None

        return ei, ii

    rounds = data.get("rounds", [])
    round_numbers = Counter(
        record["round_number"]
        for record in rounds
        if record["round_number"] is not None
    )

    for i, record in enumerate(rounds):
        path = f"rounds[{i}]"

        if (
            record["round_number"] is None
            or round_numbers[record["round_number"]] != 1
        ):
            add(
                "unresolved_round",
                path,
                "차수 번호와 중복 기록을 확인해 주세요.",
            )

        attendees = record.get("participant_names", [])
        for j, name in enumerate(attendees):
            person(name, f"{path}.participant_names[{j}]")

        if len(attendees) != len(set(attendees)):
            add(
                "duplicate_attendee",
                path,
                "같은 이름이 중복된 차수 참석 명단을 확인해 주세요.",
            )

        if (
            record.get("participant_count") is not None
            and len(set(attendees)) != record["participant_count"]
        ):
            add(
                "incomplete_attendees",
                path,
                "말한 참석 인원과 명단이 다릅니다. 전체 참석 명단을 확인해 주세요.",
            )

        for j, attendance in enumerate(record.get("attendance", [])):
            person(
                attendance["participant_name"],
                f"{path}.attendance[{j}].participant_name",
            )

    item_keys = set()

    for ei, expense in enumerate(expenses):
        path = f"expenses[{ei}]"

        person(expense["payer_name"], path + ".payer_name")

        if expense["total_amount"] is None:
            add(
                "missing_total",
                path + ".total_amount",
                "이 한 번의 결제 총액을 확인해 주세요.",
            )

        if (
            "round_number" in expense
            and round_numbers[expense["round_number"]] != 1
        ):
            add(
                "unresolved_round",
                path + ".round_number",
                "이 결제와 연결할 차수를 확인해 주세요.",
            )

        items = expense.get("items", [])

        if not items:
            add(
                "missing_items",
                path + ".items",
                "누구에게 어떤 기준으로 나눌지 구분할 비용 항목을 확인해 주세요.",
            )

        for ii, item in enumerate(items):
            item_keys.add((ei, ii))

            if (
                item["name"] is None
                or not item["name"].strip()
                or item["amount"] is None
            ):
                add(
                    "missing_item_data",
                    f"{path}.items[{ii}]",
                    "이 항목의 이름과 전체 금액을 확인해 주세요.",
                )

        if (
            items
            and all(item["amount"] is not None for item in items)
            and expense["total_amount"] is not None
        ):
            if sum(item["amount"] for item in items) != expense["total_amount"]:
                add(
                    "item_sum_mismatch",
                    path,
                    "항목 합계와 결제 총액이 다릅니다. 원본을 확인해 주세요.",
                )

        receipt = expense.get("receipt_total_amount")
        if (
            receipt is not None
            and expense["total_amount"] is not None
            and receipt != expense["total_amount"]
        ):
            add(
                "receipt_mismatch",
                path,
                "영수증에서 읽은 총액과 입력한 결제 총액을 대조해 주세요.",
            )

    rules = defaultdict(list)

    for i, rule in enumerate(data.get("split_rules", [])):
        path = f"split_rules[{i}]"
        key = target(rule, path)

        if key is not None:
            rules[key].append(rule)

        members = rule["participant_names"]

        if not members or rule["method"] is None:
            add(
                "incomplete_rule",
                path,
                "이 항목의 분담 방식과 전체 기본 부담 대상자를 확인해 주세요.",
            )

        for j, name in enumerate(members or []):
            person(name, f"{path}.participant_names[{j}]")

        if members and len(members) != len(set(members)):
            add(
                "duplicate_rule_member",
                path,
                "기본 부담 대상자 이름의 중복을 확인해 주세요.",
            )

        if "remainder_payer_name" in rule:
            person(
                rule["remainder_payer_name"],
                path + ".remainder_payer_name",
            )

        amounts = rule.get("individual_amounts", [])

        if rule["method"] == "explicit_amount":
            counts = Counter(
                row["participant_name"]
                for row in amounts
            )

            if (
                not amounts
                or members is None
                or set(counts) != set(members)
                or any(value != 1 for value in counts.values())
            ):
                add(
                    "incomplete_individual_amounts",
                    path,
                    "기본 부담 대상자마다 한 개의 소비 몫이 지정됐는지 확인해 주세요.",
                )

            for j, row in enumerate(amounts):
                person(
                    row["participant_name"],
                    f"{path}.individual_amounts[{j}]",
                )
                if row["amount"] is None:
                    add(
                        "missing_individual_amount",
                        path,
                        "각 사람의 합의된 소비 몫을 확인해 주세요.",
                    )
        elif amounts:
            add(
                "conflicting_rule",
                path,
                "개인별 지정 금액과 분담 방식의 관계를 확인해 주세요.",
            )

    for key in sorted(item_keys):
        if len(rules[key]) != 1:
            add(
                "rule_count",
                f"expenses[{key[0]}].items[{key[1]}]",
                "이 항목에 적용할 유효 분담 기준 하나를 확인해 주세요.",
            )

    adjustments = defaultdict(list)
    covers = defaultdict(list)

    for i, exception in enumerate(data.get("exceptions", [])):
        path = f"exceptions[{i}]"
        key = target(exception, path)

        person(
            exception["participant_name"],
            path + ".participant_name",
        )

        if key is not None:
            adjustments[(key, exception["participant_name"])].append(
                exception
            )

            if (
                len(rules[key]) == 1
                and rules[key][0]["participant_names"] is not None
                and exception["participant_name"]
                not in rules[key][0]["participant_names"]
            ):
                add(
                    "exception_outside_rule",
                    path,
                    "부담 조정 대상이 해당 항목의 기본 부담 대상자인지 확인해 주세요.",
                )

        kind = exception["kind"]

        if kind is None:
            add(
                "unconfirmed_adjustment",
                path,
                "조정 이유를 보고 부담 제외·합의 소비 몫·대신 부담 중 "
                "적용할 조건을 확인해 주세요.",
            )

        if kind == "fixed_amount" and exception.get("fixed_amount") is None:
            add(
                "missing_fixed_amount",
                path,
                "이 항목에서 그 사람이 부담하기로 합의한 소비 몫 전체를 확인해 주세요.",
            )

        if kind != "fixed_amount" and exception.get("fixed_amount") is not None:
            add(
                "conflicting_adjustment",
                path,
                "합의 소비 몫과 부담 조정 방식이 서로 맞는지 확인해 주세요.",
            )

        if kind == "covered_by_other":
            payer = exception.get("covered_by_name")
            person(payer, path + ".covered_by_name")

            if payer == exception["participant_name"]:
                add(
                    "self_cover",
                    path,
                    "원래 부담자와 대신 부담하는 사람이 서로 다른지 확인해 주세요.",
                )

            if key is not None and payer is not None:
                covers[key].append((
                    exception["participant_name"],
                    payer,
                ))

        elif exception.get("covered_by_name") is not None:
            add(
                "conflicting_adjustment",
                path,
                "대신 부담하는 사람과 조정 방식이 서로 맞는지 확인해 주세요.",
            )

    for (key, _), records in adjustments.items():
        if len(records) > 1:
            add(
                "duplicate_adjustment",
                f"expenses[{key[0]}].items[{key[1]}]",
                "같은 사람·항목의 여러 부담 조정을 하나의 합의로 확인해 주세요.",
            )

    for key, edges in covers.items():
        if {a for a, _ in edges} & {b for _, b in edges}:
            add(
                "cover_chain_or_cycle",
                f"expenses[{key[0]}].items[{key[1]}]",
                "대신 부담의 연쇄·순환이 있습니다. 최종 부담자를 확인해 주세요.",
            )

    applied = defaultdict(int)

    for i, contribution in enumerate(data.get("contributions", [])):
        path = f"contributions[{i}]"
        ei = target(contribution, path, item=False)

        person(
            contribution["contributor_name"],
            path + ".contributor_name",
        )

        if contribution["amount"] is None:
            add(
                "missing_contribution_amount",
                path,
                "찬조금 총액을 확인해 주세요.",
            )

        if not contribution.get("funding_note", "").strip():
            add(
                "missing_funding_note",
                path,
                "찬조금이 결제자에게 어떻게 전달되거나 충당됐는지 확인해 주세요.",
            )

        uses = contribution.get("uses", [])

        if not uses:
            add(
                "missing_contribution_uses",
                path,
                "찬조금을 어느 비용 항목에 얼마씩 적용할지 확인해 주세요.",
            )

        seen_items = set()

        for j, use in enumerate(uses):
            use_path = f"{path}.uses[{j}]"
            key = target(
                {
                    "expense_index": ei,
                    "item_index": use["item_index"],
                },
                use_path,
            )

            if key is not None:
                if key in seen_items:
                    add(
                        "duplicate_contribution_use",
                        use_path,
                        "같은 찬조금의 같은 항목 적용 기록이 중복됐는지 확인해 주세요.",
                    )

                seen_items.add(key)

                if use["amount"] is not None:
                    applied[key] += use["amount"]

            if use["amount"] is None:
                add(
                    "missing_contribution_use_amount",
                    use_path,
                    "이 항목에 적용할 찬조금 금액을 확인해 주세요.",
                )

        if (
            uses
            and contribution["amount"] is not None
            and all(use["amount"] is not None for use in uses)
        ):
            if sum(use["amount"] for use in uses) != contribution["amount"]:
                add(
                    "contribution_sum_mismatch",
                    path,
                    "항목별 적용액 합계와 찬조금 총액을 확인해 주세요.",
                )

    for key, amount in applied.items():
        item_amount = expenses[key[0]]["items"][key[1]]["amount"]

        if item_amount is not None and amount > item_amount:
            add(
                "contribution_exceeds_item",
                f"expenses[{key[0]}].items[{key[1]}]",
                "항목 금액을 넘는 찬조 적용액을 확인해 주세요.",
            )

    # 미정·참조·충돌 문제가 있으면 먼저 보완받는다.
    # 구조 검토가 통과한 뒤 정확한 몫과 잔액 조건을 검사한다.
    from .allocation_math import AllocationInputError, item_shares

    if not issues:
        for key in sorted(item_keys):
            ei, ii = key
            related = [
                exception
                for exception in data.get("exceptions", [])
                if (
                    exception["expense_index"],
                    exception["item_index"],
                ) == key
            ]

            try:
                item_shares(
                    expenses[ei]["items"][ii]["amount"] - applied[key],
                    rules[key][0],
                    related,
                )
            except AllocationInputError as exc:
                add(
                    exc.code,
                    f"expenses[{ei}].items[{ii}]",
                    str(exc),
                )

    return issues