# CHƯƠNG 1: GIỚI THIỆU

*(Bản dịch chi tiết từ `thesis/Chapter1_Introduction.md`)*

## 1.1 Bối cảnh và động lực nghiên cứu

Suy tim (Heart Failure, HF) là một trong những bệnh tim mạch mạn tính nghiêm trọng nhất. Ước tính toàn cầu có hơn 64 triệu người sống với suy tim, và số này còn tăng khi dân số già hóa cũng như khi điều trị cấp cứu tốt hơn giúp bệnh nhân sống sót sau nhồi máu cơ tim nhưng sau đó xuất hiện rối loạn chức năng thất kéo dài [1]. Suy tim không phải một bệnh đơn lẻ mà là hội chứng lâm sàng: tim không đổ đầy hoặc bơm máu đủ để đáp ứng nhu cầu cơ thể. Bệnh nhân khó thở, mệt, giữ nước, nhập viện nhiều lần. Với hệ thống y tế, suy tim là nguyên nhân nhập viện hàng đầu ở người trên 65 tuổi; tái nhập viện trong 30 ngày vừa phổ biến vừa tốn kém.

Bác sĩ phân loại suy tim theo phân suất tống máu thất trái (LVEF). HFrEF (LVEF ≤ 40%) là trọng tâm luận văn vì điều trị nội khoa theo hướng dẫn (GDMT) có bằng chứng mạnh nhất về giảm tử vong và nhập viện ở nhóm này [2], [3]. Quản lý ngoại trú cần điều chỉnh cẩn thận thuốc ức chế thần kinh–thể dịch, lợi tiểu và SGLT2i. Mỗi nhóm thuốc có tiêu chí khởi trị, chống chỉ định, tương tác và yêu cầu theo dõi riêng. Khi điều trị thiếu hoặc sai trình tự, bệnh nhân chịu hại có thể tránh được. Cải thiện nhỏ trong việc dùng GDMT có thể đổi kết cục dân số khi nhân lên hàng triệu bệnh nhân [2], [3], [6]. Hệ hỗ trợ quyết định lâm sàng (CDSS) thường được nêu như cách thu hẹp khoảng cách giữa bằng chứng đã công bố và hành động tại giường bệnh [4], [5].

Ở Việt Nam, gánh nặng suy tim theo xu hướng toàn cầu nhưng thêm ràng buộc địa phương. Chuyên khoa tim mạch tập trung ở thành phố lớn; tuyến tỉnh dựa nhiều vào nội khoa tổng quát phải xử lý GDMT phức tạp với ít hỗ trợ chuyên sâu [1]. Hồ sơ tiếng Việt, tên biệt dược địa phương và charting lẫn Việt–Anh khiến hỗ trợ quyết định có cấu trúc khó tiếp cận hơn. CDSS suy tim cho bối cảnh này phải coi tiếp nhận song ngữ và chuẩn hóa thuốc có quản trị là yêu cầu cốt lõi.

Hai xu hướng công nghệ làm nghiên cứu này kịp thời. Đồ thị tri thức y sinh, thuật ngữ chuẩn và kho nhãn thuốc mở đã chín muồi đến mức có thể nạp tự động vào catalog có quản trị mà không chép tay toàn bộ công thức [7]–[11]. Mô hình ngôn ngữ lớn (LLM) làm giao diện ngôn ngữ tự nhiên thực tế, nhưng xu hướng tạo văn bản nghe hợp lý nhưng sai khiến chúng không an toàn nếu dùng một mình để kê đơn [12], [19]. Mô hình mã mở chạy cục bộ giảm phụ thuộc API đám mây khi thí điểm bệnh viện cần giữ vignette bệnh nhân tại chỗ.

