#include "ui.h"
#include <U8g2lib.h>
#include <Keypad.h>
#include "secrets.h"
#include "config_store.h"
#include "sensors.h"
#include "control.h"
#include "protocol.h"
#include "buffer.h"
#include "net.h"

// Màn chữ không dấu vì font 6x10 không có ký tự tiếng Việt
static U8G2_SH1106_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);

static char keyMap[4][3] = {
  {'1', '2', '3'},
  {'4', '5', '6'},
  {'7', '8', '9'},
  {'*', '0', '#'},
};
static byte rowPins[4] = {pins::KP_ROWS[0], pins::KP_ROWS[1], pins::KP_ROWS[2], pins::KP_ROWS[3]};
static byte colPins[3] = {pins::KP_COLS[0], pins::KP_COLS[1], pins::KP_COLS[2]};
static Keypad keypad(makeKeymap(keyMap), rowPins, colPins, 4, 3);

static const uint32_t DRAW_PERIOD_MS = 1000;
static const uint32_t PIN_TIMEOUT_MS = 15000;
static const uint32_t PIN_LOCKOUT_MS = 60000;
static const uint8_t PIN_MAX_TRIES = 3;

static uint8_t page = 0;
static bool pinEntry = false;
static char pinBuf[5];
static uint8_t pinLen = 0, wrongTries = 0;
static uint32_t pinStartedAt = 0, lockoutUntil = 0, nextDraw = 0, msgUntil = 0;
static char msg[22] = "";

static void showMsg(const char* text, uint32_t ms = 2500) {
  snprintf(msg, sizeof msg, "%s", text);
  msgUntil = millis() + ms;
  nextDraw = 0;
}

static const char* resultText(const char* r) {
  if (strcmp(r, "executed") == 0) return "OK";
  if (strcmp(r, "duration_capped") == 0) return "OK (gioi han)";
  if (strcmp(r, "blocked_no_water") == 0) return "Chan: be can";
  if (strcmp(r, "blocked_cooldown") == 0) return "Chan: dang nghi";
  if (strcmp(r, "blocked_sensor_fault") == 0) return "Chan: loi cam bien";
  if (strcmp(r, "blocked_overheat") == 0) return "Chan: qua nong";
  return r;
}

// Thao tác tại chỗ: dùng chung hàm điều khiển với lệnh từ xa, nên chịu cùng khóa an toàn
static void localAction(const char* action) {
  JsonDocument pDoc, dDoc;
  if (strcmp(action, "pump_on") == 0) pDoc["duration_s"] = cfg.pumpMaxS;
  if (strcmp(action, "set_mode") == 0) pDoc["mode"] = modeIsAuto() ? "MANUAL" : "AUTO";
  const char* res = controlCommand(action, pDoc.as<JsonObjectConst>(), dDoc.to<JsonObject>(), Source::LOCAL);
  emitEvent("local_override", [action, res](JsonObject d) {
    d["action"] = action;
    d["result"] = res;
  });
  showMsg(resultText(res));
}

static void checkPin() {
  pinEntry = false;
  pinBuf[pinLen] = 0;
  if (strcmp(pinBuf, LOCAL_PIN) == 0) {
    wrongTries = 0;
    localEnter();
    emitEvent("local_override", [](JsonObject d) { d["action"] = "enter"; });
    showMsg("Vao LOCAL 60s");
    return;
  }
  if (++wrongTries >= PIN_MAX_TRIES) {
    wrongTries = 0;
    lockoutUntil = millis() + PIN_LOCKOUT_MS;
    emitEvent("local_override", [](JsonObject d) { d["action"] = "pin_lockout"; });
    showMsg("Sai 3 lan, khoa 60s", 4000);
  } else {
    showMsg("Sai PIN");
  }
}

static void handleKey(char k) {
  uint32_t now = millis();
  nextDraw = 0;
  if (pinEntry) {
    if (k == '#') checkPin();
    else if (k == '*') pinLen = 0;
    else if (k >= '0' && k <= '9' && pinLen < 4) pinBuf[pinLen++] = k;
    return;
  }
  if (k == '*') {
    if ((int32_t)(now - lockoutUntil) < 0) {
      showMsg("Ban phim dang khoa");
      return;
    }
    pinEntry = true;
    pinLen = 0;
    pinStartedAt = now;
    return;
  }
  if (k == '#') {
    page = (page + 1) % 3;
    return;
  }
  if (!localActive()) return;
  localTouch();
  switch (k) {
    case '1': localAction(pumpIsOn() ? "pump_off" : "pump_on"); break;
    case '2': localAction(fanIsOn() ? "fan_off" : "fan_on"); break;
    case '3': localAction("set_mode"); break;
    case '4': localAction(lampIsOn() ? "lamp_off" : "lamp_on"); break;
    case '0':
      localExit();
      emitEvent("local_override", [](JsonObject d) { d["action"] = "exit"; });
      showMsg("Thoat LOCAL");
      break;
    default: break;
  }
}

// ---------- vẽ màn hình ----------

