# TÓM TẮT LUẬN VĂN

## TÓM TẮT (Abstract)

---

### Tiếng Việt

**XÂY DỰNG HỆ THỐNG HỖ TRỢ QUYẾT ĐỊNH LÂM SÀNG CHO BỆNH SUY TIM SỬ DỤNG KNOWLEDGE GRAPH VÀ GRAPHRAG**

**Ngành:** Công nghệ Thông tin

**Mã ngành:** 9480104

**Từ khóa:** Hệ thống hỗ trợ quyết định lâm sàng, Suy tim, Knowledge Graph, GraphRAG, Large Language Model

**Số trang:** 89 trang

---

**Mục tiêu nghiên cứu:** Nghiên cứu và xây dựng hệ thống hỗ trợ quyết định lâm sàng (CDSS) cho bệnh suy tim, tích hợp Knowledge Graph và Large Language Model, cung cấp khuyến nghị điều trị cá nhân hóa dựa trên bằng chứng khoa học.

**Phương pháp nghiên cứu:** Nghiên cứu lý thuyết về CDSS, Knowledge Graph, RAG và GraphRAG. Thiết kế kiến trúc hệ thống ba lớp. Triển khai pipeline xây dựng cơ sở tri thức tự động từ FDA Drug Labels và Clinical Guidelines. Đánh giá hiệu quả hệ thống qua thử nghiệm và khảo sát người dùng.

**Kết quả:** Xây dựng thành công hệ thống CDSS với độ chính xác khuyến nghị 94.0%, thời gian phản hồi trung bình 8.1 giây. Hệ thống hỗ trợ đa ngôn ngữ (Tiếng Việt/Tiếng Anh) và cung cấp giao diện hiển thị đơn giản hóa thuật ngữ y khoa. Điểm hài lòng người dùng đạt 4.22/5.0.

**Ý nghĩa:** Hệ thống góp phần nâng cao chất lượng điều trị suy tim theo hướng dẫn thực hành lâm sàng, hỗ trợ bác sĩ đưa ra quyết định nhanh chóng và chính xác hơn.

---

### English (Abstract)

**DEVELOPMENT OF A CLINICAL DECISION SUPPORT SYSTEM FOR HEART FAILURE USING KNOWLEDGE GRAPH AND GRAPHRAG**

**Field:** Information Technology

**Code:** 9480104

**Keywords:** Clinical Decision Support System, Heart Failure, Knowledge Graph, GraphRAG, Large Language Model

**Pages:** 89 pages

---

**Research objective:** Research and develop a Clinical Decision Support System (CDSS) for heart failure, integrating Knowledge Graph and Large Language Model, providing personalized treatment recommendations based on scientific evidence.

**Research methodology:** Theoretical research on CDSS, Knowledge Graph, RAG and GraphRAG. Design of three-tier system architecture. Implementation of automated knowledge base construction pipeline from FDA Drug Labels and Clinical Guidelines. Evaluation of system effectiveness through testing and user surveys.

**Results:** Successfully built CDSS with 94.0% recommendation accuracy and average response time of 8.1 seconds. System supports multi-language (Vietnamese/English) and provides simplified medical terminology display interface. User satisfaction score reached 4.22/5.0.

**Significance:** The system contributes to improving heart failure treatment quality according to clinical practice guidelines, supporting doctors in making faster and more accurate decisions.

---

## DANH MỤC TỪ VIẾT TẮT (Abbreviations)

