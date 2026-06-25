"""Chọn loại experiment — 6 template + Full Pipeline."""

import streamlit as st

from components.experiment_card import render_card

TEMPLATES = [
    {"name": "Khám phá dữ liệu", "description": "Phân tích, EDA tự động — agent EDA làm kỹ nhất."},
    {"name": "Xử lý dữ liệu", "description": "Clean, encode, scale dữ liệu."},
    {"name": "Huấn luyện mô hình", "description": "Train baseline model, leaderboard."},
    {"name": "Đánh giá mô hình", "description": "Tính metrics, so sánh model."},
    {"name": "Suy luận mô hình", "description": "Predict trên dữ liệu mới."},
    # {"name": "Tùy chỉnh", "description": "Tự nhập yêu cầu phân tích, không có agent cố định."},
    # ^ tạm ẩn khỏi UI — không dùng data thực, 5 template + Full Pipeline đã cover đủ nhu cầu.
    {"name": "Full Pipeline", "description": "Chạy tuần tự EDA → Xử lý → Train → Đánh giá."},
]


def render():
    st.title("Chọn loại experiment")

    if st.session_state.current_problem_idx is None:
        st.warning("Vui lòng chọn hoặc tạo bài toán trước.")
        if st.button("Quay lại trang chủ"):
            st.session_state.page = "home"
            st.rerun()
        return

    problem = st.session_state.problems[st.session_state.current_problem_idx]
    st.caption(f"Bài toán: **{problem['name']}**")

    cols = st.columns(2)
    for idx, template in enumerate(TEMPLATES):
        with cols[idx % 2]:
            if render_card(template["name"], template["description"], key=f"template_{idx}"):
                st.session_state.current_experiment_type = template["name"]
                st.session_state.page = "experiment_config"
                st.rerun()

    if st.button("Quay lại"):
        st.session_state.page = "home"
        st.rerun()
