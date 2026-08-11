# CHƯƠNG 1: GIỚI THIỆU

Chương này nêu bối cảnh, mục tiêu, phạm vi, cách làm, vấn đề cần giải, ba câu hỏi nghiên cứu, tóm tắt công trình liên quan và lộ trình các chương sau. Lý thuyết chi tiết ở Chương 2; thiết kế ở Chương 3; cài đặt và số liệu ở Chương 4–5.

## 1.1 Bối cảnh và động lực

Suy tim là bệnh mạn tính: tim bơm hoặc chứa máu kém, bệnh nhân khó thở, mệt, phù, hay nhập viện. Ước tính toàn cầu có hơn 64 triệu người sống với suy tim; con số tăng khi dân số già và nhiều người sống sót sau nhồi máu nhưng còn suy chức năng thất [1].

Bác sĩ thường phân loại theo phân suất tống máu thất trái (LVEF). Khi LVEF ≤ 40% gọi là suy tim phân suất tống máu giảm (HFrEF). Luận văn tập trung HFrEF vì điều trị nội khoa theo hướng dẫn (GDMT) có bằng chứng mạnh nhất ở nhóm này [2], [3], [6].

GDMT HFrEF gồm bốn nhóm chính: ức chế hệ renin–angiotensin (ACEi, ARB hoặc ARNI), beta blocker có bằng chứng, MRA và SGLT2i. Trên thực tế, rất ít bệnh nhân đủ điều kiện dùng đủ bốn nhóm ở liều mục tiêu [6]. Người già, suy thận, tuyến tỉnh thường thiếu hơn.

Mỗi lần khám, bác sĩ phải ghép kiểu suy tim, thuốc đang dùng, xét nghiệm, sinh hiệu và quy tắc thời gian (ví dụ washout giữa ACEi và ARNI). Guideline dài; nhãn thuốc có liều theo thận, cảnh báo kali, tương tác. Ở Việt Nam, hồ sơ thường lẫn tiếng Việt–Anh, tên biệt dược khó khớp với mã quốc tế [1]. Hệ hỗ trợ quyết định (CDSS) được kỳ vọng giúp thu hẹp khoảng cách giữa khuyến cáo và thực hành [4], [5].

Công nghệ hiện có hai hướng: đồ thị tri thức và nhãn thuốc có thể nạp tự động vào kho có quản trị [7]–[11]; mô hình ngôn ngữ lớn (LLM) đọc văn bản tự do và viết giải thích dễ nghe, nhưng có thể sai liều hoặc bỏ chống chỉ định nếu không bị ràng buộc [12], [19]. Chạy model mã nguồn mở tại chỗ (Ollama) phù hợp thí điểm cần giữ dữ liệu trong bệnh viện.

## 1.2 Mục đích, phạm vi và cách tiếp cận

### 1.2.1 Mục đích

Thiết kế, cài đặt và đánh giá CDSS chuyên suy tim: đồ thị tri thức, GraphRAG lai, engine quy tắc cố định, agent kiểm chứng và LLM cục bộ. Hệ biến nhãn FDA (SPL), guideline ESC và AHA/ACC/HFSA thành catalog có quản trị, có thể truy vấn, để khuyến nghị và giải thích không mâu thuẫn nhau.

Bốn hướng kỹ thuật: (1) pipeline xây tri thức tự động; (2) truy xuất lai (dense, BM25, đồ thị, HyDE, RRF) [12]–[14]; (3) tách logic khuyến nghị khỏi văn LLM; (4) đo end-to-end theo tiêu chí Chương 5 (mục 5.0). Hệ chỉ hỗ trợ dưới giám sát bác sĩ, không thay EHR hay tự kê đơn.

### 1.2.2 Phạm vi

Trong phạm vi: GDMT dược lý HFrEF (ACEi, ARB, ARNI, beta blocker, MRA, SGLT2i), nguồn DailyMed SPL và guideline suy tim, chat bác sĩ (không HL7/FHIR trực tiếp), giao diện Việt–Anh, triển khai Docker cục bộ, đánh giá trên vignette và bộ an toàn có cấu trúc.

Ngoài phạm vi chính: HFpEF, suy tim cấp nặng, thiết bị, ghép, dược địa phương đầy đủ. Khuyến nghị mang tính tư vấn; quyết định cuối thuộc bác sĩ.

### 1.2.3 Luận điểm

CDSS lai (rule GDMT/an toàn + GraphRAG + LLM giải thích) có thể hỗ trợ điều trị suy tim đúng hướng dẫn, kịp thời, song ngữ, trong khi bác sĩ giữ quyền quyết định. Không dùng chat LLM tự do làm “người kê đơn”; không chỉ cảnh báo rule khô mà thiếu trích dẫn.

### 1.2.4 Cách làm ngoại tuyến (xây tri thức)

Thu nhãn SPL và guideline vào kho có phiên bản. Lọc mục ba bước: từ khóa, embedding (BGE-M3), LLM chỉ với mục không chắc. Cắt đoạn, trích claim, phân lớp an toàn. Đồng bộ PostgreSQL (rule thực thi), ChromaDB (vector), Neo4j (đồ thị). PostgreSQL là nơi quyết định chặn cứng.

