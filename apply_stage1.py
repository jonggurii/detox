from pathlib import Path
import sys
p=Path(sys.argv[1]) if len(sys.argv)>1 else Path('mobile/src/app/index.tsx')
s=p.read_text(encoding='utf-8')
if 'MOA_STAGE1_NAV' in s:
 print('이미 1단계 패치가 적용되어 있습니다.');sys.exit(0)
def rep(old,new):
 global s
 if s.count(old)!=1: raise RuntimeError(f'고유한 수정 위치를 찾지 못했습니다 ({s.count(old)}개): {old[:110]}')
 s=s.replace(old,new,1)
rep("import React,{useCallback,useEffect,useState} from 'react';", "import React,{useCallback,useEffect,useRef,useState} from 'react';")
rep('ActivityIndicator,Alert,KeyboardAvoidingView,Platform,Pressable,ScrollView,Share,StatusBar,StyleSheet,Switch,Text,TextInput,View', 'ActivityIndicator,Alert,BackHandler,Keyboard,KeyboardAvoidingView,Platform,Pressable,ScrollView,Share,StatusBar,StyleSheet,Switch,Text,TextInput,View')
rep("const DIFF_STORAGE='moa_mobile_direct_transfers_v1';", "const DIFF_STORAGE='moa_mobile_direct_transfers_v1';\nconst DRAFT_STORAGE='moa_mobile_draft_stage1_v1'; // MOA_STAGE1_NAV")
anchor=" const rev=doc?.revisions?.[doc.revisions.length-1];"
insert=''' // Persist text/conditions locally; never persist the photo URI as a reliable attachment.
 const [draftReady,setDraftReady]=useState(false);
 const busyLock=useRef(false);
 const pageRef=useRef(page);pageRef.current=page;
 const busyRef=useRef(busy);busyRef.current=busy;
 const dirtyRef=useRef(dirty);dirtyRef.current=dirty;
 const draftSnapshotRef=useRef('');
 const draftPayload={title,aiText,mode,manualPeople,personEntry,manualKind,diffTransfers,manualPayer,manualItem,manualAmount,manualRound,docId:doc?.session_id||null,editedContext:dirty?draft:null};
 const hasCreateDraft=Boolean(title.trim()||aiText.trim()||manualPeople.length||manualAmount.trim()||personEntry.trim()||selectedImage||diffTransfers.some(t=>t.from||t.to||t.amount));
 const confirmLeave=(next:()=>void)=>{
  if(busyRef.current){return;}
  const current=pageRef.current;
  const needsConfirmation=(current==='create'&&hasCreateDraft)||(current==='edit'&&dirtyRef.current);
  if(!needsConfirmation){Keyboard.dismiss();next();return;}
  Alert.alert('작업을 보관할까요?', '작성 중인 내용은 이 기기에 임시 저장됩니다. 나중에 다시 이어서 작성할 수 있어요.',[
   {text:'계속 작성',style:'cancel'},
   {text:'임시 저장하고 이동',onPress:()=>{Keyboard.dismiss();next();}},
  ]);
 };
 const navigateBack=()=>{
  const current=pageRef.current;
  if(busyRef.current)return true;
  if(current==='home'){
   Keyboard.dismiss();
   if(Platform.OS==='android')Alert.alert('앱 종료', '모아정산을 종료할까요?',[
    {text:'취소',style:'cancel'},
    {text:'종료',onPress:()=>BackHandler.exitApp()},
   ]);
   return true;
  }
  const target:Page=current==='edit'?'review':current==='detail'?'review':'home';
  confirmLeave(()=>setPage(target));
  return true;
 };
 useEffect(()=>{
  if(Platform.OS!=='android')return;
  const sub=BackHandler.addEventListener('hardwareBackPress',navigateBack);
  return()=>sub.remove();
 });
 useEffect(()=>{
  let active=true;
  AsyncStorage.getItem(DRAFT_STORAGE).then(raw=>{
   if(!raw||!active)return;
   const saved=JSON.parse(raw);
   if(saved.title)setTitle(saved.title);
   if(saved.aiText)setAiText(saved.aiText);
   if(saved.mode==='ai'||saved.mode==='custom')setMode(saved.mode);
   if(Array.isArray(saved.manualPeople))setManualPeople(saved.manualPeople);
   if(typeof saved.personEntry==='string')setPersonEntry(saved.personEntry);
   if(saved.manualKind==='equal'||saved.manualKind==='diff')setManualKind(saved.manualKind);
   if(Array.isArray(saved.diffTransfers)&&saved.diffTransfers.length)setDiffTransfers(saved.diffTransfers);
   if(typeof saved.manualPayer==='string')setManualPayer(saved.manualPayer);
   if(typeof saved.manualItem==='string')setManualItem(saved.manualItem);
   if(typeof saved.manualAmount==='string')setManualAmount(saved.manualAmount);
   if(typeof saved.manualRound==='string')setManualRound(saved.manualRound);
   // A previous server session can be restored by opening it from the home list.
   if(saved.docId&&saved.editedContext){
    draftSnapshotRef.current=JSON.stringify({docId:saved.docId,editedContext:saved.editedContext});
   }
  }).catch(()=>{}).finally(()=>{if(active)setDraftReady(true)});
  return()=>{active=false};
 },[]);
 useEffect(()=>{
  if(!draftReady)return;
  const timer=setTimeout(()=>{
   AsyncStorage.setItem(DRAFT_STORAGE,JSON.stringify(draftPayload)).catch(()=>{});
  },400);
  return()=>clearTimeout(timer);
 },[draftReady,title,aiText,mode,manualPeople,personEntry,manualKind,diffTransfers,manualPayer,manualItem,manualAmount,manualRound,doc,draft,dirty]);
'''
rep(anchor,insert+anchor)
# restore edited context only when the user opens the matching server session
rep("setDraft(clone(d.revisions[d.revisions.length-1].context));setDirty(false);", """setDraft(clone(d.revisions[d.revisions.length-1].context));setDirty(false);
  if(draftSnapshotRef.current){try{const saved=JSON.parse(draftSnapshotRef.current);if(saved.docId===d.session_id&&saved.editedContext){Alert.alert('임시 수정본 발견','저장되지 않은 정산 조건 수정본이 있어요. 복원할까요?', [{text:'서버 버전 사용',style:'cancel',onPress:()=>{draftSnapshotRef.current='';}}, {text:'복원',onPress:()=>{setDraft(saved.editedContext);setDirty(true);setPage('edit');}}]);}}catch{}}""")
