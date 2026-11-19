"""Script đánh giá Agent trên bộ 20 kịch bản kiểm thử (Mục 7 – Test scenario).

Chức năng:
- Chạy toàn bộ kịch bản trong data/test_messages.json qua ScamGuardAgent.
- Xuất bảng chi tiết (Pass/Fail) ra CSV để dán trực tiếp vào Google Sheet/Excel của Tester.
- Tự động tính Confusion Matrix, Precision, Recall cho 3 nhãn (Lừa đảo, An toàn, Đáng ngờ)
  và lưu tóm tắt ra reports/evaluation_summary.md.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.core import ScamGuardAgent

LABELS = ["Lừa đảo", "An toàn", "Đáng ngờ"]
DATA_PATH = ROOT_DIR / "data" / "test_messages.json"
REPORTS_DIR = ROOT_DIR / "reports"
CSV_PATH = REPORTS_DIR / "test_scenario_results.csv"
SUMMARY_PATH = REPORTS_DIR / "evaluation_summary.md"


def compute_metrics(rows: list[dict]) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, float]]]:
    """Tính Confusion Matrix và Precision/Recall/F1 cho từng nhãn."""
    matrix: dict[str, dict[str, int]] = {
        actual: {pred: 0 for pred in LABELS} for actual in LABELS
    }
    for row in rows:
        actual = row["expected_label"]
        pred = row["predicted_label"]
        if actual in matrix and pred in matrix[actual]:
            matrix[actual][pred] += 1

    metrics: dict[str, dict[str, float]] = {}
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[other][label] for other in LABELS if other != label)
        fn = sum(matrix[label][other] for other in LABELS if other != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        metrics[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return matrix, metrics


def main() -> None:
    if not DATA_PATH.exists():
        print(f"Không tìm thấy file kịch bản tại: {DATA_PATH}")
        sys.exit(1)

    with DATA_PATH.open("r", encoding="utf-8") as f:
        scenarios = json.load(f)

    agent = ScamGuardAgent()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f"CHẠY ĐÁNH GIÁ {len(scenarios)} KỊCH BẢN KIỂM THỬ – SCAMGUARD VN")
    print(
        f"LLM configured: {agent.is_llm_configured} | "
        f"Provider: {agent.provider} | Model: {agent.model}"
    )
    print("=" * 72)

    results_rows: list[dict] = []
    for idx, item in enumerate(scenarios, start=1):
        started = time.perf_counter()
        out = agent.analyze(item["message"])
        elapsed = round(time.perf_counter() - started, 2)

        res = out["result"]
        predicted = res["label"]
        expected = item["expected_label"]
        passed = predicted == expected

        row = {
            "id": item["id"],
            "title": item["title"],
            "expected_label": expected,
            "predicted_label": predicted,
            "status": "Pass" if passed else "Fail",
            "confidence": res["confidence"],
            "rounds": out["rounds"],
            "used_fallback": out["used_fallback"],
            "latency_sec": elapsed,
            "follow_up_question": res.get("follow_up_question") or "",
            "reasons": " | ".join(res.get("reasons", [])),
        }
        results_rows.append(row)
        print(
            f"[{idx:02d}/{len(scenarios)}] {item['id']} | "
            f"Kỳ vọng: {expected:<8} | Dự đoán: {predicted:<8} | "
            f"{row['status']:<4} ({elapsed:.2f}s)"
        )

    # Xuất CSV (UTF-8-SIG để mở tiếng Việt chuẩn trên Excel)
    fieldnames = [
        "id",
        "title",
        "expected_label",
        "predicted_label",
        "status",
        "confidence",
        "rounds",
        "used_fallback",
        "latency_sec",
        "follow_up_question",
        "reasons",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_rows)

    matrix, metrics = compute_metrics(results_rows)
    total = len(results_rows)
    passed_count = sum(1 for r in results_rows if r["status"] == "Pass")
    fallback_count = sum(1 for r in results_rows if r["used_fallback"])
    accuracy = round(passed_count / total, 4) if total else 0.0

    # Xuất báo cáo Markdown tổng hợp
    md_lines = [
        "# Báo cáo Đánh giá 20 Kịch bản Kiểm thử – ScamGuard VN",
        "",
        f"- **Tổng số kịch bản:** {total}",
        f"- **Pass:** {passed_count}/{total} (Accuracy: **{accuracy * 100:.1f}%**)",
        f"- **Số ca rơi vào Fallback (chưa có LLM):** {fallback_count}/{total}",
        f"- **Cấu hình LLM:** `{agent.provider}` / `{agent.model}` (Configured: `{agent.is_llm_configured}`)",
        "",
        "> **Lưu ý:** Kết quả chỉ mang tính minh họa vì số lượng mẫu nhỏ (~20 kịch bản), không thay thế đánh giá quy mô lớn.",
        "",
        "## 1. Confusion Matrix (Hàng: Thực tế | Cột: Agent dự đoán)",
        "",
        "| Thực tế \\ Dự đoán | Lừa đảo | An toàn | Đáng ngờ |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for actual in LABELS:
        md_lines.append(
            f"| **{actual}** | {matrix[actual]['Lừa đảo']} | "
            f"{matrix[actual]['An toàn']} | {matrix[actual]['Đáng ngờ']} |"
        )

    md_lines.extend(
        [
            "",
            "## 2. Precision, Recall, F1 theo từng nhãn",
            "",
            "| Nhãn | TP | FP | FN | Precision | Recall | F1 |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for label in LABELS:
        m = metrics[label]
        md_lines.append(
            f"| **{label}** | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{m['precision']:.2%} | {m['recall']:.2%} | {m['f1']:.2%} |"
        )

    md_lines.extend(
        [
            "",
            "## 3. Chi tiết từng kịch bản",
            "",
            "| ID | Mô tả | Kỳ vọng | Dự đoán | Kết quả | Độ tự tin |",
            "| :--- | :--- | :---: | :---: | :---: | :---: |",
        ]
    )
    for r in results_rows:
        md_lines.append(
            f"| {r['id']} | {r['title']} | {r['expected_label']} | "
            f"{r['predicted_label']} | **{r['status']}** | {r['confidence']:.2f} |"
        )

    SUMMARY_PATH.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"Hoàn tất! Pass: {passed_count}/{total} ({accuracy * 100:.1f}%)")
    print(f"- File CSV cho Tester: {CSV_PATH}")
    print(f"- Báo cáo tổng hợp:    {SUMMARY_PATH}")
    print("=" * 72)


if __name__ == "__main__":
    main()
