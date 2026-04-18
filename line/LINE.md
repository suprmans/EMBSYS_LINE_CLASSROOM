# LINE Module — Smart Classroom Attendance

## Overview

The LINE module is the cloud-facing half of the system. It receives beacon proximity webhooks from the LINE platform, identifies students by `userId`, logs attendance, and sends course materials — all via the free **Reply API** (zero quota cost).

---

## How LINE Beacon Works (Platform Flow)

```
Student's phone (LINE app, Bluetooth ON, "Use LINE Beacon" enabled)
        │
        │  walks within ~10 m BLE range of ESP32
        ▼
LINE platform detects beacon advertisement
        │
        ▼
LINE platform fires POST /webhook  ──► FastAPI backend
        │
        ▼
Backend reads userId + dm payload → logs attendance → sends reply
```

### Three conditions required on the student's phone

| Condition | Where to enable |
|---|---|
| Bluetooth ON | Device settings |
| "Use LINE Beacon" ON | LINE → Privacy settings |
| Following the course OA | LINE app — follow once at first class |

---

## Beacon Webhook Payload

LINE sends a `POST` to your webhook URL for every beacon event.

```json
{
  "destination": "Uxxxxxxxxxx",
  "events": [
    {
      "replyToken": "<reply-token>",
      "type": "beacon",
      "mode": "active",
      "timestamp": 1462629479859,
      "source": {
        "type": "user",
        "userId": "U4af4980629..."
      },
      "webhookEventId": "<webhook-event-id>",
      "deliveryContext": { "isRedelivery": false },
      "beacon": {
        "hwid": "d41d8cd98f",
        "type": "enter",
        "dm": "cls:open:001"
      }
    }
  ]
}
```

### Field reference

| Field | Description |
|---|---|
| `replyToken` | Single-use token for a free Reply API call (expires ~1 min) |
| `source.userId` | Unique LINE user ID — phone-bound, cannot be spoofed |
| `beacon.hwid` | Hardware ID of the ESP32 beacon, registered in LINE OA Manager |
| `beacon.type` | `"enter"` when student enters range; `"leave"` on exit; `"banner"` on tap |
| `beacon.dm` | Device message — custom payload set by ESP32 (max 13 bytes) |

### dm payload convention (this project)

| `dm` value | Session state | Backend action |
|---|---|---|
| `"cls:idle"` | IDLE | Ignore — room not active |
| `"cls:open:001"` | OPEN (15 min window) | Log PRESENT, reply with slides |
| `"cls:run:001"` | RUNNING (late window) | Log LATE, reply with slides |
| `"cls:qz:001"` | QUIZ active | Reply LIFF quiz link |
| `"cls:end:001"` | ENDED | Mark absentees, push summary |

The three-part format is `cls:<state>:<session_id>` — session ID prevents replay across weeks.

---

## FastAPI Backend

### Project structure

```
line/
├── LINE.md          ← this file
├── main.py          ← FastAPI app entry point
├── webhook.py       ← /webhook router
├── handlers.py      ← beacon + message event logic
├── database.py      ← SQLite helpers (register, log, query)
├── line_client.py   ← Reply API wrapper
└── models.py        ← Pydantic schemas for webhook payload
```

### Signature verification (required by LINE)

LINE signs every request with HMAC-SHA256 using your **channel secret**.  
You **must** validate the `X-Line-Signature` header before processing — LINE will block misconfigured endpoints during webhook verification.

```python
import hashlib, hmac, base64

def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    digest = hmac.new(
        channel_secret.encode(), body, hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode() == signature
```

### FastAPI app skeleton

```python
# main.py
from fastapi import FastAPI
from webhook import router

app = FastAPI()
app.include_router(router)
```

```python
# webhook.py
from fastapi import APIRouter, Request, HTTPException, Header
from line_client import verify_signature, CHANNEL_SECRET
from handlers import dispatch

router = APIRouter()

@router.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(None),
):
    body = await request.body()
    if not verify_signature(body, x_line_signature, CHANNEL_SECRET):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    for event in payload.get("events", []):
        await dispatch(event)

    return {"status": "ok"}
```

