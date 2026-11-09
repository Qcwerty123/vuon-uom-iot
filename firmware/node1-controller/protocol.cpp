#include "protocol.h"
#include <esp_system.h>
#include "config_store.h"
#include "sensors.h"
#include "control.h"
#include "buffer.h"
#include "net.h"

static const uint32_t STATUS_PERIOD_MS = 30000;
static const uint32_t DRAIN_GAP_MS = 200;     // gửi bù tối đa 5 bản tin/giây
static const uint8_t EVENT_CAPACITY = 30;
static const uint8_t DEDUP_CAPACITY = 20;

static uint32_t nextTelemetry = 0, nextStatus = 0, nextDrain = 0, rebootAt = 0;
static bool statusPending = false;
static char out[1024];

// ---------- thời gian: suy ra ts cho bản ghi tạo lúc chưa có NTP ----------
static uint64_t fixTs(uint64_t ts, bool synced, uint32_t ms, bool& nowSynced) {
  nowSynced = true;
  if (synced) return ts;
  if (timeSynced()) return nowMs() - (millis() - ms);
  nowSynced = false;
  return 0;
}

// ---------- event ----------
struct EventRec {
  char type[20];
  char detail[160];
  uint32_t seq;
  uint64_t ts;
  uint32_t ms;
  bool synced;
};
static EventRec events[EVENT_CAPACITY];
static uint8_t evHead = 0, evCount = 0;

void emitEvent(const char* type, DetailFn fill) {
  EventRec& e = events[evHead];
  snprintf(e.type, sizeof e.type, "%s", type);
  JsonDocument d;
  JsonObject o = d.to<JsonObject>();
  if (fill) fill(o);
  serializeJson(d, e.detail, sizeof e.detail);
  e.seq = nextEventSeq();
  e.ts = nowMs();
  e.ms = millis();
  e.synced = e.ts != 0;
  evHead = (evHead + 1) % EVENT_CAPACITY;
  if (evCount < EVENT_CAPACITY) evCount++;  // đầy thì mất event cũ nhất
}

static void flushEvents() {
  for (uint8_t k = 0; k < 5 && evCount > 0 && mqttUp(); k++) {
    EventRec& e = events[(evHead + EVENT_CAPACITY - evCount) % EVENT_CAPACITY];
    bool syn;
    JsonDocument doc;
    doc["v"] = 1;
    doc["device_id"] = deviceCode();
    doc["ts"] = fixTs(e.ts, e.synced, e.ms, syn);
    doc["seq"] = e.seq;
    doc["type"] = e.type;
    doc["detail"] = serialized(e.detail);
    serializeJson(doc, out, sizeof out);
    if (!netPublish("event", out)) break;
    evCount--;
  }
}

// ---------- telemetry ----------
static void addMetric(JsonObject data, const char* key, const Metric& m, const char* unit) {
  JsonObject o = data[key].to<JsonObject>();
  if (m.ok) o["v"] = round1(m.v);
  else o["v"] = nullptr;
  o["u"] = unit;
  o["ok"] = m.ok;
}

static bool publishTelemetry(const TelemetryRec& rec, bool buffered) {
  static const char* MODE_NAMES[] = {"AUTO", "MANUAL", "LOCAL"};
  bool syn;
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = deviceCode();
  doc["seq"] = rec.seq;
  doc["ts"] = fixTs(rec.ts, rec.synced, rec.ms, syn);
  doc["time_synced"] = syn;
  doc["buffered"] = buffered;
  JsonObject data = doc["data"].to<JsonObject>();
  addMetric(data, "soil1", rec.r.soil1, "%");
  addMetric(data, "soil2", rec.r.soil2, "%");
  addMetric(data, "soil", rec.r.soil, "%");
  addMetric(data, "air_temp", rec.r.airTemp, "C");
  addMetric(data, "air_hum", rec.r.airHum, "%RH");
  addMetric(data, "light", rec.r.light, "lux");
  addMetric(data, "tank", rec.r.tank, "%");
  if (rec.r.tank.ok) data["tank"]["raw_cm"] = round1(rec.r.tankRawCm);
  JsonObject st = doc["state"].to<JsonObject>();
  st["pump"] = rec.pump ? 1 : 0;
  st["fan"] = rec.fan ? 1 : 0;
  st["lamp"] = rec.lamp ? 1 : 0;
  st["mode"] = MODE_NAMES[rec.mode];
  locksToJson(rec.locks, st["locks"].to<JsonArray>());
  serializeJson(doc, out, sizeof out);
  return netPublish("telemetry", out);
}

