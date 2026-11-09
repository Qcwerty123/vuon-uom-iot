#include "config_store.h"
#include <Preferences.h>

Config cfg;

static Preferences prefs;
static uint32_t seqT = 0, seqE = 0;
static const uint32_t SEQ_SAVE_EVERY = 50;
static const uint32_t CFG_MAGIC = 0x4E310002;  // đổi khi đổi cấu trúc Config (v1.1.0: thêm lamp_*)

struct StoredConfig {
  uint32_t magic;
  Config c;
};

static Config defaults() {
  Config c;
  c.version = 0;
  c.soilLow = 35;
  c.soilHigh = 55;
  c.pumpMaxS = 15;
  c.cooldownS = 120;
  c.tankMin = 15;
  c.tempHigh = 32;
  c.tempHyst = 2;
  c.humHigh = 90;
  c.humHyst = 5;
  c.telemetryIntervalS = 10;
  c.manualIgnoresCooldown = false;
  c.s1 = {3150, 1320};  // thay bằng số hiệu chuẩn thật qua config
  c.s2 = {3210, 1290};
  c.tankEmptyCm = 25.0;
  c.tankFullCm = 5.0;
  c.lampStartHour = 6;
  c.lampEndHour = 20;
  c.lampLuxLow = 800;
  c.lampHyst = 700;       // tắt khi lux ≥ 1500
  c.lampSelfLux = 300;    // thay bằng số đo thật qua config
  c.lampHoldS = 10;
  c.lampMinOnS = 30;      // chạy thật nên 300–600
  c.lampMinOffS = 30;
  c.lampOverrideMin = 60;
  return c;
}

static void loadSeq(const char* key, uint32_t& seq) {
  // Giá trị lưu có thể chậm tối đa 49 so với thực tế → cộng 50 để không lặp
  seq = prefs.getULong(key, 0) + SEQ_SAVE_EVERY;
  prefs.putULong(key, seq);
}

void configBegin() {
  prefs.begin("node1", false);
  StoredConfig sc;
  size_t n = prefs.getBytes("cfg", &sc, sizeof(sc));
  if (n == sizeof(sc) && sc.magic == CFG_MAGIC) {
    cfg = sc.c;
  } else {
    cfg = defaults();
  }
  loadSeq("seqT", seqT);
  loadSeq("seqE", seqE);
}

void configSave() {
  StoredConfig sc{CFG_MAGIC, cfg};
  prefs.putBytes("cfg", &sc, sizeof(sc));
}

void configFactoryReset() {
  prefs.remove("cfg");
  prefs.remove("modeAuto");
  cfg = defaults();
}

void configPrint() {
  Serial.printf("config_version=%lu soil_low=%.0f soil_high=%.0f pump_max_s=%u cooldown_s=%u tank_min=%.0f\n",
                (unsigned long)cfg.version, cfg.soilLow, cfg.soilHigh, cfg.pumpMaxS, cfg.cooldownS, cfg.tankMin);
  Serial.printf("temp_high=%.1f temp_hyst=%.1f hum_high=%.0f hum_hyst=%.0f telemetry_interval_s=%u manual_ignores_cooldown=%d\n",
                cfg.tempHigh, cfg.tempHyst, cfg.humHigh, cfg.humHyst, cfg.telemetryIntervalS, cfg.manualIgnoresCooldown);
  Serial.printf("soil_cal s1=%u/%u s2=%u/%u tank_cal empty=%.1f full=%.1f\n",
                cfg.s1.dry, cfg.s1.wet, cfg.s2.dry, cfg.s2.wet, cfg.tankEmptyCm, cfg.tankFullCm);
  Serial.printf("lamp %02u-%02uh lux_low=%u hyst=%u (tat >= %u) self=%u hold=%us min_on=%us min_off=%us override=%umin\n",
                cfg.lampStartHour, cfg.lampEndHour, cfg.lampLuxLow, cfg.lampHyst,
                cfg.lampLuxLow + cfg.lampHyst, cfg.lampSelfLux, cfg.lampHoldS,
                cfg.lampMinOnS, cfg.lampMinOffS, cfg.lampOverrideMin);
}

// ---------- kiểm tra cấu hình nhận qua MQTT ----------

static bool takeFloat(JsonObjectConst p, const char* key, float lo, float hi, float& dst, const char*& err) {
  JsonVariantConst v = p[key];
  if (v.isNull()) return true;  // không gửi khóa này → giữ giá trị cũ
  if (!v.is<float>() && !v.is<int>()) { err = key; return false; }
  float x = v.as<float>();
  if (x < lo || x > hi) { err = key; return false; }
  dst = x;
  return true;
}

static bool takeU16(JsonObjectConst p, const char* key, long lo, long hi, uint16_t& dst, const char*& err) {
  JsonVariantConst v = p[key];
  if (v.isNull()) return true;
  if (!v.is<long>()) { err = key; return false; }
  long x = v.as<long>();
  if (x < lo || x > hi) { err = key; return false; }
  dst = (uint16_t)x;
  return true;
}

