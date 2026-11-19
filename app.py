"""Giao diện web phong cách Claude.ai cho ScamGuard VN (có lịch sử phiên & 4 chế độ Chat/SMS/Zalo/Tra SĐT)."""

from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from agent.core import MAX_INPUT_LENGTH, ScamGuardAgent
from tools.extract_info import analyze_phone_number

CHANNEL_CONFIG = {
    "Chat": {
        "icon": "💬",
        "label": "Chat",
        "placeholder": "Dán đoạn tin nhắn chat / iMessage nghi ngờ vào đây...",
        "hero": "Tôi có thể kiểm tra gì cho bạn?",
    },
    "SMS": {
        "icon": "📱",
        "label": "SMS",
        "placeholder": "Dán nội dung tin nhắn SMS (ngân hàng, điện lực, giao hàng...) vào đây...",
        "hero": "Kiểm tra tin nhắn SMS cho bạn",
    },
    "Zalo": {
        "icon": "💠",
        "label": "Zalo",
        "placeholder": "Dán tin nhắn Zalo (mượn tiền, gửi link lạ, mời việc online...) vào đây...",
        "hero": "Kiểm tra tin nhắn Zalo cho bạn",
    },
    "Tra SĐT": {
        "icon": "📞",
        "label": "Tra SĐT",
        "placeholder": "Nhập số điện thoại nghi ngờ (vd: 0901234567, +84..., +1..., 1900...) kèm nội dung cuộc gọi nếu có...",
        "hero": "Tra cứu số điện thoại nghi ngờ",
    },
}

CLAUDE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');

/* Nền tổng thể chuẩn Claude */
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #FFFFFF !important;
    color: #1F1E1D !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* Ẩn header/toolbar/footer mặc định */
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"] {
    display: none !important;
    visibility: hidden !important;
}

/* Sidebar trái giống Claude.ai */
section[data-testid="stSidebar"] {
    background-color: #F5F4F0 !important;
    border-right: 1px solid #EAE8E1 !important;
    min-width: 260px !important;
    max-width: 280px !important;
}
section[data-testid="stSidebar"] > div {
    padding-top: 1.1rem !important;
}

.sg-brand {
    font-family: 'Newsreader', Georgia, serif !important;
    font-size: 1.55rem;
    font-weight: 500;
    color: #1F1E1D;
    letter-spacing: -0.02em;
    margin-bottom: 0.9rem;
    padding-left: 4px;
}

.sg-sidebar-heading {
    font-size: 0.78rem;
    font-weight: 600;
    color: #7A7870;
    margin: 1rem 0 0.45rem 4px;
    letter-spacing: 0.01em;
}

/* Nút trong Sidebar */
section[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #2B2A27 !important;
    border: none !important;
    border-radius: 10px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 0.87rem !important;
    font-weight: 400 !important;
    padding: 0.45rem 0.7rem !important;
    box-shadow: none !important;
    transition: background-color 0.12s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #EAE8E1 !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #E6E4DC !important;
    font-weight: 500 !important;
    color: #1F1E1D !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #DCD9CF !important;
}

/* Ô tìm kiếm trong sidebar: bỏ viền đỏ focus */
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="base-input"] {
    background: #FFFFFF !important;
    border: 1px solid #E3E1D9 !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
section[data-testid="stSidebar"] [data-baseweb="input"]:focus-within {
    border-color: #C7C4B9 !important;
    box-shadow: none !important;
}

/* Vùng nội dung chính căn giữa */
.block-container {
    max-width: 760px !important;
    padding-top: 2rem !important;
    padding-bottom: 4rem !important;
}

/* Top pill giống "Free plan · Upgrade" */
.sg-top-pill-wrap {
    display: flex;
    justify-content: center;
    margin-bottom: 4.5rem;
}
.sg-top-pill-wrap.compact {
    margin-bottom: 1.5rem;
}
.sg-top-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #F4F3EE;
    color: #6B6A64;
    font-size: 0.8rem;
    font-weight: 500;
    padding: 5px 14px;
    border-radius: 999px;
    border: 1px solid #EAE8E0;
}
.sg-top-pill .accent {
    color: #2563EB;
    font-weight: 500;
}

