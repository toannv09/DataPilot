"""State layer thay cho st.session_state của bản Streamlit.

NiceGUI: `app.storage.user` persist qua cookie (sống sót khi chuyển trang/refresh) nhưng
CHỈ lưu được giá trị JSON-serializable. Object phức tạp (DataFrame, ExperimentContext,
AgentResult...) không serialize được — lưu trong registry in-memory ở server (_REGISTRY),
chỉ cất lại 1 key (str) trong app.storage.user để tra cứu lại sau khi chuyển trang.

Đánh đổi đã biết: _REGISTRY là dict toàn cục trong RAM, không tự dọn khi client đóng tab —
chấp nhận được cho prototype/đồ án, không phù hợp cho production nhiều user đồng thời lâu dài.
"""

import os
import uuid

from nicegui import app

_REGISTRY = {}

DEFAULTS = {
    "problems": [],
    "current_problem_idx": None,
    "current_experiment_type": None,
    "runs": [],
    "context_key": None,
    "agent_result_key": None,
    "pipeline_steps_key": None,
    "pipeline_stage_idx": 0,
    "pipeline_result_key": None,
    "pipeline_start_time": None,
    "report_path": None,
    "report_meta": None,
    "report_return_path": None,
    "report_breadcrumbs": None,
    "input_confirmed": False,
    "detection_key": None,
    "merge_decision": None,
    "chat_running": False,
}


def ensure_defaults():
    for key, value in DEFAULTS.items():
        if key not in app.storage.user:
            app.storage.user[key] = value


def get(key, default=None):
    return app.storage.user.get(key, default)


def set_value(key, value):
    app.storage.user[key] = value


def put_object(value):
    """Lưu object phức tạp (DataFrame, ExperimentContext, AgentResult...) vào registry
    in-memory, trả về key (str) — cất key này vào app.storage.user, không cất object thật."""
    key = str(uuid.uuid4())
    _REGISTRY[key] = value
    return key


def get_object(key, default=None):
    if key is None:
        return default
    return _REGISTRY.get(key, default)


def delete_run_record(run_id):
    """Xoá 1 run khỏi `runs` + xoá luôn file log tương ứng trên đĩa. Dùng chung bởi
    `run_history.py` (xoá từng run lẻ) và `home.py` (xoá cả bài toán -> xoá tất cả run thuộc
    bài toán đó) — tránh hai nơi tự ráp lại đường dẫn log riêng dễ lệch nhau."""
    runs = [r for r in get("runs", []) if r.get("run_id") != run_id]
    set_value("runs", runs)
    log_path = os.path.join(os.path.dirname(__file__), "..", "outputs", "logs", f"{run_id}.json")
    try:
        if os.path.exists(log_path):
            os.remove(log_path)
    except OSError:
        pass


def reset_pipeline_state():
    set_value("pipeline_steps_key", None)
    set_value("pipeline_stage_idx", 0)
    set_value("pipeline_result_key", None)
    set_value("pipeline_start_time", None)
    set_value("agent_result_key", None)
    set_value("detection_key", None)
    set_value("merge_decision", None)
    set_value("input_confirmed", False)
