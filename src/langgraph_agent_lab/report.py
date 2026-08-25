"""Report generation helper using the lab report template."""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data.

    Generate a report that includes:
    1. Metrics summary table (total scenarios, success rate, retries, interrupts)
    2. Per-scenario results table
    3. Architecture explanation (your graph design, state schema, reducers)
    4. Failure analysis (at least two failure modes you considered)
    5. Improvement plan

    Use reports/lab_report_template.md as your guide.

    Return: formatted markdown string
    """
    rows = "\n".join(
        f"| {item.scenario_id} | {item.expected_route} | {item.actual_route or '-'} | "
        f"{'Có' if item.success else 'Không'} | {item.retry_count} | "
        f"{item.interrupt_count} | {item.latency_ms} |"
        for item in metrics.scenario_metrics
    )
    replay = "Có" if metrics.resume_success else "Không"
    return f"""# Báo cáo bài lab Day 08

## 1. Nhóm / sinh viên

| Thành viên | Họ và tên | Mã sinh viên | Công việc được phân công |
|---:|---|---|---|
| 1 | Phạm Tiến Anh | 2A202601549 | Typed state, reducer và tích hợp LLM/OpenAI |
| 2 | Hà Nhật Khánh Duy | 2A202602031 | Các workflow node và xử lý retry/approval |
| 3 | Phó Viết Tiến Anh | 2A202601341 | Conditional routing và nối StateGraph |
| 4 | Ngô Quang Dũng | 2A202601819 | Persistence, checkpointer và CLI runner |
| 5 | Lâm Việt Hoàng | 2A202601067 | Metrics, scenario loader và báo cáo |

- Repository/commit: https://github.com/photienanh/Track3-DAY23-Cloud
- Ngày thực hiện: 25/08/2026

## 2. Kiến trúc

Graph gồm mười một node có trách nhiệm tách biệt. Luồng `START → intake → classify` được nối với
các nhánh điều kiện. Ticket đơn giản đi tới `answer`; yêu cầu tra cứu đi qua `tool → evaluate`;
ticket thiếu thông tin đi tới `clarify`; hành động có side effect đi qua
`risky_action → approval` trước khi gọi tool; lỗi hệ thống đi vào cổng retry có giới hạn. Graph chỉ
retry khi `attempt < max_attempts`. Yêu cầu đã hết lượt thử được chuyển tới `dead_letter`. Mọi nhánh
kết thúc đều đi qua `finalize → END` và để lại audit event.

Node phân loại dùng structured output của LLM với thứ tự ưu tiên `risky > tool > missing_info >
error > simple`. Câu trả lời được LLM sinh dựa trên query, kết quả tool, hành động đề xuất và quyết
định phê duyệt. Lỗi provider được ghi nhận rõ ràng thay vì bị che giấu.

## 3. Lược đồ state

| Trường | Reducer | Lý do |
|---|---|---|
| `messages` | append | Giữ lịch sử hội thoại và tóm tắt audit |
| `tool_results` | append | Giữ kết quả của mọi lần gọi tool |
| `errors` | append | Giữ lịch sử lỗi và retry |
| `events` | append | Bằng chứng audit chuẩn hóa theo từng node |
| `thread_id`, `scenario_id`, `query` | overwrite | Một định danh/input hiện tại cho mỗi run |
| `route`, `risk_level` | overwrite | Kết quả phân loại hiện tại; route ổn định cho metrics |
| `attempt`, `max_attempts` | overwrite | Bộ đếm hiện tại và giới hạn của run |
| `evaluation_result` | overwrite | Kết luận mới nhất của cổng đánh giá chất lượng |
| `pending_question`, `proposed_action`, `approval` | overwrite | Quyết định workflow hiện tại |
| `final_answer` | overwrite | Kết quả hiện tại trả cho người dùng |

## 4. Kết quả scenario

| Chỉ số | Giá trị |
|---|---:|
| Tổng số scenario | {metrics.total_scenarios} |
| Tỷ lệ thành công | {metrics.success_rate:.2%} |
| Số node event trung bình | {metrics.avg_nodes_visited:.2f} |
| Tổng số lần retry | {metrics.total_retries} |
| Số lần đi qua approval | {metrics.total_interrupts} |
| Đã xác minh đọc lại state history | {replay} |

| Scenario | Route kỳ vọng | Route thực tế | Thành công | Retry | Lần qua approval | Độ trễ (ms) |
|---|---|---|---:|---:|---:|---:|
{rows}

Số lần qua approval được tính từ event của node `approval`; mock reviewer mặc định không đồng nghĩa
workflow đã thật sự tạm dừng. Độ trễ được đo quanh mỗi lần gọi graph.

## 5. Phân tích lỗi

1. **Tool gặp lỗi tạm thời.** Tool append một kết quả `ERROR`; `evaluate` kiểm tra kết quả mới nhất
   và phát `needs_retry`. Chỉ node `retry` tăng bộ đếm. Khi `attempt >= max_attempts`, graph đóng an
   toàn qua `dead_letter → finalize`. Bản production vẫn cần lỗi có kiểu, timeout, idempotency key
   và exponential backoff.
2. **Hành động rủi ro chưa được duyệt.** `risky_action` chỉ chuẩn bị đề xuất. Approval luôn đứng
   trước tool; quyết định từ chối được chuyển tới `clarify`, đồng thời tool kiểm tra approval thêm
   một lần để phòng vệ. Bản production vẫn cần xác thực reviewer, policy phân quyền, thời hạn quyết
   định và kho audit bất biến.
3. **LLM/provider gặp lỗi.** Node phân loại và trả lời append loại lỗi không chứa secret cùng
   fallback audit event. Workflow vẫn kết thúc được và có thể quan sát, nhưng fallback classifier
   có độ bao phủ ngữ nghĩa thấp hơn nên cần kích hoạt cảnh báo vận hành.

## 6. Bằng chứng persistence / recovery

Mỗi scenario nhận một `thread_id` ổn định và được truyền dưới dạng `configurable.thread_id`. Runner
xác minh `get_state_history()` trên cùng thread sau khi chạy và chỉ đặt `resume_success` khi mọi run
đều trả về history. MemorySaver chứng minh khả năng replay trong cùng process. Khi được cấu hình,
SQLite adapter sử dụng thêm `SqliteSaver` và WAL mode để lưu checkpoint bền vững.
Kiểm thử persistence ghi checkpoint, đóng connection, mở lại database và xác nhận state cùng
history vẫn đọc được.

## 7. Phần mở rộng đã thực hiện

- SQLite checkpointer adapter với WAL mode và kiểm thử recovery sau khi mở lại database.
- HITL thật tùy chọn qua `LANGGRAPH_INTERRUPT=true`; mock approval vẫn là mặc định cho CI.
- Đo độ trễ runtime và xác minh state-history metrics.
- Cơ chế xử lý lỗi LLM có thể kiểm toán.

## 8. Kế hoạch cải tiến

Ưu tiên đầu tiên là thay mock tool và reviewer bằng service call có xác thực, idempotency và cơ chế
phê duyệt bền vững. Sau đó bổ sung backoff policy có kiểu, tracing/cost budget, che dữ liệu PII,
hiệu chỉnh evaluator và kiểm thử recovery qua nhiều process.
"""


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
