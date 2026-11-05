#include "control.h"
#include "config_store.h"
#include "sensors.h"
#include "protocol.h"
#include <esp_timer.h>

static const uint32_t EVAL_PERIOD_MS = 2000;
static const uint32_t LOCAL_TIMEOUT_MS = 60000;
static const uint32_t FAN_OVERRIDE_MS = 5UL * 60 * 1000;  // lệnh quạt tay trong AUTO giữ 5 phút
static const float TANK_HYST = 3;                          // %, chống bật/tắt tank_low liên tục

static bool pumpOn = false, fanOn = false;
static Source pumpSrc = Source::AUTO, fanSrc = Source::AUTO;
static uint32_t pumpStartMs = 0, pumpPlannedMs = 0, pumpOffMs = 0;
static bool pumpEverRan = false;
static uint32_t fanOverrideUntil = 0;
static bool fanOverride = false;
static bool baseAuto = true;
static bool local = false;
static uint32_t localUntil = 0;
static bool tankLow = false;
static uint32_t nextEval = 0;

// Timer phần cứng cắt bơm đúng hạn, kể cả khi vòng lặp chính đang bị chặn
// (ví dụ lúc đang chờ kết nối MQTT). Vòng lặp sẽ đồng bộ lại trạng thái + gửi event.
static esp_timer_handle_t pumpTimer = nullptr;
static volatile bool pumpCutByTimer = false;

static void relayWrite(int pin, bool on) {
  bool level = RELAY_ACTIVE_HIGH ? on : !on;
  digitalWrite(pin, level ? HIGH : LOW);
}

void controlLoadMode() { baseAuto = savedModeIsAuto(); }

static void onPumpTimer(void*) {
  relayWrite(pins::RELAY_PUMP, false);
  pumpCutByTimer = true;
}

void controlBegin() {
  // Ghi mức TẮT trước khi đặt OUTPUT để relay không nháy lúc khởi động
  const int relays[] = {pins::RELAY_PUMP, pins::RELAY_FAN, pins::RELAY_SPARE};
  for (int p : relays) {
    relayWrite(p, false);
    pinMode(p, OUTPUT);
    relayWrite(p, false);
  }
  esp_timer_create_args_t args = {};
  args.callback = &onPumpTimer;
  args.name = "pump";
  esp_timer_create(&args, &pumpTimer);
}

// ---------- bơm ----------

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
  pumpStartMs = millis();
  pumpPlannedMs = uint32_t(seconds) * 1000UL;
  uint32_t hardCapMs = uint32_t(cfg.pumpMaxS) * 1000UL;
  uint32_t capMs = pumpPlannedMs < hardCapMs ? pumpPlannedMs : hardCapMs;
  esp_timer_stop(pumpTimer);  // bỏ hẹn giờ cũ nếu bơm đang chạy
  pumpCutByTimer = false;
  esp_timer_start_once(pumpTimer, uint64_t(capMs) * 1000ULL);
  relayWrite(pins::RELAY_PUMP, true);
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
  relayWrite(pins::RELAY_PUMP, false);
  pumpEverRan = true;
  pumpOffMs = millis();
  float ran = (pumpOffMs - pumpStartMs) / 1000.0f;
  emitEvent("pump_off", [by, ran, reason](JsonObject d) {
    d["source"] = sourceName(by);
    d["duration_s"] = round1(ran);
    d["reason"] = reason;
  });
  Serial.printf("[control] BOM TAT sau %.1fs (%s)\n", ran, reason);
}

// ---------- quạt ----------

static void fanSet(bool on, Source src) {
  if (fanOn == on) return;
  fanOn = on;
  fanSrc = src;
  relayWrite(pins::RELAY_FAN, on);
  emitEvent(on ? "fan_on" : "fan_off", [src](JsonObject d) { d["source"] = sourceName(src); });
  Serial.printf("[control] QUAT %s (%s)\n", on ? "BAT" : "TAT", sourceName(src));
}

// ---------- vòng lặp ----------

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

static void checkPumpStop() {
  if (!pumpOn) return;
  const Readings& r = sensorReadings();
  uint32_t elapsed = millis() - pumpStartMs;
  uint32_t hardCap = uint32_t(cfg.pumpMaxS) * 1000UL;
  if (elapsed >= pumpPlannedMs || elapsed >= hardCap) pumpStop("done", pumpSrc);
  else if (!r.tank.ok) pumpStop("tank_sensor_fault", Source::AUTO);
  else if (tankLow) pumpStop("no_water", Source::AUTO);
  else if (pumpSrc == Source::AUTO && r.soil.ok && r.soil.v >= cfg.soilHigh) pumpStop("soil_high", Source::AUTO);
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
    if (pumpOn) pumpStop("done", pumpSrc);
  }
  if (sensorsHaveData()) updateTankState();
  checkPumpStop();
  if ((int32_t)(now - nextEval) >= 0) {
    nextEval = now + EVAL_PERIOD_MS;
    if (baseAuto && !local && sensorsHaveData()) autoEvaluate();
  }
}

// ---------- lệnh ----------

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
  if (is("set_mode")) {
    const char* m = params["mode"] | "";
    if (strcmp(m, "AUTO") != 0 && strcmp(m, "MANUAL") != 0) { detail["field"] = "mode"; return "invalid"; }
    baseAuto = (strcmp(m, "AUTO") == 0);
    saveModeIsAuto(baseAuto);
    if (!baseAuto && pumpOn && pumpSrc == Source::AUTO) pumpStop("mode_manual", src);
    if (baseAuto) fanOverride = false;
    detail["mode"] = m;
    return "executed";
  }
  return "unsupported";
}

// ---------- truy vấn trạng thái ----------

bool pumpIsOn() { return pumpOn; }
bool fanIsOn() { return fanOn; }
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
  return l;
}

void locksToJson(uint8_t l, JsonArray arr) {
  if (l & LOCK_NO_WATER) arr.add("no_water");
  if (l & LOCK_COOLDOWN) arr.add("cooldown");
  if (l & LOCK_SOIL_FAULT) arr.add("soil_fault");
  if (l & LOCK_LOCAL) arr.add("local");
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
}
