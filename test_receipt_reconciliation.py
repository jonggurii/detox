"""Run with: python -m pytest test_receipt_reconciliation.py -q"""
from receipt_reconciliation import reconcile_reviewed_receipts

NAMES = ['민수','철수','영희','지수','준호','수빈','현우']
TEXT = '''총 2차에 걸쳐 모임을 진행했어.
1차는 첫 번째 영수증이고, 총 221,300원이 나왔어. 민수, 철수, 영희, 지수, 준호, 수빈, 현우 총 7명이 참여했어. 이 중 영희와 수빈은 술을 마시지 않았기 때문에 1차 술값에서는 제외하고, 나머지 음식값은 7명이 똑같이 나눠줘.
2차는 두 번째 영수증이고, 총 250,000원이 나왔어. 1차에 참여했던 사람 중 지수와 수빈은 집에 가서, 민수, 철수, 영희, 준호, 현우 총 5명만 참여했어. 2차에서는 모두 동일하게 비용을 나눠줘.
민수가 1차와 2차 비용을 모두 결제했으니, 각 차수별 정산 금액과 사람별 최종 정산 금액을 계산해줘.'''
EVIDENCE = '''[사용자가 사진과 대조하여 승인한 차수별 영수증 내역]
각 영수증은 독립된 결제입니다. 차수별 합계는 참고용이며 별도 결제가 아닙니다.
[1차 / 영수증 1 / first.jpg]
- 성인무한리필: 132300원
- (병)카스: 15000원
- 참이슬 후레쉬: 40000원
- 물냉면(후식): 30000원
- 계란찜: 4000원
해당 영수증 총액: 221300원
[2차 / 영수증 2 / second.jpg]
- 1.한우모듬: 210000원
- 2.한우육회(소): 20000원
- 3.공기밥: 3000원
- 4.음료수: 6000원
- 5.된장(후식): 6000원
- 6.석읆냉면(후식): 5000원
해당 영수증 총액: 250000원
1차 영수증 합계: 221300원
2차 영수증 합계: 250000원'''

def data():
    return {'participants':NAMES, 'rounds':[
      {'round_number':1,'participant_names':NAMES,'participant_count':7},
      {'round_number':2,'participant_names':['민수','철수','영희','준호','현우'],'participant_count':5}],
      'expenses':[{'round_number':1,'payer_name':'민수','total_amount':221300,'items':[]},
                  {'round_number':2,'payer_name':'민수','total_amount':250000,'items':[]}],
      'split_rules':[], 'exceptions':[]}

def test_receipt_items_and_explicit_splits():
    result=reconcile_reviewed_receipts(data(), EVIDENCE, TEXT)
    assert list(map(lambda expense:len(expense['items']),result['expenses']))==[5,6]
    assert len(result['split_rules'])==11
    assert {(x['participant_name'],x['item_index']) for x in result['exceptions']} == {
        ('영희',1),('영희',2),('수빈',1),('수빈',2)}
    assert sum(item['amount'] for expense in result['expenses'] for item in expense['items'])==471300

def test_unmatched_receipt_does_not_invent_items():
    item=data()
    item['expenses'][0]['total_amount']=221301
    result=reconcile_reviewed_receipts(item,EVIDENCE,TEXT)
    assert result['expenses'][0]['items']==[]
    assert not any(rule['expense_index']==0 for rule in result['split_rules'])

def test_ambiguity_does_not_apply_equal_split_without_attendee_list():
    item=data()
    item['rounds'][0]['participant_names']=[]
    result=reconcile_reviewed_receipts(item,EVIDENCE,TEXT)
    assert result['expenses'][0]['items']
    assert not any(rule['expense_index']==0 for rule in result['split_rules'])

def test_exclusions_not_inferred_without_explicit_instruction():
    result=reconcile_reviewed_receipts(data(),EVIDENCE,TEXT.replace('1차 술값에서는 제외하고','1차 술값도 나눠야 하고'))
    assert not result['exceptions']
