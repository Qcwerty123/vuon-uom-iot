// portal.h — cài WiFi bằng điện thoại/máy tính: ESP32 tự phát AP + trang web nhỏ (captive portal).
// Không chặn vòng lặp chính (relay/cảm biến vẫn chạy). Lưu SSID/pass/host vào NVS qua identity.*, rồi khởi động lại.
//
// Khi nào bật: chưa có SSID nào (NVS trống và secrets.h để trống), hoặc không nối được WiFi sau nhiều lần
// thử liên tiếp (net.cpp), hoặc lệnh Serial 'portal'.
// Khi nào tắt: lưu xong (khởi động lại); hoặc hết 5 phút nếu đã có SSID để thử lại; không có SSID thì chờ mãi.
#pragma once
#include "app.h"

void portalStart();
void portalStop();
bool portalActive();
bool portalLoop();                 // gọi mỗi vòng loop(). true = đã lưu cấu hình, cần khởi động lại
const char* portalApName();        // tên WiFi do thiết bị phát
const char* portalApPass();        // mật khẩu WiFi đó
