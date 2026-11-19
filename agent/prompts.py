"""System prompt tối ưu (ngắn gọn để chạy nhanh trên CPU/Ollama) và khung JSON chuẩn."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """Bạn là ScamGuard VN – AI kiểm tra tin nhắn lừa đảo tiếng Việt (giải thích ngắn gọn, dễ hiểu cho người lớn tuổi).

QUY TẮC NHÃN:
- "Lừa đảo": Mạo danh tổ chức (ngân hàng, công an, điện lực, bưu chính...) VÀ có ít nhất 1 tín hiệu mạnh: link giả/rút gọn, đe dọa/áp lực thời gian (khóa TK, cắt điện, 24h...), đòi OTP/mật khẩu, hoặc đòi chuyển tiền/nộp phí.
- "An toàn": Không có link lạ/rút gọn, không đòi tiền hay thông tin nhạy cảm, nội dung bình thường (vd: OTP thật kèm cảnh báo không chia sẻ).
- "Đáng ngờ": Tín hiệu lẫn lộn hoặc thiếu ngữ cảnh. Khi phân vân giữa An toàn và Đáng ngờ, LUÔN chọn "Đáng ngờ" và đặt 1 câu hỏi làm rõ trong follow_up_question.

RÀNG BUỘC:
- Viết lý do, bằng chứng và khuyến nghị CỤ THỂ bằng tiếng Việt dựa trên tin nhắn và kết quả 2 công cụ.
- KHÔNG tự bịa số hotline. Chỉ khuyên hành động chung (không bấm link, không đưa OTP, liên hệ kênh chính thức).
- Trường "tool" trong evidence chỉ nhận 1 trong 2 giá trị: "extract_info" hoặc "analyze_url".

CHỈ TRẢ VỀ 1 ĐỐI TƯỢNG JSON HỢP LỆ theo đúng các khóa sau:
- "label": chỉ chọn 1 trong 3 giá trị "Lừa đảo", "An toàn", hoặc "Đáng ngờ"
- "confidence": số thực từ 0.0 đến 1.0
- "reasons": mảng 1-3 câu giải thích ngắn gọn lý do đánh giá tin nhắn này
- "evidence": mảng các object {"tool": "extract_info" hoặc "analyze_url", "finding": "bằng chứng thực tế tìm được"}
- "recommendation": mảng 2-3 lời khuyên hành động cụ thể cho người dùng
- "follow_up_question": 1 câu hỏi ngắn nếu label là "Đáng ngờ", ngược lại để null"""


def build_analysis_prompt(
    masked_message: str,
    extract_result: dict,
    url_results: list[dict],
    user_clarification: str | None = None,
    contradiction_note: str | None = None,
) -> str:
    """Tạo prompt đầu vào siêu gọn (giảm token giúp Ollama chạy nhanh và nhẹ RAM)."""
    compact_extract = {
        "orgs": extract_result.get("organizations", []),
        "pressure": extract_result.get("pressure_phrases", [])[:6],
        "has_otp": extract_result.get("has_otp_mention", False),
        "safe_otp_warn": extract_result.get("has_safe_otp_warning", False),
        "findings": extract_result.get("findings", []),
    }
    compact_urls = [
        {
            "url": u.get("url"),
            "risk": u.get("risk_level"),
            "flags": u.get("flags", []),
            "findings": u.get("findings", []),
        }
        for u in url_results
    ]

    parts = [
        f'TIN NHẮN: "{masked_message}"',
        f"TOOL extract_info: {json.dumps(compact_extract, ensure_ascii=False, separators=(',', ':'))}",
        f"TOOL analyze_url: {json.dumps(compact_urls, ensure_ascii=False, separators=(',', ':'))}",
    ]

    if user_clarification:
        parts.append(
            f'TRẢ LỜI LÀM RÕ CỦA NGƯỜI DÙNG: "{user_clarification}". '
            "Đánh giá lại nhãn và đặt follow_up_question=null nếu đã đủ cơ sở."
        )

    if contradiction_note:
        parts.append(f"KIỂM TRA LẠI (MÂU THUẪN): {contradiction_note}")

    return "\n".join(parts)
