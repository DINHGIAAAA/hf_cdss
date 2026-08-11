# CHƯƠNG 4: CÀI ĐẶT VÀ TRIỂN KHAI

Chương này mô tả cách triển khai thiết kế ở Chương 3: môi trường, pipeline nạp tri thức, backend chat, frontend và Docker Compose.

## 4.1. Môi trường phát triển

### 4.1.1. Cấu hình phần cứng

Cài đặt dùng laptop phát triển thông thường và một máy chủ ứng dụng riêng. Máy phát triển cần ít nhất tám lõi CPU, 16 GB RAM, và khoảng 100 GB SSD. GPU (Graphics Processing Unit) hữu ích nhưng không bắt buộc trên laptop vì job nạp dữ liệu qua đêm có thể chạy trên CPU. Máy chủ đánh giá và trình diễn dùng mười sáu lõi CPU, 32 GB RAM, SSD 500 GB, và GPU NVIDIA RTX 3080 với 10 GB bộ nhớ video.

GPU quan trọng vì lý do thực tế. Hệ thống chạy mô hình ngôn ngữ lớn (LLM) cục bộ qua Ollama để ca lâm sàng mẫu không cần rời mạng bệnh viện. Model sinh văn bản đã chọn, Qwen2.5-7B-Instruct, cần đủ bộ nhớ video để trả lời trong vài giây. Model embedding BGE-M3 cũng dùng GPU khi dựng hoặc tìm chỉ mục vector dày. Không có GPU, chat vẫn chạy nhưng độ trễ tăng và mục tiêu trung vị dưới mười giây khó đạt hơn. Sự tách giữa phát triển thân thiện CPU và chat tương tác có GPU là có chủ đích: kỹ sư viết và kiểm thử trên laptop vừa phải, bác sĩ đánh giá trên phần cứng gần trạm làm việc bệnh viện thực tế.

### 4.1.2. Stack phần mềm và lý do từng thành phần

Backend viết bằng Python 3.11. Chọn Python vì hệ sinh thái khoa học và y sinh trưởng thành, mạng bất đồng bộ mạnh, và thư viện xác thực kiểu như Pydantic tích hợp sạch với FastAPI. FastAPI là khung web. Nó nhận HTTP, xác thực JSON theo schema, và stream Server-Sent Events (SSE) tới trình duyệt. SSE là luồng một chiều đơn giản từ server tới client. Nó cho bảng điều khiển bác sĩ hiện bản nháp bệnh nhân và thẻ khuyến nghị trong khi câu trả lời hội thoại vẫn đang viết, giảm cảm giác chờ.

PostgreSQL 15 lưu catalog lâm sàng được quản trị: quy tắc ràng buộc, quy tắc liều, quy tắc tương tác, chính sách GDMT, cảnh báo an toàn liều, lịch sử chat, và sự kiện kiểm toán. PostgreSQL ở đây là nguồn sự thật an toàn. Mọi thứ có thể chặn hoặc duyệt điều trị phải nằm trong CSDL giao dịch mà quản trị viên xem, duyệt, hoặc ngưng.

Redis 7 cache dữ liệu phiên, bộ đếm giới hạn tốc độ, và phản hồi LLM lặp lại. Cache không thay quy tắc. Nó chỉ tăng tốc công việc lặp như nạp cùng lát ràng buộc nhiều lần trong giờ khám bận.

Neo4j 5 lưu đồ thị tri thức y khoa dạng nút và quan hệ. GraphRAG dùng Neo4j trả lời câu nhiều bước như thuốc nào tương tác qua đường chung. ChromaDB lưu embedding dày của đoạn bằng chứng để tìm kiếm ngữ nghĩa tìm đoạn liên quan dù cách diễn đạt bác sĩ khác văn nhãn. LocalStack cung cấp object store tương thích S3 khi phát triển. File XML FDA thô và artifact JSONL đã xử lý vào bucket có phiên bản để lần chạy pipeline tái lập được.

Ollama host model cục bộ. Sinh văn bản dùng `qwen2.5:7b` cho câu trả lời hướng bác sĩ. Trợ giúp nhẹ như mở rộng HyDE và prompt kiểm chứng có thể dùng model nhỏ hơn như `qwen2.5:1.5b`. Embedding dùng `bge-m3`. Giữ suy luận cục bộ hỗ trợ thí điểm nhạy quyền riêng tư và tránh chi phí cloud theo token.

Frontend dùng Node.js 18 trở lên, React 18, và Vite. React dựng giao diện tương tác. Vite đóng gói nhanh cho phát triển và production. Nginx đứng trước stack làm reverse proxy: phục vụ bảng điều khiển bác sĩ, định tuyến `/admin` tới cổng quản trị, và chuyển tiếp `/api` cùng SSE tới FastAPI.

### 4.1.3. Thiết lập môi trường

Thiết lập cục bộ theo thứ tự cố định để nhà phát triển không vướng thiếu CSDL. Đầu tiên clone repository. Tiếp theo tạo virtual environment Python và cài phụ thuộc backend từ `requirements.txt`. Gói frontend cài bằng `npm` trong thư mục doctor-dashboard. Docker Compose rồi khởi động PostgreSQL, Redis, Neo4j, ChromaDB, LocalStack, và Ollama. Cài đặt ứng dụng nạp từ `infrastructure/.env` dùng tên tiền tố `HF_CDSS_` để phát triển, Docker, và chạy pipeline dùng chung một từ vựng cấu hình.

Sau khi container healthy, Ollama pull model cần thiết một lần. Trọng số model lưu trong Docker volume, nên lần khởi động sau không tải lại. Dịch vụ FastAPI có thể start với Uvicorn. Khi phát triển, chế độ reload khởi động lại API khi file Python đổi. Máy chủ phát triển Vite proxy `/api` tới backend để code trình duyệt gọi cùng đường tương đối như production.

## 4.2. Pipeline xây dựng tri thức

### 4.2.1. Mục đích và các giai đoạn tổng quan

Hệ hỗ trợ quyết định lâm sàng (CDSS) chỉ đáng tin bằng cơ sở tri thức của nó. Gõ tay hàng nghìn cảnh báo nhãn vào CSDL chậm và dễ sai. Pipeline nạp dữ liệu vì vậy tự động hóa bốn giai đoạn rộng: thu nguồn thô, nạp và chuẩn hóa, trích artifact lâm sàng có cấu trúc, và lưu artifact vào PostgreSQL, ChromaDB, và Neo4j.

