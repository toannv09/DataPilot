"""Tạo bài toán mới — form tên + mô tả."""

import streamlit as st


def render():
    st.title("Tạo bài toán mới")

    with st.form("create_problem_form"):
        name = st.text_input("Tên bài toán")
        description = st.text_area("Mô tả bài toán")
        submitted = st.form_submit_button("Tạo")

    if submitted:
        if not name:
            st.error("Vui lòng nhập tên bài toán.")
        else:
            st.session_state.problems.append({"name": name, "description": description})
            st.session_state.current_problem_idx = len(st.session_state.problems) - 1
            st.session_state.page = "select_experiment"
            st.rerun()

    if st.button("Quay lại"):
        st.session_state.page = "home"
        st.rerun()
