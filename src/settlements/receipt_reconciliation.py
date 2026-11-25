"""Conservative reconstruction of user-reviewed receipt items and explicit equal splits.

Never invent items, amounts, attendees, or match ambiguous receipts. This runs
only after Gemini has returned schema-valid RequestContext data.
"""
import re
from collections import Counter

HEADER = re.compile(r'^\[(\d+)차 / 영수증 \d+ / [^\n]+\]$', re.M)
ITEM = re.compile(r'^- (.+): (\d+)원$', re.M)
TOTAL = re.compile(r'^해당 영수증 총액: (\d+)원$', re.M)
ALCOHOL = re.compile(r'카스|참이슬|처음처럼|소주|맥주|막걸리|청하|하이트|테라|켈리|클라우드|와인|위스키|하이볼|주류|술', re.I)


def _receipts(evidence):
    if not isinstance(evidence, str) or '[사용자가 사진과 대조하여 승인한 차수별 영수증 내역]' not in evidence:
        return []
    heads = list(HEADER.finditer(evidence))
    found = []
    for i, match in enumerate(heads):
        section = evidence[match.end(): heads[i+1].start() if i+1 < len(heads) else len(evidence)]
        # Stop at the matching total; never read next round's aggregate.
        total = TOTAL.search(section)
        if not total:
            continue
        items = [{'name': name.strip(), 'amount': int(amount)} for name, amount in ITEM.findall(section[:total.start()])]
        value = int(total.group(1))
        if not items or sum(x['amount'] for x in items) != value:
            continue
        found.append({'round': int(match.group(1)), 'total': value, 'items': items})
    return found


def _round_segment(text, round_number):
    # Only explicit round-introduction phrases mark boundaries. A later
    # reference like "1차 술값" must NOT end the current round's paragraph.
    matches = list(re.finditer(r'(?<!\d)(\d+)차(?:는|에서는|에는)', text))
    for i, match in enumerate(matches):
        if int(match.group(1)) == round_number:
            end = next((m.start() for m in matches[i+1:]
                        if int(m.group(1)) != round_number), len(text))
            return text[match.start():end]
    return ''


def _excluded_names(text, known_names, round_number, single=False):
    # Exclusion must be explicit and refer to this round's alcohol expense;
    # do not treat 'did not drink' alone as a bill-splitting agreement.
    segment = _round_segment(text, round_number) or (text if single else "")
    if not segment:
        return []
    selected = []
    clauses = re.split(r'[.\n]|결제했고|결제하였고|냈고', segment)
    for clause in clauses:
        if not ('술값' in clause or '주류' in clause):
            continue
        if not re.search(r'제외|안\s*내|부담하지', clause):
            continue
        # Specifically identify names, not all attendees or a guessed count.
        matched = [name for name in known_names if re.search(r'(?<![가-힣])'+re.escape(name), clause)]
        selected.extend(matched)
    return list(dict.fromkeys(selected))