rep("const run=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);try{await fn();}catch(e:any){Alert.alert('확인해 주세요',String(e?.message||e));}finally{setBusy(false);}};", "const run=async(fn:()=>Promise<void>)=>{if(busyLock.current)return;busyLock.current=true;setBusy(true);Keyboard.dismiss();try{await fn();}catch(e:any){Alert.alert('확인해 주세요',String(e?.message||e));}finally{busyLock.current=false;setBusy(false);}};")
rep("const startNew=()=>{setDoc(null);", "const startNew=()=>{setDoc(null);")
# existing startNew clears draft intentionally: replace with resume option
rep("const startNew=()=>{setDoc(null);", "const startNew=()=>{if(hasCreateDraft){Alert.alert('임시 작성 내용','이전에 작성하던 내용을 이어서 작성할까요?', [{text:'새로 작성',style:'destructive',onPress:()=>resetNew()},{text:'이어쓰기',onPress:()=>setPage('create')}]);return;}resetNew();};\n const resetNew=()=>{setDoc(null);")
rep("const Header=()=> <View style={styles.header}><Pressable onPress={()=>setPage('home')}","const Header=()=> <View style={styles.header}><Pressable onPress={()=>confirmLeave(()=>setPage('home'))}")
rep("onPress={()=>setPage(page==='edit'?'review':'home')}","onPress={navigateBack}")
rep("<KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView keyboardShouldPersistTaps=\"handled\"", "<KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':'height'}><ScrollView keyboardDismissMode=\"on-drag\" keyboardShouldPersistTaps=\"handled\"")
# prevent accidental edit loss when leaving edit through buttons; clear recovered snapshot on successful save
rep("load(updated,'review');await refresh();", "draftSnapshotRef.current='';load(updated,'review');await refresh();")
# handle navigation from result to review; keep as is (no draft to lose)
backup=p.with_suffix(p.suffix+'.stage1.bak')
backup.write_text(p.read_text(encoding='utf-8'),encoding='utf-8')
p.write_text(s,encoding='utf-8')
print('패치 완료:',p)
