// npm install --no-save jsdom 후 node tests/test_frontend_dom.cjs
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..');
const schema=JSON.parse(fs.readFileSync(path.join(root,'src/settlements/schemas/request_context.schema.json'),'utf8'));
const context={participants:['A','B'],expenses:[{payer_name:'A',total_amount:10000,items:[{name:'식사',amount:10000}]}],split_rules:[{expense_index:0,item_index:0,method:'equal',participant_names:['A','B']}]};
const document=()=>({session_id:'s1',source_text:'입력',supplied_evidence:null,revisions:[{input_revision:1,context:structuredClone(context),issues:[]}],confirmations:[],calculations:[]});
const receipt=()=>({receipt_id:'r1',review_revision:0,review:null,session_id:null,warning:null,fields:{items:[{name:'식사',amount:10000}],total_amount:10000,total_candidates:[],warnings:[],unparsed_lines:[]},ocr:{text:'식사 10,000',blocks:[],low_score_count:0}});
const tick=()=>new Promise(r=>setImmediate(r));
async function settle(dom){for(let i=0;i<10;i++)await tick();if(dom.errors.length)throw dom.errors[0];}
async function boot(file,url,handler,clipboardError=false){
 const calls=[],errors=[],copied=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented: navigation')&&!e.message.includes('Not implemented: Window'))errors.push(e);});
 const dom=new JSDOM(fs.readFileSync(path.join(root,'frontend',file+'.html'),'utf8'),{url,runScripts:'dangerously',virtualConsole:vc,beforeParse(w){w.structuredClone=structuredClone;w.confirm=()=>true;w.HTMLElement.prototype.scrollIntoView=function(){};Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async text=>{if(clipboardError)throw Error('denied');copied.push(text);}}});w.fetch=async(url,opt={})=>{const method=opt.method||'GET',body=opt.body?JSON.parse(opt.body):null;calls.push({url,method,body});const value=await handler(url,method,body);return {ok:true,json:async()=>structuredClone(value)};};}});
 dom.calls=calls;dom.errors=errors;dom.copied=copied;dom.$=id=>dom.window.document.getElementById(id);await settle(dom);return dom;
}
function input(dom,id,value){const el=typeof id==='string'?dom.$(id):id;el.value=value;el.dispatchEvent(new dom.window.Event('input',{bubbles:true}));}
function baseApi(url){if(url==='/api/schema')return schema;if(url==='/api/sessions')return [];if(url.endsWith('/receipt'))return null;if(url.startsWith('/api/sessions/'))return document();throw Error('Unexpected URL '+url);}
let count=0;
async function test(name,fn){await fn();count++;console.log('PASS',name);}
(async()=>{
await test('direct entry never guesses payer and keeps payer outside consumers',async()=>{
 const dom=await boot('index','http://localhost/',(url,method,body)=>{if(method==='POST'){assert.equal(url,'/api/sessions/manual');const doc=document();doc.revisions[0].context=body.context;return doc;}return baseApi(url);});
 for(const id of ['directParticipants','directPayer','directAmount','reviewer'])assert.equal(dom.$(id).value,'');
 input(dom,'directParticipants','A, B');input(dom,'directItemName','식사');input(dom,'directAmount','10000');input(dom,'directMethod','equal');dom.$('directStartBtn').click();await settle(dom);
 assert.equal(dom.calls.filter(c=>c.method==='POST').length,0);assert.match(dom.$('notice').textContent,/결제자/);
 input(dom,'directPayer','P');dom.$('directStartBtn').click();await settle(dom);
 const sent=dom.calls.find(c=>c.method==='POST').body.context;assert.deepEqual(sent.participants,['A','B','P']);assert.deepEqual(sent.split_rules[0].participant_names,['A','B']);
 for(const id of ['sourceCheck','peopleCheck','termsCheck','fundingCheck'])assert.equal(dom.$(id).checked,false);
 dom.window.close();
});
await test('direct 0 won is accepted; scientific notation is rejected',async()=>{
 const dom=await boot('index','http://localhost/',(url,method,body)=>method==='POST'?document():baseApi(url));
 for(const [id,v] of [['directParticipants','A'],['directPayer','A'],['directItemName','무료'],['directMethod','equal'],['directAmount','1e3']])input(dom,id,v);
 dom.$('directStartBtn').click();await settle(dom);assert.equal(dom.calls.filter(c=>c.method==='POST').length,0);
 input(dom,'directAmount','0');dom.$('directStartBtn').click();await settle(dom);assert.equal(dom.calls.find(c=>c.method==='POST').body.context.expenses[0].total_amount,0);dom.window.close();
});
await test('receipt edits invalidate review; unknowns stay null and no AI is called',async()=>{
 const dom=await boot('receipt','http://localhost/receipts/new?receipt_id=r1',(url,method)=>method==='GET'?receipt():document());
 dom.$('checked').checked=true;const name=dom.window.document.querySelector('[aria-label="품목 1 이름"]');input(dom,name,'수정 식사');assert.equal(dom.$('checked').checked,false);
 const price=dom.window.document.querySelector('[aria-label="품목 1 금액"]');input(dom,price,'');input(dom,'totalAmount','');input(dom,'receiptReviewer','검수자');dom.$('checked').checked=true;
 dom.$('settleNowBtn').click();await settle(dom);const sent=dom.calls.find(c=>c.method==='POST');assert.equal(sent.url,'/api/receipts/r1/draft');assert.equal(sent.body.items[0].amount,null);assert.equal(sent.body.total_amount,null);assert.equal(sent.body.payer_name,null);assert.equal(sent.body.split_method,null);assert.ok(!dom.calls.some(c=>c.url.endsWith('/ai')));dom.window.close();
});
await test('cleared rows and null totals stay cleared on reopening',async()=>{
 const doc=receipt();doc.review={items:[],total_amount:null,receipt_total_amount:null,payer_name:null,reviewed_by:'검수자'};
 const dom=await boot('receipt','http://localhost/receipts/new?receipt_id=r1',()=>doc);
 assert.equal(dom.$('itemsBody').children.length,0);assert.equal(dom.$('totalAmount').value,'');assert.equal(dom.$('payer').value,'');dom.window.close();
});
await test('legacy null items do not crash or generate a fake item',async()=>{
 const doc=receipt();doc.review={items:null,total_amount:0,reviewed_by:'검수자'};
 const dom=await boot('receipt','http://localhost/receipts/new?receipt_id=r1',()=>doc);
 assert.equal(dom.$('itemsBody').children.length,0);assert.equal(dom.$('totalAmount').value,'0');assert.equal(dom.$('payer').value,'');dom.window.close();
});
await test('copy uses corrected values and a denied clipboard has a manual fallback',async()=>{
 const dom=await boot('receipt','http://localhost/receipts/new?receipt_id=r1',()=>receipt(),true);
 const price=dom.window.document.querySelector('[aria-label="품목 1 금액"]');input(dom,price,'0');input(dom,'totalAmount','');dom.$('copyTextBtn').click();await settle(dom);
 assert.equal(dom.$('copyFallback').hidden,false);assert.match(dom.$('copyFallback').value,/항목 전체 금액: 0원/);assert.match(dom.$('copyFallback').value,/실제 결제 총액: 미정/);dom.window.close();
});
await test('AI handoff from receipt only saves review and does not call Gemini',async()=>{
 const dom=await boot('receipt','http://localhost/receipts/new?receipt_id=r1',(url,method)=>method==='GET'?receipt():{receipt_id:'r1',review_revision:1});
 input(dom,'receiptReviewer','검수자');dom.$('checked').checked=true;dom.$('sendToAiBtn').click();await settle(dom);
 assert.deepEqual(dom.calls.filter(c=>c.method==='POST').map(c=>c.url),['/api/receipts/r1/review']);assert.equal(dom.calls.at(-1).body.payer_name,null);dom.window.close();
});
await test('AI page loads immutable evidence and only calls on Apply',async()=>{
 const dom=await boot('index','http://localhost/?mode=ai&receipt_id=r1',(url,method)=>{if(url.endsWith('/handoff'))return {receipt_id:'r1',review_revision:4,evidence:'확인한 금액 0원',hint:'비용 분담 대상: A, B'};if(method==='POST')return document();return baseApi(url);});
 assert.equal(dom.$('aiEvidence').readOnly,true);assert.equal(dom.$('aiEvidence').value,'확인한 금액 0원');assert.equal(dom.calls.filter(c=>c.method==='POST').length,0);
 input(dom,'sentence','A와 B가 균등 분담');dom.$('parseBtn').click();await settle(dom);const sent=dom.calls.find(c=>c.method==='POST');assert.equal(sent.url,'/api/receipts/r1/ai');assert.equal(sent.body.expected_review_revision,4);assert.equal(sent.body.supplied_evidence,undefined);
 dom.$('newBtn').click();assert.equal(dom.$('aiEvidence').value,'');assert.equal(dom.window.location.search,'');dom.window.close();
});
await test('copy refuses an old calculation after another client changes the input',async()=>{
 const old=document();old.calculations=[{input_revision:1,result:{participant_totals:{A:5000,B:5000},settlements:[],allocations:[]}}];let getCount=0;
 const dom=await boot('index','http://localhost/?session_id=s1',url=>{if(url==='/api/sessions/s1'){if(getCount++===0)return old;const newer=document();newer.revisions[0].input_revision=2;return newer;}return baseApi(url);});
 dom.$('copyBtn').click();await settle(dom);assert.equal(dom.copied.length,0);assert.match(dom.$('notice').textContent,/다른 화면/);dom.window.close();
});
console.log(`${count} DOM behavior tests passed`);
})().catch(e=>{console.error(e);process.exitCode=1;});
