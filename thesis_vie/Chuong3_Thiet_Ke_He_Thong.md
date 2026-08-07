# CHƯƠNG 3: THIẾT KẾ HỆ THỐNG

## 3.0 Mục đích, phạm vi và cách tiếp cận

### 3.0.1 Mục đích nghiên cứu

Mục đích là thiết kế, cài đặt và đánh giá CDSS chuyên suy tim tích hợp đồ thị tri thức y, GraphRAG lai, engine quy tắc lâm sàng tất định, agent kiểm chứng và LLM chạy cục bộ. Hệ thống giúp bác sĩ áp dụng GDMT nhất quán và an toàn hơn bằng cách biến nguồn có thẩm quyền (DailyMed SPL/XML, guideline ESC và AHA/ACC/HFSA, tri thức tương tác đã biên soạn) thành artifact có quản trị, truy vấn được.

Về khoa học, nghiên cứu theo bốn mục tiêu: pipeline xây tri thức tự động; truy xuất lai (dense, BM25, đồ thị, HyDE, RRF) [12]–[14]; tách logic khuyến nghị tất định khỏi văn bản LLM; đo end-to-end theo tiêu chí định trước (Chương 5, mục 5.0). Về thực tiễn: prototype dùng dưới giám sát bác sĩ tim mạch với intake lai, GDMT, an toàn, GraphRAG, kiểm chứng và SSE song ngữ. Nghiên cứu không thay EHR hay tự động kê đơn không người duyệt. Phương pháp theo paradigm thiết kế–khoa học: vấn đề ở Chương 1, artifact có claim kiểm chứng, đánh giá minh bạch.

### 3.0.2 Phạm vi và giới hạn

Phạm vi lâm sàng chính: dược trị liệu GDMT HFrEF (ACEi, ARB, ARNI, beta blocker có bằng chứng, MRA, SGLT2i). HFpEF, suy tim mất bù cấp, thiết bị, ghép phần lớn ngoài phạm vi. Nguồn: DailyMed SPL, guideline ESC/AHA/ACC/HFSA, tương tác trong PostgreSQL. Dữ liệu qua chat, không HL7/FHIR. Khuyến nghị mang tính tư vấn. Triển khai cục bộ với JWT và Docker. Dashboard Việt–Anh. Đánh giá vignette và bộ an toàn có cấu trúc.

### 3.0.3 Tuyên bố luận điểm

CDSS lai ghép rule GDMT/an toàn tất định với GraphRAG và LLM giải thích cục bộ có thể mang hỗ trợ điều trị suy tim chính xác, kịp thời, song ngữ, phù hợp workflow trong khi bác sĩ giữ quyết định cuối. Luận văn từ chối chat sinh không ràng buộc và cảnh báo chỉ rule cứng thiếu giải thích bám bằng chứng.

### 3.0.4 Cách tiếp cận kỹ thuật tri thức (offline)

Nạp nhãn SPL và guideline vào object storage có phiên bản. Bộ lọc 3 tầng (từ khóa, BGE-M3, LLM vùng biên). Cắt đoạn, trích claim, phân lớp an toàn. Sync PostgreSQL, ChromaDB, Neo4j. PostgreSQL là thẩm quyền rule thực thi.

### 3.0.5 Cách tiếp cận lúc truy vấn (online)

Intake lai → engine GDMT/ràng buộc/tương tác/liều tất định. Song song GraphRAG: HyDE, dense ChromaDB, BM25, Neo4j, RRF. LLM không phải thẩm quyền lâm sàng; kiểm chứng và SSE đẩy thẻ trước văn bản giải thích.

### 3.0.6 Nguyên tắc: LLM lớp giải thích, rule là thẩm quyền

Rule và catalog quản trị quyết định trạng thái khuyến nghị, chặn cứng và liều. LLM chỉ giải thích và hỗ trợ intake/truy vấn; không ghi đè hard_block. Mục 3.2.1 diễn giải lại trong kiến trúc runtime đầy đủ.

## 3.1. Yêu cầu hệ thống

Điều trị suy tim phức tạp. Bác sĩ phải theo dõi bốn trụ cột của điều trị nội khoa theo hướng dẫn (Guideline-Directed Medical Therapy, GDMT), cảnh giác các phối hợp thuốc nguy hiểm, chỉnh liều theo chức năng thận, và giải thích quyết định rõ ràng cho bệnh nhân. Nhiều công cụ kiểu chatbot có thể viết văn bản trôi chảy nhưng không thể đáng tin cậy thực thi quy tắc an toàn hay chỉ ra khuyến nghị đến từ đâu. Chương này mô tả cách thiết kế Hệ hỗ trợ quyết định lâm sàng (Clinical Decision Support System, CDSS) suy tim đáp ứng các nhu cầu đó từ đầu đến cuối: từ xây dựng tri thức ngoại tuyến (offline), qua suy luận và truy xuất lúc truy vấn, đến giao diện song ngữ cho bác sĩ và quản trị tri thức.

### 3.1.1. Yêu cầu chức năng

Hệ thống phải thực hiện một tập công việc lâm sàng và vận hành liên kết với nhau. Mỗi công việc ánh xạ tới các module mô tả ở phần sau trong chương. Cùng nhau, chúng giải quyết GDMT chưa đầy đủ, quy tắc tương tác khó nhớ, cá thể hóa liều, neo bằng chứng, giao tiếp song ngữ, và catalog quy tắc dễ bảo trì.

**Phân tích hồ sơ bệnh nhân.** Khi bác sĩ gõ tin nhắn như "nam 65 tuổi, EF 30%, eGFR 45, K+ 4.2, đang dùng bisoprolol 5mg", hệ thống phải chuyển văn bản tự do đó thành hồ sơ bệnh nhân có cấu trúc. Hồ sơ gồm nhân khẩu học, kiểu hình suy tim, giá trị xét nghiệm, dấu hiệu sinh tồn, thuốc, dị ứng, cờ đỏ (red flags), và bối cảnh chăm sóc. Các kiểm tra an toàn phía sau phụ thuộc số đã gõ kiểu với đơn vị đã biết. Một giá trị kali sai có thể chặn nhầm hoặc cho phép nhầm thuốc đối kháng thụ thể mineralocorticoid (Mineralocorticoid Receptor Antagonist, MRA).

