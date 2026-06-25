"""Chat interface tiếng Việt — hiển thị insight và nhận câu hỏi từ user."""

import streamlit as st


def render_message(content, role="assistant"):
    """Hiển thị 1 tin nhắn trong chat."""
    with st.chat_message(role):
        st.markdown(content)


def render_history(messages):
    """Hiển thị toàn bộ lịch sử chat. messages: list[{"role":..., "content":...}]."""
    for msg in messages:
        render_message(msg["content"], msg.get("role", "assistant"))


def render_input(placeholder="Nhập câu hỏi của bạn..."):
    """Trả về nội dung user nhập, hoặc None nếu chưa nhập."""
    return st.chat_input(placeholder)
