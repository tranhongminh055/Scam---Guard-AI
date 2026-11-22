"""Công cụ 1 (extract_info): Trích xuất thông tin và tín hiệu rủi ro từ văn bản tin nhắn.

Hỗ trợ tiếng Việt có dấu và không dấu. Bao gồm hàm mask_pii() để che thông tin
cá nhân (SĐT, số tài khoản, CCCD) trước khi gửi nội dung sang dịch vụ LLM.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Danh sách tổ chức thường bị mạo danh tại Việt Nam (dạng không dấu, chữ thường)
ORG_PATTERNS: dict[str, list[str]] = {
    "Vietcombank": ["vietcombank", "vcb", "digibank"],
    "BIDV": ["bidv", "smartbanking"],
    "Techcombank": ["techcombank", "tcb"],
    "VietinBank": ["vietinbank", "viettinbank", "ipay"],
    "Agribank": ["agribank"],
    "MB Bank": ["mb bank", "mbbank", "mb-bank"],
    "ACB": ["ngan hang acb", "acb one", "acb bank"],
    "VPBank": ["vpbank", "vp bank", "vpbank neo"],
    "Sacombank": ["sacombank"],
    "TPBank": ["tpbank", "tp bank"],
    "VIB": ["ngan hang vib", "myvib"],
    "SHB": ["ngan hang shb", "shb bank"],
    "MoMo": ["vi momo", "momo"],
    "ZaloPay": ["zalopay", "zalo pay"],
    "VNPay": ["vnpay"],
    "Điện lực (EVN)": ["evn", "dien luc", "dienluc", "tien dien", "cat dien"],
    "Công an / Cơ quan điều tra": [
        "cong an",
        "bo cong an",
        "canh sat",
        "vien kiem sat",
        "toa an",
        "co quan dieu tra",
    ],
    "VNeID": ["vneid", "dinh danh dien tu"],
    "Cục Thuế": ["cuc thue", "tong cuc thue", "etax", "hoan thue"],
    "Bảo hiểm xã hội (BHXH)": ["bhxh", "bao hiem xa hoi", "vssid"],
    "Bưu chính / Giao hàng": [
        "vnpost",
        "buu dien",
        "viettel post",
        "viettelpost",
        "giao hang nhanh",
        "ghn",
        "giao hang tiet kiem",
        "ghtk",
        "j&t",
        "shopee express",
        "spx",
    ],
    "Sàn TMĐT (Shopee / Lazada / TikTok)": [
        "shopee",
        "lazada",
        "tiki",
        "tiktok shop",
    ],
}

# Các nhóm cụm từ gây áp lực / đe dọa / yêu cầu nhạy cảm (dạng không dấu)
PRESSURE_CATEGORIES: dict[str, list[str]] = {
    "ap_luc_thoi_gian": [
        "trong 24 gio",
        "trong 24h",
        "trong vong 24h",
        "trong vong 24 gio",
        "trong 2 gio",
        "trong 2h",
        "ngay lap tuc",
        "khan cap",
        "gap",
        "han chot",
        "truoc 17h",
        "truoc 12h",
        "hom nay",
        "neu khong se bi",
    ],
    "de_doa_khoa_phat": [
        "khoa tai khoan",
        "bi khoa",
        "tk bi khoa",
        "tai khoan bi khoa",
        "tam khoa",
        "dinh chi",
        "phong toa",
        "ngung cung cap dien",
        "cat dien",
        "khoi to",
        "bat giu",
        "lenh bat",
        "phat nguoi",
        "xu ly hinh su",
        "vo hieu hoa",
        "thu hoi",
    ],
    "yeu_cau_tai_chinh": [
        "nop phi",
        "dong phi",
        "thanh toan phi",
        "chuyen tien",
        "chuyen khoan",
        "dat coc",
        "phi hai quan",
        "phi giao hang",
        "phi xac minh",
        "nhan qua",
        "trung thuong",
        "hoan tien",
        "thanh toan ngay",
    ],
    "yeu_cau_thong_tin_nhay_cam": [
        "cung cap otp",
        "gui ma otp",
        "nhap ma otp",
        "doc ma otp",
        "gui otp",
        "ma xac thuc",
        "mat khau",
        "ma pin",
        "cap nhat thong tin",
        "xac minh tai khoan",
        "xac thuc tai khoan",
        "xac minh ngay",
        "xac thuc ngay",
        "xac nhan ngay",
        "cap nhat sinh trac",
        "dong bo du lieu",
    ],
}

# Cụm từ cảnh báo an toàn thường gặp trong tin OTP thật
SAFE_OTP_MARKERS = [
    "khong chia se",
    "khong cung cap",
    "khong gui cho bat ky ai",
    "tuyet doi khong",
    "do not share",
]

# Regex tách URL (có http/https, www., hoặc domain phổ biến kèm path/TLD)
URL_REGEX = re.compile(
    r"(?i)"
    r"(?:https?://[^\s<>\"'\]\)]+)"
    r"|(?:www\.[^\s<>\"'\]\)]+)"
    r"|(?:\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
    r"\.(?:com|vn|net|org|xyz|top|click|site|online|vip|club|icu|info|ly|gl|co|id|so|to|at|gy|cc|pro|live|store|tk|ml|ga|cf|gq|gov|edu|bank|io|me|app)"
    r"(?:/[^\s<>\"'\]\)]*)?)"
)

# Regex số điện thoại Việt Nam (03/05/07/08/09, +84, 84, hoặc tổng đài 1800/1900)
PHONE_REGEX = re.compile(
    r"(?<!\d)(?:(?:\+84|84|0)(?:[\s.\-]*\d){9}|(?:1800|1900)[\s.\-]?\d{4,6})(?!\d)"
)

# Regex số tài khoản ngân hàng (thường đi kèm ngữ cảnh stk/tk hoặc 9-16 chữ số)
ACCOUNT_CONTEXT_REGEX = re.compile(
    r"(?i)(?:stk|so\s*tk|so\s*tai\s*khoan|tai\s*khoan|account|acct)\s*[:#\-]?\s*(\d[\d\s.\-]{7,18}\d)"
)
GENERIC_LONG_NUMBER_REGEX = re.compile(r"(?<!\d)(\d{9,16})(?!\d)")

# Ký tự dấu câu thường dính ở cuối URL trong văn bản tiếng Việt
TRAILING_PUNCTUATION = ".,;:!?)\"']}»”’"


def normalize_vietnamese(text: str) -> str:
    """Chuyển tiếng Việt có dấu sang không dấu, chữ thường để đối chiếu ổn định."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    no_accent = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accent.lower()).strip()