Tiếp nhận dùng thiết kế lai (hybrid). Khớp mẫu (pattern matching) nhanh trích các số như phân suất tống máu, eGFR, và kali. Từ điển thuốc (medication lexicon) ánh xạ tên biệt dược và tên tiếng Việt sang khóa thuốc chuẩn. Phát hiện phủ định (negation detection) tránh đọc "không dùng ACEi" thành "đang dùng ACEi". Khi tin nhắn dài hoặc mơ hồ, mô hình ngôn ngữ lớn (Large Language Model, LLM) lấp chỗ trống. Giá trị đo được từ khớp mẫu luôn thắng khi gộp so với đoán của model. Cách này giữ tốc độ cao trên ghi chú có cấu trúc mà vẫn xử lý tóm tắt bệnh án dạng tường thuật.

**Khuyến nghị điều trị GDMT.** Hệ thống phải đánh giá mức độ bệnh nhân nhận đủ bốn nhóm GDMT (ACE inhibitor, ARB, hoặc ARNI; beta blocker; MRA; và thuốc ức chế SGLT2), xác định khoảng trống, và đề xuất thay đổi bám guideline ESC và AHA/ACC/HFSA. Mỗi khuyến nghị phải mang trạng thái rõ như bắt đầu (start), tiếp tục (continue), thận trọng (caution), hoặc tránh (avoid), kèm bằng chứng liên kết để giải thích.

Yêu cầu này do engine suy luận tất định (deterministic reasoning engine) xử lý, không chỉ dựa vào LLM. Sự phù hợp guideline phải kiểm toán và tái lập được. Dịch vụ suy luận đọc chính sách GDMT và quy tắc ràng buộc đã duyệt từ PostgreSQL và tạo đối tượng khuyến nghị có cấu trúc. Truy xuất GraphRAG cung cấp đoạn giải thích và trích dẫn cho lớp tường thuật nhưng không bao giờ ghi đè trạng thái tránh cứng (hard avoid).

**Kiểm tra tương tác thuốc.** Các phối hợp nguy hiểm như ACE inhibitor với ARNI dùng gần đây, chặn ba tầng RAAS (triple RAAS blockade), hoặc phối hợp làm tăng kali phải được phát hiện tự động. Quy tắc tương tác nằm trong PostgreSQL dưới dạng cặp tập thuốc kèm mức độ nghiêm trọng và văn bản xử lý. Tên thuốc dạng văn bản tự do được chuẩn hóa để "Entresto" và "sacubitril/valsartan" cùng trỏ một khóa hoạt chất. Kiểm tra tương tác giữ theo quy tắc vì thực thi an toàn phải chính xác và kiểm thử được.

**Tính liều thuốc và an toàn liều.** Liều khởi đầu, liều đích, chỉnh theo thận, và lịch tăng liều phải tính từ đặc điểm bệnh nhân. Quy tắc liều lưu dạng đối tượng JSON linh hoạt để thêm mẫu tăng liều mới từ nhãn FDA mà không cần migration schema. Riêng, cảnh báo an toàn liều (dose-safety warnings) đánh dấu liều dự kiến vượt mức tối đa trên nhãn cho dải chức năng thận của bệnh nhân. Hai module cùng biến văn nhãn thành hướng dẫn số có thể thực thi.

**Cảnh báo an toàn và cổng thiếu trường.** Hệ thống phải đưa ra suy giảm chức năng thận, tăng kali máu, hạ huyết áp, nhịp chậm, và thiếu xét nghiệm quan trọng trước khi chốt khuyến nghị. Ràng buộc cứng chặn hành động không an toàn. Ràng buộc mềm phát cảnh báo kèm hướng dẫn theo dõi. Nếu thiếu xét nghiệm bắt buộc cho ý định suy ra, ví dụ kali trước khi đánh giá MRA, pipeline dừng và hỏi làm rõ thay vì đoán. Kết quả an toàn được đẩy tới bác sĩ trước khi câu trả lời hội thoại sinh xong.

**Truy xuất và xác minh bằng chứng.** Với mỗi lượt khuyến nghị vượt qua kiểm tra thiếu trường, hệ thống phải gom bằng chứng sẵn sàng trích dẫn từ nhãn thuốc và guideline, và xác minh khuyến nghị có cấu trúc vẫn nhất quán với chặn cứng và ngữ cảnh đã truy xuất. Các tác tử kiểm chứng (verification agents) kiểm toán an toàn, dữ liệu thiếu, và có bằng chứng trước khi sinh tường thuật hoàn tất.

**Giao diện đa ngôn ngữ.** Hệ thống phải hỗ trợ tiếng Việt và tiếng Anh. Bác sĩ đổi ngôn ngữ mà không mất ngữ cảnh hội thoại. Tiếp nhận xử lý dấu tiếng Việt và tên thuốc song ngữ. Nhãn ngôn ngữ dễ hiểu trên thẻ khuyến nghị sinh theo locale đã chọn. Đổi ngôn ngữ chỉ render lại trường trình bày, không chạy lại truy xuất hoặc suy luận tốn kém.

**Xây dựng tri thức và quản trị.** Hệ thống phải nạp Nhãn sản phẩm có cấu trúc FDA (FDA Structured Product Labels) và guideline suy tim vào catalog được quản trị, chỉ mục vector, và kho đồ thị. Đầu mối lâm sàng (clinical lead) phải xem quy tắc nháp, tinh chỉnh điều kiện, duyệt quy tắc dùng được, và ngưng quy tắc lỗi thời mà không cần triển khai lại mã ứng dụng. Chỉ tầng thực thi đã duyệt ảnh hưởng khuyến nghị chat.

**Quan sát vận hành.** Hệ thống phải có health, readiness, và probe phụ thuộc để vận hành biết PostgreSQL, Redis, ChromaDB, Neo4j, object storage, và dịch vụ LLM cục bộ có sẵn hay không. Sự kiện kiểm toán (audit events) ghi khuyến nghị và hành động quản trị để xem lại sau.

### 3.1.2. Yêu cầu phi chức năng

**Hiệu năng.** Thời gian phản hồi khuyến nghị nên dưới mười giây cho truy vấn tương tác điển hình trên phần cứng bệnh viện vừa phải, hỗ trợ khoảng năm mươi người dùng đồng thời trong triển khai thí điểm. Luồng Server-Sent Events (SSE) hiển thị kết quả từng phần trước khi câu trả lời hội thoại đầy đủ. Cache Redis và pool truy xuất giới hạn tránh độ trễ tăng tuyến tính theo kích thước catalog.

**Độ chính xác và an toàn.** Độ chính xác khuyến nghị điều trị nên đạt ít nhất chín mươi phần trăm so với ca đánh giá bám ESC, đo trên đối tượng khuyến nghị có cấu trúc, không phải văn LLM. Ràng buộc an toàn cứng không được lặng lẽ bỏ sót. Hệ thống có thể phát cảnh báo thận trọng thay vì duyệt điều trị khi chức năng thận hoặc điện giải chưa chắc chắn.

