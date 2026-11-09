#include "control.h"
#include "config_store.h"
#include "sensors.h"
#include "protocol.h"
#include "net.h"
#include <esp_timer.h>

static const uint32_t EVAL_PERIOD_MS = 2000;
static const uint32_t LOCAL_TIMEOUT_MS = 60000;
static const uint32_t FAN_OVERRIDE_MS = 5UL * 60 * 1000;  // lệnh quạt tay trong AUTO giữ 5 phút
static const float TANK_HYST = 3;                          // %, chống bật/tắt tank_low liên tục
static const float OVERHEAT_MARGIN = 3;                    // khóa nhiệt khi air_temp ≥ temp_high + 3 (§6.11)
static const uint32_t RELAY_STAGGER_MS = 400;              // khoảng cách tối thiểu giữa 2 lần ĐÓNG relay

// ======================================================================
// Lớp relay: mọi lần BẬT đi qua hàng đợi, cách nhau ≥ 400 ms để dòng khởi động
// không cộng dồn làm sụt áp thanh 5 V. TẮT luôn chạy ngay (§6.6 mục 6, §6.11).
// ======================================================================
enum RelayId : uint8_t { R_PUMP = 0, R_FAN = 1, R_LAMP = 2, R_COUNT };
static const int RELAY_PIN[R_COUNT] = {pins::RELAY_PUMP, pins::RELAY_FAN, pins::RELAY_LAMP};
static const char* const RELAY_NAME[R_COUNT] = {"bom", "quat", "den"};
static bool relayWant[R_COUNT] = {false, false, false};
static bool relayClosed[R_COUNT] = {false, false, false};
static uint32_t relayWantAt[R_COUNT] = {0, 0, 0};
static uint32_t lastCloseAt = 0;
static bool everClosed = false;

static void relayWrite(int pin, bool on) {
  bool level = RELAY_ACTIVE_HIGH ? on : !on;
  digitalWrite(pin, level ? HIGH : LOW);
}

static void onRelayClosed(RelayId r);  // khai báo trước, định nghĩa ở phần bơm

static void relayRequest(RelayId r, bool on) {
  if (on) {
    if (!relayWant[r]) relayWantAt[r] = millis();
    relayWant[r] = true;
    return;
  }
  relayWant[r] = false;             // tắt: chạy ngay, hủy luôn yêu cầu bật đang chờ
  if (relayClosed[r]) {
    relayWrite(RELAY_PIN[r], false);
    relayClosed[r] = false;
  }
}

static void serviceRelays() {
  uint32_t now = millis();
  if (everClosed && now - lastCloseAt < RELAY_STAGGER_MS) return;
  int pick = -1;                    // yêu cầu bật chờ lâu nhất được đóng trước
  for (int r = 0; r < R_COUNT; r++) {
    if (relayWant[r] && !relayClosed[r] && (pick < 0 || (int32_t)(relayWantAt[r] - relayWantAt[pick]) < 0)) pick = r;
  }
  if (pick < 0) return;
  relayWrite(RELAY_PIN[pick], true);
  relayClosed[pick] = true;
  lastCloseAt = now;
  everClosed = true;
  Serial.printf("[relay] dong %s (t=%lums)\n", RELAY_NAME[pick], (unsigned long)now);
  onRelayClosed(RelayId(pick));
}

// ======================================================================
// Trạng thái chung
// ======================================================================
static bool baseAuto = true;
static bool local = false;
static uint32_t localUntil = 0;
static bool tankLow = false;
static bool overheat = false;
static uint32_t nextEval = 0;

void controlLoadMode() { baseAuto = savedModeIsAuto(); }

// ======================================================================
// Bơm. Thời gian bơm và timer cắt bơm tính từ lúc relay THỰC SỰ đóng.
// ======================================================================
static bool pumpOn = false;             // đã yêu cầu bơm (có thể đang chờ lệch pha)
static Source pumpSrc = Source::AUTO;
static bool pumpStarted = false;        // relay bơm đã đóng
static uint32_t pumpStartMs = 0, pumpPlannedMs = 0, pumpOffMs = 0;
static bool pumpEverRan = false;

// Timer phần cứng cắt bơm đúng hạn, kể cả khi vòng lặp chính đang bị chặn
// (ví dụ lúc đang chờ kết nối MQTT). Vòng lặp sẽ đồng bộ lại trạng thái + gửi event.
static esp_timer_handle_t pumpTimer = nullptr;
static volatile bool pumpCutByTimer = false;