Luận văn xuất phát từ nhận định: CDSS suy tim phải vượt cả engine chỉ có rule cứng và chat LLM không ràng buộc. Hệ rule có kiểm toán và an toàn tất định nhưng kém với chat tự do, giải thích song ngữ và truy xuất linh hoạt trên corpus guideline/nhãn dị thể. Chatbot LLM tương tác tự nhiên nhưng nếu dùng một mình có thể bịa liều, bịa tương tác hoặc bỏ chống chỉ định cứng. Kiến trúc lai ghép tri thức được quản trị, engine GDMT/an toàn tất định, truy xuất tăng cường đồ thị (GraphRAG) và LLM giải thích chạy cục bộ là phản ứng có nguyên tắc. Công trình xây hệ hỗ trợ GDMT cho HFrEF, giao diện Việt–Anh, xây tri thức tự động từ nhãn SPL của FDA và guideline suy tim chính, đánh giá trên vignette do bác sĩ tim mạch duyệt.

## 1.2 Mục đích nghiên cứu

Mục đích là thiết kế, cài đặt và đánh giá CDSS chuyên suy tim tích hợp đồ thị tri thức y, GraphRAG lai, engine quy tắc lâm sàng tất định, agent kiểm chứng và LLM chạy cục bộ. Hệ thống giúp bác sĩ áp dụng GDMT nhất quán và an toàn hơn bằng cách biến nguồn có thẩm quyền (DailyMed SPL/XML, guideline ESC và AHA/ACC/HFSA, tri thức tương tác đã biên soạn) thành artifact có quản trị, truy vấn được, hỗ trợ vừa suy luận có cấu trúc vừa giải thích bám bằng chứng.

Về khoa học, nghiên cứu theo bốn mục tiêu liên kết. Một, khảo sát pipeline xây tri thức tự động trích quy tắc ràng buộc, liều, tương tác, chính sách GDMT và cảnh báo an toàn liều từ tài liệu dị thể đủ chính xác để nạp PostgreSQL, ChromaDB và Neo4j. Hai, khảo sát truy xuất lai (dense embedding, BM25, duyệt lân cận đồ thị, mở rộng HyDE, hợp nhất RRF) cung cấp ngữ cảnh có thể trích dẫn khi riêng lexical hoặc semantic đều không đủ tin [12]–[14]. Ba, đánh giá việc tách logic khuyến nghị tất định khỏi văn bản LLM có giảm ảo giác mà vẫn giữ trải nghiệm hội thoại. Bốn, đo hành vi end-to-end về độ chính xác khuyến nghị, latency, độ nhạy cảnh báo an toàn, khả năng dùng song ngữ và mức hài lòng bác sĩ theo tiêu chí đặt trước khi cài đặt.

Về thực tiễn, nghiên cứu bàn giao prototype dùng dưới giám sát bác sĩ tim mạch: nạp SPL/guideline tự động; chuyển chat tự do thành hồ sơ bệnh nhân có cấu trúc qua intake lai; phân tích khoảng trống GDMT theo rule PostgreSQL; bắt buộc kiểm tra tương tác, chống chỉ định, thận, điện giải, an toàn liều; GraphRAG song song lắp bằng chứng giải thích; kiểm chứng đa agent; truyền tóm tắt ngôn ngữ dễ hiểu Việt–Anh qua dashboard React bằng SSE.

Nghiên cứu không nhằm thay EHR, tự động kê đơn không người duyệt, hay xử lý suy tim mất bù cấp cần can thiệp khẩn. Mục đích hẹp hơn: chứng minh CDSS lai có thể vận hành phần lớn tri thức GDMT ngoại trú HFrEF dưới dạng bác sĩ tương tác qua chat, tin nhờ tầng an toàn tất định, và đánh giá bằng chỉ số minh bạch. Phương pháp theo paradigm thiết kế–khoa học: nêu vấn đề có nền, đề xuất artifact có claim kiểm chứng được, cài đặt có thể tái lập, đánh giá theo tiêu chí định trước với chuyên gia và bộ kiểm thử an toàn có cấu trúc.

## 1.3 Vấn đề nghiên cứu

Vấn đề nằm giao điểm của khoảng trống chăm sóc lâm sàng dai dẳng, hạn chế cách tiếp cận kỹ thuật hiện có, và câu hỏi nghiên cứu về cách kết hợp chúng có trách nhiệm. Điều trị suy tim vừa giàu bằng chứng vừa mong manh vận hành. Hành động đúng phụ thuộc kiểu hình, thuốc đang dùng, xét nghiệm, sinh hiệu và ràng buộc trình tự trải nhiều tài liệu, cập nhật theo chu kỳ.

