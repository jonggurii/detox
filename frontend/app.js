const $ = id => document.getElementById(id);
let sid = null, revision = null, savedText = null, confirmed = false;
const money = n => Number(n).toLocaleString('ko-KR') + '원';
function status(message){$('status').textContent = message;}
function renderIssues(issues){
  const ul=$('issues'); ul.replaceChildren();
  if(!issues.length){const li=document.createElement('li');li.textContent='자동 검토에서 미해결 조건이 발견되지 않았습니다. 원문과 직접 대조해 주세요.';ul.append(li);return;}
  for(const issue of issues){const li=document.createElement('li');li.className='warn';li.textContent=`[${issue.code}] ${issue.path}: ${issue.question}`;ul.append(li);}
}
function showSession(data){
  sid=data.session_id;revision=data.revision;confirmed=data.confirmed;
  savedText=JSON.stringify(data.context,null,2);$('context').value=savedText;
  $('review').hidden=false;$('result').hidden=true;renderIssues(data.issues);
  $('confirm').disabled=!!data.issues.length;
  status(`입력 버전 ${revision}: ${data.issues.length}개 확인 항목`);
}
async function api(url,method='GET',body){
  const response=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
async function act(button,fn){button.disabled=true;try{await fn();}catch(e){status('오류: '+e.message);}finally{button.disabled=false;}}
$('parse').onclick=()=>act($('parse'),async()=>{status('Gemini 파싱 중...');showSession(await api('/api/parse','POST',{text:$('source').value}));});
$('context').addEventListener('input',()=>{$('confirm').disabled=true;confirmed=false;$('result').hidden=true;status('JSON을 수정했습니다. 수정 내용 검증을 눌러주세요.');});
$('validate').onclick=()=>act($('validate'),async()=>{
  if(!sid)throw Error('먼저 파싱을 실행하세요.');
  const context=JSON.parse($('context').value);
  showSession(await api(`/api/sessions/${sid}/context`,'PUT',{revision,context}));
});
$('confirm').onclick=()=>act($('confirm'),async()=>{
  if(!sid)throw Error('먼저 파싱을 실행하세요.');
  if($('context').value!==savedText)throw Error('수정한 JSON을 먼저 검증하세요.');
  const reviewer=$('reviewer').value.trim();if(!reviewer)throw Error('확인자를 입력하세요.');
  const data=await api(`/api/sessions/${sid}/confirm`,'POST',{revision,reviewed_by:reviewer});
  confirmed=data.confirmed;
  status('정산 조건 확정. 계산 중...');
  const result=await api(`/api/sessions/${sid}/calculate`,'POST');
  const totals=$('totals');totals.replaceChildren();
  for(const [name,amount] of Object.entries(result.participant_totals)){
    const line=document.createElement('div');line.className='amount';
    const left=document.createElement('span');left.textContent=name;
    const right=document.createElement('strong');right.textContent=money(amount);
    line.append(left,right);totals.append(line);
  }
  const transfers=$('transfers');transfers.replaceChildren();
  for(const t of result.settlement_preview){const line=document.createElement('div');line.className='amount';line.textContent=`${t.from_participant} → ${t.to_participant}: ${money(t.amount)}`;transfers.append(line);}
  if(!result.settlement_preview.length)transfers.textContent='송금 요청 없음';
  $('raw').textContent=JSON.stringify(result,null,2);$('result').hidden=false;status('계산 완료');
});
