# System Case 01 — API & Endpoint Design
### Smart Classroom Attendance via LINE Beacon

---

## Versioned Webhook Strategy

Each business case maps to its own webhook endpoint so LINE OA channels, beacon payloads,
and filtering rules stay isolated. Both share the same FastAPI app and SQLite DB.

| Endpoint | Business Case | Variant |
|---|---|---|
| `POST /webhook/v1/` | BusinessCase01 | Full session — PRESENT / LATE / QUIZ / ABSENT |
| `POST /webhook/v2/` | BusinessCase02 | Section-filtered — PRESENT / ABSENT, no quiz, lab prefix |

---

## Full Route Map

```
FastAPI app  (http://localhost:8000)
│
├── POST /webhook/v1/                           ← LINE OA v1 calls this
├── POST /webhook/v2/                           ← LINE OA v2 calls this
│
├── GET  /docs                                  ← Swagger UI (lecturer admin)
├── GET  /redoc                                 ← ReDoc alternative
│
├── /api/v1/
│   ├── sessions/
│   │   ├── GET    /                            list sessions + aggregate counts
│   │   ├── GET    /{session_id}/               single session detail
│   │   ├── GET    /{session_id}/attendance     all records for session (lecturer only)
│   │   ├── PATCH  /{session_id}/attendance     manual status override
│   │   └── GET    /{session_id}/export         download CSV
│   └── students/
│       ├── GET    /                            list registered students (no PII — count + id only)
│       └── DELETE /{student_id}/              unregister a student
│
└── /api/v2/
    └── sessions/
        ├── GET    /                            list lab sessions
        ├── GET    /{session_id}/attendance     lab attendance records
        └── GET    /{session_id}/export         CSV export
```

---

## Webhook Endpoints

### POST /webhook/v1/

LINE delivers events here for the v1 OA channel. Signature verified via `X-Line-Signature`.

**Beacon events → session state → student reply**

| `dm` prefix | Session state | Student LINE reply |
|---|---|---|
| `cls:open:NNN` | OPEN | "✅ Present! [own name] — Slides: [link]" |
| `cls:run:NNN` | RUNNING | "⏰ Late noted. [own name] — Slides: [link]" |
| `cls:qz:NNN` | QUIZ | "📝 Quiz is live! [LIFF link seeded with userId]" |
| `cls:end:NNN` | ENDED | "Class ended. Your status: [own status only]" |
| `cls:idle` | IDLE | *(ignored)* |

**Message events**

| Text | Reply |
|---|---|
| Greeting (`hello`, `สวัสดี`, …) | "สวัสดีครับ [name]! ✅" or registration prompt |
| 10-digit student ID | "Registered! 🎓 [student_id]" |
| Anything else | "Please send your 10-digit student ID." |

---

### POST /webhook/v2/

Same hardware, different OA channel + different `dm` prefix. Filters by section.

**Differences from v1:**

| | v1 | v2 |
|---|---|---|
| `dm` prefix | `cls:` | `lab:` |
| States | OPEN → RUNNING → QUIZ → ENDED | OPEN → ENDED only |
| LATE window | Yes | No |
| Quiz push | Yes | No |
| Section filter | All registered students | Only students in `LAB_SECTION` env var |
| Env credentials | `LINE_CHANNEL_*` | `LINE_V2_CHANNEL_*` |

**Beacon events → lab state**

| `dm` prefix | Action | Student LINE reply |
|---|---|---|
| `lab:open:NNN` | Log PRESENT (section-filtered) | "✅ Lab check-in confirmed. [own name]" |
| `lab:end:NNN` | Mark section absentees | "Lab ended. Your status: [own status only]" |
| anything else | Ignore | — |

---

## Lecturer Admin Endpoints

All `/api/` routes require `Authorization: Bearer <LECTURER_TOKEN>`.  
Visible and testable in Swagger UI at `/docs`.

---

### Sessions — List

```
GET /api/v1/sessions/
```

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `date` | `YYYY-MM-DD` | — | Filter by date |
| `status_summary` | bool | `true` | Include present/late/absent counts |
| `limit` | int | 20 | Max results |
| `offset` | int | 0 | Pagination offset |

**Example:**
```
GET /api/v1/sessions/?date=2026-04-20&limit=10
```

**Response:**
```json
[
  {
    "session_id": "001",
    "version": "v1",
    "opened_at": "2026-04-20T09:00:00",
    "ended_at":  "2026-04-20T11:00:00",
    "present": 28,
    "late": 4,
    "absent": 2,
    "total_registered": 34
  }
]
```

---

### Sessions — Single Detail

```
GET /api/v1/sessions/{session_id}/
```