### 1.3.1 Vấn đề lâm sàng (thiếu GDMT, rào cản)

Với HFrEF, guideline hiện đại tổ chức trị liệu quanh bốn trụ GDMT: ức chế hệ renin–angiotensin (ACEi, ARB hoặc ARNI), beta blocker có bằng chứng, MRA và SGLT2i [2], [3], [6]. Dù bằng chứng thử nghiệm mạnh, thực tế triển khai rất thiếu. Quan sát cho thấy chỉ khoảng 1–2% bệnh nhân đủ điều kiện nhận đủ bốn nhóm ở liều đích [6]. Thiếu không ngẫu nhiên: người già, suy thận, điều trị ngoài trung tâm học thuật bị thiếu nhiều hơn.

Nhiều rào cản giải thích khoảng trống này. Quá tải thông tin vượt khả năng tổng hợp liên tục của bác sĩ bận. Guideline dài hàng trăm trang; nhãn thuốc có chỉnh liều thận, cảnh báo kali, tương tác tinh tế. Chống chỉ định tuyệt đối phụ thuộc trạng thái động: khởi ARNI trong 36 giờ sau ACEi, khởi MRA khi kali/eGFR ngoài ngưỡng an toàn, tăng liều beta blocker khi hạ huyết áp triệu chứng hoặc nhịp chậm đều đòi hỏi ghép thuốc–lab–sinh hiệu đang phân tán. Phức tạp liều tăng rủi ro sai: liều khởi, liều đích và lịch chuẩn liều phải cá thể hóa theo eGFR, kali, huyết áp, nhịp tim. Nơi mật độ bác sĩ tim mạch thấp như nhiều tỉnh Việt Nam, bác sĩ thiếu hỗ trợ có cấu trúc đúng lúc cân nhắc tăng liều hoặc thêm nhóm thuốc.

Ví dụ ngoại trú: nam 68 tuổi HFrEF (LVEF 30%), tăng huyết áp, ĐTĐ type 2, CKD giai đoạn 3, đang lisinopril và carvedilol nhưng chưa MRA/SGLT2i; kali 4,9; eGFR 38; huyết áp 108/68. Kế hoạch đúng phải đánh giá đồng thời: thêm dapagliflozin? spironolactone có phù hợp? tăng liều beta blocker có an toàn? chuyển ACEi→ARNI có cần washout? [2], [3]. CDSS phải làm nổi các phụ thuộc này mạch lạc chứ không trả từng đoạn monograph rời.

Các rào cản sinh lỗi dự đoán được: chậm khởi SGLT2i, tiếp tục ACEi không lập kế hoạch washout ARNI, kê MRA thiếu ngữ cảnh kali, tăng liều beta blocker dù huyết động không ổn, trì trệ sau xuất viện. CDSS phải trả lời “hiện tại bệnh nhân này nên làm gì với lab–thuốc–rủi ro này”, kèm cưỡng chế an toàn rõ khi sai không chấp nhận được.

### 1.3.2 Vấn đề kỹ thuật (ảo giác LLM đối lập rule cứng)

Chatbot LLM thuần nhận mô tả lâm sàng lộn xộn và viết giải thích trôi chảy, giảm tải nhận thức [18], [19]. Nhưng sinh xác suất không khớp hỗ trợ quyết định thuốc nếu là thẩm quyền duy nhất. LLM có thể bịa liều, bịa tương tác, bỏ chống chỉ định cứng, hoặc lẫn HFpEF với HFrEF. Trong kê đơn rủi ro cao, một âm tính giả trên rule “tránh tuyệt đối” đã có thể thảm họa lâm sàng dù chất lượng câu trả lời trung bình trông cao.

