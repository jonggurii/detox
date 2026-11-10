"""G01~G08: YAML 기대값으로 review_context를 검사한다.

Gemini 호출 없이 다음을 검사한다.
- 확인 항목 개수
- code/path의 정확한 일치
- code/path/question의 출력 형식
- 입력 및 스키마 보존
- 지정한 다른 케이스와 결과 일치
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator

from settlements.parser import review_context


ROOT = Path(__file__).resolve().parents[1]

CASES_PATH = ROOT / "tests" / "harness" / "golden_cases.yaml"
SCHEMA_PATH = (
    ROOT
    / "src"
    / "settlements"
    / "schemas"
    / "request_context.schema.json"
)

AC_IDS = {f"AC{i}" for i in range(1, 7)}
CASE_IDS = {f"G{i:02d}" for i in range(1, 9)}

REQUIRED_KEYS = {
    "id",
    "name",
    "category",
    "ac_ids",
    "context",
    "expect_issue_count",
    "expect_issue_keys",
    "must_preserve_input",
}

OPTIONAL_KEYS = {
    "note",
    "expect_same_issue_keys_as",
}


def require(condition, message):
    if not condition:
        raise ValueError(
            f"골든 케이스 설정 오류: {message}"
        )


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def snapshot(value):
    # 일반 dict 비교에서 같다고 판단할 수 있는
    # True/1 또는 1/1.0도 구별한다.
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )


def load_cases():
    # 파일·import·YAML 오류는 수집 오류로 드러낸다.
    # 테스트를 skip하거나 빈 케이스로 바꾸지 않는다.
    with CASES_PATH.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)

    with SCHEMA_PATH.open(encoding="utf-8") as stream:
        schema = json.load(stream)

    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)

    require(
        isinstance(document, dict),
        "최상위는 객체여야 합니다.",
    )
    require(
        set(document) <= {
            "version",
            "target",
            "fixtures",
            "cases",
        },
        "알 수 없는 최상위 키",
    )
    require(
        type(document.get("version")) is int
        and document["version"] == 1,
        "version은 1이어야 합니다.",
    )
    require(
        document.get("target")
        == "settlements.parser.review_context",
        "target 불일치",
    )
    require(
        isinstance(document.get("fixtures", {}), dict),
        "fixtures는 객체여야 합니다.",
    )

    cases = document.get("cases")

    require(
        isinstance(cases, list) and len(cases) == 8,
        "G01~G08 8개가 필요합니다.",
    )

    ids = set()
    names = set()

    for index, case in enumerate(cases):
        label = f"cases[{index}]"

        require(
            isinstance(case, dict),
            f"{label}: 객체가 필요합니다.",
        )
        require(
            REQUIRED_KEYS <= set(case),
            f"{label}: 필수 키 누락",
        )
        require(
            set(case) <= REQUIRED_KEYS | OPTIONAL_KEYS,
            f"{label}: 알 수 없는 키",
        )

        for key in ("id", "name", "category"):
            require(
                nonempty_string(case[key]),
                f"{label}.{key}: 빈 문자열은 안 됩니다.",
            )

        require(
            case["id"] not in ids,
            f"중복 ID: {case['id']}",
        )
        require(
            case["name"] not in names,
            f"중복 name: {case['name']}",
        )

        ids.add(case["id"])
        names.add(case["name"])

        require(
            case["category"] in {
                "normal",
                "boundary",
                "prohibited",
            },
            f"{label}: 잘못된 category",
        )

        acs = case["ac_ids"]

        require(
            isinstance(acs, list) and bool(acs),
            f"{label}: ac_ids는 비어 있지 않은 목록",
        )
        require(
            all(
                isinstance(ac, str) and ac in AC_IDS
                for ac in acs
            ),
            f"{label}: 정의되지 않은 AC",
        )
        require(
            len(acs) == len(set(acs)),
            f"{label}: 중복 AC",
        )

        require(
            isinstance(case["context"], dict),
            f"{label}: context는 객체",
        )

        # 골든 입력 자체가 정본 스키마를 만족하는지 검사한다.
        validator.validate(case["context"])
        snapshot(case["context"])

        count = case["expect_issue_count"]
        expected = case["expect_issue_keys"]

        require(
            type(count) is int and count >= 0,
            f"{label}: 예상 개수는 0 이상 정수",
        )
        require(
            isinstance(expected, list),
            f"{label}: expect_issue_keys는 목록",
        )
        require(
            len(expected) == count,
            f"{label}: 예상 개수와 기대 목록 길이 불일치",
        )

        for pair in expected:
            require(
                isinstance(pair, dict)
                and set(pair) == {"code", "path"},
                f"{label}: code/path 쌍 필요",
            )
            require(
                all(
                    nonempty_string(pair[key])
                    for key in ("code", "path")
                ),
                f"{label}: 빈 code/path",
            )

        require(
            case["must_preserve_input"] is True,
            f"{label}: must_preserve_input은 true",
        )

        if "note" in case:
            require(
                nonempty_string(case["note"]),
                f"{label}: note는 비어 있지 않은 문자열",
            )

        if "expect_same_issue_keys_as" in case:
            require(
                nonempty_string(
                    case["expect_same_issue_keys_as"]
                ),
                f"{label}: 비교 대상 name 필요",
            )

    require(
        ids == CASE_IDS,
        "ID는 G01~G08이어야 합니다.",
    )

    for case in cases:
        if "expect_same_issue_keys_as" in case:
            reference = case["expect_same_issue_keys_as"]

            require(
                reference in names
                and reference != case["name"],
                f"{case['name']}: 잘못된 비교 대상",
            )

    return cases, schema


CASES, SCHEMA = load_cases()
BY_NAME = {
    case["name"]: case
    for case in CASES
}


def run_and_check(case):
    # YAML 앵커로 공유된 객체가 다른 케이스에 영향을 주지 않게 한다.
    context = deepcopy(case["context"])
    schema = deepcopy(SCHEMA)

    before = snapshot(context)
    schema_before = snapshot(schema)

    try:
        result = review_context(
            context,
            schema=schema,
        )
    finally:
        # 함수가 예외를 내더라도 입력 변경 여부를 검사한다.
        assert snapshot(context) == before, (
            f"{case['id']}: 입력이 변경됐습니다."
        )
        assert snapshot(schema) == schema_before, (
            f"{case['id']}: 스키마가 변경됐습니다."
        )

    assert isinstance(result, list), (
        f"{case['id']}: 결과는 목록이어야 합니다."
    )

    actual = []

    for index, issue in enumerate(result):
        # ReviewIssue 객체 또는 같은 필드를 갖는 dict를 검사한다.
        # 문자열 목록은 여기서 실패한다.
        if isinstance(issue, dict):
            row = issue
        else:
            row = {
                field: getattr(issue, field, None)
                for field in ("code", "path", "question")
            }

        for field in ("code", "path", "question"):
            assert nonempty_string(row.get(field)), (
                f"{case['id']}: issues[{index}].{field}는 "
                "비어 있지 않은 문자열이어야 합니다."
            )

        actual.append((
            row["code"],
            row["path"],
        ))

    # set으로 바꾸지 않는다.
    # 동일한 오류가 중복 반환되는 결함도 검출해야 한다.
    actual = sorted(actual)
    expected = sorted(
        (row["code"], row["path"])
        for row in case["expect_issue_keys"]
    )

    assert len(result) == case["expect_issue_count"], (
        f"{case['id']}: "
        f"기대 개수={case['expect_issue_count']}, "
        f"실제={len(result)}, "
        f"결과={actual}"
    )

    assert actual == expected, (
        f"{case['id']}: "
        f"기대={expected}, "
        f"실제={actual}"
    )

    return actual


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[case["name"] for case in CASES],
)
def test_context_review_golden(case):
    actual = run_and_check(case)

    reference = case.get("expect_same_issue_keys_as")

    if reference is not None:
        # 실행 순서와 무관하게 새 복사본으로 비교 대상을 검사한다.
        reference_actual = run_and_check(
            BY_NAME[reference]
        )

        assert actual == reference_actual