#include "identity.h"
#include <Preferences.h>
#include "secrets.h"

Identity ident;

static const char* NS = "ident";
enum Field : uint8_t { F_SSID, F_PASS, F_HOST, F_GARDEN, F_CODE, F_SECRET, F_UPLOAD, F_COUNT };
static const char* NAMES[F_COUNT] = {"ssid", "pass", "host", "garden", "code", "secret", "upload"};
static const char* PORT_KEY = "port";

static Identity pending;                 // bản sửa bằng 'set', chỉ có hiệu lực sau 'save' + khởi động lại
static bool fromNvs[F_COUNT + 1];        // [F_COUNT] = port
static bool dirty = false;

static char* fptr(Identity& d, int i) {
  switch (i) {
    case F_SSID: return d.wifiSsid;
    case F_PASS: return d.wifiPass;
    case F_HOST: return d.mqttHost;
    case F_GARDEN: return d.garden;
    case F_CODE: return d.code;
    case F_SECRET: return d.secret;
    default: return d.uploadUrl;
  }
}

static size_t fcap(int i) {
  switch (i) {
    case F_SSID: return sizeof ident.wifiSsid;
    case F_PASS: return sizeof ident.wifiPass;
    case F_HOST: return sizeof ident.mqttHost;
    case F_GARDEN: return sizeof ident.garden;
    case F_CODE: return sizeof ident.code;
    case F_SECRET: return sizeof ident.secret;
    default: return sizeof ident.uploadUrl;
  }
}

static void loadDefaults(Identity& d) {
  memset(&d, 0, sizeof d);
  strlcpy(d.wifiSsid, WIFI_SSID, sizeof d.wifiSsid);
  strlcpy(d.wifiPass, WIFI_PASS, sizeof d.wifiPass);
  strlcpy(d.mqttHost, MQTT_HOST, sizeof d.mqttHost);
  d.mqttPort = MQTT_PORT;
  strlcpy(d.garden, GARDEN_CODE, sizeof d.garden);
  strlcpy(d.code, DEVICE_CODE, sizeof d.code);
  strlcpy(d.secret, DEVICE_SECRET, sizeof d.secret);
#ifdef UPLOAD_URL
  strlcpy(d.uploadUrl, UPLOAD_URL, sizeof d.uploadUrl);
#endif
}

void identityBegin() {
  loadDefaults(ident);
  memset(fromNvs, 0, sizeof fromNvs);
  Preferences p;
  if (p.begin(NS, false)) {
    for (int i = 0; i < F_COUNT; i++) {
      String s = p.getString(NAMES[i], "");
      if (s.length() > 0 && s.length() < fcap(i)) {
        strlcpy(fptr(ident, i), s.c_str(), fcap(i));
        fromNvs[i] = true;
      }
    }
    uint16_t port = p.getUShort(PORT_KEY, 0);
    if (port) {
      ident.mqttPort = port;
      fromNvs[F_COUNT] = true;
    }
    p.end();
  }
  pending = ident;
  dirty = false;
  Serial.printf("[id] code=%s garden=%s host=%s:%u (%s)\n", ident.code, ident.garden, ident.mqttHost, ident.mqttPort,
                (fromNvs[F_CODE] || fromNvs[F_SECRET]) ? "NVS" : "secrets.h");
}

static void printSecret(const char* s, char* out, size_t n) {
  size_t len = strlen(s);
  if (len == 0) snprintf(out, n, "(trong)");
  else snprintf(out, n, "%.3s*** (%u ky tu)", s, (unsigned)len);
}

static const char* src(int i) { return fromNvs[i] ? "nvs" : "secrets.h"; }

void identityPrint() {
  char sec[40], pass[40];
  printSecret(ident.secret, sec, sizeof sec);
  printSecret(ident.wifiPass, pass, sizeof pass);
  Serial.println("--- Danh tinh thiet bi (dang dung) ---");
  Serial.printf("code   : %s  [%s]\n", ident.code, src(F_CODE));
  Serial.printf("secret : %s  [%s]\n", sec, src(F_SECRET));
  Serial.printf("garden : %s  [%s]\n", ident.garden, src(F_GARDEN));
  Serial.printf("host   : %s  [%s]\n", ident.mqttHost, src(F_HOST));
  Serial.printf("port   : %u  [%s]\n", ident.mqttPort, src(F_COUNT));
  Serial.printf("ssid   : %s  [%s]\n", ident.wifiSsid, src(F_SSID));
  Serial.printf("pass   : %s  [%s]\n", pass, src(F_PASS));
  if (ident.uploadUrl[0] || fromNvs[F_UPLOAD]) Serial.printf("upload : %s  [%s]\n", ident.uploadUrl, src(F_UPLOAD));
  if (dirty) Serial.println("(co thay doi chua luu: go 'save' de ghi va khoi dong lai, 'clear' de bo)");
}

