# AGENTS.md — AI Agent Guide
### Smart Classroom Attendance via LINE Beacon

This file gives an AI agent everything needed to work on this project cold.
Read it fully before touching any code.

---

## What This Project Does

An ESP32 on a classroom desk broadcasts a BLE LINE Beacon. When a student's phone
enters range, LINE fires a webhook to the backend. The backend logs their attendance
and replies to their LINE chat — no app install, no QR code, no manual sign-in.

A lecturer controls the session with 3 physical buttons. Each button changes session
state and updates the beacon payload, which changes what every student receives.

---

## Repo Layout

```
.
├── AGENTS.md               ← you are here
├── DEVELOPMENT.md          ← setup, DB commands, pre-commit workflow
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
│           └── case01.ino          ← BusinessCase01 firmware (full state machine)
│
└── line/                   ← Python FastAPI backend
    ├── pyproject.toml
    ├── classroom.db        ← SQLite (auto-created, git-ignored)
    └── src/
        ├── main.py         ← app entry point, loads .env, wires routers
        ├── core/           ← shared across all API versions
        │   ├── auth.py         Bearer token dependency (require_lecturer)
        │   ├── database.py     All DB tables + every query function
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
| `LINE_CHANNEL_SECRET` | `core/line_client.py` | Signature verification |
| `LINE_CHANNEL_ACCESS_TOKEN` | `core/line_client.py` | Reply API auth |
| `LINE_CHANNEL_ID` | reference only | Not read in code yet |
| `LINE_WEBHOOK_URL` | reference only | Set in LINE Developers Console |
| `LECTURER_TOKEN` | `core/auth.py` | Bearer token for all `/api/` routes |

`load_dotenv` runs at the top of `main.py` **before** any relative imports — this is
intentional because `core/line_client.py` reads `os.environ` at module level.

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

---

## API Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/webhook/v1/` | LINE signature | LINE events (beacon + message) |
| `GET` | `/api/v1/sessions/` | Bearer | List sessions + counts |
| `GET` | `/api/v1/sessions/{id}/` | Bearer | Single session detail |
| `GET` | `/api/v1/sessions/{id}/attendance` | Bearer | Attendance records |
| `PATCH` | `/api/v1/sessions/{id}/attendance` | Bearer | Manual status override |
| `GET` | `/api/v1/sessions/{id}/export` | Bearer | CSV / JSON export |
| `GET` | `/api/v1/students/` | Bearer | List registered students |
| `DELETE` | `/api/v1/students/{id}` | Bearer | Unregister a student |

---

## Database Schema

```sql
students        user_id (PK), student_id (UNIQUE), name, registered_at
sessions        session_id (PK), version, opened_at, ended_at
beacon_events   id, user_id, student_id, session_id, status, dm, ts
overrides       student_id + session_id (PK), status, reason, ts
attendance      VIEW — first beacon hit per (student_id, session_id)
```

**Read order for effective status:** overrides → attendance view.
`get_student_session_status()` in `core/database.py` handles this.

`init_db()` is called on app startup via FastAPI `lifespan`. Safe to call multiple
times — all statements use `CREATE TABLE IF NOT EXISTS` / `CREATE VIEW IF NOT EXISTS`.

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

`dm` payload in BLE beacon:

| State | `dm` value | Student receives |
|---|---|---|
| OPEN | `cls:open:NNN` | ✅ Present + slides |
| RUNNING | `cls:run:NNN` | ⏰ Late + slides |
| QUIZ | `cls:qz:NNN` | 📝 Quiz LIFF link |
| ENDED | `cls:end:NNN` | Own status only |
| IDLE | `cls:idle` | *(ignored)* |

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
1. Ignore if not `beacon_type == "enter"`
2. Parse `session_id` from `dm` (3rd colon-segment)
3. Look up student by `user_id` → prompt registration if unknown
4. Match `dm` prefix → log event + reply to that student only

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
4. Add `LINE_V2_CHANNEL_SECRET` / `LINE_V2_CHANNEL_ACCESS_TOKEN` reading to a
   new `core/line_client_v2.py` (or parameterise `line_client.py`)
5. Mount the new routers in `main.py`
6. Document in a new `docs/BusinessCase02.md` + `docs/SystemCase02.md`

See `docs/SystemCase01.md` for the v2 (lab session) design that is already spec'd.

---

## ESP32 Conventions

- `esp32/src/button_led.ino` — original prototype, **do not modify**
- Each business case gets its own subfolder: `esp32/src/caseNN/caseNN.ino`
- `case01.ino` prints `dm` payloads to Serial at 115200 baud for BLE integration debugging
- Button GPIO: Blue=26, Yellow=14, Red=13 (all `INPUT_PULLUP`, active LOW)
- LED GPIO: Blue=32, Yellow=33, Red=25

---

## Python Conventions

- Always use `python3.12` / `uv run python3.12` — never bare `python`
- Package manager: `uv` — never `pip` directly inside this project
- Run server: `uv run uvicorn src.main:app --reload --port 8000`
- Run a script: `uv run python3.12 scripts/check_env.py`

---

## Pre-Commit / Secrets

`detect-secrets` is wired as a pre-commit hook. If you add a file that looks like
it contains credentials, the commit will be blocked. Run:

```bash
make baseline-generate   # after adding intentionally non-secret files
make precommit-run       # manually run all hooks
```

Never commit `.env`. It is in `.gitignore`.
