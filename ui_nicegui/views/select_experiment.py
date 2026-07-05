"""Chọn loại experiment — 5 template hiển thị + Full Pipeline. Tương đương ui/views/select_experiment.py."""

from nicegui import ui

import state
import theme
from components.experiment_card import render_template_card
from components.header import render_breadcrumbs, render_header

# tags/time_estimate là gợi ý định hướng UX, không phải số đo benchmark thật.
TEMPLATES = [
    {
        "name": "Khám phá dữ liệu",
        "description": (
            "Agent tự động kiểm tra chất lượng dữ liệu, lập kế hoạch phân tích bằng AI, "
            "tự sinh giả thuyết và câu hỏi phân tích, rồi trực quan hóa kèm nhận xét bằng "
            "tiếng Việt. Đây là module được đầu tư kỹ nhất trong hệ thống."
        ),
        "icon": "query_stats",
        "color": "#EE0033",
        "border_color": "#EE0033",
        "badge": "Nổi bật",
        "tags": ["EDA", "Tự động", "Insight"],
        "time_estimate": "~1-2 phút",
        "button_color": "primary",
    },
    {
        "name": "Xử lý dữ liệu",
        "description": (
            "Tự động điền giá trị thiếu, xử lý outlier, mã hóa cột phân loại và chuẩn hóa "
            "cột số — có thể tùy chỉnh từng bước qua câu lệnh tiếng Việt (vd \"đừng chuẩn "
            "hóa\"). Phù hợp khi cần làm sạch dữ liệu trước khi huấn luyện mô hình."
        ),
        "icon": "tune",
        "color": "#1976D2",
        "tags": ["Clean", "Encode", "Scale"],
        "time_estimate": "~30 giây",
        "button_color": "primary",
    },
    {
        "name": "Huấn luyện mô hình",
        "description": (
            "Tự động phát hiện loại bài toán (hồi quy/phân loại/phân nhóm), huấn luyện song "
            "song nhiều model baseline (Logistic Regression, Random Forest, XGBoost...) và "
            "xếp hạng theo độ chính xác. Model tốt nhất được lưu lại để dùng cho bước sau."
        ),
        "icon": "model_training",
        "color": "#F57C00",
        "tags": ["Baseline", "Leaderboard"],
        "time_estimate": "~1-3 phút",
        "button_color": "primary",
    },
    {
        "name": "Đánh giá mô hình",
        "description": (
            "Tải lại model đã huấn luyện, tự áp dụng đúng pipeline xử lý dữ liệu đã lưu, rồi "
            "tính các chỉ số (accuracy, F1, RMSE...) trên dữ liệu kiểm tra mới. Kèm biểu đồ "
            "trực quan như ma trận nhầm lẫn hoặc actual-vs-predicted."
        ),
        "icon": "fact_check",
        "color": "#2E7D32",
        "tags": ["Metrics", "So sánh"],
        "time_estimate": "~30 giây",
        "button_color": "primary",
    },
    {
        "name": "Suy luận mô hình",
        "description": (
            "Dùng model đã huấn luyện để dự đoán trên dữ liệu hoàn toàn mới, không cần có "
            "sẵn cột target. Kết quả xuất ra file CSV kèm giải thích ý nghĩa dự đoán bằng "
            "tiếng Việt."
        ),
        "icon": "online_prediction",
        "color": "#757575",
        "tags": ["Predict"],
        "time_estimate": "~10 giây",
        "button_color": "primary",
    },
    # "Tùy chỉnh" tạm ẩn khỏi UI — giống bản Streamlit (router.py vẫn hỗ trợ nếu cần mở lại)
    {
        "name": "Full Pipeline",
        "description": (
            "Chạy nối tiếp toàn bộ 4 bước Khám phá → Xử lý → Huấn luyện → Đánh giá trong 1 "
            "lần, có thể tạm dừng xem kết quả sau mỗi bước trước khi tiếp tục. Phù hợp khi "
            "muốn đi từ dữ liệu thô tới model hoàn chỉnh mà không cấu hình từng bước riêng."
        ),
        "icon": "account_tree",
        "color": "#44494D",
        "border_color": "#44494D",
        "tags": ["End-to-end", "4 bước"],
        "time_estimate": "~3-5 phút",
        "button_color": "dark",
    },
]

_TEMPLATE_CSS = """
.template-card { transition: transform .15s ease, box-shadow .15s ease; }
.template-card:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(238,0,51,0.12); }
"""


@ui.page("/select-experiment")
def select_experiment_page():
    theme.apply()
    state.ensure_defaults()
    ui.add_css(_TEMPLATE_CSS)

    render_header()
    render_breadcrumbs([("Trang chủ", "/"), ("Chọn loại experiment", None)])

    with ui.column().classes("w-full").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
        problem_idx = state.get("current_problem_idx")
        if problem_idx is None:
            ui.label("Vui lòng chọn hoặc tạo bài toán trước.").classes("text-orange-600 mt-4")
            ui.button("Quay lại trang chủ", on_click=lambda: ui.navigate.to("/")).classes("mt-2")
            return

        problem = state.get("problems", [])[problem_idx]

        ui.label("Chọn loại experiment").classes("text-2xl font-bold mt-2")
        with ui.row().classes("items-center gap-1 mt-1 px-3 py-1 rounded-full").style(
            "background:#EE00331A; display:inline-flex; width:fit-content;"
        ):
            ui.icon("folder", color="#EE0033").style("font-size: 14px;")
            ui.label(problem["name"]).style("color:#EE0033;").classes("text-sm font-medium")

        with ui.grid(columns=3).classes("w-full gap-4 mt-4"):
            for template in TEMPLATES:
                def select(template=template):
                    state.set_value("current_experiment_type", template["name"])
                    ui.navigate.to("/experiment-config")

                render_template_card(template, on_click=select)

        ui.button("Quay lại", on_click=lambda: ui.navigate.to("/")).props("flat").classes("mt-4")
