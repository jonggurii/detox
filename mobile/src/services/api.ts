export type AnyObject = Record<string, any>;
export type Session = {
  session_id: string;
  source_text: string;
  supplied_evidence?: string | null;
  revisions: Array<{input_revision: number; context: AnyObject; issues: Array<{code:string; path:string; question:string}>}>;
  calculations: Array<{input_revision: number; result: {participant_totals: Record<string,number>; settlements: Array<{expense_index:number; from_participant:string; to_participant:string; amount:number}>; allocations: Array<{expense_index:number; item_index:number; participant_name:string; amount:number}>}} >;
};
const BASE = (process.env.EXPO_PUBLIC_API_URL || '').replace(/\/$/, '');
export function apiBase() { return BASE; }
export async function api<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (!BASE) throw new Error('mobile/.env에 EXPO_PUBLIC_API_URL=http://PC의_IP:8000 을 설정하세요.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${BASE}${path}`, {
      method, headers: body === undefined ? undefined : {'Content-Type':'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
    });
    const raw = await response.text();
    let data: any;
    try { data = raw ? JSON.parse(raw) : null; } catch { data = raw; }
    if (!response.ok) {
      const detail = data?.detail;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail ?? data ?? `HTTP ${response.status}`));
    }
    return data as T;
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new Error('서버 응답 시간이 초과됐어요. PC의 FastAPI 실행 상태를 확인하세요.');
    throw e;
  } finally { clearTimeout(timeout); }
}
export const sessionApi = {
  list: () => api<Array<{session_id:string;title?:string}>>('/api/sessions'),
  get: (id:string) => api<Session>(`/api/sessions/${encodeURIComponent(id)}`),
  manual: (source_text:string, context:AnyObject) => api<Session>('/api/sessions/manual','POST',{source_text,context}),
  ai: (text:string) => api<Session>('/api/sessions','POST',{text,supplied_evidence:null}),
  edit: (id:string, input_revision:number, context:AnyObject) => api<Session>(`/api/sessions/${encodeURIComponent(id)}/context`,'PATCH',{input_revision,context}),
  confirm: (id:string, input_revision:number, reviewed_by:string, review_notes:string, checks:AnyObject) => api<{confirmation_id:string}>(`/api/sessions/${encodeURIComponent(id)}/confirm`,'POST',{input_revision,reviewed_by,review_notes,checks}),
  calculate: (id:string, confirmation_id:string) => api<Session['calculations'][number]>(`/api/sessions/${encodeURIComponent(id)}/calculate`,'POST',{confirmation_id}),
};
