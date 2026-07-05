"""Cấu hình experiment — upload file, file nghiệp vụ, mô tả/câu hỏi. Tương đương ui/views/experiment_config.py."""

import json
import os

from nicegui import ui

import state
import theme
from agents.base_agent import ExperimentContext
from components.file_uploader import render_data_uploader, render_domain_uploader, render_model_uploader, render_test_uploader
from components.header import render_breadcrumbs, render_chip, render_header
from tools.ml.model_selector import MODEL_REGISTRY

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "models")

TASK_TYPE_LABELS = {
    "Tự động phát hiện": None,
    "Regression": "regression",
    "Classification": "classification",
    "Clustering": "clustering",
}
NO_TARGET = "(Không có — Clustering)"

# (tên field hiển thị ở sidebar, set loại experiment áp dụng — None = luôn hiện)
SIDEBAR_FIELDS = [
    ("File dữ liệu", None),
    ("File nghiệp vụ", None),
    ("Yêu cầu phân tích", None),
    ("Cấu hình huấn luyện", {"Huấn luyện mô hình", "Full Pipeline"}),
    ("Dữ liệu đánh giá", {"Full Pipeline"}),
    ("Chọn model & cột target", {"Đánh giá mô hình", "Suy luận mô hình"}),
]

PIPELINE_STEPS = [
    ("EDA — Khám phá dữ liệu", "#EE0033"),
    ("Xử lý dữ liệu", "#1976D2"),
    ("Huấn luyện mô hình", "#F57C00"),
    ("Đánh giá mô hình", "#2E7D32"),
]


def _column_options(files):
    """Lấy danh sách tên cột (không trùng) từ các file dữ liệu đã upload."""
    columns = []
    seen = set()
    for df in files.values():
        for col in df.columns:
            if col not in seen:
                seen.add(col)
                columns.append(col)
    return columns


def _card_header(icon, color, title, subtitle, badge=None):
    with ui.row().classes("items-center gap-3 w-full pb-3").style("border-bottom: 0.5px solid rgba(0,0,0,0.07);"):
        with ui.element("div").classes("flex items-center justify-center").style(
            f"background:{color}1A; color:{color}; width:32px; height:32px; flex-shrink:0; border-radius:7px;"
        ):
            ui.icon(icon, color=color).style("font-size:17px;")
        with ui.column().classes("gap-0"):
            with ui.row().classes("items-center gap-1"):
                ui.label(title).classes("text-sm font-medium")
                if badge == "required":
                    ui.label("*").classes("text-sm font-medium").style("color:#EE0033;")
                elif badge == "optional":
                    ui.label("(không bắt buộc)").classes("text-xs text-gray-400")
            ui.label(subtitle).classes("text-xs text-gray-400")


def _render_sidebar(experiment_type):
    with ui.column().style("width:210px; flex-shrink:0;").classes("gap-4"):
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-1 mb-2"):
                ui.icon("visibility", color="#EE0033").style("font-size:14px;")
                ui.label("Mục hiển thị theo experiment").classes("text-xs font-medium")

            visible_fields = [f for f, types in SIDEBAR_FIELDS if types is None or experiment_type in types]
            hidden_fields = [f for f, types in SIDEBAR_FIELDS if types is not None and experiment_type not in types]

            for f in visible_fields:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check", color="positive").style("font-size:13px;")
                    ui.label(f).classes("text-xs text-gray-700")

            if hidden_fields:
                ui.separator().classes("my-2")
                ui.label("Ẩn với experiment này:").classes("text-xs text-gray-400")
                for f in hidden_fields:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("visibility_off", color="grey-4").style("font-size:13px;")
                        ui.label(f).classes("text-xs text-gray-400").style("text-decoration: line-through;")

        if experiment_type == "Full Pipeline":
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center gap-1 mb-2"):
                    ui.icon("info", color="#EE0033").style("font-size:14px;")
                    ui.label("Pipeline sẽ chạy").classes("text-xs font-medium")

                for label, color in PIPELINE_STEPS:
                    with ui.row().classes("items-center gap-2"):
                        ui.element("div").style(
                            f"width:6px; height:6px; border-radius:50%; background:{color}; flex-shrink:0;"
                        )
                        ui.label(label).classes("text-xs text-gray-600")

                ui.separator().classes("my-2")
                ui.label("Dừng được sau mỗi bước · kết quả lưu tự động").classes("text-xs text-gray-400")


