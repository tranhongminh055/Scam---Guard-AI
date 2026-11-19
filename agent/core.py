"""Lõi Agent (agent/core.py) cho ScamGuard VN.

Thực hiện đầy đủ 8 bước trong workflow:
1. Validate đầu vào (rỗng / > 1.500 ký tự)
2. Gọi Công cụ 1 (extract_info)
3. Gọi Công cụ 2 (analyze_url)
4. Che PII và gọi LLM API (tự động retry 1 lần nếu lỗi/sai JSON)
5. Kiểm tra mâu thuẫn giữa LLM và bằng chứng công cụ (tối đa 2 vòng)
6. Áp dụng quy tắc ra nhãn & hậu kiểm an toàn
7. Trả câu hỏi làm rõ khi nhãn là "Đáng ngờ" (hỗ trợ chạy lại bước 4-6 với câu trả lời)
8. Trả kết quả JSON chuẩn kèm trace minh bạch
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

from agent.prompts import SYSTEM_PROMPT, build_analysis_prompt
from tools.analyze_url import analyze_urls
from tools.extract_info import extract_info, mask_pii

load_dotenv()

MAX_INPUT_LENGTH = 1500
VALID_LABELS = {"Lừa đảo", "An toàn", "Đáng ngờ"}
MAX_AGENT_ROUNDS = 2


class ScamGuardAgent:
    """Agent phân tích tin nhắn lừa đảo tiếng Việt."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        load_dotenv(override=True)
        self.provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
        self.api_key = (api_key if api_key is not None else os.getenv("LLM_API_KEY", "")).strip()
        self.model = (model or os.getenv("LLM_MODEL", "gemini-2.0-flash")).strip()
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).strip()
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", "20"))

    @property
    def is_llm_configured(self) -> bool:
        """Kiểm tra đã cấu hình LLM hợp lệ hay chưa (Ollama chạy local không cần API key)."""
        if self.provider == "ollama":
            return bool(self.model)
        return bool(self.api_key and self.api_key != "your_api_key_here")

    def validate_input(self, message: str) -> str | None:
        """Kiểm tra đầu vào rỗng hoặc vượt quá 1.500 ký tự."""
        if not message or not message.strip():
            return "Tin nhắn đang trống. Vui lòng dán nội dung tin nhắn cần kiểm tra."
        if len(message.strip()) > MAX_INPUT_LENGTH:
            return (
                f"Tin nhắn quá dài ({len(message.strip())} ký tự). "
                f"Vui lòng rút gọn tối đa {MAX_INPUT_LENGTH} ký tự."
            )
        return None

    def _call_llm_api(self, user_prompt: str) -> str:
        """Gọi trực tiếp REST API của Ollama (local), Gemini hoặc OpenAI-compatible."""
        if not self.is_llm_configured:
            raise RuntimeError("Chưa cấu hình LLM_API_KEY trong file .env.")

        if self.provider == "ollama":
            base = self.base_url.rstrip("/") if self.base_url else "http://localhost:11434"
            endpoint = f"{base}/api/chat"
            payload = {
                "model": self.model,
                "stream": False,
                "format": "json",
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 2048,
                    "num_predict": 320,
                },
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            }
            resp = requests.post(endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise ValueError("Ollama không trả về nội dung phản hồi.")
            return content

        if self.provider == "gemini":
            endpoint = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            )
            payload = {
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            }
            resp = requests.post(endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ValueError("Gemini không trả về nội dung phản hồi.")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts)

        
        base = self.base_url.rstrip("/") if self.base_url else "https://api.openai.com/v1"
        endpoint = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LLM không trả về choices.")
        return choices[0].get("message", {}).get("content", "")

    @staticmethod
    def _parse_json_response(raw_text: str) -> dict[str, Any]:
        """Trích xuất và parse JSON từ phản hồi LLM (xử lý cả trường hợp bọc ```json)."""
        cleaned = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1)
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start : end + 1]

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("Kết quả LLM không phải JSON object.")
        if parsed.get("label") not in VALID_LABELS:
            raise ValueError(f"Nhãn không hợp lệ: {parsed.get('label')}")
        return parsed

    def _call_llm_with_retry(self, user_prompt: str, trace: list[str]) -> dict[str, Any] | None:
        """Gọi LLM và tự động thử lại 1 lần nếu lỗi mạng, timeout hoặc JSON sai khuôn dạng."""
        for attempt in (1, 2):
            try:
                prompt_to_send = user_prompt
                if attempt == 2:
                    prompt_to_send += (
                        "\n\nNHẮC LẠI: Bắt buộc chỉ trả về JSON hợp lệ theo đúng schema, "
                        "label chỉ được là 'Lừa đảo', 'An toàn' hoặc 'Đáng ngờ'."
                    )
                raw = self._call_llm_api(prompt_to_send)
                parsed = self._parse_json_response(raw)
                trace.append(f"Gọi LLM thành công (lần thử {attempt}) → nhãn sơ bộ: {parsed['label']}.")
                return parsed
            except Exception as exc:
                trace.append(f"Lỗi LLM (lần thử {attempt}): {exc}")
        return None

    @staticmethod
    def _detect_contradiction(
        llm_result: dict[str, Any],
        extract_result: dict[str, Any],
        url_results: list[dict[str, Any]],
    ) -> str | None:
        """Kiểm tra mâu thuẫn giữa kết luận của LLM và bằng chứng từ 2 công cụ."""
        label = llm_result.get("label")
        has_high_risk_url = any(u["risk_level"] == "high" for u in url_results)
        has_short_or_suspicious_url = any(
            any(f in {"shortened_url", "brand_impersonation", "suspicious_tld", "ip_address_url"} for f in u["flags"])
            for u in url_results
        )
        has_pressure = bool(extract_result.get("pressure_phrases"))
        has_org = bool(extract_result.get("organizations"))

        
        if label == "An toàn" and (has_high_risk_url or has_short_or_suspicious_url):
            return (
                "Bằng chứng từ analyze_url cho thấy tin nhắn có đường link rủi ro cao "
                "(giả thương hiệu, link rút gọn hoặc đuôi bất thường), mâu thuẫn với nhãn 'An toàn'."
            )

       
        strong_categories = {"de_doa_khoa_phat", "yeu_cau_tai_chinh", "yeu_cau_thong_tin_nhay_cam"}
        has_strong_pressure = any(
            cat in extract_result.get("pressure_categories", {}) for cat in strong_categories
        )
        if label == "An toàn" and has_org and has_strong_pressure and not extract_result.get("has_safe_otp_warning"):
            return (
                "Tin nhắn nhắc đến tổ chức kèm cụm từ đe dọa/yêu cầu nhạy cảm, "
                "mâu thuẫn với nhãn 'An toàn'. Cần xem xét lại giữa 'Lừa đảo' và 'Đáng ngờ'."
            )

        # Mâu thuẫn 3: LLM bảo Lừa đảo nhưng công cụ không thấy bất kỳ tín hiệu nào (không link, không áp lực, không tổ chức)
        if label == "Lừa đảo" and not url_results and not has_pressure and not has_org:
            return (
                "Hai công cụ không tìm thấy URL, tổ chức bị mạo danh hay cụm từ gây áp lực nào, "
                "mâu thuẫn với nhãn 'Lừa đảo'. Hãy kiểm tra lại xem có nên gắn 'Đáng ngờ' hoặc 'An toàn' không."
            )

        return None

    @staticmethod
    def _default_followup_question(extract_result: dict[str, Any]) -> str:
        """Sinh câu hỏi làm rõ mặc định khi kết quả là Đáng ngờ."""
        orgs = extract_result.get("organizations") or []
        if any("Bưu chính" in o or "Giao hàng" in o for o in orgs):
            return "Bạn có đang chờ nhận đơn hàng nào từ đơn vị vận chuyển này không?"
        if orgs:
            return f"Bạn có đang sử dụng dịch vụ hoặc có tài khoản tại {orgs[0]} không?"
        return "Bạn có quen biết người gửi hoặc đang chờ thông báo/giao dịch nào liên quan đến tin nhắn này không?"

    @staticmethod
    def _normalize_output(
        raw_result: dict[str, Any],
        extract_result: dict[str, Any],
        url_results: list[dict[str, Any]],
        has_clarification: bool,
    ) -> dict[str, Any]:
        """Chuẩn hóa JSON đầu ra theo đúng schema ở mục 4.4."""
        label = raw_result.get("label", "Đáng ngờ")
        if label not in VALID_LABELS:
            label = "Đáng ngờ"

        try:
            confidence = float(raw_result.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = round(max(0.0, min(1.0, confidence)), 2)

        placeholder_garbage = {
            "lý do ngắn 1", "lý do ngắn 2", "lý do 1", "lý do 2",
            "khuyến nghị 1", "khuyến nghị 2", "bằng chứng ngắn",
        }
        reasons = raw_result.get("reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        reasons = [
            str(r).strip()
            for r in reasons
            if str(r).strip() and str(r).strip().lower() not in placeholder_garbage
        ]
        if not reasons:
            reasons = extract_result.get("findings", [])[:2] or [
                "Kết quả phân tích dựa trên nội dung tin nhắn và bộ công cụ kiểm tra."
            ]

        evidence = raw_result.get("evidence") or []
        clean_evidence: list[dict[str, str]] = []
        for item in evidence:
            if isinstance(item, dict) and item.get("finding"):
                finding_str = str(item.get("finding")).strip()
                if finding_str.lower() in placeholder_garbage:
                    continue
                tool_name = str(item.get("tool", "extract_info")).strip()
                if "|" in tool_name:
                    tool_name = "extract_info"
                clean_evidence.append({"tool": tool_name, "finding": finding_str})
        if not clean_evidence:
            for f in extract_result.get("findings", []):
                clean_evidence.append({"tool": "extract_info", "finding": f})
            for u in url_results:
                for f in u.get("findings", []):
                    clean_evidence.append({"tool": "analyze_url", "finding": f})

        recommendation = raw_result.get("recommendation") or []
        if isinstance(recommendation, str):
            recommendation = [recommendation]
        recommendation = [
            str(r).strip()
            for r in recommendation
            if str(r).strip() and str(r).strip().lower() not in placeholder_garbage
        ]
        if not recommendation:
            recommendation = [
                "Không bấm vào đường link lạ trong tin nhắn.",
                "Không cung cấp mã OTP, mật khẩu hay thông tin tài khoản.",
                "Kiểm tra trực tiếp qua kênh chăm sóc khách hàng chính thức của tổ chức.",
            ]

        follow_up = raw_result.get("follow_up_question")
        if label == "Đáng ngờ" and not follow_up and not has_clarification:
            follow_up = ScamGuardAgent._default_followup_question(extract_result)
        elif label != "Đáng ngờ":
            follow_up = None

        return {
            "label": label,
            "confidence": confidence,
            "reasons": reasons,
            "evidence": clean_evidence,
            "recommendation": recommendation,
            "follow_up_question": follow_up,
        }

    def _fallback_result(
        self,
        extract_result: dict[str, Any],
        url_results: list[dict[str, Any]],
        has_clarification: bool,
    ) -> dict[str, Any]:
        """Kết quả dự phòng theo mục 4.5 khi LLM lỗi/timeout/chưa cấu hình key.

        Chỉ dựa trên 2 công cụ, gắn nhãn 'Đáng ngờ' và ghi rõ 'chưa có phân tích đầy đủ'.
        """
        reasons: list[str] = [
            "Chưa có phân tích đầy đủ từ AI (kết quả dự phòng dựa trên hai công cụ phân tích tĩnh)."
        ]
        evidence: list[dict[str, str]] = []

        for finding in extract_result.get("findings", []):
            evidence.append({"tool": "extract_info", "finding": finding})
        for u in url_results:
            for finding in u.get("findings", []):
                evidence.append({"tool": "analyze_url", "finding": finding})

        high_risk_urls = [u for u in url_results if u["risk_level"] == "high"]
        if high_risk_urls:
            reasons.append("Công cụ phát hiện đường link có dấu hiệu giả mạo hoặc rút gọn đáng ngờ.")
        if extract_result.get("pressure_phrases"):
            reasons.append("Công cụ phát hiện cụm từ gây áp lực, đe dọa hoặc yêu cầu thông tin nhạy cảm.")
        if not evidence:
            evidence.append(
                {
                    "tool": "extract_info",
                    "finding": "Không tìm thấy URL hay cụm từ gây áp lực rõ ràng bằng bộ lọc từ khóa.",
                }
            )

        return {
            "label": "Đáng ngờ",
            "confidence": 0.45,
            "reasons": reasons,
            "evidence": evidence,
            "recommendation": [
                "Không bấm vào bất kỳ đường link nào trong tin nhắn.",
                "Không cung cấp mã OTP, mật khẩu hoặc chuyển tiền.",
                "Chủ động xác minh qua ứng dụng hoặc kênh chính thức của tổ chức liên quan.",
            ],
            "follow_up_question": (
                None if has_clarification else self._default_followup_question(extract_result)
            ),
        }

    def analyze(
        self,
        message: str,
        user_clarification: str | None = None,
    ) -> dict[str, Any]:
        """Chạy trọn luồng Agent cho một tin nhắn.

        Trả về dict gồm:
        - result: JSON đầu ra chuẩn theo mục 4.4
        - trace: danh sách các bước Agent đã thực hiện
        - masked_message: tin nhắn đã che PII gửi cho LLM
        - used_fallback: True nếu phải dùng chế độ dự phòng không có LLM
        - rounds: số vòng suy luận đã chạy (1 hoặc 2)
        """
        validation_error = self.validate_input(message)
        if validation_error:
            return {"error": validation_error}

        trace: list[str] = []
        cleaned_message = message.strip()
        trace.append(f"Bước 1 (Nhận đầu vào): Hợp lệ ({len(cleaned_message)} ký tự).")

        
        extract_result = extract_info(cleaned_message, strict_mode=False)
        trace.append(
            f"Bước 2 (extract_info): Tìm thấy {len(extract_result['urls'])} URL, "
            f"{len(extract_result['organizations'])} tổ chức, "
            f"{len(extract_result['pressure_phrases'])} cụm từ áp lực."
        )

        
        url_results = analyze_urls(extract_result["urls"])
        if url_results:
            high_count = sum(1 for u in url_results if u["risk_level"] == "high")
            trace.append(
                f"Bước 3 (analyze_url): Phân tích tĩnh {len(url_results)} URL "
                f"({high_count} URL rủi ro cao, không truy cập link thật)."
            )
        else:
            trace.append("Bước 3 (analyze_url): Tin nhắn không chứa URL.")

       
        masked_message = mask_pii(cleaned_message)
        if masked_message != cleaned_message:
            trace.append("Bảo mật PII: Đã che số điện thoại / số tài khoản trước khi gọi LLM.")


       
        rounds = 1
        prompt = build_analysis_prompt(
            masked_message=masked_message,
            extract_result=extract_result,
            url_results=url_results,
            user_clarification=user_clarification,
        )
        llm_result = self._call_llm_with_retry(prompt, trace)

        used_fallback = False
        if llm_result is None:
            used_fallback = True
            trace.append("Fallback: Chuyển sang kết quả dự phòng từ 2 công cụ (nhãn Đáng ngờ).")
            final_result = self._fallback_result(
                extract_result=extract_result,
                url_results=url_results,
                has_clarification=bool(user_clarification),
            )
        else:
            contradiction = self._detect_contradiction(llm_result, extract_result, url_results)
            if contradiction and rounds < MAX_AGENT_ROUNDS:
                rounds += 1
                trace.append(f"Bước 5 (Kiểm tra mâu thuẫn - Vòng {rounds}): {contradiction}")
               
                extract_result = extract_info(cleaned_message, strict_mode=True)
                recheck_prompt = build_analysis_prompt(
                    masked_message=masked_message,
                    extract_result=extract_result,
                    url_results=url_results,
                    user_clarification=user_clarification,
                    contradiction_note=contradiction,
                )
                llm_recheck = self._call_llm_with_retry(recheck_prompt, trace)
                if llm_recheck is not None:
                    llm_result = llm_recheck
            else:
                trace.append("Bước 5 (Kiểm tra mâu thuẫn): Không phát hiện mâu thuẫn.")

            final_result = self._normalize_output(
                raw_result=llm_result,
                extract_result=extract_result,
                url_results=url_results,
                has_clarification=bool(user_clarification),
            )
            trace.append(
                f"Bước 6–8 (Kết luận): Nhãn '{final_result['label']}' "
                f"(độ tự tin {int(final_result['confidence'] * 100)}%)."
            )

        return {
            "result": final_result,
            "trace": trace,
            "masked_message": masked_message,
            "used_fallback": used_fallback,
            "rounds": rounds,
            "tools_output": {
                "extract_info": extract_result,
                "analyze_url": url_results,
            },
        }


def _run_cli_demo() -> None:
    """Chạy nhanh 3 tình huống demo từ dòng lệnh (phục vụ mốc kiểm tra C1)."""
    from pathlib import Path

    data_path = Path(__file__).resolve().parent.parent / "data" / "test_messages.json"
    with data_path.open("r", encoding="utf-8") as f:
        scenarios = json.load(f)

    demo_cases = [item for item in scenarios if item.get("is_demo")]
    agent = ScamGuardAgent()

    print("=" * 68)
    print("SCAMGUARD VN – CLI DEMO (3 TÌNH HUỐNG CỐT LÕI)")
    print(f"LLM configured: {agent.is_llm_configured} | Provider: {agent.provider} | Model: {agent.model}")
    print("=" * 68)

    for case in demo_cases:
        print(f"\n[{case['id']}] {case['title']} (Kỳ vọng: {case['expected_label']})")
        print(f"Tin nhắn: {case['message']}")
        output = agent.analyze(case["message"])
        print(json.dumps(output["result"], ensure_ascii=False, indent=2))
        if output["result"].get("follow_up_question") and case.get("sample_clarification"):
            print(f"-> Câu hỏi làm rõ: {output['result']['follow_up_question']}")
            print(f"-> Người dùng trả lời: {case['sample_clarification']}")
            followup_out = agent.analyze(case["message"], user_clarification=case["sample_clarification"])
            print("-> Kết quả sau khi làm rõ:")
            print(json.dumps(followup_out["result"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _run_cli_demo()
