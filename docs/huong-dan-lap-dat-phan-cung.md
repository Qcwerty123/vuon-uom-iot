# Hướng dẫn lắp đặt phần cứng — Hệ thống chăm sóc vườn ươm thông minh

> Áp dụng cho bộ linh kiện hiện có của nhóm · v1.3 · 07/11/2026 (OLED SH1106, cảm biến đất cấp nguồn qua GPIO32, đèn LED trên relay kênh 3)
>
> Bảng gán chân khớp với `dac-ta-he-thong.md` §5. Nếu đổi chân nào, sửa cả hai tài liệu và firmware.

---

## Mục lục

- **Phần A — Chuẩn bị:** A1 nguyên tắc vàng · A2 dụng cụ · A3 kiểm tra linh kiện trước khi lắp · A4 quy ước dây · A5 cách đo bằng đồng hồ vạn năng · A6 cài Arduino IDE 2 và thư viện
- **Phần B — Bức tranh tổng thể Node 1:** B1 sơ đồ khối · B2 hai nhánh nguồn · B3 bảng đấu dây tổng hợp · B4 thứ tự lắp
- **Phần C — Lắp Node 1 theo 11 công đoạn** (+ C9b đèn)
- **Phần D — Lắp Node 2 (ESP32-CAM)**
- **Phần E — Lắp đặt vào mô hình vườn ươm**
- **Phần F — Nghiệm thu cuối và xử lý lỗi**
- **Phụ lục:** 1 sketch chẩn đoán · 2 nhật ký lắp đặt · 3 lắp khi không có đồng hồ vạn năng

---

# PHẦN A — CHUẨN BỊ

## A1. Nguyên tắc vàng

1. **Lắp một phần, kiểm tra xong mới lắp phần tiếp theo.** Lắp hết rồi mới cắm điện thì khi lỗi không biết lỗi ở đâu.
2. **Rút toàn bộ nguồn trước khi cắm hoặc rút bất kỳ dây nào**, gồm cả USB và củ sạc.
3. **Mọi GND phải nối chung:** ESP32, domino, relay, HC-SR04, tất cả cảm biến.
4. **Không bao giờ đưa 5 V vào chân GPIO của ESP32.** GPIO chỉ chịu 3,3 V. Chân ECHO của HC-SR04 bắt buộc đi qua cầu chia áp.
5. **Đọc chữ in trên từng module trước khi cắm.** Thứ tự chân VCC/GND khác nhau giữa các nhà sản xuất, nhất là màn OLED.
6. **Đo trước, cấp điện sau.** Trước mỗi lần cấp điện, đo xem +5 V và GND có bị chập không (§A5).
7. **Tải công suất (bơm, quạt) không lấy điện từ ESP32**, chỉ lấy từ domino 5 V qua relay.
8. **Bơm phải ngâm trong nước** trước khi cho chạy. Chạy khan vài chục giây là hỏng.
9. **Không đấu điện lưới 220 V** vào bất kỳ phần nào của mạch [ĐỀ 10].

## A2. Dụng cụ

| Dụng cụ | Bắt buộc | Dùng để |
|---|---|---|
| Đồng hồ vạn năng | Có | Đo điện áp, kiểm tra chập, dò chân keypad |
| Tua vít dẹt nhỏ | Có | Siết cọc vít relay, domino |
| Kìm tuốt dây, kìm cắt | Có | Dây đồng 0,6 mm, cáp nguồn |
| Băng keo điện / ống co nhiệt | Có | Bọc mối nối |
| Bút dạ, băng keo giấy | Nên có | Đánh dấu dây |
| Keo silicon hoặc keo nến | Nên có | Bọc đầu cảm biến đất |
| Thước kẻ ≥ 30 cm | Nên có | Kiểm tra HC-SR04 |
| Cốc nước, khăn | Có | Hiệu chuẩn cảm biến đất, thử bơm |
| Máy tính có Arduino IDE 2 | Có | Nạp code chẩn đoán (§A6) |
| Điện thoại | Có | Chụp ảnh từng công đoạn cho báo cáo |

## A3. Kiểm tra linh kiện trước khi lắp

### Danh sách và vai trò

| # | Linh kiện | Thuộc | Ghi chú kiểm tra |
|---|---|---|---|
| 1 | ESP32-WROOM-32 NodeMCU-32S 30 chân | Node 1 | Đếm đủ 30 chân, không cong |
| 2 | Đế ra chân ESP32 30 chân | Node 1 | Xem chữ in: hàng G-V-S, jumper chọn điện áp (nếu có) |
| 3 | 2 × cảm biến độ ẩm đất | Node 1 | Gồm que đo + mạch nhỏ 4 chân (VCC, GND, DO, AO) |
| 4 | DHT22 | Node 1 | Module 3 chân (+, OUT, −) hoặc cảm biến trần 4 chân |
| 5 | BH1750 (GY-302) | Node 1 | 5 chân: VCC, GND, SCL, SDA, ADDR |
| 6 | OLED 1.3" I2C, chip SH1106 | Node 1 | 4 chân. **Đọc thứ tự VCC/GND** |
| 7 | HC-SR04 | Node 1 | 4 chân: VCC, TRIG, ECHO, GND |
| 8 | Keypad 3×4 mềm | Node 1 | Cáp dẹt 7 chân |
| 9 | Relay 4 kênh 5 V, chọn mức H/L | Node 1 | Mỗi kênh có jumper H/L; 3 cọc vít COM/NO/NC |
| 10 | Bơm chìm mini 3–6 V + ống φ6 | Node 1 | 2 dây đỏ/đen |
| 11 | Quạt 5 V | Node 1 | 2 dây đỏ/đen |
| 12 | Động cơ mini 3–6 V | Dự phòng, hoặc chế thành quạt thay quạt 5 V (C3) | Nếu chế: gắn cánh nhựa, đấu vào relay kênh 2 như quạt (§C9) |
| 13 | Tụ 1000 µF 16 V | Node 1, 2 | Chân dài là (+), vạch trắng là (−) |
| 14 | Diode 1N4007 | Node 1 | Vạch bạc là cực âm (K) |
| 15 | Điện trở 1 kΩ (nâu-đen-đỏ), 2 kΩ (đỏ-đen-đỏ) | Node 1 | Đo lại bằng đồng hồ cho chắc |
| 16 | Domino 12 cực | Node 1 | Dùng làm "thanh cái" +5 V và GND |
| 17 | Breadboard 400 lỗ | Node 1 | Bus I2C, cầu chia áp |
| 18 | Dây đực-cái, cái-cái, dây đồng 0,6 mm, header | Chung | |
| 19 | ESP32-CAM OV2640 + đế nạp MB | Node 2 | Cáp camera đã gắn chặt |
| 20 | DHT11 | Dự phòng | Không gắn lên Node 2 (đặc tả C4) |
| 21 | Củ sạc 5V/3A, 5V/2A | Nguồn | Đo điện áp ra trước khi dùng |
| 22 | Đèn LED 5 V ánh trắng ≤ 5 W (**cần mua**) | Node 1 — relay kênh 3 | Xem công suất trên nhãn; không dùng đèn tím |

### Còn thiếu: đầu nối nguồn từ củ sạc vào domino

Danh sách chưa có món nào đưa điện từ củ sạc ra dây. Chọn một trong hai cách:

| Cách | Làm thế nào | Đánh giá |
|---|---|---|
| **B (khuyên dùng)** | Mua module USB cái ra 2 chân (USB-A hoặc USB-C "power breakout"), cắm cáp từ củ sạc vào. Hoặc mua jack DC cái có cọc vít kèm củ 5 V đầu DC | An toàn, gọn, rẻ |
| A (tạm thời) | Cắt một cáp USB cũ, giữ đầu USB-A. Lấy dây đỏ (+5 V) và đen (GND). Cắt ngắn và bọc riêng từng dây còn lại (D+, D−) | Được, nhưng **bắt buộc đo cực tính** vì màu dây không phải cáp nào cũng đúng chuẩn |

### Kiểm tra củ sạc

Cắm củ sạc, đo giữa hai dây ra (thang DC 20 V). Kết quả phải trong khoảng **4,9–5,3 V**. Ghi lại dây nào là (+).

### Kiểm tra cáp USB cho ESP32

Cắm ESP32 vào máy tính.

- **Windows:** mở Device Manager → Ports.
  - Thấy `Silicon Labs CP210x` → cài driver CP210x.
  - Thấy `USB-SERIAL CH340` → cài driver CH340.
  - Không thấy gì → cáp chỉ sạc, không truyền dữ liệu. Đổi cáp khác.
- **macOS / Linux:** xuất hiện `/dev/cu.usbserial-*` hoặc `/dev/ttyUSB0`.

## A4. Quy ước màu dây

Dùng thống nhất cho cả nhóm, ghi vào báo cáo:

| Màu | Ý nghĩa |
|---|---|
| **Đỏ** | +5 V |
| **Cam** | +3,3 V |
| **Đen / nâu** | GND |
| Vàng | Dữ liệu cảm biến analog |
| Xanh lá | I2C SDA |
| Xanh dương | I2C SCL |
| Trắng / xám | Điều khiển relay |
| Tím | HC-SR04 |
| Màu còn lại | Keypad |

Dán nhãn băng keo giấy ở hai đầu các dây dài, ví dụ "SDA", "R1", "PUMP+".

## A5. Cách đo bằng đồng hồ vạn năng

| Việc cần đo | Thang | Cách đo | Kết quả đúng |
|---|---|---|---|
| Kiểm tra chập nguồn | Thông mạch (biểu tượng loa) hoặc Ω | **Mạch chưa cấp điện.** Que đỏ vào +5 V, que đen vào GND | **Không kêu**, điện trở lớn (> vài trăm Ω; tụ lớn làm số tăng dần là bình thường) |
| Kiểm tra dây có thông | Thông mạch | Hai đầu dây | Kêu |
| Đo điện áp | DC 20 V | Que đen vào GND, que đỏ vào điểm cần đo | Đúng giá trị mong đợi ±5% |
| Đo điện trở | Ω 20 k | Hai chân điện trở, **không nằm trong mạch** | 1 kΩ: 0,98–1,02 k · 2 kΩ: 1,96–2,04 k |
| Kiểm tra diode | Thang diode | Que đỏ vào chân **không** vạch, que đen vào chân có vạch | 0,5–0,7 V; đảo que thì hiện "OL" |

Không có đồng hồ: xem **Phụ lục 3**.

## A6. Cài đặt phần mềm và thư viện (Arduino IDE 2)

Làm xong mục này **trước công đoạn C1**, vì từ C1 trở đi mỗi bước kiểm tra đều cần nạp code.

### A6.1. Nguyên tắc cho cả nhóm

- Cả nhóm dùng **Arduino IDE 2** và **cùng một phiên bản** core ESP32 và thư viện. Lệch phiên bản là nguyên nhân phổ biến nhất của chuyện "máy bạn build được, máy mình báo lỗi".
- Người cài đầu tiên ghi lại phiên bản của từng thứ vào file `firmware/LIBRARIES.md` trong repo (mẫu ở §A6.6). Những người sau cài **đúng các phiên bản đó**.
- Driver USB phải cài trước (§A3: CP210x hoặc CH340). Đế nạp của ESP32-CAM thường dùng chip CH340.

### A6.2. Cài Arduino IDE 2

