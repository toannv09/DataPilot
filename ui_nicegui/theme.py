"""Theme màu Viettel (xem COLOR_GUIDE.md) — gọi `apply()` ở ĐẦU mỗi page function.

Lý do tách riêng: nicegui >=3 cấm gọi UI element (kể cả ui.colors) ở global scope khi
app dùng nhiều @ui.page — phải gọi trong context của từng page.
"""

from nicegui import ui


def apply():
    ui.colors(
        primary="#EE0033",
        secondary="#000000",
        accent="#EE0033",
        dark="#44494D",
        positive="#2E7D32",
        negative="#C62828",
    )
