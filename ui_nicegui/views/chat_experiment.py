"""Chatbot — giao diện hội thoại có nút định hướng, gọi lại đúng agent/pipeline đã có.

Xem CHATBOT_FEATURE.md cho toàn bộ quyết định thiết kế (FSM, layout bong bóng/wide-turn).
Giao diện này tham khảo 2 mockup tham khảo (chatbot_design1/2.html, do mentor/người dùng cung
cấp) — đã chốt với người dùng: KHÔNG làm tab bar đa phiên (giữ "1 chat = 1 experiment" như đã
chốt), CÓ đổi sang thanh nhập liệu cố định ở đáy trang (`ui.footer()`).

FSM theo thứ tự (đã chốt lại sau review — khoá upload đến khi biết rõ cần file gì, tránh user
upload nhầm trước khi biết loại experiment cần gì):
intro (mô tả/chọn loại, KHÔNG upload được) → name (đặt tên) → suggest/manual_pick (chốt loại
experiment) → **requirements** (nêu rõ "cần file gì cho loại này", MỞ KHOÁ đúng nút đính kèm
tương ứng `ATTACH_KINDS`/`FILE_REQUIREMENTS`, chặn "Tiếp tục" nếu thiếu file bắt buộc) → confirm
(xác nhận cuối, nút đính kèm khoá lại) → running → result.

Thanh đáy dùng cho 2 chỗ free-text (mô tả ban đầu, góp ý chạy lại) + nút đính kèm riêng từng loại
file (data/domain/model/eval, chỉ mở khoá ở bước "requirements") — "bổ sung yêu cầu" ở bước xác
nhận vẫn nằm trong card đó, không qua thanh đáy.

Đã hỗ trợ: "Khám phá dữ liệu" (EDA), "Xử lý dữ liệu" (Preprocessing) — không cần field cấu hình
riêng ngoài data/domain file (khớp `SIDEBAR_FIELDS` trong experiment_config.py). "Huấn luyện mô
hình" cần field riêng (loại bài toán/cột target/tỷ lệ train-test) — xem `_render_train_config()`.
"Đánh giá mô hình"/"Suy luận mô hình" cần chọn model đã huấn luyện (.pkl, qua nút đính kèm "model"
— `model_dialog`, hỗ trợ cả chọn model có sẵn lẫn upload mới) + cột target tuỳ chọn — xem
`_render_eval_config()`. Cả 2 nhóm field này hiện ở bước "requirements" sau khi đã có file (cần
để liệt kê cột cho dropdown target). "Full Pipeline" cố tình KHÔNG làm qua chatbot (xem
`_NO_PLAN_TYPES`) — nhiều giai đoạn, dùng trang Chọn experiment thường tiện hơn. Mở rộng dần —
xem `_SUPPORTED_TYPES`.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

from nicegui import run as nicegui_run
from nicegui import ui

import state
import theme
from agents import report_generator
from agents.base_agent import ExperimentContext
from agents.router import route
from components.file_uploader import render_data_uploader, render_domain_uploader, render_model_uploader
from components.header import render_breadcrumbs, render_chip, render_header
from components.result_widgets import progress_steps
from llm.client import MODEL_LITE, call_llm
from views.experiment_config import MODEL_DIR, NO_TARGET, TASK_TYPE_LABELS, _column_options
from views.run_experiment import (
    AGENT_PHASES,
    EXPERIMENT_TYPE_TO_KIND,
    MAX_FEEDBACK_CONTEXT_CHARS,
    _agent_running_card,
    _detect_ambiguity,
    _EXPLANATION_ONLY_TYPES,
    _save_run,
    render_result_body,
)
from views.select_experiment import TEMPLATES

# Full Pipeline cố tình KHÔNG làm qua chatbot — nhiều giai đoạn, cần dừng/xem từng bước, làm
# qua trang Chọn experiment thường tiện hơn hẳn (quyết định của người dùng, không phải "sắp có").
_SUPPORTED_TYPES = {
    "Khám phá dữ liệu",
    "Xử lý dữ liệu",
    "Huấn luyện mô hình",
    "Đánh giá mô hình",
    "Suy luận mô hình",
}
_NO_PLAN_TYPES = {"Full Pipeline"}  # khác "chưa hỗ trợ" — cố tình không bao giờ làm qua chatbot
NAME_MAX_LEN = 80
EVAL_TARGET_AUTO = "(Tự động lấy từ model)"

# (kind, icon, label) — nút đính kèm riêng từng loại file ở thanh nhập đáy trang.
ATTACH_KINDS = [
    ("data", "upload_file", "File dữ liệu"),
    ("domain", "description", "File nghiệp vụ"),
    ("model", "smart_toy", "Model (.pkl)"),
]

# Loại nào cần file gì (bắt buộc/không) — dùng để hiện checklist trước khi xác nhận + bật/tắt
# nút đính kèm tương ứng. Khớp với SIDEBAR_FIELDS trong experiment_config.py (wizard) để 2 nơi
# không lệch thông tin.
FILE_REQUIREMENTS = {
    "Khám phá dữ liệu": [("data", "File dữ liệu", True), ("domain", "File nghiệp vụ", False)],
    "Xử lý dữ liệu": [("data", "File dữ liệu", True), ("domain", "File nghiệp vụ", False)],
    "Huấn luyện mô hình": [("data", "File dữ liệu", True), ("domain", "File nghiệp vụ", False)],
    "Đánh giá mô hình": [("data", "File dữ liệu (test)", True), ("model", "Model đã huấn luyện (.pkl)", True)],
    "Suy luận mô hình": [("data", "File dữ liệu mới", True), ("model", "Model đã huấn luyện (.pkl)", True)],
}

_CHAT_CSS = """
/* body/.q-page mặc định nền trắng — khoảng đệm trong suốt của ui.footer() (xem dưới) để lộ nền
   trắng đó ra phía sau, tạo 1 dải trắng "lạc quẻ" ở cuối trang khi cuộn xuống hết. Ép nền xám
   nhẹ xuống tận gốc để không bị lộ màu trắng ở bất kỳ khoảng hở nào. */
body, .q-page, .nicegui-content { background:#F7F7F8 !important; }
.aeda-chat-card { border:0.5px solid rgba(0,0,0,0.07); border-radius:10px; padding:8px 12px !important; }
.aeda-mini-card { transition: transform .15s ease, box-shadow .15s ease; cursor:pointer; }
.aeda-mini-card:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba(238,0,51,0.12); }
.aeda-mini-card.disabled { opacity:0.5; cursor:not-allowed; }
/* Quasar QField luôn dựng kèm .q-field__bottom (vùng hint/error/counter) chiếm chỗ trong layout
   dù rỗng, kể cả khi đã có prop hide-bottom-space — đây mới là khoảng hở thật sự co giãn không
   đều theo số dòng lúc autogrow, không phải margin/padding ta tự set. Tắt hẳn nó + bỏ padding
   nội bộ field cho riêng textarea composer (không đụng các ui.textarea() khác trong file, vd
   supplement_input ở bước xác nhận). */
