// net.h — WiFi (backoff), NTP, MQTT (LWT, subscribe QoS 1) (đặc tả §6.7, §7.1, §8.1)
// Giống hệt bản của Node 1: sửa ở một nơi thì chép sang nơi kia.
#pragma once
#include "app.h"

void netBegin();
void netLoop();                       // không chặn, trừ lúc gọi connect MQTT (tối đa vài giây)
bool wifiUp();
bool mqttUp();
bool netPublish(const char* kind, const char* payload, bool retain = false);  // kind: status/event/ack (+ telemetry ở Node 1)

uint64_t nowMs();                     // epoch ms UTC; 0 nếu chưa đồng bộ NTP
bool timeSynced();
const char* deviceCode();
int wifiRssi();
void netIp(char* buf, size_t n);
void netPrint();