Bộ điều phối nằm trong `scraper/orchestration/run_ingestion_pipeline.py`. Vận hành có thể chạy full pipeline hoặc tiếp tục từ bước đặt tên như `kg_base`, `constraints`, `dose_rules`, `interaction_rules`, hoặc `gdmt_policies`. Checkpoint ghi bước đã xong để job qua đêm lỗi có thể tiếp tục mà không lặp phần thành công. Artifact publish vào bucket S3 đã xử lý trong khi file workspace cục bộ vẫn có để debug.

Idempotency là mục tiêu thiết kế hạng nhất. Hash nội dung và cache phản hồi LLM trên đĩa dưới `data/heart_failure/.ingestion_llm_cache/` ngăn prompt giống hệt gửi lại model khi chỉnh ngưỡng. Cờ `HF_CDSS_INGESTION_SKIP_DOWNLOAD=true` cho phép xử lý lại file đã stage mà không gọi DailyMed. Cơ chế này quan trọng vì lặp pipeline thường xuyên trong nghiên cứu, và gọi LLM cloud hoặc cục bộ lặp lại nếu không sẽ chi phối chi phí và thời gian.

### 4.2.2. Thu thập: Đưa nguồn vào hệ thống

Thu thập tải tài liệu có thẩm quyền và lưu không đổi. Với Nhãn sản phẩm có cấu trúc FDA, `scraper/acquisition/download_sources.py` truy vấn API DailyMed, phân giải tên thuốc sang mã bộ SPL, và tải nhãn XML. Guideline từ ESC, AHA/ACC, và HFSA đến dạng PDF hoặc HTML theo registry nguồn. Bổ sung tương tác có thể đến dạng JSON hoặc CSV đã biên soạn, đăng ký cùng nhãn.

Giữ file thô bất biến là cố ý. Nếu sau phát hiện lỗi parse, vận hành có thể parse lại cùng byte mà không đoán website upstream có đổi không. HTTP bất đồng bộ với `httpx` tải nhiều nhãn đồng thời, rút thời gian tường khi manifest có hàng chục hoạt chất liên quan GDMT.

Hạn chế thực tế xuất hiện khi tên biệt dược cục bộ hoặc cách viết đồng nghĩa thiếu trong registry thu thập. DailyMed khi đó không phân giải được sản phẩm, và thuốc đó không vào trích xuất. Khoảng trống này cùng vấn đề đồng nghĩa tiếng Việt sau này quan sát trong đánh giá tiếp nhận chat. Cài đặt ghi độ phủ registry để vận hành biết hoạt chất nào còn cần ánh xạ.

### 4.2.3. Nạp và xử lý tài liệu

Sau thu thập, giai đoạn nạp và biến đổi chuyển nhị phân thành văn bản có mục. Nhãn XML parse có nhận thức mục để tiêu đề FDA như liều, cảnh báo, chống chỉ định, và tương tác thuốc vẫn nhận ra được. Guideline PDF dùng trích văn bản có nhận thức bố cục. Guideline HTML được dọn chrome điều hướng trước khi phân đoạn mục.

Mỗi mục nhận mã ổn định, nguồn gốc tài liệu, và thống kê độ dài. Mã ổn định sau nối trích dẫn runtime về đúng đoạn nguồn bác sĩ có thể mở. Tên thuốc chuẩn hóa về khóa kiểu RxNorm khi có thể. Đơn vị xét nghiệm chuyển dạng chuẩn để quy tắc viết theo mmol/L kali so sánh công bằng với giá trị bệnh nhân trích từ chat.

### 4.2.4. Cắt đoạn cho truy xuất

Cắt đoạn chia mục dài thành đoạn phù hợp tìm kiếm vector. Bộ cắt trong `scraper/transform/chunk_sections.py` dùng cửa sổ theo câu khoảng 512 token có chồng lấn. Nó cộng dồn câu trọn đến gần hết ngân sách, rồi mang vài câu cuối sang đoạn sau. Chồng lấn tồn tại vì chống chỉ định thường trải hai câu: câu đầu nêu thuốc, câu sau nêu ngưỡng xét nghiệm. Cắt cứng giữa hai câu sẽ để mỗi đoạn thiếu.

Đoạn tốt cải thiện GraphRAG sau này. Truy xuất dày xếp hạng đoạn theo nghĩa. BM25 thưa xếp hạng theo từ chính xác. Cả hai cần ngữ cảnh cục bộ mạch lạc. Đoạn quá lớn làm loãng liên quan. Đoạn quá nhỏ mất ngôn ngữ điều kiện. Cửa sổ 512 token chồng lấn là thỏa hiệp kỹ thuật dùng xuyên suốt đánh giá.

### 4.2.5. Lọc mục ba tầng

Không phải mọi mục trong nhãn thuốc đều hữu ích lâm sàng cho hỗ trợ quyết định suy tim. Hướng dẫn bảo quản và chi tiết đóng gói hiếm giúp suy luận GDMT. Gửi mọi mục vào LLM tốn kém và chậm. Bộ lọc mục trong `scraper/semantic/section_filter.py` vì vậy áp ba tầng.

Tầng một khớp tiêu đề giá trị cao bằng từ khóa như liều, cảnh báo, chống chỉ định, và tương tác thuốc. Mục khớp giữ ngay. Tầng hai embed tiêu đề và đoạn mở bằng BGE-M3 và so với vector mẫu cho kiểu mục lâm sàng. Điểm từ 0.52 trở lên được giữ. Tầng ba chỉ duyệt dải không chắc từ 0.40 đến 0.52 bằng prompt LLM ngắn giữ hay bỏ. Điểm dưới 0.40 bỏ không gọi LLM. Giới hạn cứng 400 lần gọi LLM biên mỗi lần chạy chặn chi phí tệ nhất.

Thác này là bản song song offline của tiếp nhận chat lai. Phương pháp tất định nhanh xử lý ca rõ. Embedding xử lý diễn đạt khác. LLM chỉ tiêu ngân sách nơi không chắc thật. Trong đánh giá, bộ lọc giữ khoảng 95 phần trăm mục trong khi chỉ gọi duyệt LLM biên trên khoảng 6.6 phần trăm đầu vào.

### 4.2.6. Trích xuất artifact lâm sàng có cấu trúc

Trích xuất chuyển văn bản giữ lại thành đối tượng runtime có thể đánh giá. Nhiều builder chuyên biệt phối hợp. Trích quy tắc ràng buộc tạo câu tránh và thận trọng có điều kiện. Trích quy tắc liều bắt liều khởi, liều đích, dải thận, và lịch tăng liều. Trích tương tác dựng cặp tập thuốc kèm mức độ và văn xử lý. Trích chính sách GDMT mã hóa kỳ vọng phủ bốn trụ cột cho HFrEF. Trích cảnh báo an toàn liều bắt mức tối đa trên nhãn phải kích hoạt khi liều dự kiến vượt giới hạn an toàn cho dải thận bệnh nhân.

