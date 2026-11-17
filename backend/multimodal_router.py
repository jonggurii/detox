"""호환용 Gemini 이미지 미리보기 라우터. 영수증 확정 전 사용자 검수를 강제한다."""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
import httpx
import asyncio

from settlements.receipt_reader import MAX_BYTES, GeminiReceiptReader, ReceiptExtractionError


def make_multimodal_router(app):
    router = APIRouter()

    class ConfirmedImage(BaseModel):
        text: str = Field(default="", max_length=12000)
        reviewed_text: str = Field(min_length=1, max_length=24000)

    async def preview(file: UploadFile):
        # SDK는 GeminiReceiptReader에서만 호출하며, 단일 GEMINI_MODEL을 사용한다.
        data = await file.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            raise HTTPException(413, "이미지는 10MB 이하로 첨부해 주세요.")
        try:
            result = await asyncio.to_thread(GeminiReceiptReader().extract_bytes, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except ReceiptExtractionError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"items": result["items"], "total_amount": result["total_amount"],
                "notes": result["warnings"], "original_text": "",
                "review_required": True}

    @router.post("/api/receipts/multimodal-preview")
    async def preview_image(file: UploadFile = File(...), text: str = Form("")):
        result = await preview(file)
        # 자연어는 영수증 사실과 구분해 그대로 보존한다.
        result["original_text"] = text
        return result

    @router.post("/api/receipts/multimodal-confirm")
    async def confirm_image(body: ConfirmedImage):
        # 사용자가 실제 확인한 텍스트만 정산 파서로 전달한다.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://localhost", timeout=150) as client:
            res = await client.post("/api/sessions", json={
                "text": body.text.strip() or "영수증에 기재된 결제 내용을 검토해 줘.",
                "supplied_evidence": body.reviewed_text,
            })
        try:
            response = res.json()
        except ValueError as exc:
            raise HTTPException(502, "정산 파서가 올바른 응답을 반환하지 않았습니다.") from exc
        if res.status_code >= 400:
            raise HTTPException(res.status_code, response.get("detail", "파서 처리 실패")
                                if isinstance(response, dict) else "파서 처리 실패")
        return response

    @router.post("/api/sessions/multimodal")
    async def legacy_multimodal(file: UploadFile = File(...), text: str = Form("")):
        # 이전 경로도 사용자 확인 없이 정산 세션을 자동 생성하지 않는다.
        return await preview_image(file, text)

    return router
