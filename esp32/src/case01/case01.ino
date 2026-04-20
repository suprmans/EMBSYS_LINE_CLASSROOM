// BusinessCase01 — Smart Classroom Attendance
// LINE Simple Beacon  HWID: 018f62bd52
//
// Blue  btn GPIO26 → LED GPIO32 : IDLE  → OPEN     (cls:open:NNN)
// Yellow btn GPIO14 → LED GPIO33 : OPEN  → RUNNING  (cls:run:NNN)
//                                  RUNNING → QUIZ    (cls:qz:NNN)
// Red   btn GPIO13 → LED GPIO25 : any   → ENDED    (cls:end:NNN)

#include <BLEDevice.h>
#include <BLEAdvertising.h>

// ── LINE Simple Beacon constants ──────────────────────────────
// Service UUID 0xFE6F  (LINE Corp)  little-endian: 6F FE
static const uint8_t LINE_HWID[5] = { 0x01, 0x8F, 0x62, 0xBD, 0x52 };
static const uint8_t TX_POWER     = 0x7F;  // 0 dBm nominal

// ── Pins ─────────────────────────────────────────────────────
const int btnPins[] = { 26, 14, 13 };  // Blue, Yellow, Red
const int ledPins[] = { 32, 33, 25 };  // Blue, Yellow, Red

// ── Session state ─────────────────────────────────────────────
enum State { IDLE, OPEN, RUNNING, QUIZ, ENDED };
State sessionState = IDLE;
int   sessionId    = 0;

// ── Debounce ──────────────────────────────────────────────────
bool          lastStable[3]  = { HIGH, HIGH, HIGH };
bool          lastRaw[3]     = { HIGH, HIGH, HIGH };
unsigned long lastChange[3]  = { 0, 0, 0 };

// ── LED blink ─────────────────────────────────────────────────
unsigned long lastBlink  = 0;
bool          blinkState = false;

// ── BLE ───────────────────────────────────────────────────────
BLEAdvertising* pAdv = nullptr;

// ─────────────────────────────────────────────────────────────
// Build LINE Simple Beacon advertisement and (re)start advertising.
// dm must be ≤ 13 bytes (LINE spec limit).
// ─────────────────────────────────────────────────────────────
void advertiseBeacon(const char* dm) {
  if (!pAdv) return;
  pAdv->stop();

  uint8_t dmLen  = (uint8_t)strnlen(dm, 13);
  // Service-data AD structure length = 2 (UUID) + 1 (sub-type) + 5 (HWID) + 1 (TX) + dmLen
  uint8_t sdLen  = 2 + 1 + 5 + 1 + dmLen;

  // Full raw advertisement payload
  // [flags AD] [UUID list AD] [service-data AD]
  uint8_t adv[31];
  uint8_t i = 0;

  // Flags
  adv[i++] = 0x02; adv[i++] = 0x01; adv[i++] = 0x06;

  // Complete list of 16-bit UUIDs: 0xFE6F
  adv[i++] = 0x03; adv[i++] = 0x03; adv[i++] = 0x6F; adv[i++] = 0xFE;

  // Service data for 0xFE6F
  adv[i++] = sdLen + 1;   // length byte (includes type byte)
  adv[i++] = 0x16;         // AD type: Service Data
  adv[i++] = 0x6F; adv[i++] = 0xFE;  // UUID little-endian
  adv[i++] = 0x02;         // LINE Simple Beacon sub-type
  for (int b = 0; b < 5; b++) adv[i++] = LINE_HWID[b];
  adv[i++] = TX_POWER;
  for (int b = 0; b < dmLen; b++) adv[i++] = (uint8_t)dm[b];

  BLEAdvertisementData data;
  data.addData(std::string((char*)adv, i));
  pAdv->setAdvertisementData(data);
  pAdv->start();

  Serial.printf("[BLE] dm=\"%s\"  (%d bytes)\n", dm, dmLen);
}

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  for (int i = 0; i < 3; i++) {
    pinMode(btnPins[i], INPUT_PULLUP);
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  // Boot flash — confirms LED wiring
  for (int i = 0; i < 3; i++) digitalWrite(ledPins[i], HIGH);
  delay(300);
  for (int i = 0; i < 3; i++) digitalWrite(ledPins[i], LOW);

  // BLE init
  BLEDevice::init("scool-beacon-01");
  pAdv = BLEDevice::getAdvertising();
  pAdv->setMinInterval(160);  // 100 ms  (units of 0.625 ms)
  pAdv->setMaxInterval(160);

  advertiseBeacon("cls:idle");
  Serial.println("Case01 ready — press Blue to start class");
}

// ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // ── Debounce all 3 buttons ────────────────────────────────
  for (int i = 0; i < 3; i++) {
    bool raw = digitalRead(btnPins[i]);
    if (raw != lastRaw[i]) { lastRaw[i] = raw; lastChange[i] = now; }

    if ((now - lastChange[i]) >= 25 && raw != lastStable[i]) {
      lastStable[i] = raw;
      if (raw == LOW) {
        if      (i == 0 && sessionState == IDLE)    transitionTo(OPEN);
        else if (i == 1 && sessionState == OPEN)    transitionTo(RUNNING);
        else if (i == 1 && sessionState == RUNNING) transitionTo(QUIZ);
        else if (i == 2 && sessionState != IDLE)    transitionTo(ENDED);
      }
    }
  }

  // ── Yellow LED blink (RUNNING=1Hz, QUIZ=5Hz) ─────────────
  unsigned long interval = (sessionState == RUNNING) ? 500 : 100;
  if ((sessionState == RUNNING || sessionState == QUIZ) && now - lastBlink >= interval) {
    lastBlink  = now;
    blinkState = !blinkState;
    digitalWrite(ledPins[1], blinkState);
  }
}

// ─────────────────────────────────────────────────────────────
void transitionTo(State next) {
  char dm[14];

  if (next == ENDED) {
    // Red LED: 3× flash
    for (int f = 0; f < 3; f++) {
      digitalWrite(ledPins[2], HIGH); delay(100);
      digitalWrite(ledPins[2], LOW);  delay(100);
    }
    for (int i = 0; i < 3; i++) digitalWrite(ledPins[i], LOW);
    snprintf(dm, sizeof(dm), "cls:end:%03d", sessionId);
    advertiseBeacon(dm);
    sessionState = IDLE;
    Serial.printf("[END] Session %03d\n", sessionId);
    delay(5000);                    // keep cls:end visible for 5 s
    advertiseBeacon("cls:idle");
    return;
  }

  if (next == OPEN) {
    sessionId++;
    digitalWrite(ledPins[0], HIGH);
    digitalWrite(ledPins[1], LOW);
    digitalWrite(ledPins[2], LOW);
    snprintf(dm, sizeof(dm), "cls:open:%03d", sessionId);
  } else if (next == RUNNING) {
    digitalWrite(ledPins[0], LOW);
    lastBlink = millis(); blinkState = false;
    snprintf(dm, sizeof(dm), "cls:run:%03d", sessionId);
  } else if (next == QUIZ) {
    lastBlink = millis(); blinkState = false;
    snprintf(dm, sizeof(dm), "cls:qz:%03d", sessionId);
  }

  sessionState = next;
  advertiseBeacon(dm);
  Serial.printf("[%-7s] Session %03d\n", dm, sessionId);
}
