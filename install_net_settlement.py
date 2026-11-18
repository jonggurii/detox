#!/usr/bin/env python3
"""Apply netted transfer UX to current Moa Settlement project (safe, all-or-nothing)."""
from pathlib import Path
from datetime import datetime
import re, shutil, ast, sys
ROOT=Path.cwd()
APP=ROOT/'app.py'
FRONT=ROOT/'mobile/src/app/index.tsx'
API=ROOT/'mobile/src/services/api.ts'
NET=ROOT/'src/settlements/netting.py'

NET_CODE='''"""Deterministic netting across rounds. Original per-expense settlements remain unchanged."""
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
'''

FRONT_HELPERS='''// 차수별 송금을 서로 상계하여 실제 보낼 송금만 계산한다. 원본 내역은 따로 보존한다.
const netTransfers=(rows:Array<{from_participant:string;to_participant:string;amount:number}>)=>{
 const balance=new Map<string,number>();
 for(const t of rows){
  if(!Number.isSafeInteger(t.amount)||t.amount<0||!t.from_participant||!t.to_participant||t.from_participant===t.to_participant)throw new Error('송금 데이터가 올바르지 않습니다.');
  balance.set(t.from_participant,(balance.get(t.from_participant)||0)-t.amount);
  balance.set(t.to_participant,(balance.get(t.to_participant)||0)+t.amount);
 }
 const cmp=(a:string,b:string)=>a<b?-1:a>b?1:0;
 const debt=[...balance].filter(([,n])=>n<0).map(([name,n])=>({name,amount:-n})).sort((a,b)=>b.amount-a.amount||cmp(a.name,b.name));
 const credit=[...balance].filter(([,n])=>n>0).map(([name,n])=>({name,amount:n})).sort((a,b)=>b.amount-a.amount||cmp(a.name,b.name));
 const result:Array<{from_participant:string;to_participant:string;amount:number}>=[];
 let i=0,j=0;
 while(i<debt.length&&j<credit.length){
  const amount=Math.min(debt[i].amount,credit[j].amount);
  if(amount)result.push({from_participant:debt[i].name,to_participant:credit[j].name,amount});
  debt[i].amount-=amount;credit[j].amount-=amount;
  if(!debt[i].amount)i++;
  if(!credit[j].amount)j++;
 }
 if(i!==debt.length||j!==credit.length)throw new Error('차수 간 잔액을 정산하지 못했습니다.');
 return result;
};
const effectiveTransfers=(calc:Calculation,localDiff=false)=>localDiff
 ?groupedTransfers(calc.result.settlements)
 :netTransfers(calc.result.settlements);
'''