static void onPumpTimer(void*) {
  relayWrite(pins::RELAY_PUMP, false);
  pumpCutByTimer = true;
}

static void armPumpTimer() {
  uint32_t hardCapMs = uint32_t(cfg.pumpMaxS) * 1000UL;
  uint32_t capMs = pumpPlannedMs < hardCapMs ? pumpPlannedMs : hardCapMs;
  esp_timer_stop(pumpTimer);
  pumpCutByTimer = false;
  esp_timer_start_once(pumpTimer, uint64_t(capMs) * 1000ULL);
}

static void onRelayClosed(RelayId r) {
  if (r == R_PUMP && pumpOn) {
    pumpStarted = true;
    pumpStartMs = millis();
    armPumpTimer();
  }
}

void controlBegin() {
  // Ghi mức TẮT trước khi đặt OUTPUT để relay không nháy lúc khởi động
  for (int r = 0; r < R_COUNT; r++) {
    relayWrite(RELAY_PIN[r], false);
    pinMode(RELAY_PIN[r], OUTPUT);
    relayWrite(RELAY_PIN[r], false);
  }
  esp_timer_create_args_t args = {};
  args.callback = &onPumpTimer;
  args.name = "pump";
  esp_timer_create(&args, &pumpTimer);
}

static bool cooldownActive() {
  return pumpEverRan && (millis() - pumpOffMs) < uint32_t(cfg.cooldownS) * 1000UL;
}

static const char* pumpBlockReason(Source src) {
  const Readings& r = sensorReadings();
  if (!r.tank.ok) return "blocked_sensor_fault";   // không biết mực nước → không bơm
  if (tankLow) return "blocked_no_water";
  if (cooldownActive() && !(src != Source::AUTO && cfg.manualIgnoresCooldown)) return "blocked_cooldown";
  return nullptr;
}

static void pumpStart(uint16_t seconds, Source src) {
  bool wasOn = pumpOn;
  pumpOn = true;
  pumpSrc = src;
  pumpPlannedMs = uint32_t(seconds) * 1000UL;
  if (pumpStarted) {                // đang chạy: đặt lại thời gian từ bây giờ
    pumpStartMs = millis();
    armPumpTimer();
  } else {
    relayRequest(R_PUMP, true);     // đóng relay khi tới lượt (lệch pha)
  }
  if (!wasOn) {
    emitEvent("pump_on", [src, seconds](JsonObject d) {
      d["source"] = sourceName(src);
      d["duration_s"] = seconds;
    });
  }
  Serial.printf("[control] BOM BAT %us (%s)\n", seconds, sourceName(src));
}

static void pumpStop(const char* reason, Source by) {
  if (!pumpOn) return;
  pumpOn = false;
  esp_timer_stop(pumpTimer);
  relayRequest(R_PUMP, false);
  float ran = pumpStarted ? (millis() - pumpStartMs) / 1000.0f : 0;
  if (pumpStarted) {
    pumpEverRan = true;
    pumpOffMs = millis();
  }
  pumpStarted = false;
  emitEvent("pump_off", [by, ran, reason](JsonObject d) {
    d["source"] = sourceName(by);
    d["duration_s"] = round1(ran);
    d["reason"] = reason;
  });
  Serial.printf("[control] BOM TAT sau %.1fs (%s)\n", ran, reason);
}

static void checkPumpStop() {
  if (!pumpOn) return;
  const Readings& r = sensorReadings();
  if (!r.tank.ok) { pumpStop("tank_sensor_fault", Source::AUTO); return; }
  if (tankLow) { pumpStop("no_water", Source::AUTO); return; }
  if (pumpSrc == Source::AUTO && r.soil.ok && r.soil.v >= cfg.soilHigh) { pumpStop("soil_high", Source::AUTO); return; }
  if (!pumpStarted) return;         // chưa tới lượt đóng relay
  uint32_t elapsed = millis() - pumpStartMs;
  uint32_t hardCap = uint32_t(cfg.pumpMaxS) * 1000UL;
  if (elapsed >= pumpPlannedMs || elapsed >= hardCap) pumpStop("done", pumpSrc);
}

// ======================================================================
// Quạt
// ======================================================================
static bool fanOn = false;
static uint32_t fanOverrideUntil = 0;
static bool fanOverride = false;