.aeda-composer-textarea .q-field__bottom {
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}
.aeda-composer-textarea .q-field__control,
.aeda-composer-textarea .q-field__control-container {
  min-height: 0 !important;
  padding: 0 !important;
}
.aeda-composer-textarea textarea {
  padding: 0 !important;
  margin: 0 !important;
  line-height: 1.55 !important;
}
"""


# datetime.now() lấy giờ local của SERVER (container chạy UTC) — không phải giờ người dùng.
# Việt Nam không có DST nên fix cứng UTC+7 là đủ, không cần phụ thuộc tzdata/zoneinfo của OS.
_VN_TZ = timezone(timedelta(hours=7))


def _now_str():
    return datetime.now(_VN_TZ).strftime("%H:%M")


def _format_duration(seconds):
    if seconds is None:
        return "—"
    seconds = max(int(seconds), 0)
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m {seconds % 60}s"


def _suggest_problem_name(description):
    try:
        raw = call_llm(
            "Đặt 1 tên ngắn gọn (dưới 10 từ, tiếng Việt, không markdown, không ngoặc kép) cho "
            f"bài toán phân tích dữ liệu sau:\n\n{description}",
            system="Bạn chỉ trả về đúng 1 dòng tên ngắn gọn, không giải thích thêm.",
            model=MODEL_LITE,
        )
        name = (raw or "").strip().strip("\"'").splitlines()[0].strip()
        return (name or description)[:NAME_MAX_LEN] or "Bài toán mới"
    except Exception:
        return (description or "Bài toán mới")[:NAME_MAX_LEN]


def _suggest_experiment_type(description, files):
    # Chỉ gợi ý các loại chatbot hỗ trợ thực sự — _NO_PLAN_TYPES (Full Pipeline) bị loại khỏi
    # danh sách vì (a) chatbot không làm được và (b) LLM hay chọn nhầm khi mô tả có nhiều mục tiêu.
    valid_names = [t["name"] for t in TEMPLATES if t["name"] not in _NO_PLAN_TYPES]
    _OPTION_HINTS = {
        "Khám phá dữ liệu": "phân tích, tìm hiểu, khám phá, EDA, thống kê, visualize, tìm pattern, xu hướng, tương quan",
        "Xử lý dữ liệu": "làm sạch, điền missing, xử lý outlier, encode, chuẩn hóa, preprocessing",
        "Huấn luyện mô hình": "train, xây dựng model, dự đoán, phân loại, hồi quy, phân nhóm, machine learning",
        "Đánh giá mô hình": "đánh giá, kiểm tra model đã train, accuracy, F1, metrics, test set",
        "Suy luận mô hình": "dự đoán trên dữ liệu mới, inference, predict, áp dụng model có sẵn",
    }
    columns = []
    for df in files.values():
        columns.extend(df.columns.tolist())
    schema_hint = ", ".join(sorted(set(columns))[:30])
    options_text = "\n".join(
        f"- {n} ({_OPTION_HINTS.get(n, '')})" for n in valid_names
    )
    try:
        raw = call_llm(
            "Dựa trên mô tả nhu cầu và tên cột dữ liệu sau, chọn ĐÚNG 1 loại experiment phù hợp "
            f"nhất từ danh sách (trả về NGUYÊN VĂN đúng 1 tên loại — phần trước dấu ngoặc đơn, không thêm gì khác):\n"
            f"{options_text}\n\nMô tả: {description}\nCác cột dữ liệu: {schema_hint or '(không rõ)'}",
            system="Bạn chỉ trả về đúng nguyên văn 1 dòng tên loại experiment có trong danh sách, không giải thích.",
            model=MODEL_LITE,
        )
        guess = (raw or "").strip().strip("\"'").splitlines()[0].strip()
        return guess if guess in valid_names else "Khám phá dữ liệu"
    except Exception:
        return "Khám phá dữ liệu"


def _check_relevant(text, files):
    """Gọi MODEL_LITE (rẻ) phân loại text có liên quan đến phân tích/xử lý dữ liệu hay huấn
    luyện/đánh giá/suy luận mô hình không — chặn mô tả/góp ý lạc đề (thảo luận xem
    CHATBOT_FEATURE.md). Dùng CHUNG cho cả bước xác nhận (gộp với `_detect_ambiguity`) lẫn bước
    góp ý chạy lại (chặn thẳng trước khi cho chạy lại) — 1 hàm, 2 nơi gọi.

    Fail-open (coi là liên quan) khi gọi LLM lỗi — tránh chặn oan vì lỗi mạng/API, đúng tinh thần
    "rào nhẹ, không làm phiền" chứ không phải rào cứng tuyệt đối."""
    if not (text or "").strip():
        return True  # rỗng xử lý riêng ở chỗ gọi (không phải lỗi "không liên quan")
    schema_hint = ", ".join(sorted({c for df in files.values() for c in df.columns})[:20])
    try:
        raw = call_llm(
            "Câu sau có liên quan đến việc mô tả/yêu cầu phân tích dữ liệu, xử lý dữ liệu, hoặc "
            "huấn luyện/đánh giá/suy luận mô hình không? Chỉ trả lời đúng 1 từ: CO hoặc KHONG.\n\n"
            f"Câu: {text}\nCác cột dữ liệu liên quan (nếu có): {schema_hint or '(không có)'}",
            system="Bạn chỉ trả lời đúng 1 từ CO hoặc KHONG, không giải thích gì thêm.",
            model=MODEL_LITE,
        )
        answer = (raw or "").strip().upper()
        return "KHONG" not in answer
    except Exception:
        return True


def _avatar(role):
    bg = "#EE0033" if role == "bot" else "#44494D"
    icon = "smart_toy" if role == "bot" else "person"
    with ui.element("div").classes("rounded-full flex items-center justify-center").style(
        f"background:{bg}; width:26px; height:26px; flex-shrink:0;"
    ):
        ui.icon(icon, color="white").style("font-size:14px;")


def _bot_bubble(builder, time_str=None):
    with ui.row().classes("w-full justify-start items-end gap-2 no-wrap"):
        _avatar("bot")
        with ui.column().classes("gap-0"):
            with ui.card().classes("aeda-chat-card gap-2").style("max-width:680px; background:#fff;"):
                builder()
            if time_str:
                ui.label(time_str).classes("text-xs text-gray-400")


def _user_bubble(text, time_str=None):
    with ui.row().classes("w-full justify-end items-end gap-2 no-wrap"):
        with ui.column().classes("gap-0 items-end"):
            with ui.card().classes("aeda-chat-card").style("max-width:680px; background:#FFF1F3;"):
                ui.label(text).classes("text-sm").style("color:#1a1a1a;")
            if time_str:
                ui.label(time_str).classes("text-xs text-gray-400")
        _avatar("user")


def _wide_row(builder):
    with ui.row().classes("w-full justify-start items-start gap-2 no-wrap"):
        _avatar("bot")
        with ui.column().classes("gap-2 flex-grow").style("max-width:1060px;"):
            builder()


def _wide_card(icon, color, title, subtitle, body_builder, chips_builder=None):
    """Card "đầu mục + chip + nội dung" — mẫu dùng cho confirm/running/kết quả, tham khảo
    `.wide-card`/`.wc-head` trong 2 mockup (chip trạng thái nằm bên phải đầu mục)."""
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-3 w-full pb-2 mb-2 no-wrap").style(
            "border-bottom:0.5px solid rgba(0,0,0,0.07);"
        ):
            with ui.element("div").classes("flex items-center justify-center").style(
                f"background:{color}1A; color:{color}; width:30px; height:30px; flex-shrink:0; border-radius:7px;"
            ):
                ui.icon(icon, color=color).style("font-size:16px;")
            with ui.column().classes("gap-0 flex-grow"):
                ui.label(title).classes("text-sm font-medium")
                if subtitle:
                    ui.label(subtitle).classes("text-xs text-gray-400")
            if chips_builder:
                with ui.row().classes("gap-1 flex-shrink-0"):
                    chips_builder()
        body_builder()


def _render_message(m):
    if m["role"] == "user":
        _user_bubble(m["text"], m.get("time"))
        return
    if m.get("kind") == "wide":
        _wide_row(m["render"])
        return
    _bot_bubble(lambda m=m: ui.label(m["text"]).classes("text-sm"), m.get("time"))


def _render_run_progress_card(experiment_type, duration):
    """Card "Tiến trình thực thi" giữ LẠI vĩnh viễn trong lịch sử chat (khác lúc đang chạy —
    `_agent_running_card` chỉ tồn tại tạm thời trong lúc await agent.run()). Đây là danh sách
    CÁC BƯỚC (giống `AGENT_PHASES`/`progress_steps` lúc đang chạy, đánh dấu "done" hết) — KHÔNG
    phải "Nhật ký thực thi" (log thô từng tool call), cái đó đã có riêng ở card kết quả
    (`render_result_body` → `render_log_card`), tránh trùng lặp."""
    phases = AGENT_PHASES.get(experiment_type, ["Agent đã xử lý xong"])

    def chips():
        render_chip("schedule", duration, "#5F5E5A")

    def body():
        progress_steps([{"label": p, "status": "done"} for p in phases])

    _wide_card("autorenew", "#2E7D32", "Tiến trình thực thi", experiment_type, body, chips)


def _unsupported_type_message(name):
    if name in _NO_PLAN_TYPES:
        return (
            f"\"{name}\" cố tình không làm qua chatbot — nhiều giai đoạn, cần dừng/xem từng "
            "bước, dùng trang Chọn experiment thường sẽ tiện hơn hẳn."
        )
    return f"\"{name}\" chưa hỗ trợ qua chatbot — dùng 1 loại đã hỗ trợ ở trên, hoặc trang Chọn experiment thường."


def _mini_type_card(template, enabled, on_click):
    classes = "aeda-mini-card w-full" + ("" if enabled else " disabled")
    with ui.card().classes(classes).style("padding:7px 9px;") as card:
        with ui.row().classes("items-center gap-2 no-wrap w-full"):
            with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                f"background:{template['color']}1A; width:26px; height:26px; flex-shrink:0;"
            ):
                ui.icon(template["icon"], color=template["color"]).style("font-size:13px;")
            with ui.column().classes("gap-0"):
                ui.label(template["name"]).classes("text-xs font-medium")
                if enabled:
                    ui.label(template.get("time_estimate", "")).classes("text-xs text-gray-400")
            if not enabled:
                badge_text = "Dùng trang thường" if template["name"] in _NO_PLAN_TYPES else "Sắp có"
                ui.label(badge_text).classes("text-xs flex-shrink-0").style(
                    "background:#F1EFE8; color:#888; border-radius:3px; padding:1px 5px; margin-left:auto;"
                )
    if enabled:
        card.on("click", on_click)
    return card


@ui.page("/chat")
async def chat_page():
    theme.apply()
    state.ensure_defaults()
    ui.add_css(_CHAT_CSS)
    render_header()
    render_breadcrumbs([("Trang chủ", "/"), ("Chatbot", None)])

    if state.get("chat_running"):
        with ui.column().classes("w-full items-center").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
            ui.label("Có 1 phiên chat đang xử lý — vui lòng chờ hoặc quay lại sau ít phút.").classes(
                "text-orange-600 mt-6"
            )
            ui.button("Về trang chủ", on_click=lambda: ui.navigate.to("/")).classes("mt-2")
        return

    session = {
        "stage": "intro",
        "description": "",
        "files": {},
        "domain_box": {"text": ""},
        "problem_name": None,
        "experiment_type": None,
        "supplement": "",
        "context": None,
        "result": None,
        "locked": False,
        "run_start": None,
        # Field cấu hình riêng theo loại experiment (xem `render_requirements_stage`). Lưu ở
        # session để KHÔNG mất giá trị đã chọn mỗi lần upload file kích hoạt rerun() (cùng lý do
        # đã xử lý cho q1/q2 ở bước xác nhận).
        "train_config": {"task_type": "Tự động phát hiện", "target_col": NO_TARGET, "split_ratio": 0.8},
        "model_box": {"value": None, "fallback_value": None},
        "eval_config": {"target_col": EVAL_TARGET_AUTO},
    }
    messages = [
        {
            "role": "bot",
            "text": (
                "Mô tả nhu cầu của bạn vào khung chat bên dưới, rồi mình sẽ gợi ý loại experiment "
                "phù hợp — hoặc bấm thẳng 1 loại bên dưới nếu bạn đã biết rõ. Sau khi xác định "
                "loại experiment, mình sẽ nói rõ cần upload file gì rồi mới mở khoá phần upload."
            ),
            "time": _now_str(),
        }
    ]

    with ui.column().classes("w-full items-center").style("background:#F7F7F8; min-height:100vh; padding:24px;"):
        transcript_zone = ui.column().classes("w-full gap-3").style("max-width:1100px;")

    def _current_requirements():
        return FILE_REQUIREMENTS.get(session["experiment_type"] or "Khám phá dữ liệu", [])

    def _has_kind(kind):
        if kind == "data":
            return bool(session["files"])
        if kind == "domain":
            return bool(session["domain_box"].get("text")) and not session["domain_box"].get("summarizing")
        if kind == "model":
            return bool(session["model_box"].get("value"))
        return False

    # Footer trong suốt (không cắt ngang trang bằng 1 dải full-width) — khung nhập THẬT là 1
    # card bo tròn, thu hẹp, "nổi" phía trên nội dung, giống thanh chat tham khảo (gọn, không
    # đè hết nền) thay vì 1 thanh ngang cồng kềnh.
    with ui.footer().props("bordered=false elevated=false").style("background:transparent; box-shadow:none; padding:0 16px 14px 16px;"):
        with ui.column().classes("w-full items-center"):
            with ui.card().classes("w-full gap-1").style(
                "max-width:860px; border-radius:16px; padding:10px 14px 8px 14px; "
                "box-shadow:0 4px 18px rgba(0,0,0,0.14); border:0.5px solid rgba(0,0,0,0.08); background:#fff;"
            ):
                context_zone = ui.column().classes("w-full gap-1")
                composer_zone = ui.column().classes("w-full gap-1")

    data_dialog = ui.dialog()
    with data_dialog, ui.card().style("min-width:440px;"):
        ui.label("File dữ liệu").classes("text-sm font-medium mb-1").style("color:#1a1a1a;")
        # on_change của render_data_uploader gọi ĐỒNG BỘ (không await) nên không thể truyền trực
        # tiếp rerun() (async) — dùng create_task để vẫn refresh được cả checklist ở bước "cần
        # file gì" (`render_requirements_stage`) lẫn chip ở thanh đáy, không chỉ riêng thanh đáy.
        refresh_data_list = render_data_uploader(
            session["files"], on_change=lambda: asyncio.create_task(rerun())
        )
        ui.button("Đóng", on_click=data_dialog.close).props("flat color=grey-7").classes("mt-2")

    domain_dialog = ui.dialog()
    with domain_dialog, ui.card().style("min-width:440px;"):
        ui.label("File nghiệp vụ").classes("text-sm font-medium mb-1").style("color:#1a1a1a;")
        _prev_domain = session.get("domain_box", {})
        session["domain_box"] = render_domain_uploader(
            on_change=lambda: asyncio.create_task(rerun()),
            initial_text=_prev_domain.get("text", ""),
            initial_name=_prev_domain.get("name"),
        )

        async def close_domain_dialog():
            domain_dialog.close()
            await rerun()

        ui.button("Đóng", on_click=close_domain_dialog).props("flat color=grey-7").classes("mt-2")

    model_dialog = ui.dialog()
    with model_dialog, ui.card().style("min-width:440px;"):
        ui.label("Model đã huấn luyện").classes("text-sm font-medium mb-1").style("color:#1a1a1a;")
        # 2 cách chọn model, khớp đúng wizard (experiment_config.py): (1) chọn từ model đã lưu
        # sẵn trên đĩa (các lần Huấn luyện trước đó), (2) upload file .pkl mới — upload luôn ưu
        # tiên hơn nếu cả 2 đều có (logic y hệt model_path_box ở wizard).
        existing_models = []
        if os.path.isdir(MODEL_DIR):
            existing_models = sorted(f for f in os.listdir(MODEL_DIR) if f.endswith(".pkl"))
        if existing_models:
            ui.label("Chọn model có sẵn:").classes("text-xs text-gray-600 mt-1")

            async def on_model_select(e):
                if e.value:
                    path = os.path.join(MODEL_DIR, e.value)
                    session["model_box"]["value"] = path
                    session["model_box"]["fallback_value"] = path
                    session["model_box"]["uploaded_name"] = None
                    await rerun()

            ui.select(existing_models, label="Model đã lưu").classes("w-full").on_value_change(on_model_select)
        else:
            ui.label("Chưa có model nào được lưu sẵn — upload file .pkl bên dưới.").classes(
                "text-xs text-gray-400"
            )
        refresh_model_list = render_model_uploader(
            session["model_box"], MODEL_DIR, on_change=lambda: asyncio.create_task(rerun())
        )

        async def close_model_dialog():
            model_dialog.close()
            await rerun()

        ui.button("Đóng", on_click=close_model_dialog).props("flat color=grey-7").classes("mt-2")

    def render_context_row():
        context_zone.clear()
        with context_zone:
            # Chỉ cho thêm/xoá file ở đúng bước "cần file gì" (`render_requirements_stage`) — sau
            # khi loại experiment đã chốt. Tại các bước trước đó (chưa biết loại), nút đính kèm
            # khoá hẳn (xem yêu cầu: "block upload, xác nhận loại trước rồi mới unlock").
            can_edit_files = session["stage"] == "requirements" and not session["locked"]

            with ui.row().classes("items-center gap-2 flex-wrap"):
                for name in session["files"]:
                    with ui.row().classes("items-center gap-1 px-2 py-1 rounded").style(
                        "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.1);"
                    ):
                        ui.icon("description", color="#EE0033").style("font-size:13px;")
                        ui.label(name).classes("text-xs").style("color:#333;")
                        if can_edit_files:

                            async def remove_file(name=name):
                                session["files"].pop(name, None)
                                refresh_data_list()  # đồng bộ lại danh sách trong dialog (bug đã gặp)
                                await rerun()

                            ui.icon("close", color="grey-5").style("font-size:12px; cursor:pointer;").on(
                                "click", remove_file
                            )
                if session["domain_box"].get("name"):
                    with ui.row().classes("items-center gap-1 px-2 py-1 rounded").style(
                        "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.1);"
                    ):
                        ui.icon("description", color="#1976D2").style("font-size:13px;")
                        ui.label(session["domain_box"]["name"]).classes("text-xs").style("color:#333;")
                        if can_edit_files:

                            async def remove_domain():
                                session["domain_box"]["text"] = ""
                                session["domain_box"]["name"] = None
                                session["domain_box"]["_refresh"]()  # đồng bộ lại dialog
                                await rerun()

                            ui.icon("close", color="grey-5").style("font-size:12px; cursor:pointer;").on(
                                "click", remove_domain
                            )
                if session["model_box"].get("value"):
                    with ui.row().classes("items-center gap-1 px-2 py-1 rounded").style(
                        "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.1);"
                    ):
                        ui.icon("smart_toy", color="#44494D").style("font-size:13px;")
                        ui.label(os.path.basename(session["model_box"]["value"])).classes("text-xs").style(
                            "color:#333;"
                        )
                        if can_edit_files:

                            async def remove_model():
                                session["model_box"]["value"] = None
                                session["model_box"]["fallback_value"] = None
                                session["model_box"]["uploaded_name"] = None
                                refresh_model_list()  # đồng bộ lại danh sách trong dialog
                                await rerun()

                            ui.icon("close", color="grey-5").style("font-size:12px; cursor:pointer;").on(
                                "click", remove_model
                            )
                if session["experiment_type"]:
                    # KHÔNG có nút "Đổi" nhanh ở đây nữa — loại experiment coi như đã CHỐT ngay
                    # khi bước qua "requirements" (lúc này nút đính kèm đã hiện đúng theo loại đó,
                    # đổi loại giữa chừng mà không dọn lại file đã chọn sẽ gây lệch). Muốn đổi
                    # loại, dùng nút "Đổi loại experiment" tường minh TRONG card "File cần thiết"
                    # (`render_requirements_stage`) — nút đó dọn sạch file đã chọn trước khi quay
                    # lại chọn loại khác, tránh đúng vụ lệch này.
                    with ui.row().classes("items-center gap-1 px-2 py-1 rounded").style(
                        "background:#fff0f3; border:0.5px solid rgba(238,0,51,0.2);"
                    ):
                        ui.icon("bar_chart", color="#EE0033").style("font-size:13px;")
                        ui.label(session["experiment_type"]).classes("text-xs").style("color:#993035;")

    def render_composer():
        """Textarea (gọn, autogrow) ở trên + 1 toolbar duy nhất ở dưới (icon đính kèm bên trái,
        nút gửi bên phải) — đúng pattern composer chuẩn (Claude/GPT/Gemini), thay vì tách rời
        hàng icon phía trên và nút gửi lệch ra ngoài như bản cũ."""
        composer_zone.clear()
        with composer_zone:
            stage = session["stage"]
            _exp_type = session.get("experiment_type") or ""
            _can_refine = _exp_type not in _EXPLANATION_ONLY_TYPES
            enabled = stage == "intro" or (stage == "result" and _can_refine)
            placeholder = {
                "intro": 'Vd: "Phân tích các yếu tố ảnh hưởng tới nghỉ việc nhân sự quý 1"...',
                "result": "Góp ý để chạy lại theo hướng khác..." if _can_refine else "Loại experiment này không hỗ trợ chạy lại",
            }.get(stage, "Hoàn tất bước hiện tại ở trên trước...")

            # hide-bottom-space: Quasar QField mặc định chừa sẵn 1 khoảng trống dưới field cho
            # slot hint/error dù không dùng — khoảng trống đó có thể hiện/biến mất không đều giữa
            # các lần autogrow tính lại chiều cao, tạo cảm giác toolbar bên dưới "nhảy"/lệch theo
            # số dòng text. Tắt hẳn slot đó cho chắc, layout chỉ còn phụ thuộc đúng 1 nguồn: chiều
            # cao thật của textarea.
            # padding-bottom cố định lớn hơn — Quasar tính lại line-height/padding nội bộ của
            # field mỗi lần autogrow đổi số dòng, dòng cuối có thể trồi sát đáy field hơn dự kiến
            # lúc nhiều dòng. Đệm sẵn khoảng trống dưới đủ rộng để dòng cuối không bao giờ áp sát
            # mép field, tách nguồn co giãn (chiều cao text) khỏi khoảng cách thị giác tới toolbar.
            text_input = ui.textarea(placeholder=placeholder).props(
                "borderless autogrow hide-bottom-space" + ("" if enabled else " disable")
            ).classes("w-full aeda-composer-textarea").style(
                "min-height:24px; color:#1a1a1a; padding:4px 4px 8px 4px;"
            )

            async def send():
                text = (text_input.value or "").strip()
                stage = session["stage"]
                if stage == "intro":
                    if not text:
                        ui.notify("Vui lòng nhập mô tả nhu cầu trước khi gửi.", color="negative")
                        return
                    session["description"] = text
                    messages.append({"role": "user", "text": text, "time": _now_str()})
                    session["stage"] = "name"
                    await rerun()
                elif stage == "result":
                    if not text:
                        ui.notify("Vui lòng nhập góp ý trước khi gửi.", color="negative")
                        return
                    if session.get("experiment_type") in _EXPLANATION_ONLY_TYPES:
                        return
                    # Góp ý chạy lại tốn nguyên 1 lượt chạy agent thật — chặn LUÔN tại đây nếu
                    # nội dung không liên quan (khác bước xác nhận chỉ hiện thêm câu hỏi làm rõ,
                    # không chặn) vì không có bước xác nhận nào ở refine để "đỡ" như bên đó.
                    relevant = await nicegui_run.io_bound(_check_relevant, text, session["files"])
                    if not relevant:
                        ui.notify(
                            "Góp ý này có vẻ không liên quan đến phân tích dữ liệu/mô hình — "
                            "vui lòng nhập lại.",
                            color="negative",
                        )
                        return
                    # Thứ tự đúng trong chat: [kết quả Run N] → [góp ý user] → [running Run N+1]
                    # Freeze kết quả hiện tại vào messages TRƯỚC khi append user message.
                    _r = session["result"]
                    _ctx = session["context"]
                    _k = EXPERIMENT_TYPE_TO_KIND.get(_ctx.experiment_type, "eda")
                    _dur = (
                        _format_duration((datetime.now() - session["run_start"]).total_seconds())
                        if session["run_start"] else "—"
                    )
                    _et = _ctx.experiment_type
                    _ok = _r.success
                    _ic = "check_circle" if _ok else "error"
                    _cl = "#2E7D32" if _ok else "#C62828"

                    def _fchips(dur=_dur, ok=_ok):
                        ui.badge("Thành công" if ok else "Lỗi", color="positive" if ok else "negative").classes("text-xs px-2")
                        render_chip("schedule", dur, "#5F5E5A")

                    def _fbody(r=_r, k=_k, ctx=_ctx):
                        render_result_body(r, k, ctx)

                    messages.append({
                        "role": "bot",
                        "kind": "wide",
                        "render": lambda ic=_ic, cl=_cl, et=_et: _wide_card(ic, cl, "Kết quả phân tích", et, _fbody, _fchips),
                    })
                    messages.append({"role": "user", "text": text, "time": _now_str()})
                    await _trigger_refine(text)
                else:
                    ui.notify("Vui lòng hoàn tất lựa chọn ở trên trước.", color="warning")

            can_edit_files = stage == "requirements" and not session["locked"]
            reqs = _current_requirements()
            needed_kinds = {k for k, _, _ in reqs}

            # flex-shrink:0 — toolbar luôn giữ nguyên chiều cao thật của nó, không bị flexbox co
            # kéo lúc textarea phía trên cao lên (đề phòng trường hợp composer_zone vô tình bị
            # ép vào 1 flex context theo hàng ngang ở đâu đó thay vì cột dọc như ý). mt-1 — khoảng
            # cách CỐ ĐỊNH tới textarea phía trên, không phụ thuộc padding nội bộ Quasar field lúc
            # autogrow đổi số dòng (xem comment ở text_input phía trên).
            with ui.row().classes("w-full items-center justify-between gap-2 mt-1").style("flex-shrink:0;"):
                with ui.row().classes("gap-1 items-center"):
                    for kind, icon, label in ATTACH_KINDS:
                        attach_enabled = kind in needed_kinds and can_edit_files
                        btn = ui.button(icon=icon).props(
                            "flat round dense size=sm color=grey-7" + ("" if attach_enabled else " disable")
                        )
                        if attach_enabled:
                            btn.tooltip(label)
                        elif stage != "requirements":
                            btn.tooltip(f"{label} — xác nhận loại experiment trước")
                        else:
                            btn.tooltip(f"{label} — chưa cần cho loại này")
                        if attach_enabled and kind == "data":
                            btn.on_click(data_dialog.open)
                        elif attach_enabled and kind == "domain":
                            btn.on_click(domain_dialog.open)
                        elif attach_enabled and kind == "model":
                            btn.on_click(model_dialog.open)

                ui.button(icon="send", on_click=send, color="primary").props(
                    "round dense" + ("" if enabled else " disable")
                )

    def render_footer():
        render_context_row()
        render_composer()

    async def rerun():
        transcript_zone.clear()
        with transcript_zone:
            for m in messages:
                _render_message(m)
            await render_stage()
        render_footer()

    def _render_file_checklist():
        reqs = _current_requirements()
        all_ok = True
        with ui.column().classes("gap-1 w-full p-2 mb-2").style(
            "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px;"
        ):
            ui.label(f'Cần cho "{session["experiment_type"]}":').classes("text-xs font-medium text-gray-600")
            for kind, label, required in reqs:
                present = _has_kind(kind)
                if required and not present:
                    all_ok = False
                if present:
                    icon, color = "check_circle", "#2E7D32"
                elif required:
                    icon, color = "cancel", "#C62828"
                else:
                    icon, color = "remove_circle_outline", "#9E9E9E"
                with ui.row().classes("items-center gap-2"):
                    ui.icon(icon, color=color).style("font-size:14px;")
                    ui.label(label + ("" if required else " (không bắt buộc)")).classes("text-xs").style(
                        f"color:{color};"
                    )
        return all_ok

    def _render_train_config():
        """Field cấu hình riêng cho Huấn luyện mô hình — loại bài toán/cột target/tỷ lệ
        train-test, khớp đúng field wizard có ở `experiment_config.py` (bỏ bớt phần nâng cao:
        chọn model cụ thể/tham số JSON/optimize — auto-chọn model tốt nhất, đúng tinh thần
        chatbot hướng người dùng không chuyên, không bắt chọn từng siêu tham số).
        Đọc/ghi trực tiếp `session["train_config"]` (không dùng biến cục bộ) để giá trị đã
        chọn KHÔNG mất khi upload file kích hoạt rerun() giữa chừng (cùng lý do với q1/q2)."""
        tc = session["train_config"]
        target_options = [NO_TARGET] + _column_options(session["files"])
        if tc["target_col"] not in target_options:
            tc["target_col"] = NO_TARGET

        with ui.column().classes("w-full gap-2 mt-2 p-2").style(
            "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px;"
        ):
            ui.label("Cấu hình huấn luyện:").classes("text-xs font-medium text-gray-600")
            with ui.grid(columns=2).classes("w-full gap-2"):
                task_select = ui.select(
                    list(TASK_TYPE_LABELS.keys()), value=tc["task_type"], label="Loại bài toán"
                ).classes("w-full")
                task_select.on_value_change(lambda e: tc.update(task_type=e.value))

                target_select = ui.select(
                    target_options, value=tc["target_col"], label="Cột target"
                ).classes("w-full")
                target_select.on_value_change(lambda e: tc.update(target_col=e.value))

            with ui.column().classes("gap-1 w-full"):
                ui.label(f'Tỷ lệ train/test: {tc["split_ratio"]:.0%} / {1 - tc["split_ratio"]:.0%}').classes(
                    "text-xs text-gray-500"
                )
                split_slider = ui.slider(min=0.5, max=0.95, step=0.05, value=tc["split_ratio"]).props(
                    "label-always"
                )
                split_slider.on_value_change(lambda e: tc.update(split_ratio=e.value))

    def _render_eval_config():
        """Field cấu hình riêng cho Đánh giá mô hình/Suy luận mô hình — chỉ 1 field (cột target,
        không bắt buộc): khớp tinh thần wizard nhưng bỏ ô nhập tay riêng (wizard có cả dropdown
        lẫn input tay — chatbot gộp lại 1 dropdown cho gọn, mặc định "tự động lấy từ model" như
        wizard để trống vẫn làm). Đọc/ghi `session["eval_config"]` (không biến cục bộ) — cùng lý
        do với `_render_train_config`."""
        ec = session["eval_config"]
        target_options = [EVAL_TARGET_AUTO] + _column_options(session["files"])
        if ec["target_col"] not in target_options:
            ec["target_col"] = EVAL_TARGET_AUTO

        with ui.column().classes("w-full gap-2 mt-2 p-2").style(
            "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px;"
        ):
            ui.label("Cấu hình:").classes("text-xs font-medium text-gray-600")
            target_select = ui.select(
                target_options, value=ec["target_col"], label="Cột target (nếu có trong file)"
            ).classes("w-full")
            target_select.on_value_change(lambda e: ec.update(target_col=e.value))

    def render_intro_stage():
        with ui.column().classes("gap-1 w-full p-3").style(
            "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.08); border-radius:8px; max-width:680px;"
        ):
            ui.label(
                "Chưa cần upload file ngay — xác định loại experiment trước, mình sẽ nói rõ cần "
                "file gì rồi mới mở khoá phần upload tương ứng. Hiện chatbot chạy được "
                "\"Khám phá dữ liệu\", \"Xử lý dữ liệu\", \"Huấn luyện mô hình\", \"Đánh giá mô "
                "hình\" và \"Suy luận mô hình\" — riêng \"Full Pipeline\" làm ở trang Chọn "
                "experiment thường sẽ tiện hơn (nhiều giai đoạn, cần dừng/xem từng bước)."
            ).classes("text-xs text-gray-500")

        ui.label("Hoặc bấm thẳng 1 loại experiment (bỏ qua bước gợi ý):").classes("text-xs text-gray-400 mt-2")
        with ui.grid(columns=3).classes("gap-2 w-full").style("max-width:680px;"):
            for t in TEMPLATES:
                enabled = t["name"] in _SUPPORTED_TYPES

                async def pick(t=t, enabled=enabled):
                    if not enabled:
                        ui.notify(_unsupported_type_message(t["name"]), color="warning")
                        return
                    session["experiment_type"] = t["name"]
                    messages.append({"role": "user", "text": f"Tôi muốn làm: {t['name']}", "time": _now_str()})
                    session["stage"] = "name"
                    await rerun()

                _mini_type_card(t, enabled, pick)

    async def _finish_name(name):
        session["problem_name"] = name
        session.pop("renaming", None)
        problems = state.get("problems", [])
        problems.append({"name": name, "description": session["description"] or session["experiment_type"]})
        state.set_value("problems", problems)
        state.set_value("current_problem_idx", len(problems) - 1)
        messages.append({"role": "bot", "text": f'Đã tạo bài toán "{name}".', "time": _now_str()})
        session["stage"] = "suggest" if session["experiment_type"] is None else "requirements"
        await rerun()

    async def render_name_stage():
        if "name_suggested" not in session:
            session["name_suggested"] = await nicegui_run.io_bound(
                _suggest_problem_name, session["description"] or session["experiment_type"]
            )
        suggested = session["name_suggested"]

        if session.get("renaming"):
            _bot_bubble(lambda: ui.label("Bạn muốn đặt tên gì cho bài toán này?").classes("text-sm"))
            with ui.column().classes("gap-2").style("max-width:680px;"):
                name_input = ui.input(value=suggested).props(f"outlined maxlength={NAME_MAX_LEN}").classes("w-full")

                async def confirm_rename():
                    name = (name_input.value or "").strip()
                    if not name:
                        ui.notify("Vui lòng nhập tên bài toán.", color="negative")
                        return
                    await _finish_name(name)

                ui.button("Xác nhận tên", icon="check", on_click=confirm_rename, color="primary")
            return

        _bot_bubble(lambda: ui.label(f'Mình đặt tên bài toán này là: "{suggested}" — OK chứ?').classes("text-sm"))

        async def accept():
            await _finish_name(suggested)

        async def start_rename():
            session["renaming"] = True
            await rerun()

        with ui.row().classes("gap-2 mt-1"):
            ui.button("Đồng ý", icon="check", on_click=accept, color="primary")
            ui.button("Đổi tên khác", on_click=start_rename).props("outline color=grey-7")

    async def render_suggest_stage():
        if "type_suggestion" not in session:
            session["type_suggestion"] = await nicegui_run.io_bound(
                _suggest_experiment_type, session["description"], session["files"]
            )
        suggestion = session["type_suggestion"]
        template = next((t for t in TEMPLATES if t["name"] == suggestion), TEMPLATES[0])

        def _content():
            ui.label("Có vẻ bạn cần:").classes("text-sm")
            with ui.row().classes("items-center gap-2 mt-1 px-3 py-2 rounded-lg").style(
                f"background:{template['color']}0D; border:0.5px solid {template['color']}33;"
            ):
                ui.icon(template["icon"], color=template["color"])
                ui.label(template["name"]).classes("text-sm font-medium").style(f"color:{template['color']};")
            ui.label("— đúng không?").classes("text-sm mt-1")

        _bot_bubble(_content)

        async def accept():
            messages.append({"role": "user", "text": f"Đúng, dùng {suggestion}", "time": _now_str()})
            if suggestion not in _SUPPORTED_TYPES:
                ui.notify(f'"{suggestion}" chưa hỗ trợ qua chatbot — chọn loại khác bên dưới.', color="warning")
                session["stage"] = "manual_pick"
            else:
                session["experiment_type"] = suggestion
                session["stage"] = "requirements"
            await rerun()

        async def reject():
            messages.append({"role": "user", "text": "Để tôi chọn loại khác", "time": _now_str()})
            session["stage"] = "manual_pick"
            await rerun()

        with ui.row().classes("gap-2 mt-1"):
            ui.button("Đúng, dùng cái này", icon="check", on_click=accept, color="primary")
            ui.button("Để tôi chọn loại khác", on_click=reject).props("outline color=grey-7")

    async def render_manual_pick_stage():
        _bot_bubble(lambda: ui.label("Chọn 1 loại experiment bên dưới:").classes("text-sm"))

        with ui.grid(columns=3).classes("gap-2 w-full mt-1").style("max-width:680px;"):
            for t in TEMPLATES:
                enabled = t["name"] in _SUPPORTED_TYPES

                async def pick(t=t, enabled=enabled):
                    if not enabled:
                        ui.notify(_unsupported_type_message(t["name"]), color="warning")
                        return
                    messages.append({"role": "user", "text": f"Dùng {t['name']}", "time": _now_str()})
                    session["experiment_type"] = t["name"]
                    session["stage"] = "requirements"
                    await rerun()

                _mini_type_card(t, enabled, pick)

    async def render_requirements_stage():
        def _content():
            ui.label(
                f'Để chạy "{session["experiment_type"]}", cần các file sau — bấm nút đính kèm '
                "ở khung chat dưới đáy trang để upload (vừa được mở khoá):"
            ).classes("text-sm")

        _bot_bubble(_content)

        def body():
            _render_file_checklist()

            if session["experiment_type"] == "Huấn luyện mô hình":
                _render_train_config()
            elif session["experiment_type"] in ("Đánh giá mô hình", "Suy luận mô hình"):
                _render_eval_config()

            async def continue_next():
                if session["domain_box"].get("summarizing"):
                    ui.notify("File nghiệp vụ đang được tóm tắt — vui lòng chờ.", color="warning")
                    return
                missing = [
                    label
                    for kind, label, required in _current_requirements()
                    if required and not _has_kind(kind)
                ]
                if missing:
                    ui.notify(f"Còn thiếu: {', '.join(missing)}.", color="negative")
                    return
                if session["experiment_type"] == "Huấn luyện mô hình":
                    tc = session["train_config"]
                    task_type_internal = TASK_TYPE_LABELS[tc["task_type"]]
                    if task_type_internal in ("regression", "classification") and tc["target_col"] == NO_TARGET:
                        ui.notify("Cần chọn cột target cho Regression/Classification.", color="negative")
                        return
                messages.append({"role": "user", "text": "Đã upload xong, tiếp tục", "time": _now_str()})
                session["stage"] = "confirm"
                await rerun()

            async def change_type():
                # Đổi loại ở ĐÚNG bước này (chưa qua "Xác nhận") phải dọn sạch file đã chọn —
                # file đã upload có thể không hợp với loại MỚI (vd đổi từ EDA sang loại cần
                # model thay vì file dữ liệu thường), giữ lại sẽ gây hiểu nhầm đã có sẵn dữ liệu
                # đúng. Đây là cách "đổi loại" tường minh duy nhất sau khi loại đã chốt — không
                # còn nút "Đổi" nhanh ở thanh chat đáy trang nữa (xem `render_context_row`).
                session["files"].clear()
                refresh_data_list()
                session["domain_box"]["text"] = ""
                session["domain_box"]["name"] = None
                session["domain_box"]["_refresh"]()
                session["model_box"]["value"] = None
                session["model_box"]["fallback_value"] = None
                session["model_box"]["uploaded_name"] = None
                refresh_model_list()
                session["experiment_type"] = None
                session["train_config"] = {"task_type": "Tự động phát hiện", "target_col": NO_TARGET, "split_ratio": 0.8}
                session["eval_config"] = {"target_col": EVAL_TARGET_AUTO}
                messages.append({"role": "user", "text": "Đổi loại experiment khác", "time": _now_str()})
                session["stage"] = "manual_pick"
                await rerun()

            with ui.row().classes("mt-2 gap-2"):
                ui.button("Tiếp tục", icon="arrow_forward", on_click=continue_next, color="primary")
                ui.button("Đổi loại experiment", icon="swap_horiz", on_click=change_type).props(
                    "outline color=grey-7"
                )

        _wide_row(
            lambda: _wide_card("upload_file", "#854F0B", "File cần thiết", session["experiment_type"], body)
        )

    async def render_confirm_stage():
        _bot_bubble(lambda: ui.label("Xác nhận trước khi chạy:").classes("text-sm"))

        # Check "mơ hồ" rẻ (xét độ dài, không gọi LLM) trước — chỉ gọi thêm LLM (MODEL_LITE, rẻ)
        # kiểm tra NGỮ NGHĨA có liên quan đến phân tích dữ liệu/mô hình không khi câu đã đủ dài
        # (đỡ tốn 1 lượt gọi cho trường hợp đã chắc chắn mơ hồ qua check rẻ).
        description = session["description"]
        needs_clarify = _detect_ambiguity(description)
        if not needs_clarify:
            relevant = await nicegui_run.io_bound(_check_relevant, description, session["files"])
            needs_clarify = not relevant

        all_ok_box = {"value": True}
        q1_widget = None
        q2_widget = None
        supplement_input = None

        def chips():
            render_chip("database", session["problem_name"], "#EE0033")
            render_chip("bar_chart", session["experiment_type"], "#44494D")

        def body():
            nonlocal q1_widget, q2_widget, supplement_input
            all_ok_box["value"] = _render_file_checklist()

            ui.label("File dữ liệu:").classes("text-xs font-medium text-gray-600 mt-1")
            for name, df in session["files"].items():
                ui.label(f"{name} — {len(df):,} dòng × {len(df.columns)} cột").classes("text-sm text-gray-700")

            if session["experiment_type"] == "Huấn luyện mô hình":
                tc = session["train_config"]
                target_text = tc["target_col"] if tc["target_col"] != NO_TARGET else "(không có — Clustering)"
                ui.label("Cấu hình huấn luyện:").classes("text-xs font-medium text-gray-600 mt-2")
                ui.label(
                    f'{tc["task_type"]} · Cột target: {target_text} · '
                    f'Train/test: {tc["split_ratio"]:.0%}/{1 - tc["split_ratio"]:.0%} · Model: tự động chọn'
                ).classes("text-sm text-gray-700")
            elif session["experiment_type"] in ("Đánh giá mô hình", "Suy luận mô hình"):
                model_name = (
                    os.path.basename(session["model_box"]["value"]) if session["model_box"]["value"] else "(chưa chọn)"
                )
                ec = session["eval_config"]
                target_text = ec["target_col"] if ec["target_col"] != EVAL_TARGET_AUTO else "(tự động lấy từ model)"
                ui.label("Model & cấu hình:").classes("text-xs font-medium text-gray-600 mt-2")
                ui.label(f"Model: {model_name} · Cột target: {target_text}").classes("text-sm text-gray-700")

            ui.label("Yêu cầu phân tích:").classes("text-xs font-medium text-gray-600 mt-2")
            ui.label(session["description"] or "(không có — agent tự lập kế hoạch theo schema)").classes(
                "text-sm text-gray-700 italic"
            )

            # Chỉ hiện 1 trong 2: nếu yêu cầu mơ hồ HOẶC không liên quan thì hỏi 2 câu cụ thể
            # (q1/q2) làm luôn vai trò "bổ sung yêu cầu" — không hiện thêm ô tự do chung nữa
            # (trước đây hiện cả 2, bị dư/trùng ý nhau khi mô tả ban đầu để trống hoặc quá ngắn).
            if needs_clarify:
                with ui.column().classes("w-full gap-1 p-2 mt-2").style(
                    "background:#FFF8F0; border-left:3px solid #854F0B; border-radius:0 6px 6px 0;"
                ):
                    ui.label("Yêu cầu chưa rõ ràng — làm rõ thêm để kết quả tốt hơn").classes(
                        "text-xs font-medium"
                    ).style("color:#854F0B;")
                    q1_widget = ui.input("Bạn muốn tập trung vào cột nào? (để trống = phân tích tất cả)").classes(
                        "w-full mt-1"
                    )
                    q2_widget = ui.input(
                        "Muốn phân tích gì? (phân phối / tương quan / xu hướng thời gian / ...)"
                    ).classes("w-full")
            else:
                with ui.column().classes("w-full gap-1 p-2 mt-2").style(
                    "background:#F7F7F8; border:0.5px solid rgba(0,0,0,0.09); border-radius:8px;"
                ):
                    ui.label("Muốn bổ sung/làm rõ thêm yêu cầu gì không? (không bắt buộc)").classes(
                        "text-xs font-medium text-gray-600"
                    )
                    supplement_input = ui.textarea().props("outlined dense").classes("w-full")

            async def confirm():
                if not all_ok_box["value"]:
                    ui.notify("Còn thiếu file bắt buộc cho loại experiment này.", color="negative")
                    return
                if not (session["description"] or "").strip():
                    ui.notify(
                        "Bạn chưa nhập mô tả/yêu cầu phân tích nào — agent sẽ tự lập kế hoạch "
                        "theo schema dữ liệu (vẫn chạy được, chỉ là nhắc bạn).",
                        color="warning",
                    )
                extra = " ".join(
                    filter(
                        None,
                        [
                            (q1_widget.value or "").strip() if q1_widget else "",
                            (q2_widget.value or "").strip() if q2_widget else "",
                            (supplement_input.value or "").strip() if supplement_input else "",
                        ],
                    )
                )
                user_query = session["description"] or session["problem_name"]
                if extra:
                    user_query = f"{user_query} {extra}".strip()

                extra_config = {}
                if session["experiment_type"] == "Huấn luyện mô hình":
                    tc = session["train_config"]
                    task_type_internal = TASK_TYPE_LABELS[tc["task_type"]]
                    if task_type_internal:
                        extra_config["task_type"] = task_type_internal
                    if tc["target_col"] != NO_TARGET:
                        extra_config["target_col"] = tc["target_col"]
                    extra_config["split_ratio"] = tc["split_ratio"]
                    extra_config["optimize"] = False
                elif session["experiment_type"] in ("Đánh giá mô hình", "Suy luận mô hình"):
                    if session["model_box"]["value"]:
                        extra_config["model_path"] = session["model_box"]["value"]
                    ec = session["eval_config"]
                    if ec["target_col"] != EVAL_TARGET_AUTO:
                        extra_config["target_col"] = ec["target_col"]

                context = ExperimentContext(
                    problem_name=session["problem_name"],
                    problem_description=session["description"],
                    experiment_type=session["experiment_type"],
                    files=session["files"],
                    domain_context=session["domain_box"].get("text", ""),
                    domain_name=session["domain_box"].get("name") or "",
                    user_query=user_query,
                    extra=extra_config,
                )
                session["context"] = context
                messages.append({"role": "user", "text": "Xác nhận & Chạy", "time": _now_str()})
                session["stage"] = "running"
                await rerun()

            with ui.row().classes("mt-2"):
                ui.button("Xác nhận & Chạy", icon="play_arrow", on_click=confirm, color="primary")

        _wide_row(lambda: _wide_card("fact_check", "#EE0033", "Tóm tắt cấu hình", "Kiểm tra kỹ trước khi bắt đầu", body, chips))

    async def render_running_stage():
        session["locked"] = True
        context = session["context"]
        session["run_start"] = datetime.now()
        state.set_value("chat_running", True)
        try:
            timer = _agent_running_card(context.experiment_type)
            start_time = session["run_start"]
            agent = route(context.experiment_type, context)
            result = await nicegui_run.io_bound(lambda: asyncio.run(agent.run(context)))
            timer.cancel()

            if result.success and context.experiment_type == "Khám phá dữ liệu":
                try:
                    report_path = await nicegui_run.io_bound(
                        report_generator.generate,
                        dataset_info={
                            "files": list(context.files.keys()),
                            "problem_name": context.problem_name,
                            "experiment_type": context.experiment_type,
                        },
                        eda_results=result.data.get("results", {}),
                        ml_results=None,
                        execution_log=result.log,
                        charts=result.charts,
                    )
                    result.data["report_path"] = report_path
                except Exception as e:
                    result.log.append({"step": "report_generator", "status": "error", "error": str(e)})

            _save_run(
                context, result, start_time, source="chat", initial_description=session["description"]
            )
        finally:
            state.set_value("chat_running", False)

        duration = _format_duration((datetime.now() - session["run_start"]).total_seconds())
        messages.append(
            {
                "role": "bot",
                "kind": "wide",
                "render": lambda exp_type=context.experiment_type, dur=duration: (
                    _render_run_progress_card(exp_type, dur)
                ),
            }
        )
        session["result"] = result
        session["stage"] = "result"
        await rerun()

    async def _trigger_refine(feedback_text):
        context = session["context"]
        result = session["result"]
        prev_text = "\n\n".join(filter(None, [result.summary, result.insights]))
        combined_prev = (prev_text or "")[:MAX_FEEDBACK_CONTEXT_CHARS]
        context.user_query = (
            f"{context.user_query or ''}\n\n"
            f"--- Kết quả lần chạy trước ---\n{combined_prev}\n\n"
            f"--- Góp ý của người dùng cho lần chạy này ---\n{feedback_text}\n"
            "Hãy điều chỉnh phân tích theo góp ý này, đừng lặp lại y nguyên kết quả cũ."
        ).strip()
        session["stage"] = "running"
        await rerun()

    async def render_result_stage():
        context = session["context"]
        result = session["result"]
        kind = EXPERIMENT_TYPE_TO_KIND.get(context.experiment_type, "eda")
        duration = (
            _format_duration((datetime.now() - session["run_start"]).total_seconds())
            if session["run_start"]
            else "—"
        )

        def chips():
            ui.badge("Thành công" if result.success else "Lỗi", color="positive" if result.success else "negative").classes(
                "text-xs px-2"
            )
            render_chip("schedule", duration, "#5F5E5A")

        def body():
            render_result_body(result, kind, context)
            if result.success and context.experiment_type not in _EXPLANATION_ONLY_TYPES:
                ui.label('Muốn chạy lại theo hướng khác? Gõ góp ý vào khung chat dưới đáy trang.').classes(
                    "text-xs text-gray-400 mt-1"
                )
            with ui.row().classes("mt-2 gap-2"):
                ui.button("Xem lịch sử", icon="history", on_click=lambda: ui.navigate.to("/run-history")).props(
                    "outline color=grey-7"
                )
                ui.button("Về trang chủ", on_click=lambda: ui.navigate.to("/")).props("outline color=grey-7")

        icon, color = ("check_circle", "#2E7D32") if result.success else ("error", "#C62828")
        _wide_row(
            lambda: _wide_card(
                icon, color, "Kết quả phân tích", context.experiment_type, body, chips
            )
        )

    async def render_stage():
        stage = session["stage"]
        if stage == "intro":
            render_intro_stage()
        elif stage == "name":
            await render_name_stage()
        elif stage == "suggest":
            await render_suggest_stage()
        elif stage == "manual_pick":
            await render_manual_pick_stage()
        elif stage == "requirements":
            await render_requirements_stage()
        elif stage == "confirm":
            await render_confirm_stage()
        elif stage == "running":
            await render_running_stage()
        elif stage == "result":
            await render_result_stage()

    await rerun()
