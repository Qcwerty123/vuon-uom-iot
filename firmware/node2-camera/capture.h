// capture.h — lịch chụp, chụp theo lệnh, upload HTTP có thử lại (đặc tả §7.1, §8.9)
#pragma once
#include "app.h"

void captureBegin();
void captureLoop();

// Yêu cầu chụp. cmdId = nullptr khi chụp theo lịch. flashOverride: -1 theo cấu hình, 0 tắt, 1 bật.
// Trả về nullptr nếu nhận việc, hoặc lý do từ chối: "busy", "camera_fault".
const char* captureRequest(const char* cmdId, int flashOverride);
bool captureBusy();
void captureReschedule();     // gọi khi đổi capture_interval_min
uint32_t captureOkCount();
uint32_t captureFailCount();
uint32_t captureNextInS();    // số giây tới lần chụp theo lịch
