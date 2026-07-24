# CHƯƠNG 6: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN

## 6.1. Kết luận

### 6.1.1. Tổng kết kết quả

Trong luận văn này, chúng tôi đã nghiên cứu, thiết kế và triển khai thành công một Hệ thống hỗ trợ quyết định lâm sàng (CDSS) cho bệnh suy tim. Hệ thống tích hợp nhiều công nghệ tiên tiến bao gồm Knowledge Graph, GraphRAG, và Large Language Models để cung cấp khuyến nghị điều trị cá nhân hóa và chính xác.

**Các đóng góp chính của luận văn:**

**1. Kiến trúc hệ thống CDSS cho suy tim:**

Chúng tôi đã đề xuất một kiến trúc ba lớp (presentation, application, data) kết hợp GraphRAG để xây dựng hệ thống CDSS chuyên biệt cho bệnh suy tim. Kiến trúc này cho phép:

- Truy xuất tri thức y khoa hiệu quả từ đồ thị tri thức
- Sinh khuyến nghị điều trị dựa trên bằng chứng
- Cung cấp phản hồi theo thời gian thực qua giao diện chat

**2. Pipeline xây dựng cơ sở tri thức tự động:**

Chúng tôi đã phát triển một pipeline tự động để trích xuất, xử lý và đồng bộ tri thức y khoa từ nhiều nguồn dữ liệu đa dạng:

- FDA Drug Labels (SPL format)
- Clinical Guidelines (ESC, AHA/ACC)
- Drug Interaction Databases

Pipeline sử dụng phương pháp lọc ba tầng (keyword → semantic → LLM review) để xác định các sections quan trọng, đạt tỷ lệ precision 95% trong việc giữ lại thông tin lâm sàng cần thiết.

**3. Giao diện người dùng đa ngôn ngữ:**

Hệ thống hỗ trợ tiếng Việt và tiếng Anh với tính năng chuyển đổi ngôn ngữ không mất ngữ cảnh hội thoại. Đặc biệt, chúng tôi đã phát triển module Simplified Display để chuyển đổi thuật ngữ y khoa chuyên ngành thành ngôn ngữ dễ hiểu hơn cho người dùng.

**4. Đánh giá hiệu quả:**

Kết quả thử nghiệm cho thấy:

- Độ chính xác khuyến nghị điều trị đạt 94.0%
- Thời gian phản hồi trung bình 8.1 giây (đáp ứng yêu cầu < 10 giây)
- 92.5% sensitivity trong việc phát hiện các vấn đề an toàn
- Điểm hài lòng người dùng 4.22/5.0

### 6.1.2. Ý nghĩa đóng góp

**Ý nghĩa khoa học:**

1. Đề xuất phương pháp kết hợp Knowledge Graph với RAG (GraphRAG) trong lĩnh vực CDSS cho suy tim
2. Phát triển pipeline tự động xây dựng cơ sở tri thức y khoa từ nhiều nguồn không đồng nhất
3. Đề xuất phương pháp lọc sections ba tầng (keyword + semantic + LLM) để tối ưu chi phí LLM

**Ý nghĩa thực tiễn:**

1. Hỗ trợ bác sĩ trong việc đưa ra quyết định điều trị suy tim theo hướng dẫn thực hành lâm sàng
2. Giảm thiểu sai sót trong kê đơn thuốc thông qua hệ thống cảnh báo an toàn
3. Tiết kiệm thời gian tra cứu thông tin cho bác sĩ
4. Đặc biệt có ý nghĩa trong bối cảnh Việt Nam với nguồn nhân lực y tế còn hạn chế

### 6.1.3. Hạn chế

Bên cạnh những kết quả đạt được, luận văn còn một số hạn chế:

1. **Phạm vi drugs còn giới hạn**: Hệ thống mới cover 60 drugs chính, chưa bao gồm đầy đủ các thuốc đang sử dụng tại Việt Nam

2. **Chưa tích hợp HL7/FHIR**: Hiện tại dữ liệu bệnh nhân được nhập thủ công qua chat, chưa kết nối trực tiếp với hệ thống HIS/HIS

3. **LLM vẫn có hallucination**: Mặc dù sử dụng GraphRAG để giảm thiểu, LLM vẫn có thể sinh ra thông tin sai, đòi hỏi human-in-the-loop

4. **Chưa có clinical trial**: Hệ thống chưa được đánh giá trong môi trường thử nghiệm lâm sàng thực tế

5. **Không có mobile app**: Chỉ hỗ trợ web, chưa có ứng dụng di động

## 6.2. Hướng phát triển

### 6.2.1. Cải thiện ngắn hạn

**1. Mở rộng cơ sở dữ liệu thuốc:**

- Bổ sung thêm 100+ drugs thường dùng trong điều trị suy tim tại Việt Nam
- Tích hợp danh mục thuốc Việt Nam (Thuốc_generic, Vietnamese Drug Dictionary)
- Xây dựng drug synonyms database cho tiếng Việt

**2. Tích hợp FHIR/HL7:**

```
Priority: Cao
Thời gian: 3 tháng
Resources: 1 backend developer, 1 integration specialist

Mục tiêu:
- Kết nối với HIS bệnh viện
- Tự động nhận dữ liệu bệnh nhân từ EHR
- Xuất khuyến nghị theo FHIR format
```

