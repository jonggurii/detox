export type NetRow={from_participant:string;to_participant:string;amount:number};
export function explainTransfers(rows:NetRow[]){
 const balance=new Map<string,number>();
 for(const t of rows){
  if(!Number.isSafeInteger(t.amount)||t.amount<0||!t.from_participant||!t.to_participant||t.from_participant===t.to_participant)throw new Error('송금 데이터가 올바르지 않습니다.');
  balance.set(t.from_participant,(balance.get(t.from_participant)||0)-t.amount);
  balance.set(t.to_participant,(balance.get(t.to_participant)||0)+t.amount);
 }
 const cmp=(a:string,b:string)=>a<b?-1:a>b?1:0;
 const debt=[...balance].filter(([,n])=>n<0).map(([name,n])=>({name,amount:-n})).sort((a,b)=>b.amount-a.amount||cmp(a.name,b.name));
 const credit=[...balance].filter(([,n])=>n>0).map(([name,n])=>({name,amount:n})).sort((a,b)=>b.amount-a.amount||cmp(a.name,b.name));
 const result:NetRow[]=[];
 const steps:Array<NetRow & {debtBefore:number;creditBefore:number;debtAfter:number;creditAfter:number}>=[];
 let i=0,j=0;
 while(i<debt.length&&j<credit.length){
  const d=debt[i],c=credit[j],amount=Math.min(d.amount,c.amount);
  if(amount){const row={from_participant:d.name,to_participant:c.name,amount};result.push(row);steps.push({...row,debtBefore:d.amount,creditBefore:c.amount,debtAfter:d.amount-amount,creditAfter:c.amount-amount});}
  d.amount-=amount;c.amount-=amount;
  if(!d.amount)i++;if(!c.amount)j++;
 }
 if(i!==debt.length||j!==credit.length)throw new Error('차수 간 잔액을 정산하지 못했습니다.');
 return {result,steps,balance};
}
export function personExplanation(name:string,rows:Array<NetRow & {expense_index:number}>,expenses:Array<{round_number?:number}>,final:NetRow[]){
 const rounds=new Map<string,{round:string;send:number;receive:number}>();
 for(const t of rows){if(t.from_participant!==name&&t.to_participant!==name)continue;
  const round=String(expenses[t.expense_index]?.round_number??'?');
  const r=rounds.get(round)||{round,send:0,receive:0};
  if(t.from_participant===name)r.send+=t.amount;else r.receive+=t.amount;rounds.set(round,r);
 }
 const details=[...rounds.values()].sort((a,b)=>Number(a.round)-Number(b.round));
 const send=details.reduce((s,r)=>s+r.send,0),receive=details.reduce((s,r)=>s+r.receive,0);
 return {details,send,receive,balance:receive-send,before:rows.filter(t=>t.from_participant===name||t.to_participant===name),after:final.filter(t=>t.from_participant===name||t.to_participant===name)};
}