**Bảo mật và quyền riêng tư.** Dữ liệu bệnh nhân phải được bảo vệ khi truyền và khi lưu theo chính sách hosting của cơ sở. JWT, phân quyền theo vai trò (Role-Based Access Control, RBAC), chấm dứt TLS, và ghi log kiểm toán đáp ứng kỳ vọng bảo mật y tế cơ bản. Suy luận LLM cục bộ qua Ollama hỗ trợ thí điểm không muốn gửi ca lâm sàng mẫu (vignette) ra API cloud bên ngoài.

**Khả mở rộng và bảo trì.** Cập nhật guideline và nhãn không được đòi triển khai lại ứng dụng. Artifact pipeline JSONL, bảng quản trị PostgreSQL, embedding ChromaDB, và import Neo4j có thể làm mới độc lập. Vòng đời nháp, đã duyệt, và ngưng dùng giữ tự động hóa chịu trách nhiệm với đầu mối lâm sàng.

**Khả năng giải thích.** Bác sĩ phải thấy vì sao một trạng thái xuất hiện. Thẻ có cấu trúc, huy hiệu kiểm chứng, và trích đoạn bằng chứng kèm liên kết nguồn mở cung cấp dấu vết đó mà không bắt bác sĩ tin văn model mờ.

## 3.2. Kiến trúc tổng thể

### 3.2.1. Nguyên tắc thiết kế

Bốn nguyên tắc định hình mọi lựa chọn kiến trúc.

Thứ nhất, **tách quyền quyết định (authority separation)**. Quy tắc tất định trong PostgreSQL là nguồn sự thật cho trạng thái GDMT, chống chỉ định cứng, tương tác, và kế hoạch liều. LLM hỗ trợ dự phòng tiếp nhận, duyệt tài liệu biên khi nạp dữ liệu, mở rộng truy vấn, và giải thích tường thuật. Chúng không trở thành nguồn sự thật lâm sàng duy nhất.

Thứ hai, **an toàn trước văn bản (safety before prose)**. Kết quả có cấu trúc như bản nháp bệnh nhân, kiểm tra thiếu trường, khuyến nghị, và phán quyết kiểm chứng được đẩy tới bác sĩ trước khi token câu trả lời kết thúc. Cách này mã hóa nguyên tắc thời điểm của Osheroff trong thiết kế giao thức.

Thứ ba, **tri thức được quản trị (governed knowledge)**. Trích xuất tự động tạo bản nháp. Con người nâng cấp quy tắc thực thi được. Loader runtime bỏ qua hàng tinh chỉnh chưa xong.

Thứ tư, **thân thiện triển khai tại chỗ (on-premise friendliness)**. Stack chạy dạng đơn khối module hóa (modular monolith) với Docker Compose, embedding cục bộ, và sinh văn bản cục bộ để bệnh viện thí điểm không bắt buộc phụ thuộc LLM cloud.

### 3.2.2. Kiến trúc runtime ba tầng

Hệ thống tương tác theo bố cục ba tầng cổ điển.

**Tầng trình bày (presentation tier)** xây bằng React và Vite. Gồm bảng điều khiển bác sĩ cho chat lâm sàng và xem bằng chứng, cổng quản trị (admin portal) cho quản trị quy tắc, và API explorer cho phát triển. Client đăng ký luồng SSE và cập nhật panel lâm sàng khi sự kiện có cấu trúc đến.

**Tầng ứng dụng (application tier)** là đơn khối module hóa FastAPI. Điều phối tiếp nhận lai, dựng trạng thái lâm sàng, kiểm tra thiếu trường, truy xuất GraphRAG, suy luận tất định, tính liều, kiểm tra an toàn liều, tác tử kiểm chứng, tóm tắt thẻ, và sinh câu trả lời streaming. Thiết kế bất đồng bộ cho phép prefetch GraphRAG chạy song song với đánh giá engine quy tắc trên thread pool, nên lượt chat dài không đói admin hay yêu cầu health.

**Tầng dữ liệu (data tier)** dùng nhiều kho vì không có một CSDL cho mọi kiểu truy cập. PostgreSQL giữ catalog quy tắc có thể quản trị, lịch sử chat, bản nháp bệnh nhân, người dùng, và sự kiện kiểm toán. Redis cache lát phiên, tra cứu ràng buộc, giới hạn tốc độ, và hash phản hồi LLM lặp lại. ChromaDB lưu embedding dày cho truy xuất ngữ nghĩa. Neo4j giữ đồ thị thực thể-quan hệ cho sự kiện lâm sàng nhiều bước. Object storage tương thích S3 giữ bản tải thô và artifact JSONL đã xử lý cho pipeline tái lập được. Ollama host model embedding và sinh văn bản cục bộ.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TẦNG TRÌNH BÀY                                 │
│  Bảng điều khiển bác sĩ (React)  |  Cổng quản trị (React)  |  API Explorer │
└─────────────────────────────────────────────────────────────────────┘
                                  │  HTTPS / SSE
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         TẦNG ỨNG DỤNG                                │
│  Auth | Chat (SSE) | Intake | Reasoning | GraphRAG | Verification     │
│  Dose | Dose Safety | Explanation | Governance Admin | Health        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           TẦNG DỮ LIỆU                               │
│  PostgreSQL | Redis | ChromaDB | Neo4j | S3/LocalStack | Ollama      │
└─────────────────────────────────────────────────────────────────────┘
```

Chọn một container backend thay vì microservice vì đơn giản triển khai quan trọng hơn scale độc lập ở tải thí điểm. Ranh giới module nội bộ giữ khả năng kiểm thử và cho phép tách GraphRAG hoặc worker nạp dữ liệu sau nếu cần.

### 3.2.3. Kiến trúc hai mặt phẳng: Tri thức offline và suy luận online

Hệ thống hoàn chỉnh không chỉ là đường chat. Có hai mặt phẳng phối hợp.

**Mặt phẳng tri thức offline (offline knowledge plane)** thu nhãn DailyMed FDA và guideline suy tim, lọc mục lâm sàng liên quan, cắt đoạn văn bản, trích claim và quy tắc, phân loại tầng an toàn, và đồng bộ artifact vào PostgreSQL, ChromaDB, và Neo4j. Mặt phẳng này trả lời: tri thức y khoa vào hệ thống thế nào và duy trì ra sao?

**Mặt phẳng suy luận online (online reasoning plane)** nhận chat bác sĩ, dựng hồ sơ bệnh nhân, đánh giá quy tắc đã quản trị, truy xuất bằng chứng, xác minh nhất quán, và stream giải thích song ngữ. Mặt phẳng này trả lời: hệ thống giúp bác sĩ cho bệnh nhân này ngay bây giờ thế nào?

Không có mặt phẳng offline, chat không có gì đáng tin để thực thi hay trích dẫn. Không có mặt phẳng online, catalog chỉ là CSDL tĩnh. Chương 4 chi tiết cài đặt cả hai mặt phẳng; chương này quy định hợp đồng thiết kế và tương tác của chúng.

```
 Mặt phẳng offline                    Mặt phẳng online
 ┌──────────────────────┐              ┌──────────────────────────┐
 │ Thu nhãn/PDF         │              │ Chat + tệp đính kèm       │
 │ Lọc + cắt đoạn       │              │ Tiếp nhận lai             │
 │ Trích + phân loại    │─────────────▶│ Suy luận + liều/an toàn   │
 │ Sync PG/Chroma/Neo4j │   catalog    │ GraphRAG + kiểm chứng     │
 │ Admin duyệt/ngưng    │◀─────────────│ SSE thẻ + tường thuật     │
 └──────────────────────┘   phản hồi    └──────────────────────────┘
