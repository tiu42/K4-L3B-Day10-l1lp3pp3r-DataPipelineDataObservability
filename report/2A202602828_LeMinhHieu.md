# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Lê Minh Hiếu               |
| MSSV               | 2A202602828                |
| Khóa/Lớp         | K4                         |
| Tên nhóm         | l1lp3pp3r (nhóm 1 người) |
| Vai trò chính    | Toàn bộ 4 vai trò: Pipeline Integrator, Data Foundation & Recovery, RAG & Vector Index, Observability & Evaluation |
| Repository         | https://github.com/tiu42/K4-L3B-Day10-l1lp3pp3r-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ---------- |
| Raw ingestion | `src/ingestion/crossref.py`: `parse_crossref_payload`, `fetch_source_records`, `load_raw_records` | Crossref `/works` API hoặc snapshot `data/raw/crossref_response.json` | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Hoàn thành |
| Cleaning & modeling | `src/ingestion/cleaning.py`: `build_clean_dataframe`, `build_text_for_embedding` | `list[PaperRecord]`, `run_date` | `data/clean/papers_clean.csv/.json` (24 dòng) | Hoàn thành |
| Quality gate & freshness | `src/observability/quality.py`: `run_data_quality_checks`, `evaluate_freshness_sla`, `build_freshness_report` | Clean dataframe | `data/quality/*_quality_report.json`, `*freshness_report.json` | Hoàn thành |
| Evaluation set | `src/evaluation/testset.py`: `build_test_set` | Clean dataframe | `data/eval/test_set.json` (10 câu) | Hoàn thành |
| Corruption suite | `src/ingestion/corruption.py`: `corrupt_clean_dataframe` | Clean dataframe | `data/clean/papers_clean_corrupted.*`, `data/results/corruption_log.json` | Hoàn thành |
| Orchestration & reporting | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` (`repair_from_raw_snapshot`), `src/observability/reporting.py` | Tất cả module trên | `data/results/*_metrics.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |

Nhóm chỉ có một thành viên nên tôi sở hữu toàn bộ luồng. Các module retrieval (`retrieval/index.py`, `qa.py`, `embeddings.py`) và `evaluation/metrics.py` có sẵn trong starter; tôi tích hợp chúng và điều chỉnh contract dữ liệu (tên cột, mẫu câu hỏi) cho khớp.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Ingest Crossref có retry + fallback snapshot | `src/ingestion/crossref.py` | 24 raw records | Lệnh CP0: in `Đã tải 24 bài báo` |
| Làm sạch, `age_days`, `text_for_embedding`, dedupe | `src/ingestion/cleaning.py` | 24 dòng sạch, `paper_id` unique | Lệnh CP1: in `Clean thành công 24 dòng`; thử nhân bản 3 record vẫn ra 24 dòng |
| Quality gate GX 1.x + Freshness SLA | `src/observability/quality.py` | `baseline_quality_report.json` success = True | Lệnh CP1: `Quality check status = True` |
| Test set 10 câu / 4 dạng | `src/evaluation/testset.py` | 3 summary, 3 authors, 2 date, 2 categories, 10 DOI khác nhau | Lệnh CP2: `Sinh được 10 câu hỏi test` |
| Pipeline baseline | `src/pipelines/phase1.py` | `baseline_metrics.json`, `phase1_report.md` | `python script/run_phase1.py` exit 0 |
| Corruption + repair + đối chiếu | `src/ingestion/corruption.py`, `src/pipelines/corruption_flow.py` | `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_report.md` | `python script/run_corruption_flow.py` exit 0, in bảng 3 cột |

Output cụ thể: `data/reports/corruption_report.md` cho thấy `mean_token_f1` giảm từ 1.00 (baseline) xuống 0.69 (corrupted) và phục hồi 100% về 1.00 (repaired). Quality gate chuyển FAIL (6 dòng trùng `paper_id`, 3 dòng `summary` quá ngắn) rồi PASS lại sau repair.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Xây dựng pipeline đưa metadata bài báo từ Crossref vào vector index cho RAG agent. Pipeline phải phát hiện được dữ liệu hỏng trước khi phục vụ. Nó cũng phải đo được tác động của dữ liệu hỏng lên chất lượng câu trả lời, và phục hồi về trạng thái tốt một cách có thể lặp lại.

### Cách triển khai

- **Ingestion:** gọi `https://api.crossref.org/works` với `query`, `filter`, `rows` từ settings. Khi gặp 429/5xx hoặc lỗi mạng thì thử lại tối đa 4 lần với backoff lũy thừa và tôn trọng header `Retry-After`. Mặc định pipeline đọc snapshot. Nó chỉ gọi API live khi `REFRESH_SOURCE=1` hoặc chưa có snapshot, và tự fallback về snapshot khi API lỗi. Parser bỏ tag JATS, dựng tên tác giả từ `given` + `family`, lấy ngày từ `date-parts`, và loại record thiếu DOI/title/abstract.
- **Cleaning:** chuẩn hóa text, tính `age_days = (run_date - published).days`. Pipeline tạo `authors_joined`, `categories_joined`, `summary_chars`, và `text_for_embedding` gồm 5 phần (Title, Authors, Categories, Published, Summary). Dedupe theo `paper_id` giữ bản `updated` mới nhất, rồi sắp theo ngày xuất bản.
- **Quality gate:** dùng Ephemeral Context của GX 1.x với 4 expectation bắt buộc: row count 5–5000, not-null `paper_id`/`title`/`text_for_embedding`, unique `paper_id`, `summary` ≥ 30 ký tự. Freshness được tính riêng: nếu tỉ lệ bài có `age_days > 180` vượt 25% thì `is_fresh = False`.
- **Test set:** chọn 10 bài trải đều theo `paper_id` sắp xếp nên kết quả ổn định. Mẫu câu hỏi chứa đúng keyword mà `retrieval/qa.py` dùng để định tuyến câu trả lời, và đặt title trong `'...'` để `qa.py` tra cứu chính xác bài báo.
- **Corruption:** tiêm 6 dạng lỗi lên các nhóm dòng tách biệt với `seed=42`. Các lỗi gồm: bỏ 20% bài mới nhất, xóa trắng summary, chèn chuỗi rác, cắt title còn 7 ký tự, lùi ngày 365 ngày, nhân đôi dòng. Sau đó `summary_chars` và `text_for_embedding` được dựng lại. Mỗi thay đổi được ghi `before`/`after` vào log.
- **Orchestration:** Phase 1 đặt quality gate **trước** bước index và dừng pipeline nếu fail. Luồng corruption cố ý chỉ **quan sát** gate trên dữ liệu bẩn để đo Silent Failure. Sau đó repair dựng lại dữ liệu từ `crossref_records.json`, và lần này gate bắt buộc phải pass mới được index.

### Input, output và contract

| Thành phần | Mô tả |
| ------------------------------ | ------------------------------------------- |
| Input | Crossref `/works` JSON (`message.items[]`); `Settings` (`source_query`, `source_filter`, `max_results`, `freshness_threshold_days`) |
| Output | Dataframe sạch với các cột `paper_id, title, summary, authors, categories, primary_category, published, updated, abs_url, pdf_url, comment, authors_joined, categories_joined, summary_chars, age_days, text_for_embedding`; các metrics/report JSON và markdown |
| Module phụ thuộc | `core/config.py`, `core/utils.py`, `retrieval/index.py`, `retrieval/qa.py`, `evaluation/metrics.py` |
| Module sử dụng output | `retrieval/index.py` đọc `text_for_embedding` và metadata; `retrieval/qa.py` đọc `authors_joined`, `published`, `categories_joined`, `summary` |
| Điều kiện lỗi cần xử lý | API 429/503/mất mạng (fallback snapshot); record thiếu DOI/title/abstract; ngày không parse được; `paper_id` trùng; title chứa dấu `'` (loại khỏi test set vì làm hỏng regex của `qa.py`); LLM judge lỗi (fallback heuristic trong `metrics.py`) |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Phase 1 in hit rate và token F1 của baseline, quality = True. Phase 2 in bảng 3 cột, trong đó corrupted giảm và repaired phục hồi.
- **Kết quả thực tế:** `Phase 1 done: 24 clean rows, hit_rate=1.00, token_f1=1.000, quality=True, is_fresh=True`. Phase 2 cho corrupted `token_f1=0.6914`, `judge_accuracy=0.70`, `hit_rate=0.90`. Repaired trở về 1.00 ở mọi metric. Quality gate: corrupted = FAIL, repaired = PASS.
- **Artifact/log:** `data/results/baseline_metrics.json`, `data/results/corrupted_metrics.json`, `data/results/repaired_metrics.json`, `data/results/corruption_log.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `fetch_source_records` có thể luôn gọi API Crossref live, hoặc ưu tiên snapshot đã commit trong `data/raw/`.
- **Các phương án đã cân nhắc:**
  1. Luôn gọi API live, chỉ fallback về snapshot khi lỗi.
  2. Mặc định đọc snapshot, chỉ gọi live khi `REFRESH_SOURCE=1` (cờ có sẵn trong `core/config.py`) hoặc khi chưa có snapshot. Nếu gọi live bị lỗi thì vẫn fallback.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Ưu tiên khả năng tái lập (reproducibility) và data lineage. Gọi live sẽ ghi đè snapshot bằng một corpus khác mỗi lần chạy, làm test set, metrics và báo cáo không còn so sánh được giữa các lần chạy. Nó cũng phụ thuộc vào rate limit của API bên ngoài.
- **Bằng chứng quyết định phù hợp:** Khi thử gọi live (ghi vào thư mục tạm), API trả về 24 bài hoàn toàn khác snapshot. Bài đầu tiên là một bài tiếng Nga về ngành sữa, `10.47576/2949-1894.2026.7.7.023`. Nếu ghi đè, `test_set.json` sẽ trỏ tới các DOI không còn trong index. Với snapshot, lệnh CP0 luôn ghi lại `crossref_records.json` giống hệt bản đã commit (`git status` không đổi).

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Lần chạy `python script/run_phase1.py` đầu tiên vẫn exit 0 và báo `judge_accuracy = 1.0`. Tuy nhiên log có 10 dòng `POST .../models/gemini-2.5-flash:generateContent "HTTP/1.1 404 Not Found"`, và mọi câu trong `baseline_answers.json` có `reasoning = "Fallback heuristic judge used because the LLM evaluator was unavailable."`.
- **Lệnh hoặc bước tái hiện:** Đặt `LLM_MODEL=gemini-2.5-flash` trong `.env` rồi chạy `python script/run_phase1.py`.
- **Nguyên nhân gốc:** Model `gemini-2.5-flash` không còn khả dụng trên Gemini API. `evaluation/metrics.py::_judge_answer` bắt mọi exception và âm thầm chuyển sang heuristic dựa trên token F1. Pipeline vì vậy không fail, nhưng các cột judge không còn là điểm do LLM chấm. Đây chính là một dạng Silent Failure ở tầng evaluation.
- **Cách xử lý:** Đổi `LLM_MODEL=gemini-3.6-flash` trong `.env` rồi chạy lại pipeline.
- **Cách xác minh sau khi sửa:** Log xuất hiện `HTTP/1.1 200 OK`, và 9/10 câu baseline có `reasoning` do LLM viết, ví dụ "The model answer is identical to the reference answer.".
- **Điều học được:** Một cơ chế fallback "an toàn" có thể che giấu lỗi. Cần kiểm tra artifact (trường `reasoning`) chứ không chỉ dựa vào exit code và con số tổng.

Vấn đề còn tồn đọng:

- **Phạm vi bị ảnh hưởng:** Gói miễn phí của Gemini giới hạn 5 request/phút (`429 RESOURCE_EXHAUSTED`). Hậu quả là 1/10 câu baseline và 8/10 câu repaired vẫn bị chấm bằng heuristic.
- **Những gì đã loại trừ:** Các câu này có token F1 = 1.0 nên heuristic cũng cho điểm 5. Kết luận về xu hướng metric không bị ảnh hưởng. Lượt corrupted có 10/10 câu được LLM chấm.
- **Bước tiếp theo:** Thêm khoảng nghỉ giữa các lượt đánh giá hoặc dùng quota trả phí. Sau đó xác minh bằng cách đếm số câu có `Fallback` trong `*_answers.json`, mục tiêu là 0.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Từ Crossref đến vector index:** payload Crossref (hoặc snapshot) được lưu nguyên vào `crossref_response.json`, parse thành `PaperRecord` và lưu vào `crossref_records.json`. Hai file raw này là nguồn lineage. Sau đó dữ liệu được clean thành dataframe có `text_for_embedding` và đi qua quality gate GX. Chỉ khi gate pass, `LocalEmbeddingIndex.build` mới embed bằng `all-MiniLM-L6-v2` và ghi vào collection ChromaDB `papers-baseline`, kèm metadata cho QA.
2. **Evaluation set và ground-truth doc IDs:** mỗi câu hỏi có `ground_truth_doc_ids` là DOI của bài gốc. `retrieval_hit_rate` đo xem DOI đó có nằm trong top-k tài liệu truy xuất không (chất lượng retrieval). `ground_truth` là câu trả lời chuẩn, được so với câu trả lời bằng token F1 và bằng LLM judge (chất lượng answer).
3. **Quality checks khác freshness:** quality checks (GX) kiểm tra tính đúng về cấu trúc và nội dung của từng dòng hoặc bảng, như số dòng, null, trùng khóa, độ dài summary. Kết quả là pass/fail và dùng để chặn dữ liệu. Freshness đo tuổi dữ liệu so với thời điểm chạy (`age_days`, tỉ lệ bài cũ hơn 180 ngày). Nó là tín hiệu cảnh báo về độ mới, không phải lỗi định dạng. Dữ liệu có thể hoàn toàn hợp lệ nhưng đã cũ.
4. **Cùng một test set cho 3 trạng thái:** để biến duy nhất thay đổi là dữ liệu trong index. Nếu đổi câu hỏi, chênh lệch metric có thể đến từ độ khó câu hỏi thay vì từ corruption hay repair.
5. **Tiêu chí repair thành công:** `data/quality/repaired_quality_report.json` có `success = true`, `repaired_freshness_report.json` quay về `stale_rows = 1/24`, và `data/results/repaired_metrics.json` trở về bằng baseline (`retrieval_hit_rate = 1.0`, `mean_token_f1 = 1.0`). Tất cả được tổng hợp trong `data/reports/corruption_report.md`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` | 1.00 | 0.90 | 1.00 | Chỉ giảm 0.10 vì hit@4 khá "dễ tính": chỉ bài bị drop (`eval_004`) mới mất hẳn khỏi top-4 |
| `mean_token_f1` | 1.00 | 0.69 | 1.00 | Giảm mạnh nhất; do summary trống (F1 = 0 ở 2 câu), ngày bị lùi (F1 = 0) và chuỗi rác (F1 = 0.91) |
| `judge_accuracy` | 1.00 | 0.70 | 1.00 | 3 câu sai rõ ràng (summary trống ×2, ngày sai) bị LLM judge chấm 1 điểm |
| `mean_judge_score` | 5.0 | 3.6 | 5.0 | Câu có chuỗi rác được chấm 3: đúng nội dung nhưng bẩn |
| Quality checks | PASS | FAIL (unique `paper_id`: 6 dòng; `summary` < 30 ký tự: 3 dòng) | PASS | Gate bắt được duplicate và blank summary, nhưng không bắt được title bị cắt hay ngày bị lùi |
| Freshness status | `is_fresh = True` (1/24 = 4.2%) | `is_fresh = True` (5/22 = 22.7%) | `is_fresh = True` (1/24 = 4.2%) | Stale ratio tăng gấp ~5 lần nhưng vẫn dưới ngưỡng 25%, nên SLA không cảnh báo |

### Kết luận từ số liệu

1. **Corruption:** blank summary, lùi ngày, chuỗi rác, trùng dòng, drop bài mới nhất → GX FAIL ở `expect_column_values_to_be_unique(paper_id)` và `expect_column_value_lengths_to_be_between(summary)`, stale ratio tăng từ 4.2% lên 22.7% → `mean_token_f1` giảm từ 1.00 xuống 0.69, `judge_accuracy` từ 1.00 xuống 0.70, hit rate từ 1.00 xuống 0.90. Trong suốt quá trình không có lỗi runtime nào: đó là Silent Failure.
2. **Repair:** `repair_from_raw_snapshot` dựng lại từ `crossref_records.json` → GX PASS, stale ratio về 4.2% → mọi metric phục hồi 100% về baseline.

**Corruption ảnh hưởng rõ nhất và vì sao:** `blank_summary` và `stale_date`. Hai lỗi này làm câu trả lời sai hoàn toàn (F1 = 0) dù retrieval vẫn trúng đúng tài liệu: `eval_001`, `eval_005`, `eval_007` đều có `retrieval_hit = True`. Lỗi nằm ở nội dung được trả lời chứ không ở khâu tìm kiếm. Vì vậy chỉ theo dõi retrieval hit rate sẽ bỏ sót phần lớn thiệt hại.

**Kết quả khác với kỳ vọng ban đầu:**

- **Title bị cắt không làm giảm metric.** Tôi kỳ vọng `eval_002`, `eval_006` sẽ sai vì exact lookup theo title thất bại. Thực tế top-1 chuyển sang một bài khác (`...3671815` thay vì `...3671803`), nhưng câu trả lời vẫn đúng vì corpus có các bài "extended study" cùng tác giả. Tôi kiểm tra bằng cách so `retrieved_doc_ids[0]` với `ground_truth_doc_ids` trong `corrupted_answers.json`. Đây là trường hợp metric answer che giấu suy giảm ranking.
- **`eval_004` đúng dù bài gốc đã bị drop.** Câu trả lời trùng categories với một bài khác. Cũng là "đúng do trùng hợp".
- **Baseline đạt 1.00 ở mọi metric.** Nguyên nhân là câu hỏi chứa đúng title nên `qa.py` tra cứu chính xác, khiến baseline là cận trên chứ không phản ánh retrieval ngữ nghĩa thuần.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Lưu raw snapshot bất biến trước mọi biến đổi là điều kiện để repair idempotent. Repair chỉ đơn giản là chạy lại cleaning từ raw, cho cùng kết quả mỗi lần.
2. **Về data quality/observability:** Quality gate chỉ bắt được những gì được định nghĩa. 4 expectation bắt buộc bỏ sót title bị cắt và ngày bị lùi, và ngưỡng freshness 25% không cảnh báo khi stale ratio tăng gấp 5 lần. Cần thêm expectation theo đúng các failure mode đã biết.
3. **Về ảnh hưởng của data đến RAG agent:** Dữ liệu hỏng không gây lỗi mà sinh ra câu trả lời sai một cách "tự tin" (chuỗi rỗng, ngày lệch đúng 365 ngày). Chỉ có evaluation với ground truth mới làm lộ ra điều này.

### Nếu có thêm thời gian

Thêm expectation `ExpectColumnValueLengthsToBeBetween(title, min_value=15)` và một kiểm tra so sánh với lần chạy trước. Kiểm tra đó sẽ cảnh báo khi `latest_published` lùi lại hoặc stale ratio tăng quá X điểm phần trăm so với baseline. Cách đo cải thiện: chạy lại `run_corruption_flow.py` và kiểm tra `corrupted_quality_report.json` có thêm expectation FAIL cho `truncate_title` và `stale_date`. Mục tiêu là cả 6 dạng corruption đều bị ít nhất một tín hiệu phát hiện, thay vì 2/6 như hiện tại (duplicate, blank summary).

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lê Minh Hiếu
**Ngày xác nhận:** 2026-09-26