RAG giảm nhưng không xóa rủi ro này [12]. RAG lấy văn bản liên quan từ kho tri thức ngoài rồi đưa làm ngữ cảnh trước khi sinh, neo câu trả lời vào tài liệu thật thay vì chỉ nhớ trong model. Ngay cả với RAG, model trôi chảy vẫn có thể mâu thuẫn đoạn an toàn đã truy xuất nếu không có rule cứng cưỡng chế khuyến nghị cuối.

CDSS chỉ có rule nằm ở cực đối diện. MYCIN chứng minh logic if–then tường minh có thể hỗ trợ trị liệu với vết kiểm toán [15]. Engine rule nhúng EHR sau này mở rộng sang cảnh báo tương tác và kiểm liều. Tổng quan hệ thống xác nhận lợi ích cho hiệu suất người hành nghề và quy trình bệnh mạn [4], [5]. Engine rule mạnh khi tri thức chính xác và output phải tái lập được, nhưng intake văn bản tự do dễ gãy, bảo trì rule tốn công, trích dẫn bằng chứng cần lớp riêng, và mệt mỏi cảnh báo làm giảm tin cậy khi độ đặc hiệu thấp.

Vấn đề kỹ thuật là cách kết hợp tri thức y có cấu trúc, logic an toàn tất định và tương tác qua LLM để CDSS suy tim vẫn chính xác, giải thích được và dùng được lâm sàng. Rule không có truy xuất khó trích dẫn và khó chat. LLM không có rule được quản trị khó an toàn và kiểm toán. Luận văn xem đây là bài toán tích hợp: engine tất định là thẩm quyền khuyến nghị và chặn cứng; truy xuất và đồ thị là thẩm quyền neo bằng chứng; LLM chỉ thẩm quyền giải thích, làm rõ biên và intake dự phòng.

### 1.3.3 Câu hỏi nghiên cứu

**RQ1 (Pipeline tri thức):** Làm sao pipeline tự động nạp nhãn SPL FDA, guideline ESC/AHA/ACC/HFSA và nguồn tương tác vào catalog ràng buộc, liều, tương tác, GDMT, cảnh báo an toàn liều có quản trị, lập chỉ mục vector và đồ thị, vừa kiểm soát chi phí trích xuất vừa giữ độ đặc hiệu lâm sàng qua lọc tầng và artifact người duyệt được?

**RQ2 (Suy luận lai):** Làm sao kết hợp engine GDMT/an toàn tất định với GraphRAG lai (HyDE, BM25, dense BGE-M3, duyệt Neo4j, RRF, rerank tùy chọn) và agent kiểm chứng để khuyến nghị có cấu trúc khớp guideline, fail-closed với chống chỉ định cứng, trong khi giải thích LLM vẫn bám bằng chứng đã truy xuất?

**RQ3 (UX song ngữ và an toàn):** Làm sao giao diện chat Việt–Anh truyền thẻ khuyến nghị và tóm tắt dễ hiểu qua SSE không mất ngữ cảnh hội thoại, và độ chính xác, latency, độ nhạy cảnh báo, mức hài lòng bác sĩ so với tiêu chí định trước trên vignette HFrEF đã biên soạn như thế nào?

## 1.4 Công trình liên quan và khoảng trống nghiên cứu

### 1.4.1 CDSS cổ điển

CDSS cổ điển đặt nguyên tắc vẫn còn giá trị. MYCIN cho thấy heuristic lâm sàng mã hóa có thể ngang chuyên gia trong miền hẹp khi kỹ thuật tri thức chặt [15]. Khung Osheroff nhấn mạnh đưa đúng thông tin tới đúng người, đúng định dạng, đúng kênh, đúng thời điểm [17]. Viện Y học Hoa Kỳ nhấn mạnh CNTT y tế phải hỗ trợ chăm sóc an toàn hơn chứ không chỉ số hóa quy trình cũ [16]. Tổng quan báo cải thiện hiệu suất người hành nghề và hiệu ứng quy trình bệnh mạn thuận lợi [4], [5], nhưng triển khai cổ điển cũng cho thấy mệt mỏi cảnh báo, gắn workflow kém, bảo trì rule mờ, mất tin khi hệ thống không giải thích được. Sản phẩm EHR doanh nghiệp thường mạnh kiểm tương tác nhưng hạn chế phân tích khoảng trống GDMT riêng suy tim.