```

### 3.2.4. Luồng dữ liệu online đầu cuối

Khi bác sĩ gửi tin chat, xử lý theo trình tự cố định ưu tiên an toàn.

Xác thực thiết lập vai trò người gọi. Dịch vụ chat đảm bảo có mã hội thoại và thêm tin người dùng vào lịch sử. Tiếp nhận lai trích và gộp sự kiện bệnh nhân với mọi bản nháp trước của hội thoại đó. Dựng trạng thái lâm sàng chuẩn hóa đơn vị, suy eGFR thiếu khi có creatinine, tuổi, và giới, và gắn cờ rủi ro cùng lớp thuốc trọng tâm. Dịch vụ phát `draft_ready`.

Bộ kiểm tra thiếu trường quyết định xét nghiệm quan trọng có thiếu cho ý định suy ra không. Nếu có, pipeline phát `missing_check`, hỏi làm rõ, và trả về mà không tạo khuyến nghị. Cố ý cấm đoán điện giải hay phân suất tống máu.

Khi trường bắt buộc đủ, prefetch GraphRAG bắt đầu bất đồng bộ trong khi dựng khuyến nghị tất định chạy trên worker thread. Suy luận đánh giá chính sách GDMT, ràng buộc, tương tác, kế hoạch liều, và cảnh báo an toàn liều. Tác tử kiểm chứng chờ cả khuyến nghị và ngữ cảnh GraphRAG, rồi kiểm toán chặn cứng, dữ liệu thiếu, và có bằng chứng. Tóm tắt ngôn ngữ dễ hiểu và trường thẻ đơn giản hóa tất định gắn tiếp. Dịch vụ phát `recommendation_ready` và `verification_ready`.

Cuối cùng, lớp giải thích stream token `answer_delta` neo vào khuyến nghị đã kiểm chứng và bằng chứng truy xuất, rồi phát `done`. Thẻ và trạng thái an toàn vẫn là nguồn sự thật; văn tường thuật chỉ giải thích.

### 3.2.5. Kiến trúc đồ thị tri thức và truy xuất lai

Đồ thị tri thức xoay quanh thực thể suy tim liên kết lớp thuốc GDMT và hoạt chất. Kiểu thực thể gồm thuốc, lớp thuốc, bệnh, khái niệm xét nghiệm, và nút lâm sàng liên quan. Kiểu quan hệ gồm điều trị (treats), chống chỉ định với (contraindicated with), chỉ định cho (indicated for), tương tác với (interacts with), và cạnh theo dõi liên quan. Lúc runtime, GraphRAG gắn thuật ngữ thuốc bệnh nhân với nút đồ thị, truy xuất sự kiện lân cận, và gộp bằng chứng từ đồ thị với đoạn văn.

Truy xuất lai kết hợp bốn tín hiệu bổ sung. Mở rộng HyDE có thể biến câu hỏi ngắn của bác sĩ thành tài liệu trả lời giả định trước khi embedding, bắc cầu khoảng cách từ vựng. Tìm kiếm dày ChromaDB với BGE-M3 tìm ngôn ngữ guideline diễn đạt khác. Tìm kiếm thưa BM25 ưu tiên tên thuốc chính xác và cụm quy định. Duyệt lân cận Neo4j đưa ra sự kiện nhiều bước có thể bị chia qua ranh giới đoạn. Hợp nhất xếp hạng nghịch đảo (Reciprocal Rank Fusion, RRF) gộp danh sách xếp hạng mà không cần hiệu chuẩn điểm tay cứng. Reranking tùy chọn tinh chỉnh pool top khi ngân sách độ trễ cho phép.

Quy tắc PostgreSQL cung cấp thực thi có thể chạy. Đồ thị và chỉ mục vector cung cấp ngữ cảnh bằng chứng cho kiểm chứng và giải thích. Sự tách này là trái tim kiến trúc của luận văn: truy xuất neo ngôn ngữ; quy tắc điều khiển an toàn.

### 3.2.6. Bản đồ thành phần tầng ứng dụng

Trong ứng dụng FastAPI, các thành phần chính và trách nhiệm như sau.

Thành phần auth phát hành và xác thực token JWT, thực thi vai trò. Bộ điều phối chat sở hữu vòng đời hội thoại và thứ tự sự kiện SSE. Trích xuất tiếp nhận lâm sàng sở hữu dựng hồ sơ lai. Trợ giúp trạng thái lâm sàng và trích rủi ro nén hồ sơ thành cờ cho suy luận và truy xuất. Thành phần thiếu trường sở hữu cổng làm rõ fail-closed. Dịch vụ suy luận sở hữu dựng RecommendationResponse. Module chính sách GDMT, ràng buộc, tương tác, tính liều, và an toàn liều cung cấp họ quy tắc suy luận phụ thuộc. Chuẩn hóa thuốc ánh xạ chuỗi bề mặt sang khóa hoạt chất. GraphRAG và module truy xuất ngữ nghĩa gom bằng chứng. Xác thực trích dẫn và tác tử kiểm chứng kiểm toán nhất quán. Module giải thích cung cấp tóm tắt thẻ và sinh tường thuật LLM. Module quản trị hỗ trợ duyệt, ngưng, và diff cho admin. Adapter datastore tách chi tiết PostgreSQL, Redis, ChromaDB, Neo4j, và bootstrap artifact khỏi logic lâm sàng.

Bản đồ này cố ý rộng hơn phác thảo "chatbot cộng CSDL" đơn giản. Mỗi thành phần tồn tại vì một kiểu lỗi đã biết xuất hiện khi thiếu nó: không chuẩn hóa thì tương tác bỏ sót tên biệt dược; không cổng thiếu trường thì quy tắc chạy trên xét nghiệm chưa đủ; không kiểm chứng thì văn trôi chảy mâu thuẫn chặn cứng; không quản trị thì bản nháp trích xuất thành mối nguy runtime im lặng.

### 3.2.7. Ví dụ đi qua bệnh nhân mẫu

Xét nam 65 tuổi HFrEF, EF 30%, dùng bisoprolol 5 mg, eGFR 45, kali 4.2, chưa dùng ACE inhibitor hoặc MRA, hỏi tối ưu GDMT.

Tiếp nhận lai trích nhân khẩu, xét nghiệm, và thuốc. Vì trường số rõ, bước gộp LLM có thể bỏ qua, giữ trích xuất nhanh. Hệ thống phát `draft_ready` với trạng thái lâm sàng tập trung lớp ACE inhibitor hoặc ARNI, MRA, và thuốc ức chế SGLT2.

GraphRAG dựng truy vấn từ trạng thái này và có thể chạy mở rộng HyDE, tìm dày ChromaDB, tìm từ khóa BM25, và truy xuất lân cận Neo4j. RRF gộp kết quả xếp hạng thành tập bằng chứng giới hạn và sự kiện đồ thị.

Engine suy luận phân loại trạng thái thận giảm vừa, kali bình thường, và kiểu HF là HFrEF. Phân tích khoảng trống GDMT có thể cho ACE inhibitor hoặc ARNI cân nhắc, beta blocker tiếp tục có thể tăng liều, MRA cân nhắc, và thuốc ức chế SGLT2 cân nhắc, giả sử không có kích hoạt tránh cứng. Tính liều gắn kế hoạch khi có hàng catalog. Tác tử kiểm chứng pass hoặc cảnh báo theo bằng chứng và kiểm tra an toàn. Bộ tóm tắt thẻ gắn nhãn tiếng Việt và tiếng Anh. LLM stream tường thuật neo bằng chứng. Bảng điều khiển React cập nhật tóm tắt bệnh nhân, lưới GDMT, huy hiệu phán quyết, và văn chat dần dần. Tổng thời gian thường vài giây trên phần cứng đánh giá.

Nếu thiếu kali, cổng thiếu trường dừng lượt và hỏi giá trị trước khi có khuyến nghị MRA. Nhánh đó là phần kiến trúc, không phải xin lỗi cho trường hợp hiếm.

## 3.3. Thiết kế xây dựng tri thức offline

### 3.3.1. Mục tiêu mặt phẳng tri thức

Mặt phẳng offline phải biến tài liệu y khoa không đồng nhất thành ba dạng runtime đồng bộ: quy tắc có thể quản trị và thực thi trong PostgreSQL, đoạn văn tìm kiếm ngữ nghĩa trong ChromaDB, và sự kiện quan hệ trong Neo4j. Phải giữ nguồn gốc (provenance) để bác sĩ mở nguồn trích dẫn. Phải kiểm soát chi phí LLM khi nạp dữ liệu. Phải hỗ trợ tiếp tục và đồng bộ lại để vận hành cập nhật một họ catalog mà không tải lại toàn bộ.

### 3.3.2. Các giai đoạn pipeline

Thu thập (acquisition) tải blob thô bất biến từ DailyMed và nguồn guideline vào object storage. Nạp và xử lý phân tích XML, PDF, và HTML thành văn bản có nhận diện mục với mã ổn định và dạng thuốc, đơn vị chuẩn hóa. Lọc mục giữ phần lâm sàng liên quan qua thác ba tầng: khớp từ khóa cho tiêu đề chuẩn, tương đồng embedding cho tiêu đề diễn đạt khác, và duyệt LLM biên chỉ trong dải điểm không chắc. Cắt đoạn (chunking) chia mục giữ lại thành cửa sổ chồng lấn theo câu phù hợp truy xuất. Trích xuất dựng artifact ràng buộc, liều, tương tác, chính sách GDMT, và an toàn liều bằng regex trước và làm giàu LLM có schema khi mẫu thưa. Phân loại gán tầng an toàn và kiểu hành động. Đồng bộ upsert catalog vào PostgreSQL và chuẩn bị chỉ mục vector và đồ thị.

### 3.3.3. Hợp đồng quản trị giữa mặt phẳng offline và online

Hàng trích xuất mặc định vào trạng thái nháp hoặc tinh chỉnh khi điều kiện chưa đủ. Đầu mối lâm sàng xem trong cổng quản trị. Chỉ tầng thực thi đã duyệt nạp vào suy luận online. Ngưng quy tắc gỡ khỏi loader runtime sau khi vô hiệu cache, vẫn giữ lịch sử kiểm toán. Hợp đồng này đảm bảo tự động hóa tăng tốc catalog mà không triển khai im lặng logic không an toàn hoặc chưa hoàn chỉnh.

## 3.4. Thiết kế module chức năng

### 3.4.1. Module trích xuất hồ sơ bệnh nhân

Module chuyển chat tự do của bác sĩ và tệp đính kèm tùy chọn thành PatientProfile có kiểu. Trích số regex bắt LVEF, eGFR, kali, huyết áp, nhịp tim, cân nặng, và giá trị liên quan, kể cả manh mối song ngữ sau chuẩn hóa Unicode. Khớp từ điển ánh xạ chuỗi thuốc sang khóa hoạt chất, ưu tiên token dài nhất trước để giảm lỗi chuỗi con. Phát hiện phủ định chặn dương tính giả gần cụm như "no," "not," "denies," và tiếng Việt "không." Chuẩn hóa đơn vị gắn đơn vị chuẩn và giữ span thô để kiểm toán.

Gộp LLM có chọn chạy chỉ khi heuristic phát hiện độ tin thấp, như tường thuật dài hoặc manh mối mâu thuẫn. Gộp giữ xét nghiệm số từ regex hơn đoán model. Đầu ra nuôi dựng trạng thái lâm sàng, nén hồ sơ thành ý định, lớp trọng tâm, và giá trị chính cho dựng truy vấn GraphRAG.

### 3.4.2. Module thiếu trường và rủi ro

Module thiếu trường quyết định ý định hiện tại có thể đánh giá an toàn không. Nếu thiếu xét nghiệm quan trọng, trả lời nhắc làm rõ và chặn phát khuyến nghị. Trợ giúp trích rủi ro suy cờ như suy giảm thận, tăng kali, hạ huyết áp, nhịp chậm, và thiếu dữ liệu quan trọng. Các cờ đó thành đầu vào khớp ràng buộc. Tách suy rủi ro khỏi đánh giá quy tắc giữ cả hai kiểm thử được.

### 3.4.3. Module chuẩn hóa thuốc

Chuẩn hóa thuốc phân giải tên biệt dược, muối, và bí danh song ngữ sang khóa chuẩn dùng bởi logic tương tác và GDMT. Không module này, catalog viết theo mã hoạt chất sẽ bỏ sót nhiều nhắc tới văn bản tự do. Chuẩn hóa là bước liên kết giữa ngôn ngữ và catalog được quản trị.

### 3.4.4. Module dịch vụ suy luận

Dịch vụ suy luận tạo RecommendationResponse có thẩm quyền, không có LLM trên đường tới quan trọng. Chuẩn hóa dải trạng thái bệnh nhân, suy rủi ro, đánh giá chính sách GDMT theo trụ cột, khớp ràng buộc đã duyệt, đánh giá tập tương tác, gắn kế hoạch liều, và áp cảnh báo an toàn liều. Trạng thái tổng thể thành blocked nếu có tránh cứng, approved with warnings khi còn rủi ro vừa, hoặc approved nếu không. Chuỗi phiên bản quản trị ghi thế hệ catalog tạo kết quả.

Ba bất biến điều khiển module. Đầu ra LLM không bao giờ sửa trạng thái avoid. Quy tắc chặn cứng ghi đè văn truy xuất cho phép. Module sau không thể hoàn tác ràng buộc cứng đã kích hoạt.

### 3.4.5. Module tính liều và an toàn liều

Tính liều cá thể hóa liều khởi, liều đích, dải thận, và lịch tăng liều từ quy tắc JSONB. Bộ đánh giá phân giải khóa thuốc, áp dải eGFR, và phát kế hoạch liều đề xuất kèm đơn vị, tần suất, và lý do. Nếu hàng catalog chưa đủ, module không bịa liều mg.

An toàn liều bổ sung kế hoạch liều bằng cách đánh dấu liều dự kiến vượt mức tối đa từ nhãn cho trạng thái thận bệnh nhân. Sự tách này giữ "liều điển hình" khác "liều quá cao cho bệnh nhân này lúc này."

### 3.4.6. Module ràng buộc an toàn và tương tác

Quy tắc ràng buộc mang lớp mục tiêu, hành động, điều kiện, mức độ, tên rủi ro, và tham chiếu bằng chứng. Ràng buộc cứng không thể vi phạm. Ràng buộc mềm cảnh báo mà không tự chặn. Quy tắc tương tác lưu tập thuốc đối xứng hoặc có hướng kèm mức độ và văn xử lý. Cả hai họ chỉ nạp hàng đã duyệt lúc runtime và có thể cache theo lớp trong Redis, vô hiệu khi admin ghi.

### 3.4.7. Module GraphRAG và truy xuất ngữ nghĩa

GraphRAG gom ngữ cảnh giải thích cho kiểm chứng và sinh câu trả lời. Dựng truy vấn thu thập thuật ngữ từ tin bác sĩ, hồ sơ bệnh nhân, và trạng thái lâm sàng. HyDE có thể mở rộng truy vấn ngắn. Phân rã truy vấn có thể phát sub-query cho lượt phức tạp. Bộ truy xuất dày, thưa, và đồ thị chạy với pool top-k giới hạn. RRF gộp xếp hạng. Mở rộng cửa sổ sau hợp nhất khôi phục ngữ cảnh câu cục bộ. Lọc bằng chứng và chấm chất lượng loại đoạn yếu. Boost thực thể lâm sàng nâng đoạn nhắc thuốc bệnh nhân. Đầu ra gồm đoạn bằng chứng xếp hạng, sự kiện đồ thị, và metadata phạm vi.

### 3.4.8. Module kiểm chứng và trích dẫn

Tác tử kiểm chứng đối chiếu chéo khuyến nghị tất định trước khi tường thuật hoàn tất. Tác tử an toàn fail khi có tránh cứng và cảnh báo khi thận trọng. Tác tử dữ liệu thiếu cảnh báo khi xét nghiệm quan trọng vẫn trống. Tác tử bằng chứng fail khi truy xuất không trả đoạn hoặc sự kiện dùng được. Xác thực trích dẫn ánh xạ tham chiếu bằng chứng sang mã đoạn truy xuất và liên kết nguồn. Phán quyết gộp xuất hiện trong payload `verification_ready` và huy hiệu UI.

### 3.4.9. Module giải thích

Giải thích có hai lớp. Bộ tóm tắt thẻ ánh xạ tất định trường có cấu trúc sang nhãn tiếng Việt và tiếng Anh dễ hiểu mà không gọi LLM. Cách này giữ thẻ GDMT ổn định khi đổi ngôn ngữ. Dịch vụ câu trả lời LLM viết tường thuật hướng bác sĩ neo vào khuyến nghị đã kiểm chứng và bằng chứng truy xuất, stream dạng token delta. Tách hai lớp tránh sinh ngôn ngữ trang trí ghi đè trạng thái an toàn.

### 3.4.10. Module quản trị

Quản trị hỗ trợ liệt kê, chi tiết, diff, duyệt, ngưng, và lịch sử cho catalog ràng buộc, liều, tương tác, GDMT, và an toàn liều. Đầu mối lâm sàng tinh chỉnh điều kiện trích xuất chưa mã hóa hết. Trợ giúp duyệt hàng loạt có thể tồn tại cho lô tin cậy, vẫn dưới kiểm tra vai trò. Chế độ xem diff giúp người duyệt thấy thay đổi giữa lần chạy pipeline trước khi nâng cấp.

### 3.4.11. Module lưu hội thoại và kiểm toán

Hội thoại, tin nhắn, và bản nháp bệnh nhân lưu PostgreSQL để nạp lại lịch sử qua phiên. Redis có thể cache bản nháp nóng cho độ trễ. Sự kiện kiểm toán ghi dừng thiếu trường, kết quả khuyến nghị, và hành động quản trị kèm thời điểm và danh tính tác nhân. CDSS vẫn không phải EHR hệ thống hồ sơ toàn bệnh viện, nhưng dấu vết kiểm toán hội thoại và khuyến nghị là artifact thiết kế hạng nhất.

## 3.5. Thiết kế cơ sở dữ liệu và lưu trữ

### 3.5.1. PostgreSQL làm kho quản trị và hội thoại

PostgreSQL giữ catalog quy tắc có phiên bản. Quy tắc ràng buộc lưu mã, lớp mục tiêu, hành động, lý do, tên rủi ro, mức độ, tham chiếu bằng chứng, JSON nguồn lâm sàng, và metadata vòng đời nháp/đã duyệt/ngưng. Quy tắc liều lưu khóa thuốc, JSON liều khởi và đích, chỉnh thận, lịch tăng liều, và tầng an toàn. Quy tắc tương tác lưu tập thuốc, kiểu, mức độ, mô tả, và văn xử lý. Chính sách GDMT lưu định nghĩa lớp thực thi được. Cảnh báo an toàn liều lưu mức tối đa số và điều kiện liên quan. Bảng lịch sử giữ dấu vết thay đổi cho xem lại quản trị.

Bảng chat lưu hội thoại, tin nhắn, và bản nháp bệnh nhân theo mã hội thoại, xóa dây chuyền khi dọn. Người dùng và vai trò hỗ trợ xác thực. Bảng sự kiện kiểm toán hỗ trợ xem lại theo ca.

Schema này lấy quản trị làm trung tâm thay vì EMR bệnh viện đầy đủ. Logic quyết định lâm sàng có thẩm quyền nằm trong catalog đã duyệt. Trạng thái bệnh nhân cho hỗ trợ quyết định có thể thoáng qua qua lượt nhưng vẫn lưu đủ cho liên tục và kiểm toán.

### 3.5.2. Thiết kế cache Redis

Redis cache lát ràng buộc theo lớp thuốc, bản nháp và tin gần theo hội thoại, bộ đếm giới hạn tốc độ, và hash phản hồi LLM hoặc HyDE lặp. Mục cache không bao giờ là nguồn sự thật lâm sàng. Thao tác admin duyệt hoặc ngưng vô hiệu khóa liên quan để quy tắc cũ không tiếp tục chạy sau thay đổi quản trị. TTL giới hạn thời gian tường thuật bệnh nhân còn trong cache.

### 3.5.3. Thiết kế kho vector ChromaDB

Collection ChromaDB lưu mã đoạn, embedding BGE-M3, văn đoạn, và metadata như kiểu nguồn, lớp thuốc, mục, và kiểu đoạn. Metadata cho lọc trước và liên kết trích dẫn. Embedding tính offline khi nạp để GraphRAG tương tác chỉ là truy vấn láng giềng gần nhất, không phải job huấn luyện embedding.

### 3.5.4. Thiết kế kho đồ thị Neo4j

Neo4j lưu thực thể và quan hệ có kiểu import từ artifact pipeline. Truy vấn runtime mở rộng từ nút thuốc hoặc bệnh khớp vào lân cận giới hạn dùng làm sự kiện đồ thị. Đồ thị tối ưu cho truy xuất giải thích nhiều bước, không thay thế thực thi PostgreSQL. Sau làm mới catalog, import đồ thị hoặc bootstrap backend nạp lại quan hệ từ artifact đã xử lý.

### 3.5.5. Thiết kế object storage

Bucket thô và đã xử lý tách bản tải bất biến khỏi đầu ra JSONL chuẩn hóa. Cache và checkpoint theo địa chỉ nội dung làm chạy lại pipeline rẻ hơn. Bootstrap backend có thể hydrate chỉ mục runtime từ artifact đã xử lý mà không cần scrape lại nguồn upstream.

## 3.6. Thiết kế API

### 3.6.1. API chat

Đường bác sĩ chính là chat streaming dưới tiền tố API có phiên bản. Endpoint chat không stream có thể tồn tại cho client đơn giản. Endpoint lịch sử nạp lại tin và bản nháp cho hội thoại. Yêu cầu mang thông tin JWT, văn tin, mã hội thoại, trường bệnh nhân gieo sẵn tùy chọn, ưu tiên ngôn ngữ, và tệp đính kèm tùy chọn.

Thứ tự sự kiện SSE là hợp đồng API: khung trạng thái, `draft_ready`, `missing_check` khi cần, rồi hoặc `done` sớm hoặc chuỗi `recommendation_ready`, `verification_ready`, token `answer_delta`, và `done`. Client phải render lưới GDMT từ payload khuyến nghị, không từ token câu trả lời.

### 3.6.2. API lâm sàng hỗ trợ

Endpoint riêng lộ dựng khuyến nghị, gom ngữ cảnh GraphRAG, kiểm chứng, tính liều, kiểm tra an toàn thuốc, trợ giúp chuẩn hóa lâm sàng, tìm bằng chứng, tìm truy xuất, tra cứu đồ thị tri thức, và lịch sử kiểm toán ca. Các endpoint hỗ trợ bảng điều khiển bác sĩ, công cụ admin, demo API explorer, và kiểm thử tự động. Chúng cũng làm kiến trúc có thể soi: mỗi mối quan tâm có thể thử mà không chạy full đường SSE chat.

### 3.6.3. API auth, health, và admin

Route auth xử lý đăng nhập, người dùng hiện tại, và đăng xuất theo cookie hoặc bearer token tùy cấu hình. Route health lộ liveness, readiness, phiên bản, và trạng thái phụ thuộc PostgreSQL, Redis, ChromaDB, Neo4j, object storage, và Ollama. Route admin quản lý catalog quản trị dưới kiểm tra vai trò. Endpoint metrics có thể lộ bộ đếm vận hành cho giám sát.

### 3.6.4. Thiết kế lỗi và idempotency

Ngắt mạch thiếu trường là kết quả lâm sàng thành công, không phải sự cố server. Chúng trả làm rõ có cấu trúc. Lỗi thật phát trạng thái lỗi cuối trong stream hoặc mã HTTP lỗi cho route không stream. Khóa idempotency có thể cache phản hồi chat giống hệt để giảm tải GPU trùng khi thử lại.

## 3.7. Thiết kế giao diện người dùng

### 3.7.1. Bảng điều khiển bác sĩ

Bảng điều khiển bác sĩ dùng bố cục chia đôi: thanh bên hội thoại và luồng chat một bên, panel lâm sàng bên kia. Header có bật/tắt thanh bên, tiêu đề ca, điều khiển ngôn ngữ, và thao tác hội thoại như chat mới, xóa tin, và xóa hội thoại.

Luồng chat hiển thị lịch sử và stream token trợ lý. Panel lâm sàng cập nhật theo sự kiện có cấu trúc: ngữ cảnh bệnh nhân khi `draft_ready`, thẻ GDMT và an toàn khi `recommendation_ready`, huy hiệu kiểm chứng khi `verification_ready`, và trích bằng chứng để neo. Thẻ chỉ bind trường có cấu trúc và nhãn đơn giản hóa tất định. Thẻ bằng chứng nhấn tiêu đề tài liệu, trang, nhà xuất bản dễ đọc, và liên kết mở nguồn thay vì mã đoạn kỹ thuật.

Bố cục này mã hóa mô hình nhận thức. Khám phá hội thoại ở chat. Artifact quyết định quét nhanh ở panel. Bác sĩ đi vòng có thể đọc trạng thái mà không phải phân tích đoạn dài.

### 3.7.2. Cổng quản trị

Cổng quản trị có bảng catalog cho ràng buộc, quy tắc liều, tương tác, chính sách GDMT, và cảnh báo an toàn liều. Chế độ xem chi tiết hiện điều kiện, nguồn gốc, và điều khiển vòng đời. Chế độ xem diff làm nổi thay đổi giữa phiên bản. Tìm bằng chứng giúp người duyệt xem đoạn khi duyệt quy tắc. Cột hành động dính và tiêu đề lâm sàng ngắn giảm nhiễu thị giác để người duyệt tập trung ý nghĩa thuốc, hành động, và điều kiện.

### 3.7.3. API explorer và mối quan tâm UI dùng chung

API explorer giúp nhà phát triển và người đánh giá thử endpoint khi demo. Gói frontend dùng chung giữ định dạng bằng chứng và client API nhất quán giữa app bác sĩ và admin. Catalog tin nhắn song ngữ điều khiển chrome UI độc lập với suy luận lâm sàng.

## 3.8. Thiết kế topology triển khai

Dù Chương 4 nói lệnh cài đặt, hình dạng triển khai là quyết định kiến trúc. Docker Compose đặt cùng host thí điểm PostgreSQL, Redis, Neo4j, ChromaDB, Ollama, object storage, backend, frontend, và Nginx. Nginx chấm dứt HTTP, phục vụ UI bác sĩ ở gốc site, phục vụ admin dưới tiền tố đường dẫn, và proxy API cùng SSE với buffering tắt. GPU passthrough tới Ollama hỗ trợ sinh cục bộ. Health check chặn backend khởi động đến khi phụ thuộc sẵn sàng.

Topology này ưu tiên kiểm soát cơ sở và tái lập demo hơn đàn hồi hyperscale. Tách microservice ngang vẫn khả thi sau vì ranh giới module đã tách GraphRAG, suy luận, và quản trị.

## 3.9. Bảo mật và kiểm soát truy cập

### 3.9.1. Xác thực và phân quyền

Xác thực dùng token truy cập JWT xác thực trên route được bảo vệ. Token mã hóa subject và vai trò. Đăng xuất có thể blocklist hoặc xóa cookie theo chế độ triển khai. Phân quyền dùng vai trò như clinician hoặc doctor cho chat, clinical lead cho duyệt quy tắc, và admin cho truy cập hệ thống đầy đủ. Endpoint ghi quản trị thực thi kiểm tra vai trò và trả forbidden không tác dụng phụ khi không được phép.

### 3.9.2. Bảo vệ dữ liệu

TLS chấm dứt tại reverse proxy trong triển khai kiểu production. Kết nối CSDL nên dùng truyền mã hóa khi chính sách cơ sở yêu cầu. Bảo vệ khi lưu dựa thực hành mã hóa host và volume. TTL Redis giới hạn lộ tường thuật cache. Log nên tránh chi tiết lâm sàng không cần trong cấu hình production.

### 3.9.3. Tóm tắt mô hình mối đe dọa

Giả mạo người duyệt đặc quyền được giảm bằng JWT ký, claim vai trò, và hành động duyệt có kiểm toán; thông tin đăng nhập lộ vẫn là rủi ro tồn dư của cơ sở. Giả mạo yêu cầu trên đường truyền được giảm bằng TLS. Lo ngại chối bác bỏ được giải quyết bằng kiểm toán phía server payload chat và khuyến nghị. Rủi ro lộ thông tin từ cache và log giảm bằng TTL, kỷ luật redaction, và phân đoạn mạng. Từ chối dịch vụ chống GPU hoặc dung lượng CSDL được giảm bằng giới hạn tốc độ, pool truy xuất giới hạn, và khởi động có health gate. Thử nâng đặc quyền trên route admin bị chặn bằng dependency vai trò. Tiêm prompt vào tiếp nhận hoặc sinh câu trả lời được giảm bằng làm sạch gộp, kiểm chứng với trạng thái có cấu trúc, và quy tắc cứng model không thể ghi đè. Xem lại tường thuật của con người vẫn bắt buộc.

## 3.10. Truy vết thiết kế tới mục tiêu nghiên cứu

Kiến trúc trả lời trực tiếp mục tiêu nghiên cứu luận văn. Mặt phẳng offline và catalog quản trị giải quyết xây dựng tri thức bền vững từ nhãn FDA và guideline. Suy luận tất định cộng GraphRAG lai và kiểm chứng giải quyết khuyến nghị chính xác, fail-closed, kèm giải thích neo bằng chứng. Thẻ song ngữ qua SSE và liên tục hội thoại giải quyết quy trình bác sĩ dùng được. Mục tiêu phi chức năng về độ trễ, độ chính xác, và bảo mật ràng buộc lựa chọn công nghệ như suy luận Ollama cục bộ, cache Redis, và triển khai đơn khối module hóa.

## 3.11. Tóm tắt chương

Chương này quy định thiết kế hệ thống đầy đủ của CDSS suy tim. Yêu cầu bao phủ hỗ trợ quyết định lâm sàng, neo bằng chứng, dùng song ngữ, quản trị, và vận hành. Kiến trúc kết hợp stack online ba tầng với mặt phẳng xây tri thức offline. Thẩm quyền thuộc quy tắc PostgreSQL được quản trị; GraphRAG và LLM hỗ trợ truy xuất và giải thích; thứ tự SSE đưa artifact an toàn trước văn bản. Thiết kế module trải từ tiếp nhận, cổng thiếu trường, chuẩn hóa, suy luận, liều và an toàn liều, ràng buộc và tương tác, GraphRAG, kiểm chứng, giải thích, quản trị, lưu trữ, và kiểm toán. Phần lưu trữ, API, giao diện, triển khai, và bảo mật cho thấy các module được lộ và bảo vệ thế nào. Chương 4 ánh xạ thiết kế này sang cài đặt cụ thể, pipeline, và vận hành.
