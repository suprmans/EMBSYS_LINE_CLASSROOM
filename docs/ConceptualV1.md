# Smart Classroom Attendance via LINE Beacon
### EMB/Real-Time Systems — Final Project Summary

---

## 1. Business Concept

### One-line pitch
> An ESP32 embedded device that uses ambient light sensing and BLE to automatically record student attendance and deliver course materials through LINE — zero app install, zero cost per message.

### Core value proposition

| Without this system | With this system |
|---|---|
| Manual sign-in sheet — forgeable | Hardware-enforced: must be physically in room |
| Staff marks attendance manually | Fully automatic — LDR gates the window |
| Students miss material if late | LINE delivers slides on entry regardless |
| Paper quiz distribution | Button press → quiz link to all present students |
| No attendance record export | SQLite log → exportable CSV per session |

### Cost model

| Item | Cost |
|---|---|
| LINE OA monthly fee | ฿0 (free tier sufficient) |
| Message cost per student per class | ฿0 (Reply API — not counted in quota) |
| Hardware BOM | ~฿800–1,200 total |
| Backend hosting | ฿0 (Render free tier / ngrok for demo) |

---

## 2. User Identification — LINE ID × Mobile Phone Mapping

The core identification mechanism is automatic. When a student who follows the course LINE OA enters BLE range, the LINE platform sends a webhook to the backend containing their `userId` — no action required from the student.

```
┌─────────────────────────────────────────────────────┐
│                  Student's Phone                    │
│                                                     │
│   LINE App ──follows──► Course OA                   │
│                                                     │
│   Walks into classroom (BLE range ~10m)             │
│          │                                          │
│          ▼                                          │
│   LINE platform detects beacon entry                │
│          │                                          │
│          ▼                                          │
│   Webhook fired to backend:                         │
│   {                                                 │
│     "type": "beacon",                               │
│     "replyToken": "nHuyWiB7...",   ◄── free reply  │
│     "source": {                                     │
│       "userId": "U4af4980629..."   ◄── identity     │
│     },                                              │
│     "beacon": {                                     │
│       "hwid": "your_hwid",                          │
│       "dm":   "cls:open:001"       ◄── session tag  │
│     }                                               │
│   }                                                 │
└─────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────┐
│                Backend Registry                     │
│                                                     │
│   userId: "U4af4980629..."                          │
│       └──► studentId:  "6501234567"                 │
│       └──► name:       "Nattapol S."                │
│       └──► course:     "EMB6201"                    │
│       └──► status:     PRESENT / LATE / ABSENT      │
└─────────────────────────────────────────────────────┘
```

### Registration flow (one-time, first class only)

```
Student follows OA
      │
      ▼
Bot: "Send your student ID to register."
      │
      ▼
Student sends: "6501234567"
      │
      ▼
Backend stores: userId → studentId mapping
      │
      ▼
All future classes: fully automatic
```

### Anti-cheat properties built into hardware

- `userId` is phone-bound — one LINE account per person, cannot be shared
- Student must be physically within ~10m BLE range
- LDR confirms room light is on — walking past a dark/locked room = not counted
- Session ID encoded in `dm` payload — each class has a unique tag, replay impossible

---

## 3. Hardware — Components and Duties

### Wiring overview (breadboard)

```
ESP32 DevKit
├── GPIO34 (ADC) ──┬── LDR
│                  └── 10kΩ resistor ── GND     (voltage divider)
│
├── GPIO26 ────────── Blue   Button ── GND      (INPUT_PULLUP, open session)
├── GPIO14 ────────── Yellow Button ── GND      (INPUT_PULLUP, quiz mode)
├── GPIO13 ────────── Red    Button ── GND      (INPUT_PULLUP, end session)
│
├── GPIO32 ── 220Ω ── LED Blue                  (system heartbeat / idle)
├── GPIO33 ── 220Ω ── LED Yellow                (session state)
├── GPIO25 ── 220Ω ── LED Red                   (quiz / alert)
│
└── BLE radio (internal) ── LINE Simple Beacon advertising
```

> **Implemented:** Buttons and LEDs are live in `button_led.ino` — 25 ms software debounce,
> toggle-on-press, boot-flash self-test. LDR and BLE are the next wiring step.

