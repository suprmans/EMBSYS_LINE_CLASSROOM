# Smart Classroom Attendance via LINE Beacon

Author: Shalong Samretnagn

ESP32-based smart attendance system for classrooms using BLE LINE Beacon, LDR light sensing, and FreeRTOS. Students are identified automatically through LINE userId mapping, then marked Present or Late by session state. The backend uses Flask and SQLite to process webhooks, register users, store logs, and send slides or quiz links through LINE Reply API. Hardware includes LDR, push button, and RGB status LEDs. Real-time design demonstrates ISR handling, mutex-protected shared state, EventGroup signaling, periodic scheduling, and embedded-to-cloud IoT integration at low cost.

Licensed under Apache License 2.0.
