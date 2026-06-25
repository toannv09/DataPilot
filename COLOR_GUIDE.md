# Bảng màu thương hiệu — tham khảo khi làm UI mới

> Trích từ "Hướng dẫn sử dụng bộ nhận diện thương hiệu Viettel" (update 9/2023), chỉ giữ phần màu sắc — dùng làm tham chiếu khi đổi UI (NiceGUI/Reflex...), không cần đọc lại file PDF gốc.

## Màu chủ đạo (Primary)

| Tên | HEX | RGB | CMYK |
|---|---|---|---|
| Đỏ Viettel (Pantone 185) | **#EE0033** | 238, 0, 51 | 0/100/90/0 |

## Màu bổ trợ (Secondary / Neutral)

| Tên | HEX | RGB | CMYK |
|---|---|---|---|
| Đen sẫm (Pantone Black 6) | **#000000** | 0, 0, 0 | 30/40/30/100 |
| Xám than (Pantone 425) | **#44494D** | 68, 73, 77 | 20/10/10/80 |
| Xám trung (Pantone 421) | **#B5B4B4** | 181, 180, 180 | 24/25/0/0 |
| Xám nhạt | **#F2F2F2** | 242, 242, 242 | 0/0/0/5 |
| Trắng | **#FFFFFF** | 255, 255, 255 | — |

## Tỷ lệ áp dụng — quy tắc 60-30-10

| Tỷ lệ | Vai trò | Màu dùng |
|---|---|---|
| **10%** | Điểm nhấn (accent) | Đỏ chủ đạo `#EE0033` |
| **30%** | Bổ trợ | Đen/xám than/xám trung `#000000` `#44494D` `#B5B4B4` |
| **60%** | Nền trung tính | Trắng/xám nhạt `#FFFFFF` `#F2F2F2` |

**Ý nghĩa khi lên UI:** không phủ đỏ tràn lan toàn màn hình — đỏ chỉ dùng làm điểm nhấn (nút chính, trạng thái active, header/dải nhấn), phần lớn diện tích (nền, khung, body text) nên trung tính (trắng/xám nhạt), xám than/đen dùng cho text chính và các UI phụ (border, nút phụ, caption).

## Cách phối màu chữ/nền (để đảm bảo đọc được, đúng chuẩn)

| Nền | Màu chữ nên dùng |
|---|---|
| Đỏ `#EE0033` | Trắng (chữ đen/đỏ trên đỏ — tránh) |
| Đen `#000000` | Trắng (hoặc đỏ làm điểm nhấn nhỏ) |
| Xám than `#44494D` | Trắng |
| Xám trung `#B5B4B4` | Trắng hoặc đen (tùy độ tương phản cần) |
| Xám nhạt `#F2F2F2` / Trắng | Đen hoặc đỏ (đỏ dùng cho heading/nhấn, đen cho nội dung) |

## Lưu ý khi áp dụng vào UI (rút từ phần ví dụ Đúng/Sai)

- **Tránh**: nền đỏ phủ kín kèm nhiều chữ/icon chen chúc, nhiều màu cạnh tranh nhau trong cùng 1 khối — nhìn rối, không đúng tinh thần "đỏ là điểm nhấn".
- **Nên**: bố cục sạch — nền trắng/xám nhạt làm chủ đạo, đỏ dùng có chủ đích (nút "Bắt đầu"/"Tải xuống", thanh trạng thái, dải tiêu đề mỏng), đen/xám cho text và phân vùng.
- Card/box dùng viền hoặc nền xám nhạt (`#F2F2F2`) để phân tách nội dung, không cần màu nổi.

## Gợi ý map sang theme code (khi đổi NiceGUI)

```python
ui.colors(
    primary="#EE0033",     # Đỏ Viettel - nút chính, trạng thái active
    secondary="#000000",   # Đen sẫm - nút phụ quan trọng, menu chính (cùng nhóm 30% bổ trợ)
    accent="#EE0033",      # Giữ đỏ làm điểm nhấn
    dark="#44494D",        # Xám than - text chính + mảng tối phụ (đỡ gắt hơn đen tuyền)
    positive="#2E7D32",    # Giữ màu hệ thống cho success, không đổi theo brand
    negative="#C62828",    # Giữ màu hệ thống cho error
)
# Nền trung tính
# body background: #FFFFFF hoặc #F2F2F2
# border/divider: #B5B4B4
```
