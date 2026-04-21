# 🧹 HA Optimizer

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-1.0.0-blue)
![HA](https://img.shields.io/badge/Home%20Assistant-2023.1+-green)
![license](https://img.shields.io/badge/license-MIT-lightgrey)
![Python](https://img.shields.io/badge/Python-3.11+-yellow)
![languages](https://img.shields.io/badge/UI-12%20ngôn%20ngữ-blueviolet)
![themes](https://img.shields.io/badge/themes-11%20built--in-ff69b4)

> 🇬🇧 **English version:** [README.md](README.md)

**Integration dọn dẹp, phân tích và kiểm tra sức khỏe hệ thống thông minh cho Home Assistant.**

Hầu hết hệ thống Home Assistant đều tích lũy hàng trăm entity chết, automation hỏng, database phình to và thiết bị âm thầm mất kết nối — mà không ai hay biết cho đến khi có sự cố. **HA Optimizer** tự động phát hiện tất cả, giúp bạn dọn dẹp an toàn và tự tin.

> ⚡ *Cài một lần. Để nó quét. Biết chính xác cái gì đang làm rác hệ thống — và dọn sạch an toàn.*

---

## 📸 Preview

![Preview 1](assets/preview1.png)
![Preview 2](assets/preview2.png)
![Preview 3](assets/preview3.png)

---

## 🔥 Tại Sao Bạn Cần Cái Này?

| Vấn đề | HA Optimizer giải quyết |
|---|---|
| 💀 Entity chết từ thiết bị đã gỡ | Phát hiện & gắn nhãn theo mức độ rủi ro |
| 🤖 Automation hỏng không ai biết | Quét dead code — trigger/action trỏ vào hư không |
| 🗄️ Database Recorder phình không kiểm soát | Tìm top entity ghi nhiều nhất, gợi ý tối ưu YAML |
| 📊 Card dashboard gọi entity không tồn tại | Audit toàn bộ Lovelace |
| 🌩️ Entity spam cập nhật 100× mỗi phút | Phát hiện state storm |
| 🔌 Integration liên tục mất kết nối | Chấm điểm sức khỏe với phân tích reconnect chi tiết |
| ❓ "HA hôm nay có hoạt động kỳ lạ không?" | Phát hiện anomaly so với chính lịch sử của bạn |
| 🧩 Add-on nằm tản mạn khắp HA settings | Panel add-on tập trung với giám sát CPU/RAM trực tiếp |
| 🖥️ Không biết host đang dùng bao nhiêu tài nguyên | Biểu đồ CPU / RAM / Disk realtime luôn hiển thị |

---

## ✨ Tính Năng

### 🔍 Quét Entity Thông Minh
- Quét **toàn bộ entity, automation, script và helper** trong một lần chạy
- Gán **mức độ rủi ro** (Thấp / Trung bình / Cao) để bạn biết cái nào an toàn khi xóa
- Phát hiện: entity cũ (không đổi trạng thái trong N ngày), entry registry mồ côi, tên đặt đáng ngờ (`test_`, `temp_`, `backup_`, v.v.), entity định nghĩa trong YAML không thể tự động xóa
- **An toàn là trên hết** — cảm biến khói, cửa/cửa sổ, khóa, chuyển động, CO/gas **không bao giờ** được gợi ý xóa (có thể cấu hình)
- Xuất ra `health_score` (0–100) cho toàn bộ hệ thống HA của bạn

### 🗑️ Purge Engine An Toàn với Soft Delete
- **Soft delete mặc định** — vô hiệu hóa entity thay vì xóa, hoàn toàn có thể khôi phục
- **Tab Thùng rác** — toàn bộ entity đã soft delete được liệt kê kèm timestamp, số ngày còn lại trước khi tự xóa, và nút khôi phục chỉ một click
- **Tự động hết hạn** — thùng rác được dọn sạch sau N ngày (có thể cấu hình)
- Xử lý đúng automation và script (tạo qua UI vs định nghĩa trong YAML)
- Phát hiện entity đã bị vô hiệu hóa sẵn và vẫn đưa vào thùng rác để theo dõi

### 🧩 Quản Lý Add-on *(tính năng mới)*
Panel điều khiển add-on đầy đủ tính năng tích hợp thẳng vào Optimizer — không cần nhảy qua lại giữa các menu HA nữa.

- Liệt kê **toàn bộ add-on đã cài** được sắp xếp theo ưu tiên: có bản cập nhật trước, đang chạy tiếp theo, đã dừng sau cùng
- Hiển thị **CPU % và RAM thực tế** của từng add-on, **tự động làm mới mỗi 5 giây** — không cần tải lại trang
- **Thao tác một click**: Cập nhật, Khởi động, Dừng và mở trang chi tiết add-on — tất cả trong cùng một màn hình
- Làm nổi bật rõ ràng các add-on có **bản cập nhật** (phiên bản cũ gạch ngang, phiên bản mới được tô xanh)
- Chip tóm tắt ở trên: tổng số, đang chạy, đã dừng, số bản cập nhật khả dụng

### 🖥️ Biểu Đồ Tài Nguyên Hệ Thống Realtime *(tính năng mới)*
Luôn hiển thị ở đầu mọi tab — bạn không bao giờ mất tầm nhìn về sức khỏe máy chủ dù đang dùng tính năng nào.

- **Ba biểu đồ bán cung động** cho CPU, RAM và Disk
- **Dải màu gradient** chuyển từ xanh lá → cam → đỏ khi tải tăng (0 → 50% → 100%)
- **Kim chỉ động** trượt mượt mà đến đúng giá trị hiện tại
- Hiển thị giá trị tuyệt đối bên dưới mỗi biểu đồ (ví dụ: `6.6 GB / 23.2 GB` cho RAM)
- Hiển thị tên OS, hostname, phiên bản HA và kernel
- **Tự động làm mới mỗi 5 giây** khi đang ở tab Add-ons; nút làm mới thủ công có sẵn trên mọi tab

### 📡 Phát Hiện Anomaly Dấu Vân Tay *(tính năng độc đáo)*
So sánh hành vi HA hôm nay **với chính lịch sử baseline của bạn** (tối đa 30 ngày). Dùng phương pháp thống kê (σ hoặc IQR tùy lượng dữ liệu có) để phát hiện:
- Đột biến bất thường trong số lần ghi state (tải DB tăng đột ngột)
- Lượng automation trigger bất thường
- Cơn bão reconnect integration
- Sự kiện lifecycle HA bất thường (khởi động lại, reload bất ngờ)

Độ tin cậy tăng dần theo số ngày baseline (20% → 99%). Hoàn toàn riêng tư — chỉ so sánh với **dữ liệu của chính bạn**, không liên quan đến người dùng khác.

### 🗄️ Phân Tích Database Recorder
- Truy vấn trực tiếp database recorder SQLite/MySQL
- Xác định **entity ghi nhiều nhất** (thủ phạm làm phình DB)
- Phát hiện **bản ghi lãng phí** — ghi nhiều nhưng ít giá trị khác nhau
- Tạo sẵn **đoạn YAML** để dán vào cấu hình `recorder:` tối ưu ngay
- Thống kê số lần ghi theo từng domain

### 📊 Phân Tích Dashboard Lovelace
- Đọc file cấu hình `.storage/lovelace*`
- Gắn cờ: card nặng/phức tạp, entity bị mất, entity trùng lặp, custom card chưa cài, card Jinja2 template, áp lực WebSocket push
- Đối chiếu với dữ liệu recorder để tìm lãng phí DB do dashboard gây ra

### 🌩️ Phát Hiện State Storm
- Tìm entity cập nhật state **bất thường nhanh** so với baseline domain
- Kèm đánh giá mức độ nghiêm trọng, tỷ lệ so với bình thường và đề xuất sửa chữa
- Bắt sensor cấu hình sai trước khi chúng lấp đầy database

### 🤖 Quét Dead Code Automation
- Quét toàn bộ automation tạo qua UI để tìm **tham chiếu hỏng**
- Kiểm tra: trigger trỏ vào thiết bị đã gỡ, action gọi entity/service đã xóa, condition dùng state của entity không còn tồn tại
- Lỗi silent fail trong automation được lộ ra trước khi gây vấn đề

### 🔌 Chấm Điểm Sức Khỏe Integration
- Phân tích **7 ngày dữ liệu recorder** cho từng integration
- Chấm điểm từng integration (0–100) dựa trên tần suất reconnect và kiểu mất kết nối
- Gắn cờ đợt mất kết nối bất thường so với trung bình rolling
- Phân tích chi tiết điểm trừ: mất kết nối 7 ngày, đang offline, config lỗi, spike hôm nay
- Thông điệp chẩn đoán: "📶 Có thể bị nhiễu sóng hoặc thiết bị quá xa hub"

### 🎨 11 Theme Giao Diện Tích Hợp *(tính năng mới)*
Đổi toàn bộ giao diện chỉ với một click — sở thích của bạn được lưu tự động.

| Theme | Phong cách |
|---|---|
| 🌌 Deep Space | Tối navy + xanh điện (mặc định) |
| 🟣 Midnight Purple | Tối thẫm + tím violet |
| 🌲 Forest Dark | Tối xanh rừng + emerald |
| 🌅 Sunset | Tối ấm + cam |
| 🌊 Ocean Light | Sáng xanh biển — chế độ sáng |
| 🪨 Slate Pro | Tối indigo + tím accent |
| 🌹 Rose Gold | Tối đỏ thẫm + hồng rose |
| ⚡ Cyber Neon | Gần đen + cyan phát sáng |
| 🟡 Amber Dark | Tối nâu vàng + hổ phách |
| 🧊 Arctic | Trắng băng — chế độ sáng |
| 🧛 Dracula | Classic Dracula tối + tím nhạt |

### 🌍 12 Ngôn Ngữ Giao Diện *(tính năng mới)*
Toàn bộ panel — mọi nhãn, nút, thông báo và lỗi — đều được dịch đầy đủ sang 12 ngôn ngữ. Chuyển đổi tức thì từ thanh chọn ngôn ngữ trên topbar; lựa chọn của bạn được lưu qua các phiên làm việc.

**Hỗ trợ:** 🇻🇳 Tiếng Việt · 🇬🇧 English · 🇩🇪 Deutsch · 🇫🇷 Français · 🇳🇱 Nederlands · 🇵🇱 Polski · 🇸🇪 Svenska · 🇭🇺 Magyar · 🇨🇿 Čeština · 🇮🇹 Italiano · 🇵🇹 Português · 🇸🇮 Slovenščina

---
## 🛠️ Cài Đặt

### Cách 1: HACS (Khuyến nghị)

[![Open HACS Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=doanlong1412&repository=HA-Optimizer&category=integration)

> Nếu nút không hoạt động, thêm thủ công:
1. Mở HACS → **Integrations** → nhấn menu **⋮** → **Custom repositories**
2. Thêm URL repository này, chọn danh mục **Integration**
3. Tìm **HA Optimizer** trong HACS store và nhấn **Download**
4. Khởi động lại Home Assistant
5. Vào **Settings → Devices & Services → Add Integration** → tìm **HA Optimizer**
6. Hoàn thành wizard cài đặt

### Cách 2: Thủ công

1. Tải hoặc clone repository này
2. Copy thư mục `ha_optimizer/` vào `config/custom_components/`:
   ```
   config/
   └── custom_components/
       └── ha_optimizer/
           ├── __init__.py
           ├── const.py
           ├── config_flow.py
           ├── scanner.py
           ├── purge_engine.py
           ├── store.py
           ├── fingerprint.py
           ├── manifest.json
           ├── services.yaml
           ├── strings.json
           └── panel.html
   ```
3. Khởi động lại Home Assistant
4. Vào **Settings → Devices & Services → Add Integration** → tìm **HA Optimizer**

---

## ⚙️ Cấu Hình

Trong quá trình cài đặt bạn sẽ được hỏi:

| Cài đặt | Mặc định | Mô tả |
|---|---|---|
| Khoảng cách quét tự động (ngày) | `7` | Đặt `0` để tắt quét tự động |
| Ngưỡng entity cũ (ngày) | `30` | Số ngày không đổi state trước khi bị gắn cờ |
| Bật soft delete | `true` | Vô hiệu hóa trước khi xóa hẳn (có thể khôi phục) |
| Số ngày trong thùng rác | `7` | Ngày ở thùng rác trước khi tự động xóa vĩnh viễn |
| Loại trừ device classes | *(mặc định an toàn)* | Danh sách cách nhau bởi dấu phẩy, không bao giờ gợi ý xóa |

Tất cả settings có thể thay đổi qua **Settings → Devices & Services → HA Optimizer → Configure**.

---

## 🚀 Cách Dùng

Mở panel **🧹 HA Optimizer** từ sidebar HA. Panel tự động kết nối qua phiên WebSocket của HA — **không cần token hay xác thực thêm**. Mọi thao tác đều thực hiện qua giao diện — không cần YAML hay gọi service thủ công.

> ✅ **Không cần Long-Lived Access Token.** Panel dùng chính kết nối đã xác thực sẵn của trình duyệt với Home Assistant — không lưu trữ, không chia sẻ bất kỳ token nào.

Panel có **9 tab** ở trên cùng:

---

### 📋 Tab Scan — Tổng Quan & Dọn Dẹp

Tab chính. Xem sức khỏe hệ thống và quản lý entity không dùng.

1. **Nhấn `🔍 Bắt đầu Scan`** — scanner phân tích toàn bộ entity, automation, script và helper (mất vài giây)
2. **Overview Dashboard** hiện ra với:
   - **Gauge Health Score** (0–100)
   - Tổng entity, số ứng viên cần xem xét, phân loại theo rủi ro (🔴 Cao / 🟡 TB / 🟢 Thấp)
   - Số entity trong thùng rác, thời gian scan lần cuối
3. Bảng bên dưới liệt kê toàn bộ item bị gắn cờ. Bạn có thể **lọc** theo rủi ro, loại hoặc nguồn, và **tìm kiếm** theo tên hoặc entity_id
4. **Tích checkbox** để chọn item, rồi dùng thanh action nổi phía dưới:
   - **🗑️ Vô hiệu hóa** → soft delete (có thể khôi phục — entity chuyển vào Thùng rác)
   - **❌ Xóa cứng** → xóa vĩnh viễn ⚠️ không thể hoàn tác
   - **✕ Bỏ chọn** → hủy chọn

> ⚠️ Luôn **backup HA** trước khi dùng Xóa cứng.

---

### 📊 Tab Recorder

1. Nhấn **`📊 Phân tích Recorder`**
2. Xem: kích thước DB, top entity ghi nhiều nhất, bản ghi lãng phí, thống kê theo domain
3. Copy **đoạn YAML sẵn sàng dán** vào `configuration.yaml` trong mục `recorder:` rồi khởi động lại HA để giảm tăng trưởng DB

---

### 🖥️ Tab Dashboard

1. Nhấn **`🖥️ Phân tích Dashboard`**
2. Panel đọc file `.storage/lovelace*` và báo cáo: card nặng, entity bị mất/unavailable, tham chiếu trùng, custom card chưa cài, card Jinja2 template
3. Issues được đánh dấu **Critical** hoặc **Warning**

> ℹ️ Chỉ hỗ trợ dashboard UI mode (lưu trong `.storage/lovelace*`). Dashboard YAML mode không thể đọc tự động.

---

### ⚡ Tab State Storm

1. Nhấn **`⚡ Phát hiện State Storms`**
2. Entity cập nhật state bất thường nhanh so với baseline domain được liệt kê kèm mức độ nghiêm trọng, tỷ lệ so với bình thường và đề xuất sửa
3. Đây là nguyên nhân phổ biến nhất gây phình DB và Lovelace chậm

---

### 🔍 Tab Dead Code

1. Nhấn **`🔍 Phân tích Dead Code`**
2. Automation UI được quét để tìm tham chiếu hỏng: trigger trỏ vào thiết bị đã gỡ, action gọi entity/service đã xóa, condition dùng state entity không còn tồn tại
3. Mỗi automation có vấn đề hiển thị link **"Mở Editor"** để sửa ngay lập tức

---

### 💚 Tab Health

1. Nhấn **`💚 Kiểm tra Health Integration`**
2. Mỗi integration được chấm điểm (0–100) dựa trên 7 ngày dữ liệu reconnect và unavailability
3. Thiết bị có vấn đề hiển thị: số lần reconnect hôm nay vs trung bình ngày, mức pin (nếu có), thông điệp chẩn đoán
4. Badge trạng thái: **Good** / **Warning** / **Critical**

---

### 🫆 Tab Fingerprint

So sánh hành vi HA hôm nay với **lịch sử baseline của chính bạn** — riêng tư, không so sánh với người dùng khác.

**Lần đầu dùng — xây dựng baseline:**

1. Nhấn **`📥 Thu thập Baseline`** — lưu snapshot metrics của ngày hôm qua
2. Lặp lại hàng ngày, hoặc tự động chạy mỗi đêm lúc **00:05**
3. Sau **3–7 ngày**, kết quả bắt đầu có ý nghĩa (độ tin cậy đạt 75%+)

**Chạy phân tích:**

1. Nhấn **`🫆 Phân tích Fingerprint`**
2. Kết quả hiển thị: độ tin cậy, số anomaly, số giờ đã qua hôm nay (extrapolate lên 24h để so sánh công bằng)
3. Mỗi anomaly cho thấy giá trị hôm nay vs baseline trung bình và phương pháp thống kê dùng (σ hoặc IQR)
4. ✅ xanh = bình thường · ⚠️ cam = phát hiện anomaly

---

### 🧩 Tab Add-ons

Panel quản lý add-on đầy đủ kèm dữ liệu tài nguyên host trực tiếp.

- Liệt kê toàn bộ add-on với trạng thái, phiên bản và thông tin cập nhật
- **CPU % và RAM** trực tiếp của từng add-on đang chạy, tự làm mới mỗi 5 giây
- **Biểu đồ hệ thống** ở trên đầu luôn hiển thị CPU / RAM / Disk của host
- **Cập nhật / Khởi động / Dừng** chỉ một click mà không cần rời panel

> ℹ️ Yêu cầu Home Assistant OS hoặc Supervised (Supervisor API). Không khả dụng trên bản Container hoặc Core.

---

### 🗑️ Tab Thùng Rác

Toàn bộ entity đã soft delete hiện ở đây kèm ngày vô hiệu hóa.

- **♻️ Khôi phục** — bật lại entity và xóa khỏi thùng rác
- **❌ Xóa cứng** — xóa vĩnh viễn khỏi HA
- Entity tự động bị xóa cứng sau số ngày đã cấu hình (mặc định: 7 ngày)

---

### Ví Dụ Automation — Quét Hàng Tuần & Thông Báo

```yaml
automation:
  alias: "HA Optimizer - Quét Hàng Tuần"
  trigger:
    - platform: time
      at: "03:00:00"
    - platform: template
      value_template: "{{ now().weekday() == 6 }}"  # Chủ nhật
  action:
    - service: ha_optimizer.scan
    - wait_for_trigger:
        platform: event
        event_type: ha_optimizer_scan_complete
      timeout: "00:05:00"
    - service: notify.mobile_app_dien_thoai_cua_ban
      data:
        title: "🧹 HA Optimizer"
        message: >
          Quét xong. Tìm thấy {{ trigger.event.data.statistics.candidates_found }}
          ứng viên. Điểm sức khỏe: {{ trigger.event.data.statistics.health_score }}/100
```

---

## 📋 Danh Sách Services

| Service | Mô tả |
|---|---|
| `ha_optimizer.scan` | Quét toàn bộ — entity, automation, script, helper |
| `ha_optimizer.purge` | Vô hiệu hóa (soft) hoặc xóa vĩnh viễn entity |
| `ha_optimizer.restore` | Khôi phục entity đã soft delete |
| `ha_optimizer.get_results` | Trả kết quả quét lần cuối dạng service response |
| `ha_optimizer.analyze_recorder` | Phân tích sâu Recorder DB + gợi ý YAML |
| `ha_optimizer.analyze_dashboard` | Audit dashboard Lovelace |
| `ha_optimizer.analyze_storms` | Phát hiện state storm / entity ghi tần suất cao |
| `ha_optimizer.analyze_dead_code` | Quét trigger/action/condition hỏng |
| `ha_optimizer.analyze_health` | Chấm điểm sức khỏe integration (cửa sổ 7 ngày) |
| `ha_optimizer.analyze_fingerprint` | Phát hiện anomaly so với baseline cá nhân |
| `ha_optimizer.analyze_addons` | Danh sách add-on + CPU/RAM trực tiếp + dữ liệu host |
| `ha_optimizer.collect_baseline` | Thu thập snapshot baseline thủ công |

---

## 🛡️ An Toàn

- **Soft delete là mặc định** — entity bị vô hiệu hóa, không bị xóa. Hoàn toàn có thể khôi phục.
- **Device class an toàn được hardcode** — cảm biến khói, CO/gas, độ ẩm, chuyển động, chiếm dụng, cửa, cửa sổ, khóa, rung, âm thanh, pin, sự cố **không bao giờ** được gợi ý.
- **Entity YAML được gắn cờ, không bao giờ tự xóa** — cần thao tác thủ công.
- **Chấm điểm rủi ro** — mỗi kết quả có mức độ rủi ro để bạn quyết định có thông tin.
- **Không lưu trữ token** — panel xác thực qua WebSocket session sẵn có của HA, không có thông tin nhạy cảm nào được lưu trong trình duyệt.

---

## 🖥️ Tương Thích

| | |
|---|---|
| Home Assistant | 2023.7+ (2023.1+ cho hầu hết tính năng) |
| Database | SQLite (mặc định) và MySQL/MariaDB |
| Cấu hình | UI config flow — không cần YAML |
| Phụ thuộc | Không — chỉ dùng HA built-ins |
| Python | 3.11+ |

> **Tại sao 2023.7+?** Panel dùng `return_response` khi gọi service (ra mắt từ HA 2023.7). Các tính năng còn lại hoạt động từ 2023.1+.

---

## 📋 Changelog

### v1.0.0 — Phát Hành Lần Đầu
- 🔍 Quét entity thông minh với phân loại rủi ro và điểm sức khỏe
- 🗑️ Soft delete + khôi phục + tab thùng rác tự hết hạn
- 📡 Phát hiện anomaly dấu vân tay (σ / IQR, baseline 30 ngày)
- 🗄️ Phân tích Recorder DB với gợi ý YAML
- 📊 Audit dashboard Lovelace
- 🌩️ Phát hiện state storm
- 🤖 Quét dead code automation
- 🔌 Chấm điểm sức khỏe integration với phân tích reconnect
- 🧩 Quản lý add-on với CPU/RAM trực tiếp mỗi add-on (tự làm mới 5 giây)
- 🖥️ Biểu đồ tài nguyên realtime (CPU / RAM / Disk) — luôn hiển thị
- 🎨 11 theme tích hợp, lưu tự động
- 🌍 12 ngôn ngữ giao diện, dịch đầy đủ
- ⚙️ Config flow UI đầy đủ với options
- 🔐 **Không cần Long-Lived Access Token** — xác thực qua WebSocket session của HA

---

## 📄 Giấy Phép

MIT License — tự do sử dụng, chỉnh sửa và phân phối.
Nếu bạn thấy hữu ích, hãy ⭐ **star repo** nhé — giúp ích rất nhiều!

---

## 🙏 Credits

Thiết kế và phát triển bởi **[@doanlong1412](https://github.com/doanlong1412)** từ 🇻🇳 Việt Nam.

---

## ☕ Ủng Hộ

Nếu HA Optimizer giúp ích cho bạn, hãy ủng hộ mình một ly cà phê nhé!

[![PayPal](https://img.shields.io/badge/Ủng%20hộ-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/doanlong1412)

Mọi sự ủng hộ đều được trân trọng và là động lực để mình tiếp tục phát triển. Cảm ơn bạn rất nhiều! 🙏
