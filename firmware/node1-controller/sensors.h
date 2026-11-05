// sensors.h — đọc, lọc trung vị, phát hiện cảm biến lỗi, hợp nhất 2 cảm biến đất (đặc tả §5.7, §6.3, §6.4)
#pragma once
#include "app.h"

void sensorsBegin();
void sensorsLoop();                 // không chặn; tự chia chu kỳ 2 s / 2,5 s
const Readings& sensorReadings();
bool sensorsHaveData();             // đã có ít nhất một chu kỳ đo
void sensorsPrint();                // in ra Serial để gỡ lỗi
