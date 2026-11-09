// config_store.h — cấu hình camera + seq event, lưu NVS (đặc tả §7.2, §8.7)
#pragma once
#include <ArduinoJson.h>
#include "app.h"

enum FlashMode : uint8_t { FLASH_OFF = 0, FLASH_ON = 1, FLASH_AUTO = 2 };

// Khung ảnh cho phép, theo thứ tự tăng dần. Giá trị lưu là chỉ số trong bảng này.
constexpr uint8_t FRAME_COUNT = 6;
extern const char* const FRAME_NAMES[FRAME_COUNT];   // VGA, SVGA, XGA, HD, SXGA, UXGA

struct Config {
  uint32_t version;            // config_version đang dùng (0 = mặc định)
  uint8_t frameSize;           // chỉ số FRAME_NAMES, mặc định SVGA
  uint8_t jpegQuality;         // 8–30, số nhỏ = nét hơn, nặng hơn
  uint8_t flash;               // FlashMode
  uint16_t captureIntervalMin; // 1–1440
  uint8_t warmupFrames;        // 0–5, bỏ vài khung đầu cho camera ổn định phơi sáng
};

extern Config cfg;

void configBegin();
void configSave();
void configFactoryReset();
void configPrint();
const char* configParse(JsonObjectConst params, Config& out);  // nullptr nếu hợp lệ, không thì tên khóa sai
const char* flashModeName(uint8_t m);

uint32_t nextEventSeq();   // không lặp lại sau khi khởi động lại
