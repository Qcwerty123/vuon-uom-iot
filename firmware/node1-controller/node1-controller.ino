/*
 * node1-controller.ino — Firmware chính Node 1 (điều khiển) · Hệ thống chăm sóc vườn ươm
 *
 * Đặc tả: docs/dac-ta-he-thong.md §6 (firmware), §8 (MQTT).
 * Board: NodeMCU-32S · Partition: Default · Serial Monitor 115200, New Line.
 * v1.1.0: đèn chiếu sáng bổ sung trên relay kênh 3 (§6.11), lệch pha 400 ms khi bật relay, khóa nhiệt.
 * Thư viện: PubSubClient, ArduinoJson 7, DHT sensor library (+ Adafruit Unified Sensor),
 *           BH1750 (Christopher Laws), Keypad, U8g2 — phiên bản theo firmware/LIBRARIES.md.
 *
 * Trước khi nạp: tạo tab secrets.h từ secrets.example.h (KHÔNG commit secrets.h).
 * v1.2.0: danh tính (WiFi/MQTT/device_code/secret) ghi đè được bằng lệnh Serial và lưu NVS (identity.*);
 *         không ghi đè thì dùng giá trị trong secrets.h như cũ.
 *
 * Các tab:
 *   app.h            hằng số, gán chân, kiểu dữ liệu chung
 *   config_store.*   cấu hình + seq lưu NVS
 *   sensors.*        đọc, lọc, phát hiện lỗi, hợp nhất 2 cảm biến đất
 *   control.*        tưới, quạt, đèn, AUTO/MANUAL/LOCAL, khóa an toàn, lệch pha relay
 *   net.*            WiFi, NTP, MQTT
 *   protocol.*       telemetry/status/event/ack, xử lý command/config
 *   buffer.*         hàng đợi 200 bản ghi khi mất mạng
 *   ui.*             OLED + keypad
 */
#include "app.h"
#include "config_store.h"
#include "sensors.h"
#include "control.h"
#include "net.h"
#include "protocol.h"
#include "buffer.h"
#include "ui.h"
#include "identity.h"

static const uint32_t LOG_PERIOD_MS = 10000;
static uint32_t nextLog = 0;
static char serialLine[160];   // đủ cho "set upload <url>"; dòng dài hơn bị bỏ cả dòng (không cắt âm thầm)
static uint8_t serialLen = 0;
static bool serialOverflow = false;

static void printHelp() {
  Serial.println("Lenh Serial: s = cam bien | d = den/relay | c = cau hinh | n = mang | h = tro giup | factory = xoa cau hinh");
  Serial.println("Danh tinh: id | set <code|secret|garden|host|port|ssid|pass> <gia tri> | save | clear");
}

static void runSerialCommand(const char* cmd) {
  if (strcmp(cmd, "s") == 0) sensorsPrint();
  else if (strcmp(cmd, "d") == 0) controlPrint();
  else if (strcmp(cmd, "c") == 0) configPrint();
  else if (strcmp(cmd, "n") == 0) netPrint();
  else if (strcmp(cmd, "h") == 0) printHelp();
  else if (strcmp(cmd, "factory") == 0) {
    configFactoryReset();
    configSave();
    Serial.println("Da ve cau hinh mac dinh, khoi dong lai...");
    controlAllOff();
    delay(200);
    ESP.restart();
  } else if (int r = identityCommand(cmd)) {
    if (r == 2) {
      controlAllOff();
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
  controlBegin();            // tắt relay trước mọi việc khác
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n== Node 1 dieu khien · fw %s · hw %s ==\n", FW_VERSION, HW_VERSION);
  configBegin();
  identityBegin();           // trước netBegin(): net dùng ident.*
  controlLoadMode();
  configPrint();
  sensorsBegin();
  uiBegin();
  netBegin();
  protocolBegin();
  printHelp();
}

void loop() {
  netLoop();
  sensorsLoop();
  controlLoop();
  protocolLoop();
  uiLoop();
  serialLoop();
  uint32_t now = millis();
  if ((int32_t)(now - nextLog) >= 0) {
    nextLog = now + LOG_PERIOD_MS;
    Serial.printf("[%lus] %s bom=%d quat=%d den=%d dem=%u | ", (unsigned long)(now / 1000), modeName(),
                  pumpIsOn(), fanIsOn(), lampIsOn(), bufCount());
    sensorsPrint();
  }
}
