#!/usr/bin/env python3
"""Patch Moa Settlement reminder flow with 3 relationship x 3 message styles.
Run from repository root: python install_reminder_styles.py
Does not change Git history, push or deploy.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import shutil
import sys
import re

ROOT = Path.cwd()
FILES = [
    'app.py',
    'src/settlements/reminder_writer.py',
    'mobile/src/services/api.ts',
    'mobile/src/app/index.tsx',
]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected exactly one matching section; found {n}. No files were changed.')
    return text.replace(old, new, 1)


def apply_app(s: str) -> str:
    s = replace_once(s,
        '    tone: Literal["friend", "senior", "junior"] = "friend"\n    repeat: StrictBool = False',
        '''    tone: Literal["friend", "senior", "junior"] = "friend"
    style: Literal["warm", "playful", "firm", "polite", "gentle", "formal", "friendly", "considerate", "clear"] | None = None
    repeat: StrictBool = False''', 'app.py ReminderBody')
    s = replace_once(s,
        '    @app.post("/api/reminders/generate")\n    def reminder_generate(body: ReminderBody, request: Request):',
        '''    @app.post("/api/reminders/generate")
    def reminder_generate(body: ReminderBody, request: Request):
        # An explicit style must belong to the selected relationship.
        allowed_styles = {
            "friend": {"warm", "playful", "firm"},
            "senior": {"polite", "gentle", "formal"},
            "junior": {"friendly", "considerate", "clear"},
        }
        if body.style is not None and body.style not in allowed_styles[body.tone]:
            raise HTTPException(422, "선택한 관계와 세부 말투가 일치하지 않습니다.")''',
        'app.py reminder endpoint')
    
    pattern = (
        r'(tone\s*=\s*body\.tone\s*,\s*'
        r'repeat\s*=\s*body\.repeat)'
        r'(?=\s*[,)])'
    )

    s, count = re.subn(
        pattern,
        r'\1, style=body.style',
        s,
    )

    if count != 1:
        raise RuntimeError(
            "app.py generate_reminder call: "
            f"expected exactly one matching section; found {count}. "
            "No files were changed."
        )

    return s

STYLE_CONFIG = '''STYLE_OPTIONS = {
    "friend": {
        "warm": "다정하게: 따뜻하고 편안한 반말로, 상대에게 부담을 주지 않고 요청",
        "playful": "장난스럽게: 가볍고 재치 있는 친구 말투, 비꼬거나 압박하지 않기",
        "firm": "단호하게: 무례하지 않되 짧고 명확하게 송금 확인 요청",
    },
    "senior": {
        "polite": "공손하게: 기본 존댓말, 예의를 지키며 정중히 요청",
        "gentle": "부드럽게: 따뜻하고 친근한 존댓말, 감사의 느낌 포함",
        "formal": "격식 있게: 공식적인 안내 문체, 군더더기 없이 간결하게",
    },
    "junior": {
        "friendly": "친근하게: 밝고 편안한 반말로 가볍게 요청",
        "considerate": "배려 있게: 상대 사정을 존중하며 부담 없이 확인 부탁",
        "clear": "깔끔하게: 핵심을 짧고 분명하게 정리하는 반말",
    },
}
DEFAULT_STYLE = {"friend": "warm", "senior": "polite", "junior": "friendly"}

'''

FALLBACK = '''def _fallback_body(tone: str, repeat: bool, style: str | None = None) -> str:
    """Deterministic, style-specific fallback when Gemini is unavailable."""
    style = style or DEFAULT_STYLE[tone]
    first = {
        "warm": "정산 내역 나왔어! 확인하고 편할 때 보내주면 고마워 😊",
        "playful": "우리 즐거운 모임 정산도 마무리하자! 확인하고 편할 때 부탁해 😄",
        "firm": "정산 내역을 확인하고 송금 부탁해. 확인되면 알려줘.",
        "polite": "정산 내역을 안내드립니다. 편하실 때 확인해 주시면 감사하겠습니다.",
        "gentle": "지난 모임 정산 내역 안내드려요. 시간 되실 때 편하게 확인 부탁드립니다 😊",
        "formal": "정산 내역을 전달드립니다. 확인 후 송금해 주시기 바랍니다. 감사합니다.",
        "friendly": "정산 내역 확인하고 편할 때 보내주면 돼! 고마워 😊",
        "considerate": "정산 내역 안내하려고 연락했어. 부담 갖지 말고 편할 때 확인 부탁해!",
        "clear": "정산 내역 확인 부탁해. 송금 후 알려주면 고마워!",
    }
    again = {
        "warm": "정산 내역 다시 알려줘! 이미 보냈다면 말해줘. 고마워 🙏",
        "playful": "정산 알림 한 번 더 살짝 남겨! 이미 보냈다면 알려줘 😄",
        "firm": "정산 내역을 다시 확인 부탁해. 이미 송금했다면 알려줘.",
        "polite": "정산 내역을 다시 안내드립니다. 이미 송금하셨다면 양해 부탁드리며, 확인 후 알려주시면 감사하겠습니다.",
        "gentle": "정산 내역 확인 차 다시 연락드려요. 이미 보내셨다면 양해 부탁드립니다 😊",
        "formal": "정산 내역 재안내드립니다. 이미 송금하셨다면 본 안내는 양해 부탁드립니다.",
        "friendly": "정산 내역 다시 한번 확인 부탁해! 이미 보냈다면 알려줘. 고마워 😊",
        "considerate": "혹시 정산 확인할 시간이 없었을까 봐 다시 남겨! 이미 보냈다면 알려줘.",
        "clear": "정산 내역 재확인 부탁해. 이미 송금했다면 알려줘.",
    }
    return (again if repeat else first)[style]


'''


def apply_writer(s: str) -> str:
    anchor = 'BODY_SCHEMA = {'
    if s.count(anchor) != 1:
        raise RuntimeError('reminder_writer.py BODY_SCHEMA missing')
    s = s.replace(anchor, STYLE_CONFIG + anchor, 1)
    a = s.index('def _fallback_body(')
    b = s.index('def compose_message(', a)
    s = s[:a] + FALLBACK + s[b:]
    # Optional style is placed after `client` to preserve legacy positional callers.
    if '    client=None,\n) -> dict:' in s:
        s = replace_once(s,
            '    client=None,\n) -> dict:',
            '    client=None,\n    style: str | None = None,\n) -> dict:',
            'reminder_writer.py generate signature')
    else:
        s = replace_once(s,
            'tone: str, repeat: bool, client=None) -> dict:',
            'tone: str, repeat: bool, client=None, style: str | None = None) -> dict:',
            'reminder_writer.py legacy generate signature')
    validation = """    # Preserve clients that only send relationship, without a sub-style.
    style = style or DEFAULT_STYLE[tone]
    if style not in STYLE_OPTIONS[tone]:
        raise ValueError("선택한 관계와 세부 말투가 일치하지 않습니다")