def reconcile_reviewed_receipts(data, evidence, user_text):
    """Return schema-compatible dict; preserve data unchanged if uncertain.

    Auto-build equal rules only where a complete participant list, explicit
    whole-round equal direction, and unambiguous reviewed receipts are present.
    """
    import copy
    receipts = _receipts(evidence)
    if not receipts or not isinstance(data, dict):
        return data
    result = copy.deepcopy(data)
    expenses = result.get('expenses', [])
    rounds = {r.get('round_number'): r for r in (result.get('rounds') or []) if isinstance(r, dict)}
    # Only a single verified receipt and a single compatible expense permit
    # implicit round binding. Never override a conflicting explicit round.
    single = len(receipts) == len(expenses) == 1 and len(rounds) == 1
    if single:
        receipt, expense = receipts[0], expenses[0]
        if expense.get('round_number') is None and expense.get('total_amount') == receipt['total'] and receipt['round'] in rounds:
            expense['round_number'] = receipt['round']
    # Match by verified (round, total); prevent ambiguous many-to-many matches.
    rc = Counter((r['round'], r['total']) for r in receipts)
    ec = Counter((e.get('round_number'), e.get('total_amount')) for e in expenses)
    matched = {}
    for ei, expense in enumerate(expenses):
        key = (expense.get('round_number'), expense.get('total_amount'))
        if rc[key] != 1 or ec[key] != 1:
            continue
        receipt = next(r for r in receipts if (r['round'], r['total']) == key)
        old_items = expense.get('items') or []
        # Do not overwrite contradictory nonempty LLM items without a safe
        # one-to-one mapping for references. Empty items are safe to restore.
        if old_items and old_items != receipt['items']:
            # Restore only if no positional references can be corrupted.
            refs = [x for k in ('split_rules','exceptions','contributions') for x in result.get(k, []) if x.get('expense_index') in (None, ei)]
            if refs:
                continue
            expense['items'] = copy.deepcopy(receipt['items'])
        if not old_items:
            expense['items'] = copy.deepcopy(receipt['items'])
        expense['receipt_total_amount'] = receipt['total']
        matched[ei] = receipt

    for ei, receipt in matched.items():
        round_number = receipt['round']
        current_round = rounds.get(round_number) or {}
        attendees = current_round.get('participant_names') or []
        if not attendees or len(attendees) != len(set(attendees)):
            continue
        if current_round.get('participant_count') is not None and len(attendees) != current_round['participant_count']:
            continue
        if any(n not in result.get('participants', []) for n in attendees):
            continue
        section = _round_segment(user_text, round_number) or (user_text if single else "")
        if not section:
            continue
        existing_rules = result.get('split_rules') or []
        existing_exceptions = result.get('exceptions') or []
        all_equal = bool(re.search(r'모두\s*동일하게|모두\s*똑같이|전원\s*균등|전체\s*균등', section))
        split_food = bool(re.search(r'나머지\s*음식값은?\s*\d+명이\s*똑같이|나머지\s*음식값은?\s*\d+명이\s*균등', section))
        excluded = _excluded_names(user_text, attendees, round_number, single)
        alcohol_explicit = bool(excluded and '술값' in section and re.search(r'술값.{0,30}제외|술값에서는\s*제외', section))
        if not all_equal and not (split_food and alcohol_explicit):
            # Explicit alcohol exclusion is known; food allocation remains a
            # user choice. Preserve any existing rules and unrelated exceptions.
            if alcohol_explicit:
                for ii, item in enumerate(receipt['items']):
                    if not ALCOHOL.search(item['name']):
                        continue
                    for name in excluded:
                        related = [x for x in existing_exceptions if x.get('expense_index') == ei and x.get('item_index') == ii and x.get('participant_name') == name]
                        if not related and not any(x.get('expense_index') is None or (x.get('expense_index') == ei and x.get('item_index') is None) for x in existing_exceptions):
                            result.setdefault('exceptions', []).append({'expense_index':ei,'item_index':ii,'participant_name':name,'kind':'exclude','reason':'사용자 명시 술값 제외'})
            continue
        if all_equal and excluded:
            # Explicit exceptions would make 'everyone equal' ambiguous.
            continue
        drinks = [bool(ALCOHOL.search(item['name'])) for item in receipt['items']]
        if split_food and not any(drinks):
            continue
        if split_food and any(name not in attendees for name in excluded):
            continue
        # Only rewrite when no unrelated non-equal rules/adjustments on this
        # expense. Do not erase fixed amounts or paid-by-other instructions.
        old_rules = [r for r in existing_rules if r.get('expense_index') == ei]
        old_exceptions = [x for x in existing_exceptions if x.get('expense_index') == ei]
        if any(r.get('method') not in (None, 'equal') for r in old_rules):
            continue
        if any(x.get('kind') not in ('exclude', None) for x in old_exceptions):
            continue
        if result.get('contributions') and any(c.get('expense_index') == ei for c in result['contributions']):
            continue
        # A rule/exception directed to an unknown expense may still belong to
        # this round: avoid silently dropping it.
        if any(r.get('expense_index') is None for r in existing_rules):
            continue
        if any(x.get('expense_index') is None for x in existing_exceptions):
            continue
        result['split_rules'] = [r for r in existing_rules if r.get('expense_index') != ei]
        result['exceptions'] = [x for x in existing_exceptions if x.get('expense_index') != ei]
        for ii, item in enumerate(receipt['items']):
            result['split_rules'].append({
                'expense_index': ei, 'item_index': ii, 'method': 'equal',
                'participant_names': list(attendees),
                'basis_note': f'{round_number}차 사용자 명시 균등 분할: {item["name"]}',
            })
            if drinks[ii] and split_food:
                for name in excluded:
                    result['exceptions'].append({
                        'expense_index': ei, 'item_index': ii,
                        'participant_name': name, 'kind': 'exclude',
                        'reason': f'{round_number}차 술값에서 {name} 제외(사용자 명시)',
                    })
    return result
