// ── Pins ─────────────────────────────────────────────────────
const int btnPins[] = { 26, 14, 13 };  // Blue, Yellow, Red
const int ledPins[] = { 32, 33, 25 };  // Blue, Yellow, Red

// ── State ────────────────────────────────────────────────────
bool ledState[3]   = { false, false, false };
bool lastStable[3] = { HIGH,  HIGH,  HIGH  };
bool lastRaw[3]    = { HIGH,  HIGH,  HIGH  };
unsigned long lastChange[3] = { 0, 0, 0 };

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

  Serial.println("Ready — press any button");
}

void loop() {
  for (int i = 0; i < 3; i++) {
    bool raw = digitalRead(btnPins[i]);

    if (raw != lastRaw[i]) {
      lastRaw[i] = raw;
      lastChange[i] = millis();
    }

    if ((millis() - lastChange[i]) >= 25 && raw != lastStable[i]) {
      lastStable[i] = raw;
      if (raw == LOW) {
        ledState[i] = !ledState[i];
        digitalWrite(ledPins[i], ledState[i]);
        const char* names[] = { "Blue", "Yellow", "Red" };
        Serial.printf("[%s] LED %s\n", names[i], ledState[i] ? "ON" : "OFF");
      }
    }
  }
}