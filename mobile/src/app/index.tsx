import React,{useCallback,useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Alert,BackHandler,Keyboard,KeyboardAvoidingView,Platform,Pressable,ScrollView,Share,StatusBar,StyleSheet,Switch,Text,TextInput,View} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import * as Clipboard from 'expo-clipboard';
import {sessionApi,previewImage,confirmImage} from '../services/api';
import type {ImagePreview} from '../services/api';
import type {Calculation,Json,Session,SessionSummary} from '../services/api';

type Page='home'|'create'|'imageReview'|'review'|'edit'|'detail';
type InputMode='ai'|'custom';
type ReminderTone='friend'|'senior'|'junior';
type ReminderRecord={count:number;lastAt:string};
type LocalMeta={title?:string;paid?:Record<string,boolean>;transferPaid?:Record<string,boolean>;reminderRecords?:Record<string,ReminderRecord>;reminderTones?:Record<string,ReminderTone>;deleted?:boolean};
type PaymentFilter='all'|'unpaid'|'paid';
type DiffTransfer={from:string;to:string;amount:string};
type LocalDiff={session:Session;calculation:Calculation};
type MetaMap=Record<string,LocalMeta>;
const STORAGE='moa_mobile_board_v2';
const DIFF_STORAGE='moa_mobile_direct_transfers_v1';
const CREATE_DRAFT_STORAGE='moa_mobile_create_draft_v1';
const EDIT_DRAFT_STORAGE='moa_mobile_edit_draft_v1';
const C={bg:'#F5F7F3',white:'#FFFFFF',ink:'#173A38',green:'#176858',greenSoft:'#E7F2EB',line:'#DEE7E0',muted:'#71817A',orange:'#B9652E',orangeSoft:'#FFF2E5'};
const money=(n:any)=>`${Number(n||0).toLocaleString('ko-KR')}원`;
// 송금 금액은 변경하지 않고, 화면/공유용으로 송금자→수취인 가나다순으로 정리한다.
const groupedTransfers=(rows:Array<{from_participant:string;to_participant:string;amount:number}>)=>{
 const grouped=new Map<string,{from_participant:string;to_participant:string;amount:number}>();
 for(const t of rows){
  if(t.amount<=0)continue;
  const key=JSON.stringify([t.from_participant,t.to_participant]);
  const old=grouped.get(key);
  if(old)old.amount+=t.amount;
  else grouped.set(key,{from_participant:t.from_participant,to_participant:t.to_participant,amount:t.amount});
 }
 const ko=new Intl.Collator('ko-KR');
 return [...grouped.values()].sort((a,b)=>ko.compare(a.from_participant,b.from_participant)||ko.compare(a.to_participant,b.to_participant));
};
// 송금별 상태 키는 계산 ID/입력 버전과 송금 관계·금액을 함께 사용한다.
// 계산 조건이 바뀌면 이전 입금 확인을 새 계산에 잘못 적용하지 않는다.
const paymentRows=(calc:Calculation)=>groupedTransfers(calc.result.settlements).map(t=>({
 ...t,
 key:JSON.stringify([calc.input_revision,(calc as any).calculation_id||'',t.from_participant,t.to_participant,t.amount]),
}));
const paymentStats=(calc:Calculation,paid:Record<string,boolean>)=>{
 const rows=paymentRows(calc);
 const totalAmount=rows.reduce((s,t)=>s+t.amount,0);
 const paidRows=rows.filter(t=>!!paid[t.key]);
 const paidAmount=paidRows.reduce((s,t)=>s+t.amount,0);
 return {rows,totalAmount,paidAmount,unpaidAmount:totalAmount-paidAmount,paidCount:paidRows.length,totalCount:rows.length,percent:totalAmount>0?Math.round(paidAmount/totalAmount*100):100};
};
// 안내 문구는 확정된 송금 결과에서만 생성한다. AI가 금액을 다시 추측하지 않는다.
const reminderText=(title:string,from:string,to:string,amount:number,tone:ReminderTone,repeat:boolean)=>{
 const sum=money(amount);
 if(tone==='senior')return repeat
  ?`안녕하세요, ${from}님. [${title}] 정산 관련하여 다시 안내드립니다. ${to}님께 ${sum} 송금 여부를 확인 부탁드립니다. 이미 송금하셨다면 양해 부탁드립니다. 감사합니다.`
  :`안녕하세요, ${from}님. [${title}] 정산 안내드립니다. ${to}님께 송금하실 금액은 ${sum}입니다. 편하실 때 확인 부탁드립니다. 감사합니다.`;
 if(tone==='junior')return repeat
  ?`${from}아, [${title}] 정산 아직 확인이 안 돼서 다시 연락해! ${to}에게 ${sum} 보내줬는지 확인 부탁해. 이미 보냈으면 알려줘 😊`
  :`${from}아, [${title}] 정산 금액은 ${sum}이야. ${to}에게 보내주면 돼! 확인 부탁해 😊`;
 return repeat
  ?`${from}아! [${title}] 정산 아직 입금 확인이 안 돼서 다시 알려줘. ${to}한테 ${sum} 부탁해! 이미 보냈으면 말해줘 🙏`
  :`${from}아, [${title}] 정산 나왔어! ${to}한테 ${sum} 보내주면 돼. 고마워!`;
};
const names=(s:string)=>s.split(/[,，\n]/).map(v=>v.trim()).filter(Boolean);
const safeAmount=(s:string)=>{const v=s.replace(/,/g,'').trim();if(!/^\d+$/.test(v)||!Number.isSafeInteger(Number(v)))throw new Error('금액은 0 이상의 정확한 원 단위 정수로 입력해 주세요.');return Number(v);};
const clone=<T,>(x:T):T=>JSON.parse(JSON.stringify(x));
const LABEL:Record<string,string>={participants:'정산 참여자',rounds:'차수 및 참석',round_number:'차수',participant_count:'참석 인원',participant_names:'참석자',attendance:'참석 기록',participant_name:'참여자',source_note:'근거 메모',note:'메모',expenses:'결제 내역',payer_name:'결제자',total_amount:'총액 (원)',description:'결제 설명',items:'결제 항목',name:'항목명',amount:'금액 (원)',category:'항목 분류',occurrence_note:'시점',receipt_total_amount:'영수증 합계',split_rules:'분담 기준',expense_index:'결제 번호 (0부터)',item_index:'항목 번호 (0부터)',method:'분담 방법',individual_amounts:'개인별 지정 금액',remainder_payer_name:'잔액 부담자',basis_note:'합의 근거',exceptions:'개인별 예외',kind:'예외 방식',fixed_amount:'지정 부담액',covered_by_name:'대신 부담자',reason:'예외 사유',contributions:'찬조금',contributor_name:'찬조자',uses:'찬조금 적용 항목',funding_note:'전달·충당 확인 메모',tone:'안내 말투',relationship:'관계',reminder_handling:'재안내 방식'};
const ENUM:Record<string,string>={equal:'균등 분담',explicit_amount:'개인별 금액 지정',exclude:'항목 제외',fixed_amount:'고정 금액',covered_by_other:'대신 부담',undecided:'미정',personal_follow_up:'개인별 재안내',external_service_only:'외부 서비스 알림'};
const CHECKS=[['source_reviewed','원문과 비교해 누락·추정된 내용이 없는지 확인했어요.'],['people_resolved','이름과 호칭이 누구를 뜻하는지 확인했어요.'],['conditions_reviewed','분담·예외·잔액 처리에 합의했어요.'],['funding_verified','찬조금의 전달과 적용액을 확인했어요.']] as const;
function Button({text,onPress,secondary=false,disabled=false,small=false,danger=false}:{text:string;onPress:()=>void;secondary?:boolean;disabled?:boolean;small?:boolean;danger?:boolean}){return <Pressable onPress={onPress} disabled={disabled} style={[styles.btn,secondary&&styles.btnSecondary,small&&styles.btnSmall,danger&&styles.btnDanger,disabled&&{opacity:.45}]}><Text style={[styles.btnText,secondary&&{color:C.ink},danger&&{color:'#A33F3F'},small&&{fontSize:13}]}>{text}</Text></Pressable>}
function Field({label,value,onChange,placeholder='',multiline=false,numeric=false}:{label:string;value:string;onChange:(s:string)=>void;placeholder?:string;multiline?:boolean;numeric?:boolean}){return <View style={styles.field}><Text style={styles.label}>{label}</Text><TextInput style={[styles.input,multiline&&{minHeight:100,textAlignVertical:'top'}]} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor="#9DAAA3" multiline={multiline} keyboardType={numeric?'numeric':'default'}/></View>}
function Panel({title,children}:{title:string;children:React.ReactNode}){return <View style={styles.panel}><Text style={styles.panelTitle}>{title}</Text>{children}</View>}
function Chip({text,active,onPress}:{text:string;active:boolean;onPress:()=>void}){return <Pressable onPress={onPress} style={[styles.chip,active&&styles.chipActive]}><Text style={[styles.chipText,active&&{color:'#FFF'}]}>{text}</Text></Pressable>}
function SchemaEditor({schema,value,onChange,path=[],label='정산 조건',depth=0}:{schema:Json;value:any;onChange:(v:any)=>void;path?:(string|number)[];label?:string;depth?:number}){
 const resolve=(s:Json):Json=>s?.$ref?schema.definitions?.[String(s.$ref).split('/').pop()||'']||s:s;
 const initial=(s:Json):any=>{s=resolve(s);const types=Array.isArray(s.type)?s.type:[s.type];if(types.includes('null'))return null;if(s.enum)return s.enum[0];if(types.includes('object'))return Object.fromEntries((s.required||[]).map((k:string)=>[k,initial(s.properties[k])]));if(types.includes('array'))return [];if(types.includes('integer'))return s.minimum??0;return '';};
 const render=(s:Json,v:any,p:(string|number)[],title:string,level:number):React.ReactNode=>{
  s=resolve(s);const types=Array.isArray(s.type)?s.type:[s.type];const update=(next:any)=>{const nextRoot=clone(value);if(!p.length){onChange(next);return;}let cursor=nextRoot;for(let i=0;i<p.length-1;i++)cursor=cursor[p[i]];cursor[p[p.length-1]]=next;onChange(nextRoot);};
  if(types.includes('object')){
   const obj=v&&typeof v==='object'&&!Array.isArray(v)?v:{};
   const absent=Object.keys(s.properties||{}).filter(k=>!(k in obj));
   return <View style={[styles.editorGroup,level===0&&{borderWidth:0,paddingHorizontal:0}]} key={p.join('-')||'root'}>{level>0&&<Text style={styles.groupTitle}>{title}</Text>}{Object.keys(obj).filter(k=>s.properties?.[k]).map(k=><View key={k} style={{marginBottom:8}}>{render(s.properties[k],obj[k],[...p,k],LABEL[k]||k,level+1)}{!(s.required||[]).includes(k)&&<Pressable onPress={()=>{const next=clone(obj);delete next[k];update(next)}}><Text style={styles.link}>− {LABEL[k]||k} 제거</Text></Pressable>}</View>)}{absent.length>0&&<View style={styles.wrap}>{absent.map(k=><Pressable key={k} style={styles.addPill} onPress={()=>update({...obj,[k]:initial(s.properties[k])})}><Text style={styles.addPillText}>＋ {LABEL[k]||k}</Text></Pressable>)}</View>}</View>;
  }
  if(types.includes('array')){
   const arr=Array.isArray(v)?v:[];
   return <View style={styles.editorGroup} key={p.join('-')}><Text style={styles.groupTitle}>{title} <Text style={styles.muted}>({arr.length})</Text></Text>{arr.map((item,i)=><View key={i} style={styles.arrayRow}><View style={styles.rowBetween}><Text style={styles.subhead}>{title} {i+1}</Text><Pressable onPress={()=>update(arr.filter((_,j)=>i!==j))}><Text style={styles.deleteText}>삭제</Text></Pressable></View>{render(s.items,item,[...p,i],typeof item==='string'?`${title} ${i+1}`:'상세 정보',level+1)}</View>)}<Button text={`＋ ${title} 추가`} secondary small onPress={()=>update([...arr,initial(s.items)])}/></View>;
  }
  if(s.enum){return <View style={styles.field} key={p.join('-')}><Text style={styles.label}>{title}</Text><View style={styles.wrap}>{s.enum.map((opt:any,i:number)=><Chip key={i} text={opt===null?'미정':ENUM[String(opt)]||String(opt)} active={opt===v} onPress={()=>update(opt)}/>)}</View></View>}
  if(types.includes('integer')){return <Field key={p.join('-')} label={title} numeric value={v===null||v===undefined?'':String(v)} onChange={text=>{const t=text.replace(/,/g,'');update(t===''?null:(/^\d+$/.test(t)&&Number.isSafeInteger(Number(t))?Number(t):v))}} placeholder="금액 또는 숫자"/>}
  return <Field key={p.join('-')} label={title} value={v===null||v===undefined?'':String(v)} onChange={t=>update(t===''&&types.includes('null')?null:t)} placeholder="입력해 주세요"/>;
 };
 return <>{render(schema,value,path,label,depth)}</>;
}
// 항목별 exclude 예외를 분담자 선택 상태에 반영한다.
const effectiveMembersFor=(rule:any,exceptions:any[],ei:number,ii:number):string[]=>{
 const raw:string[]=Array.isArray(rule?.participant_names)?rule.participant_names:[];
 const excluded=new Set((exceptions||[]).filter((x:any)=>x.expense_index===ei&&x.item_index===ii&&x.kind==='exclude').map((x:any)=>x.participant_name));
 return raw.filter(p=>!excluded.has(p));
};
// 화면에서만 사용하는 미리보기: 실제 확정 계산은 서버에서 수행한다.
const previewItem=(item:any,rule:any,contributions:any[],exceptions:any[],ei:number,ii:number)=>{
 const applied=contributions.reduce((sum:number,c:any)=>sum+(c.expense_index===ei?(c.uses||[]).reduce((v:number,u:any)=>v+(u.item_index===ii?Number(u.amount||0):0),0):0),0);
 const gross=Number(item?.amount);const net=gross-applied;
 if(!Number.isSafeInteger(gross)||gross<0||!Number.isSafeInteger(applied)||applied<0||net<0)return {error:'항목 금액과 찬조금 적용액을 확인해 주세요.',shares:[] as {name:string;amount:number}[]};
 if(!rule)return {error:'분담 규칙이 없어요.',shares:[] as {name:string;amount:number}[]};
 const members:string[]=effectiveMembersFor(rule,exceptions,ei,ii);
 const related=(exceptions||[]).filter((x:any)=>x.expense_index===ei&&x.item_index===ii);
 if(related.some((x:any)=>x.kind!=='exclude'))return {error:'고정 금액·대신 부담 등 복합 예외는 서버 계산에서 확인해 주세요.',shares:[] as {name:string;amount:number}[]};
 if(!members.length||new Set(members).size!==members.length)return {error:'분담자를 한 명 이상 중복 없이 선택해 주세요.',shares:[] as {name:string;amount:number}[]};
 if(rule.method==='equal'){
  if(rule.remainder_payer_name&& !members.includes(rule.remainder_payer_name))return {error:'잔액 부담자가 분담자에 포함되어야 해요.',shares:[] as {name:string;amount:number}[]};
  const each=Math.floor(net/members.length),remainder=net%members.length;
  if(remainder&&!rule.remainder_payer_name)return {error:`1원 단위 잔액 ${remainder}원은 서버의 잔액 배분 규칙에 따라 달라질 수 있어요.`,shares:members.map((name,i)=>({name,amount:each+(i<remainder?1:0)}))};
  return {error:'',shares:members.map(name=>({name,amount:each+(name===rule.remainder_payer_name?remainder:0)}))};
 }
 if(rule.method==='explicit_amount'){
  const entries:any[]=Array.isArray(rule.individual_amounts)?rule.individual_amounts:[];
  if(entries.length!==members.length||entries.some(x=>!members.includes(x.participant_name))||new Set(entries.map(x=>x.participant_name)).size!==members.length)return {error:'선택한 모든 분담자의 금액을 각각 지정해 주세요.',shares:[] as {name:string;amount:number}[]};
  if(entries.some(x=>!Number.isSafeInteger(x.amount)||x.amount<0))return {error:'개인별 금액을 0원 이상의 정수로 입력해 주세요.',shares:[] as {name:string;amount:number}[]};
  const sum=entries.reduce((v,x)=>v+x.amount,0);
  if(sum!==net)return {error:`개인별 금액 합계 ${money(sum)}와 분담 대상 금액 ${money(net)}가 달라요.`,shares:entries.map(x=>({name:x.participant_name,amount:x.amount}))};
  return {error:'',shares:entries.map(x=>({name:x.participant_name,amount:x.amount}))};
 }
 return {error:'고급 분담 방식은 서버 검증에서 확인해 주세요.',shares:[] as {name:string;amount:number}[]};
};
function FriendlyEditor({value,onChange}:{value:Json;onChange:(v:Json)=>void}){
 const people:string[]=Array.isArray(value.participants)?value.participants:[];
 const expenses:any[]=Array.isArray(value.expenses)?value.expenses:[];
 const rounds:any[]=Array.isArray(value.rounds)?value.rounds:[];
 const rules:any[]=Array.isArray(value.split_rules)?value.split_rules:[];
 const [entry,setEntry]=useState('');
 const [expandedPreview,setExpandedPreview]=useState<string|null>(null);
 const patch=(key:string,next:any)=>onChange({...value,[key]:next});
 const updateExpense=(ei:number,change:(e:any)=>any)=>patch('expenses',expenses.map((e,i)=>i===ei?change(e):e));
 const itemRules=(ei:number,ii:number)=>rules.filter(r=>r.expense_index===ei&&r.item_index===ii);
 const replaceRule=(ei:number,ii:number,next:any|null)=>patch('split_rules',[...rules.filter(r=>r.expense_index!==ei||r.item_index!==ii),...(next?[next]:[])]);
  // 분담자 변경 시 해당 항목의 exclude 예외도 함께 정리해 UI와 서버 의미를 맞춘다.
  const setItemMembers=(ei:number,ii:number,r:any,nextMembers:string[])=>{
   const oldExceptions:any[]=Array.isArray(value.exceptions)?value.exceptions:[];
   const nextExceptions=oldExceptions.filter(x=>!(x.expense_index===ei&&x.item_index===ii&&x.kind==='exclude'));
   const nextRule={...r,participant_names:nextMembers};
   if(r.method==='explicit_amount')nextRule.individual_amounts=nextMembers.map(p=>(r.individual_amounts||[]).find((x:any)=>x.participant_name===p)||{participant_name:p,amount:null});
   if(nextRule.remainder_payer_name&&!nextMembers.includes(nextRule.remainder_payer_name))delete nextRule.remainder_payer_name;
   onChange({...value,split_rules:[...rules.filter(x=>x.expense_index!==ei||x.item_index!==ii),nextRule],exceptions:nextExceptions});
  };
 const defaultRule=(ei:number,ii:number)=>({expense_index:ei,item_index:ii,method:'equal',participant_names:[] as string[]});
 const removeItem=(ei:number,ii:number)=>{
  const nextExpenses=expenses.map((e,i)=>i===ei?{...e,items:(e.items||[]).filter((_:any,j:number)=>j!==ii)}:e);
  const nextRules=rules.filter(r=>!(r.expense_index===ei&&r.item_index===ii)).map(r=>r.expense_index===ei&&r.item_index>ii?{...r,item_index:r.item_index-1}:r);
  const nextExceptions=(value.exceptions||[]).filter((x:any)=>!(x.expense_index===ei&&x.item_index===ii)).map((x:any)=>x.expense_index===ei&&x.item_index>ii?{...x,item_index:x.item_index-1}:x);
  const nextContributions=(value.contributions||[]).map((c:any)=>c.expense_index===ei?{...c,uses:(c.uses||[]).filter((u:any)=>u.item_index!==ii).map((u:any)=>u.item_index>ii?{...u,item_index:u.item_index-1}:u)}:c);
  onChange({...value,expenses:nextExpenses,split_rules:nextRules,...('exceptions' in value?{exceptions:nextExceptions}:{}),...('contributions' in value?{contributions:nextContributions}:{})});
 };
 const removeExpense=(ei:number)=>{
  const reindex=(xs:any[])=>xs.filter(x=>x.expense_index!==ei).map(x=>x.expense_index>ei?{...x,expense_index:x.expense_index-1}:x);
  onChange({...value,expenses:expenses.filter((_,i)=>i!==ei),split_rules:reindex(rules),...('exceptions' in value?{exceptions:reindex(value.exceptions||[])}:{}),...('contributions' in value?{contributions:reindex(value.contributions||[])}:{})});
 };
 return <View style={{gap:10}}>
  <Text style={styles.subhead}>참여자</Text>
  <View style={{flexDirection:'row',gap:8}}><TextInput style={[styles.input,{flex:1}]} value={entry} onChangeText={setEntry} placeholder="이름을 입력하세요"/><Pressable style={[styles.btn,{marginTop:0,minWidth:45}]} onPress={()=>{const n=entry.trim();if(n&&!people.includes(n))patch('participants',[...people,n]);setEntry('');}}><Text style={styles.btnText}>＋</Text></Pressable></View>
  <View style={styles.wrap}>{people.map(p=><Pressable key={p} style={styles.addPill} onPress={()=>patch('participants',people.filter(x=>x!==p))}><Text style={styles.addPillText}>{p}  ×</Text></Pressable>)}</View>
  <Text style={styles.helper}>참여자를 삭제하면 해당 이름이 포함된 차수·분담 규칙·결제자도 확인해야 해요.</Text>
  <View style={styles.divider}/><Text style={styles.subhead}>차수 및 참석자</Text>
  {rounds.map((r,i)=><View key={i} style={styles.arrayRow}><View style={styles.rowBetween}><Text style={styles.subhead}>{r.round_number??i+1}차</Text><Pressable onPress={()=>patch('rounds',rounds.filter((_,j)=>j!==i))}><Text style={styles.deleteText}>삭제</Text></Pressable></View><Field label="차수 번호" numeric value={String(r.round_number??i+1)} onChange={t=>patch('rounds',rounds.map((x,j)=>i===j?{...x,round_number:Number(t)||1}:x))}/><Text style={styles.label}>참석자 선택</Text><View style={styles.wrap}>{people.map(p=><Chip key={p} text={p} active={(r.participant_names||[]).includes(p)} onPress={()=>patch('rounds',rounds.map((x,j)=>{if(i!==j)return x;const old:string[]=x.participant_names||[];return {...x,participant_names:old.includes(p)?old.filter(n=>n!==p):[...old,p]};}))}/>)}</View></View>)}
  <Button text="＋ 차수 추가" secondary onPress={()=>patch('rounds',[...rounds,{round_number:Math.max(0,...rounds.map(r=>Number(r.round_number)||0))+1,participant_names:[...people]}])}/>
  <Text style={styles.helper}>원문에 차수가 없으면 반드시 추가할 필요는 없어요. 차수를 추가하면 각 결제의 차수도 지정해 주세요.</Text>
  <View style={styles.divider}/><Text style={styles.subhead}>결제 항목 및 분담 규칙</Text>
  {expenses.map((e,ei)=><View key={ei} style={styles.arrayRow}>
   <View style={styles.rowBetween}><Text style={styles.subhead}>결제 {ei+1}</Text><Pressable onPress={()=>removeExpense(ei)}><Text style={styles.deleteText}>삭제</Text></Pressable></View>
   <Text style={styles.label}>결제자 선택</Text><View style={styles.wrap}>{people.map(p=><Chip key={p} text={p} active={e.payer_name===p} onPress={()=>updateExpense(ei,x=>({...x,payer_name:p}))}/>)}</View>
   {!people.includes(e.payer_name)&&<Text style={styles.issue}>결제자를 선택해 주세요.</Text>}
   <Field label="총액 (원)" numeric value={String(e.total_amount??'')} onChange={t=>updateExpense(ei,x=>({...x,total_amount:t===''?null:Number(t.replace(/,/g,''))||0}))}/>
   {rounds.length>0&&<><Text style={styles.label}>차수 선택</Text><View style={styles.wrap}>{rounds.map((r,i)=><Chip key={i} text={`${r.round_number}차`} active={e.round_number===r.round_number} onPress={()=>updateExpense(ei,x=>({...x,round_number:r.round_number}))}/>)}</View></>}
   {(e.items||[]).length>0&&Number.isFinite(Number(e.total_amount))&&((e.items||[]).reduce((v:number,x:any)=>v+(Number(x.amount)||0),0)!==Number(e.total_amount))&&<Text style={styles.issue}>항목 합계 {money((e.items||[]).reduce((v:number,x:any)=>v+(Number(x.amount)||0),0))}와 결제 총액 {money(e.total_amount)}가 달라요.</Text>}
   {(e.items||[]).map((item:any,ii:number)=>{
    const matching=itemRules(ei,ii);const r=matching[0];const members:string[]=r?.participant_names||[];const effectiveMembers=effectiveMembersFor(r,value.exceptions||[],ei,ii);
    const method=r?.method;
    const preview=previewItem(item,r,value.contributions||[],value.exceptions||[],ei,ii);
    const roundMembers:string[]=rounds.find(x=>x.round_number===e.round_number)?.participant_names||people;
    const selectable=roundMembers.filter(p=>people.includes(p));
    const previewKey=`${ei}-${ii}`;
    const relatedExceptions=(value.exceptions||[]).filter((x:any)=>x.expense_index===ei&&x.item_index===ii);
    const itemContribution=(value.contributions||[]).reduce((sum:number,c:any)=>sum+(c.expense_index===ei?(c.uses||[]).reduce((v:number,u:any)=>v+(u.item_index===ii?Number(u.amount||0):0),0):0),0);
    return <View key={ii} style={styles.arrayRow}>
     <View style={styles.rowBetween}><Text style={styles.subhead}>항목 {ii+1} · {item.name||'이름 미정'}</Text><Pressable onPress={()=>removeItem(ei,ii)}><Text style={styles.deleteText}>항목 삭제</Text></Pressable></View>
     <Field label="항목명" value={item.name||''} onChange={t=>updateExpense(ei,x=>({...x,items:x.items.map((y:any,j:number)=>j===ii?{...y,name:t}:y)}))}/>
     <Field label="항목 금액 (원)" numeric value={String(item.amount??'')} onChange={t=>updateExpense(ei,x=>({...x,items:x.items.map((y:any,j:number)=>j===ii?{...y,amount:t===''?null:Number(t.replace(/,/g,''))||0}:y)}))}/>
     {matching.length>1&&<Text style={styles.issue}>분담 규칙이 중복되어 있어요. 아래에서 하나로 정리해 주세요.</Text>}
     {!r?<><Text style={styles.issue}>이 항목의 분담 규칙이 없어요.</Text><Button text="＋ 이 항목의 분담 규칙 추가" onPress={()=>replaceRule(ei,ii,defaultRule(ei,ii))}/></>:<>
      <Text style={styles.label}>분담 방식</Text><View style={styles.wrap}><Chip text="균등 분담" active={method==='equal'} onPress={()=>replaceRule(ei,ii,{...r,method:'equal',individual_amounts:undefined})}/><Chip text="개인별 금액 지정" active={method==='explicit_amount'} onPress={()=>replaceRule(ei,ii,{...r,method:'explicit_amount',individual_amounts:members.map(p=>({participant_name:p,amount:null}))})}/></View>
      <Text style={styles.label}>이 항목을 실제 부담하는 사람 (제외 예외 반영)</Text><View style={styles.wrap}>{people.map(p=><Chip key={p} text={p} active={effectiveMembers.includes(p)} onPress={()=>{const next=effectiveMembers.includes(p)?effectiveMembers.filter(x=>x!==p):[...effectiveMembers,p];setItemMembers(ei,ii,r,next);}}/>)}</View>
       {relatedExceptions.some((x:any)=>x.kind==='exclude')&&<Text style={styles.helper}>제외 예외가 적용된 사람이 선택 해제되어 있어요. 선택을 변경하면 이 항목의 제외 예외는 정리되고, 선택한 분담자 명단으로 저장됩니다.</Text>}
      <View style={styles.wrap}><Button text="해당 차수 모두 선택" secondary small onPress={()=>setItemMembers(ei,ii,r,[...selectable])}/><Button text="모두 해제" secondary small onPress={()=>setItemMembers(ei,ii,r,[])}/></View>
      {!effectiveMembers.length&&<Text style={styles.issue}>최소 한 명의 실제 분담자를 선택해 주세요.</Text>}
      {method==='equal'&&effectiveMembers.length>0&&Number(item.amount)-itemContribution>=0&&((Number(item.amount)-itemContribution)%effectiveMembers.length!==0)&&<><Text style={styles.label}>나머지 원 단위 부담자</Text><View style={styles.wrap}>{effectiveMembers.map(p=><Chip key={'remainder'+p} text={p} active={r.remainder_payer_name===p} onPress={()=>replaceRule(ei,ii,{...r,remainder_payer_name:p})}/>)}</View></>}
      <Pressable onPress={()=>setExpandedPreview(v=>v===previewKey?null:previewKey)} style={styles.previewHeader}><Text style={styles.previewTitle}>예상 분담액 {expandedPreview===previewKey?'접기 ▲':'펼치기 ▼'}</Text><Text style={styles.muted}>{effectiveMembers.length}명</Text></Pressable>
      {expandedPreview===previewKey&&<View style={styles.previewBody}>
       {itemContribution>0&&<Text style={styles.muted}>찬조금 적용: {money(itemContribution)} 차감</Text>}
       {preview.error?<Text style={styles.issue}>{preview.error}</Text>:null}
       {preview.shares.map(x=><View key={x.name} style={styles.infoRow}><Text style={styles.infoLabel}>{x.name}</Text><Text style={styles.infoValue}>{money(x.amount)}</Text></View>)}
       {relatedExceptions.length>0&&<Text style={styles.helper}>개인별 예외 {relatedExceptions.length}건: 제외 예외는 미리보기에 반영됩니다. 다른 예외와 최종 잔액 배분은 서버 계산을 확인하세요.</Text>}
       <Text style={styles.helper}>미리보기는 확정 송금액이 아니며, 서버 검증 및 계산이 최종 기준입니다.</Text>
      </View>}

      {method==='explicit_amount'&&<>{effectiveMembers.map(p=>{const amount=(r.individual_amounts||[]).find((x:any)=>x.participant_name===p)?.amount;return <Field key={p} label={`${p}의 부담 금액 (원)`} numeric value={amount==null?'':String(amount)} onChange={t=>replaceRule(ei,ii,{...r,individual_amounts:effectiveMembers.map(n=>({participant_name:n,amount:n===p?(t===''?null:Number(t.replace(/,/g,''))||0):((r.individual_amounts||[]).find((x:any)=>x.participant_name===n)?.amount??null)}))})}/>;})}<Text style={styles.helper}>개인별 금액 합계가 항목 금액과 같아야 해요.</Text></>}
      <Button text="분담 규칙 삭제" secondary small onPress={()=>replaceRule(ei,ii,null)}/>
     </>}
    </View>;
   })}
   <Button text="＋ 항목 추가" secondary small onPress={()=>updateExpense(ei,x=>({...x,items:[...(x.items||[]),{name:'',amount:0}]}))}/>
  </View>)}
  <Button text="＋ 결제 추가" secondary onPress={()=>patch('expenses',[...expenses,{payer_name:null,total_amount:0,items:[{name:'',amount:0}]}])}/>
  <Text style={styles.helper}>금액과 분담 대상은 원문을 확인해 직접 지정하세요. 찬조금과 개인별 예외는 이 화면 상단의 전용 편집기에서 수정할 수 있어요.</Text>
 </View>;
}

