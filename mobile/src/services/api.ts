import { File } from 'expo-file-system';

export type Json = Record<string, any>;
export type Issue = {code: string; path: string; question: string};
export type Revision = {input_revision: number; context: Json; issues: Issue[]};
export type Transfer = {expense_index:number; from_participant:string; to_participant:string; amount:number};
export type Calculation = {input_revision:number; result:{participant_totals:Record<string,number>; settlements:Transfer[]; allocations:Array<{expense_index:number;item_index:number;participant_name:string;amount:number}>}};
export type Session = {session_id:string; source_text:string; supplied_evidence?:string|null; revisions:Revision[]; calculations:Calculation[]};
export type SessionSummary = {session_id:string; title?:string; created_at?:string; input_revision?:number};
export type Receipt = {receipt_id:string; review_revision:number; warning?:string|null; ocr?:{text?:string};fields?:{items?:Array<{name?:string|null;amount?:number|null}>;total_amount?:number|null;warnings?:string[]};review?:Json|null};
const BASE = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');
export const apiBase = () => BASE;
export async function request<T>(path:string, method='GET', body?:unknown):Promise<T>{
  if(!BASE) throw new Error('mobile/.env에 EXPO_PUBLIC_API_URL=http://PC_IP:8000을 설정하세요.');
  const timeoutMs =
    path === '/api/receipts/multimodal-confirm' ||
    path === '/api/sessions'
      ? 180000
      : 60000;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response=await fetch(BASE+path,{method,headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
    const text=await response.text(); let data:any=text;
    try{data=text?JSON.parse(text):null;}catch{}
    if(!response.ok){const detail=data?.detail; throw new Error(typeof detail==='string'?detail:JSON.stringify(detail??data??`HTTP ${response.status}`));}
    return data as T;
  }catch(e:any){if(e?.name==='AbortError')throw new Error('서버 연결 시간이 초과됐어요. PC·스마트폰 네트워크와 FastAPI를 확인하세요.');throw e;}
  finally{clearTimeout(timer);}
}
export const sessionApi={
 list:()=>request<SessionSummary[]>('/api/sessions'),
 get:(sid:string)=>request<Session>(`/api/sessions/${encodeURIComponent(sid)}`),
 ai:(text:string)=>request<Session>('/api/sessions','POST',{text,supplied_evidence:null}),
 manual:(source_text:string,context:Json)=>request<Session>('/api/sessions/manual','POST',{source_text,context}),
 edit:(sid:string,input_revision:number,context:Json)=>request<Session>(`/api/sessions/${encodeURIComponent(sid)}/context`,'PATCH',{input_revision,context}),
 confirm:(sid:string,input_revision:number,reviewed_by:string,review_notes:string,checks:Json)=>request<{confirmation_id:string}>(`/api/sessions/${encodeURIComponent(sid)}/confirm`,'POST',{input_revision,reviewed_by,review_notes,checks}),
 calculate:(sid:string,confirmation_id:string)=>request<Calculation>(`/api/sessions/${encodeURIComponent(sid)}/calculate`,'POST',{confirmation_id}),
 schema:()=>request<Json>('/api/schema'),
};
export async function uploadReceipt(uri:string):Promise<Receipt>{
 if(!BASE)throw new Error('서버 주소를 먼저 설정하세요.');
 const form=new FormData();form.append('file',{uri,name:'receipt.jpg',type:'image/jpeg'} as any);
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),120000);
 try{const res=await fetch(BASE+'/api/receipts',{method:'POST',body:form,signal:controller.signal});const data=await res.json();if(!res.ok)throw new Error(typeof data?.detail==='string'?data.detail:JSON.stringify(data?.detail??data));return data as Receipt;}
 finally{clearTimeout(timer);}
}
export const receiptApi={
 draft:(rid:string,body:Json)=>request<Session>(`/api/receipts/${encodeURIComponent(rid)}/draft`,'POST',body),
 review:(rid:string,body:Json)=>request<{receipt_id:string;review_revision:number;evidence:string;hint:string}>(`/api/receipts/${encodeURIComponent(rid)}/review`,'POST',body),
 ai:(rid:string,expected_review_revision:number,text:string)=>request<Session>(`/api/receipts/${encodeURIComponent(rid)}/ai`,'POST',{expected_review_revision,text}),
};

