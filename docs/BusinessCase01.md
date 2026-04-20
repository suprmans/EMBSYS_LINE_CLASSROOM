# Business Case 01 — Button & LED Interaction Design
### Smart Classroom Attendance via LINE Beacon

---

## Overview

The lecturer controls the entire class session with **3 buttons**. Each button press transitions
the session state, changes the matching LED, and updates the BLE beacon payload — which changes
what LINE delivers to every student's phone automatically.

Students never open a link or scan a QR code. Their phone's LINE app detects the beacon
passively and the backend replies directly to their LINE chat.

---

## Why Students Cannot Share or Cheat

| Mechanism | How it prevents sharing |
|---|---|
| **LINE `userId`** | Bound to the LINE account on the physical device — one phone, one identity |
| **Beacon proximity** | Student must be within ~10 m of the ESP32 to trigger a webhook |
| **Session `dm` tag** | Each class has a unique session ID in the beacon payload — replaying an old detection does nothing |
| **Server-side dedup** | If the same `userId` is detected twice in one session, only the first is counted |
| **No shareable link** | There is no URL to forward — the backend pushes to the LINE account directly via Reply API |

---

## Session State Machine

```
  [Power on]
      │
      ▼
  ● IDLE  ──── Blue Button ────►  ● OPEN      (attendance window)
                                       │
                                  Yellow Button
                                       │
                                       ▼
                                  ● RUNNING   (late window / class in progress)
                                       │
                                  Yellow Button (again)  ──►  ● QUIZ
                                       │                           │
                                  Red Button               Red Button
                                       │                           │
                                       ▼                           ▼
                                  ● ENDED  ◄─────────────────────┘
```

---

## Button & LED Reference

### Blue — Start Class / Open Attendance

| | Detail |
|---|---|
| **Button** | GPIO 26 |
| **LED** | GPIO 32 — solid ON |
| **Action** | IDLE → OPEN |
| **Beacon `dm`** | `cls:open:NNN` |
| **What students receive** | "✅ Present! [Name] — Slides: [link]" pushed to their LINE chat |
| **Anti-cheat** | `userId` logged once per session; duplicates ignored |
| **LED off when** | Yellow button pressed (session moves to RUNNING) |

**Scenario:**
> Lecturer walks in, presses Blue. Blue LED lights up.
> Every student whose phone enters the room within the window gets attendance marked PRESENT
> and receives the lecture slides — no action needed from them.

---

### Yellow — Close Attendance / Start Quiz

Yellow button has **two roles** depending on current state:

#### Role 1 — Close attendance window (OPEN → RUNNING)

| | Detail |
|---|---|
| **Button** | GPIO 14 |
| **LED** | GPIO 33 — slow blink (1 Hz) |
| **Action** | OPEN → RUNNING |
| **Beacon `dm`** | `cls:run:NNN` |
| **What students receive** | "⏰ Late noted. [Name] — Slides: [link]" (late arrivals still get slides) |
| **Use case** | Press ~15 min after class starts to close on-time window; latecomers still detected but marked LATE |

#### Role 2 — Launch Quiz (RUNNING → QUIZ)

| | Detail |
|---|---|
| **Button** | GPIO 14 (press again) |
| **LED** | GPIO 33 — fast blink (5 Hz) |
| **Action** | RUNNING → QUIZ |
| **Beacon `dm`** | `cls:qz:NNN` |
| **What students receive** | "📝 Quiz is live! [unique LIFF link]" — each student gets it pushed to their own chat |
| **Anti-cheat** | LIFF link is pre-seeded with the student's registered `userId`; opening it on a different phone fails auth |
| **Use case** | Press mid-class to instantly push quiz link to every present student simultaneously |

---

### Red — End Class

| | Detail |
|---|---|
| **Button** | GPIO 13 |
| **LED** | GPIO 25 — 3× fast flash then OFF |
| **Action** | Any state → ENDED |
| **Beacon `dm`** | `cls:end:NNN` |
| **What each student receives** | Only their own result: "Class has ended. Your status: PRESENT / LATE / ABSENT" |
| **What the lecturer sees** | Aggregate counts only (Present / Late / Absent) — exported from DB, not sent via LINE chat |
| **PII rule** | No student ever sees another student's name, ID, or status — each reply goes to that person's own chat only |
| **All LEDs** | All off after flash — system returns to IDLE |

**Scenario:**
> Lecturer presses Red. Red LED flashes 3×, all dark.
> Student A's LINE chat: "Class has ended. Your status: PRESENT"
> Student B's LINE chat: "Class has ended. Your status: LATE"
> Absent students receive nothing (no `replyToken` — they were never detected)
> Lecturer checks attendance counts via the admin export, not LINE chat.

---

## Full Session Timeline

```
Time        Lecturer action         LED state              Students receive
────────────────────────────────────────────────────────────────────────────
T+0:00   Press BLUE               Blue solid             (nothing yet)
T+0:01   Students walk in         Blue solid             ✅ "Present! Nattapol"
T+0:15   Press YELLOW (#1)        Yellow slow blink      (nothing)
T+0:20   Late student walks in    Yellow slow blink      ⏰ "Late noted. Somsak"
T+0:45   Press YELLOW (#2)        Yellow fast blink      📝 "Quiz live! [link]"
T+1:00   Press RED                Red 3× flash → off     Each student gets own status only
```

---

## LED Quick Reference

| LED | Color | IDLE | OPEN | RUNNING | QUIZ | ENDED |
|---|---|---|---|---|---|---|
| GPIO 32 | Blue | off | **solid** | off | off | off |
| GPIO 33 | Yellow | off | off | **slow blink** | **fast blink** | off |
| GPIO 25 | Red | off | off | off | off | **3× flash → off** |

---

## Backend Trigger Summary

| `dm` prefix | Backend action |
|---|---|
| `cls:open:NNN` | Log PRESENT, reply slides link |
| `cls:run:NNN` | Log LATE, reply slides link |
| `cls:qz:NNN` | Reply LIFF quiz link (pre-seeded with `userId`) |
| `cls:end:NNN` | Mark remaining as ABSENT, push summary to lecturer |
| `cls:idle` | Ignore — no action |