/* Tiêu đề chào serif lớn */
.sg-hero {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    margin-bottom: 1.8rem;
    text-align: center;
}
.sg-hero-title {
    font-family: 'Newsreader', Georgia, 'Times New Roman', serif !important;
    font-size: 2.45rem;
    font-weight: 400;
    color: #2B2A27;
    letter-spacing: -0.02em;
    line-height: 1.2;
    margin: 0;
}

/* Hộp nhập liệu trắng nổi bo tròn chuẩn Claude */
div[data-testid="stForm"] {
    background: #FFFFFF !important;
    border: 1px solid #E2E0D8 !important;
    border-radius: 20px !important;
    padding: 14px 18px 12px 18px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05) !important;
}

/* XÓA TRIỆT ĐỂ viền đỏ focus và dòng "Press Ctrl+Enter to submit form" */
div[data-testid="stForm"] [data-baseweb="textarea"],
div[data-testid="stForm"] [data-baseweb="textarea"]:focus-within,
div[data-testid="stForm"] [data-baseweb="base-input"],
div[data-testid="stForm"] [data-baseweb="base-input"]:focus-within,
div[data-testid="stForm"] textarea,
div[data-testid="stForm"] textarea:focus,
div[data-testid="stForm"] textarea:active {
    background: transparent !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
div[data-testid="stForm"] textarea {
    color: #1F1E1D !important;
    font-size: 0.98rem !important;
    line-height: 1.55 !important;
    padding: 2px 0 !important;
    resize: none !important;
}
div[data-testid="stForm"] textarea::placeholder {
    color: #9A9890 !important;
}
[data-testid="InputInstructions"] {
    display: none !important;
}

/* Chân hộp nhập liệu */
.sg-input-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #8A8880;
    font-size: 0.8rem;
    padding-top: 8px;
}
.sg-mode-chip {
    background: #F4F3EE;
    color: #3D3C38;
    border: 1px solid #E6E4DC;
    border-radius: 8px;
    padding: 3px 10px;
    font-size: 0.78rem;
    font-weight: 500;
}

/* Nút gửi màu cam đất */
div[data-testid="stFormSubmitButton"] button {
    background-color: #D97757 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    padding: 0.42rem 1rem !important;
}
div[data-testid="stFormSubmitButton"] button:hover {
    background-color: #C46343 !important;
}

/* Hàng nút chọn kênh (Chat / SMS / Zalo / Tra SĐT) giống hàng pill Claude */
.stMain .stButton > button {
    background: #FFFFFF !important;
    color: #4A4944 !important;
    border: 1px solid #E5E3DC !important;
    border-radius: 10px !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    padding: 0.38rem 0.75rem !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}
.stMain .stButton > button:hover {
    background: #F5F4F0 !important;
    border-color: #D5D2C8 !important;
}
.stMain .stButton > button[kind="primary"] {
    background: #F4F3EE !important;
    color: #1F1E1D !important;
    border: 1px solid #D97757 !important;
    font-weight: 600 !important;
}

/* Bong bóng tin nhắn người dùng */
.sg-user-bubble {
    background: #F4F3EE;
    border: 1px solid #E8E6DF;
    border-radius: 16px;
    padding: 14px 18px;
    margin: 0.6rem 0 1.2rem 0;
    color: #1F1E1D;
    font-size: 0.95rem;
    line-height: 1.6;
}
.sg-user-label {
    font-size: 0.74rem;
    font-weight: 600;
    color: #8A8880;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
}