def patch_front(s):
    anchor='// 송금별 상태 키는 계산 ID/입력 버전과 송금 관계·금액을 함께 사용한다.'
    assert s.count(anchor)==1, 'index.tsx transfer helper anchor mismatch'
    s=s.replace(anchor,FRONT_HELPERS+anchor,1)
    old='const paymentRows=(calc:Calculation)=>groupedTransfers(calc.result.settlements).map(t=>({'
    new='const paymentRows=(calc:Calculation,localDiff=false)=>effectiveTransfers(calc,localDiff).map(t=>({'
    assert s.count(old)==1, 'index.tsx paymentRows mismatch'
    s=s.replace(old,new,1)
    assert s.count('const paymentStats=(calc:Calculation,paid:Record<string,boolean>)=>{')==1
    s=s.replace('const paymentStats=(calc:Calculation,paid:Record<string,boolean>)=>{\n const rows=paymentRows(calc);', 'const paymentStats=(calc:Calculation,paid:Record<string,boolean>,localDiff=false)=>{\n const rows=paymentRows(calc,localDiff);',1)
    # Both home listing and PaymentList use paymentStats; preserve local diff semantics.
    s=s.replace('paymentStats(calc,paid);','paymentStats(calc,paid,sid.startsWith(\'local-diff-\'));')
    # Different homes may have other occurrences; ensure all are safe.
    s=s.replace('paymentStats(calc,meta[s.session_id]?.transferPaid||{})','paymentStats(calc,meta[s.session_id]?.transferPaid||{},s.session_id.startsWith(\'local-diff-\'))')
    share='...groupedTransfers(calculation.result.settlements).map(t=>'
    assert s.count(share)==1, 'index.tsx share mismatch'
    s=s.replace(share,"...effectiveTransfers(calculation,doc.session_id.startsWith('local-diff-')).map(t=>",1)
    # Add opt-in to server's trusted netting calculation, never transmit an unverified amount.
    needle='      ...(isLocal?{local_amount:t.amount}:{}),'
    assert s.count(needle)==1, 'index.tsx AI reminder payload mismatch'
    s=s.replace(needle,needle+'\n      optimized:!isLocal,',1)
    # detail view is deliberately informational: payment tracking ONLY on optimized rows.
    anchor='<Text style={styles.helper}>입금 여부는 총무가 직접 확인하는 기록이며 은행 거래 내역과 자동 연동되지 않습니다.'
    assert s.count(anchor)==1, 'index.tsx detail explanatory anchor mismatch'
    s=s.replace(anchor,'''{!sid.startsWith('local-diff-')&&<View style={{marginTop:16,borderTopWidth:1,borderTopColor:C.line,paddingTop:14,gap:8}}>
    <Pressable onPress={()=>setDetailedTransfersOpen(v=>!v)} style={styles.rowBetween}>
     <Text style={styles.subhead}>차수별 송금 산출 근거 ({calc.result.settlements.length}건)</Text>
     <Text style={styles.link}>{detailedTransfersOpen?'접기 ▲':'펼치기 ▼'}</Text>
    </Pressable>
    <Text style={styles.helper}>아래는 차수별로 계산한 원래 송금 내역입니다. 실제 송금·입금 확인과 독촉은 위의 통합 송금 내역만 이용하세요. 두 목록의 금액을 함께 송금하면 중복 정산됩니다.</Text>
    {detailedTransfersOpen&&calc.result.settlements.map((t,i)=><View key={i} style={styles.infoRow}>
     <Text style={styles.infoLabel}>{(d.revisions[d.revisions.length-1]?.context?.expenses||[])[t.expense_index]?.round_number??'?'}차 · {t.from_participant} → {t.to_participant}</Text>
     <Text style={styles.infoValue}>{money(t.amount)}</Text>
    </View>)}
   </View>}
   '''+anchor,1)
    # Keep toggle outside nested PaymentList where state is created.
    anchor='const PaymentList=({d,calc}:{d:Session;calc:Calculation})=>{'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'\n  const [detailedTransfersOpen,setDetailedTransfersOpen]=useState(false);',1)
    # Show the saved transfer reduction explicitly.
    marker='  return <View style={{gap:12}}>\n   <View style={styles.progressCard}>'
    assert s.count(marker)==1, 'index.tsx payment header mismatch'
    s=s.replace(marker, '''  return <View style={{gap:12}}>
   {!sid.startsWith('local-diff-')&&<Text style={styles.success}>차수별 {calc.result.settlements.length}건 → 실제 송금 {stats.totalCount}건으로 정리했어요. 통합된 금액만 보내면 됩니다.</Text>}
   <View style={styles.progressCard}>''',1)
    # update explanatory string
    s=s.replace('같은 송금자·수취인 간 송금은 합산 표시합니다.', '차수 간 주고받을 금액은 서로 상계하여 최종 송금만 표시합니다.',1)
    s=s.replace('<Panel title="송금 및 입금 관리">','<Panel title="통합 송금 · 입금 관리">',1)
    return s

