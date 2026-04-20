import base64
import hashlib
import hmac
import os

import httpx

CHANNEL_SECRET       = os.environ["LINE_CHANNEL_SECRET"]
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
REPLY_URL            = "https://api.line.me/v2/bot/message/reply"


def verify_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode() == signature


async def reply(reply_token: str, text: str):
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        await client.post(REPLY_URL, json=payload, headers=headers)