### 1.4.2 Đồ thị tri thức và tài nguyên y sinh

Đồ thị tri thức (KG) lưu sự kiện y dưới dạng nút (thuốc, bệnh, lab) và quan hệ (điều trị, chống chỉ định, tương tác) [7], [8]. Khác bộ sưu tập tài liệu phẳng, KG cho phép đi theo đường nối để trả lời câu hỏi nhiều bước. UMLS gắn thuật ngữ đồng nghĩa giữa các hệ từ vựng [9]. SNOMED CT cung cấp phân cấp khái niệm lâm sàng [10]. DrugBank cung cấp thuộc tính thuốc, tương tác và định danh để liên kết thực thể [11]. Trích xuất tự động tạo nhiễu và cạnh lỗi thời, nên workflow quản trị quan trọng ngang thuật toán [8]. Luận văn lưu rule trong PostgreSQL với trạng thái nháp/đã duyệt/ngưng và import thực thể vào Neo4j để truy xuất lân cận kèm catalog rule được quản trị.

### 1.4.3 RAG, GraphRAG, HyDE, RRF

RAG điều kiện hóa output LLM bằng đoạn đã truy xuất ngoài, giảm phụ thuộc bộ nhớ tham số [12]. Dense retrieval dùng embedding để khớp diễn đạt khác chữ. Sparse BM25 mạnh với tên thuốc đúng chữ và cụm quy định. RRF gộp danh sách xếp hạng bằng vị trí hạng thay vì chuẩn hóa điểm không tương thích. GraphRAG mở rộng RAG bằng lân cận đồ thị cho suy luận nhiều bước trên corpus tường thuật [13]. HyDE mở rộng câu hỏi ngắn bằng cách sinh tài liệu trả lời giả định rồi embedding để tìm, cải thiện recall khi câu như “Start MRA?” ít trùng từ với đoạn nhãn [14]. Luận văn dùng HyDE, dense+sparse song song, duyệt Neo4j và RRF, đồng thời không cho LLM ghi đè chặn cứng tất định.

### 1.4.4 Guideline suy tim (ESC, AHA/ACC/HFSA)

Guideline ESC 2021 củng cố bằng chứng liệu pháp bốn trụ HFrEF và theo dõi [2]. Guideline AHA/ACC/HFSA 2022 nhấn tối ưu GDMT và tích hợp SGLT2i [3]. Đây là xương sống chuẩn mực để đánh giá CDSS. Chủ đề chính: bốn trụ sớm khi dung nạp được, ưu tiên ARNI kèm washout phù hợp, beta blocker có bằng chứng, khởi MRA kèm theo dõi kali–thận, lợi ích SGLT2i độc lập ĐTĐ [2], [3], [6]. Guideline là văn xuôi cần diễn giải; nhãn SPL bổ sung liều và chống chỉ định theo sản phẩm. CDSS phải hòa giải cả hai nguồn.

### 1.4.5 Khoảng trống nghiên cứu của luận văn

Dù tiến bộ trên CDSS, KG, RAG và guideline, khoảng trống còn: nhiều hệ nghiêng ung thư, chỉ tiếng Anh, hoặc tra cứu thụ động không có máy tính liều được quản trị; chat LLM coi trọng độ trôi chảy hơn cưỡng chế chống chỉ định fail-closed và phân tích khoảng trống GDMT có cấu trúc; RAG chỉ vector có thể bỏ chuỗi tương tác tốt hơn dưới dạng đường đồ thị hoặc rule thực thi; hệ chỉ rule có thể cảnh báo đúng nhưng không trích dẫn bằng chứng bác sĩ cần.

Ít hệ đồng thời có: nạp đa nguồn tự động vào PostgreSQL/ChromaDB/Neo4j kèm workflow người quản trị; GraphRAG lai HyDE+BM25+dense+đồ thị+RRF; engine GDMT tất định độc lập văn bản sinh; agent kiểm chứng; chat stream song ngữ với thẻ có cấu trúc. Luận văn nhắm khoảng trống kết hợp đó trong một kiến trúc tích hợp, đánh giá theo tiêu chí thành công tường minh.