1. Tải **Arduino IDE 2.x** từ trang chính thức của Arduino (`arduino.cc` → Software), chọn bản đúng hệ điều hành, cài như phần mềm bình thường.
2. Lần đầu mở, IDE có thể hỏi cài thêm driver: bấm **Đồng ý / Install**.
3. Kiểm tra thư mục sketchbook: `File → Preferences → Sketchbook location`. Thư viện sẽ được cài vào thư mục `libraries` bên trong. Nên để mặc định.

### A6.3. Cài core ESP32 (gói board)

1. `File → Preferences`. Ở ô **Additional boards manager URLs**, dán:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
   Nếu ô đã có URL khác, bấm biểu tượng bên phải ô để mở danh sách, thêm dòng này vào một dòng riêng. Bấm OK.
2. Mở **Boards Manager**: biểu tượng bảng mạch ở thanh bên trái, hoặc `Tools → Board → Boards Manager`, hoặc `Ctrl+Shift+B`.
3. Gõ `esp32`. Chọn gói **esp32 by Espressif Systems** (**không** chọn gói "Arduino ESP32 Boards" của Arduino). Chọn phiên bản **3.x mới nhất**, bấm **Install**.
4. Chờ cài xong. Gói khá nặng, lần đầu mất vài phút. Đừng đóng IDE giữa chừng.
5. Ghi số phiên bản vào `LIBRARIES.md`.

**Đạt khi:** `Tools → Board` có mục **esp32**, trong đó có **NodeMCU-32S**, **ESP32 Dev Module** và **AI Thinker ESP32-CAM**.

### A6.4. Cài thư viện

Mở **Library Manager**: biểu tượng chồng sách ở thanh bên trái, hoặc `Sketch → Include Library → Manage Libraries…`, hoặc `Ctrl+Shift+I`.

Gõ tên vào ô tìm kiếm, **kiểm tra đúng tên tác giả** (nhiều thư viện trùng tên), chọn phiên bản rồi bấm **Install**:

| # | Gõ tìm | Chọn đúng gói (tác giả) | Dùng cho | Node |
|---|---|---|---|---|
| 1 | `PubSubClient` | **PubSubClient** — Nick O'Leary | MQTT | 1, 2 |
| 2 | `ArduinoJson` | **ArduinoJson** — Benoit Blanchon (bản **7.x**) | Đóng gói / đọc JSON | 1, 2 |
| 3 | `DHT sensor library` | **DHT sensor library** — Adafruit | DHT22 | 1 |
| 4 | `BH1750` | **BH1750** — Christopher Laws | Cảm biến ánh sáng | 1 |
| 5 | `Keypad` | **Keypad** — Mark Stanley, Alexander Brevig | Keypad 3×4 | 1 |
| 6 | `U8g2` | **U8g2** — oliver | OLED 1.3" chip **SH1106** | 1 |

**Khi IDE hỏi cài thêm thư viện phụ thuộc** (hộp thoại "Install library dependencies"), bấm **INSTALL ALL**:

- DHT sensor library → kèm **Adafruit Unified Sensor**.

Bấm "Install without dependencies" sẽ gây lỗi thiếu file khi biên dịch.

**Không cần cài**, vì đã có sẵn trong core ESP32: `WiFi`, `HTTPClient`, `Preferences` (lưu NVS), `Wire` (I2C), thư viện camera `esp_camera.h`, NTP (`configTime`).

**HC-SR04 không cần thư viện**: đo bằng `pulseIn()` có sẵn.

**Cài đúng phiên bản đã thống nhất:** trong Library Manager, mỗi thư viện có ô chọn phiên bản cạnh nút Install. Chọn đúng số trong `LIBRARIES.md` rồi mới bấm Install. Nếu đã cài bản khác, chọn lại phiên bản rồi bấm Install để thay.

**Tắt tự cập nhật** để tránh lệch phiên bản giữa chừng: IDE hiện thông báo "Updates are available" thì bỏ qua. Chỉ cập nhật khi cả nhóm thống nhất.

### A6.5. Chọn board và cấu hình trong menu Tools

Mỗi lần đổi giữa Node 1 và Node 2, kiểm tra lại toàn bộ bảng này. Arduino IDE nhớ cấu hình theo từng sketch nhưng hay bị chọn nhầm.

| Mục trong `Tools` | **Node 1** (ESP32 NodeMCU-32S) | **Node 2** (ESP32-CAM) |
|---|---|---|
| Board | `esp32 → NodeMCU-32S` (nếu nạp lỗi, thử `ESP32 Dev Module`) | `esp32 → AI Thinker ESP32-CAM` |
| Port | Cổng COM của ESP32 (Windows: `COMx`; macOS: `/dev/cu.usbserial-…` hoặc `/dev/cu.wchusbserial-…`; Linux: `/dev/ttyUSB0`) | Cổng COM của đế MB |
| Upload Speed | `921600` (nạp lỗi thì hạ `115200`) | `460800` (nạp lỗi thì hạ `115200`) |
| Partition Scheme | `Default` | **`Huge APP (3MB No OTA/1MB SPIFFS)`** |
| PSRAM | — | `Enabled` (nếu menu có mục này) |
| Core Debug Level | `None` (đổi sang `Info` khi cần gỡ lỗi) | `None` |

Cách nhanh: ở thanh trên cùng có ô chọn board và cổng. Nếu IDE hiện "Unknown" khi cắm board CH340, bấm **Select other board and port…**, tìm board theo bảng trên rồi chọn cổng.

### A6.6. Tổ chức sketch trong repo

Arduino IDE yêu cầu **tên thư mục trùng tên file `.ino`**:

```
firmware/
  LIBRARIES.md                     # phiên bản core + thư viện cả nhóm dùng
  test-hardware/
    test-hardware.ino              # sketch chẩn đoán (Phụ lục 1)
    secrets.example.h              # mẫu, commit
    secrets.h                      # thật, KHÔNG commit
  node1-controller/
    node1-controller.ino
    secrets.example.h
    secrets.h                      # KHÔNG commit
    sensors.h / sensors.cpp ...    # các file khác hiện thành tab trong IDE
  node2-camera/
    node2-camera.ino
    secrets.example.h
    secrets.h                      # KHÔNG commit
```

**Tạo `secrets.h` trong IDE:**

1. Mở sketch.
2. Bấm nút **…** ở góc phải thanh tab → **New Tab**, gõ tên `secrets.h`.
3. Sao nội dung từ `secrets.example.h` sang, điền giá trị thật.
4. Trong `.ino` dùng `#include "secrets.h"` (dấu ngoặc kép, không phải `< >`).

**`.gitignore` ở gốc repo phải có:**

```
firmware/**/secrets.h
```

**Mẫu `firmware/LIBRARIES.md`** (người cài đầu tiên điền số phiên bản):

```
Arduino IDE: 2.x.x
Core: esp32 by Espressif Systems 3.x.x
PubSubClient (Nick O'Leary): x.x.x
ArduinoJson (Benoit Blanchon): 7.x.x
DHT sensor library (Adafruit): x.x.x
Adafruit Unified Sensor (Adafruit): x.x.x
BH1750 (Christopher Laws): x.x.x
Keypad (Mark Stanley, Alexander Brevig): x.x.x
U8g2 (oliver): x.x.x            # OLED SH1106
```

### A6.7. Serial Monitor và Serial Plotter

- Mở **Serial Monitor**: biểu tượng kính lúp góc trên bên phải, hoặc `Ctrl+Shift+M`. Khung Serial Monitor hiện ở phía dưới cửa sổ.
- Đặt tốc độ **115200 baud** (ô bên phải khung).
- Đặt kết thúc dòng là **New Line** (ô bên cạnh tốc độ). Sketch chẩn đoán đọc lệnh theo từng dòng; nếu để "No Line Ending" thì gõ lệnh không có phản hồi.
- Gõ lệnh vào ô nhập phía trên khung, bấm **Enter**.
- **Serial Plotter** (`Tools → Serial Plotter`) vẽ đồ thị giá trị in ra. Hữu ích khi hiệu chuẩn cảm biến đất. Serial Monitor và Serial Plotter không mở được cùng lúc.
- **Đóng Serial Monitor trước khi nạp code** nếu nạp báo cổng đang bận. IDE 2 thường tự xử lý, nhưng trên một số máy vẫn cần đóng tay.

### A6.8. Kiểm tra cài đặt thành công

**Bước 1 — biên dịch thử, chưa cần cắm board.** `File → New Sketch`, dán đoạn sau, chọn board **NodeMCU-32S**, bấm nút **Verify** (dấu ✓):

```cpp
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <BH1750.h>
#include <Keypad.h>
#include <U8g2lib.h>          // OLED SH1106
void setup() { Serial.begin(115200); }
void loop() {}
```

Khung Output báo **Done compiling**, không có dòng `No such file or directory` → đủ thư viện cho Node 1.

Với Node 2: chọn board **AI Thinker ESP32-CAM**, tạo sketch có `#include "esp_camera.h"`, bấm Verify. Không lỗi là core đã có thư viện camera.

**Bước 2 — nạp thật Node 1:** `File → Examples → 01.Basics → Blink`. Sửa `LED_BUILTIN` thành `2` nếu biên dịch báo không biết `LED_BUILTIN`. Bấm **Upload** (mũi tên →).

**Bước 3 — nạp thật Node 2:**

1. `File → Examples → ESP32 → Camera → CameraWebServer`. Ví dụ chỉ hiện khi đang chọn board ESP32.
2. Chọn model camera: tìm các dòng `#define CAMERA_MODEL_…` (nằm trong file `.ino` hoặc tab `board_config.h`, tùy phiên bản core). Bỏ comment dòng **`CAMERA_MODEL_AI_THINKER`**, comment dòng model đang bật.
3. Điền `ssid` và `password` của WiFi.
4. Upload theo §D2.

| Dấu hiệu thành công | Ở đâu |
|---|---|
| `Done compiling.` | Khung Output |
| Cuối quá trình nạp có dòng `Hard resetting via RTS pin...` và `Done uploading.` | Khung Output |
| Serial Monitor hiện chữ đọc được (không ra ký tự rác) | Serial Monitor ở 115200 |

### A6.9. Lỗi cài đặt và biên dịch thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Tools → Board` không có mục esp32 | Chưa dán URL hoặc chưa cài core | §A6.3 |
| Không thấy gói esp32 trong Boards Manager | URL dán sai hoặc mạng chặn | Kiểm tra lại URL (không thừa dấu cách); thử mạng khác |
| Cài core báo lỗi tải giữa chừng | Mạng yếu, gói lớn | Cài lại; dùng mạng ổn định hơn |
| `DHT.h` báo thiếu `Adafruit_Sensor.h` | Chưa cài Adafruit Unified Sensor | Cài thêm (Library Manager tìm `Adafruit Unified Sensor`) |
| `Multiple libraries were found for "WiFi.h"` | IDE thấy cả bản trong core và bản Arduino khác | Thường chỉ là cảnh báo. Xem dòng `Used:`; phải là thư viện trong core esp32 |
| Lỗi quanh `StaticJsonDocument` / `DynamicJsonDocument` | Code mẫu viết cho ArduinoJson 6, đang dùng bản 7 | Dùng `JsonDocument` (API bản 7) |
| `esp_camera.h: No such file` | Đang chọn board Node 1 | Chọn **AI Thinker ESP32-CAM** |
| `Sketch too big` khi nạp Node 2 | Phân vùng mặc định nhỏ | Partition Scheme **Huge APP** |
| Thư viện cũ báo lỗi biên dịch với core 3.x | Thư viện chưa cập nhật theo API core 3 | Cập nhật thư viện lên bản mới nhất; nếu vẫn lỗi, cả nhóm cùng hạ core xuống bản 2.0.x cuối cùng và ghi vào `LIBRARIES.md` |
| `Failed to connect to ESP32: Timed out…` | Chưa vào chế độ nạp | Node 1: giữ **BOOT** khi thấy `Connecting....`; Node 2: giữ **IO0**, bấm **RST**, thả IO0 rồi nạp |
| Port bị mờ, không chọn được | Driver, cáp sạc không có dây dữ liệu | §A3 |
| Serial Monitor ra ký tự rác | Sai baud | 115200 |
| Gõ lệnh không phản hồi | Line ending đang là "No Line Ending" | Chọn **New Line** |
| Bản tin MQTT dài không publish được | Buffer PubSubClient mặc định 256 byte | Trong code gọi `client.setBufferSize(1024)` |

