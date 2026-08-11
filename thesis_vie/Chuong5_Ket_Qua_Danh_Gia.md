# CHƯƠNG 5: KẾT QUẢ VÀ ĐÁNH GIÁ

Chương này báo cáo số liệu đo trên phần cứng thực tế và đánh giá bác sĩ. Câu hỏi trung tâm: hệ có đạt tiêu chí mục 5.0 (đặt trước khi cài đặt) hay không. Không lặp lại mô tả kiến trúc ở Chương 3–4.

## 5.0 Tiêu chí thành công định trước

Trước khi cài đặt, nghiên cứu đặt mục tiêu để đối chiếu kết quả Phần II. Thành công trên các claim chính nếu hệ đạt các tiêu chí sau, được đánh giá ở các mục dưới.

Độ chính xác khuyến nghị so với chuyên gia khớp guideline ≥ 90% trên đối tượng có cấu trúc, trên vignette bác sĩ tim mạch duyệt. Thời gian đáp ứng end-to-end trung bình dưới 10 giây trên phần cứng tham chiếu. Với chống chỉ định cứng trong ca an toàn biên soạn, hệ không được bỏ sót rule tránh tuyệt đối dạng hard_block. Mức hài lòng bác sĩ (Likert 5 điểm) trung bình ≥ 4,0. Giao diện Việt–Anh không mất ngữ cảnh khi đổi ngôn ngữ. Pipeline tự động hóa trích xuất nhóm thuốc GDMT chính vào catalog người duyệt được. Các tiêu chí kết hợp accuracy, an toàn, latency, bảo trì và usability theo tinh thần workflow Osheroff [17].

## 5.1 Môi trường thử nghiệm

### 5.1.1 Cấu hình phần cứng và phần mềm

Mọi lần chạy đánh giá đều dùng một máy chủ riêng với CPU 16 nhân, 32 GB RAM, ổ SSD 500 GB, và card đồ họa NVIDIA RTX 3080 với 10 GB bộ nhớ video. Hệ điều hành là Ubuntu 22.04 LTS. Stack ứng dụng gồm Python 3.11, PostgreSQL 15 cho quy tắc lâm sàng được quản trị, Redis 7 cho bộ nhớ đệm (cache), Neo4j 5 cho đồ thị tri thức, ChromaDB cho tìm kiếm vector, LocalStack làm kho đối tượng tương thích S3, và Ollama cho suy luận mô hình ngôn ngữ lớn (LLM) cục bộ.

Hệ thống dùng cùng cặp mô hình dự kiến cho môi trường sản xuất: BGE-M3 cho embedding và lọc mục, Qwen2.5-7B-Instruct cho câu trả lời hướng tới bác sĩ, và Qwen2.5-1.5B cho các tác vụ kiểm chứng nhẹ. Backend chạy dưới Docker Compose với worker bất đồng bộ FastAPI, truyền phản hồi chat bằng sự kiện đẩy từ server (SSE), và truy xuất GraphRAG lai kết hợp tìm kiếm vector dày, tìm kiếm từ khóa, và duyệt đồ thị trước khi hợp nhất kết quả.

Điều này quan trọng vì các con số báo cáo phản ánh toàn bộ hệ tích hợp, không phải benchmark từng module riêng lẻ. Độ trễ (latency) được đo trên toàn bộ đường chat. Độ chính xác được chấm trên đối tượng khuyến nghị có cấu trúc, không phải trên văn bản trả lời tự do. Các chỉ số tri thức đến từ các lần chạy pipeline đầy đủ trên toàn bộ manifest thuốc, không phải từ mẫu nhỏ chọn tay.

### 5.1.2 Dữ liệu đánh giá

Cơ sở tri thức kết hợp nhãn thuốc FDA, hướng dẫn điều trị (guideline) suy tim, và catalog quy tắc suy diễn. Manifest nguồn đăng ký 127 thuốc. Để đánh giá đầy đủ, 60 thuốc được tích hợp hoàn chỉnh qua trích xuất, phân loại, và đồng bộ cơ sở dữ liệu. Có tám guideline suy tim. Hệ thống còn giữ 6.032 quy tắc ràng buộc, 1.096 quy tắc tương tác, bốn chính sách GDMT, và 13 cảnh báo an toàn liều. Hoàn thiện quy tắc liều vẫn đang tiến hành tại thời điểm đánh giá, nên lập kế hoạch liều chưa đầy đủ bằng phạm vi ràng buộc và tương tác.

Khoảng cách giữa 127 thuốc đăng ký và 60 thuốc tích hợp đầy đủ phản ánh phạm vi pipeline vẫn đang mở rộng. Kiểm thử độ chính xác tập trung vào tập con 60 thuốc, nơi catalog ràng buộc và tương tác đủ hoàn chỉnh để suy luận tự động đáng tin cậy.

## 5.2 Kết quả xây dựng cơ sở tri thức

### 5.2.1 Trích xuất nhãn thuốc

Pipeline nạp dữ liệu tải nhãn thuốc từ DailyMed, phân tích các mục XML, lọc nội dung lâm sàng, cắt văn bản thành các đoạn (chunk), và trích xuất các khẳng định có cấu trúc. Trên 60 thuốc đã tích hợp, pipeline trích xuất 4.136 mục, trung bình khoảng 69 mục mỗi thuốc. Trích xuất thành công trên 94,2% thuốc, với thời gian xử lý trung bình khoảng 45 giây mỗi thuốc.

Độ dài nhãn khác nhau theo nhóm thuốc. Thuốc chẹn beta (beta blocker) đóng góp tổng số mục lớn nhất vì nhiều hoạt chất được xử lý. Nhãn ARNI thường dài hơn mỗi thuốc vì ngôn ngữ cảnh báo phong phú. Nhãn thuốc ức chế SGLT2 (SGLT2i) ngắn hơn trung bình sau lọc, phù hợp định dạng nhãn mới hơn.

