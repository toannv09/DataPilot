"""Trang chủ — danh sách bài toán đã tạo."""

import streamlit as st

from components.experiment_card import render_card


def render():
    st.title("AutoEDA — Trang chủ")

    col1, col2 = st.columns(2)
    col1.metric("Số bài toán", len(st.session_state.problems))
    col2.metric("Số lần chạy", len(st.session_state.runs))

    if st.button("Tạo bài toán mới"):
        st.session_state.page = "create_problem"
        st.rerun()

    st.subheader("Danh sách bài toán")

    if not st.session_state.problems:
        st.info("Chưa có bài toán nào. Hãy tạo bài toán mới.")
        return

    for idx, problem in enumerate(st.session_state.problems):
        if render_card(problem["name"], problem["description"], key=f"problem_{idx}"):
            st.session_state.current_problem_idx = idx
            st.session_state.page = "select_experiment"
            st.rerun()
