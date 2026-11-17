#include "portal.h"
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include "secrets.h"
#include "identity.h"

#ifndef PORTAL_AP_PASS
#define PORTAL_AP_PASS "vuonuom1"   // WPA2 cần >= 8 ký tự; đặt lại trong secrets.h nếu muốn
#endif

static const uint32_t PORTAL_TIMEOUT_MS = 5UL * 60 * 1000;
static const uint32_t RESTART_DELAY_MS = 2000;   // để trình duyệt nhận xong trang "đã lưu"

static WebServer server(80);
static DNSServer dns;
static bool active = false, saved = false, routesSet = false;
static uint32_t startedAt = 0, restartAt = 0;
static char apName[32];

static String esc(const String& s) {
  String o;
  o.reserve(s.length() + 8);
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '&') o += "&amp;";
    else if (c == '<') o += "&lt;";
    else if (c == '>') o += "&gt;";
    else if (c == '"') o += "&quot;";
    else o += c;
  }
  return o;
}

static const char PAGE_HEAD[] =
  "<!doctype html><html><head><meta charset=utf-8>"
  "<meta name=viewport content='width=device-width,initial-scale=1'><title>Cai WiFi</title>"
  "<style>body{font-family:sans-serif;max-width:420px;margin:1.5em auto;padding:0 1em}"
  "label{display:block;margin-top:1em;font-weight:600}"
  "input{width:100%;padding:.6em;font-size:1em;box-sizing:border-box}"
  "button{margin-top:1.5em;width:100%;padding:.8em;font-size:1em}"
  ".err{color:#b00020}.ok{color:#1b7f3b}</style></head><body>";

static void sendForm(const String& note, bool isError, int code = 200) {
  String h = PAGE_HEAD;
  h += "<h2>C&agrave;i WiFi cho ";
  h += esc(ident.code);
  h += "</h2>";
  if (note.length()) {
    h += isError ? "<p class=err>" : "<p class=ok>";
    h += esc(note);
    h += "</p>";
  }
  h += "<form method=post action=/save>"
       "<label>T&ecirc;n WiFi (2,4 GHz)</label>"
       "<input name=ssid list=nets maxlength=32 required autocomplete=off autocapitalize=off>"
       "<datalist id=nets>";
  int n = WiFi.scanComplete();
  if (n == WIFI_SCAN_FAILED) {
    WiFi.scanNetworks(true);   // chưa có kết quả: quét nền, bấm "Quét lại" sau vài giây
  } else if (n > 0) {
    for (int i = 0; i < n; i++) {
      String s = WiFi.SSID(i);
      if (s.length() == 0) continue;
      h += "<option value=\"" + esc(s) + "\">" + String(WiFi.RSSI(i)) + " dBm</option>";
    }
  }
  h += "</datalist>"
       "<label>M&#7853;t kh&#7849;u</label><input name=pass type=password maxlength=64 autocomplete=off>"
       "<label>&#272;&#7883;a ch&#7881; MQTT broker</label><input name=host maxlength=39 value=\"";
  h += esc(ident.mqttHost);
  h += "\"><button type=submit>L&#432;u v&agrave; k&#7871;t n&#7889;i</button></form>"
       "<p><a href=/rescan>Qu&eacute;t l&#7841;i WiFi xung quanh</a></p></body></html>";
  server.send(code, "text/html; charset=utf-8", h);
}

static void handleRoot() { sendForm("", false); }

static void handleRescan() {
  WiFi.scanNetworks(true);
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

static void handleSave() {
  String ssid = server.arg("ssid");
  String pass = server.arg("pass");
  String host = server.arg("host");
  ssid.trim();
  host.trim();
  if (ssid.length() < 1 || ssid.length() > 32) {
    sendForm("Tên WiFi phải từ 1 đến 32 ký tự.", true, 400);
    return;
  }
  if (pass.length() != 0 && (pass.length() < 8 || pass.length() > 64)) {
    sendForm("Mật khẩu WiFi phải từ 8 đến 64 ký tự.", true, 400);
    return;
  }
  if (host.length() > 39 || host.indexOf(' ') >= 0) {
    sendForm("Địa chỉ MQTT không hợp lệ.", true, 400);
    return;
  }
  if (!identitySetWifi(ssid.c_str(), pass.c_str(), host.c_str())) {
    sendForm("Không ghi được vào bộ nhớ thiết bị.", true, 500);
    return;
  }
  String h = PAGE_HEAD;
  h += "<h2 class=ok>&#272;&atilde; l&#432;u</h2><p>Thi&#7871;t b&#7883; &#273;ang kh&#7903;i &#273;&#7897;ng l&#7841;i v&agrave; k&#7871;t n&#7889;i WiFi <b>";
  h += esc(ssid);
  h += "</b>. B&#7841;n c&oacute; th&#7875; &#273;&oacute;ng trang n&agrave;y.</p></body></html>";
  server.send(200, "text/html; charset=utf-8", h);
  saved = true;
  restartAt = millis() + RESTART_DELAY_MS;
  Serial.printf("[portal] da luu WiFi '%s', khoi dong lai\n", ssid.c_str());
}

static void handleNotFound() {   // hệ điều hành dò "có Internet không" -> chuyển về form để hiện cửa sổ đăng nhập
  server.sendHeader("Location", String("http://") + WiFi.softAPIP().toString() + "/");
  server.send(302, "text/plain", "");
}

void portalStart() {
  if (active) return;
  snprintf(apName, sizeof apName, "VuonUom-%s", ident.code);
  WiFi.disconnect();                 // dừng thử nối STA: vừa thử nối vừa phát AP làm AP chập chờn
  WiFi.mode(WIFI_AP_STA);            // cần STA để quét WiFi xung quanh
  if (!WiFi.softAP(apName, PORTAL_AP_PASS, 1, 0, 2)) {
    Serial.println("[portal] loi: khong bat duoc AP");
    WiFi.mode(WIFI_STA);
    return;
  }
  dns.start(53, "*", WiFi.softAPIP());
  if (!routesSet) {
    server.on("/", HTTP_GET, handleRoot);
    server.on("/rescan", HTTP_GET, handleRescan);
    server.on("/save", HTTP_POST, handleSave);
    server.onNotFound(handleNotFound);
    routesSet = true;
  }
  server.begin();
  WiFi.scanNetworks(true);
  active = true;
  saved = false;
  startedAt = millis();
  Serial.printf("[portal] WiFi '%s' mat khau '%s' -> mo http://%s\n", apName, PORTAL_AP_PASS,
                WiFi.softAPIP().toString().c_str());
}

void portalStop() {
  if (!active) return;
  server.stop();
  dns.stop();
  WiFi.scanDelete();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  active = false;
  Serial.println("[portal] tat");
}

bool portalActive() { return active; }
const char* portalApName() { return apName; }
const char* portalApPass() { return PORTAL_AP_PASS; }

bool portalLoop() {
  if (!active) return false;
  dns.processNextRequest();
  server.handleClient();
  if (saved) return (int32_t)(millis() - restartAt) >= 0;
  // Đã có SSID (nhưng không nối được) thì sau 5 phút quay lại thử; chưa có SSID thì chờ đến khi được nhập
  if (ident.wifiSsid[0] && millis() - startedAt > PORTAL_TIMEOUT_MS) portalStop();
  return false;
}
