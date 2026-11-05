// buffer.h — hàng đợi vòng telemetry khi mất kết nối (đặc tả §6.7, NFR07)
#pragma once
#include "app.h"

struct TelemetryRec {
  uint32_t seq;
  uint64_t ts;        // epoch ms lúc đo (0 nếu chưa có giờ NTP)
  uint32_t ms;        // millis() lúc đo — dùng để suy ra ts nếu lúc đo chưa có giờ
  bool synced;
  Readings r;
  bool pump, fan;
  uint8_t mode;       // 0 AUTO, 1 MANUAL, 2 LOCAL
  uint8_t locks;      // LockBits
};

constexpr uint16_t BUF_CAPACITY = 200;   // ≥ 100 theo NFR07

void bufPush(const TelemetryRec& rec);   // đầy thì ghi đè bản cũ nhất, tăng dropped
bool bufPeek(TelemetryRec& out);         // bản cũ nhất
void bufPop();
uint16_t bufCount();
uint32_t bufDropped();