static void telemetryTick() {
  TelemetryRec rec;
  rec.seq = nextTelemetrySeq();
  rec.ts = nowMs();
  rec.ms = millis();
  rec.synced = rec.ts != 0;
  rec.r = sensorReadings();
  rec.pump = pumpIsOn();
  rec.fan = fanIsOn();
  rec.lamp = lampIsOn();
  rec.mode = modeCode();
  rec.locks = currentLocks();
  // Còn bản cũ chưa gửi thì xếp hàng sau để giữ đúng thứ tự
  if (bufCount() == 0 && publishTelemetry(rec, false)) return;
  bufPush(rec);
}

static void drainBuffer() {
  TelemetryRec rec;
  if (!bufPeek(rec)) return;
  if (publishTelemetry(rec, true)) bufPop();
}

// ---------- status ----------
static void publishStatus() {
  char ip[20];
  netIp(ip, sizeof ip);
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = deviceCode();
  doc["ts"] = nowMs();
  doc["online"] = true;
  doc["fw"] = FW_VERSION;
  doc["hw"] = HW_VERSION;
  doc["ip"] = ip;
  doc["rssi"] = wifiRssi();
  doc["uptime_s"] = millis() / 1000;
  doc["heap"] = ESP.getFreeHeap();
  doc["config_version"] = cfg.version;
  doc["buffered"] = bufCount();
  doc["dropped"] = bufDropped();
  serializeJson(doc, out, sizeof out);
  if (netPublish("status", out, true)) statusPending = false;
}

void requestStatusSoon() { statusPending = true; }

// ---------- ack + chống trùng lệnh ----------
struct DedupRec {
  char id[40];
  char result[24];
};
static DedupRec dedup[DEDUP_CAPACITY];
static uint8_t dedupHead = 0;

static const char* findDuplicate(const char* id) {
  for (auto& d : dedup)
    if (d.id[0] && strcmp(d.id, id) == 0) return d.result;
  return nullptr;
}

static void remember(const char* id, const char* result) {
  snprintf(dedup[dedupHead].id, sizeof dedup[0].id, "%s", id);
  snprintf(dedup[dedupHead].result, sizeof dedup[0].result, "%s", result);
  dedupHead = (dedupHead + 1) % DEDUP_CAPACITY;
}

static void sendAck(const char* id, const char* kind, const char* result, JsonVariantConst detail) {
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = deviceCode();
  doc["ts"] = nowMs();
  doc["cmd_id"] = id;
  doc["kind"] = kind;
  doc["result"] = result;
  if (!detail.isNull()) doc["detail"] = detail;
  else doc["detail"].to<JsonObject>();
  serializeJson(doc, out, sizeof out);
  netPublish("ack", out);
  Serial.printf("[ack] %s %s -> %s\n", kind, id, result);
}

