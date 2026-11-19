# ScamGuard VN – AI Agent Kiểm tra Tin nhắn Lừa đảo (Bản Demo)

Trợ lý AI Agent giúp người dùng Việt Nam kiểm tra tin nhắn nghi ngờ lừa đảo (SMS, Zalo, iMessage – có dấu hoặc không dấu) theo luồng:
`Nhận đầu vào → Tách thông tin (extract_info) → Phân tích URL tĩnh (analyze_url) → Che PII → Suy luận LLM (tối đa 2 vòng) → Hỏi lại nếu Đáng ngờ → Trả kết quả JSON`.

## Chạy nhanh trong 3 lệnh

```bash
# 1. Cài đặt thư viện
pip install -r requirements.txt

# 2. Tạo file cấu hình biến môi trường (sau đó điền LLM_API_KEY vào file .env)
copy .env.example .env

# 3. Khởi chạy giao diện demo
streamlit run app.py
```

*(Lưu ý: Nếu chưa điền `LLM_API_KEY`, hệ thống vẫn chạy được ở chế độ dự phòng bằng 2 công cụ phân tích tĩnh và gắn nhãn `Đáng ngờ`.)*

## Chạy kiểm thử & Demo dòng lệnh

- **Chạy Unit Test cho 2 công cụ & cơ chế an toàn:**
  ```bash
  pytest -v
  ```
- **Chạy nhanh 3 tình huống demo từ dòng lệnh (CLI):**
  ```bash
  python -m agent.core
  ```
- **Chạy đánh giá toàn bộ 20 kịch bản kiểm thử (xuất CSV + Confusion Matrix/Precision/Recall):**
  ```bash
  python scripts/evaluate_scenarios.py
  ```

## Cấu trúc thư mục

- `app.py` – Giao diện web 1 trang (Streamlit) có nút chọn nhanh 3 tình huống demo và bước hỏi lại.
- `agent/core.py` – Lõi Agent: vòng lặp quan sát/suy luận, kiểm tra mâu thuẫn (tối đa 2 vòng), retry & fallback.
- `agent/prompts.py` – System prompt, quy tắc ra nhãn và định dạng JSON đầu ra.
- `tools/extract_info.py` – Công cụ 1: tách URL, SĐT, STK, tổ chức bị mạo danh, cụm từ áp lực và che PII (`mask_pii`).
- `tools/analyze_url.py` – Công cụ 2: phân tích chuỗi URL tĩnh (giả thương hiệu, link rút gọn, đuôi lạ, Punycode/IP) – không mở link thật.
- `data/test_messages.json` – 3 tình huống demo + 17 kịch bản kiểm thử (tổng 20 kịch bản mẫu đã che thông tin cá nhân).
- `tests/test_tools.py` – Bộ unit test cho 2 công cụ và fallback của Agent.
- `IMPLEMENTATION_PLAN.md` – Tài liệu kế hoạch triển khai, workflow và roadmap chi tiết.