// 이미지와 자연어를 함께 보내는 멀티모달 분석 API (별도 백엔드 라우터 필요)
export async function analyzeImage(
  image: {
    uri: string;
    mimeType: string;
    name: string;
  },
  text: string
): Promise<Session> {

  if (!BASE) {
    throw new Error('EXPO_PUBLIC_API_URL이 설정되지 않았어요.');
  }

  // 1. 이미지 정보 확인
  console.log('[IMAGE DEBUG]', {
    uri: image.uri,
    name: image.name,
    mimeType: image.mimeType,
    uriType: typeof image.uri,
    nameType: typeof image.name,
    mimeTypeType: typeof image.mimeType,
  });

  // 2. FormData 생성
  const form = new FormData();

  const file = {
    uri: image.uri,
    name: image.name || 'receipt.jpg',
    type: image.mimeType || 'image/jpeg',
  };

  console.log('[UPLOAD FILE]', file);

  // 3. 이미지 및 사용자 텍스트 추가
  form.append('file', file as any);
  form.append('text', String(text ?? ''));

  // 4. FormData 내부 구조 확인
  console.log('[FORM DEBUG]', (form as any)._parts);

  // 5. 요청 제한 시간: 180초
  const controller = new AbortController();

  const timer = setTimeout(() => {
    controller.abort();
  }, 180000);

  try {
    console.log('[UPLOAD START]', BASE + '/api/sessions/multimodal');

    // 6. 백엔드로 이미지와 텍스트 전송
    const res = await fetch(
      BASE + '/api/sessions/multimodal',
      {
        method: 'POST',
        body: form,
        signal: controller.signal,
      }
    );

    console.log('[UPLOAD STATUS]', res.status);

    // 7. 서버 응답 확인
    const raw = await res.text();

    let data: any;

    try {
      data = JSON.parse(raw);
    } catch {
      data = raw;
    }

    if (!res.ok) {
      throw new Error(
        typeof data?.detail === 'string'
          ? data.detail
          : JSON.stringify(data?.detail || data)
      );
    }

    console.log('[UPLOAD SUCCESS]');

    return data as Session;

  } catch (e: any) {

    // 8. 오류 메시지 출력
    console.error('[UPLOAD ERROR]', e);

    if (e?.name === 'AbortError') {
      throw new Error(
        '사진 분석 시간이 초과됐어요. 서버 로그를 확인해 주세요.'
      );
    }

    throw e;

  } finally {
    clearTimeout(timer);
  }
}

export type ImagePreview={items:Array<{name:string;amount:number|null}>;total_amount:number|null;notes:string[];original_text:string};
export async function previewImage(
  image: {
    uri: string;
    mimeType: string;
    name: string;
  },
  text: string
): Promise<ImagePreview> {
  if (!BASE) {
    throw new Error('EXPO_PUBLIC_API_URL을 설정하세요.');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);

  try {
    console.log('[PREVIEW 1] 로컬 파일 생성 시작');

    // Expo FileSystem의 File 객체 사용
    const file = new File(image.uri);

    if (!file.exists) {
      throw new Error('선택한 사진 파일이 존재하지 않습니다.');
    }

    console.log('[PREVIEW 2] 파일 확인', {
      name: file.name,
      size: file.size,
      type: file.type,
    });

    // Expo File은 Blob 기반 파일 객체
    const form = new FormData();

    form.append(
      'file',
      file,
      image.name || file.name
    );

    form.append('text', String(text ?? ''));

    console.log('[PREVIEW 3] FormData 생성 완료');

    const res = await fetch(
      BASE + '/api/receipts/multimodal-preview',
      {
        method: 'POST',
        body: form,
        signal: controller.signal,
      }
    );

    console.log('[PREVIEW 4] 서버 응답:', res.status);

    const raw = await res.text();

    let body: any;

    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }

    if (!res.ok) {
      throw new Error(
        typeof body?.detail === 'string'
          ? body.detail
          : JSON.stringify(body?.detail || body)
      );
    }

    console.log('[PREVIEW 5] 분석 성공');

    return body as ImagePreview;

  } catch (e: any) {
    console.error('[PREVIEW ERROR]', e);

    if (e?.name === 'AbortError') {
      throw new Error('사진 분석 시간이 초과됐어요.');
    }

    throw e;

  } finally {
    clearTimeout(timer);
  }
}
export const confirmImage=(text:string,reviewed_text:string)=>request<Session>('/api/receipts/multimodal-confirm','POST',{text,reviewed_text});