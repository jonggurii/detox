#!/usr/bin/env python3
"""Make settlement review issues explain the actual condition and candidate items.
Run from project root: python install_specific_issue_guidance.py
Only changes mobile/src/app/index.tsx; makes a timestamped backup.
"""
from pathlib import Path
from datetime import datetime
import sys
import shutil

ROOT = Path.cwd()
FRONT = ROOT / 'mobile/src/app/index.tsx'
START = ' const describeIssue=(issue:any)=>{'
END = ' const IssueResolver=({issue,index}:{issue:any;index:number})=>{'
NEW = r''' const describeIssue=(issue:any)=>{
  const path=String(issue.path||'');
  const code=String(issue.code||'');
  const indexOf=(section:string)=>{
   const m=path.match(/^(split_rules|exceptions|contributions|expenses|rounds|participants)\[(\d+)\]/);
   return m&&m[1]===section?Number(m[2]):-1;
  };
  const ri=indexOf('split_rules');
  const xi=indexOf('exceptions');
  const ci=indexOf('contributions');
  const ei=indexOf('expenses');
  const roundIndex=indexOf('rounds');
  const rule=ri>=0?ctx.split_rules?.[ri]:null;
  const exception=xi>=0?ctx.exceptions?.[xi]:null;
  const contribution=ci>=0?ctx.contributions?.[ci]:null;
  const condition=rule||exception||contribution||null;
  const rawExpenseIndex=ei>=0?ei:condition?.expense_index;
  const expenseIndex=Number.isInteger(rawExpenseIndex)&&rawExpenseIndex>=0?rawExpenseIndex:null;
  const expense=expenseIndex!==null?ctx.expenses?.[expenseIndex]:null;
  const rawRound=expense?.round_number??(roundIndex>=0?ctx.rounds?.[roundIndex]?.round_number:null);
  const roundNumber=Number.isInteger(rawRound)&&rawRound>=1?rawRound:null;
  const roundLabel=roundNumber!==null?`${roundNumber}차`:(expenseIndex!==null?`${expenseIndex+1}번째 결제 (차수 미확인)`:'차수 미확인');
  const mItem=path.match(/\\.items\\[(\\d+)\\]/);
  const explicitItemIndex=mItem?Number(mItem[1]):null;
  const targetIndex=explicitItemIndex??(Number.isInteger(condition?.item_index)?condition.item_index:null);
  const items=Array.isArray(expense?.items)?expense.items:[];
  const targetItem=targetIndex!==null?items[targetIndex]:null;
  const showItem=(item:any,i:number)=>`${i+1}. ${item?.name||'이름 미확인'}${Number.isInteger(item?.amount)?` (${money(item.amount)})`:''}`;
  const targetLabel=targetItem?.name?`${targetItem.name}${Number.isInteger(targetItem.amount)?` (${money(targetItem.amount)})`:''}`:'정확한 항목 미확인';
  const allNames=Array.isArray(ctx.participants)?ctx.participants.filter((p:any)=>typeof p==='string'&&p.trim()):[];
  const attendees=roundNumber!==null?ctx.rounds?.find((r:any)=>r.round_number===roundNumber)?.participant_names:null;
  const people=Array.isArray(attendees)&&attendees.length?attendees:allNames;
  const peopleLabel=people.length?people.join(', '):'참석자 미확인';
  const names=Array.isArray(rule?.participant_names)&&rule.participant_names.length?rule.participant_names:[];
  const methodLabel:Record<string,string>={equal:'균등 분할',fixed:'고정 금액 분담',explicit_amount:'개인별 지정 금액'};
  const method=rule?.method?methodLabel[rule.method]||String(rule.method):'분담 방법 미확인';
  const amounts=Array.isArray(rule?.individual_amounts)?rule.individual_amounts:[];
  const amountText=amounts.length?` / 개인 금액: ${amounts.map((a:any)=>`${a.participant_name||'이름 미확인'} ${Number.isInteger(a.amount)?money(a.amount):'금액 미확인'}`).join(', ')}`:'';
  const conditionText=rule
   ?`분담 조건: ${method} / 대상: ${names.length?names.join(', '):'대상자 미확인'}${amountText}`
   :exception
    ?`예외 조건: ${exception.participant_name||'이름 미확인'} / ${({exclude:'분담 제외',fixed_amount:'고정 금액',covered_by_other:'다른 사람이 대신 부담'} as Record<string,string>)[exception.kind]||exception.kind||'종류 미확인'}${Number.isInteger(exception.fixed_amount)?` (${money(exception.fixed_amount)})`:''}${exception.covered_by_name?` / 대신 부담: ${exception.covered_by_name}`:''}`
    :contribution
     ?`찬조 조건: ${contribution.contributor_name||'찬조자 미확인'}${Number.isInteger(contribution.amount)?` / ${money(contribution.amount)}`:''}`
     :'해당 조건을 특정하지 못했어요';
  const candidateText=items.length?`이 결제에서 확인된 항목: ${items.map(showItem).join(' · ')}`:'현재 정산 데이터에 연결할 항목이 없습니다. 사진 검수 결과 또는 원문에서 항목을 확인해야 합니다.';
  const evidence=String(doc?.supplied_evidence||'');
  const evidenceSections=roundNumber!==null?evidence.split(/(?=\\[\\d+차 \\/ 영수증)/).filter(x=>x.startsWith(`[${roundNumber}차 / 영수증`)):[];
  const evidenceItems=evidenceSections.flatMap(x=>x.split('\\n').filter(line=>/^\\s*-\\s*.+:\\s*\\d+원/.test(line)).map(line=>line.replace(/^\\s*-\\s*/,'')));
  const evidenceText=evidenceItems.length?`사진에서 확인한 항목: ${evidenceItems.join(' · ')}`:'';
  if(code==='unresolved_item'||code==='unresolved_expense')return {
   title:`${roundLabel} · ${rule?'분담':exception?'예외':contribution?'찬조':'정산'} 조건의 적용 항목 확인`,
   detail:`${conditionText}. ${targetItem?`현재 지정된 항목: ${targetLabel}.`: 'AI가 이 조건을 어느 항목에 연결해야 하는지 확정하지 못했어요.'} ${candidateText}${evidenceText?` ${evidenceText}`:''}`,
   hint:`예: '${roundLabel}의 [실제 항목명]에 ${rule?`${names.length?names.join(', '):'참여자'}가 ${method}으로 부담`:`${exception?.participant_name||'해당 참여자'}의 예외 조건 적용`}해 줘.'처럼 조건과 항목명을 함께 알려주세요.`
  };
  if(code==='missing_items')return {
   title:`${roundLabel} · 비용 항목을 정산에 반영하지 못했어요`,
   detail:evidenceText||`현재 결제 총액${Number.isInteger(expense?.total_amount)?` ${money(expense.total_amount)}`:''}은 확인했지만 항목별 금액은 누락됐어요.`,
   hint:'이미 검수한 영수증의 항목명과 금액을 빠짐없이 반영해 달라고 AI에게 요청해 주세요.'
  };
  if(code==='rule_count'||code==='incomplete_rule'||code==='incomplete_individual_amounts'||code==='conflicting_rule')return {
   title:`${roundLabel} · ${targetLabel}의 분담 조건 확인`,
   detail:`${conditionText}. ${candidateText}`,
   hint:`${roundLabel}의 '${targetItem?.name||'실제 항목명'}'을 누가 얼마씩 또는 어떤 방식으로 나눌지 구체적으로 알려주세요.`
  };
  if(code==='item_sum_mismatch'||code==='receipt_mismatch'||code==='missing_total'||code==='missing_item_data')return {
   title:`${roundLabel} · ${targetItem?.name||'결제'} 금액 확인`,
   detail:`결제 총액: ${Number.isInteger(expense?.total_amount)?money(expense.total_amount):'미확인'}. ${candidateText}`,
   hint:'영수증과 비교해서 잘못된 항목명이나 금액을 알려주세요.'
  };
  if(ci>=0)return {
   title:`${roundLabel} · ${contribution?.contributor_name||'찬조자'}님의 찬조 조건 확인`,
   detail:`${conditionText}. ${candidateText}`,
   hint:'찬조금을 누가 제공했고 어느 결제의 어떤 항목에 얼마를 적용할지 알려주세요.'
  };
  if(xi>=0)return {
   title:`${roundLabel} · ${exception?.participant_name||'참여자'}님의 예외 조건 확인`,
   detail:`${conditionText}. 적용 항목: ${targetLabel}. ${candidateText}`,
   hint:'해당 참여자를 어느 항목에서 제외하거나 얼마로 조정해야 하는지 알려주세요.'
  };
  if(roundIndex>=0)return {
   title:`${roundLabel} · 참석자 확인`,
   detail:`현재 확인된 참석자: ${peopleLabel}`,
   hint:'이 차수의 실제 참석자 이름을 빠짐없이 알려주세요.'
  };
  if(indexOf('participants')>=0||code==='ambiguous_person'||code==='unresolved_person')return {
   title:'참여자 이름 확인',
   detail:`현재 확인된 이름: ${peopleLabel}`,
   hint:'어떤 이름이 빠졌거나 잘못되었는지 알려주세요.'
  };
  return {
   title:`${roundLabel} · 추가 확인이 필요한 조건`,
   detail:`${conditionText}. ${issue.question||'정보가 불완전합니다.'}`,
   hint:'해당 차수·항목명·참여자와 원하는 분담 방법을 문장으로 입력해 주세요.'
  };
 };
'''

# The TypeScript fragment is raw Python text; normalize regex escapes once.
NEW = NEW.replace('\\\\', '\\')

def main():
    if not FRONT.is_file():
        raise RuntimeError(f'Missing file: {FRONT}')
    old = FRONT.read_text(encoding='utf-8-sig')
    if old.count(START)!=1 or old.count(END)!=1:
        raise RuntimeError(f'Expected one describeIssue and IssueResolver anchor, found {old.count(START)} / {old.count(END)}. No files changed.')
    a = old.index(START)
    b = old.index(END, a)
    if 'const targetItemIndex=rule?.item_index' not in old[a:b]:
        raise RuntimeError('Current describeIssue differs from known version. No files changed; send current index.tsx.')
    updated = old[:a] + NEW + old[b:]
    backup = ROOT / ('_backup_issue_guidance_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    dest = backup / 'mobile/src/app/index.tsx'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FRONT, dest)
    FRONT.write_text(updated,encoding='utf-8')
    print('[OK] Detailed issue descriptions installed in mobile/src/app/index.tsx')
    print('[BACKUP]',dest)
    print('Next: cd mobile; npx tsc --noEmit; npx expo start --go --tunnel --clear')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('[STOP]', exc, file=sys.stderr)
        sys.exit(1)
