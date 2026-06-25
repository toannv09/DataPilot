"""Lịch sử các lần chạy + log chi tiết."""

import streamlit as st

from mlops.logger import ExecutionLogger


def render():
    st.title("Lịch sử chạy")

    if not st.session_state.runs:
        st.info("Chưa có lần chạy nào.")
    else:
        for run in reversed(st.session_state.runs):
            with st.expander(f"{run['run_id']} — {run['experiment_type']} — {run['status']}"):
                st.write(f"Bài toán: {run['problem']}")
                st.write(f"Tóm tắt: {run['summary']}")

                log_entries = ExecutionLogger.load(run["run_id"])
                if log_entries:
                    st.dataframe(log_entries, use_container_width=True)

    if st.button("Quay lại"):
        st.session_state.page = "run_experiment"
        st.rerun()
