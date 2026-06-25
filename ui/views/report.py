"""Xem và download báo cáo PDF/HTML."""

import os

import streamlit as st


def render():
    st.title("Báo cáo")

    report_path = st.session_state.report_path
    if not report_path or not os.path.exists(report_path):
        st.info("Chưa có báo cáo nào được sinh.")
        if st.button("Quay lại"):
            st.session_state.page = "run_experiment"
            st.rerun()
        return

    with open(report_path, "rb") as f:
        data = f.read()

    if report_path.endswith(".html"):
        st.download_button("Tải báo cáo HTML", data, file_name=os.path.basename(report_path), mime="text/html")
        st.components.v1.html(data.decode("utf-8"), height=800, scrolling=True)
    elif report_path.endswith(".pdf"):
        st.download_button("Tải báo cáo PDF", data, file_name=os.path.basename(report_path), mime="application/pdf")

    if st.button("Quay lại"):
        st.session_state.page = "run_experiment"
        st.rerun()
