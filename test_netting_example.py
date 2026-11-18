"""Optional independent check: run with PYTHONPATH=src python test_netting_example.py."""
from settlements.netting import net_settlements
from collections import defaultdict

original = [
    ('민수', '지수', 38000), ('민수', '철수', 44000),
    ('수빈', '민수', 20000), ('수빈', '철수', 24000),
    ('영희', '민수', 20000), ('영희', '지수', 32000),
    ('준호', '민수', 35000), ('준호', '지수', 15000),
    ('준호', '철수', 44000), ('지수', '민수', 35000),
    ('철수', '민수', 35000),
]
rows=[dict(from_participant=a,to_participant=b,amount=c) for a,b,c in original]
optimized=net_settlements(rows)

def balance(records):
    result=defaultdict(int)
    for t in records:
        result[t['from_participant']]-=t['amount']
        result[t['to_participant']]+=t['amount']
    return dict(result)

assert len(rows)==11
assert len(optimized)==5
assert sum(t['amount'] for t in optimized)==190000
assert balance(rows)==balance(optimized)
print('[OK] 11건 → 5건, 실제 송금 190,000원, 순잔액 동일')
for row in optimized: print(row)