@ui.page("/experiment-config")
def experiment_config_page():
    theme.apply()
    state.ensure_defaults()

    render_header()

    problem_idx = state.get("current_problem_idx")
    experiment_type = state.get("current_experiment_type")
    if problem_idx is None or not experiment_type:
        with ui.column().classes("w-full").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
            ui.label("Vui lòng chọn bài toán và loại experiment trước.").classes("text-orange-600")
            ui.button("Quay lại", on_click=lambda: ui.navigate.to("/select-experiment"))
        return

    problem = state.get("problems", [])[problem_idx]

    render_breadcrumbs([
        ("Trang chủ", "/"),
        ("Chọn experiment", "/select-experiment"),
        ("Cấu hình", None),
    ])

    with ui.column().classes("w-full").style("background:#F7F7F8; min-height:100vh; padding:24px 32px;"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-1"):
                ui.label("Cấu hình experiment").classes("text-lg font-medium")
                with ui.row().classes("gap-2 mt-1"):
                    render_chip("database", problem["name"], "#EE0033")
                    render_chip("account_tree", experiment_type, "#44494D")
            ui.button("Quay lại", on_click=lambda: ui.navigate.to("/select-experiment")).props("outline color=grey-7")

        with ui.row().classes("w-full gap-4 mt-4 items-start no-wrap"):
            with ui.column().classes("gap-4 flex-grow"):
                files = {}  # filename -> DataFrame, file_uploader tự ghi vào khi user upload
                target_selects = []  # các ui.select phụ thuộc danh sách cột, refresh khi files đổi

                def refresh_target_options():
                    options = [NO_TARGET] + _column_options(files)
                    for sel in target_selects:
                        sel.set_options(options)

                with ui.card().classes("w-full"):
                    _card_header("upload_file", "#EE0033", "File dữ liệu", "CSV hoặc Excel · tối đa 5 file · 50MB/file", "required")
                    render_data_uploader(files, on_change=refresh_target_options)

                with ui.card().classes("w-full"):
                    _card_header(
                        "description", "#1976D2", "File nghiệp vụ", "Giúp agent hiểu đúng ngữ cảnh domain", "optional"
                    )
                    def _on_domain_change():
                        if not domain_box.get("_active"):
                            return
                        state.set_value("_domain_text", domain_box.get("text", ""))
                        state.set_value("_domain_name", domain_box.get("name") or "")

                    domain_box = render_domain_uploader(
                        on_change=_on_domain_change,
                        initial_text=state.get("_domain_text", ""),
                        initial_name=state.get("_domain_name") or None,
                    )

                with ui.card().classes("w-full"):
                    _card_header(
                        "chat_bubble",
                        "#757575",
                        "Yêu cầu phân tích",
                        "Để trống — agent tự lập kế hoạch dựa trên schema",
                        "optional",
                    )
                    user_query_input = ui.textarea(
                        placeholder='Ví dụ: "So sánh phụ tải ngày lễ và ngày thường, dự báo theo giờ..."'
                    ).props("outlined").classes("w-full")
                    with ui.row().classes("items-start gap-2 mt-2 w-full p-3").style(
                        "background:#FFF8F0; border-left: 3px solid #EE0033; border-radius: 6px;"
                    ):
                        ui.icon("lightbulb", color="#EE0033").style("font-size: 16px; margin-top: 2px;")
                        ui.label(
                            'Càng cụ thể, agent càng tập trung đúng hướng. "So sánh phụ tải ngày lễ và '
                            'ngày thường" tốt hơn "phân tích dữ liệu".'
                        ).classes("text-sm text-gray-700")

                test_box = {"df": None}
                if experiment_type == "Full Pipeline":
                    with ui.card().classes("w-full"):
                        _card_header(
                            "science",
                            "#44494D",
                            "Dữ liệu đánh giá",
                            "File test riêng cho bước Evaluation — nếu không có sẽ dùng phần split từ data chính",
                            "optional",
                        )
                        test_box = render_test_uploader()

                model_path_box = {"value": None, "fallback_value": None}
                target_select = None
                target_manual_input = None

                if experiment_type in ("Đánh giá mô hình", "Suy luận mô hình"):
                    with ui.card().classes("w-full"):
                        _card_header("model_training", "#757575", "Chọn model", "Model đã huấn luyện trước đó", "required")

                        models = []
                        if os.path.isdir(MODEL_DIR):
                            models = [f for f in os.listdir(MODEL_DIR) if f.endswith(".pkl")]
                        model_select = ui.select(models, label="Chọn model có sẵn").classes("w-full") if models else None
                        if model_select is not None:
                            model_path_box["value"] = os.path.join(MODEL_DIR, models[0])
                            model_path_box["fallback_value"] = model_path_box["value"]

                            def on_model_select(e):
                                path = os.path.join(MODEL_DIR, e.value) if e.value else None
                                model_path_box["fallback_value"] = path
                                if not model_path_box.get("uploaded_name"):
                                    model_path_box["value"] = path

                            model_select.on_value_change(on_model_select)

                        render_model_uploader(model_path_box, MODEL_DIR)

                        target_select = ui.select(
                            [NO_TARGET], value=NO_TARGET, label="Cột target (nếu có trong file vừa upload)"
                        ).classes("w-full mt-2")
                        target_selects.append(target_select)
                        target_manual_input = ui.input("Hoặc nhập tên cột target thủ công").classes("w-full")
                        ui.label(
                            "Dùng khi file dữ liệu (đặc biệt Suy luận mô hình) không có cột target — để trống sẽ "
                            "tự lấy tên target đã lưu trong model lúc huấn luyện."
                        ).classes("text-xs text-gray-500")

                task_type_select = None
                split_slider = None
                model_choice_select = None
                model_params_input = None
                optimize_checkbox = None

                if experiment_type in ("Huấn luyện mô hình", "Full Pipeline"):
                    with ui.card().classes("w-full"):
                        _card_header(
                            "model_training", "#F57C00", "Cấu hình huấn luyện", "Áp dụng cho bước Train trong pipeline"
                        )

                        with ui.grid(columns=2).classes("w-full gap-3"):
                            task_type_select = ui.select(
                                list(TASK_TYPE_LABELS.keys()), value="Tự động phát hiện", label="Loại bài toán"
                            ).classes("w-full")

                            target_select_train = ui.select(
                                [NO_TARGET], value=NO_TARGET, label="Cột target (bắt buộc với Regression/Classification)"
                            ).classes("w-full")
                            target_selects.append(target_select_train)
                            if target_select is None:
                                target_select = target_select_train

                            model_choice_select = ui.select(
                                ["Tự động chọn"], value="Tự động chọn", label="Model"
                            ).classes("w-full")

                            with ui.column().classes("gap-1 w-full"):
                                ui.label("Tỷ lệ train/test").classes("text-xs text-gray-500")
                                split_slider = ui.slider(min=0.5, max=0.95, step=0.05, value=0.8).props("label-always")

                        model_params_input = ui.textarea("Tham số tùy chỉnh cho model (JSON, optional)").classes(
                            "w-full mt-2"
                        )
                        model_params_input.bind_visibility_from(
                            model_choice_select, "value", backward=lambda v: v != "Tự động chọn"
                        )

                        def refresh_model_choices(e=None):
                            task_type = TASK_TYPE_LABELS[task_type_select.value]
                            if task_type:
                                model_choice_select.set_options(["Tự động chọn"] + list(MODEL_REGISTRY[task_type].keys()))
                            else:
                                model_choice_select.set_options(["Tự động chọn"])
                                model_choice_select.value = "Tự động chọn"

                        task_type_select.on_value_change(refresh_model_choices)

                        optimize_checkbox = ui.checkbox("Optimize tham số (RandomizedSearch)", value=False).classes(
                            "mt-2"
                        )

                def handle_submit():
                    if domain_box.get("summarizing"):
                        ui.notify("File nghiệp vụ đang được tóm tắt — vui lòng chờ.", color="warning")
                        return
                    if not files:
                        ui.notify("Vui lòng upload ít nhất 1 file dữ liệu.", color="negative")
                        return

                    extra = {}

                    if experiment_type in ("Đánh giá mô hình", "Suy luận mô hình"):
                        if model_path_box["value"]:
                            extra["model_path"] = model_path_box["value"]
                        if target_manual_input and target_manual_input.value.strip():
                            extra["target_col"] = target_manual_input.value.strip()
                        elif target_select and target_select.value != NO_TARGET:
                            extra["target_col"] = target_select.value

                    if experiment_type in ("Huấn luyện mô hình", "Full Pipeline"):
                        task_type = TASK_TYPE_LABELS[task_type_select.value]
                        if task_type:
                            extra["task_type"] = task_type

                        if target_select.value != NO_TARGET:
                            extra["target_col"] = target_select.value
                        elif task_type in ("regression", "classification"):
                            ui.notify("Cần chọn cột target cho Regression/Classification.", color="negative")
                            return

                        extra["split_ratio"] = split_slider.value

                        if model_choice_select.value != "Tự động chọn":
                            extra["selected_model"] = model_choice_select.value
                            if model_params_input.value.strip():
                                try:
                                    extra["model_params"] = json.loads(model_params_input.value)
                                except json.JSONDecodeError as exc:
                                    ui.notify(f"Tham số JSON không hợp lệ: {exc}", color="negative")
                                    return

                        extra["optimize"] = optimize_checkbox.value

                    if test_box["df"] is not None:
                        extra["test_df"] = test_box["df"]

                    # "Yêu cầu phân tích" được phép để trống (agent tự lập kế hoạch theo schema) —
                    # nếu trống, fallback dùng mô tả bài toán đã nhập lúc tạo (problem["description"])
                    # thay vì bỏ phí context user đã tốn công nhập ở bước trước đó.
                    context = ExperimentContext(
                        problem_name=problem["name"],
                        problem_description=problem["description"],
                        experiment_type=experiment_type,
                        files=files,
                        domain_context=domain_box["text"],
                        domain_name=domain_box.get("name") or "",
                        user_query=(user_query_input.value or "").strip() or problem["description"],
                        extra=extra,
                    )
                    domain_box["_active"] = False
                    state.set_value("context_key", state.put_object(context))
                    state.set_value("_domain_text", "")
                    state.set_value("_domain_name", "")
                    state.reset_pipeline_state()
                    ui.navigate.to("/run-experiment")

                with ui.row().classes("w-full items-center gap-2 mt-1"):
                    ui.button("Bắt đầu", icon="play_arrow", on_click=handle_submit, color="primary")
                    ui.button("Quay lại", on_click=lambda: ui.navigate.to("/select-experiment")).props(
                        "outline color=grey-7"
                    )

            _render_sidebar(experiment_type)
