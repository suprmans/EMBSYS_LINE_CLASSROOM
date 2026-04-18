# ESP32 Module — Smart Classroom Attendance

## Overview

The ESP32 is the embedded edge device. It reads ambient light (LDR), responds to lecturer button presses, drives a 3-LED status panel, and continuously broadcasts a **LINE Simple Beacon** BLE advertisement carrying a `dm` payload that encodes the current session state.

---

## Hardware

### Wiring (breadboard)

```
ESP32 DevKit
├── GPIO34 (ADC) ──┬── LDR
│                  └── 10kΩ resistor ── GND     (voltage divider)
│
├── GPIO0  ────────── Button ── GND              (INPUT_PULLUP, FALLING edge)
│
├── GPIO25 (LEDC) ── 220Ω ── LED Green           (heartbeat / system alive)
├── GPIO26 (LEDC) ── 220Ω ── LED Yellow          (session state)
├── GPIO27 (LEDC) ── 220Ω ── LED Red             (quiz / alert)
│
└── BLE radio (internal) ── LINE Simple Beacon advertising
```

### LDR voltage divider

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

| Room condition | LDR resistance | ADC reading | Event |
|---|---|---|---|
| Bright (lights ON) | Low | High voltage | `LIGHT_ON` |
| Dark (lights OFF) | High | Low voltage | `LIGHT_OFF` |

### Component duties

| Component | Physical role | Embedded role | Course concept |
|---|---|---|---|
| **LDR** | Detects classroom light | HW Timer ISR → ADC read → circular buffer → moving average → state transition | Interrupt, ADC peripheral |
| **Button** | Lecturer manual action | GPIO falling-edge ISR → `xEventGroupSetBitsFromISR` | Interrupt, EventGroup |
| **LED Green** | System heartbeat | LEDC PWM channel, 1 Hz fade — always on | PWM peripheral |
| **LED Yellow** | Session window status | GPIO driven by LEDTask — solid = OPEN, slow blink = RUNNING | Digital output, RTOS task |
| **LED Red** | Quiz / alert signal | HW Timer callback drives 5 Hz blink — no task blocking | Timer peripheral |
| **ESP32 BLE** | Broadcasts session context | BeaconTask updates `dm` payload each cycle; `vTaskDelayUntil` enforces 100 ms period | Real-time scheduling |

---

## Session State Machine

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

### dm payload per state (max 13 bytes)

| State | `dm` value | LED state | Backend action |
|---|---|---|---|
| IDLE | `"cls:idle"` | Green heartbeat only | Ignore detections |
| OPEN | `"cls:open:001"` | Yellow solid | Log PRESENT, reply with slides |
| RUNNING | `"cls:run:001"` | Yellow slow blink | Log LATE, reply with slides |
| QUIZ | `"cls:qz:001"` | Red 5 Hz blink | Reply LIFF quiz link |
| ENDED | `"cls:end:001"` | All off | Mark absentees, send summary |

---

## FreeRTOS Architecture

### Task map

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
LecturerTask (priority 3) ← high    - reads SessionState
  - xEventGroupWaitBits               - drives LEDC channels
  - software debounce (300 ms)        - delegates Red LED to HW timer
  - cycles mode: QUIZ / END / OPEN
  - xSemaphoreTake(state_mutex)
  - writes SessionState + dm_buffer
  - xSemaphoreGive(state_mutex)
```

### Shared state

```cpp
// Shared globals — all access must hold state_mutex
SessionState session_state = IDLE;
char dm_buffer[14] = "cls:idle";
int  session_id    = 1;

SemaphoreHandle_t state_mutex;
EventGroupHandle_t event_group;
QueueHandle_t adc_queue;

