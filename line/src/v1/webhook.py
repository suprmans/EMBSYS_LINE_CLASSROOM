from fastapi import APIRouter, Header, HTTPException, Request

from ..core.line_client import verify_signature
from .handlers import dispatch

router = APIRouter(tags=["Webhook v1"])


@router.post("/webhook/v1/", include_in_schema=False)
async def webhook_v1(
    request: Request,
    x_line_signature: str = Header(None),
):
    body = await request.body()

    if not x_line_signature or not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    for event in payload.get("events", []):
        await dispatch(event)

    return {"status": "ok"}
