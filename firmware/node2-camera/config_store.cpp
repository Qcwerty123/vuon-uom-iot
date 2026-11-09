#include "config_store.h"
#include <Preferences.h>

const char* const FRAME_NAMES[FRAME_COUNT] = {"VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA"};
Config cfg;

static Preferences prefs;
static uint32_t seqE = 0;
static const uint32_t SEQ_SAVE_EVERY = 50;
static const uint32_t CFG_MAGIC = 0x4E320001;  // đổi khi đổi cấu trúc Config

struct StoredConfig {
  uint32_t magic;
  Config c;
};

static Config defaults() {
  Config c;
  c.version = 0;
  c.frameSize = 1;        // SVGA 800×600 — đủ để cắt lưới 3×3
  c.jpegQuality = 12;
  c.flash = FLASH_AUTO;
  c.captureIntervalMin = 30;
  c.warmupFrames = 2;
  return c;
}

void configBegin() {
  prefs.begin("node2", false);
  StoredConfig sc;
  size_t n = prefs.getBytes("cfg", &sc, sizeof(sc));
  cfg = (n == sizeof(sc) && sc.magic == CFG_MAGIC) ? sc.c : defaults();
  seqE = prefs.getULong("seqE", 0) + SEQ_SAVE_EVERY;  // giá trị lưu chậm tối đa 49 → cộng 50
  prefs.putULong("seqE", seqE);
}

void configSave() {
  StoredConfig sc{CFG_MAGIC, cfg};
  prefs.putBytes("cfg", &sc, sizeof(sc));
}

void configFactoryReset() {
  prefs.remove("cfg");
  cfg = defaults();
}

const char* flashModeName(uint8_t m) {
  return m == FLASH_ON ? "on" : (m == FLASH_OFF ? "off" : "auto");
}

void configPrint() {
  Serial.printf("config_version=%lu frame_size=%s jpeg_quality=%u flash=%s capture_interval_min=%u warmup_frames=%u\n",
                (unsigned long)cfg.version, FRAME_NAMES[cfg.frameSize], cfg.jpegQuality,
                flashModeName(cfg.flash), cfg.captureIntervalMin, cfg.warmupFrames);
}

static bool takeInt(JsonObjectConst p, const char* key, long lo, long hi, long& dst) {
  JsonVariantConst v = p[key];
  if (v.isNull()) return true;  // không gửi → giữ giá trị cũ
  if (!v.is<long>()) return false;
  long x = v.as<long>();
  if (x < lo || x > hi) return false;
  dst = x;
  return true;
}

const char* configParse(JsonObjectConst p, Config& out) {
  JsonVariantConst fs = p["frame_size"];
  if (!fs.isNull()) {
    const char* name = fs | "";
    int idx = -1;
    for (uint8_t i = 0; i < FRAME_COUNT; i++)
      if (strcmp(name, FRAME_NAMES[i]) == 0) idx = i;
    if (idx < 0) return "frame_size";
    out.frameSize = uint8_t(idx);
  }
  long q = out.jpegQuality, interval = out.captureIntervalMin, warm = out.warmupFrames;
  if (!takeInt(p, "jpeg_quality", 8, 30, q)) return "jpeg_quality";
  if (!takeInt(p, "capture_interval_min", 1, 1440, interval)) return "capture_interval_min";
  if (!takeInt(p, "warmup_frames", 0, 5, warm)) return "warmup_frames";
  out.jpegQuality = uint8_t(q);
  out.captureIntervalMin = uint16_t(interval);
  out.warmupFrames = uint8_t(warm);
  JsonVariantConst fl = p["flash"];
  if (!fl.isNull()) {
    const char* m = fl | "";
    if (strcmp(m, "on") == 0) out.flash = FLASH_ON;
    else if (strcmp(m, "off") == 0) out.flash = FLASH_OFF;
    else if (strcmp(m, "auto") == 0) out.flash = FLASH_AUTO;
    else return "flash";
  }
  return nullptr;
}

uint32_t nextEventSeq() {
  ++seqE;
  if (seqE % SEQ_SAVE_EVERY == 0) prefs.putULong("seqE", seqE);
  return seqE;
}
