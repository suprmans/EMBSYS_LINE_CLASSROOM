# DesignSystem — Template
### System & API Design Document

> Copy this file and rename to `SystemCaseNN.md`.  
> Fill every section. Delete guidance lines (starting with `>`).

---

## 1. Webhook Strategy

> Which LINE OA channel maps to which endpoint? Why are they versioned separately?

| Endpoint | Business Case | Filter / Variant |
|---|---|---|
| `POST /webhook/vN/` | BusinessCaseNN | *(describe difference)* |

---

## 2. Full Route Map

```
FastAPI app
│
├── POST /webhook/vN/
│
├── GET  /docs                     ← Swagger UI
│
└── /api/vN/
    ├── sessions/
    │   ├── GET    /
    │   ├── GET    /{session_id}/
    │   ├── GET    /{session_id}/attendance
    │   ├── PATCH  /{session_id}/attendance
    │   └── GET    /{session_id}/export
    └── students/
        ├── GET    /
        └── DELETE /{student_id}/
```

---

## 3. Webhook Endpoint Detail

### POST /webhook/vN/

> Document every `dm` prefix this version handles.

| `dm` prefix | Session state | Student LINE reply |
|---|---|---|
| `prefix:state:NNN` | STATE | *(own data only)* |

> Document every message event this version handles.

| Text received | Action | Reply |
|---|---|---|
| | | |

---

## 4. Admin Endpoints

> For each endpoint: method + path, query params table, example request, example response.
> Auth: `Authorization: Bearer <LECTURER_TOKEN>` on all `/api/` routes.

### [METHOD] /api/vN/[resource]/

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| | | | |

**Example request:**
```
GET /api/vN/resource/?param=value
```

**Example response:**
```json
{}
```

> Notes on PII: what is and is not returned, and why.

---

## 5. HTTP Status Codes

| Code | When used |
|---|---|
| 200 | Success |
| 400 | Bad request / invalid LINE signature |
| 401 | Missing or invalid Bearer token |
| 404 | Resource not found |
| 422 | FastAPI validation error |

---

## 6. PII Rules Enforced at API Layer

> List every rule. Be explicit.

| Rule | Where enforced |
|---|---|
| Students only see own status | `replyToken` — individual, never broadcast |
| `user_id` never returned | All `/api/` responses omit LINE internal IDs |
| Lecturer token required | Bearer middleware on all `/api/` routes |
| Override requires reason | Stored in DB for audit trail |

---

## 7. Query Design Recommendations

> Tips for this specific system — copy these into the endpoint sections.

**Filtering:**
- Always support `status=PRESENT|LATE|ABSENT` filter on attendance endpoints
- Support `date=YYYY-MM-DD` on session list — one class per day is common
- Support `section=A|B` on v2+ endpoints for multi-group filtering

**Pagination:**
- Use `limit` + `offset` on all list endpoints
- Default `limit=20` for sessions, `limit=100` for attendance records
- Return `total` count alongside results so clients can calculate pages

**Ordering:**
- Default attendance to `order=asc` (chronological — who arrived first)
- Allow `order=desc` for "who was last" queries

**Export:**
- Support `format=csv|json` — CSV for spreadsheet import, JSON for dashboard
- Filename should encode session + date: `session_001_20260420.csv`
- Never include names in export unless institution policy explicitly permits

---

## 8. Environment Variables

```env
# LINE channel for this version
LINE_VN_CHANNEL_ID=
LINE_VN_CHANNEL_SECRET=
LINE_VN_CHANNEL_ACCESS_TOKEN=

# Admin
LECTURER_TOKEN=              # strong random string
LINE_VN_WEBHOOK_URL=         # fill after deploy / ngrok
```