// 검증 오류는 자동으로 의미를 추측하지 않는다. 사용자가 원문과 대조하여 수정한다.
function ConditionEditor({value,onChange,focus}:{value:Json;onChange:(next:Json)=>void;focus:{section:string;index:number}|null}){
 const [expanded,setExpanded]=useState<string|null>(focus?`${focus.section}:${focus.index}`:null);
 useEffect(()=>{if(focus)setExpanded(`${focus.section}:${focus.index}`);},[focus?.section,focus?.index]);
 const update=(section:'contributions'|'exceptions',index:number,changes:Json)=>{
  const rows=clone(Array.isArray(value[section])?value[section]:[]);
  rows[index]={...rows[index],...changes};onChange({...value,[section]:rows});
 };
 const remove=(section:'contributions'|'exceptions',index:number)=>{
  const rows=(value[section]||[]).filter((_:any,i:number)=>i!==index);
  onChange({...value,[section]:rows});
 };
 const expenses:any[]=value.expenses||[];
 const people:string[]=value.participants||[];
 const contributionRows:any[]=value.contributions||[];
 const exceptionRows:any[]=value.exceptions||[];
 return <View style={{gap:12}}>
  <Text style={styles.subhead}>찬조금 · 전달 확인과 적용 금액</Text>
  {contributionRows.map((c,i)=>{
   const key=`contributions:${i}`,open=expanded===key;
   const ei=Number.isInteger(c.expense_index)?c.expense_index:-1;
   const items:any[]=expenses[ei]?.items||[];
   const uses:any[]=Array.isArray(c.uses)?c.uses:[];
   const used=uses.reduce((n:number,u:any)=>n+(Number(u.amount)||0),0);
   const setUse=(ii:number,text:string)=>{
    const amount=text.trim()===''?null:Number(text.replace(/,/g,''));
    const next=uses.filter((u:any)=>u.item_index!==ii);
    if(amount!==null)next.push({item_index:ii,amount});
    update('contributions',i,{uses:next.sort((a:any,b:any)=>a.item_index-b.item_index)});
   };
   return <View key={key} style={styles.editorGroup}>
    <Pressable onPress={()=>setExpanded(open?null:key)}><Text style={styles.subhead}>{c.contributor_name||'찬조자 미확인'} · {money(c.amount)} {open?'▲':'▼'}</Text></Pressable>
    <Text style={styles.helper}>적용 합계 {money(used)} / 찬조 총액 {money(c.amount)} · 전달 확인 {String(c.funding_note||'').trim()?'입력됨':'필요'}</Text>
    {open&&<>
     <Field label="찬조자" value={String(c.contributor_name||'')} onChange={t=>update('contributions',i,{contributor_name:t})}/>
     <Field label="찬조금 (원)" numeric value={c.amount==null?'':String(c.amount)} onChange={t=>update('contributions',i,{amount:t.trim()===''?null:Number(t.replace(/,/g,''))})}/>
     <Text style={styles.label}>적용할 결제</Text>
     <View style={styles.wrap}>{expenses.map((e,idx)=><Chip key={idx} text={`${idx+1}번 · ${e.description||money(e.total_amount)}`} active={ei===idx} onPress={()=>update('contributions',i,{expense_index:idx,uses:[]})}/>)}</View>
     <Field label="전달·충당 확인 메모 (실제 확인한 내용만)" multiline value={String(c.funding_note||'')} placeholder="예: 결제자에게 50,000원을 송금한 사실을 확인함" onChange={t=>update('contributions',i,{funding_note:t})}/>
     <Text style={styles.label}>항목별 찬조금 적용액</Text>
     {items.map((it,ii)=>{
      const u=uses.find((x:any)=>x.item_index===ii);
      return <Field key={ii} numeric label={`${it.name||`항목 ${ii+1}`} (항목 금액 ${money(it.amount)})`} value={u?.amount==null?'':String(u.amount)} placeholder="적용하지 않으면 비워 두세요" onChange={t=>setUse(ii,t)}/>;
     })}
     {ei<0&&<Text style={styles.issue}>먼저 찬조금을 적용할 결제를 선택해 주세요.</Text>}
     {Number.isFinite(Number(c.amount))&&used!==Number(c.amount)&&<Text style={styles.issue}>적용 합계가 찬조금과 {money(Math.abs(used-Number(c.amount)))} 차이 납니다.</Text>}
     <Button text="이 찬조금 기록 삭제" danger secondary onPress={()=>Alert.alert('찬조금 삭제','이 찬조금 기록을 삭제할까요?',[{text:'취소',style:'cancel'},{text:'삭제',style:'destructive',onPress:()=>remove('contributions',i)}])}/>
    </>}
   </View>;
  })}
  {!contributionRows.length&&<Text style={styles.helper}>입력된 찬조금이 없습니다.</Text>}
  <Text style={styles.subhead}>개인별 예외 · 대상 항목과 방식</Text>
  {exceptionRows.map((ex,i)=>{
   const key=`exceptions:${i}`,open=expanded===key;
   const ei=Number.isInteger(ex.expense_index)?ex.expense_index:-1;
   const items:any[]=expenses[ei]?.items||[];
   return <View key={key} style={styles.editorGroup}>
    <Pressable onPress={()=>setExpanded(open?null:key)}><Text style={styles.subhead}>{ex.participant_name||'대상자 미확인'} · {ei>=0?`${ei+1}번 결제`:'결제 미확인'} {open?'▲':'▼'}</Text></Pressable>
    <Text style={styles.helper}>방식: {ENUM[String(ex.kind)]||'미확정'} · 항목: {items[ex.item_index]?.name||'미확정'}</Text>
    {open&&<>
     <Text style={styles.label}>예외 대상자</Text>
     <View style={styles.wrap}>{people.map(p=><Chip key={p} text={p} active={ex.participant_name===p} onPress={()=>update('exceptions',i,{participant_name:p})}/>)}</View>
     <Text style={styles.label}>결제 선택</Text>
     <View style={styles.wrap}>{expenses.map((e,idx)=><Chip key={idx} text={`${idx+1}번 · ${e.description||money(e.total_amount)}`} active={ei===idx} onPress={()=>update('exceptions',i,{expense_index:idx,item_index:null})}/>)}</View>
     <Text style={styles.label}>항목 선택</Text>
     <View style={styles.wrap}>{items.map((it,ii)=><Chip key={ii} text={`${it.name||`항목 ${ii+1}`} (${money(it.amount)})`} active={ex.item_index===ii} onPress={()=>update('exceptions',i,{item_index:ii})}/>)}</View>
     <Text style={styles.label}>예외 방식</Text>
     <View style={styles.wrap}>{(['exclude','fixed_amount','covered_by_other'] as const).map(k=><Chip key={k} text={ENUM[k]} active={ex.kind===k} onPress={()=>update('exceptions',i,{kind:k,fixed_amount:k==='fixed_amount'?(ex.fixed_amount??null):null,covered_by_name:k==='covered_by_other'?(ex.covered_by_name??null):null})}/>)}</View>
     {ex.kind==='fixed_amount'&&<Field numeric label="이 항목에서 본인이 부담할 금액 (원)" value={ex.fixed_amount==null?'':String(ex.fixed_amount)} onChange={t=>update('exceptions',i,{fixed_amount:t.trim()===''?null:Number(t.replace(/,/g,''))})}/>}
     {ex.kind==='covered_by_other'&&<><Text style={styles.label}>대신 부담하는 사람</Text><View style={styles.wrap}>{people.filter(p=>p!==ex.participant_name).map(p=><Chip key={p} text={p} active={ex.covered_by_name===p} onPress={()=>update('exceptions',i,{covered_by_name:p})}/>)}</View></>}
     <Field label="예외 사유 / 확인 근거" multiline value={String(ex.reason||'')} onChange={t=>update('exceptions',i,{reason:t})}/>
     <Text style={styles.helper}>3만 원을 보태겠다는 말이 찬조인지 개인 부담인지 불분명하면 원문을 확인한 뒤 방식을 선택하세요. 자동으로 추정하지 않습니다.</Text>
     <Button text="이 예외 기록 삭제" danger secondary onPress={()=>Alert.alert('예외 삭제','이 예외 기록을 삭제할까요?',[{text:'취소',style:'cancel'},{text:'삭제',style:'destructive',onPress:()=>remove('exceptions',i)}])}/>
    </>}
   </View>;
  })}
  {!exceptionRows.length&&<Text style={styles.helper}>입력된 개인별 예외가 없습니다.</Text>}
 </View>;
}