static void fmtMetric(char* buf, size_t n, const Metric& m, int decimals, const char* unit) {
  if (!m.ok) snprintf(buf, n, "--");
  else if (decimals == 0) snprintf(buf, n, "%.0f%s", m.v, unit);
  else snprintf(buf, n, "%.1f%s", m.v, unit);
}

static void line(uint8_t row, const char* text) {
  oled.drawStr(0, 9 + row * 11, text);  // 6 dòng, dòng 0 là tiêu đề
}

static void drawHeader() {
  char h[32];
  if (localActive()) snprintf(h, sizeof h, "[%u/3] LOCAL %lus", page + 1, (unsigned long)localRemainingS());
  else snprintf(h, sizeof h, "[%u/3] %s %s", page + 1, modeName(), mqttUp() ? "" : "(mat mang)");
  line(0, h);
  oled.drawHLine(0, 11, 128);
}

static void drawSensors() {
  const Readings& r = sensorReadings();
  char a[10], b[10], t[32];
  fmtMetric(a, sizeof a, r.soil1, 0, "%");
  fmtMetric(b, sizeof b, r.soil2, 0, "%");
  snprintf(t, sizeof t, "Dat1 %-5s Dat2 %s", a, b);
  line(1, t);
  fmtMetric(a, sizeof a, r.soil, 0, "%");
  fmtMetric(b, sizeof b, r.tank, 0, "%");
  snprintf(t, sizeof t, "Dat  %-5s Be   %s", a, b);
  line(2, t);
  fmtMetric(a, sizeof a, r.airTemp, 1, "C");
  fmtMetric(b, sizeof b, r.airHum, 0, "%");
  snprintf(t, sizeof t, "T %-7s  H %s", a, b);
  line(3, t);
  fmtMetric(a, sizeof a, r.light, 0, "");
  snprintf(t, sizeof t, "Anh sang %s lux", a);
  line(4, t);
}

static void drawActuators() {
  char t[32];
  snprintf(t, sizeof t, "Bom: %s  Quat: %s", pumpIsOn() ? "BAT" : "tat", fanIsOn() ? "BAT" : "tat");
  line(1, t);
  snprintf(t, sizeof t, "Den: %s (%02u-%02u)", lampIsOn() ? "BAT" : "tat", cfg.lampStartHour, cfg.lampEndHour);
  line(2, t);
  snprintf(t, sizeof t, "Che do: %s", modeIsAuto() ? "AUTO" : "MANUAL");
  line(3, t);
  uint8_t l = currentLocks();
  snprintf(t, sizeof t, "Khoa:%s%s%s%s%s%s", l ? "" : " khong",
           (l & LOCK_NO_WATER) ? " BE" : "", (l & LOCK_COOLDOWN) ? " NGHI" : "",
           (l & LOCK_SOIL_FAULT) ? " DAT" : "", (l & LOCK_LOCAL) ? " TAY" : "",
           (l & LOCK_OVERHEAT) ? " NONG" : "");
  line(4, t);
}

static void drawNetwork() {
  char t[32], ip[20];
  if (wifiUp()) snprintf(t, sizeof t, "WiFi OK %ddBm", wifiRssi());
  else snprintf(t, sizeof t, "WiFi: dang ket noi");
  line(1, t);
  snprintf(t, sizeof t, "MQTT %s  dem %u", mqttUp() ? "OK" : "--", bufCount());
  line(2, t);
  netIp(ip, sizeof ip);
  snprintf(t, sizeof t, "IP %s", ip);
  line(3, t);
  snprintf(t, sizeof t, "%s v%s", deviceCode(), FW_VERSION);
  line(4, t);
}

static void draw() {
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x10_tf);
  if (pinEntry) {
    char t[16] = "PIN: ";
    for (uint8_t i = 0; i < pinLen; i++) strcat(t, "*");
    line(0, "Nhap PIN roi bam #");
    oled.drawHLine(0, 11, 128);
    line(2, t);
    line(4, "* = xoa");
  } else {
    drawHeader();
    if (page == 0) drawSensors();
    else if (page == 1) drawActuators();
    else drawNetwork();
  }
  if ((int32_t)(millis() - msgUntil) < 0) line(5, msg);
  else if (localActive() && !pinEntry) line(5, "1B 2Q 3Mode 4Den 0Ra");
  oled.sendBuffer();
}

void uiBegin() {
  oled.begin();
  oled.setFont(u8g2_font_6x10_tf);
  oled.clearBuffer();
  line(1, "Vuon uom - Node 1");
  line(3, "fw " FW_VERSION);
  oled.sendBuffer();
  keypad.setDebounceTime(30);
}

void uiLoop() {
  char k = keypad.getKey();
  if (k) handleKey(k);
  uint32_t now = millis();
  if (pinEntry && now - pinStartedAt > PIN_TIMEOUT_MS) {
    pinEntry = false;
    showMsg("Het thoi gian nhap");
  }
  if ((int32_t)(now - nextDraw) >= 0) {
    nextDraw = now + DRAW_PERIOD_MS;
    draw();
  }
}