static bool takeCal(JsonObjectConst p, const char* key, SoilCal& dst, const char*& err) {
  JsonVariantConst v = p[key];
  if (v.isNull()) return true;
  JsonObjectConst o = v.as<JsonObjectConst>();
  if (o.isNull() || !o["dry"].is<long>() || !o["wet"].is<long>()) { err = key; return false; }
  long dry = o["dry"], wet = o["wet"];
  if (dry < 0 || dry > 4095 || wet < 0 || wet > 4095 || dry - wet < 200) { err = key; return false; }
  dst = {(uint16_t)dry, (uint16_t)wet};
  return true;
}

const char* configParse(JsonObjectConst p, Config& out) {
  const char* err = nullptr;
  if (!takeFloat(p, "soil_low", 0, 100, out.soilLow, err)) return err;
  if (!takeFloat(p, "soil_high", 0, 100, out.soilHigh, err)) return err;
  if (!takeU16(p, "pump_max_s", 1, 60, out.pumpMaxS, err)) return err;
  if (!takeU16(p, "cooldown_s", 0, 3600, out.cooldownS, err)) return err;
  if (!takeFloat(p, "tank_min", 0, 100, out.tankMin, err)) return err;
  if (!takeFloat(p, "temp_high", -10, 60, out.tempHigh, err)) return err;
  if (!takeFloat(p, "temp_hyst", 0.5, 10, out.tempHyst, err)) return err;
  if (!takeFloat(p, "hum_high", 0, 100, out.humHigh, err)) return err;
  if (!takeFloat(p, "hum_hyst", 1, 20, out.humHyst, err)) return err;
  if (!takeU16(p, "telemetry_interval_s", 2, 300, out.telemetryIntervalS, err)) return err;
  JsonVariantConst mic = p["manual_ignores_cooldown"];
  if (!mic.isNull()) {
    if (!mic.is<bool>()) return "manual_ignores_cooldown";
    out.manualIgnoresCooldown = mic.as<bool>();
  }
  JsonVariantConst sc = p["soil_cal"];
  if (!sc.isNull()) {
    JsonObjectConst o = sc.as<JsonObjectConst>();
    if (o.isNull()) return "soil_cal";
    if (!takeCal(o, "s1", out.s1, err)) return "soil_cal.s1";
    if (!takeCal(o, "s2", out.s2, err)) return "soil_cal.s2";
  }
  JsonVariantConst tc = p["tank_cal"];
  if (!tc.isNull()) {
    JsonObjectConst o = tc.as<JsonObjectConst>();
    if (o.isNull()) return "tank_cal";
    if (!takeFloat(o, "empty_cm", 2, 400, out.tankEmptyCm, err)) return "tank_cal.empty_cm";
    if (!takeFloat(o, "full_cm", 2, 400, out.tankFullCm, err)) return "tank_cal.full_cm";
  }
  // Chiếu sáng bổ sung (§6.11)
  uint16_t sh = out.lampStartHour, eh = out.lampEndHour;
  if (!takeU16(p, "lamp_start_hour", 0, 23, sh, err)) return err;
  if (!takeU16(p, "lamp_end_hour", 1, 24, eh, err)) return err;
  out.lampStartHour = uint8_t(sh);
  out.lampEndHour = uint8_t(eh);
  if (!takeU16(p, "lamp_lux_low", 0, 65535, out.lampLuxLow, err)) return err;
  if (!takeU16(p, "lamp_hyst", 1, 65535, out.lampHyst, err)) return err;
  if (!takeU16(p, "lamp_self_lux", 0, 5000, out.lampSelfLux, err)) return err;
  if (!takeU16(p, "lamp_hold_s", 2, 600, out.lampHoldS, err)) return err;
  if (!takeU16(p, "lamp_min_on_s", 10, 3600, out.lampMinOnS, err)) return err;
  if (!takeU16(p, "lamp_min_off_s", 10, 3600, out.lampMinOffS, err)) return err;
  if (!takeU16(p, "lamp_override_min", 1, 240, out.lampOverrideMin, err)) return err;
  // Ràng buộc chéo giữa các khóa
  if (out.lampEndHour <= out.lampStartHour) return "lamp_end_hour";
  // Phần sáng do chính đèn tạo ra không được đủ để vượt ngưỡng tắt → đèn không tự bật/tắt liên tục
  if (uint32_t(out.lampHyst) <= uint32_t(out.lampSelfLux) + 200) return "lamp_hyst";
  if (out.soilLow >= out.soilHigh) return "soil_low";
  if (out.tankEmptyCm - out.tankFullCm < 2) return "tank_cal";
  return nullptr;
}

// ---------- seq ----------

static uint32_t bump(const char* key, uint32_t& seq) {
  ++seq;
  if (seq % SEQ_SAVE_EVERY == 0) prefs.putULong(key, seq);
  return seq;
}
uint32_t nextTelemetrySeq() { return bump("seqT", seqT); }
uint32_t nextEventSeq() { return bump("seqE", seqE); }

bool savedModeIsAuto() { return prefs.getBool("modeAuto", true); }
void saveModeIsAuto(bool isAuto) { prefs.putBool("modeAuto", isAuto); }