Kết quả cho thấy nạp tự động có thể điền một cơ sở tri thức dùng được ở quy mô lớn mà không cần chép tay từng mục nhãn. Thất bại chủ yếu do không khớp tra cứu tên thuốc chưa có trong registry thu thập, điều báo trước vấn đề sau này với tên biệt dược tiếng Việt trong intake chat.

### 5.2.2 Lọc mục

Không phải mọi mục trong nhãn thuốc đều hữu ích lâm sàng. Một số phần mô tả bảo quản, đóng gói, hoặc chi tiết nhà sản xuất. Hệ thống vì vậy dùng bộ lọc ba bước: khớp từ khóa trước, độ tương đồng ngữ nghĩa (semantic similarity) thứ hai, và chỉ gọi LLM duyệt các trường hợp không chắc chắn.

Trên nhãn thuốc và guideline, 5.381 mục vào bước lọc. Bộ lọc giữ lại 95,0% mục. Khoảng 65,5% được chấp nhận chỉ bằng quy tắc từ khóa, 22,9% bằng embedding, và chỉ 6,6% cần duyệt LLM vùng biên (borderline). Chỉ 5,0% bị loại vì không phải nội dung lâm sàng.

Thiết kế này cố ý tiết kiệm chi phí. Cách ngây thơ gửi mọi mục cho LLM sẽ cần khoảng 5.381 lần gọi model mỗi chu kỳ nạp. Pipeline quan sát được chỉ cần 354 lần duyệt vùng biên, giảm hơn 93%. Tài liệu guideline cần duyệt vùng biên nhiều hơn nhãn FDA vì tiêu đề và cách diễn đạt guideline khác nhau hơn giữa các nhà xuất bản.

Nói đơn giản, bộ lọc giữ gần như toàn bộ nội dung lâm sàng liên quan trong khi tránh dùng model không cần thiết. Cân bằng đó quan trọng với bệnh viện phải làm mới cơ sở tri thức khi nhãn hoặc guideline thay đổi.

### 5.2.3 Phân loại quy tắc

Sau trích xuất, quy tắc được phân loại theo mức an toàn và hành động khuyến nghị. Trong 6.032 artifact liên quan ràng buộc, 53,9% dùng được ngay, 35,2% cần tinh chỉnh điều kiện trước triển khai, và 11,1% được xử lý như chặn cứng (hard block) biểu thị chống chỉ định tuyệt đối.

Theo loại hành động, 24,2% được phân loại "tránh" (avoid), 35,4% "cân nhắc thận trọng" (consider with caution), 27,8% "cân nhắc" (consider), và 12,7% "tiếp tục" (continue). Tỷ lệ lớn quy tắc mang tính thận trọng giúp giải thích vì sao hệ thống tạo nhiều cảnh báo trong đánh giá. Quy tắc chặn cứng đi thẳng vào hành vi an toàn fail-closed và không bao giờ bị văn bản sinh ra ghi đè.

Tầng tinh chỉnh 35,2% không có nghĩa thất bại lúc chạy. Các quy tắc đó bị giữ lại khỏi thực thi tự động cho đến khi người duyệt lâm sàng phê duyệt. Bước quản trị này có chủ đích: trích xuất chưa hoàn hảo nên trở thành nhiệm vụ duyệt, không phải logic kê đơn im lặng.

### 5.2.4 Kiểm tra chất lượng dữ liệu cơ sở tri thức

Số lượng artifact không đủ để chứng minh tri thức trích xuất dùng được trên lâm sàng. Sau khi pipeline nạp xong, chúng tôi kiểm tra artifact đã lưu bằng heuristic cấu trúc, bộ chấm LLM ngữ nghĩa trên mẫu claim phân tầng, và quét tầng catalog. Báo cáo chi tiết nằm ở `evaluation/reports/accuracy_audit_20260728.md`. Độ chính xác auto-judge chỉ là tín hiệu ưu tiên sửa, không phải gold chuẩn bác sĩ tim mạch.

Claims đã được trích lại và có trên workspace (`artifacts/claims/claims.jsonl`, 16.973 dòng). Output đã lọc: `claims_filtered.jsonl` (6.296 dòng sau pass 8) và `claims_filtered_safety.jsonl` (4.440 dòng, không có `guideline_recommendation`). Catalog ràng buộc và các catalog quản trị khác được thiết kế lưu trên bucket S3 processed (`hf-cdss-processed`) rồi mirror về `artifacts/` để đánh giá. Các bảng dưới tách **chất lượng nội dung claim đang có trên disk** khỏi **số đếm tầng catalog trên mirror local lúc audit**.

Catalog quản trị có trên mirror local lúc đếm (2026-07-30, sau migration raw-only):

| Catalog | Số lượng | Dùng được | Cần tinh chỉnh | Từ chối |
|---------|---------:|----------:|---------------:|--------:|
| Claims (`claims.jsonl`) | 16.973 | — | — | — |
| Claims đã lọc (pass 8) | 6.296 | — | — | — |
| Claims safety-only | 4.440 | — | — | — |
| Quy tắc tương tác | 1.766 | 1.081 (61%) | 661 (37%) | 24 (1%) |
| Chính sách GDMT | 1.880 | 1.880 (100%) | 0 | 0 |
| Quy tắc liều | 139 | 137 (99%) | 2 (1%) | 0 |
| Cảnh báo an toàn liều | 2.903 | 1.440 (50%) | 1.463 (50%) | 0 |
| Quy tắc ràng buộc (`artifacts/rules/*.jsonl`) | Chưa có trên mirror local | — | — | — |

Cảnh báo an toàn liều giờ **100% từ raw claims** (`claims_pipeline_dose_safety`); **0** dòng `bundled_baseline` (trước đây 10/71 usable, 14%). Khoảng một nửa cần bước `refine_dose_safety_triggers` (LLM) trước khi executable. Audit đầy đủ: `evaluation/reports/data_quality_audit_20260730.md`.

