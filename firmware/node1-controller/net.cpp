#include "net.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>
#include <sys/time.h>
#include "secrets.h"
#include "protocol.h"
#include "identity.h"

#ifndef NTP_SERVER
#define NTP_SERVER "pool.ntp.org"
#endif

static WiFiClient wifiClient;
static PubSubClient mqtt(wifiClient);
static char topicBase[64];   // nursery/g01/ctl-0001/
static char lwtTopic[80];
static char lwtPayload[96];

static const uint32_t WIFI_ATTEMPT_MS = 10000;          // chờ tối đa cho một lần kết nối WiFi
static const uint32_t NTP_RESYNC_MS = 6UL * 3600 * 1000;
static bool wifiConnecting = false, wifiWasUp = false;
static uint32_t wifiAttemptAt = 0, wifiNextTry = 0, mqttNextTry = 0, ntpNext = 0;
static uint8_t wifiBackoff = 1, mqttBackoff = 1;   // giây: 1 → 2 → 4 → 8 → 16 → 30

static uint8_t nextBackoff(uint8_t b) { return b >= 16 ? 30 : b * 2; }

static void onMessage(char* topic, uint8_t* payload, unsigned int len) {
  size_t n = strlen(topicBase);
  if (strncmp(topic, topicBase, n) != 0) return;
  protocolOnMessage(topic + n, payload, len);
}

static void startWifi() {
  WiFi.disconnect();
  WiFi.begin(ident.wifiSsid, ident.wifiPass);
  wifiConnecting = true;
  wifiAttemptAt = millis();
  Serial.printf("[net] ket noi WiFi '%s'...\n", ident.wifiSsid);
}

static void startNtp() {
  configTime(0, 0, NTP_SERVER, "time.google.com");  // UTC, qua Internet chia sẻ vào hotspot (C11)
  ntpNext = millis() + NTP_RESYNC_MS;
}

static bool mqttConnect() {
  Serial.printf("[net] ket noi MQTT %s:%d...\n", ident.mqttHost, ident.mqttPort);
  bool ok = mqtt.connect(ident.code, ident.code, ident.secret,
                         lwtTopic, 1, true, lwtPayload, true);
  if (!ok) {
    // 4 = sai tài khoản, 5 = không được phép (thiết bị bị khóa / thu hồi)
    Serial.printf("[net] MQTT that bai, state=%d\n", mqtt.state());
    return false;
  }
  char t[80];
  snprintf(t, sizeof t, "%scommand", topicBase);
  mqtt.subscribe(t, 1);
  snprintf(t, sizeof t, "%sconfig", topicBase);
  mqtt.subscribe(t, 1);
  Serial.println("[net] MQTT OK");
  return true;
}

void netBegin() {
  snprintf(topicBase, sizeof topicBase, "nursery/%s/%s/", ident.garden, ident.code);
  snprintf(lwtTopic, sizeof lwtTopic, "%sstatus", topicBase);
  snprintf(lwtPayload, sizeof lwtPayload, "{\"v\":1,\"device_id\":\"%s\",\"online\":false}", ident.code);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);  // tự quản lý kết nối lại có backoff
  mqtt.setServer(ident.mqttHost, ident.mqttPort);
  mqtt.setCallback(onMessage);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(5);
  startWifi();
}

void netLoop() {
  uint32_t now = millis();
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasUp) {
      wifiWasUp = true;
      wifiConnecting = false;
      wifiBackoff = 1;
      char ip[20];
      netIp(ip, sizeof ip);
      Serial.printf("[net] WiFi OK, IP %s, RSSI %d\n", ip, WiFi.RSSI());
      startNtp();
      mqttNextTry = now;
    }
    if ((int32_t)(now - ntpNext) >= 0) startNtp();
    if (mqtt.connected()) {
      mqtt.loop();
    } else if ((int32_t)(now - mqttNextTry) >= 0) {
      if (mqttConnect()) {
        mqttBackoff = 1;
        protocolOnConnected();
      } else {
        mqttNextTry = millis() + mqttBackoff * 1000UL;
        mqttBackoff = nextBackoff(mqttBackoff);
      }
    }
    return;
  }
  // Không có WiFi
  if (wifiWasUp) {
    wifiWasUp = false;
    mqtt.disconnect();
    Serial.println("[net] mat WiFi");
    wifiNextTry = now;
  }
  if (wifiConnecting) {
    if (now - wifiAttemptAt > WIFI_ATTEMPT_MS) {
      wifiConnecting = false;
      wifiNextTry = now + wifiBackoff * 1000UL;
      Serial.printf("[net] WiFi chua duoc, thu lai sau %us\n", wifiBackoff);
      wifiBackoff = nextBackoff(wifiBackoff);
    }
  } else if ((int32_t)(now - wifiNextTry) >= 0) {
    startWifi();
  }
}

bool wifiUp() { return WiFi.status() == WL_CONNECTED; }
bool mqttUp() { return wifiUp() && mqtt.connected(); }

bool netPublish(const char* kind, const char* payload, bool retain) {
  if (!mqttUp()) return false;
  char t[80];
  snprintf(t, sizeof t, "%s%s", topicBase, kind);
  return mqtt.publish(t, payload, retain);
}

uint64_t nowMs() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  if (tv.tv_sec < 1700000000) return 0;  // chưa có giờ thật
  return uint64_t(tv.tv_sec) * 1000ULL + tv.tv_usec / 1000;
}

bool timeSynced() { return nowMs() != 0; }
const char* deviceCode() { return ident.code; }
int wifiRssi() { return wifiUp() ? WiFi.RSSI() : 0; }

void netIp(char* buf, size_t n) {
  if (!wifiUp()) { snprintf(buf, n, "-"); return; }
  snprintf(buf, n, "%s", WiFi.localIP().toString().c_str());
}

void netPrint() {
  char ip[20];
  netIp(ip, sizeof ip);
  Serial.printf("WiFi=%s IP=%s RSSI=%d MQTT=%s state=%d NTP=%s\n",
                wifiUp() ? "OK" : "--", ip, wifiRssi(), mqtt.connected() ? "OK" : "--",
                mqtt.state(), timeSynced() ? "OK" : "--");
}