Chiến lược lai là regex trước, LLM sau. Cụm từ SPL tần suất cao rẻ khi khớp mẫu. Khi mẫu thưa, `scraper/semantic/rule_builder.py` gọi API chat Ollama cục bộ với JSON schema xác thực bởi Pydantic. JSON không hợp lệ bị loại trước khi vào luồng artifact. Hash prompt nuôi cache nạp dữ liệu để mục giống nhau không tiêu token mỗi lần chạy lại.

Nhận diện thực thể có tên (Named Entity Recognition, NER) và liên kết quan hệ gắn thuốc, lớp, xét nghiệm, và bệnh với mỗi claim. Liên kết bằng chứng lưu mã đoạn để thẻ khuyến nghị sau hiện đoạn thúc đẩy quy tắc. Khử trùng lặp gộp trích xuất gần giống từ mục nhãn chồng lấn.

### 4.2.7. Phân loại và cổng quản trị

Phân loại gán khả năng triển khai trước khi quy tắc tới bác sĩ. Tầng an toàn gồm `hard_block` cho chống chỉ định tuyệt đối, `usable_rules` cho điều kiện thực thi đủ, và `needs_condition_refinement` cho bản nháp parse được nhưng còn cần làm rõ của con người. Kiểu hành động gồm avoid, consider with caution, consider, và continue. Nhãn này ánh xạ trực tiếp huy hiệu thẻ khuyến nghị trên bảng điều khiển bác sĩ.

Quy tắc đánh dấu tinh chỉnh đồng bộ PostgreSQL cho admin xem thay vì biến mất. Loader runtime bỏ qua bản nháp chưa xong đến khi clinical lead nâng cấp. Cổng này thiết yếu. Trích xuất tự động mạnh, nhưng an toàn suy tim không thể phụ thuộc đoán model chưa duyệt.

### 4.2.8. Đồng bộ tới kho runtime

Giai đoạn store upsert catalog đã duyệt và nháp vào PostgreSQL, publish JSONL đã xử lý lên S3, và chuẩn bị artifact hydrate ChromaDB và Neo4j. Bootstrap backend có thể kéo artifact đã xử lý khi khởi động để container mới không cần scrape lại DailyMed. Vận hành cũng có thể dựng lại chỉ mục đồ thị và vector từ `kg_base` mà không lặp thu thập khi chỉ embedding hoặc quan hệ cần làm mới.

PostgreSQL vẫn có thẩm quyền cho quy tắc thực thi. ChromaDB và Neo4j làm giàu giải thích và kiểm chứng. Redis không bao giờ được coi nhà dài hạn của sự thật lâm sàng. Sự tách giữ dấu vết kiểm toán và quy trình admin tập trung một catalog quan hệ.

## 4.3. Cài đặt backend

### 4.3.1. Bố cục đơn khối module hóa

Backend là đơn khối module hóa: một tiến trình FastAPI, nhiều module nội bộ ranh giới rõ. `app/main.py` nối route và tác vụ khởi động. Gói domain dưới `app/modules/` gồm điều phối chat, trích xuất tiếp nhận lâm sàng, dựng ràng buộc, tính liều, an toàn liều, GraphRAG, suy luận, tác tử kiểm chứng, trợ giúp giải thích, và adapter datastore. Schema dưới `app/schemas/` định nghĩa hợp đồng dùng chung bởi payload SSE, ánh xạ CSDL, và JSON hướng TypeScript frontend.

Bố cục này khớp yêu cầu Chương 3. Tiếp nhận sở hữu phân tích hồ sơ bệnh nhân. Suy luận sở hữu quyết định GDMT và tương tác. Module liều sở hữu kế hoạch tăng liều. Module ràng buộc và an toàn liều sở hữu cảnh báo. GraphRAG sở hữu gom bằng chứng. Module giải thích sở hữu nhãn thẻ song ngữ và sinh tường thuật. Adapter datastore tách chi tiết SQL, Redis, Chroma, và Neo4j để logic lâm sàng dễ đọc.

### 4.3.2. Điều phối chat và thứ tự sự kiện SSE

Điểm vào chat streaming là `stream_chat` trong `app/modules/chat/service.py`. Nó biến một tin bác sĩ thành chuỗi sự kiện SSE có thứ tự. Thứ tự có chủ đích và có ý nghĩa lâm sàng.

Đầu tiên dịch vụ phát sự kiện trạng thái xác nhận đã nhận và đảm bảo có mã hội thoại. Nó thêm tin người dùng vào lịch sử. Rồi trích sự kiện bệnh nhân từ tin mới, gộp với mọi bản nháp trước của hội thoại đó, và dựng đối tượng trạng thái lâm sàng chuẩn hóa đơn vị và suy eGFR thiếu khi có creatinine, tuổi, và giới. Bản nháp gộp được lưu và stream dạng `draft_ready`.

Tiếp theo bộ kiểm tra thiếu trường quyết định xét nghiệm quan trọng có thiếu cho ý định suy ra không. Nếu thiếu kali và quyết định MRA trong phạm vi, pipeline ngắt mạch. Nó hỏi giá trị thiếu thay vì đoán. Hành vi đó bảo vệ bệnh nhân khỏi khuyến nghị không an toàn im lặng.

Khi trường bắt buộc đủ, prefetch GraphRAG bắt đầu dạng tác vụ bất đồng bộ trong khi dựng khuyến nghị tất định chạy trên worker thread. Chuyển sang thread giữ vòng lặp sự kiện FastAPI rảnh cho API khác trong lúc đánh giá quy tắc PostgreSQL. Sau khi cả hai xong, tác tử kiểm chứng kiểm toán khuyến nghị với chặn cứng và bằng chứng truy xuất. Tóm tắt ngôn ngữ dễ hiểu và trường thẻ đơn giản hóa tất định gắn tiếp. Dịch vụ rồi phát `recommendation_ready` và `verification_ready` trước khi sinh câu trả lời hội thoại.

Sinh câu trả lời stream token `answer_delta` neo vào đối tượng khuyến nghị đã kiểm chứng. Nó không bịa trạng thái liều mới. Sự kiện `done` cuối mang payload phản hồi đầy đủ cho client thích một snapshot cuối lượt.

Cài đặt này mã hóa nguyên tắc thời điểm Osheroff trong phần mềm: thông tin có cấu trúc quan trọng đến trước khi văn tường thuật kết thúc.

### 4.3.3. Tiếp nhận lâm sàng lai