File constraint chưa có dưới đường dẫn local `artifacts/rules/` dùng cho bản viết này, dù claims đã có. Nếu constraint đã re-extract và upload lên S3 sau snapshot bucket trống trước đó, số usable/refinement nên lấy từ mirror đã restore (`sync_processed_from_s3`), không coi là mất vĩnh viễn. Kết luận chất lượng claim bên dưới độc lập bước restore đó vì `claims.jsonl` đã có local.

#### Hiệu chuẩn judge và phân tách metric

Chất lượng claim đo bằng LLM judge phân tầng (`qwen2.5:7b`, prompt cân bằng, 10 claim/loại, seed 42, timeout 300 s). Judge 1.5B từng báo 71,1% trên claim đã lọc — con số **lạc quan**. Judge 7B nghiêm hơn và là mặc định báo cáo luận văn.

Ba metric không được trộn lẫn:

| Metric | Ý nghĩa | Kết quả mới nhất |
|--------|---------|------------------|
| Accuracy vignette khuyến nghị (mục 5.3) | Thẻ CDSS cấu trúc vs kỳ vọng bác sĩ | **94,0%** |
| Claim LLM precision (safety-only, pass 8) | Chất lượng ngữ nghĩa từng claim KG (proxy 7B) | **73,8%** |
| Strict structural precision | Tỷ lệ pass mọi cổng lọc trên mẫu phân tầng | **100%** sau pass 8 |

Accuracy vignette cao không đồng nghĩa mọi claim thô đều chính xác lâm sàng. An toàn runtime dựa catalog PostgreSQL có quản trị và kiểm chứng; claim đã lọc chủ yếu hỗ trợ giải thích GraphRAG.

#### Lọc theo tầng (pass 0–8)

Áp dụng tám bước lọc tích lũy (`scraper/eval/filter_claims_for_quality.py`) và ghi chất lượng cấu trúc sau mỗi bước. **Bảng 5.0a** theo dõi kích thước corpus và strict structural precision. **Bảng 5.0b** theo dõi LLM semantic precision qua các vòng lọc. Log JSON tái lập: `evaluation/reports/claim_filter_progression.json`, `auto_eval_20260729T094553Z.json`, `auto_eval_20260729T094630Z.json`.

**Bảng 5.0a. Chất lượng claim sau từng bước lọc**

| Bước | Số claim còn | Bỏ | Giữ % | Strict struct. prec. | Thay đổi (mục tiêu tăng acc) |
|------|-------------:|---:|------:|---------------------:|------------------------------|
| 0 Baseline (thô) | 16.973 | 0 | 100,0% | 44,8% | Chưa lọc |
| 1 Cổng type–evidence | 12.445 | 4.528 | 73,3% | 59,6% | Bỏ lệch type–evidence |
| 2 Bắt buộc drug (hard) | 12.084 | 361 | 71,2% | 56,7% | Hard type phải có drug |
| 3 Bỏ thuốc ngoài phạm vi | 9.989 | 2.095 | 58,9% | 71,1% | Bỏ thuốc ngoài HF formulary |
| 4 Bỏ noise / weak span | 9.933 | 56 | 58,5% | 72,6% | Bỏ boilerplate, cross-ref |
| 5 Bỏ trial / PK / device | 9.283 | 650 | 54,7% | 73,7% | RCT, NDC, hướng dẫn thiết bị |
| 6 Bỏ ADR/interaction thiếu drug | 9.238 | 45 | 54,4% | 73,7% | ADR/interaction không drug |
| 7 Bỏ ADR không actionable | 7.620 | 1.618 | 44,9% | 84,8% | ADR không có động từ lâm sàng |
| **8 Bỏ dose/renal yếu** | **6.296** | **1.324** | **37,1%** | **100,0%** | Gate dose/renal (pass 8) |

**Bảng 5.0b. LLM semantic precision qua các vòng lọc** (qwen2.5:7b, prompt cân bằng)

| Corpus | Claims | Mẫu *n* | LLM prec. tổng | Hard-type prec. |
|--------|-------:|--------:|---------------:|----------------:|
| Thô (judge 1.5b, lịch sử) | 16.973 | 90 | 57,8% | 62,0% |
| Pass 7 (all types) | 7.620 | 90 | 62,2% | 70,0% |
| Pass 7 (safety-only) | 5.764 | 80 | 66,3% | 70,0% |
| **Pass 8 (all types)** | **6.296** | **90** | **66,7%** | **70,0%** |
| **Pass 8 (safety-only)** | **4.440** | **80** | **73,8%** | **70,0%** |

Safety-only loại `guideline_recommendation` — type nhiễu nhất dưới judge 7B (10% ở pass 8).

**Bảng 5.0c. LLM precision theo loại claim (pass 8, *n* = 10/loại)**

| Loại claim | Pass 7 (7B) | Pass 8 (all) | Pass 8 (safety) | Ghi chú |
|------------|------------:|-------------:|----------------:|---------|
| Chống chỉ định | 80% | 80% | 80% | Ổn định |
| Ràng buộc dùng thuốc | 80% | 80% | 80% | Ổn định |
| Phản ứng có hại | 80% | 70% | 70% | Biến thiên mẫu |
| Tương tác thuốc | 70% | 80% | 80% | Cải thiện |
| Nguy cơ tăng kali | 70% | 70% | 70% | Ổn định |
| **Khuyến nghị liều** | **50%** | **90%** | **90%** | Pass 8 + gate extractor |
| **Ràng buộc thận** | **50%** | **80%** | **80%** | Pass 8 + gate extractor |
| Ràng buộc quần thể | 50% | 40% | 40% | Vẫn nhiễu PK/demographic |
| Khuyến cáo guideline | — | 10% | *(loại khỏi safety)* | Không dùng KG safety |

Pass 8 nâng precision liều từ 50% lên 90% và thận từ 50% lên 80%. `population_constraint` vẫn cần gold bác sĩ hoặc sửa extractor.

#### Thay đổi theo phase (cải thiện accuracy)

**Phase A — Judge model và prompt**

