# CHƯƠNG 1: GIỚI THIỆU

*(Bản dịch từ `thesis/Chapter1_Introduction.md`)*

Chương này nêu vấn đề luận văn giải quyết, tóm tắt mối liên hệ với công trình trước, và phác thảo cấu trúc Phần II. Bối cảnh lâm sàng, mục tiêu nghiên cứu, phạm vi, cách tiếp cận kỹ thuật và lý thuyết chi tiết được phát triển ở các chương sau như đã chỉ dẫn.

## 1.1 Phát biểu vấn đề

Vấn đề nằm giao điểm của khoảng trống chăm sóc lâm sàng dai dẳng, hạn chế của cách tiếp cận kỹ thuật hiện có, và câu hỏi nghiên cứu về cách kết hợp chúng có trách nhiệm. Điều trị suy tim vừa giàu bằng chứng vừa mong manh vận hành. Hành động đúng phụ thuộc kiểu hình, thuốc đang dùng, xét nghiệm, sinh hiệu và ràng buộc trình tự trải nhiều tài liệu, cập nhật theo chu kỳ.

### 1.1.1 Vấn đề lâm sàng (thiếu GDMT, rào cản)

Với HFrEF, guideline hiện đại tổ chức trị liệu quanh bốn trụ GDMT: ức chế hệ renin–angiotensin (ACEi, ARB hoặc ARNI), beta blocker có bằng chứng, MRA và SGLT2i [2], [3], [6]. Dù bằng chứng thử nghiệm mạnh, thực tế triển khai rất thiếu. Quan sát cho thấy chỉ khoảng 1–2% bệnh nhân đủ điều kiện nhận đủ bốn nhóm ở liều đích [6]. Thiếu không ngẫu nhiên: người già, suy thận, điều trị ngoài trung tâm học thuật bị thiếu nhiều hơn.

Nhiều rào cản giải thích khoảng trống này. Quá tải thông tin vượt khả năng tổng hợp liên tục của bác sĩ bận. Guideline dài hàng trăm trang; nhãn thuốc có chỉnh liều thận, cảnh báo kali, tương tác tinh tế. Chống chỉ định tuyệt đối phụ thuộc trạng thái động: khởi ARNI trong 36 giờ sau ACEi, khởi MRA khi kali/eGFR ngoài ngưỡng an toàn, tăng liều beta blocker khi hạ huyết áp triệu chứng hoặc nhịp chậm đều đòi hỏi ghép thuốc–lab–sinh hiệu đang phân tán. Phức tạp liều tăng rủi ro sai. Nơi mật độ bác sĩ tim mạch thấp như nhiều tỉnh Việt Nam, bác sĩ thiếu hỗ trợ có cấu trúc đúng lúc cân nhắc tăng liều hoặc thêm nhóm thuốc.

Ví dụ ngoại trú: nam 68 tuổi HFrEF (LVEF 30%), tăng huyết áp, ĐTĐ type 2, CKD giai đoạn 3, đang lisinopril và carvedilol nhưng chưa MRA/SGLT2i; kali 4,9; eGFR 38; huyết áp 108/68. Kế hoạch đúng phải đánh giá đồng thời thêm dapagliflozin, spironolactone, tăng liều beta blocker, washout ACEi→ARNI [2], [3]. CDSS phải làm nổi các phụ thuộc này mạch lạc chứ không trả từng đoạn monograph rời.

Các rào cản sinh lỗi dự đoán được: chậm khởi SGLT2i, tiếp tục ACEi không lập kế hoạch washout ARNI, kê MRA thiếu ngữ cảnh kali, tăng liều beta blocker dù huyết động không ổn, trì trệ sau xuất viện. CDSS phải trả lời “hiện tại bệnh nhân này nên làm gì với lab–thuốc–rủi ro này”, kèm cưỡng chế an toàn rõ. Chương 2 phát triển bối cảnh dịch tễ và guideline làm nền cho các yêu cầu này.

### 1.1.2 Vấn đề kỹ thuật (ảo giác LLM đối lập rule cứng)

Chatbot LLM thuần nhận mô tả lâm sàng lộn xộn và viết giải thích trôi chảy [18], [19]. Sinh xác suất không khớp hỗ trợ quyết định thuốc nếu là thẩm quyền duy nhất. LLM có thể bịa liều, bịa tương tác, bỏ chống chỉ định cứng, hoặc lẫn HFpEF với HFrEF. Trong kê đơn rủi ro cao, một âm tính giả trên rule “tránh tuyệt đối” đã có thể thảm họa lâm sàng.

RAG giảm nhưng không xóa rủi ro [12]. Ngay cả với RAG, model trôi chảy vẫn có thể mâu thuẫn đoạn an toàn đã truy xuất nếu không có rule cứng cưỡng chế khuyến nghị cuối.

