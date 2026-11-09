// config_store.h — cấu hình thiết bị, số thứ tự seq, chế độ; lưu NVS (đặc tả §6.5, §6.7, §8.7)
#pragma once
#include <ArduinoJson.h>
#include "app.h"

struct SoilCal {
  uint16_t dry;  // ADC khi để ngoài không khí
  uint16_t wet;  // ADC khi nhúng nước tới vạch
};

struct Config {
  uint32_t version;  // config_version đang dùng (0 = mặc định xuất xưởng)
  float soilLow, soilHigh;
  uint16_t pumpMaxS, cooldownS;
  float tankMin;
  float tempHigh, tempHyst, humHigh, humHyst;
  uint16_t telemetryIntervalS;
  bool manualIgnoresCooldown;
  SoilCal s1, s2;
  float tankEmptyCm, tankFullCm;
  // Chiếu sáng bổ sung (§6.11)
  uint8_t lampStartHour, lampEndHour;   // khung [start, end), giờ Việt Nam
  uint16_t lampLuxLow;                  // ngưỡng bật
  uint16_t lampHyst;                    // ngưỡng tắt = lampLuxLow + lampHyst
  uint16_t lampSelfLux;                 // ΔE_LED đo khi hiệu chuẩn
  uint16_t lampHoldS;                   // debounce
  uint16_t lampMinOnS, lampMinOffS;     // thời gian giữ tối thiểu
  uint16_t lampOverrideMin;             // lệnh tay khi AUTO giữ tối đa bao lâu
};

extern Config cfg;

void configBegin();                 // nạp từ NVS, không có thì dùng mặc định
void configSave();
void configFactoryReset();          // xóa NVS cấu hình, về mặc định
void configPrint();

// Áp các khóa có trong params lên bản sao 'out' (bắt đầu từ cfg hiện tại).
// Trả về nullptr nếu hợp lệ, hoặc tên khóa sai đầu tiên.
const char* configParse(JsonObjectConst params, Config& out);

// Số thứ tự không bao giờ lặp lại kể cả sau khi khởi động lại (§6.7)
uint32_t nextTelemetrySeq();
uint32_t nextEventSeq();

// Chế độ nền AUTO/MANUAL, giữ qua khởi động lại
bool savedModeIsAuto();
void saveModeIsAuto(bool isAuto);