```python
# handlers.py
from database import get_student, log_attendance, mark_absentees
from line_client import reply

async def dispatch(event: dict):
    etype = event.get("type")
    if etype == "beacon":
        await handle_beacon(event)
    elif etype == "message":
        await handle_registration(event)

async def handle_beacon(event: dict):
    user_id    = event["source"]["userId"]
    reply_tkn  = event["replyToken"]
    dm         = event["beacon"].get("dm", "")
    beacon_type = event["beacon"].get("type", "")

    # Only act on entry events
    if beacon_type != "enter":
        return

    student = get_student(user_id)
    if not student:
        await reply(reply_tkn, "Welcome! Please register by sending your student ID.")
        return

    if dm.startswith("cls:idle"):
        return  # session not active

    elif dm.startswith("cls:open"):
        log_attendance(student["id"], "PRESENT")
        await reply(reply_tkn, f"Present! {student['name']}. Slides: bit.ly/emb-w12")

    elif dm.startswith("cls:run"):
        log_attendance(student["id"], "LATE")
        await reply(reply_tkn, f"Late noted. {student['name']}. Slides: bit.ly/emb-w12")

    elif dm.startswith("cls:qz"):
        await reply(reply_tkn, "Quiz is live! Open: liff.line.me/quiz-emb")

    elif dm.startswith("cls:end"):
        mark_absentees(dm)  # session_id extracted from dm

async def handle_registration(event: dict):
    user_id    = event["source"]["userId"]
    reply_tkn  = event["replyToken"]
    text       = event["message"]["text"].strip()

    if text.isdigit() and len(text) == 10:
        from database import register_student
        register_student(user_id, text)
        await reply(reply_tkn, f"Registered! Student ID: {text}. All future classes are automatic.")
    else:
        await reply(reply_tkn, "Please send your 10-digit student ID to register.")
```

### Reply API helper

```python
# line_client.py
import os, httpx

CHANNEL_SECRET       = os.environ["LINE_CHANNEL_SECRET"]
CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
REPLY_URL            = "https://api.line.me/v2/bot/message/reply"

async def reply(reply_token: str, text: str):
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    body = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        await client.post(REPLY_URL, json=body, headers=headers)
```

### Database helpers

```python
# database.py
import sqlite3, contextlib

DB_PATH = "attendance.db"

def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                user_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL,
                name TEXT DEFAULT ''
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT,
                session_id TEXT,
                status TEXT,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")

@contextlib.contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

def get_student(user_id: str):
    with _conn() as c:
        row = c.execute("SELECT * FROM students WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

def register_student(user_id: str, student_id: str):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO students(user_id, student_id) VALUES(?,?)",
                  (user_id, student_id))

def log_attendance(student_id: str, status: str, session_id: str = ""):
    with _conn() as c:
        c.execute("INSERT INTO attendance(student_id, session_id, status) VALUES(?,?,?)",
                  (student_id, session_id, status))

def mark_absentees(dm: str):
    # dm = "cls:end:001" → session_id = "001"
    parts = dm.split(":")
    session_id = parts[2] if len(parts) == 3 else ""
    with _conn() as c:
        present = {r["student_id"] for r in
                   c.execute("SELECT student_id FROM attendance WHERE session_id=?",
                             (session_id,)).fetchall()}
        all_students = {r["student_id"] for r in
                        c.execute("SELECT student_id FROM students").fetchall()}
        for sid in all_students - present:
            c.execute("INSERT INTO attendance(student_id, session_id, status) VALUES(?,?,?)",
                      (sid, session_id, "ABSENT"))
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `LINE_CHANNEL_SECRET` | Channel secret — used for signature verification |
| `LINE_CHANNEL_ACCESS_TOKEN` | Long-lived token for Reply/Push API calls |

Set in `.env` (never commit) and load with `python-dotenv` or Render/Railway secrets.

---

## Running Locally

```bash
# install deps
pip3.12 install fastapi uvicorn httpx python-dotenv

# expose via ngrok for LINE webhook registration
ngrok http 8000

# run server
uvicorn main:app --reload --port 8000
```

Register `https://<ngrok-id>.ngrok.io/webhook` in LINE Developers console under **Messaging API → Webhook URL**.

---

## Cost Model

| Action | Quota used |
|---|---|
| Reply API (beacon reply) | **0** — Reply tokens are free and unlimited |
| Push API | Counts toward free-tier monthly quota (500 msg/mo) |
| LINE OA monthly fee | ฿0 on free tier |

Use Reply API exclusively for all beacon responses to stay at zero cost.

---

## Registration Flow (One-Time)

```
Student follows OA
      │
      ▼
Bot: "Welcome! Send your student ID."
      │
      ▼
Student sends: "6501234567"
      │
      ▼
Backend: stores userId → studentId
      │
      ▼
All future classes: fully automatic — no student action needed
```

---

## Anti-Cheat Properties

- `userId` is LINE-account-bound — cannot be shared or spoofed
- Student must be physically within ~10 m BLE range
- LDR on ESP32 confirms room light is ON (locked/dark room = no session)
- Session ID in `dm` is unique per class — prevents cross-week replay
