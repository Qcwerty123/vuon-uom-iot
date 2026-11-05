#include "sensors.h"
#include <algorithm>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include "config_store.h"
#include "protocol.h"

static DHT dht(pins::DHT_DATA, DHT22);
static BH1750 lightMeter(0x23);
static Readings rd;
static bool haveData = false;

// ---------- bộ lọc trung vị 5 mẫu ----------
struct Median5 {
  float buf[5];
  uint8_t n = 0, i = 0;
  void push(float x) {
    buf[i] = x;
    i = (i + 1) % 5;
    if (n < 5) n++;
  }
  bool empty() const { return n == 0; }
  float value() const {
    float t[5];
    for (uint8_t k = 0; k < n; k++) t[k] = buf[k];
    std::sort(t, t + n);
    return t[n / 2];
  }
};

static Median5 mSoil1, mSoil2, mTemp, mHum, mLight, mDist;

// ---------- trạng thái lỗi từng cảm biến ----------
static bool fSoil1 = false, fSoil2 = false, fMismatch = false;
static bool fDht = false, fLight = false, fUs = false;
static uint32_t soil1NormalAt = 0, soil2NormalAt = 0;
static uint8_t dhtNan = 0, lightErr = 0, usTimeout = 0;
static bool lightStarted = false;
static uint32_t lightRetryAt = 0;

static void setFault(const char* name, bool& flag, bool fault) {
  if (flag == fault) return;
  flag = fault;
  emitEvent(fault ? "sensor_fault" : "sensor_ok", [name](JsonObject d) { d["sensor"] = name; });
  Serial.printf("[sensor] %s %s\n", name, fault ? "LOI" : "OK");
}

// ---------- lịch đo ----------
static const uint32_t FAST_PERIOD_MS = 2000;   // đất, siêu âm, ánh sáng
static const uint32_t DHT_PERIOD_MS = 2500;    // DHT22 tối thiểu 2 s
static const uint32_t SOIL_SETTLE_MS = 100;    // chờ sau khi bật nguồn cảm biến đất
static const uint32_t SOIL_STUCK_MS = 30000;   // ADC kẹt 0/4095 lâu hơn → lỗi
static uint32_t nextFast = 0, nextDht = 0, soilReadAt = 0;
static bool soilPowered = false;

static float soilPercent(float adc, const SoilCal& c) {
  return clampf((float(c.dry) - adc) / float(c.dry - c.wet) * 100.0f, 0, 100);
}

static void readSoil(uint32_t now) {
  uint32_t s1 = 0, s2 = 0;
  for (int k = 0; k < 8; k++) {
    s1 += analogRead(pins::SOIL1);
    s2 += analogRead(pins::SOIL2);
  }
  digitalWrite(pins::SOIL_PWR, LOW);  // tắt ngay để giảm ăn mòn que đo
  soilPowered = false;
  float a1 = s1 / 8.0f, a2 = s2 / 8.0f;
  if (a1 > 10 && a1 < 4085) soil1NormalAt = now;
  if (a2 > 10 && a2 < 4085) soil2NormalAt = now;
  mSoil1.push(a1);
  mSoil2.push(a2);
  setFault("soil1", fSoil1, now - soil1NormalAt > SOIL_STUCK_MS);
  setFault("soil2", fSoil2, now - soil2NormalAt > SOIL_STUCK_MS);

  rd.soil1.ok = !fSoil1 && !mSoil1.empty();
  rd.soil2.ok = !fSoil2 && !mSoil2.empty();
  if (rd.soil1.ok) rd.soil1.v = soilPercent(mSoil1.value(), cfg.s1);
  if (rd.soil2.ok) rd.soil2.v = soilPercent(mSoil2.value(), cfg.s2);

  // Hợp nhất 2 cảm biến (§6.4)
  if (rd.soil1.ok && rd.soil2.ok) {
    bool mismatch = fabs(rd.soil1.v - rd.soil2.v) > 30;
    setFault("soil_mismatch", fMismatch, mismatch);
    rd.soil.ok = !mismatch;
    if (!mismatch) rd.soil.v = (rd.soil1.v + rd.soil2.v) / 2;
  } else {
    setFault("soil_mismatch", fMismatch, false);
    rd.soil.ok = rd.soil1.ok || rd.soil2.ok;
    if (rd.soil1.ok) rd.soil.v = rd.soil1.v;
    else if (rd.soil2.ok) rd.soil.v = rd.soil2.v;
  }
}