def _clean_url(raw_url: str) -> str:
    """Loại bỏ dấu câu dư thừa ở cuối URL (ví dụ dấu chấm kết thúc câu)."""
    cleaned = raw_url.strip()
    while cleaned and cleaned[-1] in TRAILING_PUNCTUATION:
        cleaned = cleaned[:-1]
    return cleaned


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def extract_urls(text: str) -> list[str]:
    """Trích xuất tất cả URL trong văn bản và làm sạch dấu câu cuối."""
    raw_matches = URL_REGEX.findall(text)
    cleaned = [_clean_url(m) for m in raw_matches]
    cleaned = [u for u in cleaned if u and "." in u and "@" not in u.split("/")[0]]
    return _dedupe_preserve_order(cleaned)


def extract_phones(text: str) -> list[str]:
    """Trích xuất số điện thoại nhiều định dạng tại Việt Nam."""
    matches = PHONE_REGEX.findall(text)
    result: list[str] = []
    for m in matches:
        digits = re.sub(r"\D", "", m)
        # Bỏ qua nếu độ dài không khớp chuẩn SĐT VN
        if digits.startswith("84") and len(digits) == 11:
            result.append(m.strip())
        elif digits.startswith("0") and len(digits) == 10:
            result.append(m.strip())
        elif (digits.startswith("1800") or digits.startswith("1900")) and 8 <= len(digits) <= 10:
            result.append(m.strip())
    return _dedupe_preserve_order(result)


def extract_account_numbers(text: str, phones: list[str]) -> list[str]:
    """Trích xuất số tài khoản ngân hàng (loại trừ số trùng với SĐT)."""
    phone_digits = {re.sub(r"\D", "", p) for p in phones}
    accounts: list[str] = []

    for match in ACCOUNT_CONTEXT_REGEX.finditer(text):
        digits = re.sub(r"\D", "", match.group(1))
        if 8 <= len(digits) <= 16 and digits not in phone_digits:
            accounts.append(digits)

    for match in GENERIC_LONG_NUMBER_REGEX.finditer(text):
        digits = match.group(1)
        if digits in phone_digits:
            continue
        # Tránh nhầm SĐT 10 số bắt đầu bằng 03/05/07/08/09 hoặc 11 số bắt đầu bằng 84
        if len(digits) == 10 and digits[:2] in {"03", "05", "07", "08", "09"}:
            continue
        if len(digits) == 11 and digits.startswith("84"):
            continue
        accounts.append(digits)

    return _dedupe_preserve_order(accounts)


def extract_organizations(normalized_text: str) -> list[str]:
    """Nhận diện tên tổ chức/ngân hàng/cơ quan được nhắc đến trong tin nhắn."""
    found: list[str] = []
    for org_name, keywords in ORG_PATTERNS.items():
        for kw in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", normalized_text):
                found.append(org_name)
                break
    return found


NEGATION_PREFIXES = (
    "khong yeu cau ",
    "khong can ",
    "khong chia se ",
    "khong cung cap ",
    "khong phai ",
    "khong doi ",
)


