// control.h — tưới, quạt, chế độ AUTO/MANUAL/LOCAL, khóa an toàn (đặc tả §6.5, §6.6)
#pragma once
#include <ArduinoJson.h>
#include "app.h"

void controlBegin();     // gọi ĐẦU TIÊN trong setup(): tắt mọi relay
void controlLoadMode();  // sau configBegin(): khôi phục AUTO/MANUAL đã lưu
void controlLoop();

// Thực thi lệnh điều khiển. Trả về chuỗi result của ack (§8.6), ghi thêm vào detail.
// Lệnh hệ thống (reboot, request_status) do protocol xử lý.
const char* controlCommand(const char* action, JsonObjectConst params, JsonObject detail, Source src);

bool pumpIsOn();
bool fanIsOn();
bool modeIsAuto();
uint8_t modeCode();          // 0 AUTO, 1 MANUAL, 2 LOCAL
const char* modeName();
uint8_t currentLocks();      // LockBits
void locksToJson(uint8_t locks, JsonArray arr);

// Chế độ LOCAL (keypad)
void localEnter();
void localExit();
void localTouch();           // gia hạn 60 s mỗi lần bấm phím
bool localActive();
uint32_t localRemainingS();

void controlAllOff();        // tắt bơm và quạt ngay (dùng trước khi reboot)
