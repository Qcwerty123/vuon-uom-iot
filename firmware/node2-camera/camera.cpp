#include "camera.h"
#include "config_store.h"
#include "protocol.h"
#include "net.h"

// Sơ đồ chân camera của board AI-Thinker (giống ví dụ CameraWebServer)
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

static const framesize_t FRAME_MAP[FRAME_COUNT] = {
  FRAMESIZE_VGA, FRAMESIZE_SVGA, FRAMESIZE_XGA, FRAMESIZE_HD, FRAMESIZE_SXGA, FRAMESIZE_UXGA,
};
static const uint32_t REINIT_GAP_MS = 30000;

static bool ready = false, fault = false, hasPsram = false;
static uint8_t grabFails = 0;
static uint32_t retryAt = 0;
static bool flashOn = false, flashTimed = false;
static uint32_t flashOffAt = 0;

static void setFault(bool f) {
  if (fault == f) return;
  fault = f;
  emitEvent(f ? "sensor_fault" : "sensor_ok", [](JsonObject d) { d["sensor"] = "camera"; });
  Serial.printf("[cam] camera %s\n", f ? "LOI" : "OK");
}

static bool initCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;
  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;
  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;
  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;
  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.fb_count = 1;
  c.grab_mode = CAMERA_GRAB_LATEST;  // luôn lấy khung mới nhất
  hasPsram = psramFound();
  if (hasPsram) {
    c.frame_size = FRAMESIZE_UXGA;   // cấp buffer theo khung lớn nhất, sau đó hạ theo cấu hình
    c.jpeg_quality = 10;
    c.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[cam] KHONG thay PSRAM: kiem tra menu Tools > PSRAM = Enabled");
    c.frame_size = FRAMESIZE_SVGA;
    c.jpeg_quality = 12;
    c.fb_location = CAMERA_FB_IN_DRAM;
  }
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("[cam] khoi tao that bai 0x%x (kiem tra cap camera, nguon 5V/2A)\n", (unsigned)err);
    return false;
  }
  return true;
}

void cameraApplyConfig() {
  if (!ready) return;
  sensor_t* s = esp_camera_sensor_get();
  if (!s) return;
  uint8_t idx = cfg.frameSize;
  if (!hasPsram && idx > 1) idx = 1;  // không có PSRAM thì tối đa SVGA
  s->set_framesize(s, FRAME_MAP[idx]);
  s->set_quality(s, cfg.jpegQuality);
}

bool cameraBegin() {
  digitalWrite(pins::FLASH_LED, LOW);
  pinMode(pins::FLASH_LED, OUTPUT);
  digitalWrite(pins::FLASH_LED, LOW);
  ready = initCamera();
  if (ready) {
    cameraApplyConfig();
    Serial.println("[cam] camera OK");
  } else {
    setFault(true);
    retryAt = millis() + REINIT_GAP_MS;
  }
  return ready;
}

void cameraLoop() {
  uint32_t now = millis();
  if (flashTimed && (int32_t)(now - flashOffAt) >= 0) flashOff();
  if (!ready && (int32_t)(now - retryAt) >= 0) {
    Serial.println("[cam] thu khoi tao lai camera...");
    esp_camera_deinit();
    ready = initCamera();
    if (ready) {
      cameraApplyConfig();
      grabFails = 0;
      setFault(false);
    } else {
      setFault(true);
      retryAt = now + REINIT_GAP_MS;
    }
  }
}

bool cameraReady() { return ready; }

camera_fb_t* cameraGrab(bool useFlash) {
  if (!ready) return nullptr;
  flashTimed = false;
  if (useFlash) {
    digitalWrite(pins::FLASH_LED, HIGH);
    flashOn = true;
    delay(150);
  }
  // Khung đầu có thể là khung cũ trong buffer; khi bật flash cần thêm vài khung để camera chỉnh phơi sáng
  uint8_t discard = useFlash ? (cfg.warmupFrames > 0 ? cfg.warmupFrames : 1) : 1;
  for (uint8_t i = 0; i < discard; i++) {
    camera_fb_t* old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
  }
  camera_fb_t* fb = esp_camera_fb_get();
  if (useFlash) flashOff();
  if (!fb || fb->format != PIXFORMAT_JPEG || fb->len == 0) {
    if (fb) esp_camera_fb_return(fb);
    if (++grabFails >= 3) {
      setFault(true);
      ready = false;           // khởi tạo lại ở cameraLoop()
      retryAt = millis();
    }
    return nullptr;
  }
  grabFails = 0;
  setFault(false);
  return fb;
}

void cameraRelease(camera_fb_t* fb) {
  if (fb) esp_camera_fb_return(fb);
}

bool flashWanted(int overrideFlash) {
  if (overrideFlash >= 0) return overrideFlash == 1;
  if (cfg.flash == FLASH_ON) return true;
  if (cfg.flash == FLASH_OFF) return false;
  uint64_t ms = nowMs();                // auto: bật trong 19h–6h giờ Việt Nam
  if (ms == 0) return false;            // chưa có giờ thì không bật
  uint32_t hour = uint32_t((ms / 1000 + TZ_OFFSET_H * 3600ULL) / 3600 % 24);
  return hour >= 19 || hour < 6;
}

void flashOnFor(uint16_t seconds) {
  digitalWrite(pins::FLASH_LED, HIGH);
  flashOn = true;
  flashTimed = true;
  flashOffAt = millis() + uint32_t(seconds) * 1000UL;
}

void flashOff() {
  digitalWrite(pins::FLASH_LED, LOW);
  flashOn = false;
  flashTimed = false;
}

bool flashIsOn() { return flashOn; }
