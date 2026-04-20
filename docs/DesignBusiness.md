# DesignBusiness — Template
### Business Case Document

> Copy this file and rename to `BusinessCaseNN.md`.  
> Fill every section. Delete guidance lines (starting with `>`).

---

## 1. One-Line Pitch

> One sentence. What does this do and for whom?

---

## 2. Problem → Solution

| Without this | With this |
|---|---|
| *(pain point)* | *(how it's solved)* |

---

## 3. Anti-Cheat / Trust Model

> How does the system prevent abuse, sharing, or spoofing?

| Mechanism | How it prevents abuse |
|---|---|
| | |

---

## 4. Session State Machine

> Draw the states and transitions. Use button labels, not GPIO numbers.

```
[Power on]
    │
    ▼
● STATE ──── [Trigger] ────► ● STATE
```

---

## 5. Button & LED Reference

> One section per button. State what changes on hardware and what the user receives.

### [Color] Button — [Action Name]

| Field | Detail |
|---|---|
| **Button GPIO** | |
| **LED GPIO** | |
| **LED pattern** | solid / slow blink / fast blink / N× flash |
| **Session transition** | STATE_A → STATE_B |
| **Beacon `dm`** | `prefix:state:NNN` |
| **Student receives** | *(own data only — no other student info)* |
| **PII rule** | Each reply goes to the individual student's chat only |

**Scenario:**
> *(Real-world walkthrough — 2–3 sentences)*

---

## 6. Session Timeline

```
Time     Lecturer action     LED state     Students receive
──────────────────────────────────────────────────────────
T+0:00
T+0:XX
```

---

## 7. LED Quick Reference

| LED | Color | STATE_A | STATE_B | STATE_C | ENDED |
|---|---|---|---|---|---|
| GPIO XX | | | | | |

---

## 8. Backend Trigger Summary

| `dm` prefix | Backend action | Student receives |
|---|---|---|
| `prefix:state:NNN` | | *(own status only)* |

---

## 9. PII Checklist

- [ ] Students only receive their own name/status
- [ ] No student list ever sent via LINE chat
- [ ] Absent students receive no message (no replyToken)
- [ ] Lecturer sees aggregate counts, not individual IDs in LINE
- [ ] Individual records accessible only via authenticated `/api/` export