Tiếp nhận lâm sàng chuyển chat lộn xộn thành trường có kiểu. Biểu thức chính quy (regex) bắt mẫu số như "EF 30%", "eGFR 45", và "K+ 4.2". Từ điển ánh xạ chuỗi thuốc, kể cả bí danh tiếng Việt và tên biệt dược, sang khóa thuốc nội bộ. Xử lý phủ định ngăn "not on ACE inhibitor" thành thuốc đang dùng. Chuẩn hóa đơn vị chuyển biểu thức xét nghiệm liên quan thành giá trị so sánh được.

Khi độ tin regex thấp, đường trích xuất LLM có chọn đề xuất trường bổ sung. Gộp ưu tiên giá trị đo regex hơn đề xuất model. Ưu tiên đó là triết lý nhận thức lâm sàng mã hóa trong code: số kiểu dụng cụ đo thắng đoán xác suất. Lịch sử hội thoại cũng có thể đóng góp sự kiện đã nói trước để chat nhiều lượt tích lũy hồ sơ thay vì bắt bác sĩ gõ lại mọi thứ.

Tệp đính kèm như ghi chú dán hoặc file văn bản tải lên nối vào tin trích xuất. Tài liệu lâm sàng trong yêu cầu gộp vào đối tượng bệnh nhân khi có. Kết quả là `PatientProfile` đủ giàu cho đánh giá quy tắc nhưng vẫn truy vết được tới lời bác sĩ đã gõ.

### 4.3.4. Engine suy luận tất định

Dịch vụ suy luận dựng đối tượng khuyến nghị có cấu trúc từ catalog PostgreSQL. Nó đánh giá phủ lớp GDMT cho ACE inhibitor hoặc ARB hoặc ARNI, beta blocker, MRA, và thuốc ức chế SGLT2. Với mỗi lớp gán trạng thái như start, continue, caution, hoặc avoid. Quy tắc ràng buộc khớp cờ rủi ro và xét nghiệm bệnh nhân. Quy tắc tương tác so tập thuốc đã chuẩn hóa. Quy tắc liều tạo kế hoạch khởi và đích khi catalog có hàng đủ cho hoạt chất và dải thận.

Không có LLM trên đường tới quan trọng này. Tái lập và kiểm toán đòi hỏi cùng trạng thái bệnh nhân cho cùng trạng thái có cấu trúc. GraphRAG sau có thể giải thích vì sao trạng thái xuất hiện, nhưng không thể đảo chặn cứng thành duyệt.

### 4.3.5. Cài đặt dịch vụ GraphRAG

Gom GraphRAG chủ yếu trong `app/modules/graphrag/service.py` với trợ giúp mở rộng HyDE, phân rã truy vấn, lập chỉ mục BM25, hợp nhất RRF, và reranking tùy chọn.

Dựng truy vấn thu thập thuật ngữ từ tin bác sĩ, hồ sơ bệnh nhân, và trạng thái lâm sàng. Nếu truy vấn ngắn hoặc mơ hồ, HyDE có thể sinh tài liệu trả lời giả định và embed tài liệu đó thay vì câu hỏi thô ngắn. Mục đích là bắc cầu từ vựng: bác sĩ gõ "Start MRA?" vẫn truy xuất được đoạn bàn spironolactone, eplerenone, kali, và theo dõi thận.

Truy xuất dày truy vấn ChromaDB lấy đoạn bằng chứng gần nhất. Truy xuất BM25 thưa ưu tiên tên thuốc chính xác và cụm quy định. Truy vấn lân cận Neo4j gom sự kiện đồ thị nhiều bước quanh thuốc và bệnh khớp. Reciprocal Rank Fusion gộp danh sách xếp hạng bằng công thức ổn định thưởng đoạn xuất hiện cao trên nhiều danh sách. Reranking ngữ nghĩa tùy chọn sắp xếp lại ứng viên top sau hợp nhất khi ngân sách độ trễ cho phép.

Bộ lọc metadata có thể giới hạn ứng viên theo lớp thuốc hoặc kiểu đoạn khi trạng thái lâm sàng đã tập trung hội thoại. Chấm chất lượng và lọc bằng chứng loại đoạn yếu hoặc ngoài phạm vi trước khi tới model giải thích. Trợ giúp trích dẫn gắn liên kết nguồn để panel Bằng chứng mở trang DailyMed hoặc guideline.

Chỉ mục BM25 dựng lại trong bộ nhớ khi backend khởi động từ metadata đoạn đã publish. Lựa chọn này ưu tiên độ trễ truy vấn thấp hơn cập nhật tăng dần liên tục. Sau làm mới tri thức, khởi động lại hoặc nạp lại backend dựng lại chỉ mục thưa từ artifact mới.

### 4.3.6. Tác tử kiểm chứng

Kiểm chứng chạy sau khi khuyến nghị và GraphRAG hoàn tất. Tác tử kiểm tra câu hỏi nhất quán mà quy tắc hay truy xuất một mình không phủ hết. Chặn cứng có kích hoạt trong khi tường thuật nghe có vẻ cho phép không? Truy xuất có trả bằng chứng cho claim được trích dẫn không? Thuốc khuyến nghị có khớp danh sách thuốc đã chuẩn hóa không? Model nhẹ có thể hỗ trợ kiểm tra diễn đạt, nhưng chặn cứng fail-closed vẫn đến từ catalog tất định.

Kết quả kiểm chứng stream tới UI dạng huy hiệu và payload có cấu trúc. Chúng cho bác sĩ tín hiệu thứ hai bên cạnh thẻ khuyến nghị.

### 4.3.7. Bộ tóm tắt thẻ và sinh câu trả lời

Bộ tóm tắt thẻ ánh xạ trường có cấu trúc sang nhãn tiếng Việt và tiếng Anh dễ hiểu mà không gọi LLM. Mã lớp thuốc thành cụm đọc được. Mã trạng thái thành văn huy hiệu. Vì ánh xạ tất định, thẻ ổn định khi đổi ngôn ngữ và không nhấp nháy khi giọng tường thuật đổi.

Sinh câu trả lời viết giải thích hướng bác sĩ neo vào khuyến nghị đã kiểm chứng và bằng chứng truy xuất. Token streaming cập nhật luồng chat. Quy tắc kiến trúc không đổi: thẻ và trạng thái an toàn có thẩm quyền; văn bản giải thích.

### 4.3.8. Lưu trữ, cache, và kiểm toán

Bản nháp bệnh nhân, tin nhắn, và artifact khuyến nghị lưu qua adapter datastore. Redis có thể cache bản nháp và phản hồi idempotent để yêu cầu giống hệt không tính lại mọi thứ. Sự kiện kiểm toán ghi dừng thiếu trường, kết quả khuyến nghị, và hành động quản trị. Log này hỗ trợ xem lại lâm sàng và debug sau mà không chỉ đọc log ứng dụng thô.

