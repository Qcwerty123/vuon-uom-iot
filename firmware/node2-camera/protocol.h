// protocol.h — status, event, ack; xử lý command/config cho Node 2 (đặc tả §7.4, §8)
#pragma once
#include <functional>
#include <ArduinoJson.h>
#include "app.h"

using DetailFn = std::function<void(JsonObject)>;

void protocolBegin();
void protocolLoop();
void protocolOnConnected();
void protocolOnMessage(const char* kind, const uint8_t* payload, unsigned int len);  // "command" | "config"

void emitEvent(const char* type, DetailFn fill = nullptr);
void requestStatusSoon();

// Lệnh capture được ack SAU khi upload xong (§7.1) — capture.cpp gọi hàm này
void protocolCaptureDone(const char* cmdId, const char* result, DetailFn fill);