| Từ viết tắt | Tiếng Anh | Tiếng Việt |
|--------------|----------|------------|
| ACEi | Angiotensin-Converting Enzyme inhibitor | Thuốc ức chế men chuyển Angiotensin |
| AHA | American Heart Association | Hiệp hội Tim mạch Hoa Kỳ |
| ARB | Angiotensin Receptor Blocker | Thuốc chẹn thụ thể Angiotensin |
| ARNI | Angiotensin Receptor-Neprilysin Inhibitor | Thuốc ức chế ARB và Neprilysin |
| API | Application Programming Interface | Giao diện lập trình ứng dụng |
| BNP | Brain Natriuretic Peptide | Peptide Natriuretic não |
| CDSS | Clinical Decision Support System | Hệ thống hỗ trợ quyết định lâm sàng |
| CKD | Chronic Kidney Disease | Bệnh thận mạn tính |
| CPU | Central Processing Unit | Bộ xử lý trung tâm |
| CRUD | Create, Read, Update, Delete | Tạo, Đọc, Sửa, Xóa |
| EHR | Electronic Health Record | Hồ sơ sức khỏe điện tử |
| eGFR | Estimated Glomerular Filtration Rate | Tốc độ lọc cầu thận ước tính |
| EN | English | Tiếng Anh |
| ESC | European Society of Cardiology | Hội Tim mạch Châu Âu |
| FDA | Food and Drug Administration | Cục Quản lý Thực phẩm và Dược phẩm Hoa Kỳ |
| FHIR | Fast Healthcare Interoperability Resources | Tiêu chuẩn FHIR |
| GDMT | Guideline-Directed Medical Therapy | Điều trị dựa trên hướng dẫn |
| GPU | Graphics Processing Unit | Bộ xử lý đồ họa |
| HF | Heart Failure | Suy tim |
| HFSA | Heart Failure Society of America | Hội Suy tim Hoa Kỳ |
| HFrEF | Heart Failure with reduced Ejection Fraction | Suy tim phân suy giảm phân suất tống máu |
| HIS | Hospital Information System | Hệ thống thông tin bệnh viện |
| HL7 | Health Level Seven | Tiêu chuẩn HL7 |
| JSON | JavaScript Object Notation | Định dạng JSON |
| K+ | Potassium | Kali |
| LLM | Large Language Model | Mô hình ngôn ngữ lớn |
| MRA | Mineralocorticoid Receptor Antagonist | Thuốc đối kháng thụ thể Mineralocorticoid |
| NER | Named Entity Recognition | Nhận diện thực thể có tên |
| NLP | Natural Language Processing | Xử lý ngôn ngữ tự nhiên |
| NPV | Negative Predictive Value | Giá trị dự báo âm |
| OAS | OpenAPI Specification | Đặc tả OpenAPI |
| ORM | Object-Relational Mapping | Ánh xạ đối tượng-quan hệ |
| PDF | Portable Document Format | Định dạng tài liệu di động |
| PostgreSQL | PostgreSQL | Hệ quản trị PostgreSQL |
| PPV | Positive Predictive Value | Giá trị dự báo dương |
| RAAS | Renin-Angiotensin-Aldosterone System | Hệ thống Renin-Angiotensin-Aldosterone |
| RAG | Retrieval Augmented Generation | Sinh trợ giúp Tìm kiếm |
| RAM | Random Access Memory | Bộ nhớ truy cập ngẫu nhiên |
| RBAC | Role-Based Access Control | Kiểm soát truy cập dựa trên vai trò |
| RCT | Randomized Controlled Trial | Thử nghiệm ngẫu nhiên có kiểm soát |
| REST | Representational State Transfer | REST |
| SGLT2i | Sodium-Glucose Cotransporter 2 inhibitor | Thuốc ức chế SGLT2 |
| SNOMED | Systematized Nomenclature of Medicine | Hệ thống danh pháp y học |
| SPL | Structured Product Label | Nhãn sản phẩm có cấu trúc |
| SQL | Structured Query Language | Ngôn ngữ truy vấn có cấu trúc |
| SSE | Server-Sent Events | Sự kiện gửi từ máy chủ |
| TLS | Transport Layer Security | Bảo mật tầng truyền tải |
| UMLS | Unified Medical Language System | Hệ thống ngôn ngữ y khoa thống nhất |
| VI | Vietnamese | Tiếng Việt |
| XML | Extensible Markup Language | Ngôn ngữ đánh dấu mở rộng |

---

## BẢNG KÝ HIỆU

| Ký hiệu | Ý nghĩa | Đơn vị |
|----------|----------|---------|
| % | Phần trăm | - |
| bpm | Nhịp tim mỗi phút (beats per minute) | /min |
| ° | Độ | - |
| °C | Độ Celsius | °C |
| mg | Miligam | mg |
| g | Gam | g |
| kg | Kilogam | kg |
| mEq/L | Milli-equivalent per liter | mEq/L |
| mmol/L | Milimol per liter | mmol/L |
| mL/min/1.73m² | Tốc độ lọc cầu thận | mL/min/1.73m² |
| mmHg | Milimet thủy ngân | mmHg |
| ≥ | Lớn hơn hoặc bằng | - |
| ≤ | Nhỏ hơn hoặc bằng | - |
| > | Lớn hơn | - |
| < | Nhỏ hơn | - |
| → | Dẫn đến, suy ra | - |
| ↔ | Tương đương, hai chiều | - |