**Response:**
```json
{
  "session_id": "001",
  "version": "v1",
  "opened_at": "2026-04-20T09:00:00",
  "ended_at": "2026-04-20T11:00:00",
  "present": 28,
  "late": 4,
  "absent": 2,
  "total_registered": 34
}
```

---

### Attendance — View Records

```
GET /api/v1/sessions/{session_id}/attendance
```

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `PRESENT\|LATE\|ABSENT\|QUIZ` | — | Filter by status |
| `order` | `asc\|desc` | `asc` | Sort by timestamp |
| `limit` | int | 100 | Max records |
| `offset` | int | 0 | Pagination |

**Example:**
```
GET /api/v1/sessions/001/attendance?status=ABSENT
GET /api/v1/sessions/001/attendance?status=LATE&order=desc
```

**Response:**
```json
[
  { "student_id": "6501234567", "status": "PRESENT", "ts": "2026-04-20T09:03:12" },
  { "student_id": "6509876543", "status": "LATE",    "ts": "2026-04-20T09:18:44" },
  { "student_id": "6501111111", "status": "ABSENT",  "ts": "2026-04-20T11:00:00" }
]
```

> Student names are not returned — `student_id` only. Protects PII at API layer.

---

### Attendance — Manual Override

```
PATCH /api/v1/sessions/{session_id}/attendance
```

Use when a student's beacon was missed (door obstruction, phone in bag).

**Request body:**
```json
{
  "student_id": "6501234567",
  "status": "PRESENT",
  "reason": "beacon missed at classroom door"
}
```

**Validation:**
- `status` must be one of `PRESENT | LATE | ABSENT`
- `student_id` must exist in `students` table
- `reason` is required (audit trail)

**Response:**
```json
{ "updated": true, "previous_status": "ABSENT", "new_status": "PRESENT" }
```

---

### Attendance — Export CSV

```
GET /api/v1/sessions/{session_id}/export
```

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `PRESENT\|LATE\|ABSENT` | all | Filter exported rows |
| `format` | `csv\|json` | `csv` | Output format |

**Example:**
```
GET /api/v1/sessions/001/export?status=ABSENT&format=csv
```

**CSV output** (`session_001_20260420.csv`):
```
student_id,status,timestamp
6501234567,PRESENT,2026-04-20T09:03:12
6509876543,LATE,2026-04-20T09:18:44
6501111111,ABSENT,2026-04-20T11:00:00
```

> No names exported. `student_id` is the identifier per institution policy.

---

### Students — List Registered

```
GET /api/v1/students/
```

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Max results |
| `offset` | int | 0 | Pagination |

**Response:**
```json
{
  "total": 34,
  "students": [
    { "student_id": "6501234567", "registered_at": "2026-03-01T10:00:00" },
    { "student_id": "6509876543", "registered_at": "2026-03-01T10:05:00" }
  ]
}
```

> `user_id` (LINE internal ID) is never returned — it stays server-side only.

---

### Students — Unregister

```
DELETE /api/v1/students/{student_id}
```

Removes the `userId → studentId` mapping. Student must re-register next class.

**Response:** `{ "deleted": true }`

---

## HTTP Status Codes Used

| Code | Meaning |
|---|---|
| `200 OK` | Success |
| `400 Bad Request` | Invalid signature (webhook) or bad request body |
| `401 Unauthorized` | Missing or invalid `Authorization` header |
| `404 Not Found` | Session or student not found |
| `422 Unprocessable Entity` | FastAPI validation error (wrong field type/value) |

---

## PII Rules Enforced at API Layer

| Rule | Where enforced |
|---|---|
| Students only receive own status | LINE `replyToken` — individual push, never broadcast |
| No student list in LINE chat | `cls:end` handler replies own status only |
| `user_id` never exposed in API | All `/api/` responses omit `user_id` |
| Student names not in API responses | `student_id` only — name join requires separate institution DB |
| Lecturer token required for all `/api/` | `Authorization: Bearer` middleware |
| Override requires reason | Audit trail in `beacon_events` table |

---

## Environment Variables

```env
# v1 LINE channel
LINE_CHANNEL_ID=2009838380
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...

# v2 LINE channel (lab)
LINE_V2_CHANNEL_ID=...
LINE_V2_CHANNEL_SECRET=...
LINE_V2_CHANNEL_ACCESS_TOKEN=...

# Admin
LECTURER_TOKEN=...           # Bearer token — set a strong random string
LAB_SECTION=A                # v2 section filter

# Webhook (fill after ngrok / deploy)
LINE_WEBHOOK_URL=
LINE_V2_WEBHOOK_URL=
```