### A6.10. Công cụ phụ trợ (dùng từ khi có broker)

| Công cụ | Dùng để |
|---|---|
| **MQTTX** (giao diện đồ họa) hoặc `mosquitto_pub` / `mosquitto_sub` | Xem bản tin thiết bị gửi lên, gửi thử lệnh xuống |
| Serial Plotter của Arduino IDE | Xem đồ thị cảm biến khi hiệu chuẩn |

### A6.11. (Tùy chọn) PlatformIO

Thành viên nào quen VS Code có thể dùng **PlatformIO IDE** thay Arduino IDE. Code `.ino` dùng chung được (đổi tên thành `src/main.cpp` và thêm `#include <Arduino.h>` ở đầu). Thư viện khai báo trong `platformio.ini` và tự tải khi build:

```ini
[env:node1]
platform = espressif32
board = nodemcu-32s
framework = arduino
monitor_speed = 115200
lib_deps =
    knolleary/PubSubClient
    bblanchon/ArduinoJson
    adafruit/DHT sensor library
    adafruit/Adafruit Unified Sensor
    claws/BH1750
    chris--a/Keypad
    olikraus/U8g2

[env:node2]
platform = espressif32
board = esp32cam
framework = arduino
monitor_speed = 115200
board_build.partitions = huge_app.csv
lib_deps =
    knolleary/PubSubClient
    bblanchon/ArduinoJson
```

Ghim phiên bản (ví dụ `bblanchon/ArduinoJson @ 7.x.x`) theo đúng `LIBRARIES.md`. Lưu ý nền tảng `espressif32` chính thức của PlatformIO có thể dùng core khác với bản trong Arduino IDE; nếu có khác biệt khi biên dịch, lấy Arduino IDE làm chuẩn.

---

# PHẦN B — BỨC TRANH TỔNG THỂ NODE 1

## B1. Sơ đồ khối

```
                         ┌───────────────── ESP32 (cấp bằng USB khi lắp ráp) ─────────────────┐
  [Đất 1]  AO ──────────►│ GPIO34                                       GPIO26 ├──► Relay IN1 ─► Bơm
  [Đất 2]  AO ──────────►│ GPIO35                                       GPIO27 ├──► Relay IN2 ─► Quạt
  [DHT22]  OUT ─────────►│ GPIO4                                        GPIO25 ├──► Relay IN3 ─► Đèn  
  [BH1750]+[OLED] SDA ◄─►│ GPIO21                                              │
                  SCL ◄─►│ GPIO22                                              │
  [HC-SR04] TRIG ◄───────│ GPIO5                                               │
            ECHO ─[chia áp 1k/2k]─► GPIO18                                     │
  [Keypad] hàng R1–R4 ◄──│ GPIO13, 14, 16, 17                                  │
           cột C1–C3 ───►│ GPIO19, 23, 33                                      │
                         │ 3V3 ──► VCC: DHT22, BH1750, OLED                    │
                         │ GPIO32 ──► VCC: đất ×2 (chỉ bật khi đo)             │
                         │ GND ──┐                                             │
                         └───────┼─────────────────────────────────────────────┘
                                 │  (GND chung — BẮT BUỘC)
  Củ sạc 5V/3A ─► Domino ── +5V ─┼─► Relay VCC, HC-SR04 VCC, COM relay 1, 2, 3
                          └─ GND ┴─► Relay GND, HC-SR04 GND, (−) bơm, (−) quạt, (−) đèn
                             Tụ 1000µF giữa +5V và GND
```

## B2. Hai nhánh nguồn

| Nhánh | Nguồn | Cấp cho | Vì sao tách |
|---|---|---|---|
| **3,3 V logic** | Chân 3V3 của ESP32 (ESP32 lấy điện từ USB); riêng cảm biến đất lấy từ GPIO32 | Cảm biến đất ×2, DHT22, BH1750, OLED | Mức tín hiệu khớp với GPIO 3,3 V |
| **5 V công suất** | Củ sạc 5V/3A → domino | Relay, HC-SR04, bơm, quạt, đèn | Bơm và quạt kéo dòng lớn và gây nhiễu; không để dòng này đi qua ESP32 |

- **Trong lúc lắp và test:** ESP32 lấy điện từ USB máy tính, nhánh 5 V lấy từ củ sạc. Hai nhánh **chỉ nối chung GND**. Không nối +5 V domino vào VIN.
- **Khi chạy độc lập** (không còn máy tính): rút USB, nối +5 V domino vào chân **VIN** của ESP32 (§C11).

Ngân sách dòng nhánh 5 V (ước lượng):

| Tải | Dòng |
|---|---|
| Cuộn relay | ~70 mA/kênh × 3 |
| Bơm | 100–300 mA (lúc khởi động cao hơn) |
| Quạt | 100–200 mA |
| Đèn LED ≤ 5 W | ≤ 1 A |
| HC-SR04 | 15 mA |
| ESP32 (khi chạy độc lập) | ~250 mA đỉnh |
| **Tổng** | **< 2 A**. Củ 3 A vẫn đủ, đèn dùng chung nguồn (đặc tả C25) |

## B3. Bảng đấu dây tổng hợp Node 1

| Linh kiện | Chân linh kiện | Nối tới | Đi qua |
|---|---|---|---|
| Cảm biến đất 1 | VCC / GND / AO / DO | **GPIO32** (qua hàng "SOIL-VCC") / GND / **GPIO34** / để trống | Breadboard + đế ra chân |
| Cảm biến đất 2 | VCC / GND / AO / DO | **GPIO32** (qua hàng "SOIL-VCC") / GND / **GPIO35** / để trống | Breadboard + đế ra chân |
| DHT22 (module) | + / OUT / − | 3V3 / **GPIO4** / GND | Đế ra chân |
| BH1750 | VCC / GND / SDA / SCL / ADDR | 3V3 / GND / **GPIO21** / **GPIO22** / để trống | Breadboard (bus I2C) |
| OLED 1.3" | VCC / GND / SDA / SCL | 3V3 / GND / **GPIO21** / **GPIO22** | Breadboard (bus I2C) |
| HC-SR04 | VCC / GND / TRIG | **+5V domino** / GND / **GPIO5** | |
| HC-SR04 | ECHO | **Cầu chia áp** → **GPIO18** | Breadboard |
| Keypad | 4 dây hàng | **GPIO13, 14, 16, 17** | Đế ra chân |
| Keypad | 3 dây cột | **GPIO19, 23, 33** | Đế ra chân |
| Relay 4 kênh | VCC / GND | +5V domino / GND domino | |
| Relay 4 kênh | IN1 / IN2 / IN3 / IN4 | **GPIO26** / **GPIO27** / **GPIO25** / để trống | Đế ra chân |
| Relay kênh 1 | COM / NO / NC | +5V domino / (+) bơm / để trống | Cọc vít |
| Relay kênh 2 | COM / NO / NC | +5V domino / (+) quạt / để trống | Cọc vít |
| Relay kênh 3 | COM / NO / NC | +5V domino / (+) đèn / để trống | Cọc vít |
| Bơm, quạt, đèn | (−) | GND domino | |
| Diode 1N4007 | ×2 | Song song ngược với bơm, với quạt (đèn LED không cần) | Tại cọc vít hoặc đầu dây tải |
| Tụ 1000 µF | (+) / (−) | +5V / GND domino | |

**Chân tránh dùng:** GPIO0, 2, 12, 15 (ảnh hưởng chế độ khởi động); 6–11 (flash nội); 1, 3 (Serial).

**Chân đo của sketch chẩn đoán:** lệnh `a` đọc điện áp ở chân **VP (GPIO36)**. Mạch chính không dùng chân này.

## B4. Thứ tự lắp

| Công đoạn | Nội dung | Nguồn khi test |
|---|---|---|
| C1 | ESP32 + đế ra chân | USB |
| C2 | Bus I2C: OLED + BH1750 | USB |
| C3 | DHT22 | USB |
| C4 | 2 cảm biến độ ẩm đất | USB |
| C5 | Keypad | USB |
| C6 | Nhánh nguồn 5 V: củ sạc → domino → tụ | Củ sạc (ESP32 chưa nối) |
| C7 | HC-SR04 + cầu chia áp | USB + củ sạc, chung GND |
| C8 | Module relay, **chưa nối tải** | USB + củ sạc |
| C9 | Quạt + diode vào relay 2 | USB + củ sạc |
| C9b | Đèn LED vào relay 3 + hiệu chuẩn ΔE_LED | USB + củ sạc |
| C10 | Bơm + diode vào relay 1 | USB + củ sạc |
| C11 | Chạy độc lập (VIN) và đi dây gọn | Củ sạc |

Các công đoạn C1–C5 chỉ dùng 3,3 V từ USB, ít rủi ro nhất, nên làm trước.

---

# PHẦN C — LẮP NODE 1

Mỗi công đoạn có 5 mục: **Mục đích · Nối với cái gì · Các bước · Lưu ý · Kiểm tra thành công.**

Phần kiểm tra bằng phần mềm dùng **sketch chẩn đoán** (Phụ lục 1): mở Serial Monitor tốc độ 115200, kết thúc dòng **New Line**, gõ một chữ cái rồi Enter để chạy từng bài test. Board và cổng chọn theo §A6.5.

---

## C1. ESP32 + đế ra chân

**Mục đích:** có một bộ điều khiển chạy ổn định, nạp được code, trước khi gắn bất cứ thứ gì.

**Nối với cái gì:** ESP32 cắm vào đế ra chân. Đế nối với máy tính bằng cáp USB cắm vào cổng của ESP32.

**Các bước:**

1. Xem chữ in trên đế: tìm vị trí chân `3V3`, `EN`, `GND`, `VIN` và chiều cắm. Chữ in trên ESP32 phải khớp với chữ in trên đế ở **cả hai hàng**. Cắm ngược sẽ đưa nguồn vào sai chân.
2. Nếu đế có **jumper chọn điện áp cho hàng V** (thường ghi `3V3 / 5V`): đặt ở **3V3**. Các cảm biến lấy nguồn từ hàng V sẽ chạy ở 3,3 V.
3. Nếu đế có **jack DC riêng**: xem dải điện áp in bên cạnh (thường 6,5–16 V). **Không cắm củ sạc 5 V vào jack này.** Sau mạch ổn áp sẽ không đủ áp. Cấp nguồn qua cổng USB của ESP32.
4. Ấn ESP32 xuống đều tay, tất cả chân vào hết.
5. Cắm USB vào máy tính.

**Lưu ý:**

