from settlements.receipt_reconciliation import reconcile_reviewed_receipts
from settlements.parser import review_context, validate_context_data

NAMES = ['민수','지훈','영희','수빈','민지','민재','민준']
TEXT = '민수, 지훈, 영희, 수빈, 민지, 민재, 민준 7명이 먹었어. 민수가 전액 결제했고 영희는 술을 안 마셔서 술값에서 제외해 줘.'
EVIDENCE = '''[사용자가 사진과 대조하여 승인한 차수별 영수증 내역]
[1차 / 영수증 1 / first.jpg]
- 성인무한리필: 132300원
- (병)카스: 15000원
- 참이슬 후레쉬: 40000원
- 물냉면(후식): 30000원
- 계란찜: 4000원
해당 영수증 총액: 221300원'''

def context():
    return {'participants':NAMES,'rounds':[{'round_number':1,'participant_names':NAMES}], 'expenses':[{'round_number':None,'payer_name':'민수','total_amount':221300,'items':[]}], 'split_rules':[], 'exceptions':[]}

def test_single_receipt_scope_and_explicit_exclusion():
    original=context()
    result=reconcile_reviewed_receipts(original,EVIDENCE,TEXT)
    assert result['expenses'][0]['round_number']==1
    assert len(result['expenses'][0]['items'])==5
    assert {(x['item_index'],x['participant_name']) for x in result['exceptions']}=={(1,'영희'),(2,'영희')}
    assert result['split_rules']==[]  # user must choose, never guess
    assert original['expenses'][0]['items']==[]
    validate_context_data(result)

def test_restore_partial_items_without_references():
    data=context();data['expenses'][0]['items']=[{'name':'식사','amount':221300}]
    assert len(reconcile_reviewed_receipts(data,EVIDENCE,TEXT)['expenses'][0]['items'])==5

def test_preserve_referenced_items():
    data=context();data['expenses'][0]['items']=[{'name':'식사','amount':221300}]
    data['split_rules']=[{'expense_index':0,'item_index':0,'method':'equal','participant_names':NAMES}]
    assert reconcile_reviewed_receipts(data,EVIDENCE,TEXT)['expenses'][0]['items']==data['expenses'][0]['items']

def test_no_exclusion_without_request():
    assert not reconcile_reviewed_receipts(context(),EVIDENCE,'영희는 술을 안 마셨어.')['exceptions']

def test_confirmed_candidates_pass_review():
    result=reconcile_reviewed_receipts(context(),EVIDENCE,TEXT)
    result['split_rules']=[{'expense_index':0,'item_index':i,'method':'equal','participant_names':NAMES} for i in range(5)]
    assert not review_context(validate_context_data(result))

def test_single_receipt_repairs_null_round_record():
    data=context();data['rounds'][0]['round_number']=None
    result=reconcile_reviewed_receipts(data,EVIDENCE,TEXT)
    assert result['rounds'][0]['round_number']==result['expenses'][0]['round_number']==1
    assert not any(x.code=='unresolved_round' for x in review_context(validate_context_data(result)))


def test_single_receipt_without_round_record():
    data=context();data['rounds']=[]
    result=reconcile_reviewed_receipts(data,EVIDENCE,TEXT)
    assert result['rounds']==[{'round_number':1}]
    assert result['expenses'][0]['round_number']==1
    assert {(x['item_index'],x['participant_name']) for x in result['exceptions']}=={(1,'영희'),(2,'영희')}


def test_explicit_conflicting_round_not_overwritten():
    data=context();data['rounds'][0]['round_number']=2;data['expenses'][0]['round_number']=2
    result=reconcile_reviewed_receipts(data,EVIDENCE,'2차는 '+TEXT)
    assert result['expenses'][0]['round_number']==2


def test_selected_members_excluding_alcohol_exception_pass_review():
    result=reconcile_reviewed_receipts(context(),EVIDENCE,TEXT)
    result['split_rules']=[{'expense_index':0,'item_index':i,'method':'equal','participant_names':[n for n in NAMES if i not in (1,2) or n!='영희']} for i in range(5)]
    assert not review_context(validate_context_data(result))