## 4.4. Cài đặt frontend

### 4.4.1. Cấu trúc ứng dụng

Monorepo frontend dưới `frontend/` gồm bảng điều khiển bác sĩ, cổng quản trị, và gói dùng chung cho client API và trợ giúp hiển thị. Bảng điều khiển bác sĩ là bề mặt lâm sàng chính. Gồm thành phần runtime chat, panel lâm sàng bên, điều khiển thanh bên hội thoại, duyệt bằng chứng, và catalog tin nhắn song ngữ.

Trạng thái hội thoại có thể lưu cục bộ để bác sĩ quay lại ca. Tạo hội thoại ghi tên bệnh nhân và mở tin chào mừng. Xóa hoặc xóa sạch hội thoại gỡ lịch sử cục bộ và đưa UI về thiết lập ca sạch khi cần. Các điều khiển nghe nhỏ nhưng quan trọng cho khả dụng khi demo và xem nhiều ca.

### 4.4.2. Client SSE và render dần

Module client tiêu thụ luồng chat phân tích khung SSE và điều phối theo kiểu sự kiện. Khi `draft_ready` đến, panel lâm sàng có thể hiện sinh hiệu và thuốc trích được. Khi `recommendation_ready` đến, thẻ GDMT render. Khi `verification_ready` đến, huy hiệu kiểm chứng cập nhật. Token câu trả lời nối vào tin trợ lý khi stream.

Render dần không chỉ trang trí. Nó thực thi cùng thứ tự ưu tiên an toàn như backend. Bác sĩ có thể đọc lời khuyên có cấu trúc trước khi đoạn văn đầy đủ kết thúc, hữu ích khi đi vòng mà từng giây quan trọng.

### 4.4.3. Panel lâm sàng và thẻ bằng chứng

Panel lâm sàng hiện ngữ cảnh bệnh nhân, thẻ khuyến nghị, kế hoạch liều khi có, và trích bằng chứng. Thẻ khuyến nghị chỉ bind trường có cấu trúc và nhãn đơn giản hóa. Chúng không suy trạng thái avoid hay continue từ token văn tự do. Thẻ bằng chứng nhấn tiêu đề tài liệu, số trang, nhà xuất bản, và trích dẫn dễ đọc thay vì mã đoạn kỹ thuật. Liên kết "Open source" đưa bác sĩ tới nhãn hoặc guideline gốc khi có URL.

### 4.4.4. Chuyển đổi ngôn ngữ

`LanguageProvider` lưu locale ưu tiên, cập nhật thuộc tính accessibility, và cung cấp hàm dịch cho component. Chuyển giữa tiếng Việt và tiếng Anh tái sinh nhãn thẻ và chrome UI. Mã hội thoại và trạng thái bệnh nhân có cấu trúc không đổi. Vì đơn giản hóa tất định và rẻ, chuyển ngôn ngữ dưới hai giây trong đánh giá mà không chạy lại GraphRAG hay suy luận.

### 4.4.5. Cài đặt cổng quản trị

Cổng quản trị lộ bảng quản trị cho ràng buộc, quy tắc liều, tương tác, chính sách GDMT, và catalog liên quan. Clinical lead có thể mở bản ghi, xem nguồn gốc, tinh chỉnh điều kiện, duyệt quy tắc dùng được, hoặc ngưng quy tắc lỗi thời. Trang tìm bằng chứng giúp người duyệt xem đoạn truy xuất khi biên soạn catalog. Cột hành động dính và nhãn hiển thị ngắn giảm rối để người duyệt tập trung ý nghĩa lâm sàng thay vì mã thô.

Quy trình admin khép vòng với pipeline nạp dữ liệu. Trích xuất có thể nháp hàng nghìn quy tắc, nhưng chỉ tầng thực thi đã duyệt ảnh hưởng khuyến nghị chat. Cổng con người là phần cài đặt, không phải suy nghĩ sau.

### 4.4.6. Luồng duyệt và ngưng trong admin

Khi clinical lead mở ràng buộc nháp trong cổng quản trị, UI hiện đối tượng điều kiện, lý do, bằng chứng liên kết, và trạng thái quản trị hiện tại. Duyệt bản ghi cập nhật PostgreSQL và có thể vô hiệu cache Redis giữ lát catalog cũ. Ngưng quy tắc giữ hàng lịch sử cho kiểm toán nhưng gỡ khỏi loader runtime. Sửa điều kiện có thể chuyển quy tắc từ `needs_condition_refinement` sang `usable_rules` sau xác thực. Thao tác này nghe hành chính, nhưng là trái tim vận hành của khả năng bảo trì: dịch vụ chat không cần deploy code chỉ vì nhãn thêm cảnh báo kali mới.

Diff phiên bản và panel chi tiết giúp người duyệt thấy thay đổi giữa lần chạy pipeline. Panel điều kiện bề mặt hóa predicate có cấu trúc vốn ẩn trong JSON. Trang danh sách catalog dùng tiêu đề lâm sàng ngắn với mã kỹ thuật để thứ yếu để người duyệt quét theo thuốc và hành động thay vì chuỗi hash.

### 4.4.7. Gói dùng chung và client API

Gói frontend dùng chung tập trung trợ giúp HTTP, định dạng hiển thị bằng chứng, và render trường quản trị. App bác sĩ và admin vì vậy hiện nhãn nhất quán cho cùng catalog nền. Client API mã hóa đường như chat stream, lịch sử, tìm bằng chứng, và endpoint danh sách admin một lần, giảm logic fetch trùng và giữ header xác thực nhất quán giữa trang.

## 4.5. Triển khai hệ thống

### 4.5.1. Topology Docker Compose

Docker Compose điều phối PostgreSQL, Redis, Neo4j, ChromaDB, Ollama, LocalStack, backend FastAPI, dịch vụ frontend, và Nginx. Health check trì hoãn khởi động backend đến khi CSDL và dịch vụ model sẵn sàng. GPU passthrough tới container Ollama được cấu hình trên host có NVIDIA Container Toolkit.

Mỗi dịch vụ có việc rõ. PostgreSQL lưu sự thật được quản trị. Redis tăng tốc đọc nóng. Neo4j trả lời truy vấn quan hệ. ChromaDB trả lời truy vấn đoạn ngữ nghĩa. Ollama chạy embedding và sinh văn bản. LocalStack lưu artifact thô và đã xử lý. Backend điều phối lâm sàng. Frontend trình bày quy trình bác sĩ và quản trị. Nginx thống nhất truy cập qua một cổng host.

