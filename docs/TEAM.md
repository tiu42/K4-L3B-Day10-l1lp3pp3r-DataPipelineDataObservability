# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `l1lp3pp3r`
- **Mã Nhóm / Lớp:** `K4-L3-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3B-Day10-l1lp3pp3r-DataPipelineDataObservability` (https://github.com/tiu42/K4-L3B-Day10-l1lp3pp3r-DataPipelineDataObservability)

---

## # Thành viên

Nhóm có **1 thành viên**, đảm nhận toàn bộ 4 vai trò.

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Lê Minh Hiếu | 2A202602828 | hieu04022004@gmail.com | Trưởng nhóm / Pipeline Integrator (`phase1.py`, `corruption_flow.py`); Data Foundation & Recovery (`crossref.py`, `cleaning.py`, `corruption.py`, raw data); RAG & Vector Index (ChromaDB 3 collection); Observability & Evaluation (`quality.py` GX 1.x, `testset.py`, `reporting.py`) | `report/2A202602828_LeMinhHieu.md` |

---

## # Tỷ lệ đóng góp (% Contribution)

| Thành viên | MSSV | Phạm vi | % Contribution | Xác nhận |
|---|---|---|---:|---|
| Lê Minh Hiếu | 2A202602828 | Toàn bộ pipeline (ingestion, cleaning, quality gate, testset, evaluation, corruption, repair, reporting) | 100% | Đã xác nhận (nhóm 1 người) |

---

## # Cá nhân

### ## LeMinhHieu-2A202602828
- **Vai trò:** Thành viên duy nhất, đảm nhận cả 4 vai trò: điều phối pipeline, ingestion & phục hồi dữ liệu, RAG & vector index, observability & evaluation.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/crossref.py`: parse payload Crossref, fetch API có retry cho 429/5xx và fallback đọc snapshot local, `load_raw_records`.
  - `src/ingestion/cleaning.py`: làm sạch text (JATS tag, whitespace), tính `age_days`, sinh `text_for_embedding` 5 phần, khử trùng lặp theo `paper_id`.
  - `src/observability/quality.py`: Quality Gate với Great Expectations 1.x (Ephemeral Context, 4 expectation bắt buộc) và Freshness SLA (`age_days > 180` vượt 25% ⇒ `is_fresh = False`).
  - `src/evaluation/testset.py`: bộ 10 câu hỏi ground truth trải đều 4 dạng `summary`/`authors`/`date`/`categories`.
  - `src/ingestion/corruption.py`: 6 kịch bản làm bẩn dữ liệu có seed cố định và nhật ký `corruption_log.json`.
  - `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `src/observability/reporting.py`: xâu chuỗi pipeline baseline, luồng corrupt → repair idempotent từ raw snapshot → đối chiếu 3 trạng thái, xuất báo cáo markdown.
  - Quản lý 3 collection ChromaDB tách biệt (`papers-baseline`, `papers-corrupted`, `papers-repaired`).
- **Điều học được / Đóng góp chính:**
  - Dữ liệu hỏng không gây lỗi runtime (Silent Failure); chỉ quality gate và metric đánh giá mới làm lộ ra vấn đề, nên cần đặt quality gate trước khi dữ liệu vào vector DB.
  - Repair an toàn phải dựa trên raw snapshot bất biến để có thể chạy lại nhiều lần cho cùng kết quả.
