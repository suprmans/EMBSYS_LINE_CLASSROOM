// BusinessCase01 — Smart Classroom Attendance
// Blue  btn GPIO26 → LED GPIO32 : Start class   (IDLE → OPEN)
// Yellow btn GPIO14 → LED GPIO33 : Close window / Quiz (OPEN → RUNNING → QUIZ)
// Red   btn GPIO13 → LED GPIO25 : End class     (any → ENDED)

// ── Pins ─────────────────────────────────────────────────────
const int btnPins[] = { 26, 14, 13 };  // Blue, Yellow, Red
const int ledPins[] = { 32, 33, 25 };  // Blue, Yellow, Red

// ── Session state ─────────────────────────────────────────────
enum State { IDLE, OPEN, RUNNING, QUIZ, ENDED };
State sessionState = IDLE;

// ── Debounce state ────────────────────────────────────────────
bool ledState[3]              = { false, false, false };
bool lastStable[3]            = { HIGH,  HIGH,  HIGH  };
bool lastRaw[3]               = { HIGH,  HIGH,  HIGH  };
unsigned long lastChange[3]   = { 0, 0, 0 };

// ── LED blink timers ──────────────────────────────────────────
unsigned long lastBlink       = 0;
bool blinkToggle              = false;

// ── Session ID ────────────────────────────────────────────────
int sessionId = 0;

// ── Forward declarations ──────────────────────────────────────
void applyLEDs();
void transitionTo(State next);
const char* stateName(State s);

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

  Serial.println("Case01 ready — press Blue to start class");
}

// ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // ── Debounce all 3 buttons ───────────────────────────────
  for (int i = 0; i < 3; i++) {
    bool raw = digitalRead(btnPins[i]);

    if (raw != lastRaw[i]) {
      lastRaw[i]    = raw;
      lastChange[i] = now;
    }

    if ((now - lastChange[i]) >= 25 && raw != lastStable[i]) {
      lastStable[i] = raw;

      if (raw == LOW) {  // confirmed press
        if (i == 0) {    // Blue
          if (sessionState == IDLE) transitionTo(OPEN);

        } else if (i == 1) {  // Yellow
          if      (sessionState == OPEN)    transitionTo(RUNNING);
          else if (sessionState == RUNNING) transitionTo(QUIZ);

        } else if (i == 2) {  // Red
          if (sessionState != IDLE) transitionTo(ENDED);
        }
      }
    }
  }

  // ── Blink handler (Yellow LED) ───────────────────────────
  if (sessionState == RUNNING && now - lastBlink >= 500) {
    lastBlink  = now;
    blinkToggle = !blinkToggle;
    digitalWrite(ledPins[1], blinkToggle);  // 1 Hz slow blink
  }
  if (sessionState == QUIZ && now - lastBlink >= 100) {
    lastBlink  = now;
    blinkToggle = !blinkToggle;
    digitalWrite(ledPins[1], blinkToggle);  // 5 Hz fast blink
  }
}

// ─────────────────────────────────────────────────────────────
void transitionTo(State next) {
  // ENDED → IDLE after flash
  if (next == ENDED) {
    // Red LED: 3× flash
    for (int f = 0; f < 3; f++) {
      digitalWrite(ledPins[2], HIGH); delay(100);
      digitalWrite(ledPins[2], LOW);  delay(100);
    }
    // All LEDs off
    for (int i = 0; i < 3; i++) digitalWrite(ledPins[i], LOW);
    sessionState = IDLE;
    Serial.printf("[END] Session %03d ended\n", sessionId);
    return;
  }

  if (next == OPEN) {
    sessionId++;
    digitalWrite(ledPins[0], HIGH);  // Blue solid
    digitalWrite(ledPins[1], LOW);
    digitalWrite(ledPins[2], LOW);
    blinkToggle = false;
  }

  if (next == RUNNING) {
    digitalWrite(ledPins[0], LOW);   // Blue off
    lastBlink   = millis();
    blinkToggle = false;
  }

  if (next == QUIZ) {
    lastBlink   = millis();
    blinkToggle = false;
  }

  sessionState = next;
  Serial.printf("[%s] Session %03d — dm: cls:%s:%03d\n",
    stateName(next), sessionId, stateName(next), sessionId);
}

// ─────────────────────────────────────────────────────────────
const char* stateName(State s) {
  switch (s) {
    case IDLE:    return "idle";
    case OPEN:    return "open";
    case RUNNING: return "run";
    case QUIZ:    return "qz";
    case ENDED:   return "end";
    default:      return "?";
  }
}