def extract_pressure_phrases(normalized_text: str) -> dict[str, list[str]]:
    """Phát hiện các cụm từ gây áp lực, đe dọa, yêu cầu tài chính hoặc thông tin nhạy cảm.

    Bỏ qua các cụm từ bị phủ định trực tiếp (vd: 'khong yeu cau chuyen tien').
    """
    found_by_category: dict[str, list[str]] = {}
    for category, phrases in PRESSURE_CATEGORIES.items():
        matched: list[str] = []
        for phrase in phrases:
            idx = normalized_text.find(phrase)
            if idx == -1:
                continue
            prefix_window = normalized_text[max(0, idx - 36) : idx]
            if any(neg in prefix_window for neg in NEGATION_PREFIXES):
                continue
            matched.append(phrase)
        if matched:
            found_by_category[category] = matched
    return found_by_category


def mask_pii(text: str) -> str:
    """Che thông tin cá nhân (SĐT, số tài khoản, CCCD) trước khi gửi cho LLM API.

    Giữ nguyên URL/tên miền để LLM vẫn đánh giá được ngữ cảnh lừa đảo.
    """
    if not text:
        return ""

    masked = PHONE_REGEX.sub("[SĐT_ĐÃ_CHE]", text)

    def _mask_acct(match: re.Match[str]) -> str:
        full = match.group(0)
        number_part = match.group(1)
        return full.replace(number_part, "[STK_ĐÃ_CHE]")

    masked = ACCOUNT_CONTEXT_REGEX.sub(_mask_acct, masked)
    # Che các chuỗi 12 chữ số (CCCD) hoặc dãy số tài khoản dài đứng độc lập
    masked = re.sub(r"(?<!\d)\d{12}(?!\d)", "[CCCD/STK_ĐÃ_CHE]", masked)
    masked = re.sub(r"(?<!\d)\d{9,16}(?!\d)", "[SỐ_ĐÃ_CHE]", masked)
    return masked


def extract_info(text: str, strict_mode: bool = False) -> dict[str, Any]:
    """Hàm chính của Công cụ 1: trích xuất toàn bộ thực thể và tín hiệu từ tin nhắn.

    Args:
        text: Nội dung tin nhắn gốc do người dùng cung cấp.
        strict_mode: Nếu True (dùng khi agent kiểm tra lại ở vòng 2), bổ sung
            kiểm tra các tín hiệu viết tắt / mơ hồ sâu hơn.
    """
    normalized = normalize_vietnamese(text)
    urls = extract_urls(text)
    phones = extract_phones(text)
    accounts = extract_account_numbers(text, phones)
    organizations = extract_organizations(normalized)
    pressure_by_category = extract_pressure_phrases(normalized)

    all_pressure_phrases = [
        phrase for phrases in pressure_by_category.values() for phrase in phrases
    ]
    has_safe_otp_warning = any(marker in normalized for marker in SAFE_OTP_MARKERS)
    has_otp_mention = bool(re.search(r"(?<![a-z0-9])otp(?![a-z0-9])", normalized))

    extra_signals: list[str] = []
    if strict_mode:
        # Kiểm tra thêm các cụm viết tắt tiếng Việt hay xuất hiện trong tin lừa đảo
        abbreviations = {
            "tk": "Nhắc đến viết tắt tài khoản ('tk')",
            "ck": "Nhắc đến viết tắt chuyển khoản ('ck')",
            "stk": "Nhắc đến số tài khoản ('stk')",
            "lh": "Yêu cầu liên hệ viết tắt ('lh')",
        }
        for abbr, desc in abbreviations.items():
            if re.search(rf"(?<![a-z0-9]){abbr}(?![a-z0-9])", normalized):
                extra_signals.append(desc)

    findings: list[str] = []
    if organizations:
        findings.append(f"Nhắc đến tổ chức: {', '.join(organizations)}.")
    if urls:
        findings.append(f"Tìm thấy {len(urls)} đường link: {', '.join(urls)}.")
    if phones:
        findings.append(f"Tìm thấy {len(phones)} số điện thoại (đã che khi gửi AI).")
    if accounts:
        findings.append(f"Tìm thấy {len(accounts)} số tài khoản (đã che khi gửi AI).")
    if all_pressure_phrases:
        findings.append(
            f"Phát hiện cụm từ gây áp lực/nhạy cảm: {', '.join(all_pressure_phrases[:6])}."
        )
    if has_otp_mention and has_safe_otp_warning and not urls:
        findings.append("Tin nhắn có mã OTP kèm cảnh báo không chia sẻ (dấu hiệu tin OTP thật).")
    if extra_signals:
        findings.extend(extra_signals)

    return {
        "urls": urls,
        "phones": phones,
        "account_numbers": accounts,
        "organizations": organizations,
        "pressure_categories": pressure_by_category,
        "pressure_phrases": all_pressure_phrases,
        "has_otp_mention": has_otp_mention,
        "has_safe_otp_warning": has_safe_otp_warning,
        "extra_signals": extra_signals,
        "findings": findings,
    }