### Component duties

| Component | Pin(s) | Physical role | Embedded role | Course concept |
|---|---|---|---|---|
| **LDR** | GPIO34 | Detects classroom light on/off | Hardware Timer ISR → ADC read → circular buffer → moving average → state transition | Interrupt, ADC peripheral |
| **Blue Button** | GPIO26 | Lecturer: open attendance window | Polling debounce (25 ms) → toggle → `LecturerTask` sets OPEN | GPIO, debounce |
| **Yellow Button** | GPIO14 | Lecturer: start quiz | Polling debounce (25 ms) → toggle → `LecturerTask` sets QUIZ | GPIO, debounce |
| **Red Button** | GPIO13 | Lecturer: end session | Polling debounce (25 ms) → toggle → `LecturerTask` sets ENDED | GPIO, debounce |
| **LED Blue** | GPIO32 | System heartbeat / idle indicator | LEDC PWM 1 Hz fade — always on while powered | PWM peripheral |
| **LED Yellow** | GPIO33 | Session window status | GPIO driven by LEDTask — solid = OPEN, blink = RUNNING, off = IDLE | Digital output, RTOS task |
| **LED Red** | GPIO25 | Quiz / alert signal | Hardware Timer callback drives 5 Hz blink — no task blocking | Timer peripheral |
| **ESP32 BLE** | internal | Broadcasts session context | BeaconTask updates `dm` payload each cycle; `vTaskDelayUntil` 100 ms period | Real-time scheduling |

### LDR circuit detail

```
3.3V
 │
LDR  (resistance drops in bright light)
 │
 ├──── GPIO34 ADC input
 │
10kΩ
 │
GND
```

Bright room → LDR resistance low → ADC reads high voltage → `LIGHT_ON` event  
Dark room  → LDR resistance high → ADC reads low voltage → `LIGHT_OFF` event

---

## 4. Software Architecture

### FreeRTOS task map

```
Core 1                              Core 0
────────────────────────────────    ────────────────────────────────
SensorTask (priority 2)             BeaconTask (priority 1)
  - reads xQueue from HW Timer        - xSemaphoreTake(state_mutex)
  - computes moving average           - copies dm_buffer
  - runs state machine                - calls updateBeaconPayload()
  - xSemaphoreTake(state_mutex)       - vTaskDelayUntil(100ms)  ← RT
  - writes SessionState               - xSemaphoreGive(state_mutex)
  - xSemaphoreGive(state_mutex)
                                    LEDTask (priority 1)
LecturerTask (priority 3)  ← high    - reads SessionState
  - xEventGroupWaitBits               - drives LEDC channels
  - software debounce (300ms)         - delegates Red LED to HW timer
  - cycles mode: QUIZ / END / OPEN
  - xSemaphoreTake(state_mutex)
  - writes SessionState + dm_buffer
  - xSemaphoreGive(state_mutex)
```

### Session state machine

```
         LDR: light ON
IDLE ────────────────────► OPEN (attendance window, 15 min timer)
 ▲                              │
 │                              │ xTimer expires
 │                              ▼
 │   LDR: light OFF       RUNNING (late window, 30 min timer)
 └───────────────────────       │
                           button: QUIZ mode
                                 │
                                 ▼
                           QUIZ ──► ENDED (timer or button)
                                         │
                                         └─► mark absentees
                                             push summary to lecturer
```

### dm payload encoding (13 bytes max)

| State | dm value | Backend action | LED state |
|---|---|---|---|
| IDLE | `"cls:idle"` | Ignore detections | Green heartbeat only |
| OPEN | `"cls:open:001"` | Log PRESENT, reply with slides | Yellow solid on |
| RUNNING | `"cls:run:001"` | Log LATE, reply with slides | Yellow slow blink |
| QUIZ | `"cls:qz:001"` | Reply LIFF quiz link to all present | Red 5Hz blink |
| ENDED | `"cls:end:001"` | Mark absentees, send summary | All LEDs off |

### Key code patterns

**Hardware Timer ISR → queue (50Hz ADC sampling)**
```cpp
// Timer ISR — runs every 20ms on hardware timer
void IRAM_ATTR onTimer() {
    int raw = analogRead(LDR_PIN);
    xQueueSendFromISR(adc_queue, &raw, NULL);
}
```

