/*
 * test-hardware.ino — Sketch chẩn đoán phần cứng Node 1
 *
 * Dùng cùng docs/huong-dan-lap-dat-phan-cung.md (Phần C, Phụ lục 1, Phụ lục 3).
 * Mỗi lệnh test một linh kiện. Lắp tới công đoạn nào thì chạy lệnh của công đoạn đó.
 *
 * Arduino IDE 2:
 *   Board: NodeMCU-32S (hoặc ESP32 Dev Module)
 *   Serial Monitor: 115200 baud, kết thúc dòng "New Line"
 *
 * Thư viện: DHT sensor library + Adafruit Unified Sensor, BH1750, Keypad, U8g2
 * (xem firmware/LIBRARIES.md). Cần tạo tab secrets.h từ secrets.example.h.
 *
 * Gán chân khớp docs/dac-ta-he-thong.md §5.2.
 */

#include <WiFi.h>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include <Keypad.h>
#include <U8g2lib.h>
#include <esp_system.h>
#include "secrets.h"

// ------------------------------------------------------------
// Cấu hình
// ------------------------------------------------------------
// 1 = OLED chip SH1106 (thường gặp ở màn 1.3"), 0 = SSD1306
#define OLED_IS_SH1106 1

// ------------------------------------------------------------
// Gán chân
// ------------------------------------------------------------
const int PIN_SOIL1 = 34;   // ADC1, chỉ đầu vào
const int PIN_SOIL2 = 35;   // ADC1, chỉ đầu vào
const int PIN_DHT   = 4;
const int PIN_SDA   = 21;
const int PIN_SCL   = 22;
const int PIN_TRIG  = 5;
const int PIN_ECHO  = 18;   // BẮT BUỘC qua cầu chia áp 1k/2k
const int PIN_SOIL_PWR = 32; // cấp VCC cho 2 cảm biến đất loại điện trở, chỉ bật khi đo
const int PIN_PROBE = 36;   // chân VP. Lệnh 'a': CHỈ đưa tín hiệu <= 3,3 V vào chân này

const int   RELAY_COUNT = 3;
const int   RELAY_PINS[RELAY_COUNT]  = {26, 27, 25};
const char* RELAY_NAMES[RELAY_COUNT] = {"Relay 1 - Bom", "Relay 2 - Quat", "Relay 3 - Du phong"};

const byte KP_ROWS = 4;
const byte KP_COLS = 3;
byte rowPins[KP_ROWS] = {13, 14, 16, 17};
byte colPins[KP_COLS] = {19, 23, 33};
char keyMap[KP_ROWS][KP_COLS] = {
  {'1', '2', '3'},
  {'4', '5', '6'},
  {'7', '8', '9'},
  {'*', '0', '#'}
};

// ------------------------------------------------------------
// Đối tượng
// ------------------------------------------------------------
Keypad keypad = Keypad(makeKeymap(keyMap), rowPins, colPins, KP_ROWS, KP_COLS);
DHT    dht(PIN_DHT, DHT22);
BH1750 lightMeter(0x23);
#if OLED_IS_SH1106
U8G2_SH1106_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);
#else
U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);
#endif

bool relayActiveHigh = true;   // jumper H trên module relay (khuyên dùng với ESP32)
bool bh1750Ready     = false;
bool oledReady       = false;
int  oledCounter     = 0;

// ------------------------------------------------------------
// Relay
// ------------------------------------------------------------
void relayWrite(int idx, bool on) {
  bool level = relayActiveHigh ? on : !on;
  digitalWrite(RELAY_PINS[idx], level ? HIGH : LOW);
}

void allRelaysOff() {
  for (int i = 0; i < RELAY_COUNT; i++) relayWrite(i, false);
}

// ------------------------------------------------------------
// Tiện ích
// ------------------------------------------------------------
void printResetReason() {
  Serial.print("Ly do khoi dong lan truoc: ");
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  Serial.println("bat nguon"); break;
    case ESP_RST_EXT:      Serial.println("chan EN / nut RESET"); break;
    case ESP_RST_SW:       Serial.println("reset phan mem"); break;
    case ESP_RST_PANIC:    Serial.println("loi chuong trinh (panic)"); break;
    case ESP_RST_BROWNOUT: Serial.println("SUT AP (brownout)! Kiem tra nguon, tu 1000uF, diode, GND chung"); break;
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:      Serial.println("watchdog"); break;
    default:               Serial.println((int)esp_reset_reason()); break;
  }
}