### 1.2.5 Cách làm khi truy vấn (online)

Intake lai (regex, từ điển thuốc, phủ định, LLM khi cần) → engine GDMT/ràng buộc/tương tác/liều cố định. Song song GraphRAG: HyDE, dense, BM25, Neo4j, RRF. LLM viết giải thích và hỗ trợ intake; không đổi trạng thái hard_block. SSE đẩy thẻ có cấu trúc trước văn dài.

### 1.2.6 Nguyên tắc: rule là thẩm quyền, LLM là lớp ngôn ngữ

Trạng thái khuyến nghị, chặn cứng, liều lấy từ catalog PostgreSQL đã duyệt. Đoạn trích dẫn phải khớp chunk đã truy xuất. LLM không được hạ mức an toàn hay bịa thuốc ngoài output engine.

## 1.3 Phát biểu vấn đề và câu hỏi nghiên cứu

### 1.3.1 Vấn đề lâm sàng

Thiếu GDMT và sai trình tự vẫn phổ biến: chậm SGLT2i, không lập washout ARNI, kê MRA khi kali/eGFR rủi ro, tăng liều khi huyết động chưa ổn. CDSS cần trả lời: với lab, thuốc và rủi ro hiện tại, nên làm gì tiếp theo, kèm chặn an toàn rõ.

Ví dụ: nam 68 tuổi, HFrEF (LVEF 30%), đang ACEi và carvedilol, chưa MRA/SGLT2i; K+ 4,9; eGFR 38; HA 108/68. Kế hoạch phải xét đồng thời thêm SGLT2i, MRA, tăng liều beta blocker và lộ trình ARNI sau washout [2], [3].

### 1.3.2 Vấn đề kỹ thuật

Chat LLM thuần dễ viết đẹp nhưng không đáng tin để kê đơn [18], [19]. RAG giúp bám tài liệu [12] nhưng không tự cưỡng chế rule fail-closed. Engine chỉ rule mạnh về kiểm toán nhưng yếu intake chat và trích dẫn. Bài toán là ghép catalog có quản trị, logic cố định, truy xuất lai và LLM giới hạn vai trò.

### 1.3.3 Câu hỏi nghiên cứu

**RQ1 (Pipeline tri thức):** Làm sao nạp nhãn SPL FDA, guideline suy tim và nguồn tương tác vào catalog có quản trị, chỉ mục vector và đồ thị, vừa kiểm soát chi phí trích xuất vừa giữ độ đặc hiệu lâm sàng?

**RQ2 (Suy luận lai):** Làm sao kết hợp engine GDMT/an toàn cố định với GraphRAG lai và agent kiểm chứng để khuyến nghị khớp guideline, fail-closed trên chống chỉ định cứng, và giải thích LLM bám bằng chứng đã truy xuất?

**RQ3 (Giao diện song ngữ và an toàn):** Làm sao chat Việt–Anh stream thẻ khuyến nghị qua SSE không mất ngữ cảnh khi đổi ngôn ngữ, và các chỉ số so với tiêu chí mục 5.0 trên vignette HFrEF?

## 1.4 Công trình liên quan (tóm tắt)

Chương 2 xem xét chi tiết. Ở đây chỉ định vị luận văn:

- **CDSS cổ điển** [15], [4], [5], [17]: rule kiểm toán được; EHR thương mại mạnh tương tác chung nhưng ít tập trung khoảng trống GDMT HFrEF và chat song ngữ.
- **Đồ thị tri thức y** [7]–[11]: suy luận quan hệ; cần quản trị vì trích xuất tự động dễ nhiễu [8].
- **RAG / GraphRAG** [12]–[14]: neo LLM vào tài liệu; ít sản phẩm CDSS ghép đủ với tầng rule fail-closed cho GDMT.
- **Guideline và nhãn suy tim** [2], [3], [6]: chuẩn điều trị và chi tiết liều theo sản phẩm.

Khoảng trống: thiếu hệ HFrEF, song ngữ, chat có cấu trúc, nạp đa nguồn có quản trị, đánh giá trên đối tượng khuyến nghị có cấu trúc (không chỉ văn LLM trông hợp lý).

## 1.5 Bố cục luận văn

**Phần I** (chương này): bối cảnh, mục tiêu, phạm vi, vấn đề, RQ, công trình liên quan tóm tắt.

**Phần II:**

| Chương | Nội dung chính |
|--------|----------------|
| 2 | Lý thuyết CDSS, đồ thị, RAG, LLM, GraphRAG, nền HFrEF (không mô tả code) |
| 3 | Yêu cầu, kiến trúc, module, API, UI |
| 4 | Cài đặt, pipeline, Docker, kiểm thử |
| 5 | Tiêu chí 5.0, số liệu accuracy, latency, an toàn, usability |
| 6 | Đóng góp, trả lời RQ, hạn chế, hướng phát triển |

Tài liệu tham khảo và phụ lục hình nằm ở cuối luận văn tiếng Anh trong `thesis/`.