static void handleCommand(const uint8_t* p, unsigned int len) {
  JsonDocument in;
  if (deserializeJson(in, p, len)) {
    Serial.println("[cmd] JSON loi, bo qua");
    return;
  }
  const char* id = in["cmd_id"] | "";
  const char* action = in["action"] | "";
  if (!*id || strlen(id) >= sizeof dedup[0].id) {
    Serial.println("[cmd] thieu/sai cmd_id, bo qua");
    return;
  }
  if (const char* prev = findDuplicate(id)) {
    JsonDocument d;
    d["duplicate"] = true;
    sendAck(id, "command", prev, d.as<JsonVariantConst>());  // gửi lại kết quả cũ, không chạy lại
    return;
  }
  JsonDocument resDoc;
  JsonObject detail = resDoc.to<JsonObject>();
  uint64_t issued = in["issued_at"].as<uint64_t>();
  uint32_t ttl = in["ttl_s"] | 0;
  const char* result;
  if (!*action) {
    result = "invalid";
  } else if (timeSynced() && issued > 0 && ttl > 0 && nowMs() > issued + uint64_t(ttl) * 1000ULL) {
    result = "expired";
  } else if (strcmp(action, "request_status") == 0) {
    result = "executed";
    requestStatusSoon();
  } else if (localActive()) {
    result = "blocked_local";   // đang có người thao tác keypad (§6.6)
  } else if (strcmp(action, "reboot") == 0) {
    result = "executed";
    rebootAt = millis() + 500;  // gửi ack xong mới khởi động lại
  } else {
    result = controlCommand(action, in["params"].as<JsonObjectConst>(), detail, Source::REMOTE);
  }
  remember(id, result);
  sendAck(id, "command", result, resDoc.as<JsonVariantConst>());
}

static void handleConfig(const uint8_t* p, unsigned int len) {
  JsonDocument in;
  if (deserializeJson(in, p, len)) {
    Serial.println("[cfg] JSON loi, bo qua");
    return;
  }
  uint32_t ver = in["config_version"] | 0;
  if (ver == 0) return;
  char id[20];
  snprintf(id, sizeof id, "cfg-%lu", (unsigned long)ver);
  JsonDocument resDoc;
  JsonObject detail = resDoc.to<JsonObject>();
  if (ver < cfg.version) {
    Serial.printf("[cfg] bo qua ban cu %lu (dang dung %lu)\n", (unsigned long)ver, (unsigned long)cfg.version);
    return;
  }
  if (ver == cfg.version) {
    // Bản retain gửi lại sau khi kết nối: xác nhận lại để backend chắc chắn đã APPLIED
    sendAck(id, "config", "executed", resDoc.as<JsonVariantConst>());
    return;
  }
  Config tmp = cfg;
  const char* bad = configParse(in["params"].as<JsonObjectConst>(), tmp);
  if (bad) {
    detail["field"] = bad;
    sendAck(id, "config", "invalid", resDoc.as<JsonVariantConst>());
    return;
  }
  tmp.version = ver;
  cfg = tmp;
  configSave();
  sendAck(id, "config", "executed", resDoc.as<JsonVariantConst>());
  requestStatusSoon();
  configPrint();
}

void protocolOnMessage(const char* kind, const uint8_t* payload, unsigned int len) {
  if (strcmp(kind, "command") == 0) handleCommand(payload, len);
  else if (strcmp(kind, "config") == 0) handleConfig(payload, len);
}

// ---------- vòng lặp ----------
static const char* resetReasonName() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    default: return "unknown";
  }
}

void protocolBegin() {
  const char* reason = resetReasonName();
  emitEvent("boot", [reason](JsonObject d) {
    d["reset_reason"] = reason;
    d["fw"] = FW_VERSION;
  });
  nextTelemetry = millis() + 3000;  // chờ cảm biến có vài mẫu
}

void protocolOnConnected() {
  publishStatus();
  nextStatus = millis() + STATUS_PERIOD_MS;
  flushEvents();
}

void protocolLoop() {
  uint32_t now = millis();
  if ((int32_t)(now - nextTelemetry) >= 0) {
    nextTelemetry = now + uint32_t(cfg.telemetryIntervalS) * 1000UL;
    if (sensorsHaveData()) telemetryTick();
  }
  if (rebootAt && (int32_t)(now - rebootAt) >= 0) {
    Serial.println("[sys] khoi dong lai theo lenh");
    controlAllOff();
    flushEvents();
    delay(200);
    ESP.restart();
  }
  if (!mqttUp()) return;
  if (statusPending || (int32_t)(now - nextStatus) >= 0) {
    nextStatus = now + STATUS_PERIOD_MS;
    publishStatus();
  }
  flushEvents();
  if (bufCount() > 0 && (int32_t)(now - nextDrain) >= 0) {
    nextDrain = now + DRAIN_GAP_MS;
    drainBuffer();
  }
}