# Bảng đầu số di động phổ biến tại Việt Nam (3 chữ số đầu)
VN_MOBILE_PREFIXES: dict[str, str] = {
    "032": "Viettel", "033": "Viettel", "034": "Viettel", "035": "Viettel",
    "036": "Viettel", "037": "Viettel", "038": "Viettel", "039": "Viettel",
    "086": "Viettel", "096": "Viettel", "097": "Viettel", "098": "Viettel",
    "070": "MobiFone", "076": "MobiFone", "077": "MobiFone", "078": "MobiFone",
    "079": "MobiFone", "089": "MobiFone", "090": "MobiFone", "093": "MobiFone",
    "081": "VinaPhone", "082": "VinaPhone", "083": "VinaPhone", "084": "VinaPhone",
    "085": "VinaPhone", "088": "VinaPhone", "091": "VinaPhone", "094": "VinaPhone",
    "052": "Vietnamobile", "056": "Vietnamobile", "058": "Vietnamobile", "092": "Vietnamobile",
    "059": "Gmobile", "099": "Gmobile",
    "055": "Reddi/Wintel", "087": "I-Telecom",
}


def analyze_phone_number(raw_text: str) -> dict[str, Any]:
    """Phân tích tĩnh số điện thoại (đầu số, nhà mạng, tổng đài, đầu số quốc tế lạ).

    Không tra cứu cơ sở dữ liệu bên ngoài; chỉ phân tích định dạng & quy tắc đầu số.
    """
    cleaned = raw_text.strip()
    digits = re.sub(r"\D", "", cleaned)
    flags: list[str] = []
    findings: list[str] = []

    if not digits:
        return {
            "normalized": "",
            "type": "invalid",
            "flags": ["invalid_phone"],
            "findings": ["Không tìm thấy chuỗi chữ số điện thoại hợp lệ."],
        }

    # Chuẩn hóa +84 / 84 về đầu 0
    local_digits = digits
    is_intl_non_vn = False
    if cleaned.startswith("+") and not cleaned.startswith("+84"):
        is_intl_non_vn = True
    elif digits.startswith("00") and not digits.startswith("0084"):
        is_intl_non_vn = True
    elif digits.startswith("84") and len(digits) == 11:
        local_digits = "0" + digits[2:]

    if is_intl_non_vn:
        flags.append("international_number")
        findings.append(
            f"Đầu số quốc tế ngoài Việt Nam ({cleaned}) — thường bị kẻ gian giả mạo "
            "cơ quan nhà nước, ngân hàng hoặc gọi nháy máy lừa đảo."
        )
        phone_type = "international"
    elif local_digits.startswith("1900") and 8 <= len(local_digits) <= 10:
        flags.append("premium_hotline_1900")
        findings.append(
            f"Đầu số tổng đài tính cước 1900 ({local_digits}). Cần kiểm tra đúng tổng đài chính thức "
            "trên website tổ chức trước khi gọi lại."
        )
        phone_type = "hotline_1900"
    elif local_digits.startswith("1800") and 8 <= len(local_digits) <= 10:
        flags.append("toll_free_1800")
        findings.append(f"Đầu số tổng đài miễn cước 1800 ({local_digits}).")
        phone_type = "hotline_1800"
    elif len(local_digits) == 10 and local_digits[:3] in VN_MOBILE_PREFIXES:
        carrier = VN_MOBILE_PREFIXES[local_digits[:3]]
        flags.append("vn_mobile_personal")
        findings.append(
            f"Số di động cá nhân Việt Nam ({local_digits[:3]}xxxx — nhà mạng {carrier}). "
            "Ngân hàng và cơ quan nhà nước KHÔNG dùng số di động cá nhân để yêu cầu OTP hay chuyển tiền."
        )
        phone_type = "mobile"
    elif local_digits.startswith("02") and len(local_digits) == 11:
        flags.append("vn_landline")
        findings.append(
            f"Số máy bàn cố định Việt Nam ({local_digits[:4]}xxxx). "
            "Cần thận trọng vì nhiều cuộc gọi mạo danh Công an/Tòa án dùng đầu số cố định ảo."
        )
        phone_type = "landline"
    else:
        flags.append("unusual_format")
        findings.append(
            f"Định dạng số điện thoại bất thường ({cleaned}, {len(digits)} chữ số), "
            "không khớp chuẩn số di động/tổng đài thông thường tại Việt Nam."
        )
        phone_type = "unusual"

    return {
        "normalized": local_digits,
        "type": phone_type,
        "flags": flags,
        "findings": findings,
    }
