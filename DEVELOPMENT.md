# Development

## One-Time Setup

Bootstrap the project — installs git hooks and syncs LINE service dependencies:

```bash
make setup
```

This runs two steps in order:
1. Installs `pre-commit` + `detect-secrets` tools and enables the git hook
2. Runs `uv sync` inside `line/` and prints all installed FastAPI service packages

Expected output (truncated):
```
→ Syncing LINE service dependencies (line/)...
Resolved 18 packages in ...
Installed packages:
 Package             Version
 ------------------- -------
 anyio               4.x.x
 fastapi             0.115.x
 httpx               0.27.x
 psycopg             3.1.x
 python-dotenv       1.0.x
 uvicorn             0.30.x
 ...
Bootstrap complete.
Next → run 'make check-env' to validate LINE credentials before starting the server.
```

To install only the hooks (without syncing deps):

```bash
make precommit-install
```

---

## Environment Secret Check

Run this **before starting the server** to verify required credentials exist and are not placeholders:

```bash
make check-env
```

Copy the template and fill in real values:

```bash
cp .env.example .env
# edit .env — see variable reference below
```

### Environment variable reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL DSN — `postgresql://user:pass@host:5432/db` | <!-- pragma: allowlist secret -->
| `LINE_CHANNEL_ID` | ✅ | From LINE Developers Console |
| `LINE_CHANNEL_SECRET` | ✅ | Used to verify webhook signatures |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | Long-lived token for Reply API |
| `LINE_BEACON_HWID` | ✅ | 10-char hex issued from LINE Manager Beacon page |
| `LINE_WEBHOOK_URL` | reference | Set this URL in LINE Developers Console |
| `LECTURER_TOKEN` | ✅ | Bearer token for all `/api/` admin routes |

---

## LINE Beacon Setup

> Official docs: https://developers.line.biz/en/docs/messaging-api/using-beacons/#getting-beacon

### Step 1 — Link beacon with your bot account

1. Go to **LINE Manager → [Beacon](https://manager.line.biz/beacon/register)**
2. Click **Link beacons with bot account**
3. Select your OA (e.g. **scool.BEACON**) and click **Select**

### Step 2 — Issue a hardware ID

1. Click **Issue LINE Simple Beacon hardware IDs**
2. Select your OA → click **Issue hardware ID**
3. Copy the 10-character hex HWID shown in the table (e.g. `018f62bd52`)
4. You can issue up to **10 hardware IDs** per account

> Current issued HWID: `018f62bd52`

### Step 3 — Add HWID to firmware and env

In `.env`:
```
LINE_BEACON_HWID=018f62bd52
```

In `esp32/src/case01/case01.ino`, verify the bytes match:
```cpp
// 018f62bd52 → 0x01, 0x8F, 0x62, 0xBD, 0x52
static const uint8_t LINE_HWID[5] = { 0x01, 0x8F, 0x62, 0xBD, 0x52 };
```

### Step 4 — Set webhook URL in LINE Developers Console

1. Start backend + ngrok:
```bash
cd line && uv run uvicorn src.main:app --reload --port 8000
ngrok http 8000
```
2. In [LINE Developers Console](https://developers.line.me/console/) → your channel → **Messaging API**
3. Set **Webhook URL** to:
```
https://<your-ngrok-id>.ngrok-free.app/webhook/v1/
```
4. Toggle **Use webhook** ON → click **Verify** → expect `200 OK`

### LINE Simple Beacon packet format (reference)

```
AD flags:          02 01 06
UUID list:         03 03 6F FE          (service UUID 0xFE6F — LINE Corp)
Service data:      XX 16 6F FE
                      02               sub-type: LINE Simple Beacon
                      [5 bytes HWID]
                      7F               TX power
                      [≤13 bytes dm]   device message (session payload)
```

---

## Database — PostgreSQL

The backend uses **PostgreSQL 17**. The schema is created automatically on first server start.

### Create database & user (one-time)

```bash
psql postgres -c "CREATE USER scool_beacon WITH PASSWORD 'your_password';"  # pragma: allowlist secret
psql postgres -c "CREATE DATABASE scool_beacon OWNER scool_beacon;"
```

### Initialize schema manually

```bash
cd line
uv run python -c "
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('..') / '.env')
from src.core.database import init_db
init_db()
print('DB initialized.')
"
```

### Schema overview

```
students        user_id (PK), student_id (UNIQUE), name, registered_at
sessions        session_id (PK), version, opened_at, ended_at
beacon_events   id (SERIAL), user_id, student_id, session_id, status, dm, ts
overrides       student_id + session_id (PK), status, reason, ts
attendance      VIEW — first beacon hit per (student_id, session_id)
```

### Inspect with psql

```bash
psql -U scool_beacon -d scool_beacon

-- inside psql:
\dt                                          -- list tables
\dv                                          -- list views
SELECT * FROM students;
SELECT * FROM attendance WHERE session_id = '001';
SELECT * FROM beacon_events ORDER BY ts DESC LIMIT 20;
\q
```

### Export attendance as CSV

```bash
psql -U scool_beacon -d scool_beacon \
  -c "\COPY (SELECT student_id, status, ts FROM attendance WHERE session_id = '001') TO 'session_001.csv' CSV HEADER"
```

Or use the API:
```bash
curl -H "Authorization: Bearer <LECTURER_TOKEN>" \
  "http://localhost:8000/api/v1/sessions/001/export?format=csv" \
  -o session_001.csv
```

---

## Running the Server

```bash
cd line
uv run uvicorn src.main:app --reload --port 8000
```

Swagger UI (lecturer admin): `http://localhost:8000/docs`
Click 🔒 **Authorize** → paste `LECTURER_TOKEN`.

Suppress info logs:
```bash
uv run uvicorn src.main:app --reload --port 8000 --log-level warning
```

---

## Pre-Commit Workflow

Run all hooks manually against every file:

```bash
make precommit-run
```

Update pinned hook versions:

```bash
make precommit-update
```

Regenerate secrets baseline (after adding new files):

```bash
make baseline-generate
```

Audit baseline entries interactively:

```bash
make baseline-audit
```