static void fanSet(bool on, Source src) {
  if (fanOn == on) return;
  fanOn = on;
  relayRequest(R_FAN, on);
  emitEvent(on ? "fan_on" : "fan_off", [src](JsonObject d) { d["source"] = sourceName(src); });
  Serial.printf("[control] QUAT %s (%s)\n", on ? "BAT" : "TAT", sourceName(src));
}

// ======================================================================
// Đèn chiếu sáng bổ sung (§6.11)
// ======================================================================
static bool lampOn = false;
static bool lampEverChanged = false;
static uint32_t lampChangedAt = 0;
static uint32_t lampPendingSince = 0;   // 0 = không có điều kiện đổi trạng thái đang đếm
static bool lampOverride = false;       // lệnh tay đang giữ hiệu lực (chỉ khi AUTO)
static uint32_t lampOverrideUntil = 0;

static void lampSet(bool on, Source src, const char* reason) {
  lampPendingSince = 0;
  if (lampOn == on) return;
  lampOn = on;
  lampEverChanged = true;
  lampChangedAt = millis();
  relayRequest(R_LAMP, on);
  emitEvent(on ? "lamp_on" : "lamp_off", [src, reason](JsonObject d) {
    d["source"] = sourceName(src);
    d["reason"] = reason;
  });
  Serial.printf("[control] DEN %s (%s, %s)\n", on ? "BAT" : "TAT", sourceName(src), reason);
}

static int localHour() {
  uint64_t ms = nowMs();
  if (ms == 0) return -1;  // chưa có giờ NTP
  return int((ms / 1000 + TZ_OFFSET_H * 3600ULL) / 3600 % 24);
}

static bool inLampWindow(int hour) {
  return hour >= cfg.lampStartHour && hour < cfg.lampEndHour;
}

// Debounce + thời gian giữ cho quyết định theo lux (dòng 5–6 bảng §6.11)
static void lampDebounced(bool want, const char* reason) {
  if (want == lampOn) {
    lampPendingSince = 0;
    return;
  }
  uint32_t now = millis();
  uint32_t minHoldMs = uint32_t(lampOn ? cfg.lampMinOnS : cfg.lampMinOffS) * 1000UL;
  if (lampEverChanged && now - lampChangedAt < minHoldMs) {
    lampPendingSince = 0;           // còn trong thời gian giữ: chưa bắt đầu đếm
    return;
  }
  if (lampPendingSince == 0) {
    lampPendingSince = now;
    return;
  }
  if (now - lampPendingSince >= uint32_t(cfg.lampHoldS) * 1000UL) lampSet(want, Source::AUTO, reason);
}

static void updateOverheat() {
  const Readings& r = sensorReadings();
  if (!r.airTemp.ok) return;                     // không có số đo → giữ nguyên trạng thái khóa
  float on = cfg.tempHigh + OVERHEAT_MARGIN;
  if (!overheat && r.airTemp.v >= on) {
    overheat = true;
    Serial.println("[control] KHOA NHIET: qua nong");
  } else if (overheat && r.airTemp.v <= on - cfg.tempHyst) {
    overheat = false;
    Serial.println("[control] het qua nong");
  }
}

static void lampEvaluate() {
  // Khóa nhiệt: áp dụng ở MỌI chế độ, tắt ngay
  if (overheat) {
    if (lampOn) lampSet(false, Source::AUTO, "overheat");
    lampOverride = false;
    return;
  }
  bool overrideEnded = false;
  if (lampOverride && (int32_t)(millis() - lampOverrideUntil) >= 0) {
    lampOverride = false;
    overrideEnded = true;
  }
  if (!baseAuto || local) return;   // MANUAL / LOCAL: đèn chỉ chạy theo lệnh
  if (lampOverride) return;         // lệnh tay còn hiệu lực

  int hour = localHour();
  if (hour < 0) return;             // 1. chưa có giờ NTP: không tự bật, không tự tắt
  if (!inLampWindow(hour)) {        // 2. ngoài khung giờ: tắt ngay
    if (lampOn) lampSet(false, Source::AUTO, overrideEnded ? "override_end" : "window_end");
    lampPendingSince = 0;
    return;
  }
  const Readings& r = sensorReadings();
  if (!r.light.ok) {                // 4. BH1750 lỗi: bật theo lịch suốt khung giờ
    if (!lampOn) lampSet(true, Source::AUTO, "sensor_fallback");
    return;
  }
  bool want;
  const char* reason;
  if (!lampOn) {                    // 5. đang tắt: bật khi thiếu sáng
    want = r.light.v < cfg.lampLuxLow;
    reason = "low_light";
  } else {                          // 6. đang bật: chỉ tắt khi tổng lux vượt hẳn ngưỡng
    want = r.light.v < float(cfg.lampLuxLow) + float(cfg.lampHyst);
    reason = "bright";
  }
  if (overrideEnded && want != lampOn) {
    lampSet(want, Source::AUTO, "override_end");   // hết lệnh tay: trả về AUTO ngay
    return;
  }
  lampDebounced(want, reason);
}

