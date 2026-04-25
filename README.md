# Smart Classroom Attendance via LINE Beacon

**Author:** Shalong Samretnagn

ESP32-based smart attendance system for classrooms using BLE LINE Beacon and FastAPI. Students are identified automatically through their LINE `userId` and marked Present, Late, or Absent by session state — no app install, no QR code. The lecturer controls the session with 3 physical buttons. The backend uses FastAPI and PostgreSQL to process webhooks, register students, and push attendance status and quiz links via LINE Reply API.

Licensed under Apache License 2.0.

---

## Architecture Overview

### System Flow

```mermaid
flowchart LR
    subgraph HW["Hardware — ESP32"]
        BTN_B["Blue Button\nGPIO 26"]
        BTN_Y["Yellow Button\nGPIO 14"]
        BTN_R["Red Button\nGPIO 13"]
        LED_B["Blue LED GPIO 32\nsolid — OPEN"]
        LED_Y["Yellow LED GPIO 33\nsolid — LATE_CHECKIN\nfast blink — QUIZ"]
        LED_R["Red LED GPIO 25\n3× flash — ENDED"]
        BLE["BLE Advertiser\ncls:open / cls:late\ncls:qz / cls:end"]
        BTN_B & BTN_Y & BTN_R --> BLE
        BLE -.->|drives| LED_B & LED_Y & LED_R
    end

    subgraph PHONE["Student Phone"]
        LINE_APP["LINE App\nBluetooth ON"]
    end

    subgraph BACKEND["Cloud Backend"]
        WEBHOOK["FastAPI\nPOST /webhook/v1/"]
        DB[("PostgreSQL\nstudents\nsessions\nbeacon_events")]
        REPLY_API["LINE Reply API"]
    end

    BLE -->|"BLE Advertisement\n~10 m range"| LINE_APP
    LINE_APP -->|"beacon enter event\nHTTPS POST"| WEBHOOK
    WEBHOOK <-->|"read / write"| DB
    WEBHOOK -->|"reply_token"| REPLY_API
    REPLY_API -->|"chat reply"| LINE_APP
```

### ESP32 Dual-Core Architecture

```mermaid
graph TB
    subgraph ESP32["ESP32-WROOM-32 — Xtensa LX6 Dual-Core 240 MHz"]
        subgraph Core0["Core 0 — Protocol CPU"]
            BT_CTRL["Bluetooth Controller\nHCI + Link Layer"]
            BLE_HOST["BLE Host Stack\n(Bluedroid)"]
            ADV_TASK["Advertising Task\nbluetoothTask"]
            BT_CTRL --> BLE_HOST --> ADV_TASK
        end
        subgraph Core1["Core 1 — Application CPU"]
            SETUP["setup()\nGPIO init · BLEDevice::init()\nboot flash · advertiseBeacon(cls:idle)"]
            LOOP["loop()\nButton debounce 25 ms\nYellow LED blink — QUIZ only"]
            SM["transitionTo(state)\nLED output · advertiseBeacon(dm)"]
            SETUP --> LOOP --> SM
        end
        Core1 -->|"BLEAdvertising API\npAdv->stop() / setAdvertisementData() / start()"| Core0
    end
```

### Session State Machine

```mermaid
flowchart LR
    IDLE -->|"Blue / cls:open"| OPEN
    OPEN -->|"Yellow / cls:late"| LATE_CHECKIN
    LATE_CHECKIN -->|"Yellow / cls:qz"| QUIZ
    QUIZ -->|"Yellow / cls:late"| LATE_CHECKIN
    OPEN -->|"Red / cls:end"| ENDED
    LATE_CHECKIN -->|"Red / cls:end"| ENDED
    QUIZ -->|"Red / cls:end"| ENDED
    ENDED -->|"auto 5 s"| IDLE
```

### Button & LED Reference

| Button | GPIO | State transition | LED (GPIO) | Beacon payload | Student status |
|---|---|---|---|---|---|
| Blue | 26 | IDLE → OPEN | Blue 32 solid ON | `cls:open` | PRESENT |
| Yellow | 14 | OPEN → LATE_CHECKIN | Yellow 33 solid ON | `cls:late` | LATE (if not already checked in) |
| Yellow | 14 | LATE_CHECKIN → QUIZ | Yellow 33 fast blink 5 Hz | `cls:qz` | QUIZ |
| Red | 13 | any → ENDED | Red 25 × 3 flash | `cls:end` | ABSENT (unmarked students) |