void printMenu() {
  Serial.println();
  Serial.println("========== TEST PHAN CUNG NODE 1 ==========");
  Serial.println(" h  : menu nay");
  Serial.println(" w  : ket noi WiFi (sua secrets.h truoc)        [C1]");
  Serial.println(" i  : quet bus I2C                               [C2]");
  Serial.println(" o  : hien 'OLED OK' len man hinh                [C2]");
  Serial.println(" l  : doc anh sang BH1750                        [C2]");
  Serial.println(" d  : doc DHT22                                  [C3]");
  Serial.println(" s  : doc 2 cam bien dat (ADC)                   [C4]");
  Serial.println(" k  : in phim bam keypad trong 20 giay           [C5]");
  Serial.println(" kp : do chan keypad (khong can dong ho)         [C5, PL3]");
  Serial.println(" u  : do khoang cach HC-SR04                     [C7]");
  Serial.println(" 1  : bat relay 1 (bom) 3 giay                   [C8, C10]");
  Serial.println(" 2  : bat relay 2 (quat) 3 giay                  [C8, C9]");
  Serial.println(" 3  : bat relay 3 (du phong) 3 giay              [C8]");
  Serial.println(" r  : dao logic kich relay H <-> L               [C8]");
  Serial.println(" a  : do dien ap chan VP/GPIO36 (<= 3,3 V)       [PL3]");
  Serial.printf ("Relay hien dang kich muc %s. OLED: %s\n",
                 relayActiveHigh ? "CAO (H)" : "THAP (L)",
                 OLED_IS_SH1106 ? "SH1106" : "SSD1306");
  Serial.println("===========================================");
}

// ------------------------------------------------------------
// Các bài test
// ------------------------------------------------------------
void testWifi() {
  Serial.printf("Ket noi WiFi '%s'", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  OK. IP: %s   RSSI: %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("  THAT BAI. Kiem tra ten/mat khau, WiFi phai la 2.4 GHz (ESP32 khong ho tro 5 GHz).");
  }
}

void scanI2C() {
  int n = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  Tim thay 0x%02X", addr);
      if (addr == 0x3C || addr == 0x3D) Serial.print("  (OLED)");
      if (addr == 0x23 || addr == 0x5C) Serial.print("  (BH1750)");
      Serial.println();
      n++;
    }
  }
  Serial.printf("  Tong: %d thiet bi. Mong doi: 0x3C (OLED) va 0x23 (BH1750).\n", n);
  if (n == 0) Serial.println("  Khong thay gi: kiem tra dao SDA/SCL, GND, nguon 3V3.");
}

void testOled() {
  if (!oledReady) {
    oled.begin();
    oledReady = true;
  }
  oledCounter++;
  char line[24];
  snprintf(line, sizeof(line), "Lan thu: %d", oledCounter);
  oled.clearBuffer();
  oled.drawFrame(0, 0, 128, 64);
  oled.setFont(u8g2_font_ncenB12_tr);
  oled.drawStr(8, 26, "OLED OK");
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawStr(8, 48, line);
  oled.sendBuffer();
  Serial.println("  Da gui 'OLED OK' len man hinh.");
  Serial.println("  Man nhieu / lech 2 cot: doi OLED_IS_SH1106 o dau file roi nap lai.");
}

void testLight() {
  if (!bh1750Ready) {
    bh1750Ready = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire);
    if (!bh1750Ready) {
      Serial.println("  LOI: khong khoi tao duoc BH1750. Chay 'i' de kiem tra bus I2C.");
      return;
    }
    delay(200);
  }
  for (int i = 0; i < 3; i++) {
    float lux = lightMeter.readLightLevel();
    if (lux < 0) Serial.println("  Loi doc BH1750");
    else         Serial.printf("  Anh sang: %.1f lux\n", lux);
    delay(500);
  }
  Serial.println("  Lay tay che: lux giam manh. Soi den dien thoai: lux tang manh.");
}

void testDht() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (isnan(h) || isnan(t)) {
    Serial.println("  LOI doc DHT22: kiem tra chan OUT (GPIO4), nguon 3V3; cho >= 2 giay giua 2 lan doc.");
  } else {
    Serial.printf("  Nhiet do: %.1f C   Do am: %.1f %%RH\n", t, h);
  }
}

void testSoil() {
  long sum1 = 0, sum2 = 0;
  digitalWrite(PIN_SOIL_PWR, HIGH);   // bật nguồn cảm biến
  delay(100);                         // chờ mạch ổn định
  for (int i = 0; i < 10; i++) {
    sum1 += analogRead(PIN_SOIL1);
    sum2 += analogRead(PIN_SOIL2);
    delay(20);
  }
  digitalWrite(PIN_SOIL_PWR, LOW);    // tắt ngay để giảm ăn mòn que đo
  Serial.printf("  Dat 1 (GPIO34): ADC = %ld\n", sum1 / 10);
  Serial.printf("  Dat 2 (GPIO35): ADC = %ld\n", sum2 / 10);
  Serial.println("  Ngoai khong khi -> so LON (DRY). Trong nuoc -> so NHO (WET). Ghi vao nhat ky.");
  Serial.println("  Luon 0 hoac 4095: sai chan AO, mat nguon, que chua noi.");
}

void testKeypad() {
  Serial.println("  Bam phim trong 20 giay...");
  unsigned long t0 = millis();
  while (millis() - t0 < 20000) {
    char k = keypad.getKey();
    if (k) Serial.printf("  Phim: %c\n", k);
    delay(5);
  }
  Serial.println("  Het thoi gian. Ky tu lon xon -> sai thu tu day, chay 'kp' de do lai.");
}

