from fastapi import APIRouter, Header, HTTPException, Request

from .handlers import dispatch
from .line_client import verify_signature

router = APIRouter()


@router.post("/webhook")
async def webhook(
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