static bool validToken(const char* s) {   // chữ, số, '-', '_' ; không rỗng
  if (!*s) return false;
  for (; *s; s++)
    if (!isalnum((unsigned char)*s) && *s != '-' && *s != '_') return false;
  return true;
}

static int fieldByName(const char* name) {
  for (int i = 0; i < F_COUNT; i++)
    if (strcmp(name, NAMES[i]) == 0) return i;
  return -1;
}

static void doSet(const char* args) {
  // args = "<khóa> <giá trị...>" — giá trị là phần còn lại của dòng (cho phép dấu cách trong tên WiFi)
  char key[12];
  size_t k = 0;
  while (args[k] && args[k] != ' ' && k < sizeof key - 1) {
    key[k] = args[k];
    k++;
  }
  key[k] = 0;
  const char* val = args + k;
  while (*val == ' ') val++;
  char v[160];   // > mọi fcap(), nên giá trị quá dài bị phát hiện thay vì bị cắt âm thầm
  strlcpy(v, val, sizeof v);
  size_t n = strlen(v);
  while (n > 0 && v[n - 1] == ' ') v[--n] = 0;

  if (strcmp(key, "port") == 0) {
    long port = atol(v);
    if (port < 1 || port > 65535) {
      Serial.println("port phai trong 1..65535");
      return;
    }
    pending.mqttPort = (uint16_t)port;
    dirty = true;
    Serial.printf("port = %u (chua luu)\n", pending.mqttPort);
    return;
  }
  int f = fieldByName(key);
  if (f < 0) {
    Serial.println("Khoa hop le: code | secret | garden | host | port | ssid | pass | upload");
    return;
  }
  if (n == 0 && f != F_UPLOAD) {
    Serial.println("thieu gia tri");
    return;
  }
  if (n >= fcap(f)) {
    Serial.printf("gia tri qua dai (toi da %u ky tu)\n", (unsigned)(fcap(f) - 1));
    return;
  }
  if ((f == F_CODE || f == F_GARDEN) && !validToken(v)) {
    Serial.println("chi dung chu, so, '-' va '_'");
    return;
  }
  if (f == F_SECRET && strchr(v, ' ')) {
    Serial.println("secret khong co dau cach");
    return;
  }
  strlcpy(fptr(pending, f), v, fcap(f));
  dirty = true;
  if (f == F_SECRET) Serial.printf("secret = (%u ky tu, chua luu)\n", (unsigned)n);
  else if (f == F_PASS) Serial.println("pass = *** (chua luu)");
  else Serial.printf("%s = %s (chua luu)\n", key, v);
}

int identityCommand(const char* cmd) {
  if (strcmp(cmd, "id") == 0) {
    identityPrint();
    return 1;
  }
  if (strncmp(cmd, "set ", 4) == 0) {
    doSet(cmd + 4);
    return 1;
  }
  if (strcmp(cmd, "save") == 0) {
    if (!dirty) {
      Serial.println("Khong co thay doi nao de luu.");
      return 1;
    }
    Preferences p;
    if (!p.begin(NS, false)) {
      Serial.println("Loi: khong mo duoc NVS");
      return 1;
    }
    for (int i = 0; i < F_COUNT; i++) p.putString(NAMES[i], fptr(pending, i));
    p.putUShort(PORT_KEY, pending.mqttPort);
    p.end();
    Serial.println("Da luu danh tinh vao NVS, khoi dong lai...");
    return 2;
  }
  if (strcmp(cmd, "clear") == 0) {
    Preferences p;
    if (p.begin(NS, false)) {
      p.clear();
      p.end();
    }
    Serial.println("Da xoa danh tinh trong NVS (ve gia tri secrets.h), khoi dong lai...");
    return 2;
  }
  return 0;
}