// ======================================================================
// Vòng lặp
// ======================================================================
static void updateTankState() {
  const Readings& r = sensorReadings();
  if (!r.tank.ok) return;
  if (!tankLow && r.tank.v < cfg.tankMin) {
    tankLow = true;
    float v = r.tank.v;
    emitEvent("tank_low", [v](JsonObject d) { d["tank"] = round1(v); });
  } else if (tankLow && r.tank.v >= cfg.tankMin + TANK_HYST) {
    tankLow = false;
    float v = r.tank.v;
    emitEvent("tank_ok", [v](JsonObject d) { d["tank"] = round1(v); });
  }
}

static void autoEvaluate() {
  const Readings& r = sensorReadings();
  // Tưới
  if (!pumpOn && r.soil.ok && r.soil.v < cfg.soilLow && pumpBlockReason(Source::AUTO) == nullptr) {
    pumpStart(cfg.pumpMaxS, Source::AUTO);
  }
  // Thông gió (có trễ)
  if (fanOverride && (int32_t)(millis() - fanOverrideUntil) >= 0) fanOverride = false;
  if (fanOverride) return;
  bool tOk = r.airTemp.ok, hOk = r.airHum.ok;
  if (!tOk && !hOk) return;  // không có số liệu → giữ nguyên
  bool wantOn = (tOk && r.airTemp.v >= cfg.tempHigh) || (hOk && r.airHum.v >= cfg.humHigh);
  bool wantOff = (!tOk || r.airTemp.v <= cfg.tempHigh - cfg.tempHyst) &&
                 (!hOk || r.airHum.v <= cfg.humHigh - cfg.humHyst);
  if (wantOn) fanSet(true, Source::AUTO);
  else if (wantOff) fanSet(false, Source::AUTO);
}

void controlLoop() {
  uint32_t now = millis();
  if (local && (int32_t)(now - localUntil) >= 0) {
    localExit();
    Serial.println("[control] het 60 s, thoat LOCAL");
  }
  if (pumpCutByTimer) {
    pumpCutByTimer = false;
    relayClosed[R_PUMP] = false;    // timer đã cắt relay
    if (pumpOn) pumpStop("done", pumpSrc);
  }
  if (sensorsHaveData()) updateTankState();
  checkPumpStop();
  if ((int32_t)(now - nextEval) >= 0) {
    nextEval = now + EVAL_PERIOD_MS;
    if (sensorsHaveData()) {
      updateOverheat();
      if (baseAuto && !local) autoEvaluate();
      lampEvaluate();               // tự kiểm tra chế độ bên trong (khóa nhiệt chạy ở mọi chế độ)
    }
  }
  serviceRelays();
}

