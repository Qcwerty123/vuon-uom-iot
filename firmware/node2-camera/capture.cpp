#include "capture.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"
#include "camera.h"
#include "config_store.h"
#include "net.h"
#include "protocol.h"

static const uint32_t MIN_GAP_MS = 20000;        // backend giới hạn 1 ảnh / 20 s (§8.9)
static const uint8_t MAX_ATTEMPTS = 3;
static const uint32_t RETRY_GAP_MS = 5000;
static const uint16_t HTTP_TIMEOUT_MS = 10000;
static const size_t MAX_BYTES = 300 * 1024;
static const uint32_t FIRST_CAPTURE_MS = 60000;  // ảnh theo lịch đầu tiên: 1 phút sau khi khởi động

enum class St : uint8_t { IDLE, WAIT_GAP, UPLOAD, WAIT_RETRY };
static St st = St::IDLE;
static camera_fb_t* fb = nullptr;
static bool byCommand = false;
static char cmdId[40] = "";
static int flashOverride = -1;
static uint64_t capturedAt = 0;
static uint8_t attempts = 0;
static uint32_t nextScheduled = 0, waitUntil = 0, lastPostAt = 0;
static bool everPosted = false;
static uint32_t okCount = 0, failCount = 0;
static WiFiClient httpClient;

static uint32_t intervalMs() { return uint32_t(cfg.captureIntervalMin) * 60000UL; }

static const char* reasonFor(int code) {
  if (code < 0) return "network";
  switch (code) {
    case 400: return "bad_image";
    case 401: return "unauthorized";
    case 403: return "forbidden";      // thiết bị bị khóa / thu hồi
    case 413: return "too_large";
    case 429: return "rate_limited";
    default: return "http_error";
  }
}

static void finish() {
  cameraRelease(fb);
  fb = nullptr;
  st = St::IDLE;
  cmdId[0] = 0;
}

static void finishOk(const char* imageId, const char* diagId, size_t bytes) {
  okCount++;
  Serial.printf("[cap] upload OK image_id=%s (%u byte, %u lan thu)\n", imageId, (unsigned)bytes, attempts);
  if (byCommand) {
    protocolCaptureDone(cmdId, "executed", [&](JsonObject d) {
      d["image_id"] = imageId;
      if (diagId[0]) d["diagnosis_id"] = diagId;
      d["bytes"] = bytes;
      d["attempts"] = attempts;
    });
  }
  finish();
}

static void finishFail(const char* reason, int http) {
  failCount++;
  Serial.printf("[cap] THAT BAI: %s (http %d, %u lan thu)\n", reason, http, attempts);
  bool cmd = byCommand;
  emitEvent("upload_failed", [&](JsonObject d) {
    d["trigger"] = cmd ? "command" : "schedule";
    d["reason"] = reason;
    d["http"] = http;
    d["attempts"] = attempts;
  });
  if (cmd) {
    protocolCaptureDone(cmdId, "failed", [&](JsonObject d) {
      d["reason"] = reason;
      d["http"] = http;
    });
  }
  finish();
}

static void doUpload() {
  attempts++;
  int code = -1;
  char imageId[48] = "", diagId[48] = "";
  if (wifiUp()) {
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    if (http.begin(httpClient, UPLOAD_URL)) {
      http.setAuthorization(DEVICE_CODE, DEVICE_SECRET);   // Basic auth device_code:secret
      http.addHeader("Content-Type", "image/jpeg");
      if (capturedAt) {
        char ts[24];
        snprintf(ts, sizeof ts, "%llu", (unsigned long long)capturedAt);
        http.addHeader("X-Captured-At", ts);
      }
      http.addHeader("X-Trigger", byCommand ? "command" : "schedule");
      if (byCommand && cmdId[0]) http.addHeader("X-Cmd-Id", cmdId);
      lastPostAt = millis();
      everPosted = true;
      code = http.POST(fb->buf, fb->len);
      if (code == 201 || code == 200) {
        String body = http.getString();
        JsonDocument d;
        if (!deserializeJson(d, body.c_str())) {
          snprintf(imageId, sizeof imageId, "%s", (const char*)(d["image_id"] | ""));
          snprintf(diagId, sizeof diagId, "%s", (const char*)(d["diagnosis_id"] | ""));
        }
      }
      http.end();
    }
  }
  Serial.printf("[cap] POST lan %u -> %d\n", attempts, code);
  if (code == 201 || code == 200) {
    finishOk(imageId, diagId, fb->len);
    return;
  }
  bool permanent = code == 400 || code == 401 || code == 403 || code == 413;  // thử lại cũng vô ích
  if (permanent || attempts >= MAX_ATTEMPTS) {
    finishFail(reasonFor(code), code);
    return;
  }
  waitUntil = millis() + (code == 429 ? MIN_GAP_MS : RETRY_GAP_MS);
  st = St::WAIT_RETRY;
}

const char* captureRequest(const char* id, int flashOv) {
  if (st != St::IDLE) return "busy";
  if (!cameraReady()) return "camera_fault";
  byCommand = id != nullptr;
  snprintf(cmdId, sizeof cmdId, "%s", id ? id : "");
  flashOverride = flashOv;
  attempts = 0;
  st = St::WAIT_GAP;
  return nullptr;
}

void captureBegin() { nextScheduled = millis() + FIRST_CAPTURE_MS; }

void captureLoop() {
  uint32_t now = millis();
  switch (st) {
    case St::IDLE:
      if ((int32_t)(now - nextScheduled) >= 0) {
        nextScheduled = now + intervalMs();
        if (captureRequest(nullptr, -1) != nullptr) Serial.println("[cap] bo qua lich chup (camera loi)");
      }
      break;
    case St::WAIT_GAP: {
      if (everPosted && now - lastPostAt < MIN_GAP_MS) break;  // chờ đủ 20 s kể từ lần gửi trước
      fb = cameraGrab(flashWanted(flashOverride));
      if (!fb) {
        finishFail("camera", 0);
        break;
      }
      capturedAt = nowMs();
      Serial.printf("[cap] chup %ux%u, %u byte\n", (unsigned)fb->width, (unsigned)fb->height, (unsigned)fb->len);
      if (fb->len > MAX_BYTES) {
        finishFail("too_large", 0);   // tăng jpeg_quality hoặc giảm frame_size
        break;
      }
      st = St::UPLOAD;
      break;
    }
    case St::WAIT_RETRY:
      if ((int32_t)(now - waitUntil) >= 0) st = St::UPLOAD;
      break;
    case St::UPLOAD:
      doUpload();
      break;
  }
}

bool captureBusy() { return st != St::IDLE; }
void captureReschedule() { nextScheduled = millis() + intervalMs(); }
uint32_t captureOkCount() { return okCount; }
uint32_t captureFailCount() { return failCount; }
uint32_t captureNextInS() {
  int32_t ms = int32_t(nextScheduled - millis());
  return ms > 0 ? uint32_t(ms) / 1000 : 0;
}