## 1.5 Phạm vi và giới hạn

Phạm vi lâm sàng chính: dược trị liệu GDMT HFrEF (ACEi, ARB, ARNI, beta blocker có bằng chứng, MRA, SGLT2i) gồm khởi trị, tăng liều, chống chỉ định, tương tác và cảnh báo an toàn liều chính. HFpEF, suy tim mất bù cấp cần vận mạch tĩnh mạch, thiết bị, ghép, chăm sóc giảm nhẹ phần lớn ngoài phạm vi. Nguồn tri thức: DailyMed SPL/XML, guideline ESC và AHA/ACC/HFSA, tri thức tương tác trong PostgreSQL. Tích hợp đầy đủ công thức Việt là việc tương lai.

Dữ liệu bệnh nhân vào qua chat, không phải feed HL7/FHIR. Khuyến nghị mang tính tư vấn: ràng buộc tránh cứng gắn cờ hành động không an toàn trong output có cấu trúc, nhưng quyền kê đơn thuộc bác sĩ. Triển khai giả định hosting cục bộ với JWT và Docker. Dashboard hỗ trợ Việt–Anh, giữ ngữ cảnh khi đổi ngôn ngữ. Đánh giá dùng vignette biên soạn và bộ an toàn có cấu trúc, không phải thử nghiệm ngẫu nhiên tiến cứu.

## 1.6 Tuyên bố luận điểm và cách tiếp cận kỹ thuật

### 1.6.1 Tuyên bố luận điểm

Claim trung tâm: CDSS lai ghép rule GDMT/an toàn tất định với GraphRAG và LLM giải thích chạy cục bộ có thể mang hỗ trợ điều trị suy tim chính xác, kịp thời, song ngữ, phù hợp workflow lâm sàng mà vẫn giữ bác sĩ trong vòng quyết định. Chính xác = khớp guideline của đối tượng khuyến nghị có cấu trúc trên ca chuyên gia duyệt. Kịp thời = latency end-to-end điển hình dưới 10 giây. An toàn = fail-closed trên chống chỉ định cứng trong catalog được quản trị, bổ sung agent kiểm chứng. Luận văn từ chối cả chat sinh không ràng buộc và cảnh báo chỉ rule cứng thiếu giải thích bám bằng chứng.

### 1.6.2 Kỹ thuật kỹ thuật tri thức (offline)

Nạp offline vào kho đồng bộ. Tải nhãn SPL XML và guideline vào object storage có phiên bản. Bộ lọc mục 3 tầng giữ nội dung lâm sàng, giảm chi phí LLM: khớp từ khóa tiêu đề chuẩn, điểm tương đồng ngữ nghĩa BGE-M3, LLM vùng biên chỉ với mục mơ hồ. Văn bản sống sót được cắt đoạn theo câu, trích claim, phân lớp an toàn hard_block / usable_rules / needs_condition_refinement. Artifact sync PostgreSQL (quản trị), ChromaDB (vector), Neo4j (đồ thị). PostgreSQL là thẩm quyền rule thực thi; vector/đồ thị làm giàu giải thích, không ghi đè chặn cứng.

### 1.6.3 Kỹ thuật lúc truy vấn (online)

Intake lai chuyển chat thành hồ sơ: regex lab/sinh hiệu, lexicon thuốc/bệnh kèm phủ định, LLM chọn lọc khi tin cậy thấp. Engine reasoning đánh giá phủ GDMT, áp ràng buộc/tương tác, tính kế hoạch liều đồng bộ từ catalog, không phụ thuộc sinh LLM cho trạng thái cốt lõi.

Song song, GraphRAG lắp ngữ cảnh giải thích: HyDE mở rộng truy vấn; retriever dense ChromaDB, sparse BM25, duyệt Neo4j; gộp bằng RRF; đoạn phục vụ agent kiểm chứng và LLM giải thích kèm metadata trích dẫn. LLM ở đây không phải thẩm quyền lâm sàng: hỗ trợ intake mơ hồ, HyDE, và sinh tường thuật có điều kiện trên output có cấu trúc và ngữ cảnh đã truy xuất. SSE đẩy thẻ an toàn có cấu trúc trước khi văn bản giải thích kết thúc.

