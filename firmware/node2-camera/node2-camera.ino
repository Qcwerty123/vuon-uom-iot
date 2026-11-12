/*
 * node2-camera.ino — Firmware chính Node 2 (camera ESP32-CAM) · Hệ thống chăm sóc vườn ươm
 *
 * Đặc tả: docs/dac-ta-he-thong.md §7 (firmware camera), §8 (MQTT), §8.9 (upload ảnh).
 * Board: AI Thinker ESP32-CAM · Partition: Huge APP (3MB No OTA/1MB SPIFFS) · PSRAM: Enabled
 * Thư viện cài thêm: PubSubClient, ArduinoJson 7 (esp_camera, HTTPClient có sẵn trong core).
 * Nạp qua đế ESP32-CAM-MB. Serial Monitor 115200, New Line.
 *
 * Trước khi nạp: tạo tab secrets.h từ secrets.example.h (KHÔNG commit secrets.h).
 * v1.1.0: danh tính (WiFi/MQTT/device_code/secret/upload) ghi đè được bằng lệnh Serial và lưu NVS (identity.*);
 *         không ghi đè thì dùng giá trị trong secrets.h như cũ.
 *
 * Các tab:
 *   app.h            hằng số, chân flash/LED
 *   config_store.*   cấu hình camera + seq event, lưu NVS
 *   camera.*         khởi tạo OV2640, chụp, flash
 *   capture.*        lịch chụp, chụp theo lệnh, upload HTTP có thử lại
 *   net.*            WiFi, NTP, MQTT (giống Node 1)
 *   protocol.*       status/event/ack, xử lý command/config
 */
#include "app.h"
#include "config_store.h"
#include "camera.h"
#include "capture.h"
#include "net.h"
#include "protocol.h"
#include "identity.h"

static char serialLine[160];   // đủ cho "set upload <url>"; dòng dài hơn bị bỏ cả dòng (không cắt âm thầm)
static uint8_t serialLen = 0;
static bool serialOverflow = false;
static uint32_t nextLog = 0;

static void printHelp() {
  Serial.println("Lenh Serial: p = chup + gui thu | f = nhay flash 1 s | c = cau hinh | n = mang | factory | h");
  Serial.println("Danh tinh: id | set <code|secret|garden|host|port|ssid|pass|upload> <gia tri> | save | clear");
}

static void runSerialCommand(const char* cmd) {
  if (strcmp(cmd, "p") == 0) {
    const char* why = captureRequest(nullptr, -1);
    Serial.println(why ? why : "da xep lich chup");
  } else if (strcmp(cmd, "f") == 0) {
    flashOnFor(1);
  } else if (strcmp(cmd, "c") == 0) {
    configPrint();
  } else if (strcmp(cmd, "n") == 0) {
    netPrint();
  } else if (strcmp(cmd, "h") == 0) {
    printHelp();
  } else if (strcmp(cmd, "factory") == 0) {
    configFactoryReset();
    configSave();
    Serial.println("Da ve cau hinh mac dinh, khoi dong lai...");
    delay(200);
    ESP.restart();
  } else if (int r = identityCommand(cmd)) {
    if (r == 2) {
      delay(200);
      ESP.restart();
    }
  } else if (cmd[0]) {
    Serial.printf("Khong hieu lenh '%s'\n", cmd);
    printHelp();
  }
}

static void serialLoop() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      serialLine[serialLen] = 0;
      if (serialOverflow) Serial.println("Dong lenh qua dai (>158 ky tu), da bo qua.");
      else runSerialCommand(serialLine);
      serialLen = 0;
      serialOverflow = false;
    } else if (serialLen < sizeof(serialLine) - 1) {
      serialLine[serialLen++] = ch;
    } else {
      serialOverflow = true;
    }
  }
}

void setup() {
  pinMode(pins::RED_LED, OUTPUT);
  redLed(true);                    // sáng cho tới khi kết nối MQTT xong
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n== Node 2 camera · fw %s · hw %s ==\n", FW_VERSION, HW_VERSION);
  configBegin();
  identityBegin();                 // trước netBegin(): net và capture dùng ident.*
  configPrint();
  cameraBegin();                   // khởi tạo camera TRƯỚC WiFi để tránh sụt áp cùng lúc
  netBegin();
  protocolBegin();
  captureBegin();
  printHelp();
}

void loop() {
  netLoop();
  cameraLoop();
  captureLoop();
  protocolLoop();
  serialLoop();
  redLed(!mqttUp());               // LED đỏ sáng = chưa kết nối được broker
  uint32_t now = millis();
  if ((int32_t)(now - nextLog) >= 0) {
    nextLog = now + 30000;
    Serial.printf("[%lus] camera=%s anh_ok=%lu loi=%lu chup_tiep_sau=%lus heap=%u psram=%u\n",
                  (unsigned long)(now / 1000), cameraReady() ? "OK" : "LOI",
                  (unsigned long)captureOkCount(), (unsigned long)captureFailCount(),
                  (unsigned long)captureNextInS(), (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getFreePsram());
  }
}
