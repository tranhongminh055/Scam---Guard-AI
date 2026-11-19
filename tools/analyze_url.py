"""Công cụ 2 (analyze_url): Phân tích chuỗi URL tĩnh, KHÔNG truy cập mạng.

Phát hiện:
- Link rút gọn (bit.ly, tinyurl.com, bom.so...)
- Tên miền giả dạng thương hiệu (thay chữ O bằng số 0, thêm gạch ngang, lỗi chính tả)
- Đuôi tên miền (TLD) bất thường / rủi ro cao (.xyz, .top, .click, .vip...)
- Ký tự lạ (Punycode xn--, ký tự @, địa chỉ IP trực tiếp, quá nhiều subdomain/gạch ngang)
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

# Danh sách tên miền rút gọn phổ biến
URL_SHORTENERS: set[str] = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
    "is.gd",
    "buff.ly",
    "s.id",
    "bom.so",
    "bom.to",
    "rebrand.ly",
    "cutt.ly",
    "shorturl.at",
    "rb.gy",
    "tiny.cc",
    "lnkd.in",
    "short.link",
    "by.com.vn",
    "rutgon.com.vn",
}

# Đuôi tên miền (TLD) hay bị lạm dụng trong tin nhắn lừa đảo
SUSPICIOUS_TLDS: set[str] = {
    "xyz",
    "top",
    "click",
    "club",
    "vip",
    "site",
    "online",
    "icu",
    "buzz",
    "tk",
    "ml",
    "ga",
    "cf",
    "gq",
    "work",
    "loan",
    "pw",
    "cc",
    "live",
    "store",
    "info",
    "pro",
    "asia",
}

# Ánh xạ thương hiệu -> danh sách tên miền chính thức (official domains)
BRAND_OFFICIAL_DOMAINS: dict[str, set[str]] = {
    "vietcombank": {"vietcombank.com.vn", "vcbdigibank.vietcombank.com.vn"},
    "vcb": {"vietcombank.com.vn", "vcbdigibank.vietcombank.com.vn"},
    "bidv": {"bidv.com.vn", "smartbanking.bidv.com.vn"},
    "techcombank": {"techcombank.com", "techcombank.com.vn"},
    "vietinbank": {"vietinbank.vn", "ipay.vietinbank.vn"},
    "agribank": {"agribank.com.vn"},
    "mbbank": {"mbbank.com.vn"},
    "vpbank": {"vpbank.com.vn"},
    "sacombank": {"sacombank.com.vn"},
    "tpbank": {"tpb.vn", "tpbank.vn"},
    "acb": {"acb.com.vn"},
    "momo": {"momo.vn"},
    "zalopay": {"zalopay.vn"},
    "vnpay": {"vnpay.vn"},
    "evn": {"evn.com.vn", "cskh.evnhanoi.vn", "cskh.evnhcmc.vn", "cskh.npc.com.vn", "cskh.cpc.vn", "cskh.evnspc.vn"},
    "vneid": {"vneid.gov.vn", "dinhdanhdientu.gov.vn"},
    "dichvucong": {"dichvucong.gov.vn"},
    "vnpost": {"vnpost.vn"},
    "viettelpost": {"viettelpost.com.vn", "viettelpost.vn"},
    "ghn": {"ghn.vn"},
    "ghtk": {"ghtk.vn", "giaohangtietkiem.vn"},
    "shopee": {"shopee.vn"},
    "lazada": {"lazada.vn"},
}

# Từ khóa thường xuất hiện trong đường dẫn lừa đảo (phishing path)
PHISHING_PATH_KEYWORDS: set[str] = {
    "verify",
    "xacminh",
    "xac-minh",
    "xacthuc",
    "xac-thuc",
    "login",
    "dang-nhap",
    "dangnhap",
    "khoa-tk",
    "mokhoa",
    "update",
    "cap-nhat",
    "otp",
    "banking",
    "support",
    "ho-tro",
    "nhan-qua",
    "trung-thuong",
}

TRAILING_PUNCTUATION = ".,;:!?)\"']}»”’"

# Bảng chuẩn hóa ký tự giả dạng (leetspeak / homoglyph phổ biến)
HOMOGLYPH_MAP = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "@": "a",
    }
)


def _levenshtein(a: str, b: str) -> int:
    """Tính khoảng cách chỉnh sửa (Levenshtein distance) giữa 2 chuỗi."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, ch_b in enumerate(b, start=1):
            cost = 0 if ch_a == ch_b else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _normalize_for_brand_check(domain: str) -> str:
    """Chuẩn hóa tên miền về dạng chữ thường, đổi số giả chữ (0->o, 1->l...) và bỏ gạch ngang."""
    lower = domain.lower().replace("rn", "m")
    translated = lower.translate(HOMOGLYPH_MAP)
    return re.sub(r"[^a-z]", "", translated)