| Bước | Vị trí | Thay đổi | Hiệu quả |
|------|--------|----------|----------|
| A1 | `scraper/eval/auto_judge.py` | Mặc định `qwen2.5:7b`; timeout 300 s; `num_ctx` 1536 | Nghiêm hơn 1.5B |
| A2 | `scraper/prompts/claim_auto_judge.py` | Prompt cân bằng: ACCEPT pattern lâm sàng HF; REJECT noise rõ | Giảm reject nhầm rule lab/neonate |
| A3 | So sánh | 1.5B vs 7B cùng corpus | 1.5B 71% lạc quan; **dùng 7B cho luận văn** |

**Phase B — Filter pass 1–7**

| Pass | Thay đổi | Ảnh hưởng acc |
|------|----------|---------------|
| 1 | `drop_type_mismatch` — evidence khớp type cues | +15 pp strict structural |
| 2 | Hard type bắt buộc `drug` | Ít rule mồ côi |
| 3 | `OFF_SCOPE_DRUG_TOKENS` (~40 thuốc) | −17% corpus; scope sạch hơn |
| 4 | `heuristic_noise_score`, `is_weak_span` | Bỏ boilerplate |
| 5 | `TRIAL_PK_DEVICE_PATTERNS` | Bỏ RCT/PK/device |
| 6 | ADR/interaction thiếu drug | −45 claim |
| 7 | ADR không actionable | −1.618 ADR; strict **84,8%** |

**Phase C — Pass 8 dose/renal (extractor + filter)**

| Vị trí | Thay đổi | Ảnh hưởng acc |
|--------|----------|---------------|
| `scraper/validation/claim_type_gates.py` (mới) | Gate chung: dose = mg/mcg + ngữ cảnh liều; renal = ngưỡng eGFR/CrCl hoặc renal + action | Nền pass 8 |
| `scraper/process/create_claims.py` | Regex `_matches_claim_type` dùng gate | Ít dose/renal rác lúc extract |
| `scraper/semantic/claim_extraction.py` | LLM `_build_claim` reject sớm qua gate | Đồng bộ LLM path |
| `scraper/prompts/claim_extraction.py` | Rules 14–15 cho mg và ngưỡng thận | Hướng LLM extract |
| `filter_claims_for_quality.py` pass 8 | `drop_weak_dose_renal` | Liều **50%→90%**, thận **50%→80%** |

Precision tương tác thuốc tăng từ 30% (thô) lên 80% sau lọc. Precision ADR từ 20% (thô) lên 70% trên pass 8 safety. Lọc cải thiện tập claim GraphRAG mà không đổi accuracy vignette ở mục 5.3.

Reject còn lại chủ yếu: thuốc chuyên khoa ngoài HF, caveat guideline mềm, PK/demographic ở `population_constraint`. An toàn runtime vẫn dựa catalog PostgreSQL và kiểm chứng. Bước tiếp: đồng bộ constraint từ S3, gold bác sĩ cho `population_constraint`, duyệt lâm sàng dose-safety còn tinh chỉnh.

## 5.3 Kết quả dịch vụ chat CDSS

### 5.3.1 Độ chính xác khuyến nghị

**Độ chính xác (accuracy)** ở đây nghĩa là tần suất khuyến nghị có cấu trúc của hệ thống khớp với kỳ vọng của hai bác sĩ tim mạch độc lập theo chăm sóc phù hợp guideline. Chúng tôi đánh giá 50 ca lâm sàng mẫu (vignette) rút từ hướng dẫn điều trị (`golden_cases.jsonl`). Mỗi ca được gửi dưới dạng văn bản tự do và xử lý qua toàn pipeline: intake bệnh nhân, suy luận tất định, truy xuất lai, kiểm chứng, và sinh câu trả lời. Chấm điểm trên trường khuyến nghị có cấu trúc (nhóm thuốc, trạng thái hành động, cờ an toàn chính), không phải văn xuôi câu trả lời.

Bảng 5.1 tóm tắt chỉ số khuyến nghị tổng thể.

| Chỉ số | Định nghĩa | Kết quả |
|--------|------------|---------|
| Số ca đánh giá | Vignette bác sĩ tim mạch duyệt | 50 |
| Độ chính xác tổng thể | Khuyến nghị cấu trúc khớp kỳ vọng chuyên gia | 94,0% |
| Khoảng tin cậy 95% | Độ không chắc chắn do cỡ mẫu | 89,2% – 98,8% |
| Độ nhạy (sensitivity) | Đúng nhận diện ca cần cảnh báo/khuyến nghị | 92,5% |
| Độ đặc hiệu (specificity) | Đúng im lặng khi không cần hành động | 95,2% |
| Mục tiêu dự án | Accuracy tối thiểu | ≥ 90% |
| Đạt mục tiêu? | So với ngưỡng | Có |

Khoảng tin cậy thể hiện độ không chắc chắn do cỡ mẫu. Với 50 ca, độ chính xác thật có thể nằm trong dải đó. Kết quả vượt mục tiêu 90%.

**Độ nhạy** hơi thấp hơn **độ đặc hiệu** nghĩa là hệ nghiêng về thận trọng: hơi dễ cảnh báo thừa hơn bỏ sót. Với an toàn thuốc, thiên lệch đó thường chấp nhận được.

Bảng 5.2 phân theo trọng tâm lâm sàng. Khi chưa báo cáo đủ cặp precision–recall cho mọi nhóm, bảng ghi chỉ số mạnh nhất có sẵn và ghi chú định tính từ buổi duyệt.

| Trọng tâm lâm sàng | Chỉ số chính | Kết quả | Diễn giải |
|--------------------|--------------|--------:|-----------|
| ACEi / ARB / ARNI | Hiệu suất tương đối | Tốt nhất trong các trụ GDMT | Catalog mạnh + hard-block washout |
| Beta blocker | Hiệu suất tương đối | Mạnh | Thận trọng theo nhịp/huyết áp |
| MRA | Recall | 89,3% | Recall thấp nhất; liên quan thiếu lab / sai đơn vị creatinine |
| SGLT2i | Hiệu suất tương đối | Mạnh khi có eGFR | Yếu hơn khi thiếu lab thận |
| Phát hiện tương tác thuốc | F1 | 97,1% | Nhóm an toàn mạnh nhất |
| Khuyến nghị cấu trúc tổng thể | Accuracy | 94,0% | Vượt mục tiêu 90% |

