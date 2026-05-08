from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .line_bot import handle_line_webhook


router = APIRouter()
logger = logging.getLogger(__name__)
MAX_LINE_BODY_BYTES = 1024 * 1024


@router.post("/line/webhook")
async def line_webhook(request: Request) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_LINE_BODY_BYTES:
                raise HTTPException(status_code=413, detail="LINE webhook body is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content-length") from exc
    body = await request.body()
    if len(body) > MAX_LINE_BODY_BYTES:
        raise HTTPException(status_code=413, detail="LINE webhook body is too large")
    signature = request.headers.get("x-line-signature")
    try:
        return await handle_line_webhook(body, signature)
    except Exception as exc:
        logger.exception("LINE webhook failed")
        raise HTTPException(status_code=500, detail="LINE webhook failed") from exc


@router.post("/webhook")
async def legacy_line_webhook(request: Request) -> dict[str, Any]:
    return await line_webhook(request)