def _is_official_domain(domain: str, official_domains: set[str]) -> bool:
    """Kiểm tra tên miền có khớp chính xác hoặc là subdomain hợp lệ của official domain không."""
    domain = domain.lower().strip(".")
    for official in official_domains:
        if domain == official or domain.endswith("." + official):
            return True
    return False


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def analyze_url(raw_url: str) -> dict[str, Any]:
    """Phân tích tĩnh một chuỗi URL, không thực hiện bất kỳ kết nối mạng nào."""
    cleaned = raw_url.strip()
    while cleaned and cleaned[-1] in TRAILING_PUNCTUATION:
        cleaned = cleaned[:-1]

    to_parse = cleaned if re.match(r"(?i)^https?://", cleaned) else f"http://{cleaned}"
    parsed = urlparse(to_parse)
    netloc = parsed.netloc.lower()
    path_and_query = f"{parsed.path}?{parsed.query}".lower()

    flags: list[str] = []
    findings: list[str] = []
    score = 0

    # 1. Kiểm tra ký tự '@' trong netloc (kỹ thuật che giấu domain thật)
    if "@" in netloc:
        flags.append("contains_at_symbol")
        findings.append("URL chứa ký tự '@' dùng để đánh lừa tên miền hiển thị.")
        score += 3
        host_port = netloc.split("@")[-1]
    else:
        host_port = netloc

    domain = host_port.split(":")[0].strip(".")
    if domain.startswith("www."):
        bare_domain = domain[4:]
    else:
        bare_domain = domain

    # 2. Kiểm tra địa chỉ IP trực tiếp
    if _is_ip_address(bare_domain):
        flags.append("ip_address_url")
        findings.append(f"Đường link dùng địa chỉ IP trực tiếp ({bare_domain}) thay vì tên miền chính thức.")
        score += 3

    # 3. Kiểm tra Punycode / ký tự ngoài bảng mã ASCII
    if "xn--" in bare_domain or any(ord(ch) > 127 for ch in bare_domain):
        flags.append("punycode_or_non_ascii")
        findings.append("Tên miền chứa ký tự lạ hoặc mã Punycode (xn--) có thể giả mạo chữ cái.")
        score += 3

    # 4. Kiểm tra link rút gọn
    if bare_domain in URL_SHORTENERS:
        flags.append("shortened_url")
        findings.append(f"Link rút gọn ({bare_domain}) che giấu địa chỉ đích thật sự.")
        score += 2

    # 5. Kiểm tra đuôi tên miền (TLD) bất thường
    parts = [p for p in bare_domain.split(".") if p]
    tld = parts[-1] if len(parts) >= 2 else ""
    if tld in SUSPICIOUS_TLDS:
        flags.append("suspicious_tld")
        findings.append(f"Đuôi tên miền '.{tld}' bất thường, thường bị lạm dụng trong trang giả mạo.")
        score += 2

    # 6. Kiểm tra cấu trúc tên miền (quá nhiều gạch ngang hoặc subdomain)
    if bare_domain.count("-") >= 2:
        flags.append("excessive_hyphens")
        findings.append(f"Tên miền '{bare_domain}' có nhiều dấu gạch ngang bất thường.")
        score += 1
    if len(parts) >= 4 and not bare_domain.endswith(".com.vn") and not bare_domain.endswith(".gov.vn"):
        flags.append("excessive_subdomains")
        findings.append(f"Tên miền '{bare_domain}' có quá nhiều tên miền phụ (subdomain).")
        score += 1

    # 7. Kiểm tra giả dạng thương hiệu (Lookalike / Typosquatting)
    # Tách phần tên miền chính (bỏ TLD cuối) để so sánh
    domain_without_tld = ".".join(parts[:-1]) if len(parts) >= 2 else bare_domain
    norm_domain = _normalize_for_brand_check(domain_without_tld)
    domain_tokens = [
        _normalize_for_brand_check(tok)
        for tok in re.split(r"[.\-_]", domain_without_tld)
        if tok
    ]

    impersonated_brand: str | None = None
    for brand, official_domains in BRAND_OFFICIAL_DOMAINS.items():
        if _is_official_domain(bare_domain, official_domains):
            impersonated_brand = None
            flags.append("official_domain")
            findings.append(f"Tên miền '{bare_domain}' khớp với tên miền chính thức của {brand}.")
            score = max(0, score - 2)
            break

        # Khớp trực tiếp sau khi chuẩn hóa homoglyph (vd: vietc0mbank -> vietcombank)
        if len(brand) >= 4 and brand in norm_domain:
            impersonated_brand = brand
            break
        # Với thương hiệu ngắn (3 ký tự như vcb, evn, acb, ghn), yêu cầu khớp nguyên token
        if len(brand) == 3 and brand in domain_tokens:
            impersonated_brand = brand
            break
        # Kiểm tra lỗi chính tả gần đúng (Levenshtein <= 2) cho thương hiệu dài >= 6 ký tự
        if len(brand) >= 6:
            for tok in domain_tokens:
                if abs(len(tok) - len(brand)) <= 2 and _levenshtein(tok, brand) <= 2:
                    impersonated_brand = brand
                    break
            if impersonated_brand:
                break

    if impersonated_brand:
        flags.append("brand_impersonation")
        findings.append(
            f"Tên miền '{bare_domain}' có dấu hiệu giả dạng thương hiệu '{impersonated_brand}' "
            f"(không phải tên miền chính thức)."
        )
        score += 3

    # 8. Kiểm tra từ khóa phishing trong đường dẫn (nếu không phải domain chính thức)
    if "official_domain" not in flags:
        matched_path_kw = [kw for kw in PHISHING_PATH_KEYWORDS if kw in path_and_query]
        if matched_path_kw:
            flags.append("suspicious_path")
            findings.append(
                f"Đường dẫn chứa từ khóa nhạy cảm ({', '.join(matched_path_kw[:3])}) trên tên miền không chính thức."
            )
            score += 1

    # Xếp mức rủi ro
    if score >= 3:
        risk_level = "high"
    elif score >= 1:
        risk_level = "medium"
    else:
        risk_level = "low"
        if not findings:
            findings.append(f"Chưa phát hiện dấu hiệu bất thường rõ ràng trên chuỗi URL '{bare_domain}'.")

    return {
        "url": cleaned,
        "domain": bare_domain,
        "risk_level": risk_level,
        "risk_score": score,
        "flags": flags,
        "findings": findings,
    }


def analyze_urls(urls: list[str]) -> list[dict[str, Any]]:
    """Phân tích danh sách URL."""
    return [analyze_url(url) for url in urls]