// ======================================================================
// Lệnh
// ======================================================================
const char* controlCommand(const char* action, JsonObjectConst params, JsonObject detail, Source src) {
  auto is = [action](const char* x) { return strcmp(action, x) == 0; };
  if (is("pump_on")) {
    JsonVariantConst dv = params["duration_s"];
    if (!dv.is<long>() || dv.as<long>() < 1) { detail["field"] = "duration_s"; return "invalid"; }
    const char* blocked = pumpBlockReason(src);
    if (blocked) return blocked;
    long want = dv.as<long>();
    bool capped = want > cfg.pumpMaxS;
    uint16_t sec = capped ? cfg.pumpMaxS : uint16_t(want);
    pumpStart(sec, src);
    detail["duration_s"] = sec;
    return capped ? "duration_capped" : "executed";
  }
  if (is("pump_off")) {
    pumpStop("command", src);
    return "executed";
  }
  if (is("fan_on") || is("fan_off")) {
    fanSet(is("fan_on"), src);
    if (baseAuto && src == Source::REMOTE) {
      fanOverride = true;
      fanOverrideUntil = millis() + FAN_OVERRIDE_MS;
      detail["override_s"] = FAN_OVERRIDE_MS / 1000;
    }
    return "executed";
  }
  if (is("lamp_on") || is("lamp_off")) {
    bool on = is("lamp_on");
    long minutes = cfg.lampOverrideMin;
    JsonVariantConst dm = params["duration_min"];
    if (on && !dm.isNull()) {
      if (!dm.is<long>() || dm.as<long>() < 1 || dm.as<long>() > cfg.lampOverrideMin) {
        detail["field"] = "duration_min";
        return "invalid";
      }
      minutes = dm.as<long>();
    }
    if (on && overheat) return "blocked_overheat";
    lampSet(on, src, "command");
    if (baseAuto) {                 // AUTO: giữ lệnh tay một thời gian rồi trả về tự động
      lampOverride = true;
      lampOverrideUntil = millis() + uint32_t(minutes) * 60000UL;
      detail["override_min"] = minutes;
    }
    return "executed";
  }
  if (is("set_mode")) {
    const char* m = params["mode"] | "";
    if (strcmp(m, "AUTO") != 0 && strcmp(m, "MANUAL") != 0) { detail["field"] = "mode"; return "invalid"; }
    baseAuto = (strcmp(m, "AUTO") == 0);
    saveModeIsAuto(baseAuto);
    if (!baseAuto && pumpOn && pumpSrc == Source::AUTO) pumpStop("mode_manual", src);
    if (baseAuto) {
      fanOverride = false;
      lampOverride = false;
    }
    detail["mode"] = m;
    return "executed";
  }
  return "unsupported";
}

// ======================================================================
// Truy vấn trạng thái
// ======================================================================
bool pumpIsOn() { return pumpOn; }
bool fanIsOn() { return fanOn; }
bool lampIsOn() { return lampOn; }
bool overheatActive() { return overheat; }
bool modeIsAuto() { return baseAuto; }
uint8_t modeCode() { return local ? 2 : (baseAuto ? 0 : 1); }
const char* modeName() { return local ? "LOCAL" : (baseAuto ? "AUTO" : "MANUAL"); }

uint8_t currentLocks() {
  const Readings& r = sensorReadings();
  uint8_t l = 0;
  if (tankLow || !r.tank.ok) l |= LOCK_NO_WATER;
  if (cooldownActive()) l |= LOCK_COOLDOWN;
  if (sensorsHaveData() && !r.soil.ok) l |= LOCK_SOIL_FAULT;
  if (local) l |= LOCK_LOCAL;
  if (overheat) l |= LOCK_OVERHEAT;
  return l;
}

void locksToJson(uint8_t l, JsonArray arr) {
  if (l & LOCK_NO_WATER) arr.add("no_water");
  if (l & LOCK_COOLDOWN) arr.add("cooldown");
  if (l & LOCK_SOIL_FAULT) arr.add("soil_fault");
  if (l & LOCK_LOCAL) arr.add("local");
  if (l & LOCK_OVERHEAT) arr.add("overheat");
}

void localEnter() {
  local = true;
  localUntil = millis() + LOCAL_TIMEOUT_MS;
}
void localExit() { local = false; }
void localTouch() {
  if (local) localUntil = millis() + LOCAL_TIMEOUT_MS;
}
bool localActive() { return local; }
uint32_t localRemainingS() {
  if (!local) return 0;
  int32_t ms = int32_t(localUntil - millis());
  return ms > 0 ? (ms + 999) / 1000 : 0;
}

void controlAllOff() {
  pumpStop("shutdown", Source::AUTO);
  fanSet(false, Source::AUTO);
  lampSet(false, Source::AUTO, "shutdown");
}

void controlPrint() {
  int h = localHour();
  Serial.printf("den=%s gio=%d khung=%02u-%02u override=%s qua_nong=%s | relay dong: bom=%d quat=%d den=%d\n",
                lampOn ? "BAT" : "tat", h, cfg.lampStartHour, cfg.lampEndHour,
                lampOverride ? "co" : "khong", overheat ? "CO" : "khong",
                relayClosed[R_PUMP], relayClosed[R_FAN], relayClosed[R_LAMP]);
}