#define BIT_BUTTON BIT0
```

---

## Key Code Patterns

### Hardware Timer ISR → Queue (50 Hz ADC sampling)

```cpp
// Timer ISR — runs every 20 ms on hardware timer
void IRAM_ATTR onTimer() {
    int raw = analogRead(LDR_PIN);
    xQueueSendFromISR(adc_queue, &raw, NULL);
}
```

### Button ISR → EventGroup (aperiodic, lecturer)

```cpp
void IRAM_ATTR buttonISR() {
    BaseType_t woken = pdFALSE;
    xEventGroupSetBitsFromISR(event_group, BIT_BUTTON, &woken);
    portYIELD_FROM_ISR(woken);
}
```

### Semaphore-guarded state write

```cpp
if (xSemaphoreTake(state_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    session_state = new_state;
    snprintf(dm_buffer, 14, "cls:%s:%03d", state_str, session_id);
    xSemaphoreGive(state_mutex);
}
```

### Real-time beacon period — BeaconTask (hard 100 ms deadline)

```cpp
TickType_t last_wake = xTaskGetTickCount();
for (;;) {
    vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(100));
    updateBeaconPayload(dm_buffer);
}
```

`vTaskDelayUntil` guarantees the 100 ms period regardless of how long `updateBeaconPayload` takes — this is the textbook hard real-time constraint.

### Debounce in task context (not ISR)

```cpp
TickType_t now = xTaskGetTickCount();
if ((now - last_press) < pdMS_TO_TICKS(300)) continue;
last_press = now;
```

### SensorTask moving average (circular buffer)

```cpp
#define BUF_SIZE 10
int buf[BUF_SIZE] = {0};
int idx = 0;

// In SensorTask loop:
int raw;
if (xQueueReceive(adc_queue, &raw, portMAX_DELAY)) {
    buf[idx++ % BUF_SIZE] = raw;
    int avg = 0;
    for (int i = 0; i < BUF_SIZE; i++) avg += buf[i];
    avg /= BUF_SIZE;

    if (avg > LIGHT_THRESHOLD) trigger_light_on();
    else                        trigger_light_off();
}
```

---

## LINE Simple Beacon BLE Advertisement

The ESP32 broadcasts a BLE advertisement following the **LINE Simple Beacon** specification. The `hwid` is registered in LINE Official Account Manager and links the hardware to the OA.

```
BLE Advertisement payload
├── hwid      (10 hex chars) — device identity, registered with LINE
├── type      "enter" is detected by LINE app automatically
└── dm        up to 13 bytes — custom payload, set by firmware each cycle
```

The `dm` payload is the only field the firmware controls per-cycle. It is updated inside `BeaconTask` on every 100 ms tick.

---

## Interrupt & Peripheral Mapping to Course Topics

| Month | Topic | This project |
|---|---|---|
| January | Interrupt programming, counting events with ISR | HW Timer ISR at 50 Hz feeds ADC queue; GPIO ISR on button falling edge |
| February | FreeRTOS, semaphores, reader-writer problem | `state_mutex` guards `SessionState`; 2 readers (LED, Beacon) vs 2 writers (Sensor, Lecturer) |
| March | Real-time scheduling, `vTaskDelayUntil`, preemption | BeaconTask hard 100 ms deadline; LecturerTask (priority 3) preempts SensorTask (priority 2) |
| April | Timer peripheral, PWM (LEDC), ADC, UART | HW Timer for ADC sampling + Red LED blink; LEDC for Green heartbeat; Serial debug output |

---

## Build & Flash

```bash
# PlatformIO (recommended)
pio run --target upload

# Arduino IDE
# Board: "ESP32 Dev Module"
# Partition: default
# Upload speed: 921600
```

### Dependencies (platformio.ini)

```ini
[env:esp32dev]
platform  = espressif32
board     = esp32dev
framework = arduino
lib_deps  =
    ESP32 BLE Arduino
```

---

## UART Debug Output

```
[SENSOR]  avg=2841  state=OPEN  session=001
[BEACON]  dm=cls:open:001
[LECTURER] button pressed → QUIZ mode
[LED]     state=QUIZ → Red 5Hz blink
```

Serial baud rate: **115200**
