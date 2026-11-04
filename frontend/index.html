import React, {useCallback, useEffect, useState} from 'react';
import {ActivityIndicator, Alert, Pressable, ScrollView, Share, StyleSheet, Switch, Text, TextInput, View} from 'react-native';
import {apiBase, sessionApi, Session} from '../services/api';

type Mode = 'direct'|'ai'|'receipt';
const money = (n:number) => `${Number(n).toLocaleString('ko-KR')}원`;
const GREEN = '#176858';
const EMPTY_CHECKS = {source_reviewed:false, people_resolved:false, conditions_reviewed:false, funding_verified:false};

export default function HomeScreen() {
  const [mode,setMode] = useState<Mode>('direct');
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState('');
  const [history,setHistory] = useState<Array<{session_id:string;title?:string}>>([]);
  const [doc,setDoc] = useState<Session|null>(null);
  const [contextText,setContextText] = useState('');
  const [dirty,setDirty] = useState(false);
  const [checks,setChecks] = useState(EMPTY_CHECKS);
  const [reviewer,setReviewer] = useState('');
  const [note,setNote] = useState('');
  const [result,setResult] = useState<Session['calculations'][number]|null>(null);
  const [participants,setParticipants] = useState('');
  const [payer,setPayer] = useState('');
  const [item,setItem] = useState('');
  const [amount,setAmount] = useState('');
  const [aiText,setAiText] = useState('');
  const revision = doc?.revisions?.[doc.revisions.length-1];
  const hasFunding = !!revision?.context?.contributions?.length;
  const issues = revision?.issues ?? [];

  const reloadHistory = useCallback(async () => {
    try {setHistory(await sessionApi.list());} catch (e:any) {setNotice(e.message);}
  },[]);
  useEffect(()=>{reloadHistory();},[reloadHistory]);

  const loadDoc = (next:Session) => {
    const latest = next.revisions[next.revisions.length-1];
    setDoc(next);
    setContextText(JSON.stringify(latest.context,null,2));
    setDirty(false);
    setChecks({...EMPTY_CHECKS}); setReviewer('');setNote('');
    setResult([...(next.calculations ?? [])].reverse().find(c=>c.input_revision===latest.input_revision) ?? null);
  };
  const run = async (fn:()=>Promise<void>) => {
    if(busy)return;
    setBusy(true);
    try {await fn();} catch(e:any) {Alert.alert('확인해 주세요',e?.message||String(e));}
    finally {setBusy(false);}
  };
  const createDirect = () => run(async()=>{
    const consumers=participants.split(/[,，]/).map(s=>s.trim());
    const value=amount.trim();
    if (!consumers.length || consumers.some(x=>!x) || new Set(consumers).size!==consumers.length) throw new Error('참여자 이름을 쉼표로 구분하고 중복·빈 이름을 확인해 주세요.');
    if (!payer.trim() || !item.trim()) throw new Error('결제자와 항목명을 입력해 주세요.');
    if (!/^(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)$/.test(value)) throw new Error('금액을 0 이상의 원 단위 정수로 입력해 주세요.');
    const number=Number(value.replace(/,/g,''));
    if (!Number.isSafeInteger(number)) throw new Error('금액이 너무 커요.');
    const people=consumers.includes(payer.trim())?consumers:[...consumers,payer.trim()];
    const context={participants:people,expenses:[{payer_name:payer.trim(),total_amount:number,items:[{name:item.trim(),amount:number}]}],split_rules:[{expense_index:0,item_index:0,method:'equal',participant_names:consumers}]};
    const source=`[직접 입력] 분담 대상: ${consumers.join(', ')} / 결제자: ${payer.trim()} / ${item.trim()} ${money(number)} 균등 분담`;
    loadDoc(await sessionApi.manual(source,context)); await reloadHistory();setNotice('정산 초안을 만들었어요. 조건을 검토한 뒤 확인하세요.');
  });
  const createEmpty = () => run(async()=>{
    loadDoc(await sessionApi.manual('직접 입력한 정산',{participants:[],expenses:[]}));await reloadHistory();
    setNotice('JSON 편집기에 사람·결제·분담 기준을 입력하고 저장하세요.');
  });
  const createAi = () => run(async()=>{
    if(!aiText.trim())throw new Error('정산 상황을 입력해 주세요.');
    loadDoc(await sessionApi.ai(aiText));await reloadHistory();setNotice('AI가 추출한 조건을 검토해 주세요.');
  });
  const save = () => run(async()=>{
    if(!doc||!revision)return;
    let context;
    try {context=JSON.parse(contextText);}catch {throw new Error('JSON 형식이 올바르지 않아요. 괄호와 쉼표를 확인하세요.');}
    if (!context || Array.isArray(context) || typeof context!=='object') throw new Error('정산 조건은 JSON 객체여야 해요.');
    loadDoc(await sessionApi.edit(doc.session_id,revision.input_revision,context));await reloadHistory();setNotice('새 입력 버전으로 저장했어요. 확인 항목을 다시 체크하세요.');
  });
  const calculate = () => run(async()=>{
    if(!doc||!revision)return;
    if(dirty)throw new Error('변경된 조건을 먼저 저장해 주세요.');
    if(issues.length)throw new Error('자동 검토에서 발견한 문제를 먼저 수정해 주세요.');
    if(!checks.source_reviewed||!checks.people_resolved||!checks.conditions_reviewed||(hasFunding&&!checks.funding_verified))throw new Error('필요한 확인 항목을 모두 체크해 주세요.');
    if(!reviewer.trim()||!note.trim())throw new Error('확인 담당자와 확인 메모를 입력해 주세요.');
    const confirmed=await sessionApi.confirm(doc.session_id,revision.input_revision,reviewer.trim(),note.trim(),checks);
    const calculated=await sessionApi.calculate(doc.session_id,confirmed.confirmation_id);
    setResult(calculated);setNotice('확인한 조건으로 계산했어요. 송금 안내는 초안이며 실제 송금은 실행하지 않아요.');
  });
  const share = () => run(async()=>{
    if(!doc||!revision||!result||dirty)return;
    const current=await sessionApi.get(doc.session_id);
    if(current.revisions[current.revisions.length-1].input_revision!==result.input_revision){setResult(null);throw new Error('다른 화면에서 조건이 변경됐어요. 다시 확인하고 계산해 주세요.');}
    const lines=result.result.settlements.map(t=>`${t.expense_index+1}번 결제: ${t.from_participant} → ${t.to_participant} ${money(t.amount)}`);
    await Share.share({message:['정산 안내',...lines].join('\n')});
  });
  const reset = () => {
    if(dirty){Alert.alert('저장하지 않은 변경','변경을 버리고 새 정산을 만들까요?', [{text:'취소'}, {text:'새 정산',style:'destructive',onPress:()=>{setDoc(null);setResult(null);setDirty(false);setNotice('');}}]);}
    else {setDoc(null);setResult(null);setNotice('');}
  };
  const openSession = (sid:string) => {
    const go=()=>run(async()=>{loadDoc(await sessionApi.get(sid));setNotice('저장한 정산을 불러왔어요.');});
    if(dirty)Alert.alert('저장하지 않은 변경','변경을 버리고 다른 정산을 열까요?', [{text:'취소'}, {text:'열기',onPress:go}]);
    else go();
  };
  return <ScrollView style={styles.page} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
    <View style={styles.header}><Text style={styles.brand}>모아정산</Text><Text style={styles.caption}>함께 쓴 돈, 함께 확인</Text></View>
    <Text style={styles.eyebrow}>SETTLEMENT WORKSPACE</Text>
    <Text style={styles.hero}>정산은 정확하게,{'\n'}확인은 함께.</Text>
    <Text style={styles.muted}>입력 방식 선택 → 조건 검토·수정 → 확인 후 정산 계산</Text>
    <Text style={styles.server}>서버: {apiBase()||'주소 미설정'}</Text>
    {!!notice&&<View style={styles.notice}><Text>{notice}</Text></View>}
    {busy&&<ActivityIndicator color={GREEN} size="large" />}
    <View style={styles.card}><View style={styles.between}><Text style={styles.heading}>최근 정산</Text><Action label="＋ 새 정산" onPress={reset}/></View>
      {history.length===0?<Text style={styles.muted}>저장된 정산이 없어요.</Text>:history.slice(0,8).map(h=><Pressable key={h.session_id} onPress={()=>openSession(h.session_id)} style={styles.history}><Text style={styles.historyText}>{h.title||'직접 입력 정산'}</Text></Pressable>)}
    </View>
    {!doc ? <View style={styles.card}>
      <Text style={styles.heading}>정산 만들기</Text>
      <View style={styles.tabs}>{([['direct','직접 입력'],['receipt','영수증 OCR'],['ai','AI 조건 입력']] as const).map(([value,label])=><Pressable key={value} onPress={()=>setMode(value)} style={[styles.tab,mode===value&&styles.tabActive]}><Text style={[styles.tabText,mode===value&&styles.tabTextActive]}>{label}</Text></Pressable>)}</View>
      {mode==='direct'&&<><Text style={styles.muted}>AI 없이 균등 분담 정산을 만들어요.</Text><Field label="분담 대상자 (쉼표로 구분)" value={participants} onChangeText={setParticipants} placeholder="민수, 지수, 도윤"/><Field label="결제자" value={payer} onChangeText={setPayer} placeholder="민수"/><Field label="결제 항목명" value={item} onChangeText={setItem} placeholder="식사비"/><Field label="결제 금액(원)" value={amount} onChangeText={setAmount} placeholder="36000" keyboardType="numeric"/><Text style={styles.muted}>분담 방식: 입력한 대상자 균등 분담</Text><Primary label="직접 입력으로 정산 시작" disabled={busy} onPress={createDirect}/><Action label="빈 양식으로 상세 입력" onPress={createEmpty}/></>}
      {mode==='ai'&&<><Text style={styles.muted}>다차수·술값 제외·찬조금 등의 조건을 문장으로 설명해 주세요.</Text><Field label="정산 상황 설명" value={aiText} onChangeText={setAiText} multiline placeholder="민수, 지수, 도윤이 식사했어. 식사비 6만원, 술값 2만원..."/><Primary label="AI 적용 (조건 추출)" disabled={busy} onPress={createAi}/></>}
      {mode==='receipt'&&<><Text style={styles.muted}>최신 웹앱의 OCR은 영수증 업로드 → 항목 검수 → 정산으로 이어져요. 이 모바일 패치에는 아직 촬영·OCR 검수 화면이 포함되지 않았어요.</Text><Text style={styles.muted}>우선 직접 입력과 AI 정산을 검증한 뒤 OCR을 연결합니다.</Text></>}
    </View> : <>
      <View style={styles.card}><Text style={styles.heading}>조건 검토·수정</Text><Text style={styles.pill}>입력 버전 {revision?.input_revision}</Text><Text style={styles.label}>원문</Text><Text style={styles.source}>{doc.source_text}{doc.supplied_evidence?'\n\n[영수증 근거]\n'+doc.supplied_evidence:''}</Text>
        <Text style={styles.heading}>자동 검토</Text>{issues.length?issues.map((i,idx)=><View key={idx} style={styles.issue}><Text>{i.question}</Text></View>):<Text style={styles.muted}>자동 검토에서 문제를 찾지 못했어요. 실제 조건은 직접 대조해 주세요.</Text>}
        <Text style={styles.label}>정산 조건 JSON (고급 편집)</Text><Text style={styles.muted}>최신 웹앱의 항목별 편집기를 대체하는 임시 편집 화면입니다. JSON을 수정한 뒤 저장하세요.</Text>
        <TextInput multiline value={contextText} onChangeText={t=>{setContextText(t);setDirty(true);setResult(null);setChecks({...EMPTY_CHECKS});}} style={styles.json} autoCapitalize="none" autoCorrect={false} textAlignVertical="top"/>
        {dirty&&<Text style={styles.warning}>저장하지 않은 변경이 있어요. 저장 후 다시 확인해야 해요.</Text>}
        <Primary label="수정 내용 저장" onPress={save} disabled={!dirty||busy}/>
      </View>
      <View style={styles.card}><Text style={styles.heading}>사용자 확인 후 계산</Text>
        <Check label="입력 내용과 비교해 누락·추정 내용을 확인했어요." value={checks.source_reviewed} onValueChange={v=>setChecks(c=>({...c,source_reviewed:v}))}/>
        <Check label="이름과 호칭이 누구를 뜻하는지 확인했어요." value={checks.people_resolved} onValueChange={v=>setChecks(c=>({...c,people_resolved:v}))}/>
        <Check label="분담 방법, 예외, 찬조금과 잔액 처리에 합의했어요." value={checks.conditions_reviewed} onValueChange={v=>setChecks(c=>({...c,conditions_reviewed:v}))}/>
        {hasFunding&&<Check label="찬조금의 실제 전달·충당과 적용액을 확인했어요." value={checks.funding_verified} onValueChange={v=>setChecks(c=>({...c,funding_verified:v}))}/>}
        <Field label="확인 담당자" value={reviewer} onChangeText={setReviewer} placeholder="담당자 이름"/>
        <Field label="확인 메모" value={note} onChangeText={setNote} placeholder="조건 확인 완료"/>
        <Primary label="조건 확인하고 계산" disabled={busy||dirty||issues.length>0} onPress={calculate}/>
        <Text style={styles.muted}>실제 송금은 실행하지 않아요.</Text>
      </View>
      {result&&<View style={styles.card}><Text style={styles.heading}>정산 안내 미리보기</Text><Text style={styles.muted}>전달 전 초안</Text>
        {Object.entries(result.result.participant_totals).map(([name,total])=><View style={styles.person} key={name}><Text>{name}</Text><Text style={styles.total}>{money(total)}</Text></View>)}
        <Text style={styles.heading}>송금 내역</Text>{result.result.settlements.length?result.result.settlements.map((t,i)=><View key={i} style={styles.transfer}><Text>{t.expense_index+1}번 결제 · {t.from_participant} → {t.to_participant}</Text><Text style={styles.totalSmall}>{money(t.amount)}</Text></View>):<Text style={styles.muted}>다른 사람에게 보낼 금액이 없어요.</Text>}
        <Text style={styles.heading}>항목별 부담액</Text>{result.result.allocations.map((a,i)=><Text key={i} style={styles.allocation}>{a.expense_index+1}번 결제 · {revision?.context?.expenses?.[a.expense_index]?.items?.[a.item_index]?.name||'항목'} · {a.participant_name}: {money(a.amount)}</Text>)}
        <Primary label="송금 안내 공유" onPress={share} disabled={busy}/><Text style={styles.muted}>메시지 공유 화면만 열며 자동 발송하지 않아요.</Text>
      </View>}
    </>}
    <Text style={styles.footer}>자동 검토는 원문 누락이나 실제 입금을 보증하지 않아요. 담당자가 조건을 대조한 뒤 사용하세요.</Text>
  </ScrollView>;
}
function Field(props:{label:string;value:string;onChangeText:(v:string)=>void;placeholder?:string;multiline?:boolean;keyboardType?:'numeric'}){return <View style={styles.field}><Text style={styles.label}>{props.label}</Text><TextInput style={[styles.input,props.multiline&&styles.multiline]} value={props.value} onChangeText={props.onChangeText} placeholder={props.placeholder} multiline={props.multiline} keyboardType={props.keyboardType} textAlignVertical="top"/></View>}
function Action({label,onPress}:{label:string;onPress:()=>void}){return <Pressable onPress={onPress} style={styles.action}><Text style={styles.actionText}>{label}</Text></Pressable>}
function Primary({label,onPress,disabled}:{label:string;onPress:()=>void;disabled?:boolean}){return <Pressable disabled={disabled} onPress={onPress} style={[styles.primary,disabled&&styles.disabled]}><Text style={styles.primaryText}>{label}</Text></Pressable>}
function Check({label,value,onValueChange}:{label:string;value:boolean;onValueChange:(v:boolean)=>void}){return <View style={styles.check}><Switch value={value} onValueChange={onValueChange} trackColor={{true:'#92c4ad'}} thumbColor={value?GREEN:'#eee'}/><Text style={styles.checkText}>{label}</Text></View>}
const styles=StyleSheet.create({page:{flex:1,backgroundColor:'#f5f7f2'},content:{padding:18,paddingBottom:56},header:{flexDirection:'row',alignItems:'baseline',justifyContent:'space-between',marginBottom:22},brand:{fontSize:25,fontWeight:'900',color:'#173a38'},caption:{fontSize:12,color:'#687a73'},eyebrow:{color:GREEN,fontSize:11,fontWeight:'800',letterSpacing:2},hero:{fontSize:29,fontWeight:'800',color:'#173a38',marginTop:9,marginBottom:8},muted:{fontSize:13,color:'#687a73',lineHeight:21,marginVertical:6},server:{fontSize:11,color:'#687a73',marginTop:8},card:{backgroundColor:'#fff',borderColor:'#dce6df',borderWidth:1,borderRadius:18,padding:18,marginTop:16,gap:10},heading:{fontSize:19,fontWeight:'800',color:'#173a38'},between:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},notice:{backgroundColor:'#e8f2e8',padding:12,borderRadius:10,marginTop:14},history:{padding:12,borderRadius:10,backgroundColor:'#f8faf5'},historyText:{fontSize:13,color:'#173a38'},tabs:{flexDirection:'row',gap:5,flexWrap:'wrap',marginTop:8},tab:{paddingHorizontal:10,paddingVertical:9,borderRadius:9,borderWidth:1,borderColor:'#dce6df'},tabActive:{backgroundColor:GREEN,borderColor:GREEN},tabText:{fontSize:12,color:'#173a38',fontWeight:'700'},tabTextActive:{color:'#fff'},field:{gap:5,marginTop:6},label:{fontSize:13,fontWeight:'650',color:'#4e665e'},input:{borderWidth:1,borderColor:'#cedbd1',backgroundColor:'#fff',borderRadius:9,paddingHorizontal:12,paddingVertical:10,fontSize:15,color:'#173a38'},multiline:{minHeight:130},primary:{backgroundColor:GREEN,padding:14,borderRadius:10,alignItems:'center',marginTop:8},primaryText:{color:'#fff',fontWeight:'800',fontSize:15},disabled:{opacity:.45},action:{borderWidth:1,borderColor:'#dce6df',padding:10,borderRadius:9,alignItems:'center'},actionText:{fontSize:13,fontWeight:'700',color:'#173a38'},pill:{alignSelf:'flex-start',backgroundColor:'#eaf4e9',color:GREEN,paddingHorizontal:10,paddingVertical:5,borderRadius:20,fontSize:12},source:{backgroundColor:'#f4f7f1',padding:12,borderLeftWidth:3,borderLeftColor:'#9db8a0',fontSize:13,lineHeight:21},issue:{backgroundColor:'#fff6e5',padding:12,borderRadius:9},json:{borderWidth:1,borderColor:'#cedbd1',borderRadius:9,backgroundColor:'#f8faf8',minHeight:250,padding:12,fontSize:12,fontFamily:'monospace',color:'#173a38'},warning:{color:'#a34b1c',fontSize:13},check:{flexDirection:'row',alignItems:'center',gap:10,marginVertical:4},checkText:{flex:1,color:'#173a38',fontSize:13,lineHeight:20},person:{backgroundColor:'#f1f6ee',padding:14,borderRadius:12},total:{fontSize:23,fontWeight:'800',color:'#173a38'},transfer:{paddingVertical:10,borderBottomWidth:1,borderBottomColor:'#dce6df'},totalSmall:{fontSize:16,fontWeight:'800',color:GREEN,marginTop:3},allocation:{fontSize:12,color:'#4e665e',lineHeight:20},footer:{color:'#687a73',fontSize:11,lineHeight:19,marginTop:25}});
