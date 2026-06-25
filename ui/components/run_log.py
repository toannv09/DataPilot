"""Hiển thị execution log realtime dạng bảng."""

import pandas as pd
import streamlit as st


def render_log(log_entries):
    """log_entries: list[dict] — mỗi dict là 1 bước thực thi."""
    if not log_entries:
        return

    st.subheader("Nhật ký thực thi")
    st.dataframe(pd.DataFrame(log_entries), use_container_width=True)