Chọn Compose thay Kubernetes ở quy mô đánh giá. Thí điểm một host phục vụ khoảng hàng chục người dùng đồng thời không biện minh overhead vận hành Kubernetes. Đơn khối module hóa sau có thể tách GraphRAG hoặc Ollama thành dịch vụ riêng nếu hồ sơ tải đòi hỏi.

Volume lưu file CSDL, trọng số model, và dữ liệu object store qua lần khởi động lại. Không volume, mỗi reboot Compose buộc tải lại model và catalog rỗng, không chấp nhận được cho demo lâm sàng lặp.

### 4.5.2. Định tuyến Nginx

Nginx chấm dứt HTTP và định tuyến theo đường dẫn. Bảng điều khiển bác sĩ phục vụ ở gốc site. Cổng quản trị phục vụ dưới `/admin`. API và SSE dưới `/api` proxy tới FastAPI với buffering tắt để luồng flush kịp. Một origin đơn giản hóa bảo mật trình duyệt bằng tránh phức tạp cross-origin trong production.

### 4.5.3. Quản lý cấu hình

Ngưỡng và tên model nằm trong biến môi trường. Ví dụ gồm URL CSDL, URL Redis, URL cơ sở Ollama, tên model sinh và embedding, thông tin đăng nhập Neo4j, host Chroma, endpoint và tên bucket S3, secret JWT, origin CORS, ngưỡng tương đồng lọc mục, bật LLM biên, và cài đặt top-k truy xuất. Vận hành có thể chỉnh chi phí và chất lượng mà không sửa mã Python. Điều này quan trọng khi PDF guideline mới dùng tiêu đề lạ và ngưỡng lọc mục cần điều chỉnh.

### 4.5.4. Đánh đổi triển khai

Ollama cục bộ được ưu tiên hơn API LLM cloud để giữ ca lâm sàng trong viện, kiểm soát độ trễ, và tránh phí theo token. Đánh đổi là chi phí vốn GPU và vận hành model. LocalStack được ưu tiên hơn S3 cloud khi phát triển để hành vi SDK giống nhau mà không cần tài khoản cloud. Production có thể chuyển MinIO hoặc AWS S3 mà không đổi bố cục artifact. Neo4j Community và ChromaDB đặt cùng stack để embedding và sự kiện đồ thị vẫn dưới kiểm soát cơ sở; khôi phục thảm họa dựng lại chỉ mục từ artifact S3 đã xử lý khi cần.

## 4.6. Kiểm thử

### 4.6.1. Triết lý kiểm thử

Kiểm thử theo kiến trúc lai. Module tất định phải pass mà không phụ thuộc ngẫu nhiên model. Thành phần sinh văn bản được mock trong tích hợp liên tục (CI) để không cần GPU cho mọi pull request. Độ chính xác lâm sàng vẫn cần bác sĩ tim mạch xem, báo cáo ở Chương 5, vì phán đoán ca lâm sàng mẫu không tự động hóa hết.

### 4.6.2. Kiểm thử đơn vị

Kiểm thử đơn vị bao phủ ánh xạ bộ tóm tắt thẻ, ưu tiên gộp tiếp nhận cho giá trị đo, phát hiện phủ định, suy eGFR, khớp ràng buộc, chọn dải thận liều, bất biến xếp hạng RRF, và kiểm tra vai trò JWT trên route admin. Các test fail nhanh khi ánh xạ an toàn hoặc chính sách gộp đổi nhầm.

### 4.6.3. Kiểm thử tích hợp

Kiểm thử tích hợp lái pipeline chat với phản hồi Ollama mock. Chúng khẳng định ca HFrEF điển hình tạo bản nháp bệnh nhân và khuyến nghị, sự kiện SSE đến đúng thứ tự bắt buộc, và thiếu kali chặn phát khuyến nghị khi cần đánh giá MRA. Test GraphRAG dùng embedding fixture xác minh hành vi hợp nhất và lọc.

### 4.6.4. Kiểm thử pipeline

Test nạp dữ liệu kiểm tra biên tầng lọc mục, phân loại hard-block cho mẫu washout ACE inhibitor và ARNI, idempotency upsert PostgreSQL, và vô hiệu cache sau duyệt admin. Báo cáo chất lượng dữ liệu so sánh số lượng catalog với baseline vàng để hồi quy pipeline im lặng hiện rõ.

### 4.6.5. Kiểm thử frontend

Test frontend bao phủ phân tích khung SSE, lưu ưu tiên ngôn ngữ, và fallback thẻ khuyến nghị khi thiếu trường đơn giản hóa. Fixture SSE ghi lại phát lại cập nhật panel dần mà không cần backend sống.

## 4.7. Vận hành và bảo trì

### 4.7.1. Giám sát sức khỏe

Route health lộ liveness, readiness, và probe phụ thuộc. Liveness xác nhận tiến trình nhận yêu cầu. Readiness xác nhận hydrate khởi động xong. Kiểm tra phụ thuộc báo kết nối PostgreSQL, Redis, ChromaDB, Neo4j, S3, và Ollama riêng để vận hành thấy subsystem nào lỗi. Log có cấu trúc gồm mã hội thoại và thời gian từng giai đoạn, sau hỗ trợ phân rã độ trễ trong đánh giá.

### 4.7.2. Sao lưu và phục hồi

Dump PostgreSQL bảo vệ catalog quản trị và bản ghi chat. Volume Neo4j và Chroma có thể snapshot, nhưng chỉ mục cũng dựng lại từ artifact đã xử lý. Kế hoạch phục hồi vì vậy coi catalog quan hệ là chính và kho vector hoặc đồ thị là dẫn xuất có thể dựng lại. Lập trường này khớp mô hình thẩm quyền lúc runtime.

### 4.7.3. Làm mới tri thức y khoa

Khi nhãn FDA hoặc guideline đổi, vận hành chạy lại nạp dữ liệu từ bước phù hợp, đồng bộ catalog vào PostgreSQL, xem quy tắc nháp trong cổng quản trị, duyệt nâng cấp, và nạp lại chỉ mục truy xuất. Giám sát số lần gọi LLM biên khi nạp lại giúp phát hiện lệch bố cục tài liệu. Ưu tiên chỉnh từ điển từ khóa hoặc ngưỡng tương đồng hơn tắt hẳn duyệt biên, vì dải không chắc tồn tại đúng cho tiêu đề lạ.

### 4.7.4. Vận hành lâm sàng hàng ngày

Dùng lâm sàng hàng ngày cần ít công việc pipeline. Bác sĩ tạo hội thoại, chat về ca, xem thẻ và bằng chứng, và đổi ngôn ngữ khi cần. Quản trị viên định kỳ dọn quy tắc đã ngưng, điều tra hàng đợi tinh chỉnh, và xác nhận tương tác mới duyệt xuất hiện trong chat. Tách vai trò giữ công việc kỹ thuật nghiên cứu không chặn phiên demo lâm sàng thường.