"""
    if '    # 2. Gemini 오류 시 사용할 기본 문구' in s:
        s = replace_once(s, '    # 2. Gemini 오류 시 사용할 기본 문구',
                         validation + '    # 2. Gemini 오류 시 사용할 기본 문구',
                         'reminder_writer.py style validation')
        s = replace_once(s, 'body = _fallback_body(tone, repeat)',
                         'body = _fallback_body(tone, repeat, style)', 'reminder_writer.py fallback')
    else:
        s = replace_once(s, '    source, body = "template", _fallback_body(tone, repeat)',
                         validation + '    source, body = "template", _fallback_body(tone, repeat, style)',
                         'reminder_writer.py legacy fallback')
    # Append without personal data, for both compact and multiline prompt styles.
    s = replace_once(s,
        '        model_response = (',
        '        prompt += f"\\n세부 말투: {STYLE_OPTIONS[tone][style]}"\n        model_response = (',
        'reminder_writer.py Gemini prompt extension')
    return s


def apply_api(s: str) -> str:
    s = replace_once(s,
        "export type ReminderTone = 'friend'|'senior'|'junior';",
        "export type ReminderTone = 'friend'|'senior'|'junior';\nexport type ReminderStyle = 'warm'|'playful'|'firm'|'polite'|'gentle'|'formal'|'friendly'|'considerate'|'clear';",
        'api.ts tone type')
    s = replace_once(s,
        'title:string;tone:ReminderTone;repeat:boolean',
        'title:string;tone:ReminderTone;style?:ReminderStyle;repeat:boolean',
        'api.ts reminder payload')
    return s

FRONT_TYPES = '''type ReminderStyle='warm'|'playful'|'firm'|'polite'|'gentle'|'formal'|'friendly'|'considerate'|'clear';
const REMINDER_STYLES:Record<ReminderTone,Array<{value:ReminderStyle;label:string;description:string}>>={
 friend:[
  {value:'warm',label:'다정하게',description:'부담 없이 부드럽게 부탁'},
  {value:'playful',label:'장난스럽게',description:'친구끼리 가볍고 유쾌하게'},
  {value:'firm',label:'단호하게',description:'짧고 명확하게 정산 요청'},
 ],
 senior:[
  {value:'polite',label:'공손하게',description:'정중한 존댓말로 부탁'},
  {value:'gentle',label:'부드럽게',description:'친근하면서 예의를 갖춰서'},
  {value:'formal',label:'격식 있게',description:'공식적이고 간결한 안내'},
 ],
 junior:[
  {value:'friendly',label:'친근하게',description:'편안하고 밝게 부탁'},
  {value:'considerate',label:'배려 있게',description:'상대방 사정을 존중하며 요청'},
  {value:'clear',label:'깔끔하게',description:'핵심만 짧고 분명하게'},
 ],
};
const DEFAULT_REMINDER_STYLE:Record<ReminderTone,ReminderStyle>={friend:'warm',senior:'polite',junior:'friendly'};
'''

FRONT_TEMPLATE = '''// Local fallback also follows the selected relationship and sub-style.
const reminderText=(title:string,from:string,to:string,amount:number,tone:ReminderTone,repeat:boolean,style:ReminderStyle=DEFAULT_REMINDER_STYLE[tone])=>{
 const first:Record<ReminderStyle,string>={
  warm:'정산 내역 나왔어! 확인하고 편할 때 보내주면 고마워 😊',
  playful:'우리 즐거운 모임 정산도 마무리하자! 확인하고 편할 때 부탁해 😄',
  firm:'정산 내역을 확인하고 송금 부탁해. 확인되면 알려줘.',
  polite:'정산 내역을 안내드립니다. 편하실 때 확인해 주시면 감사하겠습니다.',
  gentle:'지난 모임 정산 내역 안내드려요. 시간 되실 때 편하게 확인 부탁드립니다 😊',
  formal:'정산 내역을 전달드립니다. 확인 후 송금해 주시기 바랍니다. 감사합니다.',
  friendly:'정산 내역 확인하고 편할 때 보내주면 돼! 고마워 😊',
  considerate:'정산 내역 안내하려고 연락했어. 부담 갖지 말고 편할 때 확인 부탁해!',
  clear:'정산 내역 확인 부탁해. 송금 후 알려주면 고마워!',
 };
 const again:Record<ReminderStyle,string>={
  warm:'정산 내역 다시 알려줘! 이미 보냈다면 말해줘. 고마워 🙏',
  playful:'정산 알림 한 번 더 살짝 남겨! 이미 보냈다면 알려줘 😄',
  firm:'정산 내역을 다시 확인 부탁해. 이미 송금했다면 알려줘.',
  polite:'정산 내역을 다시 안내드립니다. 이미 송금하셨다면 양해 부탁드리며, 확인 후 알려주시면 감사하겠습니다.',
  gentle:'정산 내역 확인 차 다시 연락드려요. 이미 보내셨다면 양해 부탁드립니다 😊',
  formal:'정산 내역 재안내드립니다. 이미 송금하셨다면 본 안내는 양해 부탁드립니다.',
  friendly:'정산 내역 다시 한번 확인 부탁해! 이미 보냈다면 알려줘. 고마워 😊',
  considerate:'혹시 정산 확인할 시간이 없었을까 봐 다시 남겨! 이미 보냈다면 알려줘.',
  clear:'정산 내역 재확인 부탁해. 이미 송금했다면 알려줘.',
 };
 const allowed=REMINDER_STYLES[tone].some(x=>x.value===style);
 const choice=allowed?style:DEFAULT_REMINDER_STYLE[tone];
 return `[${title}] 송금 안내\\n${from} → ${to}: ${money(amount)}\\n\\n${(repeat?again:first)[choice]}`;
};
'''

FRONT_PANEL = '''        return <View style={{gap:9}}>
         <Text style={styles.label}>1. 상대방과의 관계</Text>
         <View style={styles.wrap}>
          <Chip text="친구" active={tone==='friend'} onPress={()=>chooseTone(t.key,'friend')}/>
          <Chip text="선배" active={tone==='senior'} onPress={()=>chooseTone(t.key,'senior')}/>
          <Chip text="후배" active={tone==='junior'} onPress={()=>chooseTone(t.key,'junior')}/>
         </View>
         <Text style={styles.label}>2. 원하는 세부 말투</Text>
         <View style={{gap:7}}>
          {REMINDER_STYLES[tone].map(option=><Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{selected:style===option.value}}
            onPress={()=>chooseStyle(t.key,option.value)}
            style={{borderWidth:style===option.value?2:1,borderColor:style===option.value?C.green:C.line,backgroundColor:style===option.value?C.greenSoft:C.white,borderRadius:12,padding:12}}
          ><Text style={{color:C.ink,fontWeight:'800'}}>{style===option.value?'◉ ':'◯ '}{option.label}</Text>
           <Text style={styles.muted}>{option.description}</Text>
          </Pressable>)}
         </View>
         <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between'}}>
          <View style={{flex:1}}><Text style={styles.label}>3. 재독촉 문구로 만들기</Text>
           <Text style={styles.muted}>이전에 안내한 경우 선택해 주세요.</Text></View>
          <Switch value={repeat} onValueChange={value=>chooseRepeat(t.key,value)} trackColor={{false:'#D7DDD7',true:'#8EC2A9'}} thumbColor={repeat?C.green:'#F7F8F6'}/>
         </View>
         <Text style={styles.muted}>{repeat?'재안내 문구':'첫 안내 문구'} · {draft?.source==='gemini'?'Gemini 작성':draft?.source==='template'?'기본 문구(대체)':'기본 문구'} · {sid.startsWith('local-diff-')?'직접 입력한 송금액':'확정 계산된 송금액'} 기준</Text>
         <Button text={aiReminderBusyKey===draftKey?'AI 문구 생성 중…':'✨ Gemini로 안내 문구 만들기'} secondary small disabled={!!aiReminderBusyKey} onPress={()=>createAiReminder(t,tone,style,repeat,draftKey)}/>
         <Text style={styles.reminderMessage}>{msg}</Text>
         <View style={styles.wrap}>
          <Button text="문구 복사" secondary small onPress={()=>copyReminder(msg).catch(e=>Alert.alert('복사 실패',String(e?.message||e)))}/>
          <Button text="공유하기" secondary small onPress={()=>shareReminder(msg).catch(e=>Alert.alert('공유 실패',String(e?.message||e)))}/>
          <Button text="안내했어요 · 기록" small onPress={()=>markReminder(t)}/>
         </View>
         <Text style={styles.helper}>실제 발송은 자동으로 이루어지지 않습니다. 전달을 완료한 뒤에만 '안내했어요'를 눌러 주세요.</Text>
        </View>;'''


def apply_front(s: str) -> str:
    s = replace_once(s,
        "type ReminderTone='friend'|'senior'|'junior';",
        "type ReminderTone='friend'|'senior'|'junior';\n" + FRONT_TYPES.rstrip(),
        'index.tsx reminder types')
    s = replace_once(s,
        'reminderTones?:Record<string,ReminderTone>;deleted?:boolean',
        'reminderTones?:Record<string,ReminderTone>;reminderStyles?:Record<string,ReminderStyle>;reminderRepeats?:Record<string,boolean>;deleted?:boolean',
        'index.tsx LocalMeta')
    a = s.index('const reminderText=(')
    b = s.index('const names=(', a)
    s = s[:a] + FRONT_TEMPLATE + s[b:]
    s = replace_once(s,
        '''   const tones=meta[sid]?.reminderTones||{};
   const chooseTone=(key:string,tone:ReminderTone)=>setLocal(sid,{reminderTones:{...tones,[key]:tone}});''',
        '''   const tones=meta[sid]?.reminderTones||{};
   const styleChoices=meta[sid]?.reminderStyles||{};
   const repeatChoices=meta[sid]?.reminderRepeats||{};
   const chooseTone=(key:string,tone:ReminderTone)=>setLocal(sid,{
    reminderTones:{...tones,[key]:tone},
    reminderStyles:{...styleChoices,[key]:DEFAULT_REMINDER_STYLE[tone]},
   });
   const chooseStyle=(key:string,style:ReminderStyle)=>setLocal(sid,{reminderStyles:{...styleChoices,[key]:style}});
   const chooseRepeat=(key:string,value:boolean)=>setLocal(sid,{reminderRepeats:{...repeatChoices,[key]:value}});''',
        'index.tsx chooseTone')
    s = replace_once(s,
        'const createAiReminder=async(t:typeof stats.rows[number],tone:ReminderTone,repeat:boolean,cacheKey:string)=>{',
        'const createAiReminder=async(t:typeof stats.rows[number],tone:ReminderTone,style:ReminderStyle,repeat:boolean,cacheKey:string)=>{',
        'index.tsx createAiReminder declaration')
    s = replace_once(s,
        "title:meta[sid]?.title||'모아정산',tone,repeat,",
        "title:meta[sid]?.title||'모아정산',tone,style,repeat,",
        'index.tsx API reminder body')
    s = replace_once(s,
        't.amount,tone,repeat),source:\'template\'',
        't.amount,tone,repeat,style),source:\'template\'',
        'index.tsx catch fallback')
    s = replace_once(s,
        '''       const tone=tones[t.key]||'friend';
       const repeat=(reminders[t.key]?.count||0)>0;
       const draftKey=JSON.stringify([sid,t.key,tone,repeat,meta[sid]?.title||'모아정산']);
       const draft=aiReminders[draftKey];
       const msg=draft?.message||reminderText(meta[sid]?.title||'모아정산',t.from_participant,t.to_participant,t.amount,tone,repeat);''',
        '''       const tone=tones[t.key]||'friend';
        const currentStyle=styleChoices[t.key]||DEFAULT_REMINDER_STYLE[tone];
        const style=REMINDER_STYLES[tone].some(x=>x.value===currentStyle)?currentStyle:DEFAULT_REMINDER_STYLE[tone];
        const repeat=repeatChoices[t.key]??((reminders[t.key]?.count||0)>0);
        const draftKey=JSON.stringify([sid,t.key,tone,style,repeat,meta[sid]?.title||'모아정산']);
       const draft=aiReminders[draftKey];
       const msg=draft?.message||reminderText(meta[sid]?.title||'모아정산',t.from_participant,t.to_participant,t.amount,tone,repeat,style);''',
        'index.tsx draft setup')
    a = s.index('       return <View style={{gap:9}}>', s.index('const draftKey=JSON.stringify([sid,t.key,tone,style,repeat'))
    b = s.index('       </View>;', a)+len('       </View>;')
    s = s[:a] + FRONT_PANEL + s[b:]
    return s


def main() -> int:
    source = {}
    try:
        for p in FILES:
            file = ROOT / p
            if not file.is_file():
                raise RuntimeError(f'Missing file: {file}')
            source[p] = file.read_text(encoding='utf-8-sig')
        changes = {
            'app.py': apply_app(source['app.py']),
            'src/settlements/reminder_writer.py': apply_writer(source['src/settlements/reminder_writer.py']),
            'mobile/src/services/api.ts': apply_api(source['mobile/src/services/api.ts']),
            'mobile/src/app/index.tsx': apply_front(source['mobile/src/app/index.tsx']),
        }
        # Compile newly generated Python before touching source files.
        compile(changes['app.py'], 'app.py', 'exec')
        compile(changes['src/settlements/reminder_writer.py'], 'reminder_writer.py', 'exec')
    except Exception as exc:
        print(f'[STOP] {exc}', file=sys.stderr)
        return 1

    backup = ROOT / ('_backup_reminder_styles_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    for p in FILES:
        dst = backup / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / p, dst)
    try:
        for p in FILES:
            (ROOT / p).write_text(changes[p], encoding='utf-8')
    except Exception:
        for p in FILES:
            shutil.copy2(backup / p, ROOT / p)
        raise
    print('[OK] Added 9 sub-styles, repeat toggle, style-specific local fallback and Gemini prompt.')
    print('[OK] Changed: ' + ', '.join(FILES))
    print('[BACKUP] ' + str(backup))
    print('Next: $env:PYTHONPATH="src"; python -m pytest tests -q')
    print('Then: cd mobile; npx.cmd tsc --noEmit; npx.cmd expo export --platform web')
    return 0


if __name__ == '__main__':
    sys.exit(main())