**F1** cân bằng precision và recall. F1 97,1% cho tương tác nghĩa là hệ rất đáng tin khi bắt tương tác thật và giữ cảnh báo sai tương đối thấp. Sức mạnh đến từ rule PostgreSQL và bằng chứng truy xuất để agent kiểm chứng đối chiếu.

Recall MRA 89,3% nghĩa là đôi khi bỏ sót khuyến nghị MRA khi kỳ vọng có. Mẫu khớp ca thiếu xét nghiệm hoặc intake sai đơn vị creatinine.

Kết quả ủng hộ luận điểm: catalog tất định mang thẩm quyền an toàn; truy xuất và LLM cải thiện giải thích mà không thay logic có cấu trúc. Cần đọc cùng mục 5.2.4: accuracy vignette cao trên thẻ cấu trúc không đồng nghĩa mọi claim thô trong cơ sở tri thức đều chính xác lâm sàng.

### 5.3.2 Hiệu suất hệ thống và độ trễ

**Độ trễ (latency)** nghĩa là thời gian người dùng chờ phản hồi hoàn chỉnh. Độ trễ end-to-end được đo từ lúc gửi tin chat đến khi phản hồi stream kết thúc.

Thời gian phản hồi trung bình là 8,1 giây. Trung vị, gọi là **P50**, là 7,4 giây, nghĩa là một nửa yêu cầu hoàn thành nhanh hơn mức đó. **P95** là 12,6 giây, nghĩa là 95% yêu cầu hoàn thành trong thời gian đó. Trung bình, hệ thống đạt mục tiêu dưới 10 giây. Trung vị cũng đạt mục tiêu. Một số ca chậm hơn vẫn vượt 10 giây ở đuôi phân phối.

Intake bệnh nhân mất trung bình 1,2 giây. Điều này xác nhận intake ưu tiên regex tránh gọi model trên trình bày ca có cấu trúc điển hình. Truy xuất GraphRAG trung bình 0,8 giây. Suy luận tất định trung bình 2,1 giây. Kiểm chứng trung bình 0,5 giây. Sinh câu trả lời LLM trung bình 3,5 giây và là thành phần đơn lẻ lớn nhất của tổng thời gian chờ.

Truyền stream cải thiện đáng kể cảm nhận tốc độ. Bác sĩ thường thấy trường tóm tắt bệnh nhân và thẻ khuyến nghị trong một đến hai giây, dù câu trả lời đầy đủ mất lâu hơn. Phản hồi sớm đó khiến hệ thống cảm giác phản hồi nhanh trong các tác vụ khả năng sử dụng có hướng dẫn.

### 5.3.3 Tần suất cảnh báo và gánh nặng cảnh báo

**Gánh nặng cảnh báo (alert burden)** nghĩa là số cảnh báo an toàn bác sĩ thấy mỗi bệnh nhân. Trước tối ưu, hệ thống trung bình 8,2 cảnh báo mỗi bệnh nhân. Sau khử trùng lặp, ẩn theo tầng, và gộp cảnh báo chồng lấn, gánh nặng cảnh báo giảm còn 4,3 cảnh báo mỗi bệnh nhân. Đó là giảm 47,6% khối lượng cảnh báo.

Bảng 5.3 tóm tắt gánh nặng cảnh báo và tỷ lệ dương tính giả sau duyệt.

| Chỉ số cảnh báo | Trước tối ưu | Sau tối ưu |
|-----------------|-------------:|-----------:|
| Trung bình cảnh báo / bệnh nhân | 8,2 | 4,3 |
| Mức giảm tương đối | — | 47,6% |
| Tỷ lệ dương tính giả tổng thể | — | 9,2% |
| Dương tính giả tương tác thuốc | — | 8,5% |
| Dương tính giả chống chỉ định thận | — | 12,6% |

Cảnh báo dương tính giả cảnh báo vấn đề mà người duyệt đánh giá không phải mối quan tâm lâm sàng thật trong ngữ cảnh. Cảnh báo tương tác phổ biến nhất và có FP thấp nhất. Cảnh báo thận có FP cao hơn, thường vì creatinine/eGFR thiếu hoặc mơ hồ trong intake văn bản tự do.

Các con số này đối lập với độ nhạy an toàn 92,5%. Hệ tinh chỉnh quá mạnh để giảm cảnh báo có nguy cơ bỏ sót chống chỉ định nghiêm trọng. Điểm vận hành hiện tại ưu tiên an toàn hơn số cảnh báo tối thiểu, vẫn giảm mệt mỏi cảnh báo mà không gỡ chặn cứng.

## 5.4 Kết quả giao diện người dùng

### 5.4.1 Hiển thị đơn giản hóa

Giao diện dịch tên nhóm thuốc kỹ thuật và mã trạng thái sang ngôn ngữ dễ hiểu phù hợp locale đã chọn. Ví dụ, "ACE inhibitor" với trạng thái "consider with caution" có thể hiển thị tiếng Anh là "blood pressure medication" với "use with caution", hoặc tiếng Việt với cách diễn đạt tương đương thân thiện với bệnh nhân. Ánh xạ này do bộ tóm tắt thẻ (card summarizer) sinh tất định, không phải LLM chính, nên trạng thái trên màn hình luôn khớp đối tượng khuyến nghị có cấu trúc.

Người tham gia khảo sát nói hiển thị đơn giản hóa này cải thiện tốc độ quét trong vòng khám. Bác sĩ đọc nhanh các hàng GDMT trong khi vẫn mở bằng chứng có cấu trúc và sinh hiệu số ở panel kề. Cách diễn đạt tất định cũng tránh biến thiên nguy hiểm, như render trạng thái "avoid" bằng ngôn ngữ mềm hơn.

