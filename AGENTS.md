# AGENTS.md — AI Agent Guide
### Smart Classroom Attendance via LINE Beacon

This file gives an AI agent everything needed to work on this project cold.
Read it fully before touching any code.

---

## What This Project Does

An ESP32 on a classroom desk broadcasts a BLE LINE Beacon. When a student's phone
enters range (~10 m), LINE fires a webhook to the backend. The backend logs their
attendance and replies to their LINE chat — no app install, no QR code, no manual sign-in.

A lecturer controls the session with 3 physical buttons. Each button changes session
state and updates the beacon payload, which changes what every student receives.

**Issued HWID:** `018f62bd52` (LINE Manager → scool.BEACON)

---

## Repo Layout

```
.
├── AGENTS.md               ← you are here
├── DEVELOPMENT.md          ← setup, DB commands, beacon setup, pre-commit workflow
├── .env                    ← secrets (git-ignored) — never commit
├── .env.example            ← template with placeholder values
├── Makefile                ← make setup / make check-env / make precommit-run
│
├── docs/
│   ├── ConceptualV1.md     ← full system concept + hardware GPIO reference
│   ├── BusinessCase01.md   ← button/LED/state design for v1
│   ├── SystemCase01.md     ← API endpoint + query design for v1
│   ├── DesignBusiness.md   ← template for future BusinessCaseNN.md
│   └── DesignSystem.md     ← template for future SystemCaseNN.md
│
├── esp32/
│   └── src/
│       ├── button_led.ino          ← original hardware prototype (do not modify)
│       └── case01/
│           └── case01.ino          ← BusinessCase01 firmware (BLE beacon + state machine)
│
└── line/                   ← Python FastAPI backend
    ├── pyproject.toml
    └── src/
        ├── main.py         ← app entry point, loads .env, wires routers
        ├── core/           ← shared across all API versions
        │   ├── auth.py         Bearer token dependency (require_lecturer)
        │   ├── database.py     All DB tables + every query function (PostgreSQL)
        │   └── line_client.py  verify_signature(), reply()
        └── v1/             ← BusinessCase01
            ├── webhook.py      POST /webhook/v1/  (LINE calls this)
            ├── handlers.py     beacon + message dispatch logic
            └── api.py          Lecturer admin endpoints under /api/v1/
```

---

## Environment

| Variable | Used by | Notes |
|---|---|---|
| `DATABASE_URL` | `core/database.py` | PostgreSQL DSN — required, no default |
| `LINE_CHANNEL_SECRET` | `core/line_client.py` | Signature verification |
| `LINE_CHANNEL_ACCESS_TOKEN` | `core/line_client.py` | Reply API auth |
| `LINE_CHANNEL_ID` | reference only | Not read in code |
| `LINE_BEACON_HWID` | reference / firmware | `018f62bd52` — issued from LINE Manager |
| `LINE_WEBHOOK_URL` | reference only | Set in LINE Developers Console |
| `LECTURER_TOKEN` | `core/auth.py` | Bearer token for all `/api/` routes |

`load_dotenv` runs at the top of `main.py` **before** any relative imports — this is
intentional because `core/line_client.py` reads `os.environ` at module level.

All timestamps are stored as `TIMESTAMPTZ`. The DB connection forces `timezone=Asia/Bangkok`
so all values display and compare in Bangkok time (UTC+7).

---

## LINE Beacon Setup (one-time)

> Docs: https://developers.line.biz/en/docs/messaging-api/using-beacons/#getting-beacon