// Dò chân keypad bằng phần mềm: kéo lần lượt từng chân xuống LOW,
// chân nào khác đọc thấy LOW thì 2 chân đó đang được nối qua phím đang bấm.
void probeKeypad() {
  const int N = 7;
  const int pins[N] = {13, 14, 16, 17, 19, 23, 33};
  Serial.println("  Do chan keypad trong 30 giay.");
  Serial.println("  Bam va giu lan luot phim 1, 5, 9, # (moi phim khoang 1 giay).");
  int lastA = -1, lastB = -1;
  unsigned long t0 = millis();
  while (millis() - t0 < 30000) {
    int foundA = -1, foundB = -1;
    for (int i = 0; i < N && foundA < 0; i++) {
      for (int j = 0; j < N; j++) pinMode(pins[j], INPUT_PULLUP);
      pinMode(pins[i], OUTPUT);
      digitalWrite(pins[i], LOW);
      delayMicroseconds(50);
      for (int j = 0; j < N; j++) {
        if (j != i && digitalRead(pins[j]) == LOW) {
          foundA = i;
          foundB = j;
          break;
        }
      }
    }
    if (foundA >= 0 && (foundA != lastA || foundB != lastB)) {
      Serial.printf("  Thong nhau: GPIO%d <-> GPIO%d\n", pins[foundA], pins[foundB]);
      lastA = foundA;
      lastB = foundB;
    }
    if (foundA < 0) {
      lastA = -1;
      lastB = -1;
    }
    delay(20);
  }
  for (int j = 0; j < N; j++) pinMode(pins[j], INPUT_PULLUP);
  Serial.println("  Xong. Doi chieu GPIO voi day keypad P1..P7 da ghi de suy ra hang/cot.");
}

void testUltrasonic() {
  for (int i = 0; i < 5; i++) {
    digitalWrite(PIN_TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_TRIG, LOW);
    unsigned long dur = pulseIn(PIN_ECHO, HIGH, 30000UL);
    if (dur == 0) {
      Serial.println("  Khong co xung ECHO: kiem tra 5V, GND chung, cau chia ap, TRIG/ECHO.");
    } else {
      Serial.printf("  Khoang cach: %.1f cm\n", dur * 0.0343f / 2.0f);
    }
    delay(100);
  }
}

void testRelay(int idx) {
  Serial.printf("  Bat %s trong 3 giay (kich muc %s)...\n",
                RELAY_NAMES[idx], relayActiveHigh ? "H" : "L");
  relayWrite(idx, true);
  delay(3000);
  relayWrite(idx, false);
  Serial.println("  Da tat. Neu ESP32 vua khoi dong lai -> loi nguon (xem 'Ly do khoi dong').");
}

void toggleRelayLogic() {
  relayActiveHigh = !relayActiveHigh;
  allRelaysOff();
  Serial.printf("  Relay chuyen sang kich muc %s. Tat ca relay da ve trang thai TAT.\n",
                relayActiveHigh ? "CAO (H)" : "THAP (L)");
}

void probeVoltage() {
  Serial.println("  Do chan VP / GPIO36 (CHI dua tin hieu <= 3,3 V vao chan nay):");
  for (int i = 0; i < 5; i++) {
    uint32_t mv = analogReadMilliVolts(PIN_PROBE);
    Serial.printf("    %lu mV\n", (unsigned long)mv);
    delay(200);
  }
  Serial.println("  Thu cau chia ECHO voi 3V3: dung ~2100-2300 mV;");
  Serial.println("  ~1000-1200 mV: dao 2 dien tro; ~3300 mV: thieu 2k xuong GND.");
}

void handleCommand(const String& cmd) {
  Serial.print("> ");
  Serial.println(cmd);
  if      (cmd == "h")  printMenu();
  else if (cmd == "w")  testWifi();
  else if (cmd == "i")  scanI2C();
  else if (cmd == "o")  testOled();
  else if (cmd == "l")  testLight();
  else if (cmd == "d")  testDht();
  else if (cmd == "s")  testSoil();
  else if (cmd == "k")  testKeypad();
  else if (cmd == "kp") probeKeypad();
  else if (cmd == "u")  testUltrasonic();
  else if (cmd == "1")  testRelay(0);
  else if (cmd == "2")  testRelay(1);
  else if (cmd == "3")  testRelay(2);
  else if (cmd == "r")  toggleRelayLogic();
  else if (cmd == "a")  probeVoltage();
  else Serial.println("  Lenh khong hop le. Go 'h' de xem menu.");
}

// ------------------------------------------------------------
void setup() {
  // Tắt relay TRƯỚC mọi việc khác để tải không bật lúc khởi động
  for (int i = 0; i < RELAY_COUNT; i++) {
    relayWrite(i, false);
    pinMode(RELAY_PINS[i], OUTPUT);
    relayWrite(i, false);
  }

  Serial.begin(115200);
  delay(300);

  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_SOIL_PWR, OUTPUT);
  digitalWrite(PIN_SOIL_PWR, LOW);
  analogReadResolution(12);

  Wire.begin(PIN_SDA, PIN_SCL);
  dht.begin();

  Serial.println();
  printResetReason();
  printMenu();
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) handleCommand(cmd);
  }
}