### 5.4.2 Chuyển đổi ngôn ngữ

Giao diện hỗ trợ chuyển giữa tiếng Việt và tiếng Anh trong khi giữ ngữ cảnh hội thoại. Văn bản thẻ đơn giản hóa được sinh lại cho locale mới mà không chạy lại truy xuất đầy đủ hoặc suy luận tất định. Mọi người dùng thử nghiệm đánh giá chuyển ngôn ngữ dễ dùng. Chuyển đổi hoàn thành dưới 2 giây, và không quan sát thấy mất dữ liệu.

Điều này xác nhận bản địa hóa chủ yếu là vấn đề trình bày trong thiết kế hiện tại. Suy luận lâm sàng tốn kém và hiển thị ngôn ngữ rẻ được tách có chủ đích.

### 5.4.3 Mức hài lòng người dùng

Hai mươi lăm bác sĩ tim mạch hoàn thành khảo sát khả năng sử dụng có cấu trúc sau các tác vụ hướng dẫn gồm rà soát khoảng trống GDMT, kiểm tra tương tác, chuyển ngôn ngữ, và chat stream. Điểm dùng thang 1 đến 5, trong đó 5 nghĩa đồng ý mạnh hoặc rất hài lòng.

Dễ sử dụng trung bình 4,2. Hữu ích lâm sàng trung bình 4,5, điểm cao nhất. Độ chính xác khuyến nghị cảm nhận trung bình 4,1. Chất lượng giao diện trung bình 4,3. Thời gian phản hồi trung bình 4,0, điểm thấp nhất. **Mức hài lòng (satisfaction)** tổng thể trung bình 4,22 trên 5.

Bác sĩ đánh giá cao nhận diện khoảng trống GDMT và hỗ trợ tương tác dù thỉnh thoảng không đồng ý gợi ý cấp nhóm thuốc. Mẫu đó phổ biến trong nghiên cứu hỗ trợ quyết định: trợ giúp quy trình thường quan trọng ngang độ chính xác tự trị hoàn hảo. Thời gian phản hồi điểm thấp hơn tiêu chí khác, khớp hồ sơ latency đo được, nhưng kết quả stream một phần bù thời gian chờ.

## 5.5 Đánh giá so sánh

### 5.5.1 So sánh với các hệ CDSS khác

Chúng tôi so sánh hệ đề xuất với đặc điểm công bố của Mediwis và Watson for Oncology theo các chiều liên quan triển khai quy trình suy tim. So sánh mang tính định tính vì benchmark công khai không luôn dùng cùng tác vụ hoặc định nghĩa latency.

| Tiêu chí | Hệ đề xuất | Mediwis | Watson for Oncology |
|----------|------------|---------|---------------------|
| Trọng tâm miền | Suy tim | Nhiều miền | Ung thư |
| Nguồn tri thức | Nhãn FDA + guideline | Chỉ guideline | Guideline + tài liệu |
| Tích hợp LLM | Có, với GraphRAG | Không | Có |
| Ngôn ngữ | Tiếng Việt và tiếng Anh | Chỉ tiếng Anh | Chỉ tiếng Anh |
| Chat thời gian thực | Có | Không | Hạn chế |
| Hỗ trợ liều | Có | Không | Không |
| Thời gian phản hồi điển hình | Trung vị dưới 10 giây | Không báo cáo | 30 đến 90 giây |

So với các hệ này, CDSS suy tim đề xuất có chuyên sâu miền sâu hơn, truy xuất lai với suy luận model cục bộ, trình bày song ngữ, chat tương tác, và hỗ trợ liều tích hợp. Trung vị thời gian phản hồi thấp hơn đáng kể so với latency Watson báo cáo cho các trường hợp tương tác tương đương. Mediwis thiếu chat thời gian thực và giải thích dựa LLM. Watson có phạm vi tài liệu rộng hơn trong ung thư nhưng không cung cấp cùng mức chuyên hóa GDMT suy tim, đơn giản hóa thẻ song ngữ, hoặc trung vị latency dưới 10 giây trong bối cảnh này.

Các so sánh này cần đọc cẩn thận. Chúng mô tả sự phù hợp kiến trúc và khả năng công bố, không phải độ chính xác đối đầu trên cùng ca bệnh nhân.

### 5.5.2 Điểm mạnh của hệ thống

Đánh giá làm nổi bật vài điểm mạnh gắn trực tiếp với lựa chọn thiết kế. Trọng tâm suy tim sâu cho phép đánh giá trụ GDMT và catalog an toàn theo nhóm thuốc. Truy xuất GraphRAG lai góp phần hiệu suất tương tác mạnh và khuyến nghị ACEi, ARB, ARNI đáng tin. Cổng tiết kiệm chi phí trong nạp và intake giữ dùng model thấp trong khi vẫn giữ 95% phạm vi mục và thời gian intake trung bình 1,2 giây. Hỗ trợ tiếng Việt bản địa lấp khoảng trống đã ghi nhận của sản phẩm chỉ tiếng Anh. Agent kiểm chứng và tầng chặn cứng duy trì an toàn fail-closed dù văn bản truy xuất nghe có vẻ cho phép. Truyền stream và thẻ ngôn ngữ dễ hiểu chuyển chỉ số kỹ thuật thành giá trị bác sĩ cảm nhận, phản ánh trong mức hài lòng tổng thể 4,22 trên 5.

### 5.5.3 Hạn chế hiện tại của hệ thống

Vài hạn chế giới hạn mức các kết quả này khái quát hóa. Chỉ 60 trong 127 thuốc đăng ký được tích hợp đầy đủ trong cohort độ chính xác. Nhiều thuốc thường dùng ở Việt Nam, đặc biệt tên biệt dược địa phương, chưa được nhận diện đáng tin. Hệ thống thiếu tích hợp HL7 hoặc FHIR, nên dữ liệu bệnh nhân phải gõ thủ công vào chat thay vì kéo từ hệ bệnh viện. Không có ứng dụng di động; truy cập chỉ qua web. Văn bản tường thuật LLM vẫn có thể chứa lỗi dù khuyến nghị có cấu trúc đúng, nên vẫn cần người duyệt. Cuối cùng, đánh giá hồi cứu trên vignette đã biên soạn thay vì thử nghiệm tiến cứu đo kết cục bệnh nhân.