CDSS chỉ có rule nằm ở cực đối diện [15], [4], [5]. Engine rule mạnh khi tri thức chính xác và output phải tái lập được, nhưng intake văn bản tự do dễ gãy, bảo trì rule tốn công, trích dẫn bằng chứng cần lớp riêng, mệt mỏi cảnh báo làm giảm tin cậy.

Vấn đề kỹ thuật là cách kết hợp tri thức y có cấu trúc, logic an toàn tất định và tương tác qua LLM. Luận văn xem đây là bài toán tích hợp: engine tất định là thẩm quyền khuyến nghị và chặn cứng; truy xuất và đồ thị neo bằng chứng; LLM chỉ giải thích, làm rõ biên và intake dự phòng. Chương 3 nêu luận điểm và kiến trúc; Chương 4 và 5 báo cáo cài đặt và đo lường.

### 1.1.3 Câu hỏi nghiên cứu

**RQ1 (Pipeline tri thức):** Làm sao pipeline tự động nạp nhãn SPL FDA, guideline ESC/AHA/ACC/HFSA và nguồn tương tác vào catalog có quản trị, lập chỉ mục vector và đồ thị, vừa kiểm soát chi phí trích xuất vừa giữ độ đặc hiệu lâm sàng?

**RQ2 (Suy luận lai):** Làm sao kết hợp engine GDMT/an toàn tất định với GraphRAG lai và agent kiểm chứng để khuyến nghị khớp guideline, fail-closed với chống chỉ định cứng, giải thích LLM vẫn bám bằng chứng đã truy xuất?

**RQ3 (UX song ngữ và an toàn):** Làm sao giao diện chat Việt–Anh truyền thẻ khuyến nghị qua SSE không mất ngữ cảnh, và các chỉ số so với tiêu chí định trước (Chương 5, mục 5.0) trên vignette HFrEF?

## 1.2 Công trình liên quan

Thiết kế CDSS suy tim dựa trên bốn dòng nghiên cứu. Chương 2 xem xét chi tiết; ở đây chỉ nêu liên hệ với vấn đề trên và vị trí luận văn.

**CDSS cổ điển** [15], [4], [5], [17]: logic có thể kiểm toán; EHR doanh nghiệp mạnh kiểm tương tác chung nhưng hạn chế phân tích khoảng trống GDMT HFrEF và intake chat song ngữ.

**Đồ thị tri thức và thuật ngữ y sinh** [7]–[11]: suy luận đa bước; cần quản trị vì trích xuất tự động tạo nhiễu [8].

**RAG, GraphRAG, truy xuất lai** [12]–[14]: neo LLM vào tài liệu; ít sản phẩm CDSS triển khai kết hợp này với tầng rule fail-closed cho GDMT.

**Guideline suy tim** [2], [3], [6]: xương sống chuẩn mực; nhãn SPL bổ sung liều theo sản phẩm.

**Khoảng trống:** nhiều hệ chỉ tiếng Anh, ung thư, hoặc tra cứu thụ động; chat LLM ưu tiên độ trôi chảy; RAG chỉ vector bỏ chuỗi tương tác; rule-only thiếu trích dẫn. Luận văn nhắm kiến trúc tích hợp: nạp đa kho có quản trị, GraphRAG lai, engine GDMT tất định, agent kiểm chứng, chat stream song ngữ với thẻ có cấu trúc, đánh giá theo tiêu chí Chương 5.

## 1.3 Bố cục luận văn

Luận văn chia hai phần. **Phần I** (chương này): vấn đề và công trình liên quan. **Phần II**: lý thuyết, thiết kế, cài đặt, kết quả, kết luận.

**Chương 2:** bối cảnh, CDSS, KG, RAG/GraphRAG, LLM, xây tri thức y, nền lâm sàng suy tim, công nghệ triển khai, kỹ thuật được chọn.

**Chương 3:** mục đích, phạm vi, cách tiếp cận; yêu cầu; kiến trúc 3 tầng; module intake/GraphRAG/reasoning/an toàn/stream.

**Chương 4:** backend, pipeline, runtime, Docker Compose.

**Chương 5:** tiêu chí thành công định trước; số liệu pipeline, accuracy, latency, an toàn, usability.

**Chương 6:** đóng góp, phản ánh RQ1–RQ3, hạn chế, hướng phát triển.

References và Phụ lục A: nguồn và sơ đồ. Phần II lập luận CDSS lai tăng cường đồ thị có thể hỗ trợ GDMT suy tim khi phân quyền thẩm quyền đúng, tri thức được quản trị, bác sĩ giữ quyết định cuối.