- Không để ESP32 nằm trên bề mặt kim loại hay dây đồng vụn.
- Nếu đế có công tắc nguồn, bật lên.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Đèn nguồn trên ESP32 và trên đế | Sáng |
| 2 | Đo hàng **V** so với hàng **G** trên đế | ≈ 3,3 V (nếu jumper ở 3V3) |
| 3 | Đo chân VIN/5V so với GND | 4,6–5,0 V (từ USB) |
| 4 | Nạp ví dụ Blink (LED trên board là GPIO2) | Nạp thành công, LED nhấp nháy |
| 5 | Nạp sketch chẩn đoán, gõ `h` | Hiện menu |
| 6 | Gõ `w` (sửa tên và mật khẩu WiFi trong sketch trước) | Kết nối WiFi, in ra IP |

**Lỗi thường gặp:**

- `Failed to connect… Timed out waiting for packet header`: giữ nút **BOOT** khi màn hình hiện `Connecting....`, thả ra khi bắt đầu nạp.
- Không thấy cổng COM: xem lại §A3 (driver, cáp sạc không có dây dữ liệu).

📸 Chụp ảnh ESP32 trên đế, có đèn sáng.

---

## C2. Bus I2C: OLED 1.3" + BH1750

**Mục đích:** hai thiết bị dùng chung 2 dây SDA/SCL. Bus I2C chạy thì màn hình hiển thị và cảm biến ánh sáng mới đọc được.

**Nối với cái gì:**

```
ESP32 3V3 ──► hàng (+) breadboard ──► VCC OLED, VCC BH1750
ESP32 GND ──► hàng (−) breadboard ──► GND OLED, GND BH1750
ESP32 GPIO21 ──► cột "SDA" trên breadboard ──► SDA OLED, SDA BH1750
ESP32 GPIO22 ──► cột "SCL" trên breadboard ──► SCL OLED, SCL BH1750
BH1750 ADDR: để trống (địa chỉ 0x23)
```

**Các bước:**

1. Chọn 2 cột trống trên breadboard, dán nhãn "SDA" và "SCL".
2. Kéo 1 dây từ GPIO21 vào cột SDA, 1 dây từ GPIO22 vào cột SCL.
3. Kéo 3V3 và GND từ ESP32 vào hai hàng nguồn của breadboard.
4. **Đọc chữ in trên OLED.** Có loại `VCC GND SCL SDA`, có loại `GND VCC SCL SDA`. Cắm theo **chữ in**, không theo vị trí.
5. Nối OLED vào hai hàng nguồn và hai cột SDA/SCL.
6. Lắp tiếp BH1750 vào cùng các cột đó.

**Lưu ý:**

- **Đảo VCC/GND trên OLED là cách phổ biến nhất làm cháy màn.** Kiểm tra hai lần trước khi cấp điện.
- Không đảo SDA và SCL. Đảo thì không hỏng gì nhưng sẽ không tìm thấy thiết bị.
- Phần lớn module OLED và GY-302 đã có điện trở kéo lên cho I2C, không cần thêm.
- Chip đã xác định là **SH1106** (đặc tả C2). Sketch chẩn đoán để sẵn `OLED_IS_SH1106 1`.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Trước khi cắm USB: đo thông mạch giữa hàng (+) và (−) breadboard | Không kêu |
| 2 | Gõ `i` (quét I2C) | Thấy **0x3C** (hoặc 0x3D) và **0x23** |
| 3 | Gõ `o` | Màn hình hiện chữ "OLED OK" rõ, không lệch. Ra nhiễu: kiểm tra `OLED_IS_SH1106 1` ở đầu sketch |
| 4 | Gõ `l` | Ra số lux. Phòng sáng: 100–1000; lấy tay che: còn vài lux; soi đèn điện thoại: tăng mạnh |

**Lỗi thường gặp:**

| Hiện tượng | Nguyên nhân |
|---|---|
| Không tìm thấy thiết bị nào | Đảo SDA/SCL, thiếu GND, chưa cấp 3V3, dây breadboard lỏng |
| Chỉ thấy 1 địa chỉ | Thiết bị kia chưa được cấp nguồn hoặc chưa nối vào bus |
| BH1750 hiện 0x5C | Chân ADDR đang được kéo lên mức cao. Để trống hoặc nối GND |

---

## C3. DHT22

**Mục đích:** đo nhiệt độ và độ ẩm không khí.

**Nối với cái gì:** `+ → 3V3`, `OUT → GPIO4`, `− → GND`. Cắm thẳng vào hàng G-V-S của chân 4 trên đế bằng dây cái-cái.

**Các bước:**

1. Đọc chữ in trên module: `+`, `OUT` (hoặc `DAT`), `−`.
2. Cắm vào chân 4 trên đế: S = OUT, V = +, G = −.

**Lưu ý:**

- Loại **trần 4 chân** (không có mạch đế): chân 1 VCC, chân 2 DATA, chân 3 bỏ trống, chân 4 GND, nhìn từ mặt có lưới. Cần thêm điện trở **10 kΩ** từ DATA lên 3V3. Bộ linh kiện không có 10 kΩ, nên ưu tiên dùng loại module.
- DHT22 đọc chậm: tối thiểu 2 giây mỗi lần. Đọc nhanh hơn sẽ báo lỗi.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Gõ `d` | Nhiệt độ hợp lý với phòng (20–35 °C ở Hà Nội), độ ẩm 40–90% |
| 2 | Hà hơi vào cảm biến rồi gõ `d` sau 5 giây | Độ ẩm tăng rõ rệt |
| 3 | Gõ `d` 5 lần, mỗi lần cách 3 giây | Không có lần nào báo `NaN` hay lỗi |

**Lỗi:** báo lỗi liên tục → sai chân OUT, đảo nguồn, hoặc loại trần thiếu điện trở kéo lên.

---

## C4. Hai cảm biến độ ẩm đất

**Mục đích:** đo độ ẩm đất ở 2 điểm trong khay.

**Nối với cái gì:**

```
Que đo ──(2 dây ngắn)──► Mạch so sánh (4 chân: VCC GND DO AO)
GPIO32 ──► hàng "SOIL-VCC" trên breadboard ──► VCC mạch 1, VCC mạch 2
Mạch 1: GND→GND, AO→GPIO34, DO để trống
Mạch 2: GND→GND, AO→GPIO35, DO để trống
```

**Các bước:**

1. Nối que đo với mạch so sánh (2 dây đi kèm, không phân cực).
2. Kéo 1 dây từ chân S của **GPIO32** vào một hàng trống trên breadboard, dán nhãn "SOIL-VCC".
3. Nối VCC của cả 2 mạch vào hàng SOIL-VCC. Nối GND của 2 mạch vào GND.
4. Nối AO mạch 1 vào chân S của **GPIO34**, AO mạch 2 vào chân S của **GPIO35**. Dùng chân AO, **không dùng DO**.
5. Dán nhãn "Đất 1", "Đất 2" lên que đo.

**Lưu ý:**

- **Chỉ dùng chân ADC1 (GPIO32–39).** ADC2 không đọc được khi WiFi bật. GPIO34 và 35 chỉ làm đầu vào, rất hợp cho cảm biến analog.
- VCC lấy từ GPIO32 (mức 3,3 V), **không** cấp 5 V: AO có thể lên gần mức nguồn, mà ESP32 chỉ chịu 3,3 V.
- GPIO32 chỉ bật khi đo: lệnh `s` và firmware chính bật 100 ms, đọc, rồi tắt. Cấp điện liên tục thì que kim loại bị ăn mòn nhanh.
- **Cách phân biệt loại cảm biến:**
  - Que hình nĩa hai chân kim loại trần là loại **điện trở**. Bộ của nhóm là loại này (đặc tả C10).
  - Que phẳng phủ sơn, mạch liền một khối là loại **điện dung**, bền hơn.
- Không nhúng phần mạch điện tử xuống nước. Chỉ nhúng tới vạch giới hạn.

**Kiểm tra thành công và hiệu chuẩn:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Gõ `s` khi cả 2 que để ngoài không khí | 2 số ADC lớn (thường 2800–4095). Ghi lại: **DRY1, DRY2** |
| 2 | Nhúng cả 2 que vào cốc nước tới vạch, chờ 10 giây, gõ `s` | Cả 2 số **giảm mạnh**. Ghi lại: **WET1, WET2** |
| 3 | Cầm tay vào que | Số giảm nhẹ (da người có độ ẩm) |
| 4 | So 2 cảm biến trong cùng cốc nước sau khi quy đổi % | Chênh nhau dưới 10 điểm % |
| 5 | Gõ `s`, nhìn đèn nguồn trên 2 mạch so sánh | Đèn chỉ sáng lúc đo rồi tắt. Đèn sáng mờ, hoặc số đo thấp hẳn so với khi tạm cấp 3V3: GPIO32 không đủ dòng cho 2 mạch, báo lại nhóm (đặc tả §5.2) |

Lặp lại bước 1–2 ba lần, lấy trung bình. Ghi DRY/WET vào **nhật ký lắp đặt** (Phụ lục 2). Firmware cần các số này.

**Lỗi:**

- Ra 0 hoặc 4095 liên tục: sai chân AO, chưa cấp nguồn (dây GPIO32 → SOIL-VCC lỏng), que chưa nối vào mạch.
- Số nhảy loạn: dây lỏng; hoặc đang đọc nhầm chân DO (DO chỉ ra 0 hoặc 1).

📸 Chụp que đo khi nhúng nước, kèm màn Serial hiện số.

---

## C5. Keypad 3×4

**Mục đích:** điều khiển tay tại chỗ, có mã PIN.

**Nối với cái gì:** 4 dây hàng → GPIO13, 14, 16, 17. 3 dây cột → GPIO19, 23, 33. Keypad không cần nguồn.

**Bước 1: dò thứ tự 7 chân bằng đồng hồ.** Keypad mềm không thống nhất thứ tự chân, nên phải dò.

1. Đánh số dây cáp từ trái sang phải: P1…P7 (nhìn mặt phím, cáp hướng xuống).
2. Đặt đồng hồ ở thang thông mạch. Giữ phím **1**, dò từng cặp chân, tìm cặp nào kêu. Đó là **hàng 1** và **cột 1**.
3. Giữ phím **5**: tìm ra **hàng 2** và **cột 2**. Giữ phím **9**: **hàng 3**, **cột 3**. Giữ phím **#**: **hàng 4**.
4. Ghi kết quả vào bảng:

| Phím giữ | Cặp chân kêu | Suy ra |
|---|---|---|
| 1 | P? – P? | R1, C1 |
| 5 | P? – P? | R2, C2 |
| 9 | P? – P? | R3, C3 |
| # | P? – P? | R4, C3 |

**Bước 2: nối dây.** R1→13, R2→14, R3→16, R4→17, C1→19, C2→23, C3→33. Cáp keypad là đầu cái, dùng dây đực-cái hoặc header đực để nối.

**Lưu ý:**

- GPIO16 và 17 là UART2 trên một số board. Không sao, vì firmware không dùng UART2.
- Không cần điện trở. Firmware bật pull-up nội cho các chân cột.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Gõ `k`, lần lượt bấm cả 12 phím | Mỗi phím in đúng ký tự in trên phím |
| 2 | Bấm giữ một phím | Chỉ in 1 lần, không lặp |

**Lỗi:** ký tự lộn xộn hoặc lệch cột → thứ tự chân sai. Sửa thứ tự dây theo bảng dò, hoặc sửa mảng `rowPins`/`colPins` trong code.

📸 Chụp lại bảng dò chân keypad (đưa vào báo cáo).

---

## C6. Nhánh nguồn 5 V: củ sạc → domino → tụ