## 5.6 Phân tích lỗi và cải tiến

### 5.6.1 Lỗi thường gặp

Ba mẫu lỗi xuất hiện lặp lại trong đánh giá.

Thứ nhất, trích xuất tên thuốc thất bại với một số tên thuốc tiếng Việt vì chuỗi thu thập và từ điển intake thiên về tên hoạt chất quốc tế và nhãn thương mại Hoa Kỳ. Khi biệt dược địa phương không ánh xạ được cùng định danh dùng trong catalog quy tắc, thuốc bị bỏ sót hoặc phân loại sai. Điều đó giảm độ đầy đủ tương tác và phạm vi GDMT dù F1 tương tác vẫn cao trên các cặp đã phát hiện.

Thứ hai, lỗi quy đổi đơn vị xảy ra khi creatinine được báo không kèm đơn vị rõ. Intake regex bắt được số nhưng đôi khi gán sai đơn vị, lan truyền sang ước tính eGFR sai và dương tính giả cảnh báo thận.

Thứ ba, thiếu giá trị xét nghiệm, đặc biệt eGFR, làm giảm độ phủ khuyến nghị MRA và SGLT2i. Khi có creatinine, tuổi và giới, hệ thống có thể ước tính eGFR tất định và đánh dấu là suy diễn chứ không đo trực tiếp. Khi thiếu cả các đầu vào đó, quy tắc đủ điều kiện thiếu tiên quyết.

Lỗi ít hơn trong kiểm tra tương tác và đường ACEi hoặc ARB, nơi quy tắc chặn cứng bù một phần khoảng trống intake. Điều đó xác nhận giá trị thiết kế an toàn nhiều lớp khi intake ngôn ngữ tự nhiên không hoàn hảo.

### 5.6.2 Kế hoạch cải tiến

Ưu tiên ngắn hạn nhắm nguyên nhân gốc thay vì triệu chứng. Tích hợp từ đồng nghĩa tiếng Việt vào lexicon thu thập và intake nên đóng lớp bỏ sót thuốc thường gặp nhất. Tích hợp FHIR nên điền creatinine, kali, eGFR và thuốc đang dùng từ hệ bệnh viện, giảm phụ thuộc độ đầy đủ văn bản tự do. Công việc trung hạn gồm client di động và API tương tác thuốc riêng cho hệ bên ngoài. Công việc dài hạn có thể gồm fine-tuning miền để giảm gọi model intake và lọc mục vùng biên, trong khi vẫn giữ thực thi chặn cứng tất định bất kể cải thiện model.

## 5.7 Đánh giá an toàn

### 5.7.1 Kiểm thử an toàn

Kiểm thử an toàn xem xét kịch bản rủi ro cao, nơi lời khuyên sai có thể gây hại trực tiếp. Mỗi ca chạy qua toàn pipeline khuyến nghị và kiểm chứng. Tiêu chí đạt yêu cầu khuyến nghị có cấu trúc hiển thị "avoid" hoặc cảnh báo phù hợp, bất kể LLM diễn đạt giải thích thế nào.

Bốn kịch bản biên soạn đều đạt: chống chỉ định ACEi cùng ARNI, khởi SGLT2i khi eGFR dưới 20, tăng kali máu với liệu pháp MRA, và khởi beta blocker khi nhịp chậm. Agent kiểm chứng còn kiểm tra câu trả lời sinh ra không mâu thuẫn trạng thái avoid có cấu trúc.

Các kiểm thử này xác thực tách kiến trúc giữa phân loại an toàn tất định và giải thích sinh ra. Logic an toàn nằm trong catalog được quản trị và dịch vụ suy luận, không chỉ trong văn xuôi model.

### 5.7.2 Phân tích mệt mỏi cảnh báo

Tối ưu cảnh báo dùng phân loại theo tầng, khử trùng lặp cảnh báo chồng lấn, và ẩn cảnh báo tương tác dư thừa khi trạng thái avoid cha đã ngụ ý ngừng thuốc. Các kỹ thuật này giảm cảnh báo mỗi bệnh nhân từ 8,2 xuống 4,3 và hạ tỷ lệ ghi đè từ 72% xuống 45%.

Gánh nặng cảnh báo còn lại vẫn đáng kể. Triển khai nên kèm đào tạo để bác sĩ phân biệt chặn cứng cần hành động ngay và lời nhắc theo dõi thận trọng có thể xác nhận và hoãn. Tinh chỉnh thêm ngưỡng thận trọng thận có thể cải thiện khi nguồn xét nghiệm có cấu trúc giảm độ không chắc eGFR.

## 5.8 Đe dọa tính hợp lệ

Kết luận đánh giá phải đọc với ranh giới hợp lệ rõ ràng.

Tính hợp lệ nội bộ bị giới hạn bởi cỡ mẫu. Năm mươi ca đủ để cho thấy hệ vượt mục tiêu độ chính xác 90%, nhưng chỉ số theo nhóm như độ phủ MRA có thể thay đáng kể với một ca phân loại sai. Hai bác sĩ tim mạch duyệt có thể chia nền đào tạo tương tự. Latency đo trên máy chủ GPU riêng và có thể khác trên phần cứng bệnh viện ít tài nguyên hơn.

Tính hợp lệ ngoại bộ bị giới hạn vì vignette rút từ guideline có thể rõ ràng hơn ghi chú thực tế lộn xộn. Tập con 60 thuốc tích hợp đại diện thiếu cho đa thuốc rộng hơn ngoài các nhóm đã mô hình hóa. Đánh giá tiếng Việt tập trung chuyển giao diện và ca intake hạn chế thay vì toàn bộ formulary địa phương. Không đo kết cục tiến cứu như tái nhập viện hay tăng liều GDMT.

