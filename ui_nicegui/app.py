"""Entry point NiceGUI — thay ui/app.py (Streamlit). Theme màu Viettel + đăng ký các trang."""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)  # cho agents/tools/llm/mlops
sys.path.insert(0, THIS_DIR)  # cho state/views/components trong ui_nicegui/

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from nicegui import ui  # noqa: E402

# Import các trang để đăng ký @ui.page route (import có side-effect, không xóa import này).
# Theme màu (ui.colors) được gọi RIÊNG trong từng page function (theme.apply()), không gọi
# ở đây — nicegui cấm UI element ở global scope khi dùng nhiều @ui.page.
from views import (  # noqa: E402,F401
    chat_experiment,
    create_problem,
    experiment_config,
    home,
    report,
    run_experiment,
    run_history,
    select_experiment,
)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="DataPilot",
        host="0.0.0.0",
        port=8502,
        reload=False,
        storage_secret=os.environ.get("NICEGUI_STORAGE_SECRET", "datapilot-dev-secret-change-me"),
    )