## 4.8. Chi tiết cài đặt cụ thể

### 4.8.1. Các pha trích xuất pipeline trong thực tế

Giai đoạn extract không phải một script đơn. Sau khi nền tri thức (`kg_base`) tạo mục, đoạn, thực thể, và quan hệ, các pha chuyên biệt dựng từng họ catalog. Pha constraints biến claim thành quy tắc tránh và thận trọng có điều kiện. Pha dose-rules dựng đối tượng liều khởi và đích với predicate thận. Pha dose-safety-warnings suy mức tối đa số sau đó cờ liều dự kiến không an toàn. Pha interaction-rules chuẩn hóa claim cặp thuốc thành tập có thẻ mức độ. Pha GDMT-policies mã hóa kỳ vọng phủ bốn trụ cột. Pha finalize xác thực mã, sửa liên kết nguồn gốc khi cần, và chuẩn bị gói nâng cấp cho store.

Vận hành thường chỉ chạy lại một pha. Ví dụ sau cải thiện prompt tương tác, họ tiếp tục từ `interaction_rules` mà không tải lại DailyMed hay embed lại mọi mục. File checkpoint ghi bước đã xong để job qua đêm bị ngắt tiếp tục sạch. Thiết kế theo pha này là điều biến pipeline nghiên cứu thành quy trình vận hành được thay vì notebook một lần.

### 4.8.2. Ví dụ hình dạng quy tắc ràng buộc

Quy tắc ràng buộc lưu cho đánh giá runtime là đối tượng có cấu trúc, không phải văn tự do. Ở dạng đơn giản hóa gồm mã quy tắc ổn định, một hoặc nhiều khóa thuốc hoặc lớp, hành động như avoid hoặc consider with caution, đối tượng điều kiện có thể yêu cầu eGFR dưới ngưỡng hoặc kali trên ngưỡng, lý do đọc được, nguồn gốc trỏ đoạn nguồn, tầng an toàn, và trạng thái quản trị như draft, approved, hoặc retired. Engine suy luận đánh giá điều kiện với hồ sơ bệnh nhân có kiểu. Nếu điều kiện khớp và tầng thực thi được, trạng thái khuyến nghị tương ứng cập nhật.

Hình dạng này giải thích vì sao trích xuất phải phát JSON qua xác thực Pydantic. Một đoạn đẹp nói "thận trọng khi suy thận" không đủ cho phần mềm. Máy cần predicate có thể kiểm tra. Khi trích xuất không dựng predicate đủ, phân loại đánh dấu `needs_condition_refinement` để clinical lead hoàn thiện logic thay vì để nửa quy tắc chạy.

### 4.8.3. Chuỗi payload SSE chat

Giao thức streaming dễ hiểu nhất như dòng thời gian. Sau khi trình duyệt gửi yêu cầu chat, server có thể phát khung trạng thái như received, extracting patient, building recommendation, verifying evidence, và generating answer. Mốc có cấu trúc rồi xuất hiện dạng sự kiện có kiểu. `draft_ready` mang bản nháp bệnh nhân gộp và trạng thái lâm sàng. `missing_check` báo trường bắt buộc có thiếu không. Nếu pipeline tiếp tục, `recommendation_ready` mang mục GDMT, tương tác, kế hoạch liều, và cờ rủi ro. `verification_ready` mang phán quyết tác tử và kiểm tra trích dẫn. Khung `answer_delta` nối văn tường thuật. `done` đóng lượt với đối tượng phản hồi đầy đủ.

Frontend không chờ `done` mới hữu ích. Ngay khi `recommendation_ready` đến, thẻ render. Đó là lợi ích thực tế của SSE so với một JSON duy nhất cuối pipeline nhiều giây.

### 4.8.4. Song song trong một lượt chat

Hai công cụ đồng thời quan trọng trong dịch vụ chat. Thứ nhất, `asyncio.create_task` khởi động GraphRAG trong khi suy luận chạy. Thứ hai, `asyncio.to_thread` chuyển đánh giá quy tắc PostgreSQL đồng bộ ra khỏi vòng lặp sự kiện. Không offload thread, quét quy tắc dài sẽ chặn yêu cầu API không liên quan như health check hay truy vấn danh sách admin. Không prefetch GraphRAG, kiểm chứng phải chờ truy xuất chỉ bắt đầu sau suy luận xong, thêm độ trễ tránh được. Điểm hội tụ fork-join là kiểm chứng: nó chờ cả đối tượng khuyến nghị và ngữ cảnh GraphRAG prefetch trước khi stream kết quả an toàn.

### 4.8.5. Module tính liều

Tính liều đọc quy tắc liều JSONB mô tả liều khởi, liều đích, bước tăng liều, và dải chỉnh thận. Cho eGFR bệnh nhân và thuốc ứng viên, module chọn dải khớp và trả đối tượng kế hoạch liều cho panel thẻ. Nếu hàng catalog chưa đủ, module không trả số bịa. Sự trung thực này quan trọng: đánh giá ghi độ đủ quy tắc liều chậm hơn catalog khác, và UI không được bịa liều mg khi hàng được quản trị thiếu.

Cảnh báo an toàn liều bổ sung kế hoạch liều. Chúng kích hoạt khi liều dự kiến vượt mức tối đa từ nhãn cho trạng thái thận bệnh nhân. Cùng nhau, kế hoạch liều và cảnh báo an toàn liều biến văn nhãn thành kiểm tra số có thể thực thi.

### 4.8.6. Runtime hội thoại và chat frontend

Bảng điều khiển bác sĩ giữ hội thoại trong trạng thái client với lưu cục bộ tùy chọn. Tạo hội thoại mở modal bệnh nhân, dựng tin chào mừng ban đầu, và chọn ca mới làm active. Chọn hội thoại khác nạp tin vào runtime assistant-ui và có thể đồng bộ lịch sử từ backend khi có. Xóa sạch tin reset luồng nhưng giữ ngữ cảnh bệnh nhân. Xóa hội thoại gỡ khỏi thanh bên và chọn ca khác, hoặc mở lại luồng tạo bệnh nhân khi không còn ca.

Adapter runtime chat chuyển đổi giữa đối tượng tin lưu và mô hình luồng assistant-ui. Khi người dùng gửi tin, adapter POST tới endpoint streaming, áp cập nhật SSE vào trạng thái hội thoại, và giữ panel lâm sàng đồng bộ. Lỗi thành tin trợ lý thay vì fail im lặng, để bác sĩ thấy lượt chưa hoàn tất.

