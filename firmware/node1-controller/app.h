// app.h — hằng số, gán chân và kiểu dữ liệu dùng chung (đặc tả §5.2, §6)
#pragma once
#include <Arduino.h>

#define FW_VERSION "1.0.0"
#define HW_VERSION "node1-r1"

// Jumper relay đặt ở H (kích mức cao) — hướng dẫn lắp đặt §C8.
// Nếu đặt ở L thì đổi thành 0.
#define RELAY_ACTIVE_HIGH 1

namespace pins {
constexpr int SOIL1 = 34;        // ADC1, chỉ đầu vào
constexpr int SOIL2 = 35;        // ADC1, chỉ đầu vào
constexpr int SOIL_PWR = 32;     // VCC cảm biến đất (loại điện trở), chỉ bật khi đo
constexpr int DHT_DATA = 4;
constexpr int I2C_SDA = 21;      // BH1750 0x23 + OLED SH1106 0x3C
constexpr int I2C_SCL = 22;
constexpr int US_TRIG = 5;
constexpr int US_ECHO = 18;      // qua cầu chia 1k/2k
constexpr int RELAY_PUMP = 26;   // IN1
constexpr int RELAY_FAN = 27;    // IN2
constexpr int RELAY_SPARE = 25;  // IN3 — để trống, luôn tắt
constexpr uint8_t KP_ROWS[4] = {13, 14, 16, 17};
constexpr uint8_t KP_COLS[3] = {19, 23, 33};
}

// Một đại lượng đo: giá trị + hợp lệ
struct Metric {
  float v = 0;
  bool ok = false;
};

struct Readings {
  Metric soil1, soil2, soil;  // %; soil = giá trị đã hợp nhất (§6.4)
  Metric airTemp, airHum;     // °C, %RH
  Metric light;               // lux
  Metric tank;                // %
  float tankRawCm = 0;
};

enum class Source : uint8_t { AUTO, REMOTE, LOCAL };
inline const char* sourceName(Source s) {
  return s == Source::AUTO ? "auto" : (s == Source::REMOTE ? "remote" : "local");
}

// Bit khóa an toàn trong telemetry (§8.3)
enum LockBits : uint8_t {
  LOCK_NO_WATER = 1,
  LOCK_COOLDOWN = 2,
  LOCK_SOIL_FAULT = 4,
  LOCK_LOCAL = 8,
};

inline float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
inline double round1(float x) { return round(x * 10.0) / 10.0; }