**3-Button polling debounce (implemented in `button_led.ino`)**
```cpp
// Per-button state: lastRaw[], lastStable[], lastChange[], ledState[]
for (int i = 0; i < 3; i++) {
    bool raw = digitalRead(btnPins[i]);          // btnPins = {26,14,13}
    if (raw != lastRaw[i]) { lastRaw[i] = raw; lastChange[i] = millis(); }
    if ((millis() - lastChange[i]) >= 25 && raw != lastStable[i]) {
        lastStable[i] = raw;
        if (raw == LOW) {                        // confirmed press
            ledState[i] = !ledState[i];
            digitalWrite(ledPins[i], ledState[i]);  // ledPins = {32,33,25}
        }
    }
}
```

**Button EventGroup path (FreeRTOS layer — planned)**
```cpp
void IRAM_ATTR buttonISR() {
    BaseType_t woken = pdFALSE;
    xEventGroupSetBitsFromISR(event_group, BIT_BUTTON, &woken);
    portYIELD_FROM_ISR(woken);
}
```

**Semaphore-guarded state write**
```cpp
if (xSemaphoreTake(state_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    session_state = new_state;
    snprintf(dm_buffer, 14, "cls:%s:%03d", state_str, session_id);
    xSemaphoreGive(state_mutex);
}
```

**Real-time beacon period (BeaconTask)**
```cpp
TickType_t last_wake = xTaskGetTickCount();
for (;;) {
    // guaranteed 100ms period regardless of payload update time
    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(100));
    updateBeaconPayload(dm_buffer);
}
```

**Debounce in task context (not ISR)**
```cpp
TickType_t now = xTaskGetTickCount();
if ((now - last_press) < pdMS_TO_TICKS(300)) continue; // ignore bounce
last_press = now;
```

### Backend (Python Flask — ~80 lines)

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    events = request.json["events"]
    for event in events:
        if event["type"] == "beacon":
            user_id    = event["source"]["userId"]
            reply_tkn  = event["replyToken"]
            dm         = event["beacon"].get("dm", "")
            handle_beacon(user_id, reply_tkn, dm)   # free reply
        elif event["type"] == "message":
            handle_registration(event)              # student ID input
    return "OK", 200

def handle_beacon(user_id, reply_token, dm):
    student = db.get(user_id)
    if not student:
        reply(reply_token, "Please register: send your student ID.")
        return
    if dm.startswith("cls:open"):
        db.log_attendance(student.id, "PRESENT")
        reply(reply_token, f"Present! {student.name}. Slides: bit.ly/emb-w12")
    elif dm.startswith("cls:run"):
        db.log_attendance(student.id, "LATE")
        reply(reply_token, f"Late noted. {student.name}. Slides: bit.ly/emb-w12")
    elif dm.startswith("cls:qz"):
        reply(reply_token, "Quiz live! liff.line.me/quiz-emb")