### 1.6.4 Nguyên tắc thiết kế: LLM lớp giải thích, rule là thẩm quyền

Rule tất định và catalog được quản trị là thẩm quyền trạng thái khuyến nghị, chặn cứng và tính liều. Bằng chứng đã truy xuất là thẩm quyền đoạn được phép trích dẫn. LLM chỉ giao diện và giải thích; không ghi đè hard_block hay bịa thuốc ngoài output engine. Bác sĩ nhận thẻ có cấu trúc trước, rồi giải thích stream. Hậu kiểm có thể truy vết khuyến nghị về rule PostgreSQL và claim về metadata chunk đã truy xuất.

## 1.7 Tiêu chí thành công

Thành công nếu đạt mục tiêu định trước ở Chương 5. Độ chính xác khuyến nghị so với chuyên gia khớp guideline ≥ 90% trên đối tượng có cấu trúc (nhóm thuốc, trạng thái hành động, cờ an toàn chính), đo trên vignette bác sĩ tim mạch duyệt. Thời gian đáp ứng end-to-end trung bình dưới 10 giây trên phần cứng tham chiếu, từ gửi chat đến SSE xong. Với chống chỉ định cứng trong ca an toàn biên soạn, hệ không được bỏ sót rule tránh tuyệt đối dạng hard_block; thất bại bất kỳ ca tránh bắt buộc đều loại thành công dù accuracy trung bình cao. Mức hài lòng bác sĩ (Likert 5 điểm) trung bình ≥ 4,0 gồm hữu ích lâm sàng, tin cảnh báo an toàn, dùng song ngữ. Giao diện hỗ trợ Việt–Anh không mất ngữ cảnh khi đổi ngôn ngữ. Pipeline tự động hóa trích xuất nhóm thuốc GDMT chính vào catalog người duyệt được mà không redeploy code. Các tiêu chí kết hợp accuracy, an toàn, latency, bảo trì và usability theo tinh thần workflow Osheroff [17].

## 1.8 Đóng góp

Về kiến trúc: CDSS lai tích hợp backend FastAPI, dashboard React SSE, catalog PostgreSQL, embedding ChromaDB, đồ thị Neo4j, suy luận Ollama cục bộ; module tất định trên đường an toàn; LLM giới hạn ở giải thích và tăng cường truy xuất.

Về phương pháp: pipeline đa nguồn từ DailyMed SPL và guideline qua lọc 3 tầng, trích claim, phân lớp an toàn, sync quan hệ–vector–đồ thị kèm approve/retire admin. Về truy xuất: GraphRAG lai HyDE+BM25+dense+đồ thị+RRF+agent kiểm chứng gắn engine GDMT tất định độc lập văn bản sinh.

Về usability: dashboard Việt–Anh với thẻ khuyến nghị và tóm tắt dễ hiểu. Về thực nghiệm: báo cáo phủ xây tri thức, accuracy, latency, độ nhạy an toàn, hài lòng bác sĩ theo mục 1.7, đồng thời ghi nhận hạn chế như khoảng trống biệt dược địa phương và thiết kế vignette hồi cứu.

## 1.9 Bố cục luận văn

Chương 2: tổng quan lý thuyết CDSS, KG, RAG/GraphRAG/HyDE/RRF, LLM, guideline suy tim, ánh xạ kỹ thuật sang vai trò kiến trúc.  
Chương 3: yêu cầu và thiết kế 3 tầng, lược đồ KG, module intake/GraphRAG/reasoning/an toàn/kiểm chứng/stream chat.  
Chương 4: cài đặt backend/frontend, pipeline, dịch vụ runtime, Docker Compose.  
Chương 5: kết quả và đánh giá theo tiêu chí 1.7.  
Chương 6: kết luận, trả lời RQ1–RQ3, hạn chế, hướng phát triển.  
References và Phụ lục A: nguồn và sơ đồ.
