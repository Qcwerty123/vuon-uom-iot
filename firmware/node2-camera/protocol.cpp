#include "protocol.h"
#include <esp_system.h>
#include "config_store.h"
#include "camera.h"
#include "capture.h"
#include "net.h"

static const uint32_t STATUS_PERIOD_MS = 30000;
static const uint8_t EVENT_CAPACITY = 20;
static const uint8_t DEDUP_CAPACITY = 20;

static uint32_t nextStatus = 0, rebootAt = 0;
static bool statusPending = false;
static char out[1024];
static char pendingAck[1024] = "";   // ack capture chưa gửi được (mất mạng đúng lúc upload xong)

static uint64_t fixTs(uint64_t ts, bool synced, uint32_t ms) {
  if (synced) return ts;
  if (timeSynced()) return nowMs() - (millis() - ms);
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
  if (evCount < EVENT_CAPACITY) evCount++;
}

static void flushEvents() {
  for (uint8_t k = 0; k < 5 && evCount > 0 && mqttUp(); k++) {
    EventRec& e = events[(evHead + EVENT_CAPACITY - evCount) % EVENT_CAPACITY];
    JsonDocument doc;
    doc["v"] = 1;
    doc["device_id"] = deviceCode();
    doc["ts"] = fixTs(e.ts, e.synced, e.ms);
    doc["seq"] = e.seq;
    doc["type"] = e.type;
    doc["detail"] = serialized(e.detail);
    serializeJson(doc, out, sizeof out);
    if (!netPublish("event", out)) break;
    evCount--;
  }
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
  doc["psram"] = ESP.getFreePsram();
  doc["config_version"] = cfg.version;
  doc["camera_ok"] = cameraReady();
  doc["images_ok"] = captureOkCount();
  doc["images_failed"] = captureFailCount();
  doc["next_capture_s"] = captureNextInS();
  serializeJson(doc, out, sizeof out);
  if (netPublish("status", out, true)) statusPending = false;
}

void requestStatusSoon() { statusPending = true; }

// ---------- ack + chống trùng ----------
struct DedupRec {
  char id[40];
  char result[24];   // "pending" khi lệnh capture đang chạy
};
static DedupRec dedup[DEDUP_CAPACITY];
static uint8_t dedupHead = 0;

static DedupRec* findDedup(const char* id) {
  for (auto& d : dedup)
    if (d.id[0] && strcmp(d.id, id) == 0) return &d;
  return nullptr;
}

static void remember(const char* id, const char* result) {
  DedupRec* d = findDedup(id);
  if (!d) {
    d = &dedup[dedupHead];
    dedupHead = (dedupHead + 1) % DEDUP_CAPACITY;
  }
  snprintf(d->id, sizeof d->id, "%s", id);
  snprintf(d->result, sizeof d->result, "%s", result);
}

static bool sendAck(const char* id, const char* kind, const char* result, JsonVariantConst detail) {
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
  Serial.printf("[ack] %s %s -> %s\n", kind, id, result);
  return netPublish("ack", out);
}

void protocolCaptureDone(const char* cmdId, const char* result, DetailFn fill) {
  remember(cmdId, result);
  JsonDocument d;
  JsonObject o = d.to<JsonObject>();
  if (fill) fill(o);
  if (!sendAck(cmdId, "command", result, d.as<JsonVariantConst>())) {
    snprintf(pendingAck, sizeof pendingAck, "%s", out);  // gửi lại khi có kết nối
  }
}