def patch_api(s):
    # The reminder-style patch adds style?:ReminderStyle between tone and repeat.
    # Insert optimized independently of argument order/spacing and preserve style.
    signature = re.search(
        r'generate\s*:\s*\(data\s*:\s*\{(?P<fields>[^{}]*)\}\)',
        s,
    )
    if not signature or 'tone:ReminderTone' not in signature.group('fields') or 'repeat:boolean' not in signature.group('fields'):
        raise ValueError('api.ts reminder payload not found; no files changed')
    fields = signature.group('fields')
    if 'optimized?:boolean' in fields:
        raise ValueError('api.ts already has optimized field; no files changed')
    updated_fields, count = re.subn(
        r'(\brepeat\s*:\s*boolean\b)',
        r'\1;optimized?:boolean',
        fields,
    )
    if count != 1:
        raise ValueError('api.ts repeat field ambiguous; no files changed')
    return s[:signature.start('fields')] + updated_fields + s[signature.end('fields'):]

def patch_app(s):
    # Current version may put ReminderBody/generate route in app.py, but recent branches differ.
    if '@app.post("/api/reminders/generate")' not in s:
        raise ValueError('app.py does not contain /api/reminders/generate. Supply your CURRENT app.py; no files changed.')
    if 'optimized: StrictBool = False' not in s:
        anchor='    repeat: StrictBool = False'
        assert s.count(anchor)==1,'app.py reminder request signature mismatch'
        s=s.replace(anchor,'    optimized: StrictBool = False\n'+anchor,1)
    if 'from settlements.netting import net_settlements' not in s:
        marker='from settlements.calculator import CalculationError'
        assert s.count(marker)==1,'app.py import mismatch'
        s=s.replace(marker,marker+'\nfrom settlements.netting import net_settlements',1)
    # Prefer existing confirmed calculation and compute netting server side from original settlements.
    start=s.index('    @app.post("/api/reminders/generate")')
    stop=s.find('    # 영수증 업로드',start)
    if stop<0: stop=len(s)
    section=s[start:stop]
    # Accept both compact and multiline sum(), without changing sender/receiver checks.
    pattern = (
        r'(?m)^(?P<indent>[ \t]*)amount\s*=\s*sum\(\s*'
        r'x\["amount"\]\s+for\s+x\s+in\s+'
        r'calc\["result"\]\["settlements"\]'
        r'(?=\s+if\s+x\["from_participant"\])'
    )
    def insert_netting(match):
        indent = match.group('indent')
        return (
            indent + 'trusted_rows = (\n'
            + indent + '    net_settlements(calc["result"]["settlements"])\n'
            + indent + '    if body.optimized else calc["result"]["settlements"]\n'
            + indent + ')\n'
            + indent + 'amount = sum(\n'
            + indent + '    x["amount"]\n'
            + indent + '    for x in trusted_rows'
        )
    section, count = re.subn(pattern, insert_netting, section)
    assert count == 1, 'app.py reminder validated amount block mismatch'
    s=s[:start]+section+s[stop:]
    return s

def main():
    for path in [APP,FRONT,API]:
        if not path.is_file(): raise FileNotFoundError(path)
    original={p:p.read_text(encoding='utf-8-sig') for p in [APP,FRONT,API]}
    if NET.exists(): raise RuntimeError('netting.py already exists; stop to avoid overwriting')
    result={APP:patch_app(original[APP]),FRONT:patch_front(original[FRONT]),API:patch_api(original[API])}
    ast.parse(result[APP]);ast.parse(NET_CODE)
    backup=ROOT/('_backup_net_settlement_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    for p in result:
        dest=backup/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    try:
        for p,content in result.items():p.write_text(content,encoding='utf-8')
        NET.parent.mkdir(parents=True,exist_ok=True);NET.write_text(NET_CODE,encoding='utf-8')
    except Exception:
        for p in result:shutil.copy2(backup/p.relative_to(ROOT),p)
        if NET.exists(): NET.unlink()
        raise
    print('[OK] Updated app.py, mobile/src/app/index.tsx, mobile/src/services/api.ts')
    print('[OK] Created src/settlements/netting.py')
    print('[BACKUP]',backup)
    print('Check: $env:PYTHONPATH="src"; python -m pytest tests -q; cd mobile; npx tsc --noEmit')
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('[STOP]',exc,file=sys.stderr);sys.exit(1)