**3. Cải thiện drug name extraction:**

- Fine-tune NER model cho tiếng Việt
- Xây dựng drug name aliases database
- Hỗ trợ tên thuốc thương mại Việt Nam

### 6.2.2. Phát triển trung hạn

**4. Mở rộng sang bệnh lý khác:**

```
Phase 1: Diabetes Management
├── Blood glucose monitoring
├── Insulin dosing
└── Diabetes-HF comorbidity

Phase 2: CKD Management
├── eGFR tracking
├── Renal dosing
└── Dialysis protocols

Phase 3: Anticoagulation
├── DOAC dosing
├── Warfarin management
└── Bleeding risk assessment
```

**5. Mobile Application:**

- Phát triển React Native app cho iOS/Android
- Offline mode cho areas có internet hạn chế
- Push notifications cho drug interaction alerts

**6. Clinical Decision Dashboard:**

- Tổng hợp recommendations cho multiple patients
- Population health analytics
- Outcome tracking

### 6.2.3. Nghiên cứu dài hạn

**7. Fine-tune LLM cho clinical domain:**

```
Model: Qwen2.5-7B → HF-CDSs-Finetuned
Training Data:
- 10,000+ clinical notes (de-identified)
- Drug interaction pairs
- Guideline paragraphs
- Q&A pairs from medical textbooks

Expected Improvements:
- 15% reduction in hallucination
- Better Vietnamese clinical terminology
- Improved dosing accuracy
```

**8. Federated Learning cho privacy:**

- Train models across multiple hospitals without sharing patient data
- Collaborative learning while maintaining HIPAA/PDPD compliance
- Local model updates aggregated centrally

**9. Real-time clinical trial matching:**

- Match patients to relevant clinical trials
- Eligibility criteria matching
- Trial outcome tracking

### 6.2.4. Đề xuất nghiên cứu tiếp theo

**Nghiên cứu 1: Đánh giá lâm sàng có kiểm soát**

Mục tiêu: Đánh giá hiệu quả của CDSS trong thực tế lâm sàng tại bệnh viện.

Phương pháp:
- Randomized controlled trial (RCT)
- 200 bệnh nhân suy tim
- Primary outcome: GDMT optimization rate
- Secondary outcome: 30-day readmission rate

**Nghiên cứu 2: So sánh GraphRAG vs Vector RAG**

Mục tiêu: Đánh giá hiệu quả của GraphRAG so với Vector RAG truyền thống trong CDSS.

Phương pháp:
- A/B testing trên production
- Metrics: precision, recall, response time, user satisfaction
- Statistical analysis

**Nghiên cứu 3: Explainable AI cho CDSS**

Mục tiêu: Phát triển phương pháp giải thích khuyến nghị CDSS một cách minh bạch.

Phương pháp:
- Attention visualization
- Knowledge graph path explanation
- Evidence citation

## 6.3. Kết luận chung

Bệnh suy tim là một trong những gánh nặng y tế lớn nhất trên thế giới và tại Việt Nam. Việc điều trị suy tim đòi hỏi kiến thức chuyên sâu về nhiều nhóm thuốc, tương tác thuốc, và theo dõi chặt chẽ các chỉ số lâm sàng. Hệ thống CDSS được đề xuất trong luận văn này là một bước tiến quan trọng trong việc hỗ trợ bác sĩ đưa ra quyết định điều trị chính xác và kịp thời.

Với kết quả đạt được (94% accuracy, 8.1s response time, 4.22/5 user satisfaction), hệ thống cho thấy tiềm năng lớn trong việc cải thiện chất lượng điều trị suy tim. Tuy nhiên, để triển khai rộng rãi trong thực tế, cần tiếp tục mở rộng cơ sở tri thức, tích hợp với hệ thống thông tin bệnh viện, và tiến hành các thử nghiệm lâm sàng có kiểm soát.

Luận văn này không chỉ đóng góp một hệ thống CDSS cụ thể mà còn đề xuất phương pháp tiếp cận có thể áp dụng cho các bệnh lý và lĩnh vực y tế khác, góp phần vào mục tiêu nâng cao chất lượng chăm sóc sức khỏe cho người dân Việt Nam.

---

## Tài liệu tham khảo Chương 6

[1] McDonagh, T. A., Metra, M., Adamo, M., Gardner, R. S., Baumbach, A., Böhm, M., ... & Pelliccia, A. (2021). 2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure. *European Heart Journal*, 42(36), 3599-3726.

[2] Heidenreich, P. A., Bozkurt, B., Aguilar, D., Allen, L. A., Byun, J. J., Colvin, M. M., ... & Yancy, C. W. (2022). 2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure. *Journal of the American College of Cardiology*, 79(17), e263-e421.

[3] World Health Organization. (2023). *Global Health Estimates 2023*. WHO Press.

[4] Bộ Y tế Việt Nam. (2023). *Báo cáo tổng kết công tác y tế năm 2023 và nhiệm vụ, giải pháp năm 2024*.

[5]able AI in Healthcare. (2024). *The AI Healthcare Report*. Tractica.