static void readUltrasonic() {
  digitalWrite(pins::US_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(pins::US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(pins::US_TRIG, LOW);
  unsigned long us = pulseIn(pins::US_ECHO, HIGH, 30000UL);  // tối đa ~5 m
  if (us == 0) {
    if (usTimeout < 255) usTimeout++;
  } else {
    usTimeout = 0;
    float cm = us * 0.0343f / 2.0f;
    if (cm >= 2 && cm <= 400) mDist.push(cm);  // ngoài dải đo thì bỏ mẫu
  }
  setFault("ultrasonic", fUs, usTimeout >= 10);
  rd.tank.ok = !fUs && !mDist.empty();
  if (rd.tank.ok) {
    rd.tankRawCm = mDist.value();
    rd.tank.v = clampf((cfg.tankEmptyCm - rd.tankRawCm) / (cfg.tankEmptyCm - cfg.tankFullCm) * 100.0f, 0, 100);
  }
}

static void readLight(uint32_t now) {
  if (!lightStarted) {
    if (now < lightRetryAt) return;
    lightStarted = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
    if (!lightStarted) {
      lightRetryAt = now + 10000;  // thử lại sau 10 s
      setFault("bh1750", fLight, true);
      rd.light.ok = false;
      return;
    }
  }
  float lux = lightMeter.readLightLevel();
  if (lux < 0) {
    if (++lightErr >= 3) {
      setFault("bh1750", fLight, true);
      lightStarted = false;  // khởi tạo lại ở lần sau
      lightRetryAt = now + 10000;
    }
  } else {
    lightErr = 0;
    mLight.push(lux);
    setFault("bh1750", fLight, false);
  }
  rd.light.ok = !fLight && !mLight.empty();
  if (rd.light.ok) rd.light.v = mLight.value();
}

static void readDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  bool bad = isnan(t) || isnan(h) || t < -40 || t > 80 || h < 0 || h > 100;
  if (bad) {
    if (dhtNan < 255) dhtNan++;
  } else {
    dhtNan = 0;
    mTemp.push(t);
    mHum.push(h);
  }
  setFault("dht", fDht, dhtNan >= 5);
  rd.airTemp.ok = rd.airHum.ok = !fDht && !mTemp.empty();
  if (rd.airTemp.ok) {
    rd.airTemp.v = mTemp.value();
    rd.airHum.v = mHum.value();
  }
}

void sensorsBegin() {
  pinMode(pins::SOIL_PWR, OUTPUT);
  digitalWrite(pins::SOIL_PWR, LOW);
  pinMode(pins::US_TRIG, OUTPUT);
  digitalWrite(pins::US_TRIG, LOW);
  pinMode(pins::US_ECHO, INPUT);
  analogReadResolution(12);
  Wire.begin(pins::I2C_SDA, pins::I2C_SCL);
  dht.begin();
  uint32_t now = millis();
  soil1NormalAt = soil2NormalAt = now;  // cho 30 s ân hạn lúc khởi động
  nextFast = now + 500;
  nextDht = now + 2000;
}

void sensorsLoop() {
  uint32_t now = millis();
  if (!soilPowered && (int32_t)(now - nextFast) >= 0) {
    nextFast = now + FAST_PERIOD_MS;
    digitalWrite(pins::SOIL_PWR, HIGH);
    soilPowered = true;
    soilReadAt = now + SOIL_SETTLE_MS;
    readUltrasonic();
    readLight(now);
  }
  if (soilPowered && (int32_t)(now - soilReadAt) >= 0) {
    readSoil(now);
    haveData = true;
  }
  if ((int32_t)(now - nextDht) >= 0) {
    nextDht = now + DHT_PERIOD_MS;
    readDht();
  }
}

const Readings& sensorReadings() { return rd; }
bool sensorsHaveData() { return haveData; }

static void printMetric(const char* name, const Metric& m, const char* unit) {
  if (m.ok) Serial.printf("%s=%.1f%s ", name, m.v, unit);
  else Serial.printf("%s=-- ", name);
}

void sensorsPrint() {
  printMetric("dat1", rd.soil1, "%");
  printMetric("dat2", rd.soil2, "%");
  printMetric("dat", rd.soil, "%");
  printMetric("T", rd.airTemp, "C");
  printMetric("H", rd.airHum, "%");
  printMetric("lux", rd.light, "");
  printMetric("be", rd.tank, "%");
  Serial.printf("(%.1f cm)\n", rd.tankRawCm);
}
