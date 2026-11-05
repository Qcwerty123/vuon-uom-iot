// protocol.h — đóng gói/đọc bản tin MQTT: telemetry, status, event, ack, command, config (đặc tả §8)
#pragma once
#include <functional>
#include <ArduinoJson.h>
#include "app.h"

using DetailFn = std::function<void(JsonObject)>;

void protocolBegin();
void protocolLoop();                 // lịch telemetry, heartbeat, gửi bù, xả hàng đợi event
void protocolOnConnected();          // gọi sau mỗi lần kết nối MQTT thành công
void protocolOnMessage(const char* kind, const uint8_t* payload, unsigned int len);  // kind: "command" | "config"

// Ghi một event vào hàng đợi; được gửi khi có kết nối (§8.5)
void emitEvent(const char* type, DetailFn fill = nullptr);
void requestStatusSoon();            // gửi status ở vòng lặp tới