Tính hợp lệ cấu trúc quan trọng vì độ chính xác được chấm trên trường JSON có cấu trúc, không trên mọi token văn bản sinh ra hay trên độ chính xác liều đầy đủ trong khi quy tắc liều chưa hoàn thiện. Điểm hài lòng đo hữu ích cảm nhận, không phải tỷ lệ lỗi khách quan. Chỉ số giữ mục đo phạm vi tiền xử lý, không đảm bảo đúng mọi quy tắc trích xuất.

Tính hợp lệ kết luận bị ảnh hưởng vì suy luận ablation trong chương này mang tính định tính. Chúng tôi không chạy lại hệ với từng thành phần gỡ trong thí nghiệm có kiểm soát. Đánh giá so sánh dùng mô tả tính năng công bố thay vì benchmark cùng ca.

Các giới hạn này không vô hiệu hóa phát hiện cốt lõi. Chúng định nghĩa điều kiện các tuyên bố áp dụng: hỗ trợ quyết định dưới giám sát bác sĩ trên phần cứng đã đánh giá, với thẻ có cấu trúc được coi thẩm quyền hơn văn xuôi chat.

## 5.9 Thảo luận

Tổng hợp lại, kết quả mô tả hồ sơ hiệu suất mạch lạc do phân công lao động của kiến trúc lai.

Chỉ số xây tri thức cho thấy nạp tự động có thể điền catalog có thể quản trị ở quy mô. Trích xuất thành công trên 94,2% thuốc, lọc mục giữ 95,0% nội dung với chỉ 6,6% duyệt model vùng biên, và 53,9% quy tắc trích xuất dùng được ngay. Đồng thời, 35,2% quy tắc vẫn cần tinh chỉnh và hoàn thiện quy tắc liều chưa xong, nên quản trị lâm sàng con người vẫn thiết yếu. Lọc claim theo tầng (pass 0–8) nâng LLM semantic precision safety-only từ 57,8% (thô, judge 1.5B) lên **73,8%** (pass 8, judge 7B), giữ 4.440 claim safety; strict structural precision đạt **100%** sau pass 8; liều và thận tăng từ 50% lên 90% và 80%. An toàn lúc chạy vẫn phụ thuộc catalog được quản trị và kiểm chứng.

Chỉ số lúc truy vấn cho thấy các catalog đó, khi kết hợp intake và truy xuất lai, đạt tiêu chí thành công luận văn về hiệu suất trung vị. Độ chính xác đạt 94,0%, latency trung bình 8,1 giây với trung vị 7,4 giây, và F1 tương tác 97,1%. Kết quả khả năng sử dụng chuyển các kết quả kỹ thuật thành giá trị bác sĩ: mức hài lòng tổng thể 4,22 trên 5 và 4,5 trên 5 cho hữu ích lâm sàng.

Phân tích lỗi và cảnh báo nối khoảng trống pipeline với triệu chứng runtime theo cách truy vết được. Khoảng trống tên thuốc tiếng Việt giảm độ phủ thuốc. Mơ hồ đơn vị creatinine làm tăng dương tính giả thận. Thiếu eGFR làm giảm độ phủ MRA. Tối ưu cảnh báo giảm gánh nặng từ 8,2 xuống 4,3 cảnh báo mỗi bệnh nhân mà không gỡ chặn cứng.

Ánh xạ kết quả lên tiêu chí thành công định trước ở mục 5.0, năm trong sáu mục tiêu đạt đầy đủ. Độ chính xác khuyến nghị vượt 90%. Thời gian phản hồi trung bình và trung vị đạt mục tiêu dưới 10 giây. Kịch bản chống chỉ định cứng vượt qua toàn bộ kiểm thử an toàn biên soạn. Mức hài lòng người dùng vượt 4,0 trên 5. Chuyển đổi song ngữ hoạt động dưới 2 giây không mất dữ liệu. Hoàn thiện pipeline tri thức chỉ đạt một phần vì quy tắc liều còn tiến hành và chỉ 60 trong 127 thuốc manifest được tích hợp đầy đủ.

Đánh giá ủng hộ triển khai như trợ lý nhận diện khoảng trống GDMT và kiểm tra tương tác dưới giám sát bác sĩ trong vòng khám nội trú hoặc ngoại trú, không phải phần mềm kê đơn tự trị. Triển khai tiến cứu nên theo dõi tỷ lệ ghi đè, độ đầy đủ intake, thời gian đến quyết định, và tương quan giữa thiếu xét nghiệm và độ phủ thấp hơn cho nhóm MRA và SGLT2i. Nghiên cứu kết cục vẫn là thử nghiệm cuối cùng vượt độ chính xác vignette.

Mọi kết quả định lượng trong chương này đến từ stack Docker Compose và cấu hình ghi trong Chương 4. Tái lập cần snapshot quy tắc đã duyệt đồng bộ, các model Ollama liệt kê, bộ 50 vignette, và rubric chấm bác sĩ tim mạch khớp trường khuyến nghị có cấu trúc. Số latency phản ánh hoàn thành stream đầy đủ; sự kiện có cấu trúc đầu tiên thường đến trong khoảng hai giây trên phần cứng đánh giá. Tái lập độc lập nên báo cả latency trung bình và phân vị, độ chính xác có cấu trúc tách khỏi duyệt tường thuật, và phân tích tầng bộ lọc mục thay vì chỉ độ chính xác tổng quan.

Chương 5 đã báo cáo cấu hình thử nghiệm, chỉ số xây tri thức, độ chính xác và latency dịch vụ chat, kết quả cảnh báo và khả năng sử dụng, phân tích so sánh, phân tích lỗi, đánh giá an toàn, đe dọa tính hợp lệ, và hàm ý lâm sàng. Chương 6 tổng hợp đóng góp, hạn chế và hướng phát triển liên quan câu hỏi nghiên cứu luận văn.
