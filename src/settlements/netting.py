"""Deterministic netting across rounds. Original per-expense settlements remain unchanged."""
from collections import defaultdict


def net_settlements(rows):
    balances = defaultdict(int)
    for item in rows:
        t = item if isinstance(item, dict) else vars(item)
        amount = t["amount"]
        sender, receiver = t["from_participant"], t["to_participant"]
        if type(amount) is not int or amount < 0 or not sender or not receiver or sender == receiver:
            raise ValueError("유효하지 않은 송금 내역입니다.")
        balances[sender] -= amount
        balances[receiver] += amount
    debts = [[name, -value] for name, value in balances.items() if value < 0]
    credits = [[name, value] for name, value in balances.items() if value > 0]
    debts.sort(key=lambda x: (-x[1], x[0]))
    credits.sort(key=lambda x: (-x[1], x[0]))
    result = []
    i = j = 0
    while i < len(debts) and j < len(credits):
        amt = min(debts[i][1], credits[j][1])
        if amt:
            result.append({"from_participant": debts[i][0], "to_participant": credits[j][0], "amount": amt})
        debts[i][1] -= amt
        credits[j][1] -= amt
        if debts[i][1] == 0: i += 1
        if credits[j][1] == 0: j += 1
    if i != len(debts) or j != len(credits):
        raise ValueError("최적화 전후 순잔액 검증 실패")
    return result
