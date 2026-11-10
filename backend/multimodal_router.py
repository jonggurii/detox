"""Optional FastAPI router: photo + text -> Gemini multimodal -> existing session parser.

Install: pip install python-multipart httpx
In app.py AFTER app = FastAPI(...):
    from backend.multimodal_router import make_multimodal_router
    app.include_router(make_multimodal_router(app))
Requires GEMINI_API_KEY environment variable. No OCR or manual re-entry.
"""
import asyncio
import base64
import json
import os
from urllib import request, error

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile


def make_multimodal_router(app):
    router = APIRouter()

    @router.post('/api/sessions/multimodal')
    async def analyze_image(file: UploadFile = File(...), text: str = Form('')):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise HTTPException(503, 'GEMINI_API_KEY 환경변수가 설정되지 않았습니다.')
        mime = file.content_type or 'image/jpeg'
        if mime not in ('image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'):
            raise HTTPException(415, 'JPG, PNG, WEBP 또는 HEIC 이미지만 지원합니다.')
        data = await file.read(8 * 1024 * 1024 + 1)
        if not data or len(data) > 8 * 1024 * 1024:
            raise HTTPException(413, '사진은 8MB 이하로 첨부해 주세요.')
        model = os.getenv('GEMINI_MULTIMODAL_MODEL', 'gemini-2.5-flash')
        prompt = (
            '당신은 모임 정산 정보를 추출하는 도우미입니다. 이미지와 사용자 설명을 함께 읽고 '
            '이미지에 보이는 결제 금액, 메뉴, 영수증 합계, 날짜 및 사용자 설명의 참여자, 차수, '
            '결제자, 항목별 부담자, 비주류 제외, 중도 이탈, 찬조를 한국어 자연어로 빠짐없이 정리하세요. '
            '사진에서 읽기 어려운 값은 추측하지 말고 불명확하다고 적으세요. '
            '사용자 설명과 사진이 충돌하면 둘 다 명시하고 확정하지 마세요. '
            '정산 금액을 임의로 계산하지 마세요.\n\n사용자 설명:\n' + (text or '(추가 설명 없음)')
        )
        payload = {
            'contents': [{'role': 'user', 'parts': [
                {'text': prompt},
                {'inline_data': {'mime_type': mime, 'data': base64.b64encode(data).decode('ascii')}}
            ]}],
            'generationConfig': {'temperature': 0.1}
        }

        def call_gemini():
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            req = request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={
                'Content-Type': 'application/json', 'x-goog-api-key': api_key
            }, method='POST')
            with request.urlopen(req, timeout=120) as res:
                return json.load(res)

        try:
            result = await asyncio.to_thread(call_gemini)
            parts = result['candidates'][0]['content']['parts']
            extracted = '\n'.join(p.get('text', '') for p in parts).strip()
            if not extracted:
                raise ValueError('모델에서 추출한 텍스트가 없습니다.')
        except error.HTTPError as exc:
            detail = exc.read(2000).decode('utf-8', 'replace')
            raise HTTPException(502, f'Gemini 이미지 분석 실패 ({exc.code}): {detail}') from exc
        except Exception as exc:
            raise HTTPException(502, f'Gemini 이미지 분석 실패: {exc}') from exc

        # Preserve the existing ontology/schema, revisions, validation and session creation.
        # This second step uses the already-installed Gemini text parser; no OCR step.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://localhost', timeout=150) as client:
            res = await client.post('/api/sessions', json={
                'text': extracted,
                'supplied_evidence': '사용자 설명: ' + (text or '(없음)') + '\n이미지: ' + (file.filename or '첨부 사진')
            })
        try:
            body = res.json()
        except ValueError:
            raise HTTPException(502, f'기존 정산 파서 응답 오류: HTTP {res.status_code}')
        if res.status_code >= 400:
            raise HTTPException(res.status_code, body.get('detail', body) if isinstance(body, dict) else body)
        return body

    return router
