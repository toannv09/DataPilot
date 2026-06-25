# Dataset điện lực

Dataset demo chính của project. Gồm 5 file CSV về hệ thống điện Việt Nam.

---

## `phu_tai.csv`
- **Tần suất:** 30 phút/bản ghi
- **Đơn vị:** MW

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `thoi_gian` | datetime | Thời điểm đo |
| `phu_tai_mien_bac_MW` | float | Phụ tải miền Bắc |
| `phu_tai_mien_trung_MW` | float | Phụ tải miền Trung |
| `phu_tai_mien_nam_MW` | float | Phụ tải miền Nam |
| `phu_tai_he_thong_MW` | float | Tổng phụ tải cả nước |

---

## `thoi_tiet.csv`
- **Tần suất:** 1 giờ/bản ghi
- **Thành phố:** Hà Nội, Đà Nẵng, TP.HCM

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `time` | datetime | Thời điểm |
| `province` | str | Tỉnh/thành phố |
| `temperature_2m` | float | Nhiệt độ 2m (°C) |
| `relative_humidity_2m` | float | Độ ẩm (%) |
| `apparent_temperature` | float | Nhiệt độ cảm nhận |
| `precipitation` | float | Lượng mưa (mm) |
| `cloud_cover` | float | Độ che phủ mây (%) |
| `wind_speed_10m` | float | Tốc độ gió (km/h) |

---

## `buc_xa_mat_troi.csv`
- **Tần suất:** 1 giờ/bản ghi
- **Phạm vi:** Các tỉnh có farm điện mặt trời

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `time` | datetime | Thời điểm |
| `province` | str | Tỉnh |
| `latitude` | float | Vĩ độ |
| `longitude` | float | Kinh độ (**lưu ý:** bị format sai, cần parse) |
| `temperature_2m` | float | Nhiệt độ (°C) |
| `shortwave_radiation` | float | Bức xạ sóng ngắn (W/m²) |
| `direct_radiation` | float | Bức xạ trực tiếp (W/m²) |
| `diffuse_radiation` | float | Bức xạ khuếch tán (W/m²) |

> **Bug:** `longitude` có giá trị dạng `1.071.667` thay vì `107.1667` — cần fix khi đọc file.

---

## `san_luong_theo_ngay.csv`
- **Tần suất:** 1 ngày/bản ghi
- **Đơn vị:** Triệu kWh

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `thoi_gian` | date | Ngày |
| `loai_hinh_dien` | str | Loại: thủy điện, nhiệt điện, điện mặt trời... |
| `san_luong_trieu_kwh` | float | Sản lượng (triệu kWh) |

---

## `ngay_le_tet.csv`

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `date` | date | Ngày lễ |
| `mapped_lag_1y` | date | Ngày tương ứng năm trước |
| `holiday_name` | str | Tên ngày lễ |

---

## Lưu ý kỹ thuật khi đọc file

```python
# phu_tai — parse datetime
df = pd.read_csv('phu_tai.csv', parse_dates=['thoi_gian'])

# buc_xa — fix longitude bị format sai
df = pd.read_csv('buc_xa_mat_troi.csv')
df['longitude'] = df['longitude'].astype(str).str.replace('.', '', 1).astype(float) / 10

# san_luong — filter chỉ lấy điện mặt trời
df_solar = df[df['loai_hinh_dien'].str.contains('mặt trời', case=False)]
```