static int parseFlashParam(JsonVariantConst v, bool& ok) {
  ok = true;
  if (v.isNull()) return -1;
  const char* s = v | "";
  if (strcmp(s, "on") == 0) return 1;
  if (strcmp(s, "off") == 0) return 0;
  ok = false;
  return -1;
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
  if (DedupRec* prev = findDedup(id)) {
    if (strcmp(prev->result, "pending") == 0) {
      Serial.printf("[cmd] %s dang chay, bo qua ban trung\n", id);
      return;
    }
    JsonDocument d;
    d["duplicate"] = true;
    sendAck(id, "command", prev->result, d.as<JsonVariantConst>());
    return;
  }
  JsonDocument resDoc;
  JsonObject detail = resDoc.to<JsonObject>();
  JsonObjectConst params = in["params"].as<JsonObjectConst>();
  uint64_t issued = in["issued_at"].as<uint64_t>();
  uint32_t ttl = in["ttl_s"] | 0;
  const char* result;
  auto is = [action](const char* x) { return strcmp(action, x) == 0; };

  if (!*action) {
    result = "invalid";
  } else if (timeSynced() && issued > 0 && ttl > 0 && nowMs() > issued + uint64_t(ttl) * 1000ULL) {
    result = "expired";
  } else if (is("request_status")) {
    result = "executed";
    requestStatusSoon();
  } else if (is("capture")) {
    bool ok;
    int flashOv = parseFlashParam(params["flash"], ok);
    if (!ok) {
      detail["field"] = "flash";
      result = "invalid";
    } else if (const char* why = captureRequest(id, flashOv)) {
      detail["reason"] = why;
      result = "failed";
    } else {
      remember(id, "pending");   // ack gửi sau khi upload xong
      return;
    }
  } else if (is("flash")) {
    const char* state = params["state"] | "";
    long dur = params["duration_s"] | 3L;
    if (strcmp(state, "on") != 0 && strcmp(state, "off") != 0) {
      detail["field"] = "state";
      result = "invalid";
    } else if (strcmp(state, "on") == 0 && (dur < 1 || dur > 10)) {
      detail["field"] = "duration_s";
      result = "invalid";
    } else if (captureBusy()) {
      detail["reason"] = "busy";
      result = "failed";
    } else {
      if (strcmp(state, "on") == 0) {
        flashOnFor(uint16_t(dur));
        detail["duration_s"] = dur;
      } else {
        flashOff();
      }
      result = "executed";
    }
  } else if (is("reboot")) {
    if (captureBusy()) {
      detail["reason"] = "busy";
      result = "failed";
    } else {
      result = "executed";
      rebootAt = millis() + 500;
    }
  } else {
    result = "unsupported";
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
  if (ver < cfg.version) return;
  if (ver == cfg.version) {
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
  bool intervalChanged = tmp.captureIntervalMin != cfg.captureIntervalMin;
  tmp.version = ver;
  cfg = tmp;
  configSave();
  cameraApplyConfig();
  if (intervalChanged) captureReschedule();
  sendAck(id, "config", "executed", resDoc.as<JsonVariantConst>());
  requestStatusSoon();
  configPrint();
}

void protocolOnMessage(const char* kind, const uint8_t* payload, unsigned int len) {
  if (strcmp(kind, "command") == 0) handleCommand(payload, len);
  else if (strcmp(kind, "config") == 0) handleConfig(payload, len);
}

static const char* resetReasonName() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON: return "power_on";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_BROWNOUT: return "brownout";   // gần như chắc chắn do nguồn yếu
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
}

void protocolOnConnected() {
  publishStatus();
  nextStatus = millis() + STATUS_PERIOD_MS;
  if (pendingAck[0] && netPublish("ack", pendingAck)) pendingAck[0] = 0;
  flushEvents();
}

void protocolLoop() {
  uint32_t now = millis();
  if (rebootAt && (int32_t)(now - rebootAt) >= 0) {
    Serial.println("[sys] khoi dong lai theo lenh");
    flashOff();
    flushEvents();
    delay(200);
    ESP.restart();
  }
  if (!mqttUp()) return;
  if (pendingAck[0] && netPublish("ack", pendingAck)) pendingAck[0] = 0;
  if (statusPending || (int32_t)(now - nextStatus) >= 0) {
    nextStatus = now + STATUS_PERIOD_MS;
    publishStatus();
  }
  flushEvents();
}