/* Thẻ kết quả phân tích */
.sg-result-card {
    background: #FFFFFF;
    border: 1px solid #E5E3DC;
    border-radius: 18px;
    padding: 20px 24px;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.04);
    margin-bottom: 1rem;
}
.sg-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 14px;
}
.sg-badge.scam { background: #FDECEC; color: #B42318; border: 1px solid #F9C6C6; }
.sg-badge.safe { background: #ECFDF3; color: #067647; border: 1px solid #ABEFC6; }
.sg-badge.suspicious { background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }

.sg-section-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: #73726C;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 14px 0 6px 0;
}
.sg-list {
    margin: 0;
    padding-left: 1.2rem;
    color: #2B2A27;
    font-size: 0.94rem;
    line-height: 1.65;
}
.sg-list li { margin-bottom: 4px; }
.sg-tool-tag {
    display: inline-block;
    background: #F4F3EE;
    color: #5C5B56;
    border: 1px solid #E5E3DC;
    border-radius: 6px;
    padding: 1px 7px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.76rem;
    margin-right: 6px;
}
.sg-followup-box {
    background: #FFF9F5;
    border: 1px solid #F2D3C4;
    border-radius: 14px;
    padding: 14px 18px;
    margin: 0.8rem 0;
    color: #3D2B24;
    font-size: 0.94rem;
}
div[data-testid="stExpander"] {
    background: #FAF9F5 !important;
    border: 1px solid #E8E6DF !important;
    border-radius: 12px !important;
    margin-top: 0.5rem !important;
}
</style>
"""

SPARK_SVG = (
    '<svg width="34" height="34" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<g stroke="#D97757" stroke-width="2.6" stroke-linecap="round">'
    '<line x1="18" y1="3" x2="18" y2="12"/><line x1="18" y1="24" x2="18" y2="33"/>'
    '<line x1="3" y1="18" x2="12" y2="18"/><line x1="24" y1="18" x2="33" y2="18"/>'
    '<line x1="7.4" y1="7.4" x2="13.8" y2="13.8"/><line x1="22.2" y1="22.2" x2="28.6" y2="28.6"/>'
    '<line x1="28.6" y1="7.4" x2="22.2" y2="13.8"/><line x1="13.8" y1="22.2" x2="7.4" y2="28.6"/>'
    "</g></svg>"
)


def build_shareable_summary(result: dict) -> str:
    reasons_text = "\n".join(f"- {r}" for r in result.get("reasons", []))
    rec_text = "\n".join(f"- {r}" for r in result.get("recommendation", []))
    return (
        f"[ScamGuard VN] Kết quả kiểm tra: {result['label'].upper()} "
        f"(Độ tự tin: {int(result['confidence'] * 100)}%)\n\n"
        f"Lý do:\n{reasons_text}\n\n"
        f"Khuyến nghị:\n{rec_text}"
    )


def run_check(agent: ScamGuardAgent, channel: str, raw_text: str, clarification: str | None = None) -> dict:
    """Chạy kiểm tra tin nhắn hoặc tra cứu SĐT theo kênh đã chọn."""
    text = raw_text.strip()
    if channel == "Tra SĐT":
        phone_info = analyze_phone_number(text)
        enriched_input = (
            f"[Kênh: Tra cứu số điện thoại] {text}\n"
            f"(Phân tích đầu số sơ bộ: {'; '.join(phone_info['findings'])})"
        )
        output = agent.analyze(enriched_input, user_clarification=clarification)
        if "error" not in output:
            # Bổ sung trực tiếp bằng chứng phân tích đầu số vào evidence
            phone_evidence = [
                {"tool": "analyze_phone", "finding": f} for f in phone_info["findings"]
            ]
            output["result"]["evidence"] = phone_evidence + output["result"].get("evidence", [])
        return output

    prefixed = f"[Kênh: {channel}] {text}" if channel != "Chat" else text
    return agent.analyze(prefixed, user_clarification=clarification)


def render_result(channel: str, message: str, output: dict) -> None:
    result = output["result"]
    label = result["label"]
    confidence_pct = int(result["confidence"] * 100)

    if label == "Lừa đảo":
        badge_cls, badge_text = "scam", f"Lừa đảo · Độ tự tin {confidence_pct}%"
    elif label == "An toàn":
        badge_cls, badge_text = "safe", f"An toàn · Độ tự tin {confidence_pct}%"
    else:
        badge_cls, badge_text = "suspicious", f"Đáng ngờ · Độ tự tin {confidence_pct}%"

    safe_msg = html.escape(message).replace("\n", "<br>")
    st.markdown(
        f'<div class="sg-user-bubble"><div class="sg-user-label">{html.escape(channel)} · Nội dung bạn gửi</div>{safe_msg}</div>',
        unsafe_allow_html=True,
    )

    reasons_html = "".join(f"<li>{html.escape(str(r))}</li>" for r in result.get("reasons", []))
    evidence_html = "".join(
        f'<li><span class="sg-tool-tag">{html.escape(str(ev.get("tool", "tool")))}</span>'
        f'{html.escape(str(ev.get("finding", "")))}</li>'
        for ev in result.get("evidence", [])
    )
    recs_html = "".join(f"<li>{html.escape(str(r))}</li>" for r in result.get("recommendation", []))

    fallback_banner = ""
    if output.get("used_fallback"):
        fallback_banner = (
            '<div style="background:#F4F3EE;border-radius:10px;padding:10px 14px;'
            'font-size:0.85rem;color:#5C5B56;margin-bottom:12px;">'
            "Chế độ dự phòng đang hoạt động (chưa kết nối được LLM). "
            "Kết quả hiện dựa trên các công cụ phân tích tĩnh.</div>"
        )

    card_html = (
        '<div class="sg-result-card">'
        f'<div class="sg-badge {badge_cls}">{badge_text}</div>'
        f"{fallback_banner}"
        '<div class="sg-section-title">Lý do</div>'
        f'<ul class="sg-list">{reasons_html}</ul>'
        '<div class="sg-section-title">Bằng chứng từ công cụ</div>'
        f'<ul class="sg-list">{evidence_html}</ul>'
        '<div class="sg-section-title">Khuyến nghị việc cần làm</div>'
        f'<ul class="sg-list">{recs_html}</ul>'
        "</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)

    with st.expander("Tóm tắt dễ gửi lại cho người thân"):
        st.code(build_shareable_summary(result), language=None)

    with st.expander("Xem luồng xử lý của Agent (Trace) & JSON đầu ra"):
        st.markdown(f"**Số vòng suy luận:** `{output.get('rounds', 1)}`")
        st.markdown("**Nội dung đã che thông tin cá nhân (gửi cho AI):**")
        st.code(output.get("masked_message", ""), language=None)
        st.markdown("**Các bước thực thi:**")
        for step in output.get("trace", []):
            st.markdown(f"- {step}")
        st.markdown("**JSON đầu ra chuẩn:**")
        st.json(result)


def main() -> None:
    st.set_page_config(
        page_title="ScamGuard VN",
        page_icon="🛡️",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    st.markdown(CLAUDE_CSS, unsafe_allow_html=True)

    agent = ScamGuardAgent()

    if "channel" not in st.session_state:
        st.session_state.channel = "Chat"
    if "history" not in st.session_state:
        st.session_state.history = []  # Lưu lịch sử trong phiên hiện tại
    if "active_idx" not in st.session_state:
        st.session_state.active_idx = None

    # --- SIDEBAR TRÁI KIỂU CLAUDE (LỊCH SỬ) ---
    with st.sidebar:
        st.markdown('<div class="sg-brand">ScamGuard</div>', unsafe_allow_html=True)

        if st.button("＋  Kiểm tra mới", type="primary", use_container_width=True):
            st.session_state.active_idx = None
            st.rerun()

        search_q = st.text_input(
            "Tìm kiếm",
            placeholder="🔍 Tìm trong lịch sử...",
            label_visibility="collapsed",
        )

        st.markdown('<div class="sg-sidebar-heading">Lịch sử kiểm tra</div>', unsafe_allow_html=True)

        if not st.session_state.history:
            st.caption("Chưa có lượt kiểm tra nào trong phiên này.")
        else:
            q = search_q.strip().lower()
            for idx in range(len(st.session_state.history) - 1, -1, -1):
                entry = st.session_state.history[idx]
                preview = entry["message"].replace("\n", " ")
                if q and q not in preview.lower() and q not in entry["channel"].lower():
                    continue
                label = entry["output"]["result"]["label"]
                dot = "🔴" if label == "Lừa đảo" else ("🟢" if label == "An toàn" else "🟡")
                short_text = (preview[:28] + "...") if len(preview) > 28 else preview
                btn_label = f"{dot} [{entry['channel']}] {short_text}"
                if st.button(btn_label, key=f"hist_{idx}", use_container_width=True):
                    st.session_state.active_idx = idx
                    st.rerun()

    # --- NỘI DUNG CHÍNH ---
    active_entry = (
        st.session_state.history[st.session_state.active_idx]
        if st.session_state.active_idx is not None
        and 0 <= st.session_state.active_idx < len(st.session_state.history)
        else None
    )

    pill_cls = "sg-top-pill-wrap compact" if active_entry else "sg-top-pill-wrap"
    st.markdown(
        f'<div class="{pill_cls}"><div class="sg-top-pill"><span>ScamGuard VN</span><span>·</span>'
        f'<span class="accent">{html.escape(agent.provider.capitalize())} · {html.escape(agent.model)}</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    if active_entry is None:
        cfg = CHANNEL_CONFIG[st.session_state.channel]
        st.markdown(
            f'<div class="sg-hero">{SPARK_SVG}<h1 class="sg-hero-title">{html.escape(cfg["hero"])}</h1></div>',
            unsafe_allow_html=True,
        )

        with st.form("check_form", clear_on_submit=False):
            message = st.text_area(
                "Nội dung cần kiểm tra",
                height=110,
                label_visibility="collapsed",
                placeholder=cfg["placeholder"],
            )
            meta_col, btn_col = st.columns([3, 1])
            with meta_col:
                st.markdown(
                    f'<div class="sg-input-meta"><span class="sg-mode-chip">{cfg["icon"]} {cfg["label"]}</span>'
                    f"<span>Tối đa {MAX_INPUT_LENGTH} ký tự · Không mở link thật</span></div>",
                    unsafe_allow_html=True,
                )
            with btn_col:
                submitted = st.form_submit_button("Kiểm tra", use_container_width=True)

        # Hàng 4 nút chọn kênh (Chat / SMS / Zalo / Tra SĐT) ngay dưới ô nhập giống Claude
        ch_cols = st.columns(4)
        for col, (ch_key, ch_info) in zip(ch_cols, CHANNEL_CONFIG.items()):
            is_selected = st.session_state.channel == ch_key
            if col.button(
                f"{ch_info['icon']} {ch_info['label']}",
                key=f"ch_{ch_key}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            ):
                st.session_state.channel = ch_key
                st.rerun()

        if submitted:
            with st.spinner("Đang phân tích..."):
                output = run_check(agent, st.session_state.channel, message)
            if "error" in output:
                st.error(output["error"])
            else:
                st.session_state.history.append(
                    {
                        "channel": st.session_state.channel,
                        "message": message.strip(),
                        "output": output,
                        "time": datetime.now().strftime("%H:%M"),
                    }
                )
                st.session_state.active_idx = len(st.session_state.history) - 1
                st.rerun()
    else:
        render_result(active_entry["channel"], active_entry["message"], active_entry["output"])

        follow_up = active_entry["output"]["result"].get("follow_up_question")
        if follow_up:
            st.markdown(
                f'<div class="sg-followup-box"><strong>Agent hỏi thêm để làm rõ:</strong> '
                f"{html.escape(follow_up)}</div>",
                unsafe_allow_html=True,
            )
            with st.form("followup_form", clear_on_submit=True):
                clarification = st.text_area(
                    "Câu trả lời của bạn",
                    height=80,
                    label_visibility="collapsed",
                    placeholder="Nhập câu trả lời của bạn (vd: Tôi không đặt đơn hàng nào cả)...",
                )
                _, send_col = st.columns([3, 1])
                with send_col:
                    sent = st.form_submit_button("Gửi trả lời", use_container_width=True)
            if sent:
                if not clarification.strip():
                    st.warning("Vui lòng nhập câu trả lời trước khi gửi.")
                else:
                    with st.spinner("Đang đánh giá lại với câu trả lời của bạn..."):
                        updated = run_check(
                            agent,
                            active_entry["channel"],
                            active_entry["message"],
                            clarification=clarification.strip(),
                        )
                    st.session_state.history[st.session_state.active_idx]["output"] = updated
                    st.rerun()


if __name__ == "__main__":
    main()
