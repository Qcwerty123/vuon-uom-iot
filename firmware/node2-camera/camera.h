// camera.h — khởi tạo OV2640, chụp JPEG, đèn flash (đặc tả §7.2, §7.3)
#pragma once
#include <esp_camera.h>
#include "app.h"

bool cameraBegin();              // khởi tạo; lỗi thì tự thử lại trong cameraLoop()
void cameraLoop();               // tắt flash hẹn giờ, thử khởi tạo lại khi camera lỗi
bool cameraReady();
void cameraApplyConfig();        // áp frame_size, jpeg_quality từ cfg

// Chụp 1 ảnh JPEG. useFlash: bật flash + bỏ cfg.warmupFrames khung đầu.
// Trả về nullptr nếu lỗi. Gọi cameraRelease() ngay khi dùng xong.
camera_fb_t* cameraGrab(bool useFlash);
void cameraRelease(camera_fb_t* fb);

bool flashWanted(int overrideFlash);   // -1 = theo cfg.flash; 0 = tắt; 1 = bật
void flashOnFor(uint16_t seconds);     // lệnh flash (≤ 10 s)
void flashOff();
bool flashIsOn();
