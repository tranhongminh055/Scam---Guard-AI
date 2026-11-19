"""Unit test cho Công cụ 1 (extract_info), Công cụ 2 (analyze_url) và cơ chế an toàn của Agent."""

from agent.core import ScamGuardAgent
from tools.analyze_url import analyze_url
from tools.extract_info import analyze_phone_number, extract_info, mask_pii, normalize_vietnamese


class TestExtractInfo:
    def test_url_with_trailing_punctuation(self):
        msg = "Vui long xac minh tai https://vietc0mbank-verify.xyz/login. Cam on!"
        res = extract_info(msg)
        assert res["urls"] == ["https://vietc0mbank-verify.xyz/login"]

    def test_shortened_url_without_scheme(self):
        msg = "Thanh toan tien dien tai bit.ly/evn-hoadon, trong 24h!"
        res = extract_info(msg)
        assert "bit.ly/evn-hoadon" in res["urls"]

    def test_phone_multiple_formats(self):
        msg = "Lien he 0901.234.567 hoac +84 912 345 678 hoac 0987-654-321."
        res = extract_info(msg)
        assert len(res["phones"]) == 3

    def test_vietnamese_no_accent_and_pressure_phrases(self):
        msg = "Vietcombank thong bao tk bi khoa trong 24h, vui long xac minh ngay va gui ma otp."
        res = extract_info(msg)
        assert "Vietcombank" in res["organizations"]
        assert "ap_luc_thoi_gian" in res["pressure_categories"]
        assert "de_doa_khoa_phat" in res["pressure_categories"]
        assert "yeu_cau_thong_tin_nhay_cam" in res["pressure_categories"]

    def test_account_number_extraction_not_confused_with_phone(self):
        msg = "Chuyen tien vao stk 19001234567890 hoac goi 0901234567."
        res = extract_info(msg)
        assert "19001234567890" in res["account_numbers"]
        assert "0901234567" not in res["account_numbers"]
        assert "0901234567" in res["phones"]

    def test_mask_pii_hides_phone_and_account_but_keeps_url(self):
        msg = "Goi 0901234567 chuyen vao stk 19001234567890 tai https://vietc0mbank.xyz"
        masked = mask_pii(msg)
        assert "0901234567" not in masked
        assert "19001234567890" not in masked
        assert "https://vietc0mbank.xyz" in masked

    def test_normalize_vietnamese(self):
        assert normalize_vietnamese("Điện lực Đắk Lắk khóa tài khoản") == "dien luc dak lak khoa tai khoan"


class TestAnalyzeUrl:
    def test_brand_impersonation_zero_for_o_and_hyphen(self):
        res = analyze_url("https://vietc0mbank-verify.xyz/xac-thuc.")
        assert res["url"] == "https://vietc0mbank-verify.xyz/xac-thuc"
        assert "brand_impersonation" in res["flags"]
        assert "suspicious_tld" in res["flags"]
        assert res["risk_level"] == "high"

    def test_shortened_url_detected(self):
        res = analyze_url("bit.ly/evn-hoadon")
        assert "shortened_url" in res["flags"]
        assert res["risk_level"] in {"medium", "high"}

    def test_typosquatting_brand_detected(self):
        res = analyze_url("https://techcombak-vn.site/login")
        assert "brand_impersonation" in res["flags"]
        assert res["risk_level"] == "high"

    def test_official_domain_low_risk(self):
        res = analyze_url("https://www.vietcombank.com.vn/news")
        assert "official_domain" in res["flags"]
        assert "brand_impersonation" not in res["flags"]
        assert res["risk_level"] == "low"

    def test_ip_address_and_punycode(self):
        res_ip = analyze_url("http://192.168.1.10/login")
        assert "ip_address_url" in res_ip["flags"]
        assert res_ip["risk_level"] == "high"

        res_puny = analyze_url("https://xn--vietcombank-1a.com")
        assert "punycode_or_non_ascii" in res_puny["flags"]
        assert res_puny["risk_level"] == "high"


class TestAgentSafetyAndFallback:
    def test_input_validation_empty_and_too_long(self):
        agent = ScamGuardAgent(provider="gemini", api_key="")
        assert "error" in agent.analyze("   ")
        assert "error" in agent.analyze("a" * 1501)

    def test_fallback_when_no_api_key(self):
        agent = ScamGuardAgent(provider="gemini", api_key="")
        out = agent.analyze(
            "Vietcombank thong bao tai khoan bi khoa trong 24h tai https://vietc0mbank-verify.xyz"
        )
        assert out["used_fallback"] is True
        assert out["result"]["label"] == "Đáng ngờ"
        assert any("chưa có phân tích đầy đủ" in r.lower() for r in out["result"]["reasons"])
        assert len(out["result"]["evidence"]) >= 2

    def test_contradiction_detector_flags_safe_with_high_risk_url(self):
        agent = ScamGuardAgent(provider="gemini", api_key="")
        ext = extract_info("Vietcombank tai https://vietc0mbank-verify.xyz")
        urls = [analyze_url("https://vietc0mbank-verify.xyz")]
        note = agent._detect_contradiction({"label": "An toàn"}, ext, urls)
        assert note is not None

    def test_analyze_phone_number_types(self):
        res_mobile = analyze_phone_number("0901234567")
        assert res_mobile["type"] == "mobile"
        res_intl = analyze_phone_number("+1 202 555 0199")
        assert res_intl["type"] == "international"
        res_1900 = analyze_phone_number("19001234")
        assert res_1900["type"] == "hotline_1900"