---

## How Student Check-In Works

LINE fires a `beacon enter` event the **first time** the phone detects the beacon in a given session. If a student is already in range when the session changes state, they will **not** automatically receive the new message.

**To get the ✅ Present message:**
1. Make sure you are in range (~10 m) of the ESP32 when the blue LED is on (OPEN state)
2. If you were already in range before the lecturer pressed the button — walk out of range and walk back, **or** toggle Bluetooth off then on

**If you leave the room and come back:**
- LINE fires another `enter` event when you return
- Both events are stored in the full beacon log
- Your **official attendance status is set by the first event** (earliest timestamp) — subsequent re-entries are recorded for the audit trail only

---

## LINE Beacon Reference

### What is LINE Beacon

LINE Beacon lets a LINE Official Account receive webhook events when a user's LINE app detects a Bluetooth Low Energy (BLE) advertisement from a registered beacon device. This project uses the **LINE Simple Beacon** specification — any BLE hardware (e.g. ESP32) can act as a beacon as long as it advertises the correct frame format with a registered HWID.

**Requirements for a beacon event to fire:**
- The user's LINE app has **Bluetooth** and **LINE Beacon** enabled in LINE Settings → Privacy
- The user has **added the linked LINE OA as a friend**
- The user is within BLE range of the advertising device (~10 m)

