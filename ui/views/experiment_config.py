"""Cấu hình experiment — upload file, file nghiệp vụ, mô tả/câu hỏi."""

import json
import os

import streamlit as st

from agents.base_agent import ExperimentContext
from components.file_uploader import render_data_uploader, render_domain_uploader, render_test_uploader
from tools.ml.model_selector import MODEL_REGISTRY

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "outputs", "models")

TASK_TYPE_LABELS = {
    "Tự động phát hiện": None,
    "Regression": "regression",
    "Classification": "classification",
    "Clustering": "clustering",
}

NO_TARGET = "(Không có — Clustering)"


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


def render():
    st.title("Cấu hình experiment")

    if st.session_state.current_problem_idx is None or not st.session_state.current_experiment_type:
        st.warning("Vui lòng chọn bài toán và loại experiment trước.")
        if st.button("Quay lại"):
            st.session_state.page = "select_experiment"
            st.rerun()
        return

    problem = st.session_state.problems[st.session_state.current_problem_idx]
    experiment_type = st.session_state.current_experiment_type
    st.caption(f"Bài toán: **{problem['name']}** — Experiment: **{experiment_type}**")

    files = render_data_uploader()
    domain_context = render_domain_uploader()
    user_query = st.text_area("Mô tả yêu cầu / câu hỏi")

    extra = {}
    config_valid = True
    test_df = None

    if experiment_type == "Full Pipeline":
        st.subheader("Dữ liệu đánh giá")
        test_df = render_test_uploader()

    if experiment_type in ("Đánh giá mô hình", "Suy luận mô hình"):
        models = []
        if os.path.isdir(MODEL_DIR):
            models = [f for f in os.listdir(MODEL_DIR) if f.endswith(".pkl")]
        model_file = st.selectbox("Chọn model có sẵn", models) if models else None

        uploaded_model = st.file_uploader("Hoặc upload model (.pkl)", type=["pkl"])
        if uploaded_model is not None:
            os.makedirs(MODEL_DIR, exist_ok=True)
            model_path = os.path.join(MODEL_DIR, uploaded_model.name)
            with open(model_path, "wb") as f:
                f.write(uploaded_model.getbuffer())
            extra["model_path"] = model_path
        elif model_file:
            extra["model_path"] = os.path.join(MODEL_DIR, model_file)

        target_choices = [NO_TARGET] + _column_options(files)
        target_col = st.selectbox("Cột target (nếu có trong file vừa upload)", target_choices)
        target_col_manual = st.text_input(
            "Hoặc nhập tên cột target thủ công",
            value="",
            help=(
                "Dùng khi file dữ liệu (đặc biệt với Suy luận mô hình) không có cột target — "
                "đó là điều cần dự đoán nên thường không có sẵn. Nếu để trống, hệ thống sẽ tự "
                "lấy tên target đã lưu trong model lúc huấn luyện."
            ),
        )
        if target_col_manual.strip():
            extra["target_col"] = target_col_manual.strip()
        elif target_col != NO_TARGET:
            extra["target_col"] = target_col

    if experiment_type in ("Huấn luyện mô hình", "Full Pipeline"):
        st.subheader("Cấu hình huấn luyện")

        task_type_label = st.selectbox("Loại bài toán", list(TASK_TYPE_LABELS.keys()))
        task_type = TASK_TYPE_LABELS[task_type_label]
        if task_type:
            extra["task_type"] = task_type

        target_choices = [NO_TARGET] + _column_options(files)
        target_col = st.selectbox("Cột target (bắt buộc với Regression/Classification)", target_choices)
        if target_col != NO_TARGET:
            extra["target_col"] = target_col
        elif task_type in ("regression", "classification"):
            st.warning("Cần chọn cột target cho Regression/Classification.")

        split_ratio = st.slider("Tỷ lệ train/test", 0.5, 0.95, 0.8, 0.05)
        extra["split_ratio"] = split_ratio

        if task_type:
            model_choices = ["Tự động chọn"] + list(MODEL_REGISTRY[task_type].keys())
            selected_model_label = st.selectbox("Model", model_choices)
        else:
            selected_model_label = "Tự động chọn"
            st.caption("Chọn loại bài toán cụ thể để chọn model thủ công.")

        if selected_model_label != "Tự động chọn":
            extra["selected_model"] = selected_model_label

            params_text = st.text_area("Tham số tùy chỉnh cho model (JSON, optional)", value="")
            if params_text.strip():
                try:
                    extra["model_params"] = json.loads(params_text)
                except json.JSONDecodeError as e:
                    st.error(f"Tham số JSON không hợp lệ: {e}")
                    config_valid = False

        extra["optimize"] = st.checkbox("Optimize tham số (RandomizedSearch)", value=False)

    if test_df is not None:
        extra["test_df"] = test_df

    if st.button("Bắt đầu"):
        if not files:
            st.error("Vui lòng upload ít nhất 1 file dữ liệu.")
        elif not config_valid:
            st.error("Vui lòng sửa lỗi cấu hình trước khi bắt đầu.")
        else:
            st.session_state.files = files
            st.session_state.domain_context = domain_context
            st.session_state.user_query = user_query
            st.session_state.context = ExperimentContext(
                problem_name=problem["name"],
                problem_description=problem["description"],
                experiment_type=experiment_type,
                files=files,
                domain_context=domain_context,
                user_query=user_query,
                extra=extra,
            )
            st.session_state.detection = None
            st.session_state.merge_decision = None
            st.session_state.agent_result = None
            st.session_state.pipeline_steps = {}
            st.session_state.pipeline_stage_idx = 0
            st.session_state.pipeline_result = None
            st.session_state.page = "run_experiment"
            st.rerun()

    if st.button("Quay lại"):
        st.session_state.page = "select_experiment"
        st.rerun()