```

---

## 5. Mapping to Class Knowledge Topics

### January — Embedded Processors & Interrupt Programming

| Topic taught | Where it appears in this project |
|---|---|
| IOT board + interrupt programming | ESP32 is the IoT board; two hardware interrupt sources |
| Counting events with interrupts | HW Timer ISR fires 50 samples/sec, counted in circular buffer |
| Programming with interrupt | `IRAM_ATTR` ISR functions for both Timer and GPIO |
| Embedded systems design | Full system design: sensor → MCU → cloud → user |

**Specific mapping:**  
The LDR is sampled by a hardware timer interrupt at 50Hz — exactly the "counting events" pattern from January's stopwatch demo, repurposed for ADC event counting. Three lecturer buttons (GPIO 26/14/13) use software-debounced GPIO reads (25 ms window), directly applying the January interrupt and input-debounce exercises at hardware scale.

---

### February — Operating Systems, Task Scheduling, Semaphores

| Topic taught | Where it appears in this project |
|---|---|
| Multitask-OS (MOS) | 4 FreeRTOS tasks running concurrently on 2 cores |
| Semaphores | `SemaphoreHandle_t state_mutex` — classic mutual exclusion |
| Reader-writer problem | LEDTask + BeaconTask (readers) vs SensorTask + LecturerTask (writers) |
| Cooperative processes | BeaconTask yields voluntarily via `vTaskDelayUntil` |
| Implementing semaphores | `xSemaphoreTake` / `xSemaphoreGive` wrapping every shared state access |

**Specific mapping:**  
The `state_mutex` protecting `SessionState` and `dm_buffer` is a direct implementation of the reader-writer semaphore pattern from `mos-rz2.txt`. Two reader tasks (LED, Beacon) and two writer tasks (Sensor, Lecturer) — matching the lecture's producer-consumer structure exactly.

---

### March — RTOS, Real-Time Scheduling, Embedded Communication

| Topic taught | Where it appears in this project |
|---|---|
| Real-time systems / RTOS | `vTaskDelayUntil` in BeaconTask enforces hard 100ms deadline |
| Real-time scheduling | Task priorities: LecturerTask (3) > SensorTask (2) > LED/Beacon (1) |
| Preemptive scheduling | Button ISR preempts SensorTask immediately via EventGroup |
| Embedded systems communication | BLE advertising = wireless embedded communication protocol |
| Actual hardware Arduino/ESP32 | ESP32 on breadboard with real sensors, wired and flashed |

**Specific mapping:**  
The `vTaskDelayUntil(100ms)` in BeaconTask is a textbook hard real-time deadline — if BLE advertising doesn't update within 100ms, the period is violated. This is the definition of a real-time constraint from the March RTOS lectures. The lecturer button at priority 3 preempts everything — demonstrating preemptive scheduling where a higher-priority task immediately takes CPU from lower ones.

---

### April — Memory, Peripherals, IoT, I2C

| Topic taught | Where it appears in this project |
|---|---|
| Counter / Timer peripheral | Hardware Timer for 50Hz LDR sampling + Red LED 5Hz blink |
| PWM peripheral | LEDC (ESP32 PWM) for Green LED heartbeat fade |
| LED display | 3-LED status panel showing system state visually |
| UART | Serial debug output: session state + detected userId printed |
| ADC | `analogRead(LDR_PIN)` — LDR voltage divider into 12-bit ADC |
| Internet of Things: Everything as a service | LINE Messaging API = cloud service; ESP32 = IoT edge device |
| I2C bus | Optional extension: BMP280 temperature sensor to detect room occupancy from heat signature |

**Specific mapping:**  
The April peripherals checklist — Timer, PWM, LED, UART, ADC — are all present in a single project, each serving a real function rather than a standalone demo. The IoT lecture's "Everything as a Service" framing maps directly: the ESP32 publishes a service (attendance) consumed by LINE's cloud platform, which delivers it to students as a notification service.

---

## 6. Project Summary

| Dimension | Detail |
|---|---|
| Domain | Smart classroom — university lecture attendance |
| Physical input | LDR (room light), 3× Button — Blue/Yellow/Red (lecturer actions) |
| Physical output | 3× LED — Blue/Yellow/Red (GPIO 32/33/25) |
| Communication | BLE LINE Beacon → LINE Messaging API (Reply — free) |
| User identification | LINE userId (automatic) → student registry mapping |
| Concurrency model | 4 FreeRTOS tasks, 1 mutex, 1 EventGroup, 2 software timers |
| Interrupt sources | Hardware Timer ISR (50Hz ADC) + GPIO ISR (button) |
| Real-time deadline | BeaconTask: `vTaskDelayUntil(100ms)` hard period |
| Backend | Python Flask, SQLite, LINE Reply API |
| Message cost | ฿0 — Reply API is free, not counted in quota |
| Hardware cost | ~฿800–1,200 total BOM |
| 1-week feasibility | High — hardware simple, software layered incrementally |

### Effort distribution

```
Hardware + wiring           10%   LDR divider, 3 LEDs, button, ESP32
Timer ISR + ADC pipeline    15%   HW timer, circular buffer, xQueue
Button ISR + LecturerTask   15%   GPIO ISR, EventGroup, debounce
State machine + SensorTask  25%   5-state FSM, mutex, session logic
LINE beacon + webhook        35%   BLE payload + Flask backend + Reply API
```

---