**Mục đích:** tạo "thanh cái" +5 V và GND cho relay, HC-SR04 và tải.

**Nối với cái gì:**

```
Củ sạc 5V/3A ─► (module USB / jack DC / cáp USB cắt) ─► Domino
Domino: chọn 6 cực làm dãy +5V (nối tắt bằng dây đồng), 6 cực làm dãy GND (nối tắt)
Tụ 1000µF: chân (+) vào dãy +5V, chân có vạch (−) vào dãy GND
```

**Các bước:**

1. **Chưa cắm củ sạc.**
2. Domino có 12 cặp cọc. Quy ước 6 cặp bên trái là **+5 V**, 6 cặp bên phải là **GND**. Dùng dây đồng 0,6 mm nối tắt các cọc cùng dãy ở một phía. Dán nhãn "+5V" (đỏ) và "GND" (đen).
3. Nối dây (+) của nguồn vào dãy +5 V, dây (−) vào dãy GND. Siết chặt cọc vít, kéo nhẹ thử dây không tuột.
4. Lắp tụ 1000 µF: chân **dài** (hoặc phía **không** có vạch) vào +5 V, chân có **vạch** vào GND.
5. Kéo 1 dây GND từ dãy GND domino về chân GND của ESP32. Đây là dây **GND chung bắt buộc**. Vẫn **chưa** nối +5 V vào ESP32.

**Lưu ý:**

- **Cắm ngược tụ hóa sẽ làm tụ phồng hoặc nổ.** Kiểm tra hai lần.
- Dây nguồn 5 V nên dùng dây to hơn dây jumper, hoặc chập đôi dây đồng. Bơm khởi động kéo dòng lớn.
- Bọc kín mọi đoạn dây trần thừa ra khỏi cọc vít.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | **Chưa cắm củ sạc.** Đo thông mạch giữa dãy +5 V và GND | Không kêu. Số Ω tăng dần là do tụ đang nạp, bình thường |
| 2 | Đo thông mạch giữa các cọc trong cùng dãy +5 V | Kêu (đã nối tắt) |
| 3 | Cắm củ sạc, đo +5 V so với GND | 4,9–5,3 V, **dấu dương** (âm là đảo cực, rút ngay) |
| 4 | Sờ tụ sau 1 phút | Không nóng, không phồng |
| 5 | Đo giữa GND domino và GND ESP32 (thang thông mạch, đã rút nguồn) | Kêu |

📸 Chụp domino đã dán nhãn.

---

## C7. HC-SR04 + cầu chia áp

**Mục đích:** đo khoảng cách từ cảm biến xuống mặt nước, quy đổi ra % mực nước bể.

**Nối với cái gì:**

```
HC-SR04 VCC  ──► +5V domino
HC-SR04 GND  ──► GND domino
HC-SR04 TRIG ──► GPIO5            (3,3 V từ ESP32 đủ kích, không cần chia áp)
HC-SR04 ECHO ──[1 kΩ]──┬──► GPIO18
                       │
                    [2 kΩ]
                       │
                      GND
```

ECHO ra 5 V. Qua cầu chia: 5 × 2/(1+2) ≈ **3,33 V**, an toàn cho ESP32.

**Các bước:**

1. **Lắp cầu chia trên breadboard, chưa nối vào ESP32:**
   - Điện trở 1 kΩ: một đầu ở cột "ECHO-IN", đầu kia ở cột "ECHO-OUT".
   - Điện trở 2 kΩ: một đầu ở "ECHO-OUT", đầu kia ở hàng GND.
2. **Thử cầu chia trước khi dùng:** cấp nguồn domino, nối tạm cột "ECHO-IN" vào +5 V, đo cột "ECHO-OUT" so với GND. Phải được 3,2–3,4 V. Rút dây nối tạm ra.
3. Rút nguồn. Nối ECHO của HC-SR04 vào "ECHO-IN", nối "ECHO-OUT" vào GPIO18.
4. Nối VCC, GND, TRIG như sơ đồ.

**Lưu ý:**

- **Không cắm ECHO thẳng vào GPIO18.** Có thể chạy được một thời gian nhưng chân GPIO sẽ hỏng dần.
- Đổi nhầm vị trí hai điện trở sẽ ra ≈ 1,67 V, ESP32 đọc không ổn định. Kiểm tra lại theo bước 2.
- HC-SR04 cần đúng **5 V**. Cấp 3,3 V sẽ đo sai hoặc không đo được.
- Vùng mù gần: dưới 2 cm sẽ đo không chính xác. Lắp cảm biến cách mặt nước lúc đầy bể ít nhất 4–5 cm.
- GND của HC-SR04 phải chung với GND ESP32 (đã nối ở C6).

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Đo điện áp cầu chia (bước 2) | 3,2–3,4 V |
| 2 | Cắm USB + củ sạc. Gõ `u`, đặt tấm bìa phẳng cách 20 cm (đo bằng thước) | 19–21 cm |
| 3 | Đưa bìa lại gần 10 cm, rồi ra xa 40 cm | Số thay đổi đúng xu hướng, sai số ≤ 1 cm |
| 4 | Gõ `u` 10 lần liên tiếp | Không có lần nào báo timeout hoặc 0 |

**Lỗi:**

- "Không có xung" hoặc luôn 0: thiếu 5 V, thiếu GND chung, cầu chia đấu sai, ECHO/TRIG đảo.
- Số nhảy lung tung: mặt phản xạ nghiêng, vật mềm (vải, tay) hấp thụ sóng; dây breadboard lỏng.

---

## C8. Module relay 4 kênh — chưa nối tải

**Mục đích:** ESP32 điều khiển được relay và relay đóng/ngắt đúng, trước khi cho dòng tải đi qua.

**Nối với cái gì:**

```
Relay VCC ──► +5V domino        Relay GND ──► GND domino
Relay IN1 ──► GPIO26 (bơm)      Relay IN2 ──► GPIO27 (quạt)
Relay IN3 ──► GPIO25 (đèn)      Relay IN4 ──► để trống
```

**Bước 1: đặt jumper mức kích H/L cho từng kênh — chọn H.**

Module có jumper chọn mức kích cho từng kênh. Với ESP32 (3,3 V), đặt **H (kích mức cao)** cho kênh 1, 2, 3:

- Ở chế độ **L**, chân IN được kéo lên 5 V trên module. Mức HIGH 3,3 V của ESP32 có thể không tắt hẳn opto, nên relay dễ bị dính hoặc LED sáng mờ.
- Ở chế độ **H**, mức 3,3 V đủ để kích. Khi ESP32 khởi động (chân ở mức thấp hoặc thả nổi), relay **tắt**. Đó là trạng thái an toàn.

Ghi lại lựa chọn vào nhật ký. Firmware đặt `RELAY_ACTIVE_LOW = false` cho chế độ H.

Nếu module có thêm jumper **JD-VCC / VCC**: giữ nguyên jumper (cuộn relay và mạch opto dùng chung 5 V của domino).

**Bước 2: nối dây.**

1. **Rút hết nguồn.** Nối VCC, GND của relay vào domino.
2. Nối IN1, IN2, IN3 vào GPIO26, 27, 25.

**Lưu ý:**

- Mỗi kênh có 3 cọc vít: **COM** (chung), **NO** (thường mở), **NC** (thường đóng). Hệ thống chỉ dùng **COM và NO**. Khi mất điện hoặc ESP32 khởi động lại, tải luôn tắt.
- Chưa nối gì vào cọc vít ở công đoạn này.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Cấp nguồn (USB + củ sạc), ESP32 khởi động | **Tất cả relay tắt**: không tiếng "tách", LED kênh tắt |
| 2 | Gõ `1` (bật kênh 1 trong 3 giây) | Nghe "tách", LED kênh 1 sáng 3 giây rồi tắt |
| 3 | Gõ `2`, `3` | Tương tự cho kênh 2, 3 |
| 4 | Rút nguồn, đo thông mạch giữa COM và NO kênh 1 | Không kêu (thường mở) |
| 5 | Cấp nguồn, chuẩn bị sẵn que đo ở COM và NO kênh 1, gõ `1` và đo trong 3 giây relay bật | Kêu trong 3 giây, sau đó im (đóng rồi mở lại) |
| 6 | Bấm nút RESET trên ESP32 trong khi relay đang bật | Relay tắt ngay khi ESP32 reset |

**Lỗi:**

- Relay bật ngay khi cấp điện, test thì tắt: đang ở chế độ L. Chuyển jumper sang H, hoặc gõ `r` để đảo logic trong sketch.
- LED sáng nhưng không có tiếng "tách": thiếu 5 V ở VCC relay, hoặc củ sạc yếu.

---

## C9. Quạt + diode vào relay kênh 2

**Mục đích:** relay đóng/ngắt được tải thật, có bảo vệ chống xung ngược.

**Nối với cái gì:**

```
+5V domino ──► COM kênh 2
NO kênh 2  ──► dây đỏ (+) quạt
dây đen (−) quạt ──► GND domino
Diode 1N4007 song song với quạt: vạch bạc (K) về phía dây (+), đầu kia về phía dây (−)
```

**Các bước:**

1. **Rút nguồn.** Tuốt đầu dây, siết vào cọc vít COM và NO của kênh 2.
2. Nối dây (−) của quạt vào dãy GND domino.
3. Lắp diode: chân phía **vạch bạc** nối vào dây **(+)** của quạt (cùng điểm với NO), chân kia nối vào dây **(−)**. Có thể kẹp cả hai chân diode vào hai cọc domino, hoặc quấn vào đầu dây quạt rồi bọc co nhiệt.

**Lưu ý:**

- **Diode lắp ngược chiều dòng điện.** Bình thường diode không dẫn. Nó chỉ dẫn xung ngược sinh ra khi động cơ bị ngắt. Lắp sai chiều (vạch về phía GND) sẽ chập nguồn khi relay đóng.
- Quạt có chiều thổi: thường mặt có nhãn là mặt **hút gió ra**. Xác định trước khi lắp vào mô hình.
- **Nếu dùng động cơ mini chế thành quạt** (thay quạt 5 V, đặc tả C3):
  - Gắn chặt cánh nhựa vào trục, cố định thân động cơ lên khung. Không cầm tay khi thử, cánh lỏng sẽ văng.
  - Động cơ thường không ghi cực, đảo dây thì quay ngược. Thử chiều gió trước (chạm tạm 2 dây vào +5 V/GND domino trong 1 giây), dán nhãn dây (+), rồi mới lắp diode theo dây đó. Đã lắp diode mà đảo dây thì phải đảo cả diode, nếu không sẽ chập nguồn khi relay đóng.
  - Động cơ chổi than gây nhiễu nhiều hơn quạt 5 V: đi dây động cơ xa dây cảm biến. Bật quạt mà ESP32 khởi động lại thì thêm 1 tụ 1000 µF trên domino, sát cọc relay.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | **Chưa cấp nguồn.** Đo diode tại chỗ bằng thang diode: que đỏ ở dây (−), que đen ở dây (+) | 0,5–0,7 V. Đảo que: OL |
| 2 | Cấp nguồn, gõ `2` | Quạt quay 3 giây rồi dừng |
| 3 | Theo dõi Serial trong lúc quạt chạy và tắt | ESP32 **không** in thông báo khởi động lại (`rst:` hoặc `Brownout`) |
| 4 | Đo +5 V domino trong lúc quạt chạy | Không thấp hơn 4,8 V |

## C9b. Đèn LED vào relay kênh 3

**Mục đích:** chiếu sáng bổ sung cho khay cây (đặc tả §6.11). Đèn là tải nhẹ và không sinh xung ngược.

