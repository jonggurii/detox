"""Safely enhance parser prompts and retry missing split rules (whitespace-tolerant)."""
from pathlib import Path
import ast
import re
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("사용법: python tools/patch_parser.py src/settlements/parser.py")
p = Path(sys.argv[1]).resolve()
s = p.read_text(encoding="utf-8")
if "extraction_guidance =" in s:
    raise SystemExit("이미 패치된 parser.py로 보입니다. 중복 적용하지 않았습니다.")

# Match the real code structure, not an exact number of blank lines.
first = re.search(r'(?m)^(?P<indent>[ \t]*)feedback = ""[ \t]*\n(?:(?:[ \t]*\n)*)[ \t]*for attempt in \(1, 2\):', s)
second = re.search(r'(?m)^(?P<indent>[ \t]*)issues = review_context\(context, schema=schema\)[ \t]*\n(?:(?:[ \t]*\n)*)[ \t]*return ParseResult\(', s)
if not first or not second:
    raise SystemExit("패치 위치를 찾지 못했습니다. 원본을 변경하지 않았습니다. parser.py를 다시 확인해 주세요.")
if len(first.group('indent')) != 4 or len(second.group('indent')) != 8:
    raise SystemExit("예상하지 못한 함수 들여쓰기입니다. 원본을 변경하지 않았습니다.")

guidance = """
정산 분담 규칙 추출 지침:
- expenses의 각 items 항목에 대해 split_rules를 각각 생성하려고 시도하세요.
- 'A와 B만', 'C를 빼고', 'A와 B 각각' 등 원문에 명시된 부담 대상을 반영하세요.
- 분담 방식이 균등하다고 명시되거나 명확히 합의된 경우에만 method=equal을 사용하세요.
- 개인별 금액이 명시된 경우 method=explicit_amount 및 individual_amounts를 사용하세요.
- 대상자나 방식이 불명확하면 추측하지 말고 method=null 또는 participant_names=null로 남겨 확인을 받으세요.
- payer_name은 실제 선결제자가 명시된 경우에만 기입하세요. 먹은 사람과 결제자는 다릅니다.
- 차수가 언급되지 않았다면 rounds를 억지로 생성할 필요가 없습니다.
- 원문의 항목·총액·인원·예외를 빠뜨리지 마세요.
"""

first_replacement = '    extraction_guidance = ' + repr(guidance) + '\n    feedback = extraction_guidance\n\n    for attempt in (1, 2):'
second_replacement = """        issues = review_context(context, schema=schema)

        # Retry once if a model response omitted item-level rules.
        if attempt == 1 and any(issue.code == "rule_count" for issue in issues):
            feedback = extraction_guidance + (
                "\\n이전 결과에서 일부 items의 split_rules가 누락되었습니다. "
                "원문에 근거해 항목마다 정확히 하나의 규칙을 작성하세요. "
                "불명확한 method/participant_names는 null로 남기세요. "
                "결제자를 임의 지정하지 마세요."
            )
            continue

        return ParseResult("""
# Apply later span first so offsets remain valid.
s = s[:second.start()] + second_replacement + s[second.end():]
s = s[:first.start()] + first_replacement + s[first.end():]
ast.parse(s)
backup = p.with_suffix(".py.before_rule_fix.bak")
if backup.exists():
    raise SystemExit(f"기존 백업이 있어 중단했습니다: {backup}")
shutil.copy2(p, backup)
p.write_text(s, encoding="utf-8")
print(f"완료: {p} / 백업: {backup}")