### 4.8.7. Trợ giúp hiển thị khuyến nghị

Trợ giúp hiển thị định dạng đối tượng khuyến nghị cho con người. Chúng dựng câu dẫn ngắn, gom chip sinh hiệu chung như LVEF, eGFR, kali, huyết áp, và nhịp tim, và tránh lặp cùng sinh hiệu trên mọi thẻ. Trợ giúp hiển thị bằng chứng sửa artifact gạch nối từ trích PDF, chọn tiêu đề tài liệu đọc được, và ẩn mã đoạn kỹ thuật khỏi thẻ hướng bác sĩ. Các trợ giúp tồn tại vì JSON thô đúng cho máy nhưng khó chịu cho bác sĩ bận.

### 4.8.8. Bề mặt API chính

Ngoài chat streaming, backend lộ nạp lịch sử cho hội thoại, endpoint health cho vận hành, tìm bằng chứng cho admin và soi lâm sàng, và route quản trị kiểu CRUD cho từng họ catalog. Route admin yêu cầu xác thực JWT và kiểm tra vai trò để chỉ clinical lead được phép duyệt quy tắc. Tìm bằng chứng trả đoạn kèm metadata phù hợp UI bằng chứng thiết kế lại: tiêu đề, trang, nhà xuất bản, và trích dẫn thay vì hash nội bộ.

### 4.8.9. Tóm tắt bố cục repository

Ở mức repository, `backend/` giữ ứng dụng FastAPI. `frontend/doctor-dashboard/` giữ UI bác sĩ. `frontend/admin/` giữ màn hình quản trị. `frontend/shared/` giữ tiện ích API và hiển thị dùng chung. `scraper/` giữ pipeline nạp dữ liệu. `infrastructure/` giữ Docker Compose, Nginx, và mẫu môi trường. `data/heart_failure/` giữ cache cục bộ và đầu ra workspace khi phát triển. Bố cục này tách mã pipeline nghiên cứu khỏi mã phục vụ tương tác nhưng vẫn dùng chung từ vựng và mã lâm sàng.

## 4.9. Walkthrough cài đặt đầu cuối

Xét bác sĩ gõ: "68-year-old man with HFrEF, LVEF 30%, eGFR 38, potassium 4.9, on lisinopril 10 mg and carvedilol 12.5 mg twice daily. Can we add MRA and SGLT2 inhibitor?"

Yêu cầu tới FastAPI và nhận mã hội thoại. Regex tiếp nhận bắt tuổi, LVEF, eGFR, và kali. Từ điển ánh xạ lisinopril sang khóa ACE inhibitor và carvedilol sang khóa beta blocker có bằng chứng. Trạng thái lâm sàng ghi HFrEF và suy giảm chức năng thận. Vì kali và eGFR có mặt, kiểm tra thiếu trường pass và UI nhận `draft_ready`.

Prefetch GraphRAG bắt đầu. HyDE có thể mở rộng câu hỏi ngắn thành đoạn giả định phong phú hơn về khởi MRA và điều trị SGLT2 ở phân suất giảm. Tìm dày, BM25, và truy vấn lân cận Neo4j chạy, rồi RRF gộp ứng viên. Trong lúc đó engine suy luận so bốn trụ GDMT với điều trị hiện tại, thấy thiếu MRA và SGLT2, đánh giá kali và eGFR với ràng buộc MRA, và kiểm tra tương tác với ACE inhibitor đang dùng. Module liều gắn kế hoạch khi có hàng catalog.

Kiểm chứng kiểm toán chặn cứng và có bằng chứng. Nhãn tiếng Việt hoặc tiếng Anh đơn giản hóa gắn. Bảng điều khiển render thẻ khuyến nghị và huy hiệu kiểm chứng, rồi stream câu trả lời giải thích kèm trích bằng chứng ở panel bên. Nếu bác sĩ đổi ngôn ngữ, thẻ gắn nhãn lại ngay mà không lặp truy xuất.

Nếu cùng bác sĩ thiếu kali, pipeline dừng sau `missing_check`, hỏi giá trị, và từ chối phát khuyến nghị MRA dựa trên điện giải đoán. Nhánh đó quan trọng như đường thuận lợi vì nó cho thấy hành vi fail-closed được cài trong code, không chỉ mô tả trong tài liệu thiết kế.

## 4.10. Bài học từ cài đặt

Một số bài học kỹ thuật nổi lên khi xây hệ thống. Thứ nhất, tách đầu ra có cấu trúc có thẩm quyền khỏi văn sinh không tùy chọn trong dược lý trị liệu. Mỗi khi hai lớp tạm trộn lẫn khi prototype, debug khó hơn và bác sĩ mất tin. Thứ hai, trường trạng thái quản trị quan trọng như chất lượng trích xuất. Extractor hoàn hảo vẫn cần trạng thái nháp, đã duyệt, và ngưng. Thứ ba, giao SSE dần cải thiện khả dụng hơn cắt vài trăm mili giây tổng độ trễ, vì bác sĩ hành động theo thẻ trong khi tường thuật tiếp tục. Thứ tư, hỗ trợ song ngữ phải bắt đầu từ từ điển tiếp nhận và bản đồ thẻ tất định; chỉ dịch đoạn cuối để nguyên lỗi nhận diện thuốc. Thứ năm, checkpoint pipeline và bucket artifact biến xây tri thức từ script mong manh thành quy trình vận hành bệnh viện có thể chạy lại khi nhãn đổi.

## 4.11. Tóm tắt chương

Chương này ánh xạ thiết kế hệ thống sang cài đặt cụ thể sâu hơn. Pipeline nạp dữ liệu thu nhãn FDA và guideline, lọc mục bằng thác ba tầng, trích artifact được quản trị qua các pha chuyên biệt, và đồng bộ PostgreSQL, ChromaDB, và Neo4j. Backend FastAPI điều phối tiếp nhận lai, suy luận tất định, tính liều, truy xuất GraphRAG, kiểm chứng, và streaming SSE để kết quả an toàn có cấu trúc xuất hiện trước văn tường thuật. Bảng điều khiển bác sĩ và cổng quản trị React biến các sự kiện đó thành quy trình lâm sàng và quản trị, gồm quản lý hội thoại, hiển thị bằng chứng, và chuyển ngôn ngữ. Docker Compose, Nginx, cấu hình môi trường, kiểm thử, và thủ tục vận hành làm stack tái lập được trên phần cứng bệnh viện vừa phải. Walkthrough và bài học cài đặt cho thấy các phần phối hợp trên ca HFrEF thực. Chương 5 báo cáo cách cài đặt này hoạt động dưới đánh giá có biên soạn.