**Chuẩn bị đèn:**

- Đèn LED **5 V ánh trắng (phổ đầy đủ)**, công suất thấp ≤ 5 W, dùng **chung củ sạc 5V/3A** (đặc tả C25). Dòng ≈ công suất ÷ 5 V, ví dụ 5 W ≈ 1 A.
- **Không** dùng đèn tím (đỏ + xanh dương): ánh tím làm sai màu lá trong ảnh Node 2, AI dễ nhầm lá vàng và lá đốm.
- Đèn có đầu cắm USB: dùng một đầu USB cái có dây ra (để không phải cắt cáp đèn), hoặc cắt cáp và tách 2 dây nguồn. Dây đỏ là (+), dây đen là (−). Cáp có thêm dây dữ liệu (xanh lá, trắng) thì bọc riêng, không nối.

**Nối với cái gì:**

```
+5V domino ──► COM kênh 3
NO kênh 3  ──► (+) đèn
(−) đèn ──► GND domino
Không cần diode (LED không phải tải cảm ứng như bơm, quạt)
```

**Các bước:**

1. **Rút nguồn.** Siết dây (+) đèn vào NO kênh 3, nối COM kênh 3 với +5 V domino, nối dây (−) đèn vào GND domino.
2. Treo đèn cách mặt khay **20–30 cm**, chiếu thẳng xuống.
3. Đặt BH1750 sao cho **đèn không chiếu thẳng vào mặt cảm biến**: quay mặt cảm biến ra phía cửa sổ, hoặc dán một tấm bìa nhỏ phía trên, chắn giữa đèn và cảm biến. Nếu không, cảm biến đo cả ánh đèn và đèn sẽ tự bật/tắt liên tục.

**Lưu ý:**

- Bơm, quạt, đèn ≤ 5 W và ESP32 cùng chạy tốn dưới 2 A, củ 3 A vẫn đủ.
- Đèn không sáng khi relay đã kêu "tách": thường là đảo cực đèn hoặc đấu nhầm NC. Rút nguồn rồi sửa, đừng để đảo cực lâu.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Cấp nguồn, gõ `3` | Đèn sáng 3 giây rồi tắt |
| 2 | Theo dõi Serial lúc đèn bật và tắt | ESP32 **không** khởi động lại |
| 3 | Gõ `2` rồi `3` ngay | Quạt và đèn cùng chạy, ESP32 ổn định |
| 4 | Đo +5 V domino lúc quạt và đèn cùng chạy (nếu có đồng hồ) | Không thấp hơn 4,8 V |

**Hiệu chuẩn độ sáng do chính đèn tạo ra (ΔE_LED → cấu hình `lamp_self_lux`):**

1. Làm khi đèn và BH1750 đã ở **vị trí cuối cùng**, trong phòng tối (tắt đèn phòng, kéo rèm).
2. Gõ `l` → ghi lux lúc đèn tắt (E0).
3. Gõ `3`, rồi gõ `l` ngay trong 3 giây đèn đang sáng → ghi E1.
4. Lặp bước 2–3 ba lần, lấy trung bình. **ΔE_LED = E1 − E0.**
5. Ghi vào `hardware/nhat-ky-lap-dat.md`. Khi chạy firmware chính, gửi giá trị này vào cấu hình `lamp_self_lux`.
6. Kiểm tra điều kiện **ΔE_LED + 200 < `lamp_hyst`** (mặc định 700, tức ΔE_LED phải dưới 500 lux). Không đạt thì che chắn BH1750 kỹ hơn hoặc dời đèn rồi đo lại, hoặc tăng `lamp_hyst` qua cấu hình. Firmware từ chối cấu hình vi phạm điều kiện này.

**Lỗi:**

| Hiện tượng | Nguyên nhân |
|---|---|
| Relay kêu nhưng đèn không sáng | Đấu nhầm NC, thiếu +5 V ở COM, đảo cực đèn, cọc vít lỏng |
| Đèn sáng mờ | Củ sạc yếu; dây nguồn dài và nhỏ |
| ΔE_LED trên 500 lux | BH1750 nhìn thẳng vào đèn: che chắn hoặc đổi hướng cảm biến |

📸 Chụp ảnh vị trí đèn và BH1750 cho báo cáo.

---

## C10. Bơm chìm + diode vào relay kênh 1

**Mục đích:** tưới được. Đây là tải nặng nhất và gây nhiễu nhiều nhất, nên lắp cuối.

**Nối với cái gì:**

```
+5V domino ──► COM kênh 1
NO kênh 1  ──► dây đỏ (+) bơm
dây đen (−) bơm ──► GND domino
Diode 1N4007 song song với bơm (vạch bạc về phía +), như quạt
Ống φ6 gắn vào đầu ra của bơm
```

**Các bước:**

1. **Rút nguồn.** Đấu như quạt nhưng vào kênh 1.
2. Lắp diode như C9.
3. Gắn ống vào đầu ra bơm, đầu kia đặt vào một cốc rỗng để hứng nước.
4. **Thả bơm vào chậu nước** sao cho ngập hoàn toàn trước khi cấp điện.
5. Bọc kín mối nối dây bơm bằng co nhiệt hoặc băng keo điện. Mối nối gần nước.

**Lưu ý:**

- **Bơm không được chạy khan.** Chạy không có nước vài chục giây là hỏng.
- Mối nối dây bơm không được ngập nước. Kéo dây đủ dài để mối nối nằm trên miệng bể.
- Khi bơm khởi động, dòng tăng vọt. Đây là lúc dễ làm ESP32 khởi động lại nhất. Tụ 1000 µF, diode, và GND chung chính là để ngăn việc này.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Kiểm tra diode như C9 | Đúng chiều |
| 2 | Gõ `1` | Bơm chạy 3 giây, nước chảy ra ống đều |
| 3 | Theo dõi Serial | ESP32 **không** khởi động lại |
| 4 | Gõ `1` liên tiếp 10 lần | Lần nào cũng chạy, không reset, relay không dính |
| 5 | Đo lượng nước trong 10 giây chạy | Ghi lại lưu lượng (ml/s) để chỉnh `pump_max_s` |
| 6 | Chạy đồng thời bơm, quạt, đèn (gõ `1`, `2`, `3` liên tiếp) | Cả ba chạy, ESP32 vẫn ổn định |

**Lỗi:**

| Hiện tượng | Nguyên nhân |
|---|---|
| Bơm chạy là ESP32 reset | Thiếu tụ, thiếu diode, chưa nối GND chung, dây nguồn nhỏ và dài, củ sạc yếu |
| Relay kêu nhưng bơm không chạy | Đấu nhầm vào NC, thiếu +5 V ở COM, cọc vít lỏng |
| Bơm kêu ù, không ra nước | Còn khí trong bơm (lắc nhẹ dưới nước), ống bị gập |

📸 Quay video bơm chạy theo lệnh, kèm màn Serial.

---

## C11. Chạy độc lập và hoàn thiện

**Mục đích:** Node 1 chạy không cần máy tính, dây gọn, an toàn để đặt cạnh nước.

**Các bước:**

1. Rút USB khỏi ESP32. **Rút củ sạc.**
2. Nối một dây từ dãy **+5 V domino** vào chân **VIN** của ESP32 (hoặc chân 5V/VIN trên đế, xem chữ in).
3. Kiểm tra không còn dây USB nào cắm vào ESP32. Không cấp đồng thời USB và VIN, trừ khi chắc board có diode chặn dòng ngược.
4. Cấp củ sạc.
5. Gom dây theo nhóm, buộc lạt. Dán nhãn hai đầu các dây dài.
6. Đặt ESP32, breadboard, relay, domino vào hộp nhựa khô (hộp cơm cũ cũng được), khoét lỗ cho dây ra. Hộp đặt **cao hơn và cách xa** bể nước.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Cấp nguồn bằng củ sạc | ESP32 khởi động, OLED sáng (nếu firmware có hiển thị) |
| 2 | Đo VIN so với GND | 4,9–5,2 V |
| 3 | Không còn Serial vì đã rút USB; quan sát qua OLED hoặc trang quản lý router | Thiết bị kết nối được WiFi (thấy IP trên OLED, hoặc thấy ESP32 trong danh sách thiết bị của router) |
| 4 | Lắc nhẹ hộp, kéo nhẹ từng dây | Không có dây nào tuột |
| 5 | Chạy 30 phút liên tục với bơm và quạt bật tắt theo lệnh | Không reset, không chi tiết nào nóng bất thường |

📸 Chụp Node 1 hoàn chỉnh trong hộp, có nhãn dây.

---

# PHẦN D — LẮP NODE 2 (ESP32-CAM)

## D1. Kiểm tra và lắp camera

**Mục đích:** camera gắn chắc, board nạp được code và chụp được ảnh.

**Các bước:**

1. Kiểm tra cáp dẹt của camera OV2640 đã cắm chặt vào khe trên ESP32-CAM:
   - Mở chốt đen bằng cách nhấc nhẹ lên.
   - Cắm cáp vào với mặt tiếp điểm hướng xuống bo mạch, cắm hết.
   - Ấn chốt xuống.
2. Gỡ miếng nhựa bảo vệ trên ống kính (nếu còn).
3. Cắm ESP32-CAM lên đế nạp MB đúng chiều: camera cùng phía với cổng micro-USB của đế (theo chữ in trên đế).
4. Ăng-ten: dùng ăng-ten PCB trên board (mặc định). Không cần ăng-ten ngoài.

**Lưu ý:**

- Không gập cáp camera nhiều lần, rất dễ đứt.
- Đế MB có hai nút: **IO0** (vào chế độ nạp) và **RST**.

## D2. Nạp code và thử camera

**Các bước:**

1. Cắm đế MB vào máy tính bằng cáp micro-USB có truyền dữ liệu.
2. Chọn board "AI Thinker ESP32-CAM".
3. Nạp ví dụ **CameraWebServer** (có sẵn trong core ESP32), đặt model camera `CAMERA_MODEL_AI_THINKER`, điền WiFi.
4. Nếu nạp không vào: giữ nút **IO0**, bấm rồi thả **RST**, thả IO0, nạp lại.
5. Nạp xong bấm **RST** để chạy.

**Kiểm tra thành công:**

| # | Kiểm tra | Kết quả đúng |
|---|---|---|
| 1 | Serial Monitor 115200 sau khi RST | In ra địa chỉ IP, **không** có dòng `Brownout detector was triggered` |
| 2 | Mở IP trên trình duyệt, bấm "Start Stream" | Có hình ảnh, rõ, không sọc |
| 3 | Chọn độ phân giải SVGA (800×600), bấm "Get Still" | Ảnh chụp rõ |
| 4 | Bật/tắt flash trên giao diện (LED Intensity) | Đèn flash GPIO4 sáng/tắt |
| 5 | Để stream 10 phút | Không mất kết nối, board không reset |

## D3. Nguồn cho Node 2

**Các bước:**

1. Sau khi thử xong với máy tính, cắm đế MB vào **củ sạc 5V/2A** bằng cáp micro-USB.
2. Nếu gặp brownout:
   - Đổi sang cáp ngắn, dây to.
   - Thêm tụ 470–1000 µF giữa chân 5V và GND của ESP32-CAM (đúng cực).
   - Giảm độ phân giải xuống VGA.

**Lưu ý:** không tắt brownout detector để "chữa cháy". Đó là che giấu lỗi nguồn, ảnh sẽ lỗi ngẫu nhiên.