export default function HomeScreen(){
 const [splash,setSplash]=useState(true);const [docsById,setDocsById]=useState<Record<string,Session>>({});const [page,setPage]=useState<Page>('home');const [mode,setMode]=useState<InputMode>('ai');const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');const [history,setHistory]=useState<SessionSummary[]>([]);const [meta,setMeta]=useState<MetaMap>({});const [hydrated,setHydrated]=useState(false);
 const [doc,setDoc]=useState<Session|null>(null);const [draft,setDraft]=useState<Json|null>(null);const [dirty,setDirty]=useState(false);const [calculation,setCalculation]=useState<Calculation|null>(null);const [schema,setSchema]=useState<Json|null>(null);
 const [title,setTitle]=useState('');const [aiText,setAiText]=useState('');const [manualPeople,setManualPeople]=useState<string[]>([]);const [personEntry,setPersonEntry]=useState('');const [manualKind,setManualKind]=useState<'equal'|'diff'>('equal');const [diffTransfers,setDiffTransfers]=useState<DiffTransfer[]>([{from:'',to:'',amount:''}]);const [localDiffs,setLocalDiffs]=useState<Record<string,LocalDiff>>({});const [diffHydrated,setDiffHydrated]=useState(false);
 const [selectedImage, setSelectedImage] = useState<{
  uri: string;
  mimeType: string;
  name: string;
} | null>(null);

const [imagePreview, setImagePreview] =
  useState<ImagePreview | null>(null);

const [imageItems, setImageItems] =
  useState<Array<{ name: string; amount: string }>>([]);

const [imageTotal, setImageTotal] = useState('');

const [imageNotes, setImageNotes] = useState('');
 const [sourceEditing,setSourceEditing]=useState(false);
 const [sourceEvidence,setSourceEvidence]=useState<string|null>(null);
 const [manualPayer,setManualPayer]=useState('');const [manualItem,setManualItem]=useState('식사비');const [manualAmount,setManualAmount]=useState('');const [manualRound,setManualRound]=useState('1');
  const [reminderOpenKey,setReminderOpenKey]=useState<string|null>(null);
 const [editorFocus,setEditorFocus]=useState<{section:string;index:number}|null>(null);
 const [paymentFilter,setPaymentFilter]=useState<PaymentFilter>('all');const [showAdvanced,setShowAdvanced]=useState(false);const [menuSid,setMenuSid]=useState<string|null>(null);const [checks,setChecks]=useState<Record<string,boolean>>({});const [reviewer,setReviewer]=useState('');const [reviewNote,setReviewNote]=useState('조건 확인 완료');

 // Stage 1: local drafts, hardware back navigation, and duplicate-request guard.
 const [draftsHydrated,setDraftsHydrated]=useState(false);
 const [savedCreateDraft,setSavedCreateDraft]=useState<any|null>(null);
 const [savedEditDraft,setSavedEditDraft]=useState<{sessionId:string;inputRevision:number;draft:Json}|null>(null);
 const [createDraftEnabled,setCreateDraftEnabled]=useState(false);
 const busyLock=useRef(false);
 const backActionRef=useRef<()=>boolean>(()=>true);
 const hasCreateContent=Boolean(title.trim()||aiText.trim()||selectedImage||manualPeople.length||personEntry.trim()||manualAmount.trim()||manualPayer.trim()||diffTransfers.some(t=>t.from||t.to||t.amount));
 const snapshotCreate=()=>({title,aiText,mode,manualPeople,personEntry,manualKind,diffTransfers,manualPayer,manualItem,manualAmount,manualRound});
 const restoreCreate=(s:any)=>{
  setTitle(s.title||'');setAiText(s.aiText||'');setMode(s.mode==='custom'?'custom':'ai');
  setManualPeople(Array.isArray(s.manualPeople)?s.manualPeople:[]);setPersonEntry(s.personEntry||'');
  setManualKind(s.manualKind==='diff'?'diff':'equal');setDiffTransfers(Array.isArray(s.diffTransfers)&&s.diffTransfers.length?s.diffTransfers:[{from:'',to:'',amount:''}]);
  setManualPayer(s.manualPayer||'');setManualItem(s.manualItem||'식사비');setManualAmount(s.manualAmount||'');setManualRound(s.manualRound||'1');
  setSelectedImage(null);setCreateDraftEnabled(true);setPage('create');
 };
 const clearCreateDraft=()=>{setSavedCreateDraft(null);AsyncStorage.removeItem(CREATE_DRAFT_STORAGE).catch(()=>{});};
 const clearEditDraft=()=>{setSavedEditDraft(null);AsyncStorage.removeItem(EDIT_DRAFT_STORAGE).catch(()=>{});};
 useEffect(()=>{
  let mounted=true;
  Promise.all([AsyncStorage.getItem(CREATE_DRAFT_STORAGE),AsyncStorage.getItem(EDIT_DRAFT_STORAGE)])
   .then(([a,b])=>{if(!mounted)return;try{if(a)setSavedCreateDraft(JSON.parse(a));}catch{}try{if(b)setSavedEditDraft(JSON.parse(b));}catch{}})
   .finally(()=>{if(mounted)setDraftsHydrated(true);});
  return()=>{mounted=false;};
 },[]);
 useEffect(()=>{
  if(!draftsHydrated||!createDraftEnabled||page!=='create')return;
  const snapshot=hasCreateContent?snapshotCreate():null;
  const timer=setTimeout(()=>{
   if(snapshot){AsyncStorage.setItem(CREATE_DRAFT_STORAGE,JSON.stringify(snapshot)).then(()=>setSavedCreateDraft(snapshot)).catch(()=>{});}
   else clearCreateDraft();
  },450);
  return()=>clearTimeout(timer);
 },[draftsHydrated,createDraftEnabled,page,title,aiText,mode,manualPeople,personEntry,manualKind,diffTransfers,manualPayer,manualItem,manualAmount,manualRound,selectedImage]);
 useEffect(()=>{
  if(!draftsHydrated||page!=='edit'||!doc||!draft||!dirty)return;
  const snapshot={sessionId:doc.session_id,inputRevision:doc.revisions[doc.revisions.length-1].input_revision,draft};
  const timer=setTimeout(()=>{AsyncStorage.setItem(EDIT_DRAFT_STORAGE,JSON.stringify(snapshot)).then(()=>setSavedEditDraft(snapshot)).catch(()=>{});},450);
  return()=>clearTimeout(timer);
 },[draftsHydrated,page,doc,draft,dirty]);
 const navigateBack=()=>{
  Keyboard.dismiss();
  if(busyLock.current)return true;
  if(page==='home'){
   Alert.alert('앱 종료','모아정산을 종료할까요?',[
    {text:'취소',style:'cancel'},
    {text:'종료',onPress:()=>BackHandler.exitApp()},
   ]);return true;
  }
  if(page==='create'){
   if(hasCreateContent){
    Alert.alert('작성 중인 정산','입력 내용은 임시 저장됩니다. 홈으로 이동할까요?',[
     {text:'계속 작성',style:'cancel'},
     {text:'홈으로',onPress:()=>{AsyncStorage.setItem(CREATE_DRAFT_STORAGE,JSON.stringify(snapshotCreate())).catch(()=>{});setPage('home');setCreateDraftEnabled(false);}},
    ]);
   }else{setPage('home');setCreateDraftEnabled(false);}
   return true;
  }
  if(page==='imageReview'){setPage('create');return true;}
  if(page==='edit'){
   if(dirty){
    Alert.alert('저장하지 않은 수정 내용','수정 내용은 임시 저장됩니다. 검수 화면으로 이동할까요?',[
     {text:'계속 수정',style:'cancel'},
     {text:'검수 화면으로',onPress:()=>{if(doc&&draft)AsyncStorage.setItem(EDIT_DRAFT_STORAGE,JSON.stringify({sessionId:doc.session_id,inputRevision:doc.revisions[doc.revisions.length-1].input_revision,draft})).catch(()=>{});setPage('review');}},
    ]);
   }else setPage('review');
   return true;
  }
  if(page==='detail'){setPage('home');return true;}
  if(page==='review'){setPage('home');return true;}
  return true;
 };
 backActionRef.current=navigateBack;
 useEffect(()=>{
  if(Platform.OS!=='android')return;
  const subscription=BackHandler.addEventListener('hardwareBackPress',()=>backActionRef.current());
  return()=>subscription.remove();
 },[]);
 const rev=doc?.revisions?.[doc.revisions.length-1];const ctx=rev?.context||{};const issues=rev?.issues||[];
 // 같은 찬조금의 '적용 항목 누락' 오류만 화면에서 하나로 합친다.
 // 원본 issues는 그대로 유지하여 미해결 오류가 정산 시작을 차단하도록 한다.
 const visibleIssues=issues.filter((issue:any,index:number,all:any[])=>{
  const path=String(issue.path||'');
  const contributionMatch=path.match(/^contributions\[(\d+)\]/);
  const missingUses=contributionMatch&&(issue.code==='missing_contribution_uses'||path.includes('.uses'));
  const identity=missingUses
   ? `contribution-uses:${contributionMatch[1]}`
   : `exact:${String(issue.code||'')}:${path}:${String(issue.question||issue.message||issue.reason||'')}`;
  return all.findIndex((other:any)=>{
   const otherPath=String(other.path||'');
   const otherMatch=otherPath.match(/^contributions\[(\d+)\]/);
   const otherMissing=otherMatch&&(other.code==='missing_contribution_uses'||otherPath.includes('.uses'));
   const otherIdentity=otherMissing
    ? `contribution-uses:${otherMatch[1]}`
    : `exact:${String(other.code||'')}:${otherPath}:${String(other.question||other.message||other.reason||'')}`;
   return identity===otherIdentity;
  })===index;
 });
 const active=[...history,...Object.values(localDiffs).map(x=>({session_id:x.session.session_id,title:meta[x.session.session_id]?.title||'차액 정산'}))].filter(s=>!meta[s.session_id]?.deleted);
 const total=(d:Session)=>{const c=d.revisions[d.revisions.length-1].context;return (c.expenses||[]).reduce((sum:number,e:any)=>sum+(Number(e.total_amount)||0),0)};
 const lastCalculation=(d:Session)=>[...(d.calculations||[])].reverse().find(c=>c.input_revision===d.revisions[d.revisions.length-1].input_revision)||null;
 const load=useCallback((d:Session,target:Page='review')=>{
  setDoc(d);setDraft(clone(d.revisions[d.revisions.length-1].context));setDirty(false);setChecks({});setReviewer('');setReviewNote('조건 확인 완료');setCalculation(lastCalculation(d));setPaymentFilter('all');setReminderOpenKey(null);setPage(target);
  const revision=d.revisions[d.revisions.length-1].input_revision;
  AsyncStorage.getItem(EDIT_DRAFT_STORAGE).then(raw=>{
   if(!raw)return;
   try{
    const saved=JSON.parse(raw);
    if(saved.sessionId!==d.session_id||saved.inputRevision!==revision)return;
    Alert.alert('수정 내용 복구','이 정산에서 저장하지 않은 수정 내용이 있습니다.',[
     {text:'삭제',style:'destructive',onPress:()=>clearEditDraft()},
     {text:'복구',onPress:()=>{setDraft(saved.draft);setDirty(true);setPage('edit');}},
    ]);
   }catch{}
  }).catch(()=>{});
 },[]);
 const refresh=useCallback(async()=>{
  const list=await sessionApi.list();setHistory(list);
  const loaded:Record<string,Session>={};
  for(let i=0;i<list.length;i+=8){
    const chunk=await Promise.allSettled(list.slice(i,i+8).map(s=>sessionApi.get(s.session_id)));
    chunk.forEach((r,j)=>{if(r.status==='fulfilled')loaded[list[i+j].session_id]=r.value;});
  }
  setDocsById(loaded);
 },[]);
 useEffect(()=>{const timer=setTimeout(()=>setSplash(false),1100);return()=>clearTimeout(timer);},[]);
 useEffect(()=>{(async()=>{try{const stored=await AsyncStorage.getItem(STORAGE);if(stored)setMeta(JSON.parse(stored));}catch{}finally{setHydrated(true);}})();},[]);
 useEffect(()=>{if(!hydrated)return;AsyncStorage.setItem(STORAGE,JSON.stringify(meta)).catch(()=>{});},[meta,hydrated]);
 useEffect(()=>{AsyncStorage.getItem(DIFF_STORAGE).then(v=>{if(v)setLocalDiffs(JSON.parse(v));}).catch(()=>{}).finally(()=>setDiffHydrated(true));},[]);
 useEffect(()=>{if(!diffHydrated)return;AsyncStorage.setItem(DIFF_STORAGE,JSON.stringify(localDiffs)).catch(()=>{});},[localDiffs,diffHydrated]);
 useEffect(()=>{refresh().catch(e=>setMessage('서버 연결 실패: '+String(e?.message||e)));sessionApi.schema().then(setSchema).catch(()=>{});},[refresh]);
 const run=async(fn:()=>Promise<void>)=>{if(busyLock.current)return;busyLock.current=true;setBusy(true);try{await fn();}catch(e:any){Alert.alert('확인해 주세요',String(e?.message||e));}finally{busyLock.current=false;setBusy(false);}};
 const setLocal=(sid:string,patch:Partial<LocalMeta>)=>setMeta(prev=>({...prev,[sid]:{...prev[sid],...patch}}));
 const startNew=()=>{
  const fresh=()=>{setDoc(null);setDraft(null);setCalculation(null);setTitle('');setAiText('');setSelectedImage(null);setImagePreview(null);setManualPeople([]);setPersonEntry('');setDiffTransfers([{from:'',to:'',amount:''}]);setManualKind('equal');setMode('ai');setManualPayer('');setManualItem('식사비');setManualAmount('');setManualRound('1');setMessage('');setSourceEditing(false);setSourceEvidence(null);setCreateDraftEnabled(true);setPage('create');};
  AsyncStorage.getItem(CREATE_DRAFT_STORAGE).then(raw=>{
   if(!raw){fresh();return;}
   try{
    const saved=JSON.parse(raw);
    Alert.alert('이전 입력 복구','작성 중이던 정산 내용이 있습니다. 이어서 작성할까요?',[
     {text:'새로 작성',onPress:()=>{clearCreateDraft();fresh();}},
     {text:'이어서 작성',onPress:()=>{fresh();restoreCreate(saved);}},
    ]);
   }catch{fresh();}
  }).catch(fresh);
 };
 const afterCreate=async(d:Session)=>{if(title.trim())setLocal(d.session_id,{title:title.trim()});setCreateDraftEnabled(false);clearCreateDraft();load(d,'review');await refresh();setMessage('추출된 조건을 확인한 뒤 정산을 시작하세요.');};
 const createAI=()=>run(async()=>{
  if(sourceEditing){
   if(!aiText.trim())throw new Error('정산 상황을 입력해 주세요.');
   const d=sourceEvidence?await confirmImage(aiText.trim(),sourceEvidence):await sessionApi.ai(aiText.trim());
   setSourceEditing(false);setSourceEvidence(null);await afterCreate(d);return;
  }
  if(!aiText.trim()&&!selectedImage)throw new Error('정산 상황이나 사진을 입력해 주세요.');
  if(!selectedImage){await afterCreate(await sessionApi.ai(aiText.trim()));return;}
  const result=await previewImage(selectedImage,aiText.trim());
  setImagePreview(result);
  setImageItems(result.items.map(x=>({name:x.name,amount:x.amount===null?'':String(x.amount)})));
  setImageTotal(result.total_amount===null?'':String(result.total_amount));
  setImageNotes(result.notes.join('\n'));
  setPage('imageReview');
 });
 const confirmReceipt=()=>run(async()=>{
  if(!imagePreview)throw new Error('이미지 분석 결과가 없습니다.');
  const total=safeAmount(imageTotal);
  if(!imageItems.length)throw new Error('항목을 하나 이상 입력해 주세요.');
  if(imageItems.some(x=>!x.name.trim()||!x.amount.trim()))throw new Error('항목명과 금액을 모두 확인해 주세요.');
  const rows=imageItems.map(x=>({name:x.name.trim(),amount:safeAmount(x.amount)}));
  if(rows.reduce((sum,x)=>sum+x.amount,0)!==total)throw new Error('항목 금액의 합계가 영수증 총액과 일치하지 않습니다.');
  const evidence=['[사용자가 사진과 대조하여 승인한 영수증 내역]',...rows.map(x=>`${x.name}: ${x.amount}원`),`영수증 총액: ${total}원`,imageNotes.trim()?`추가 확인 사항: ${imageNotes.trim()}`:''].filter(Boolean).join('\n');
  await afterCreate(await confirmImage(aiText.trim(),evidence));
  setImagePreview(null);
 });
 // 기존 원문과 검수된 영수증 증거를 보존한 채 다시 자연어 분석할 수 있다.
 const returnToOriginal=()=>{
  if(!doc)return;
  setAiText(doc.source_text||aiText);
  setSourceEvidence(doc.supplied_evidence||null);
  setMode('ai');setSourceEditing(true);setCreateDraftEnabled(true);
  setPage('create');
 };
 const issueIndex=(path:string,section:string)=>{
  const match=path.match(new RegExp('^'+section+'\\[(\\d+)\\]'));
  return match?Number(match[1]):-1;
 };
 const openIssueEditor=(issue:any)=>{
  const path=String(issue.path||'');
  const ci=issueIndex(path,'contributions');
  const xi=issueIndex(path,'exceptions');
  setEditorFocus(ci>=0?{section:'contributions',index:ci}:xi>=0?{section:'exceptions',index:xi}:null);
  setPage('edit');
 };
 const describeIssue=(issue:any)=>{
  const path=String(issue.path||'');
  const code=String(issue.code||'');
  const raw=String(issue.question||issue.message||issue.reason||'').trim();
  const ci=issueIndex(path,'contributions');
  const ri=issueIndex(path,'split_rules');
  const ei=issueIndex(path,'expenses');
  const pi=issueIndex(path,'participants');
  const c=ci>=0?ctx.contributions?.[ci]:null;
  const r=ri>=0?ctx.split_rules?.[ri]:null;
  const expIndex=r?.expense_index??c?.expense_index??ei;
  const expense=Number.isInteger(expIndex)?ctx.expenses?.[expIndex]:null;
  const item=expense?.items?.[r?.item_index];
  if(ci>=0){
   const name=c?.contributor_name||'찬조자';
   const amount=c?.amount!=null?money(c.amount):'금액 미확인';
   if(code==='missing_funding_note')return {title:`${name}님의 찬조금 전달·충당 확인`,detail:'찬조금을 실제로 누구에게 전달했거나 어떤 결제에 충당했는지 기록되지 않았어요.',hint:'찬조금 편집에서 전달·충당 확인 메모를 실제 확인한 사실대로 입력해 주세요.'};
   if(code==='missing_contribution_uses'||path.includes('.uses'))return {title:`${name}님의 찬조금 ${amount} 적용`,detail:`${expense?`${expense.round_number||'?'}차 결제`: '해당 결제'}에서 찬조금을 어떤 항목에 적용할지 정해야 해요.`,hint:'찬조금 편집에서 적용할 항목과 항목별 금액을 직접 지정해 주세요.'};
   return {title:`${name}님의 찬조금 ${amount} 확인`,detail:raw||`찬조금의 적용 방식 또는 입력값(${path})을 확인해야 해요.`,hint:'찬조자, 금액, 적용 항목을 직접 수정해 주세요.'};
  }
  if(ri>=0)return {title:`${item?.name||`분담 규칙 ${ri+1}`}의 정산 방식 확인`,detail:raw||`이 항목의 참여자와 분담 기준이 불명확해요. (${code||path})`,hint:'전체 참석자 균등 분담이 맞을 때만 선택하세요. 개인별 예외가 있으면 직접 수정해 주세요.'};
  if(ei>=0)return {title:`${expense?.items?.[0]?.name||`결제 ${ei+1}`} 내역 확인`,detail:raw||`결제 금액이나 항목 정보를 확인해 주세요. (${code||path})`,hint:'영수증의 항목별 금액과 결제 총액을 비교해 주세요.'};
  if(pi>=0)return {title:`${ctx.participants?.[pi]||`참여자 ${pi+1}`} 정보 확인`,detail:raw||'참여자 이름이나 정산 참여 여부를 확인해 주세요.',hint:'참여자 및 차수별 참석자를 직접 수정해 주세요.'};
  if(path.startsWith('rounds'))return {title:'차수별 참석자 확인',detail:raw||`차수 정보(${path})를 확인해야 해요.`,hint:'해당 차수에 실제 참여한 사람을 직접 선택해 주세요.'};
  if(path.startsWith('exceptions')){
   const xi=issueIndex(path,'exceptions');
   const ex=xi>=0?ctx.exceptions?.[xi]:null;
   const targetExpense=ex&&Number.isInteger(ex.expense_index)?ctx.expenses?.[ex.expense_index]:null;
   const targetItem=ex&&Number.isInteger(ex.item_index)?targetExpense?.items?.[ex.item_index]:null;
   const person=ex?.participant_name||'대상자 미확인';
   const kind=ex?.kind==='exclude'?'비용 분담 제외':ex?.kind==='fixed_amount'?'고정 금액 부담':ex?.kind==='covered_by_other'?'다른 사람 대신 부담':ex?.kind||'방식 미확인';
   const target=targetItem?.name|| (targetExpense?`${ex.expense_index+1}번 결제의 항목 미확인`:'결제·항목 미확인');
   const extra=ex?.reason||ex?.basis_note||ex?.note||'';
   return {title:`${person} · ${target} 예외 확인`,detail:`대상: ${person} / 항목: ${target} / 방식: ${kind}${ex?.fixed_amount!=null?` / 지정액: ${money(ex.fixed_amount)}`:''}${ex?.covered_by_name?` / 대신 부담: ${ex.covered_by_name}`:''}. ${extra?`기록된 사유: ${extra}`:raw||'적용 사유와 대상이 올바른지 확인해 주세요.'}`,hint:!ex||!targetItem?'대상자나 항목이 확정되지 않았어요. 직접 조건 수정에서 정확히 지정해 주세요.':'이 예외가 실제 합의 내용과 일치하는지 확인해 주세요.'};
  }
  return {title:raw?'정산 조건 확인':'확인할 정산 조건이 있어요',detail:raw||`검증 항목 ${code||path||'미지정'}의 내용을 확인해야 해요.`,hint:'세부 정산 조건을 열어 수정할 수 있어요.'};
 };
 const IssueResolver=({issue,index}:{issue:any;index:number})=>{
  const description=describeIssue(issue);
  return <View style={styles.editorGroup} key={`${issue.path}:${issue.code}:${index}`}>
   <Text style={styles.subhead}>{description.title}</Text>
   <Text style={styles.muted}>{description.detail}</Text>
   <Text style={styles.helper}>{description.hint}</Text>
   <Text style={styles.helper}>검증 코드: {issue.code||'unknown'} · 위치: {issue.path||'미지정'}</Text>
   <Button text="이 조건 직접 수정하기" secondary onPress={()=>openIssueEditor(issue)}/>
  </View>;
 };
 const createCustom=()=>run(async()=>{
  const people=manualPeople;if(!people.length||new Set(people).size!==people.length)throw new Error('참여자 명단을 확인해 주세요.');
  if(!manualPayer.trim()||!manualItem.trim())throw new Error('결제자와 항목을 입력해 주세요.');const amount=safeAmount(manualAmount);const round=Number(manualRound);
  if(!Number.isInteger(round)||round<1)throw new Error('차수는 1 이상의 정수여야 해요.');
  const all=people.includes(manualPayer.trim())?people:[...people,manualPayer.trim()];
  const context={participants:all,rounds:[{round_number:round,participant_names:people}],expenses:[{round_number:round,payer_name:manualPayer.trim(),total_amount:amount,items:[{name:manualItem.trim(),amount}]}],split_rules:[{expense_index:0,item_index:0,method:'equal',participant_names:people}]};
  const source=`[사용자 지정] ${title.trim()||'새 정산'} / ${people.join(', ')} / ${manualPayer.trim()} 결제 / ${manualItem.trim()} ${money(amount)}`;
  await afterCreate(await sessionApi.manual(source,context));
 });
 const createBlank=()=>run(async()=>{await afterCreate(await sessionApi.manual(`[사용자 지정] ${title.trim()||'상세 정산'}`,{participants:[],expenses:[]}));setPage('edit');});
 const open=(sid:string)=>run(async()=>{const d=localDiffs[sid]?.session||await sessionApi.get(sid);load(d,lastCalculation(d)?'detail':'review');});
 const saveEdit=()=>run(async()=>{if(!doc||!rev||!draft)return;const updated=await sessionApi.edit(doc.session_id,rev.input_revision,draft);clearEditDraft();load(updated,'review');await refresh();setMessage('수정 내용을 저장했어요. 확인 항목을 다시 검토해 주세요.');});
 const begin=()=>run(async()=>{if(!doc||!rev)return;if(dirty)throw new Error('수정 내용을 먼저 저장해 주세요.');if(issues.length)throw new Error('미해결 확인 항목을 수정해 주세요.');const c=await sessionApi.confirm(doc.session_id,rev.input_revision,'모바일 사용자','정산 시작 버튼으로 조건 확인',{source_reviewed:true,people_resolved:true,conditions_reviewed:true,funding_verified:!!ctx.contributions?.length});const calc=await sessionApi.calculate(doc.session_id,c.confirmation_id);setCalculation(calc);setPage('detail');setMessage('정산이 시작됐어요. 입금 여부는 직접 확인해 주세요.');});
 const deleteSession=()=>{if(doc)deleteById(doc.session_id);};
 const share=()=>run(async()=>{if(!doc||!calculation)return;const latest=localDiffs[doc.session_id]?.session||await sessionApi.get(doc.session_id);if(latest.revisions[latest.revisions.length-1].input_revision!==calculation.input_revision)throw new Error('정산 조건이 변경됐어요. 다시 계산해 주세요.');await Share.share({message:[`[${meta[doc.session_id]?.title||'모아정산'}] 송금 안내`,...groupedTransfers(calculation.result.settlements).map(t=>`${t.from_participant} → ${t.to_participant}: ${money(t.amount)}`)].join('\n')});});
 const chooseImage=()=>run(async()=>{const perm=await ImagePicker.requestMediaLibraryPermissionsAsync();if(!perm.granted)throw new Error('사진 접근 권한이 필요해요.');const picked=await ImagePicker.launchImageLibraryAsync({mediaTypes:['images'],quality:.8});if(picked.canceled)return;const image=picked.assets[0];setSelectedImage({uri:image.uri,mimeType:image.mimeType||'image/jpeg',name:image.fileName||'receipt.jpg'});setImagePreview(null);});
 const addPerson=()=>{const name=personEntry.trim();if(!name)return;if(manualPeople.includes(name)){Alert.alert('중복된 참여자','이미 추가된 이름이에요.');return;}setManualPeople(p=>[...p,name]);setPersonEntry('');};
 const diffTotal=diffTransfers.reduce((sum,t)=>sum+(Number(t.amount.replace(/,/g,''))||0),0);
 const diffValid=manualAmount.trim()!==''&&/^\d+$/.test(manualAmount.replace(/,/g,''))&&Number(manualAmount.replace(/,/g,''))===diffTotal&&diffTransfers.length>0&&diffTransfers.every(t=>t.from&&t.to&&t.from!==t.to&&manualPeople.includes(t.from)&&manualPeople.includes(t.to)&&/^\d+$/.test(t.amount.replace(/,/g,''))&&Number(t.amount.replace(/,/g,''))>0);
 const createDiff=()=>{if(!diffValid){Alert.alert('금액 불일치','송금액 합계와 총액, 참여자 및 송금 관계를 확인해 주세요.');return;}const sid='local-diff-'+Date.now();const amount=safeAmount(manualAmount);const transfers=diffTransfers.map(t=>({expense_index:0,from_participant:t.from,to_participant:t.to,amount:safeAmount(t.amount)}));const context={participants:manualPeople,rounds:[{round_number:Number(manualRound)||1,participant_names:manualPeople}],expenses:[],split_rules:[],direct_transfers:transfers,transfer_total:amount};const calc:Calculation={input_revision:1,result:{participant_totals:{},settlements:transfers,allocations:[]}};const d:Session={session_id:sid,source_text:'[사용자 지정 차액 정산] 송금 총액 '+money(amount),revisions:[{input_revision:1,context,issues:[]}],calculations:[calc]};setLocalDiffs(v=>({...v,[sid]:{session:d,calculation:calc}}));setLocal(sid,{title:title.trim()||'차액 정산'});setCreateDraftEnabled(false);clearCreateDraft();load(d,'detail');setMessage('차액 정산이 생성됐어요. 송금 내역을 확인하세요.');};
 const deleteAllVisible=()=>{
  if(!active.length)return;
  const count=active.length;
  Alert.alert('정산 내역 전체 삭제',`현재 목록의 ${count}건을 이 기기에서 숨길까요? 서버 원본은 삭제되지 않으며, 기존 입금 기록도 복구할 수 없을 수 있어요.`,[
   {text:'취소',style:'cancel'},
   {text:`${count}건 삭제`,style:'destructive',onPress:()=>{
    const ids=active.map(x=>x.session_id);
    setMeta(prev=>{
     const next={...prev};
     for(const id of ids)next[id]={...next[id],deleted:true};
     return next;
    });
    setMenuSid(null);
    setMessage(`${count}건을 이 기기의 정산 목록에서 숨겼어요. 서버 원본은 유지됩니다.`);
   }},
  ]);
 };
 const deleteById=(sid:string)=>Alert.alert('정산 삭제','이 기기의 목록에서 정산을 삭제할까요? 서버에 저장된 원본은 유지돼요.',[{text:'취소',style:'cancel'},{text:'삭제',style:'destructive',onPress:()=>{setLocal(sid,{deleted:true});setPage('home');setDoc(null);}}]);
 const Header=()=> <View style={styles.header}><Pressable onPress={()=>{if(page!=='home')navigateBack();}}><Text style={styles.logo}>모아<Text style={{color:C.green}}>정산</Text></Text><Text style={styles.logoSub}>함께 쓴 돈, 함께 확인</Text></Pressable><Text style={styles.headerIcon}>◈</Text></View>;
 const Back=({label='돌아가기'}:{label?:string})=><Pressable style={{marginBottom:16}} onPress={()=>navigateBack()}><Text style={styles.link}>‹ {label}</Text></Pressable>;
 const Summary=({context}:{context:Json})=><View><View style={styles.infoRow}><Text style={styles.infoLabel}>참여자</Text><Text style={styles.infoValue}>{(context.participants||[]).join(', ')||'미입력'}</Text></View>{(context.rounds||[]).map((r:any,i:number)=><View key={i} style={styles.infoRow}><Text style={styles.infoLabel}>{r.round_number??i+1}차 참석</Text><Text style={styles.infoValue}>{(r.participant_names||[]).join(', ')||'확인 필요'}</Text></View>)}{(context.expenses||[]).map((e:any,i:number)=><View key={i} style={styles.summaryBox}><Text style={styles.subhead}>{i+1}번 결제 · {e.round_number?`${e.round_number}차`: '차수 미지정'}</Text><Text style={styles.cardAmount}>{money(e.total_amount)}</Text><Text style={styles.muted}>결제자: {e.payer_name||'확인 필요'}</Text>{(e.items||[]).map((item:any,j:number)=><Text key={j} style={styles.itemText}>· {item.name||'항목 미정'} {money(item.amount)}</Text>)}</View>)}{(context.direct_transfers||[]).map((t:any,i:number)=><View key={'direct'+i} style={styles.infoRow}><Text style={styles.infoLabel}>{t.from_participant} → {t.to_participant}</Text><Text style={styles.infoValue}>{money(t.amount)}</Text></View>)}{[['split_rules','분담 기준'],['exceptions','개인별 예외'],['contributions','찬조금']].map(([key,label])=>(context[key]||[]).length?<View key={key} style={styles.infoRow}><Text style={styles.infoLabel}>{label}</Text><Text style={styles.infoValue}>{context[key].length}건 · 상세 수정에서 확인</Text></View>:null)}</View>;
 const PaymentList=({d,calc}:{d:Session;calc:Calculation})=>{
  const sid=d.session_id;
  const paid=meta[sid]?.transferPaid||{};
  const stats=paymentStats(calc,paid);
  const filtered=stats.rows.filter(t=>paymentFilter==='all'||(paymentFilter==='paid'?!!paid[t.key]:!paid[t.key]));
  const markPaid=(key:string,next:boolean)=>setLocal(sid,{transferPaid:{...paid,[key]:next}});
  const copyTransfer=async(t:typeof stats.rows[number])=>{
   const title=meta[sid]?.title||'모아정산';
   await Clipboard.setStringAsync(`[${title}] 송금 안내\n${t.from_participant} → ${t.to_participant}: ${money(t.amount)}`);
   if(Platform.OS==='web')setMessage(`${t.from_participant}님의 송금 안내를 복사했어요.`);
   else Alert.alert('복사 완료',`${t.from_participant}님의 송금 안내를 복사했어요.`);
  };
   const reminders=meta[sid]?.reminderRecords||{};
   const tones=meta[sid]?.reminderTones||{};
   const chooseTone=(key:string,tone:ReminderTone)=>setLocal(sid,{reminderTones:{...tones,[key]:tone}});
   const markReminder=(t:typeof stats.rows[number])=>{
    if(paid[t.key]){Alert.alert('입금 완료','이미 입금 확인된 송금에는 안내 기록을 추가할 수 없어요.');return;}
    const old=reminders[t.key];
    const save=()=>setLocal(sid,{reminderRecords:{...reminders,[t.key]:{count:(old?.count||0)+1,lastAt:new Date().toISOString()}}});
    const hours=old?.lastAt?(Date.now()-new Date(old.lastAt).getTime())/3600000:Infinity;
    if(Platform.OS==='web'){
     const prompt=hours>=0&&hours<24?'마지막 안내 기록 후 24시간이 지나지 않았어요. 실제로 다시 안내했나요?':'실제로 메시지를 전달했나요? 복사나 공유 창 열기만으로는 전달이 확인되지 않아요.';
     if(typeof window!=='undefined'&&window.confirm(prompt))save();
     return;
    }
    if(hours>=0&&hours<24){
     Alert.alert('24시간 이내 재안내','마지막 안내 기록 후 24시간이 지나지 않았어요. 실제로 다시 안내했나요?',[
      {text:'취소',style:'cancel'},{text:'안내했어요',onPress:save}
     ]);
    }else Alert.alert('안내 기록 확인','메시지를 실제로 전달했을 때만 기록해 주세요. 복사나 공유 창 열기만으로는 전달이 확인되지 않아요.',[
     {text:'취소',style:'cancel'},{text:'안내했어요',onPress:save}
    ]);
   };
   const copyReminder=async(text:string)=>{
    await Clipboard.setStringAsync(text);
    if(Platform.OS==='web')setMessage('안내 문구를 복사했어요. 실제로 보낸 뒤 안내 완료를 기록해 주세요.');
    else Alert.alert('복사 완료','안내 문구를 복사했어요. 실제로 보낸 뒤 안내 완료를 기록해 주세요.');
   };
   const shareReminder=async(text:string)=>{await Share.share({message:text});};
  return <View style={{gap:12}}>
   <View style={styles.progressCard}>
    <View style={styles.rowBetween}><Text style={styles.subhead}>입금 확인 진행률</Text><Text style={styles.progressPercent}>{stats.percent}%</Text></View>
    <View style={styles.progressTrack}><View style={[styles.progressFill,{width:`${stats.percent}%`}]}/></View>
    <Text style={styles.muted}>확인 {stats.paidCount}/{stats.totalCount}건 · 확인 금액 {money(stats.paidAmount)} / {money(stats.totalAmount)}</Text>
    <Text style={[styles.subhead,{color:stats.unpaidAmount>0?C.orange:C.green}]}>미확인 금액 {money(stats.unpaidAmount)}</Text>
   </View>
   <Text style={styles.label}>송금 내역 필터</Text>
   <View style={styles.wrap}>
    <Chip text={`전체 ${stats.totalCount}`} active={paymentFilter==='all'} onPress={()=>setPaymentFilter('all')}/>
    <Chip text={`미납 ${stats.totalCount-stats.paidCount}`} active={paymentFilter==='unpaid'} onPress={()=>setPaymentFilter('unpaid')}/>
    <Chip text={`완료 ${stats.paidCount}`} active={paymentFilter==='paid'} onPress={()=>setPaymentFilter('paid')}/>
   </View>
   {filtered.length?filtered.map(t=><View key={t.key} style={styles.transferCard}>
    <View style={styles.rowBetween}>
     <View style={{flex:1}}><Text style={styles.personName}>{t.from_participant} → {t.to_participant}</Text><Text style={styles.cardAmount}>{money(t.amount)}</Text></View>
     <Text style={[styles.paidText,{color:paid[t.key]?C.green:C.orange}]}>{paid[t.key]?'입금 확인':'미납 · 미확인'}</Text>
    </View>
    <View style={styles.transferActions}>
     <View style={{flexDirection:'row',alignItems:'center',gap:7}}><Text style={styles.muted}>입금 확인</Text><Switch value={!!paid[t.key]} onValueChange={v=>markPaid(t.key,v)} trackColor={{false:'#D7DDD7',true:'#8EC2A9'}} thumbColor={paid[t.key]?C.green:'#F7F8F6'}/></View>
     <Button text="개별 복사" secondary small onPress={()=>copyTransfer(t).catch(e=>Alert.alert('복사 실패',String(e?.message||e)))}/>
     </View>
     {!paid[t.key]&&<View style={styles.reminderSection}>
      <Pressable onPress={()=>setReminderOpenKey(v=>v===t.key?null:t.key)} style={styles.rowBetween}>
       <Text style={styles.subhead}>개별 안내 · 리마인더</Text>
       <Text style={styles.link}>{reminderOpenKey===t.key?'접기 ▲':'열기 ▼'}</Text>
      </Pressable>
      {reminders[t.key]&&<Text style={styles.muted}>안내 기록 {reminders[t.key].count}회 · 마지막 {new Date(reminders[t.key].lastAt).toLocaleString('ko-KR')}</Text>}
      {reminderOpenKey===t.key&&(()=>{
       const tone=tones[t.key]||'friend';
       const repeat=(reminders[t.key]?.count||0)>0;
       const msg=reminderText(meta[sid]?.title||'모아정산',t.from_participant,t.to_participant,t.amount,tone,repeat);
       return <View style={{gap:9}}>
        <Text style={styles.label}>관계별 말투</Text>
        <View style={styles.wrap}>
         <Chip text="친구" active={tone==='friend'} onPress={()=>chooseTone(t.key,'friend')}/>
         <Chip text="선배 · 정중" active={tone==='senior'} onPress={()=>chooseTone(t.key,'senior')}/>
         <Chip text="후배 · 편하게" active={tone==='junior'} onPress={()=>chooseTone(t.key,'junior')}/>
        </View>
        <Text style={styles.muted}>{repeat?'재안내 문구':'첫 안내 문구'} · 현재 계산된 송금액 기준</Text>
        <Text style={styles.reminderMessage}>{msg}</Text>
        <View style={styles.wrap}>
         <Button text="문구 복사" secondary small onPress={()=>copyReminder(msg).catch(e=>Alert.alert('복사 실패',String(e?.message||e)))}/>
         <Button text="공유하기" secondary small onPress={()=>shareReminder(msg).catch(e=>Alert.alert('공유 실패',String(e?.message||e)))}/>
         <Button text="안내했어요 · 기록" small onPress={()=>markReminder(t)}/>
        </View>
        <Text style={styles.helper}>실제 발송은 자동으로 이루어지지 않습니다. 전달을 완료한 뒤에만 '안내했어요'를 눌러 주세요.</Text>
       </View>;
      })()}
     </View>}
    </View>):<Text style={styles.success}>{paymentFilter==='unpaid'?'미납 송금 내역이 없어요.':paymentFilter==='paid'?'아직 입금 확인된 송금이 없어요.':'송금할 금액이 없어요.'}</Text>}
   <Text style={styles.helper}>입금 여부는 총무가 직접 확인하는 기록이며 은행 거래 내역과 자동 연동되지 않습니다. 같은 송금자라도 수취인이 다르면 별도로 확인할 수 있어요. 같은 송금자·수취인 간 송금은 합산 표시합니다.</Text>
  </View>;
 };

 return <View style={{flex:1,backgroundColor:C.bg}}><StatusBar barStyle="dark-content" /><KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.container}><Header/>
 {page==='home'&&<><View style={styles.hero}><Text style={styles.eyebrow}>SETTLEMENT HOME</Text><Text style={styles.heroTitle}>정산 현황을{ '\n'}한눈에.</Text><Text style={styles.muted}>진행 중인 정산과 입금 확인을 관리하세요.</Text></View>{message?<Text style={styles.notice}>{message}</Text>:null}<View style={styles.rowBetween}><Text style={styles.sectionTitle}>내 정산 <Text style={styles.muted}>{active.length}건</Text></Text><View style={{flexDirection:'row',alignItems:'center',gap:12}}>{active.length>0&&<Pressable onPress={deleteAllVisible}><Text style={{color:'#B42318',fontWeight:'800',fontSize:13}}>전체 삭제</Text></Pressable>}<Pressable onPress={()=>run(refresh)}><Text style={styles.link}>새로고침 ↻</Text></Pressable></View></View><View style={styles.board}>{active.map((s,i)=>{
  const d=localDiffs[s.session_id]?.session||docsById[s.session_id];const context=d?.revisions?.[d.revisions.length-1]?.context;
  const calc=d?lastCalculation(d):null;
  const people:string[]=context?.participants||[];
  return <View key={s.session_id} style={styles.boardTile}>
   <Pressable onPress={()=>open(s.session_id)}>
    <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center'}}><Text style={styles.tileNumber}>{String(i+1).padStart(2,'0')} · 진행 중</Text><Pressable hitSlop={12} onPress={()=>setMenuSid(v=>v===s.session_id?null:s.session_id)}><Text style={{fontSize:23,color:C.muted}}>⋯</Text></Pressable></View>
    {menuSid===s.session_id&&<Pressable onPress={()=>{setMenuSid(null);deleteById(s.session_id)}} style={{backgroundColor:'#FFF0F0',borderRadius:8,padding:9,marginTop:5}}><Text style={{color:'#B42318',fontWeight:'800'}}>정산 삭제</Text></Pressable>}<Text numberOfLines={2} style={styles.tileTitle}>{meta[s.session_id]?.title||s.title||'이름 없는 정산'}</Text>
    <Text style={styles.tilePrice}>{d?money(localDiffs[s.session_id]?d.revisions[0].context.transfer_total:total(d)):'불러오는 중'}</Text>
    <Text style={styles.tileHint} numberOfLines={2}>{people.join(', ')||'참여자 확인 필요'}</Text>
   </Pressable>
   <View style={styles.tilePayments}>
    {calc?(()=>{const st=paymentStats(calc,meta[s.session_id]?.transferPaid||{});return <View style={{gap:5}}><Text style={styles.tileHint}>입금 확인 {st.paidCount}/{st.totalCount}건 · {st.percent}%</Text><View style={styles.progressTrack}><View style={[styles.progressFill,{width:`${st.percent}%`}]}/></View><Text style={styles.tileHint}>미확인 {money(st.unpaidAmount)}</Text></View>;})():<Text style={styles.tileHint}>정산 계산 후 진행률 표시</Text>}
   </View>
   <Pressable onPress={()=>open(s.session_id)}><Text style={styles.link}>자세히 보기 ›</Text></Pressable>
  </View>;
 })}<Pressable style={[styles.boardTile,styles.addTile]} onPress={startNew}><Text style={styles.addIcon}>＋</Text><Text style={styles.addTitle}>정산 추가</Text></Pressable></View><Text style={styles.helper}>정산은 사용자가 직접 목록에서 삭제할 때까지 남아요. 입금 확인은 이 기기에 저장돼요.</Text></>}
 {page==='create'&&<><Back/><Text style={styles.eyebrow}>NEW SETTLEMENT</Text><Text style={styles.heroTitle}>새 정산 만들기</Text><Text style={styles.muted}>AI에 상황과 사진을 함께 전달하거나 직접 입력하세요.</Text><Panel title="정산 이름"><Field label="이름 (선택)" value={title} onChange={setTitle} placeholder="예: 동아리 회식"/></Panel><Panel title="입력 방식"><View style={styles.wrap}><Chip text="✦ AI 조건 입력" active={mode==='ai'} onPress={()=>setMode('ai')}/><Chip text="사용자 지정" active={mode==='custom'} onPress={()=>setMode('custom')}/></View></Panel>{mode==='ai'?<Panel title="AI 정산 분석"><Text style={styles.muted}>텍스트와 영수증·메모 사진을 함께 분석할 수 있어요. 사진을 첨부하면 AI 분석 후 영수증 항목과 금액을 먼저 검수합니다.</Text><Field label="정산 상황 (사진만 있어도 가능)" value={aiText} onChange={setAiText} multiline placeholder="민수가 식사비 6만원을 냈고 도윤은 술을 안 마셨어..."/><Button text={selectedImage?`✓ 사진 첨부됨 · 다른 사진 선택`:'＋ 영수증 / 메모 사진 첨부'} secondary onPress={chooseImage} disabled={busy}/>{selectedImage?<Text style={styles.success}>첨부 사진: {selectedImage.name}</Text>:null}{sourceEditing&&<Text style={styles.success}>이전에 검수한 영수증 내역은 보존됩니다. 문장만 수정하여 다시 분석하세요.</Text>}<Button text={busy?'분석 중...':sourceEditing?'수정한 문장으로 다시 분석하기 →':'AI로 조건 분석하기 →'} onPress={createAI} disabled={busy}/></Panel>:<><Panel title="정산 방식"><View style={styles.wrap}><Chip text="N분의 1 정산" active={manualKind==='equal'} onPress={()=>setManualKind('equal')}/><Chip text="차액 정산" active={manualKind==='diff'} onPress={()=>setManualKind('diff')}/></View></Panel><Panel title="정산 참여자"><View style={{flexDirection:'row',gap:8,alignItems:'center'}}><TextInput style={[styles.input,{flex:1}]} value={personEntry} onChangeText={setPersonEntry} placeholder="이름 입력" onSubmitEditing={addPerson}/><Pressable onPress={addPerson} style={[styles.btn,{marginTop:0,minWidth:48}]}><Text style={styles.btnText}>＋</Text></Pressable></View><View style={styles.wrap}>{manualPeople.map(p=><Pressable key={p} style={styles.addPill} onPress={()=>setManualPeople(v=>v.filter(x=>x!==p))}><Text style={styles.addPillText}>{p}  ×</Text></Pressable>)}</View></Panel><Panel title={manualKind==='equal'?'균등 정산 조건':'차액 정산 조건'}><Field label={manualKind==='diff'?'송금 총액 (원)':'총 지출액 (원)'} value={manualAmount} onChange={setManualAmount} numeric placeholder="90000"/><Field label="차수" value={manualRound} onChange={setManualRound} numeric/>{manualKind==='equal'?<><Field label="결제자" value={manualPayer} onChange={setManualPayer} placeholder="민수"/><Field label="항목" value={manualItem} onChange={setManualItem}/><Button text="기본 정산 조건 만들기 →" onPress={createCustom} disabled={busy}/><Text style={styles.helper}>차수별 참여, 비주류 제외, 찬조금은 다음 정산 조건 수정 화면에서 추가할 수 있어요.</Text><Button text="빈 양식으로 상세 입력" secondary onPress={createBlank} disabled={busy}/></>:<><Text style={styles.muted}>총액은 송금할 금액의 합계를 뜻해요. 누가 누구에게 얼마를 보내는지 입력하세요.</Text>{diffTransfers.map((t,i)=><View key={i} style={styles.arrayRow}><View style={styles.rowBetween}><Text style={styles.subhead}>송금 {i+1}</Text><Pressable onPress={()=>setDiffTransfers(v=>v.filter((_,j)=>j!==i))}><Text style={styles.deleteText}>삭제</Text></Pressable></View><Text style={styles.label}>보내는 사람</Text><View style={styles.wrap}>{manualPeople.map(p=><Chip key={'from'+p} text={p} active={t.from===p} onPress={()=>setDiffTransfers(v=>v.map((x,j)=>j===i?{...x,from:p}:x))}/>)}</View><Text style={styles.label}>받는 사람</Text><View style={styles.wrap}>{manualPeople.map(p=><Chip key={'to'+p} text={p} active={t.to===p} onPress={()=>setDiffTransfers(v=>v.map((x,j)=>j===i?{...x,to:p}:x))}/>)}</View><Field label="송금액 (원)" numeric value={t.amount} onChange={v=>setDiffTransfers(a=>a.map((x,j)=>j===i?{...x,amount:v}:x))}/></View>)}<Button text="＋ 송금 내역 추가" secondary onPress={()=>setDiffTransfers(v=>[...v,{from:'',to:'',amount:''}])}/><Text style={{fontWeight:'800',color:diffValid?'#2563EB':'#DC2626'}}>{diffValid?'금액이 일치해요!':'총액과 정산 금액이 불일치해요!'}</Text><Text style={styles.muted}>송금액 합계: {money(diffTotal)}</Text><Button text="정산 시작 · 금액 계산 →" disabled={!diffValid} onPress={createDiff}/></>}</Panel></>}</>}


 {page==='imageReview'&&imagePreview&&<><Back label="사진 입력으로 돌아가기"/><Text style={styles.heroTitle}>영수증 분석 결과 확인</Text><Text style={styles.muted}>사진 원본과 비교하여 품목과 금액을 수정하세요. 승인 전에는 정산 세션을 만들지 않습니다.</Text><Panel title="인식된 품목">{imageItems.map((item,i)=><View key={i} style={styles.arrayRow}><Field label={`항목 ${i+1}`} value={item.name} onChange={v=>setImageItems(a=>a.map((x,j)=>j===i?{...x,name:v}:x))}/><Field label="항목 전체 금액 (원)" numeric value={item.amount} onChange={v=>setImageItems(a=>a.map((x,j)=>j===i?{...x,amount:v}:x))}/><Button text="항목 삭제" secondary small onPress={()=>setImageItems(a=>a.filter((_,j)=>i!==j))}/></View>)}<Button text="＋ 항목 추가" secondary onPress={()=>setImageItems(a=>[...a,{name:'',amount:''}])}/><Field label="영수증 총액 (원)" numeric value={imageTotal} onChange={setImageTotal}/><Text style={styles.muted}>항목 합계: {money(imageItems.reduce((sum,x)=>sum+(Number(x.amount.replace(/,/g,''))||0),0))}</Text><Field label="불명확한 부분 / 추가 확인 사항" multiline value={imageNotes} onChange={setImageNotes}/><Button text={busy?'확인 중...':'영수증 확인 완료 · 정산 조건 검토 →'} disabled={busy} onPress={confirmReceipt}/><Text style={styles.helper}>영수증을 확인한 후에도 기존 정산 조건 검토 화면에서 인원·분담·예외를 확인해야 합니다.</Text></Panel></>}
 {page==='review'&&doc&&<><Back/><Text style={styles.eyebrow}>REVIEW BEFORE SETTLEMENT</Text><Text style={styles.heroTitle}>조건을 확인해 주세요</Text><Text style={styles.muted}>AI가 추출했더라도 금액·인원·예외는 직접 확인해야 해요.</Text><Button text="← 처음 입력한 문장 수정하기" secondary onPress={returnToOriginal}/><Panel title="정산 조건 요약"><Summary context={ctx}/><Text style={styles.muted}>입력 버전 {rev?.input_revision}</Text><Button text="✎ 정산 조건 수정" onPress={()=>setPage('edit')}/></Panel><Panel title="원문 및 확인이 필요한 부분"><Text style={styles.sourceText}>{doc.source_text}</Text>{doc.supplied_evidence?<Text style={styles.sourceText}>{doc.supplied_evidence}</Text>:null}{visibleIssues.length?visibleIssues.map((x,i)=><IssueResolver key={`${String(x.path||'')}:${String(x.code||'')}:${i}`} issue={x} index={i}/>):<Text style={styles.success}>자동 검토에서 미해결 항목을 찾지 못했어요. 실제 조건은 직접 확인하세요.</Text>}</Panel><View style={{marginTop:18}}><Button text={busy?'계산 중...':'정산 시작 · 금액 계산 →'} disabled={busy||!!issues.length} onPress={begin}/><Text style={styles.helper}>버튼을 누르면 표시된 정산 조건을 확인한 것으로 기록하고 계산합니다. 실제 송금은 자동으로 수행하지 않아요.</Text></View></>}
 {page==='edit'&&doc&&draft&&<><Back label="검수 화면으로"/><Text style={styles.eyebrow}>CUSTOM EDITOR</Text><Text style={styles.heroTitle}>정산 조건 수정</Text><Text style={styles.muted}>참여자, 차수, 항목, 분담 기준, 예외, 찬조금을 직접 수정할 수 있어요.</Text><Panel title="정산 조건 편집"><ConditionEditor value={draft} focus={editorFocus} onChange={v=>{setDraft(v);setDirty(true);}}/><FriendlyEditor value={draft} onChange={v=>{setDraft(v);setDirty(true);}}/><Button text={showAdvanced?'고급 조건 편집 닫기':'스키마 고급 편집 (선택 사항)'} secondary onPress={()=>setShowAdvanced(v=>!v)}/>{showAdvanced&&(schema?<SchemaEditor schema={schema} value={draft} onChange={v=>{setDraft(v);setDirty(true);}}/>:<Text style={styles.issue}>서버의 /api/schema를 불러오지 못했어요. 네트워크를 확인해 주세요.</Text>)}<Text style={styles.helper}>결제 번호와 항목 번호는 0부터 시작합니다. 항목을 삭제했다면 참조 번호도 다시 확인하세요.</Text><Button text={busy?'저장 중...':'수정 내용 저장 · 다시 검수 →'} disabled={busy||!dirty} onPress={saveEdit}/></Panel></>}
 {page==='detail'&&doc&&<><Back label="홈으로"/><Text style={styles.eyebrow}>ACTIVE SETTLEMENT</Text><Text style={styles.heroTitle}>{meta[doc.session_id]?.title||'진행 중인 정산'}</Text><Text style={styles.muted}>입금 상태를 직접 대조하고 토글로 기록하세요.</Text><Panel title="정산 개요"><Summary context={ctx}/><Text style={styles.cardAmount}>{money(localDiffs[doc.session_id]?ctx.transfer_total:total(doc))}</Text>{!localDiffs[doc.session_id]&&<Button text="조건 다시 검토·수정" secondary onPress={()=>setPage('review')}/>}</Panel>{calculation&&calculation.input_revision===rev?.input_revision?<><Panel title="송금 및 입금 관리"><PaymentList d={doc} calc={calculation}/><Button text="전체 송금 안내 공유" secondary onPress={share}/></Panel></>:<Panel title="정산 진행 전"><Text style={styles.muted}>아직 계산이 완료되지 않았어요.</Text><Button text="검수하고 계산하기" onPress={()=>setPage('review')}/></Panel>}<Panel title="정산 관리"><Field label="정산명" value={meta[doc.session_id]?.title||''} onChange={v=>setLocal(doc.session_id,{title:v})} placeholder="정산명 입력"/><Button text="정산 삭제" secondary danger onPress={deleteSession}/></Panel></>}
 </ScrollView></KeyboardAvoidingView>{splash&&<View style={styles.splash}><Text style={styles.splashMark}>모</Text><Text style={styles.splashName}>모아정산</Text><Text style={styles.logoSub}>함께 쓴 돈, 함께 확인</Text></View>}{busy&&<View style={styles.loading}><ActivityIndicator size="large" color={C.green}/><Text style={{color:C.ink,marginTop:10}}>처리 중...</Text></View>}</View>;
}
const styles=StyleSheet.create({reminderSection:{borderTopWidth:1,borderTopColor:C.line,paddingTop:10,gap:6},reminderMessage:{backgroundColor:C.bg,color:C.ink,borderRadius:11,padding:13,fontSize:13,lineHeight:22},progressCard:{backgroundColor:C.greenSoft,borderRadius:12,padding:13,gap:8},progressPercent:{fontSize:23,fontWeight:'900',color:C.green},progressTrack:{height:9,backgroundColor:'#D7E3DA',borderRadius:9,overflow:'hidden'},progressFill:{height:'100%',backgroundColor:C.green,borderRadius:9},transferCard:{borderWidth:1,borderColor:C.line,borderRadius:12,padding:12,gap:8},transferActions:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8},previewHeader:{marginTop:9,padding:11,borderRadius:10,backgroundColor:C.greenSoft,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},previewTitle:{fontWeight:'800',fontSize:13,color:C.green},previewBody:{padding:10,borderWidth:1,borderColor:C.line,borderRadius:10,gap:5},container:{paddingHorizontal:20,paddingTop:44,paddingBottom:90,maxWidth:720,width:'100%',alignSelf:'center'},header:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',marginBottom:34},logo:{fontSize:26,fontWeight:'900',letterSpacing:-1.2,color:C.ink},logoSub:{color:C.muted,fontSize:12,marginTop:2},headerIcon:{fontSize:26,color:C.green},hero:{marginBottom:26},eyebrow:{color:C.green,fontSize:12,fontWeight:'800',letterSpacing:2,marginBottom:12},heroTitle:{fontSize:34,lineHeight:43,fontWeight:'900',color:C.ink,letterSpacing:-1.4,marginBottom:12},muted:{color:C.muted,fontSize:13,lineHeight:21},sectionTitle:{color:C.ink,fontWeight:'800',fontSize:20},rowBetween:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginBottom:14},board:{flexDirection:'row',flexWrap:'wrap',justifyContent:'space-between',gap:12},boardTile:{width:'48%',minHeight:174,borderRadius:19,backgroundColor:C.white,borderColor:C.line,borderWidth:1,padding:17,justifyContent:'space-between'},tileNumber:{fontSize:12,color:C.green,fontWeight:'800'},tilePrice:{fontSize:20,fontWeight:'900',color:C.ink,marginTop:7},tilePayments:{borderTopWidth:1,borderTopColor:C.line,paddingTop:6,marginTop:7},tilePayRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',minHeight:30},tilePerson:{color:C.muted,fontSize:12,flex:1},tileTitle:{fontSize:18,fontWeight:'800',color:C.ink,marginTop:12},tileHint:{fontSize:11,color:C.muted},tileBadge:{alignSelf:'flex-start',color:C.green,backgroundColor:C.greenSoft,paddingHorizontal:9,paddingVertical:4,overflow:'hidden',borderRadius:20,fontSize:11,fontWeight:'700'},addTile:{backgroundColor:'#ECF3ED',borderStyle:'dashed',borderColor:'#A8C3B4',alignItems:'center',justifyContent:'center'},addIcon:{fontSize:36,color:C.green},addTitle:{fontSize:17,color:C.green,fontWeight:'800'},helper:{color:C.muted,fontSize:12,lineHeight:20,marginTop:12},panel:{backgroundColor:C.white,borderColor:C.line,borderWidth:1,borderRadius:20,padding:19,marginTop:18,marginBottom:2,gap:13},panelTitle:{fontSize:19,color:C.ink,fontWeight:'800',marginBottom:3},field:{gap:7,marginTop:5},label:{fontSize:13,color:'#4B6259',fontWeight:'700'},input:{backgroundColor:'#FCFDFC',borderWidth:1,borderColor:'#CDDCD0',borderRadius:11,paddingVertical:12,paddingHorizontal:13,fontSize:15,color:C.ink,minHeight:47},btn:{backgroundColor:C.green,borderRadius:12,minHeight:49,alignItems:'center',justifyContent:'center',paddingHorizontal:16,paddingVertical:10,marginTop:5},btnSecondary:{backgroundColor:C.white,borderWidth:1,borderColor:'#C8D9CD'},btnSmall:{minHeight:37,alignSelf:'flex-start'},btnDanger:{borderColor:'#E5B8B8'},btnText:{fontWeight:'800',fontSize:15,color:'#FFF'},wrap:{flexDirection:'row',flexWrap:'wrap',gap:8,marginTop:7},chip:{borderRadius:12,borderWidth:1,borderColor:C.line,backgroundColor:C.white,paddingHorizontal:13,paddingVertical:10},chipActive:{backgroundColor:C.green,borderColor:C.green},chipText:{fontSize:13,fontWeight:'700',color:C.ink},divider:{height:1,backgroundColor:C.line,marginVertical:7},subhead:{fontSize:14,fontWeight:'800',color:C.ink},sourceText:{color:C.ink,fontSize:13,lineHeight:21,backgroundColor:C.bg,borderRadius:11,padding:13},infoRow:{flexDirection:'row',justifyContent:'space-between',gap:10,paddingVertical:8,borderBottomColor:C.line,borderBottomWidth:1},infoLabel:{color:C.muted,fontSize:13,flex:1},infoValue:{color:C.ink,fontWeight:'600',fontSize:13,flex:2,textAlign:'right'},summaryBox:{backgroundColor:C.bg,borderRadius:12,padding:13,gap:5,marginVertical:7},cardAmount:{fontSize:24,color:C.ink,fontWeight:'900'},itemText:{color:C.muted,fontSize:13},issue:{backgroundColor:C.orangeSoft,color:C.orange,borderRadius:9,padding:12,fontSize:13,lineHeight:20},success:{color:C.green,backgroundColor:C.greenSoft,padding:12,borderRadius:10,fontSize:13},paymentRow:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',paddingVertical:11,borderBottomColor:C.line,borderBottomWidth:1,gap:8},personName:{color:C.ink,fontWeight:'800',fontSize:15},paidText:{fontSize:12,fontWeight:'800'},link:{color:C.green,fontWeight:'800',fontSize:13},notice:{backgroundColor:C.greenSoft,padding:13,borderRadius:12,color:C.ink,marginBottom:12},editorGroup:{borderWidth:1,borderColor:C.line,borderRadius:12,padding:12,marginTop:9,gap:8},groupTitle:{color:C.ink,fontSize:15,fontWeight:'800',marginBottom:5},arrayRow:{borderWidth:1,borderColor:C.line,borderRadius:12,padding:10,marginVertical:5,gap:6},deleteText:{color:'#A34C4C',fontWeight:'800',fontSize:13},addPill:{borderWidth:1,borderColor:'#BFD4C6',borderRadius:10,paddingHorizontal:10,paddingVertical:8},addPillText:{fontSize:12,color:C.green,fontWeight:'700'},splash:{position:'absolute',top:0,left:0,right:0,bottom:0,backgroundColor:C.bg,alignItems:'center',justifyContent:'center'},splashMark:{fontSize:50,color:'#FFF',backgroundColor:C.green,borderRadius:28,overflow:'hidden',paddingHorizontal:30,paddingVertical:14,fontWeight:'900'},splashName:{fontSize:33,fontWeight:'900',color:C.ink,marginTop:22,marginBottom:5},loading:{position:'absolute',top:0,left:0,right:0,bottom:0,backgroundColor:'#F5F7F3CC',alignItems:'center',justifyContent:'center'}});