1. **LINE Manager → [Beacon](https://manager.line.biz/beacon/register)**
2. **Link beacons with bot account** → select OA → **Select**
3. **Issue LINE Simple Beacon hardware IDs** → select OA → **Issue hardware ID**
4. Copy 10-char hex HWID → add to `.env` as `LINE_BEACON_HWID`
5. Update `LINE_HWID[5]` bytes in `esp32/src/case01/case01.ino` to match
6. Flash ESP32 → start backend → set webhook URL in LINE Developers Console → **Verify**

---

## How to Run

```bash
cd line
uv run uvicorn src.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs`
Click 🔒 **Authorize** → paste `LECTURER_TOKEN` to use lecturer endpoints.

For public webhook (ngrok):
```bash
ngrok http 8000
# paste https://<id>.ngrok-free.app/webhook/v1/ into LINE Developers Console
```

**Note:** the venv uses Python 3.14. Always use `uv run python` (not `uv run python3.12`)
when running scripts inside `line/`.

---

## API Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/webhook/v1/` | LINE signature | LINE events (beacon + message) |
| `POST` | `/api/v1/sessions/` | Bearer | Pre-schedule a session (label + time window + materials) |
| `GET` | `/api/v1/sessions/` | Bearer | List sessions + attendance counts |
| `GET` | `/api/v1/sessions/{id}/` | Bearer | Single session detail |
| `PATCH` | `/api/v1/sessions/{id}/` | Bearer | Update slides_url / supplementary_url |
| `GET` | `/api/v1/sessions/{id}/attendance` | Bearer | Official attendance (first event per student) |
| `PATCH` | `/api/v1/sessions/{id}/attendance` | Bearer | Manual status override |
| `GET` | `/api/v1/sessions/{id}/log` | Bearer | Full beacon log — all re-entries per student |
| `GET` | `/api/v1/sessions/{id}/export` | Bearer | CSV / JSON export of attendance |
| `GET` | `/api/v1/students/` | Bearer | List registered students |
| `DELETE` | `/api/v1/students/{id}` | Bearer | Unregister a student |

---

## Database Schema (PostgreSQL)

```sql
students        user_id (PK), student_id (UNIQUE), name, registered_at

sessions        session_id (PK, UUID text), label, version,
                start_time, end_time,          -- Bangkok-time window
                status (SCHEDULED/OPEN/RUNNING/QUIZ/ENDED),
                slides_url, supplementary_url,
                auto_created BOOLEAN           -- TRUE if walk-in (no pre-schedule)

beacon_events   id (SERIAL PK), user_id, student_id, session_id,
                status, dm, ts                 -- every beacon hit stored

overrides       student_id + session_id (PK), status, reason, ts

attendance      VIEW — first beacon hit per (student_id, session_id)
                       this is the official attendance status

beacon_log      VIEW — all beacon hits with entry_number per student per session
                       use for full audit trail and re-entry reports
```

**Effective status read order:** `overrides` → `attendance` view.
`get_student_session_status()` in `core/database.py` handles this.

All queries use `%s` placeholders (psycopg3). Never use `?` (that's sqlite3).

---

## Session Lifecycle

### Pre-scheduled (normal flow)

1. Lecturer calls `POST /api/v1/sessions/` with `start_time`, `end_time`, `label`, optional URLs
2. Session is created with `status = SCHEDULED`
3. Lecturer presses Blue button → `cls:open` beacon fires → handler calls `find_active_session()` → transitions to `OPEN`
4. Yellow → `RUNNING`, Yellow again → `QUIZ`, Red → `ENDED`

### Walk-in (fallback)

If no session with `start_time <= NOW() <= end_time AND status != ENDED` exists when Blue is pressed:
- `create_walkin_session()` auto-creates a 3-hour session with `auto_created = TRUE`, label `"Walk-in — DD Mon YYYY HH:MM"`
- Students see `ℹ️ No session was scheduled — a walk-in session was created automatically.` appended to their reply
- Lecturer can retroactively set materials via `PATCH /api/v1/sessions/{id}/`
- `GET /api/v1/sessions/` shows `"auto_created": true` as a clear signal

---

## Session State Machine (v1)

```
IDLE ──[Blue btn]──► OPEN ──[Yellow btn]──► RUNNING ──[Yellow btn]──► QUIZ
                                                │                         │
                                           [Red btn]                 [Red btn]
                                                └──────────┬──────────────┘
                                                           ▼
                                                         ENDED → IDLE
```

`dm` payload in BLE beacon (no session ID — resolved server-side by time window):

| State | `dm` value | Student receives |
|---|---|---|
| OPEN | `cls:open` | ✅ Present + materials (if set) |
| RUNNING | `cls:run` | ⏰ Late + materials (if set) |
| QUIZ | `cls:qz` | 📝 Quiz link + materials (if set) |
| ENDED | `cls:end` | Own status only (5 s hold, then `cls:idle`) |
| IDLE | `cls:idle` | *(ignored)* |

---

## BLE Re-Entry Behaviour — Important

LINE fires `beacon enter` **once per session** — when the phone first detects the beacon.

**Student implications:**
- If already in range when lecturer presses Blue → won't auto-receive ✅ Present
- Must walk out (~5–10 m) and back, **or** toggle Bluetooth off then on
- The reply message includes this tip automatically

**Re-entry is stored, not silently dropped:**
- Every `enter` event (including bathroom trip → return) is inserted into `beacon_events`
- The `attendance` VIEW takes the **first** event timestamp → official status
- The `beacon_log` VIEW shows **all** events with `entry_number` (1 = first, 2 = return, …)
- Use `GET /api/v1/sessions/{id}/log` to inspect re-entries for any student

**Example — student leaves and returns:**
```
entry_number=1  ts=09:05  status=PRESENT  dm=cls:open   ← official
entry_number=2  ts=09:47  status=LATE     dm=cls:run    ← re-entry during RUNNING state
```
The official status stays PRESENT; the second row is in the audit log only.

---

## LINE Simple Beacon Packet Format

```
02 01 06                    AD flags
03 03 6F FE                 Complete UUID list: 0xFE6F (LINE Corp)
XX 16 6F FE                 Service data header
   02                       Sub-type: LINE Simple Beacon
   01 8F 62 BD 52           HWID bytes (018f62bd52)
   7F                       TX power
   [≤13 bytes dm]           Device message — session payload
```

Advertising interval: 100 ms (160 × 0.625 ms units).

LINE sends the `dm` field **hex-encoded** in webhook events.
`handlers.py` decodes it: `binascii.unhexlify(dm_hex).decode("utf-8")`.

---

## Beacon Handler Flow

```
LINE webhook POST /webhook/v1/
    │
    ├── verify X-Line-Signature (core/line_client.py)
    ├── for each event → v1/handlers.py dispatch()
    │       ├── type == "beacon"  → _handle_beacon()
    │       └── type == "message" → _handle_message()
    │
    └── return {"status": "ok"}
```

`_handle_beacon` in `v1/handlers.py`:
1. Ignore if `beacon_type != "enter"`
2. Decode hex `dm` field → plain text (e.g. `"cls:open"`)
3. Ignore `cls:idle` and unknown prefixes
4. Look up student by `user_id` → prompt registration if unknown
5. Call `find_active_session()` to resolve session by time window
6. `cls:open` + no session → auto-create walk-in session
7. Log beacon event + reply to that student only

---

## PII Rules — Never Violate These

- Each student's LINE reply contains **only their own** name / status.
- `cls:end` handler replies the triggering student's own status — never a list.
- No student ID list is ever sent via LINE chat.
- `user_id` (LINE internal) is never returned in any API response.
- `/api/` export CSV contains `student_id` + `status` + `ts` only — no names.
- Lecturer sees aggregate counts in session list; individual records only via `/api/`.

---

## Adding a New Version (e.g. v2)

1. Create `line/src/v2/` with `__init__.py`, `webhook.py`, `handlers.py`, `api.py`
2. Import from `..core.*` — do not duplicate core code
3. Register a new LINE OA channel with its own `LINE_V2_CHANNEL_*` env vars
4. Add a `core/line_client_v2.py` (or parameterise `line_client.py`) for the new secrets
5. Mount the new routers in `main.py`
6. Issue a second HWID from LINE Manager for the new beacon device
7. Document in `docs/BusinessCase02.md` + `docs/SystemCase02.md`

See `docs/SystemCase01.md` for the v2 (lab session) design that is already spec'd.

---

## ESP32 Conventions

- `esp32/src/button_led.ino` — original prototype, **do not modify**
- Each business case gets its own subfolder: `esp32/src/caseNN/caseNN.ino`
- `case01.ino` uses `BLEDevice` / `BLEAdvertising` from the ESP32 Arduino BLE library
- `dm` strings carry **no session ID** — backend resolves session by time window
- Prints state to Serial at 115200 baud on every transition
- Button GPIO: Blue=26, Yellow=14, Red=13 (all `INPUT_PULLUP`, active LOW)
- LED GPIO: Blue=32, Yellow=33, Red=25

---

## Python Conventions

- Package manager: `uv` — never `pip` directly inside this project
- The venv (`line/.venv`) uses **Python 3.14** — use `uv run python` not `uv run python3.12`
- Run server: `uv run uvicorn src.main:app --reload --port 8000`
- Run a script: `uv run python scripts/check_env.py`

---

## Pre-Commit / Secrets

`detect-secrets` is wired as a pre-commit hook. If you add a file that looks like
it contains credentials, the commit will be blocked. Run:

```bash
make baseline-generate   # after adding intentionally non-secret files
make precommit-run       # manually run all hooks
```

Never commit `.env`. It is in `.gitignore`.