**Kiểm tra thành công:** cấp bằng củ sạc, mở stream từ điện thoại cùng mạng WiFi, chạy 15 phút không reset.

## D4. DHT11 trên Node 2 — không làm

Nhóm đã chốt **không gắn** DHT11 lên Node 2 (đặc tả C4). Node 2 chỉ chụp ảnh và nhận lệnh. DHT11 giữ làm linh kiện dự phòng cho DHT22 của Node 1 (kém chính xác hơn, chỉ dùng khi DHT22 hỏng).

---

# PHẦN E — LẮP ĐẶT VÀO MÔ HÌNH VƯỜN ƯƠM

## E1. Bố trí tổng thể

```
           [Node 2 ESP32-CAM trên giá, cao 30–40 cm, nhìn thẳng xuống]
                                 │
    [BH1750 hướng lên]   [DHT22 trong bóng râm]      [Quạt thổi ngang khay]
                 ┌──────────────── KHAY CÂY ────────────────┐
                 │  Đất 1 (giữa nửa trái)   Đất 2 (giữa nửa phải) │  ◄── đầu ống tưới
                 └──────────────────────────────────────────┘
   [Hộp điện Node 1: ESP32, relay, domino — đặt CAO, cách xa nước]
   [Bể nước: HC-SR04 trên nắp nhìn xuống · bơm chìm dưới đáy]
```

## E2. Lắp từng thiết bị

| Thiết bị | Cách lắp | Lưu ý | Kiểm tra |
|---|---|---|---|
| Cảm biến đất ×2 | Cắm thẳng đứng vào đất, sâu tới vạch, hai điểm cách xa nhau trong khay | Bọc silicon phần mạch và mối nối trước khi cắm; không đặt ngay chỗ ống nước xả xuống | Tưới tay một chút quanh cảm biến → % tăng trong 1 phút |
| DHT22 | Gắn cạnh khay, cao ngang ngọn cây, trong bóng râm | Không để nước tưới hay hơi nước phun trúng | Giá trị gần với nhiệt kế/điện thoại |
| BH1750 | Mặt cảm biến hướng lên, ngang mặt khay | Không để bóng của giá camera che | Che tay → lux giảm |
| HC-SR04 | Gắn trên nắp hoặc thanh ngang miệng bể, hai mắt nhìn **thẳng đứng** xuống mặt nước | Cách mặt nước lúc đầy ≥ 4–5 cm; không để ống bơm hay dây nằm trong vùng sóng; tránh hơi nước đọng trên cảm biến | Đo `TANK_EMPTY_CM` (bể cạn) và `TANK_FULL_CM` (bể đầy) → ghi vào nhật ký |
| Bơm | Đặt đáy bể, có thể dùng đế hút | Ngập hoàn toàn; mối nối dây ở trên miệng bể | Bơm 5 giây → nước tới khay |
| Ống tưới | Đi từ bơm tới khay, cố định đầu ống bằng kẹp/băng keo | Đầu ống cao hơn mực nước bể để không bị chảy ngược (xi-phông) khi bơm tắt | Tắt bơm → nước ngừng chảy trong vài giây |
| Quạt | Hướng thổi ngang qua khay | Không thổi thẳng vào DHT22 (sai số đo) | Bật quạt → cây rung nhẹ |
| Node 2 | Giá cố định, cao 30–40 cm, nhìn thẳng xuống khay | Khung hình chỉ có khay, không có người; đánh dấu vị trí giá để ảnh các ngày khớp nhau | Ảnh chụp rõ cả khay, khay chiếm phần lớn khung |
| Hộp điện Node 1 | Đặt cao hơn bể và khay, cách xa ít nhất 30 cm | Dây đi xuống rồi mới vòng lên hộp (vòng nhỏ giọt) để nước theo dây không chảy vào hộp | Đổ thử ít nước lên dây → nước nhỏ giọt ở đáy vòng, không vào hộp |

## E3. Hiệu chuẩn tại chỗ

Sau khi lắp vào mô hình, đo lại và ghi vào nhật ký:

1. `TANK_EMPTY_CM`, `TANK_FULL_CM` của bể thật.
2. Lưu lượng bơm thực tế (ml trong 10 giây) qua ống thật.
3. Độ ẩm đất (%) ngay sau khi tưới đẫm và sau 1 ngày không tưới. Dùng để chọn `soil_low`, `soil_high`.

---

# PHẦN F — NGHIỆM THU CUỐI VÀ XỬ LÝ LỖI

## F1. Checklist an toàn trước khi chạy dài hạn

- [ ] Không còn đoạn dây trần thừa ra khỏi cọc vít.
- [ ] Tụ 1000 µF đúng cực, không phồng.
- [ ] Diode ở bơm và quạt đúng chiều (vạch về phía +).
- [ ] Đèn nối NO kênh 3, BH1750 không bị đèn chiếu thẳng, đã đo ΔE_LED.
- [ ] Chân ECHO đi qua cầu chia áp, đo được ≈ 3,3 V.
- [ ] Mọi GND nối chung (đo thông mạch GND ESP32 ↔ GND domino ↔ GND relay ↔ GND HC-SR04).
- [ ] Relay dùng NO, tắt hết khi khởi động.
- [ ] Không có USB và VIN cấp đồng thời.
- [ ] Hộp điện khô, cao hơn nước.
- [ ] Mối nối dây bơm không ngập nước.
- [ ] Bơm ngập trong nước.

## F2. Nghiệm thu chức năng phần cứng

| # | Hạng mục | Cách thử | Đạt khi |
|---|---|---|---|
| 1 | Toàn bộ cảm biến | Gõ lần lượt `d`, `s`, `l`, `u` | Đủ 4 loại số liệu, hợp lý |
| 2 | Hiển thị và nhập | `o`, `k` | OLED hiện chữ, 12 phím đúng |
| 3 | Cơ cấu chấp hành | `1`, `2`, `3` | Bơm, quạt, đèn chạy đúng kênh |
| 4 | Ổn định nguồn | Bật bơm + quạt cùng lúc 10 lần | Không reset |
| 5 | Chạy độc lập | Chỉ củ sạc, 1 giờ | Không reset, không nóng |
| 6 | Node 2 | Stream + chụp + flash | Đủ, không brownout |

Đạt cả 6 mục thì chuyển sang nạp firmware chính (theo `dac-ta-he-thong.md` §6, §7).

## F3. Bảng xử lý lỗi tổng hợp

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| Không nạp được code | Cáp không truyền dữ liệu, thiếu driver, chưa vào chế độ nạp | §A3; giữ BOOT (Node 1) hoặc IO0 (Node 2) |
| I2C không thấy thiết bị | Đảo SDA/SCL, thiếu GND/3V3 | Dò lại theo C2 |
| OLED sáng nhưng hình nhiễu, lệch | Khai báo sai chip (phải là SH1106) | `OLED_IS_SH1106 1` / constructor `U8G2_SH1106_…` |
| DHT22 báo lỗi | Sai chân, loại trần thiếu điện trở kéo lên, đọc quá nhanh | C3 |
| Cảm biến đất 0 hoặc 4095 | Sai chân AO, mất nguồn, que chưa nối | C4 |
| Cảm biến đất đọc sai trong firmware chính, sketch chẩn đoán vẫn đúng | Firmware chưa bật GPIO32 trước khi đọc | Bật GPIO32, chờ 100 ms rồi mới đọc (đặc tả §5.2) |
| Số cảm biến đất nhảy khi bơm chạy | Nhiễu nguồn, dây đất dài chạy song song dây bơm | Tách dây tín hiệu khỏi dây bơm; kiểm tra GND chung |
| HC-SR04 không có xung | Thiếu 5 V, cầu chia sai, GND không chung | C7 |
| HC-SR04 đo sai trong bể | Cảm biến nghiêng, gần thành bể, hơi nước đọng | Chỉnh thẳng đứng, lau cảm biến |
| Relay bật khi khởi động | Chế độ L | Jumper sang H hoặc đảo logic |
| Bơm chạy là ESP32 reset | Thiếu tụ/diode/GND chung, dây nguồn nhỏ | C6, C10 |
| Relay kêu, tải không chạy | Nhầm NC, thiếu +5 V ở COM, cọc lỏng | C9, C10 |
| ESP32-CAM `Brownout detector was triggered` | Nguồn yếu, cáp dài/mảnh | D3 |
| ESP32-CAM `Camera init failed` | Cáp camera lỏng, sai model camera trong code | D1, chọn `AI_THINKER` |

---

# PHỤ LỤC

## Phụ lục 1 — Sketch chẩn đoán phần cứng

Một sketch riêng (`firmware/test-hardware/test-hardware.ino`), chạy qua Serial Monitor 115200, kết thúc dòng **New Line** (§A6.7). Mỗi lệnh test một linh kiện để kiểm tra từng công đoạn ở Phần C:

| Lệnh | Chức năng | Dùng ở |
|---|---|---|
| `h` | In menu và chân đang cấu hình | C1 |
| `w` | Kết nối WiFi, in IP và RSSI | C1 |
| `i` | Quét bus I2C, in các địa chỉ tìm thấy | C2 |
| `o` | Hiển thị "OLED OK" và số đếm lên màn | C2 |
| `l` | Đọc BH1750 (lux) | C2 |
| `d` | Đọc DHT22 (°C, %RH) | C3 |
| `s` | Bật nguồn cảm biến đất (GPIO32), đọc ADC 10 lần, in trung bình, tắt nguồn | C4 |
| `k` | In phím bấm từ keypad trong 20 giây; chế độ dò chân `kp`: in cặp GPIO thông nhau khi bấm phím | C5, Phụ lục 3 |
| `u` | Đo HC-SR04 5 lần, in cm | C7 |
| `1` / `2` / `3` | Bật relay kênh 1 (bơm) / 2 (quạt) / 3 (đèn) trong 3 giây | C8–C10, C9b |
| `r` | Đảo logic kích relay (mức H ↔ L) | C8 |
| `a` | Đọc điện áp chân VP / GPIO36 (mV, đã hiệu chỉnh), 5 lần | Phụ lục 3 — thay đồng hồ đo tín hiệu ≤ 3,3 V |

## Phụ lục 2 — Nhật ký lắp đặt

Điền trong lúc lắp, đưa vào thư mục `hardware/` và báo cáo:

| Mục | Giá trị | Ngày |
|---|---|---|
| Điện áp ra củ sạc 5V/3A | ___ V | |
| Điện áp ra củ sạc 5V/2A | ___ V | |
| Chip USB của ESP32 (CP210x / CH340) | | |
| Jumper hàng V của đế | 3V3 / 5V | |
| Địa chỉ I2C của OLED (SH1106) | 0x__ | |
| Địa chỉ BH1750 | 0x__ | |
| Cảm biến đất (loại điện trở) cấp qua GPIO32: đèn module sáng rõ khi đo? | Có / Không | |
| Đất 1: DRY / WET | ____ / ____ | |
| Đất 2: DRY / WET | ____ / ____ | |
| Thứ tự chân keypad P1…P7 | | |
| Chế độ kích relay | H / L | |
| Điện áp cầu chia ECHO | ___ V | |
| HC-SR04 tại 20 cm thước | ___ cm | |
| `TANK_EMPTY_CM` / `TANK_FULL_CM` | ___ / ___ | |
| Lưu lượng bơm | ___ ml / 10 s | |
| Điện áp +5 V khi bơm + quạt + đèn cùng chạy | ___ V | |
| Đèn: công suất ghi trên nhãn | ___ W | |
| ΔE_LED (`lamp_self_lux`) = lux đèn bật − lux đèn tắt, phòng tối | ___ lux | |
| Quạt dùng | Quạt 5 V / động cơ mini gắn cánh | |
| Node 2: độ phân giải ổn định | SVGA / VGA | |
| Node 2: có brownout không | Có / Không | |

