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

Run this **before starting the server** to verify required LINE credentials exist and are not placeholders:

```bash
make check-env
```

Check against a specific env file:

```bash
make check-env-file
# or
make check-env-file ENV_FILE=.env.local
```

Validate additional variables (optional):

```bash
uv run scripts/check_env.py --require APP_ENV --require WEBHOOK_BASE_URL
```

Copy the template and fill in real values:

```bash
cp .env.example .env
# edit .env with your LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN
```

---

## Database — SQLite3

The backend uses **SQLite3**, which ships with Python 3.12 stdlib — no installation required.

### DB file location

The database file is created automatically at `line/classroom.db` on first server start (or first `init_db()` call). It is git-ignored.

### Schema overview

```
beacon_events          ← raw layer: every beacon hit, append-only
attendance             ← clean VIEW: first-occurrence-wins per (student_id, session_id)
students               ← registration: userId → studentId mapping
```

### Initialize manually

```bash
cd line
uv run python3.12 -c "from src.database import init_db; init_db(); print('DB initialized.')"
```

### Example connection (interactive)

```python
import sqlite3

con = sqlite3.connect("line/classroom.db")
con.row_factory = sqlite3.Row

# list all registered students
rows = con.execute("SELECT * FROM students").fetchall()
for r in rows:
    print(dict(r))

# view deduplicated attendance for a session
rows = con.execute(
    "SELECT * FROM attendance WHERE session_id = ?", ("001",)
).fetchall()
for r in rows:
    print(dict(r))

# raw event log (includes duplicates + absentees)
rows = con.execute(
    "SELECT * FROM beacon_events ORDER BY ts DESC LIMIT 20"
).fetchall()
for r in rows:
    print(dict(r))

con.close()
```

### Inspect with the sqlite3 CLI

```bash
sqlite3 line/classroom.db

# inside the sqlite3 shell:
.tables
.schema beacon_events
SELECT * FROM attendance WHERE session_id = '001';
.quit
```

### Export attendance as CSV

```bash
sqlite3 -header -csv line/classroom.db \
  "SELECT * FROM attendance WHERE session_id = '001';" \
  > session_001.csv
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
