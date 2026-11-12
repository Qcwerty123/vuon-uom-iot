// app.h — hằng số và gán chân Node 2 (ESP32-CAM AI-Thinker) (đặc tả §5.4, §7)
#pragma once
#include <Arduino.h>

#define FW_VERSION "1.1.0"
#define HW_VERSION "node2-r1"

// Giờ Việt Nam (UTC+7) — chỉ dùng cho chế độ flash "auto" (bật 19h–6h)
#define TZ_OFFSET_H 7

namespace pins {
constexpr int FLASH_LED = 4;   // đèn flash trắng, rất sáng — chỉ bật khi chụp
constexpr int RED_LED = 33;    // LED đỏ trên board, sáng khi kéo LOW
}

inline void redLed(bool on) { digitalWrite(pins::RED_LED, on ? LOW : HIGH); }
