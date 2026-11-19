"""Giao diện web 1 trang (Streamlit) cho ScamGuard VN – Bản demo."""

from __future__ import annotations

import streamlit as st

from agent.core import MAX_INPUT_LENGTH, ScamGuardAgent


def build_shareable_summary(result: dict) -> str:
    """Tạo đoạn tóm tắt ngắn gọn để người thân dễ sao chép, chuyển tiếp cho ông bà/cha mẹ."""
    reasons_text = "\n".join(f"- {r}" for r in result.get("reasons", []))
    rec_text = "\n".join(f"- {r}" for r in result.get("recommendation", []))
    return (
        f"[ScamGuard VN] Kết quả kiểm tra tin nhắn: {result['label'].upper()} "
        f"(Độ tự tin: {int(result['confidence'] * 100)}%)\n\n"
        f"Lý do:\n{reasons_text}\n\n"
        f"Khuyến nghị:\n{rec_text}"
    )


def render_result(output: dict) -> None:
    result = output["result"]
    label = result["label"]
    confidence_pct = int(result["confidence"] * 100)

    if label == "Lừa đảo":
        st.error(f"### Kết quả: LỪA ĐẢO (Độ tự tin: {confidence_pct}%)")
    elif label == "An toàn":
        st.success(f"###  Kết quả: AN TOÀN (Độ tự tin: {confidence_pct}%)")
    else:
        st.warning(f"###  Kết quả: ĐÁNG NGỜ (Độ tự tin: {confidence_pct}%)")

    if output.get("used_fallback"):
        st.info(
            "Chế độ dự phòng đang hoạt động (chưa kết nối được LLM API). "
            "Kết quả hiện dựa trên 2 công cụ phân tích tĩnh `extract_info` và `analyze_url`."
        )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Lý do")
        for reason in result.get("reasons", []):
            st.markdown(f"- {reason}")

        st.markdown("#### Khuyến nghị việc cần làm")
        for rec in result.get("recommendation", []):
            st.markdown(f"- {rec}")

    with col2:
        st.markdown("#### Bằng chứng từ công cụ")
        for ev in result.get("evidence", []):
            tool_name = ev.get("tool", "tool")
            finding = ev.get("finding", "")
            st.markdown(f"- **`{tool_name}`**: {finding}")

        with st.expander("📋 Tóm tắt dễ gửi lại cho người thân"):
            st.code(build_shareable_summary(result), language=None)

    with st.expander("🔍 Xem luồng xử lý của Agent (Trace) & JSON đầu ra"):
        st.markdown(f"**Số vòng suy luận:** `{output.get('rounds', 1)}`")
        st.markdown("**Tin nhắn đã che thông tin cá nhân (gửi cho AI):**")
        st.code(output.get("masked_message", ""), language=None)
        st.markdown("**Các bước thực thi:**")
        for step in output.get("trace", []):
            st.markdown(f"- {step}")
        st.markdown("**JSON đầu ra chuẩn:**")
        st.json(result)


def main() -> None:
    st.set_page_config(
        page_title="ScamGuard VN – Kiểm tra tin nhắn lừa đảo",
        page_icon="🛡️",
        layout="centered",
    )

    st.title("🛡️ ScamGuard VN – Trợ lý AI kiểm tra tin nhắn lừa đảo")
    st.caption(
        "Dán tin nhắn SMS, Zalo hoặc iMessage (có dấu hoặc không dấu) để kiểm tra nhanh. "
        "Hệ thống chỉ phân tích văn bản & chuỗi URL tĩnh, KHÔNG mở đường link và tự động che SĐT/STK trước khi gửi AI."
    )

    agent = ScamGuardAgent()

    if "message_input" not in st.session_state:
        st.session_state.message_input = ""
    if "last_output" not in st.session_state:
        st.session_state.last_output = None
    if "last_message" not in st.session_state:
        st.session_state.last_message = ""

    message = st.text_area(
        "Nội dung tin nhắn cần kiểm tra",
        key="message_input",
        height=140,
        placeholder="Dán nội dung tin nhắn SMS, Zalo, iMessage vào đây...",
    )
    st.caption(f"Độ dài hiện tại: {len(message.strip())} / {MAX_INPUT_LENGTH} ký tự")

    btn_col1, btn_col2 = st.columns([1, 4])
    check_clicked = btn_col1.button("🔎 Kiểm tra tin nhắn", type="primary", use_container_width=True)
    if btn_col2.button("🗑️ Xóa nội dung"):
        st.session_state.message_input = ""
        st.session_state.last_output = None
        st.session_state.last_message = ""
        st.rerun()

    if check_clicked:
        with st.spinner("Đang tách thông tin, phân tích URL và suy luận..."):
            output = agent.analyze(message)
        if "error" in output:
            st.error(output["error"])
            st.session_state.last_output = None
        else:
            st.session_state.last_output = output
            st.session_state.last_message = message

    if st.session_state.last_output:
        st.markdown("---")
        render_result(st.session_state.last_output)

        follow_up = st.session_state.last_output["result"].get("follow_up_question")
        if follow_up:
            st.markdown("---")
            st.info(f" **Agent hỏi thêm để làm rõ:** {follow_up}")
            with st.form("followup_form"):
                clarification = st.text_input(
                    "Câu trả lời của bạn:",
                    placeholder="Ví dụ: Tôi không đặt đơn hàng nào cả / Tôi không có tài khoản ở ngân hàng này...",
                )
                submitted = st.form_submit_button("Gửi câu trả lời để kiểm tra lại", type="primary")
                if submitted:
                    if not clarification.strip():
                        st.warning("Vui lòng nhập câu trả lời trước khi gửi.")
                    else:
                        with st.spinner("Đang phân tích lại với thông tin bổ sung..."):
                            updated_output = agent.analyze(
                                st.session_state.last_message,
                                user_clarification=clarification.strip(),
                            )
                        st.session_state.last_output = updated_output
                        st.rerun()


if __name__ == "__main__":
    main()