> Reference: [Using beacons — LINE Developers](https://developers.line.biz/en/docs/messaging-api/using-beacons/)

---

### Beacon Event Webhook Payload

When a beacon event fires, LINE POSTs a webhook to your server. The `beacon` object contains:

| Field | Type | Description |
|---|---|---|
| `hwid` | string | 10-char hex hardware ID issued at manager.line.biz |
| `type` | string | `enter` \| `leave` \| `banner` \| `stay` |
| `dm` | string | Optional hex-encoded device message from the BLE advertisement |

**Event types:**

| Type | Description |
|---|---|
| `enter` | User's phone detects the beacon for the first time after entering range |
| `leave` | User's phone has moved out of beacon range (requires LINE ≥ 7.14.0) |
| `banner` | User tapped a beacon banner notification |
| `stay` | User remains in range (periodic re-notification) |

**Example payload:**

```json
{
  "replyToken": "<reply_token>",
  "type": "beacon",
  "mode": "active",
  "timestamp": 1462629479859,
  "source": {
    "type": "user",
    "userId": "U4af4980629..."
  },
  "webhookEventId": "<webhook_id>",
  "deliveryContext": { "isRedelivery": false },
  "beacon": {
    "hwid": "<hex_hardware_id>",
    "type": "enter",
    "dm": "636c733a6f70656e"
  }
}
```

The `dm` field is decoded by the backend to determine which session state fired the event:

| BLE payload | Hex `dm` | Session state | Attendance outcome |
|---|---|---|---|
| `cls:open` | `636c733a6f70656e` | OPEN | PRESENT |
| `cls:late` | `636c733a6c617465` | LATE_CHECKIN | LATE |
| `cls:qz` | `636c733a717a` | QUIZ | QUIZ (bonus) |
| `cls:end` | `636c733a656e64` | ENDED | ABSENT (unmarked) |

> Reference: [Beacon event — Messaging API Reference](https://developers.line.biz/en/reference/messaging-api/#beacon-event)

---

### HWID ↔ LINE OA Binding

The **hardware ID (HWID)** is a 10-character hex string (5 bytes) that ties a physical beacon device to a specific LINE Official Account. LINE's servers use the HWID in the BLE advertisement to look up the correct OA and route the webhook.

**How the binding works:**

```
ESP32 advertises HWID  →  LINE app detects BLE frame
→  LINE servers look up which OA owns that HWID
→  POST beacon webhook to that OA's webhook URL
```

**Key rules:**
- A HWID must be **issued** via [LINE OA Manager → Beacon](https://manager.line.biz/beacon/register) — arbitrary values will not trigger webhooks
- Each HWID is bound to **exactly one** LINE OA; one OA can have multiple HWIDs
- If the HWID in the BLE frame is not registered or not linked to an OA, **no webhook is sent** and LINE silently ignores the advertisement
- The HWID in `esp32/src/case01/case01.ino` must match the issued value byte-for-byte

**Issuing a HWID:**
1. Go to [manager.line.biz/beacon/register](https://manager.line.biz/beacon/register)
2. Click **Link beacons with bot account** → select your OA
3. Click **Issue LINE Simple Beacon hardware IDs** → **Issue hardware ID**
4. Copy the 10-char hex HWID and set `LINE_BEACON_HWID=<hwid>` in `.env`
5. Update `LINE_HWID` bytes in the Arduino sketch to match

---

## Quick Start

### 1. Prerequisites

- Python ≥ 3.12, [uv](https://github.com/astral-sh/uv), PostgreSQL 17
- Arduino IDE with ESP32 board package
- LINE OA channel (Messaging API) + LINE Manager account

### 2. Clone & bootstrap

```bash
git clone <repo>
cd EMBSYS_LINE_CLASSROOM
make setup
```

### 3. Configure environment

```bash
cp .env.example .env
# fill in: DATABASE_URL, LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, LECTURER_TOKEN
```

### 4. Set up LINE Beacon

> Full guide: https://developers.line.biz/en/docs/messaging-api/using-beacons/#getting-beacon

**Step 1 — Link beacon with your bot account**
1. Go to [LINE Manager → Beacon](https://manager.line.biz/beacon/register)
2. Click **Link beacons with bot account**
3. Select your OA (e.g. **scool.BEACON**) → **Select**

**Step 2 — Issue a hardware ID**
1. Click **Issue LINE Simple Beacon hardware IDs**
2. Select your OA → **Issue hardware ID**
3. Copy the 10-character hex HWID (e.g. `018f62bd52`)
4. Add it to `.env`: `LINE_BEACON_HWID=018f62bd52`

**Step 3 — Flash ESP32**
1. Open `esp32/src/case01/case01.ino` in Arduino IDE
2. Verify the `LINE_HWID` bytes match your issued HWID
3. Flash to ESP32

### 5. Start the backend

```bash
cd line
uv run uvicorn src.main:app --reload --port 8000
```

### 6. Expose via ngrok & set webhook

```bash
ngrok http 8000
```

In [LINE Developers Console](https://developers.line.me/console/) → Messaging API → Webhook URL:
```
https://<your-ngrok-id>.ngrok-free.app/webhook/v1/
```
Enable **Use webhook** → **Verify** (expect 200 OK).

### 7. Pre-schedule a session (lecturer)

Before pressing the blue button, create a session via the API so the time window is known:

```bash
curl -X POST -H "Authorization: Bearer <LECTURER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Week 12 — Real-Time Systems",
    "start_time": "2026-04-20T09:00:00+07:00",
    "end_time":   "2026-04-20T11:00:00+07:00",
    "slides_url": "bit.ly/emb-w12",
    "supplementary_url": "bit.ly/emb-w12-ref"
  }' \
  http://localhost:8000/api/v1/sessions/
```

If the blue button is pressed without a pre-scheduled session, a walk-in session is created automatically (students see a note in their reply).

### 8. Test

Open Swagger UI at `http://localhost:8000/docs`, click 🔒 **Authorize**, paste `LECTURER_TOKEN`.

Send **Hello** to your LINE OA — the bot should reply with a greeting.

---

## Hardware

| Component | GPIO | Role |
|---|---|---|
| Blue button | 26 | Start class (IDLE → OPEN) |
| Yellow button | 14 | Open late check-in (OPEN → LATE_CHECKIN) / start quiz (LATE_CHECKIN → QUIZ) |
| Red button | 13 | End class (any → ENDED) |
| Blue LED | 32 | Solid — session OPEN |
| Yellow LED | 33 | Solid — LATE_CHECKIN / fast blink 5 Hz — QUIZ |
| Red LED | 25 | 3× flash — session ENDED |

---

Sessions are pre-scheduled by the lecturer via `POST /api/v1/sessions/` with a Bangkok-time window.
The backend resolves the active session at event time — the ESP32 does not carry a session ID.

See `docs/` for full business case, API design, and conceptual diagrams.