Kèm ảnh từng công đoạn (📸) và video bơm chạy theo lệnh. Đây là bằng chứng "hình ảnh sản phẩm thực tế" mà đề bài yêu cầu trong báo cáo.

## Phụ lục 3 — Lắp khi không có đồng hồ vạn năng

Nhóm vẫn nên mua hoặc mượn một chiếc đồng hồ cơ bản (kiểu DT-830) **trước công đoạn C6** (nhánh 5 V). Cho tới lúc đó, làm theo phụ lục này. Nguyên tắc chung: **không dò được bằng đo thì loại bỏ khả năng sai ngay từ cách lắp, và để một thiết bị có bảo vệ chịu thay khi có sự cố.**

### P3.1. Bảy lỗi gây cháy cần chặn

| # | Lỗi | Hậu quả | Chặn bằng |
|---|---|---|---|
| 1 | Đảo VCC/GND của OLED | Cháy màn | Kiểm tra hai người (P3.3) |
| 2 | ECHO HC-SR04 cắm thẳng GPIO18 | Hỏng dần chân GPIO | Thử cầu chia bằng ADC (P3.6) |
| 3 | 5 V vào chân 3V3 hoặc GPIO | Hỏng ESP32 | Quy ước màu dây, kiểm tra hai người |
| 4 | Chập +5 V với GND ở domino | Nóng dây, hỏng nguồn | Module USB có in cực + thử nguồn rỗng bằng sạc dự phòng (P3.2, P3.5) |
| 5 | Cắm ngược tụ hóa | Tụ phồng, có thể nổ | Kiểm tra hai người: chân dài vào +5 V, vạch vào GND |
| 6 | Lắp ngược diode ở bơm/quạt | Chập nguồn khi relay đóng | Thử bằng quạt với sạc dự phòng (P3.7) |
| 7 | Cấp đồng thời USB và VIN | Dòng ngược vào máy tính | Chỉ nối VIN ở C11, sau khi đã rút USB |

### P3.2. Nguồn vào domino: không cắt cáp USB

Không dùng cách A ở §A3 (cắt cáp USB), vì không đo được dây nào là (+). Bắt buộc dùng **module USB ra chân có in sẵn `+`/`−`** (hoặc `VCC`/`GND`), hoặc jack DC có cọc vít ghi cực.

Kiểm tra củ sạc còn tốt bằng cách cắm sạc điện thoại: điện thoại báo đang sạc là được.

### P3.3. Kiểm tra "hai người, ba lần" trước mỗi lần cấp điện

1. **Người lắp đọc to** từng dây theo bảng §B3, ví dụ "VCC OLED vào 3V3, GND OLED vào GND…".
2. **Chụp ảnh** mạch, rõ chữ in trên module.
3. **Người thứ hai** xem ảnh, tự đối chiếu với bảng và đánh dấu vào checklist, không nghe người lắp giải thích.

Bốn điểm bắt buộc kiểm tra ở cả hai lượt:

- [ ] Chữ in VCC/GND trên OLED khớp với dây cắm vào.
- [ ] Tụ: chân dài (phía không có vạch) ở +5 V.
- [ ] Diode: vạch bạc về phía dây (+) của tải.
- [ ] Dây ECHO đi qua điện trở 1 kΩ trước khi tới GPIO18.

### P3.4. Nguồn cho lần cấp điện đầu tiên

| Công đoạn | Nguồn cho lần đầu | Lý do |
|---|---|---|
| C1–C5 (chỉ 3,3 V) | Cổng USB máy tính | Cổng USB có mạch giới hạn dòng; chập thì máy ngắt cổng hoặc báo lỗi |
| C6–C10 (nhánh 5 V) | **Sạc dự phòng** cho domino; ESP32 vẫn cấp qua USB máy tính | Phần lớn sạc dự phòng tự ngắt khi chập. Củ sạc tường thì đẩy hết dòng vào chỗ chập |
| C11 và chạy dài | Củ sạc 5V/3A | Chỉ dùng sau khi mọi công đoạn đã qua thử nghiệm |

Lưu ý: một số sạc dự phòng tự tắt khi tải quá nhỏ (dưới khoảng 50–100 mA). Nếu sạc dự phòng tự tắt sau vài chục giây mà không có dấu hiệu chập, đó là do tải nhỏ, không phải lỗi mạch.

### P3.5. Thử nhanh 5 giây sau mỗi lần cấp điện

1. Cắm nguồn, đếm 5 giây, quan sát:
   - Đèn nguồn ESP32 / module sáng.
   - Không có mùi khét.
   - Máy tính không báo lỗi USB (kiểu "USB device has exceeded power limits").
   - Sạc dự phòng không tự ngắt hoặc nháy đèn báo lỗi.
2. Rút nguồn. Dùng **mu bàn tay** chạm nhẹ vào ESP32, module vừa lắp, tụ, dây nguồn. Mu bàn tay nhạy nhiệt và ít bị bỏng hơn đầu ngón tay.
3. Có thứ gì ấm rõ rệt thì **dừng lại**, kiểm tra lại theo P3.3 trước khi cấp điện tiếp.
4. Không có gì bất thường thì cấp điện lại và chạy bài test của công đoạn.

**Thử nguồn rỗng ở C6:** lắp domino và tụ, chưa nối gì khác, cấp bằng sạc dự phòng. Sạc dự phòng ngắt ngay hoặc nháy đèn lỗi nghĩa là có chập ở domino.

### P3.6. Dùng ESP32 làm vôn kế cho tín hiệu ≤ 3,3 V

Chân ADC1 đọc được 0–3,3 V. Lệnh `a` của sketch chẩn đoán in điện áp chân **VP (GPIO36)** (đơn vị mV, đã hiệu chỉnh). Trên đế, chân này có thể in là `VP`, `SVP` hoặc `36`. Mạch chính không dùng chân này. (GPIO32 đã dùng để cấp nguồn cho cảm biến đất nên không dùng làm chân đo nữa.)

**Không bao giờ đưa nguồn trên 3,3 V vào chân đo.**

**Thử cầu chia áp ECHO (thay bước 2 của C7):**

1. Lắp cầu chia trên breadboard như C7 (1 kΩ ở trên, 2 kΩ xuống GND).
2. Cấp **3V3 của ESP32** (không phải +5 V) vào đầu "ECHO-IN".
3. Nối "ECHO-OUT" vào **VP (GPIO36)**, gõ `a`.

| Kết quả | Ý nghĩa |
|---|---|
| ≈ 2100–2300 mV | **Đúng.** 3,3 × 2/3 ≈ 2,2 V. Khi thay bằng ECHO 5 V sẽ ra ≈ 3,3 V |
| ≈ 1000–1200 mV | Hai điện trở bị đảo chỗ. Đổi lại |
| ≈ 3300 mV (bão hòa) | Thiếu điện trở 2 kΩ xuống GND, hoặc đầu dưới chưa nối GND. **Không được nối ECHO 5 V vào** |
| ≈ 0 mV | Đầu "ECHO-IN" chưa có 3V3, hoặc nối nhầm điểm |

Đạt rồi thì: rút USB, gỡ dây 3V3 và dây VP ra, nối ECHO vào "ECHO-IN" và "ECHO-OUT" vào GPIO18 như C7.

**Kiểm tra hàng V của đế (thay đo ở C1):** **không** nối thẳng hàng V vào chân đo, vì nếu hàng V đang là 5 V thì chân đo bị quá áp. Đi qua cầu chia 1 kΩ/2 kΩ giống C7: hàng V → 1 kΩ → điểm giữa → 2 kΩ → GND; nối điểm giữa vào VP, gõ `a`.

| Kết quả | Ý nghĩa |
|---|---|
| ≈ 2100–2300 mV | Hàng V là **3,3 V** |
| ≥ 3000 mV | Hàng V là **5 V**. Không cắm cảm biến 3,3 V vào hàng V; chuyển jumper sang 3V3 |

Vẫn nên chụp ảnh jumper và chữ in bên cạnh để người thứ hai xác nhận.

### P3.7. Kiểm tra chiều diode bằng quạt

Thay bước 1 của C9:

1. Lắp quạt vào relay kênh 2 như C9, **chưa gắn diode**.
2. Cấp nhánh 5 V bằng **sạc dự phòng**. Gõ `2` vài lần → quạt quay. Mạch tải đã đúng.
3. Rút nguồn. Gắn diode: vạch bạc về phía dây đỏ (+) của quạt.
4. Cấp lại sạc dự phòng, gõ `2`:

| Kết quả | Ý nghĩa |
|---|---|
| Quạt quay bình thường, diode không ấm | **Đúng chiều** |
| Quạt không quay, sạc dự phòng ngắt, ESP32 có thể reset, diode ấm | **Ngược chiều** → rút nguồn ngay, đảo diode |

5. Đúng rồi thì lắp diode cho bơm theo **cùng hướng** (vạch bạc về phía dây đỏ của bơm), rồi thử bơm cũng bằng sạc dự phòng.

### P3.8. Bảng thay thế phép đo theo công đoạn

| Công đoạn | Phép đo trong hướng dẫn | Thay bằng |
|---|---|---|
| A3 | Đo điện áp củ sạc | Cắm sạc điện thoại; dùng module USB có in cực |
| A3 | Đo điện trở | Đọc vạch màu (1 kΩ: nâu-đen-đỏ; 2 kΩ: đỏ-đen-đỏ); dán nhãn túi |
| A3 | Kiểm tra diode | P3.7 |
| C1 | Đo hàng V | Xem jumper + chữ in; `a` chỉ xác nhận có nguồn |
| C2, C6 | Kiểm tra chập trước khi cấp điện | P3.3 + P3.5 (USB máy tính / sạc dự phòng) |
| C5 | Dò chân keypad | Nối 7 dây theo thứ tự bất kỳ vào 7 chân keypad, ghi lại dây nào vào GPIO nào. Gõ `kp` (chế độ dò chân): sketch quét mọi cặp GPIO và in ra cặp nào thông khi bấm phím. Bấm lần lượt 1, 5, 9, # → điền bảng dò như C5 (keypad không có nguồn nên cắm sai thứ tự không gây hỏng) |
| C6 | Đo +5 V domino | Đèn nguồn trên module relay sáng khi nối vào; sạc dự phòng không báo lỗi |
| C7 | Đo cầu chia | P3.6 |
| C8 | Đo COM–NO | Lắp quạt (C9) làm tải thử: relay đóng thì quạt quay |
| C9, C10 | Đo sụt áp khi bơm chạy | Theo dõi Serial: bật bơm + quạt cùng lúc 10 lần không có dòng `rst:` / `Brownout` là nguồn đủ |
| C11 | Đo VIN | ESP32 khởi động và kết nối WiFi bằng củ sạc là đủ |

### P3.9. Hai việc vẫn nên có đồng hồ

1. **Xác nhận điện áp thật của củ sạc** — đặc biệt củ không rõ nguồn gốc, có thể ra cao hơn 5,5 V.
2. **Đo sụt áp khi bơm và quạt cùng chạy** — số liệu này có ích cho phần đánh giá trong báo cáo.

Cả hai nằm ở công đoạn C6 trở đi, nên đó là thời điểm cần có đồng hồ.
