// identity.h — danh tính thiết bị (WiFi, MQTT, device_code, secret) lưu NVS, ghi đè qua lệnh Serial.
// Giống hệt bản của Node 2: sửa ở một nơi thì chép sang nơi kia.
//
// Quy tắc: mỗi trường lấy từ NVS nếu đã được 'set' + 'save', nếu không thì lấy giá trị biên dịch trong secrets.h.
// NVS trống (hoặc 'clear') = chạy y hệt firmware cũ.
#pragma once
#include <Arduino.h>

struct Identity {
  char wifiSsid[33];
  char wifiPass[65];
  char mqttHost[40];
  uint16_t mqttPort;
  char garden[12];
  char code[20];      // device_code, ví dụ ctl-0001
  char secret[72];    // secret cấp phát (~43 ký tự)
  char uploadUrl[128];  // chỉ Node 2 dùng; Node 1 để trống
};

extern Identity ident;   // giá trị đang dùng (chỉ đổi lúc khởi động)

void identityBegin();    // gọi trong setup() TRƯỚC netBegin()

// Xử lý lệnh Serial: id | set <khóa> <giá trị> | save | clear
// Trả về 0 = không phải lệnh danh tính; 1 = đã xử lý; 2 = đã xử lý và cần khởi động lại.
int identityCommand(const char* cmd);
void identityPrint();
