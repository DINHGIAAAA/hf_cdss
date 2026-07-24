# CHƯƠNG 1: GIỚI THIỆU

## 1.1. Đặt vấn đề

Suy tim (Heart Failure - HF) là một trong những bệnh lý tim mạch nguy hiểm nhất trên thế giới, ảnh hưởng đến hơn 64 triệu người trên toàn cầu [1]. Tại Việt Nam, theo thống kê của Bộ Y tế, suy tim đang có xu hướng gia tăng nhanh chóng và trở thành gánh nặng đáng kể cho hệ thống y tế. Bệnh suy tim không chỉ làm giảm chất lượng cuộc sống của người bệnh mà còn có tỷ lệ tử vong cao nếu không được chẩn đoán và điều trị kịp thời.

Việc điều trị suy tim đòi hỏi sự phối hợp đa chuyên khoa, bao gồm tim mạch, nội tiết, thận, và dinh dưỡng. Các bác sĩ lâm sàng cần nắm vững nhiều hướng dẫn điều trị (guidelines), tương tác thuốc phức tạp, và liều lượng chính xác dựa trên đặc điểm riêng của từng bệnh nhân. Điều này đặt ra thách thức lớn trong thực hành lâm sàng hàng ngày.

Một trong những phương pháp điều trị hiệu quả nhất cho suy tim có phân suy giảm chức năng tâm thu (Heart Failure with reduced Ejection Fraction - HFrEF) là **Điều trị dựa trên bằng chứng (Evidence-Based Therapy)**. Phác đồ điều trị bao gồm bốn nhóm thuốc chính (GDMT - Guideline-Directed Medical Therapy):

1. **Thuốc ức chế hệ thống Renin-Angiotensin (RAASi)**: ACE inhibitors, ARBs, hoặc ARNI
2. **Thuốc chẹn beta (Beta Blockers)**: Bisoprolol, Carvedilol, Metoprolol succinate
3. **Thuốc đối kháng aldosterone (MRAs)**: Spironolactone, Eplerenone
4. **Thuốc ức chế SGLT2 (SGLT2i)**: Dapagliflozin, Empagliflozin

Tuy nhiên, việc áp dụng đầy đủ phác đồ GDMT trong thực tế lâm sàng gặp nhiều khó khăn. Nghiên cứu cho thấy chỉ khoảng 1-2% bệnh nhân suy tim nhận được đầy đủ cả bốn nhóm thuốc này [2]. Các rào cản bao gồm:

- **Thiếu thông tin**: Bác sĩ không thể cập nhật kịp thời tất cả các nghiên cứu mới
- **Quá tải thông tin**: Khối lượng hướng dẫn điều trị quá lớn để tổng hợp
- **Phức tạp về tương tác thuốc**: Nhiều tương tác cần tránh và cảnh báo
- **Khác biệt cá thể**: Liều lượng phụ thuộc vào chức năng thận, mức kali, và các yếu tố khác

Trước thực trạng này, việc xây dựng một **Hệ thống hỗ trợ quyết định lâm sàng (Clinical Decision Support System - CDSS)** đóng vai trò quan trọng trong việc giúp bác sĩ đưa ra quyết định điều trị chính xác và kịp thời.

## 1.2. Mục tiêu nghiên cứu

### 1.2.1. Mục tiêu chung

Xây dựng và phát triển một Hệ thống hỗ trợ quyết định lâm sàng (CDSS) cho bệnh suy tim, tích hợp tri thức y khoa từ các nguồn dữ liệu đa dạng, cung cấp khuyến nghị điều trị cá nhân hóa dựa trên bằng chứng khoa học.

### 1.2.2. Mục tiêu cụ thể

1. **Nghiên cứu và xây dựng cơ sở tri thức y khoa** từ các nguồn:
   - Nhãn thuốc FDA (FDA Drug Labels)
   - Hướng dẫn điều trị lâm sàng (Clinical Guidelines)
   - Cơ sở dữ liệu tương tác thuốc

2. **Thiết kế và triển khai hệ thống CDSS** với các chức năng:
   - Phân tích hồ sơ bệnh nhân
   - Đề xuất phác đồ điều trị GDMT
   - Kiểm tra tương tác thuốc
   - Tính toán liều lượng thuốc
   - Cảnh báo an toàn dựa trên chức năng thận và điện giải

3. **Đánh giá hiệu quả** của hệ thống thông qua:
   - Độ chính xác của khuyến nghị
   - Khả năng áp dụng trong thực tế lâm sàng
   - Độ hài lòng của người sử dụng

## 1.3. Phạm vi nghiên cứu

### 1.3.1. Phạm vi về bệnh lý

- Tập trung vào **Suy tim có phân suy giảm chức năng tâm thu (HFrEF)** - loại phổ biến nhất của suy tim
- Các khuyến nghị dựa trên hướng dẫn của ESC (European Society of Cardiology) và ACC/AHA (American College of Cardiology/American Heart Association)

### 1.3.2. Phạm vi về chức năng

- Hỗ trợ quyết định cho bác sĩ chuyên khoa tim mạch
- Không bao gồm chẩn đoán tự động (khuyến nghị vẫn do bác sĩ xem xét và quyết định)
- Tập trung vào mặt dược lý của điều trị suy tim

### 1.3.3. Phạm vi về dữ liệu

- Sử dụng nguồn dữ liệu từ:
  - Cơ sở dữ liệu thuốc FDA
  - Hướng dẫn điều trị được công bố
  - Tài liệu y khoa có kiểm chứng

## 1.4. Ý nghĩa nghiên cứu

### 1.4.1. Ý nghĩa khoa học

- Đóng góp phương pháp tiếp cận xây dựng cơ sở tri thức y khoa tự động từ nhiều nguồn dữ liệu không đồng nhất
- Đề xuất mô hình CDSS kết hợp Knowledge Graph và Large Language Model (LLM)

### 1.4.2. Ý nghĩa thực tiễn

- Giúp bác sĩ tiết kiệm thời gian trong việc tra cứu thông tin thuốc
- Giảm thiểu sai sót trong kê đơn thuốc
- Nâng cao chất lượng điều trị suy tim theo hướng dẫn thực hành lâm sàng
- Đặc biệt có ý nghĩa trong bối cảnh Việt Nam, nơi tỷ lệ bác sĩ/trên dân số còn thấp

## 1.5. Cấu trúc luận văn

Luận văn được tổ chức thành các chương sau:

- **Chương 2**: Trình bày cơ sở lý thuyết về CDSS, Knowledge Graph, và các công nghệ liên quan
- **Chương 3**: Mô tả thiết kế và kiến trúc tổng thể của hệ thống
- **Chương 4**: Trình bày chi tiết quá trình cài đặt và triển khai
- **Chương 5**: Kết quả thử nghiệm và đánh giá hệ thống
- **Chương 6**: Kết luận và hướng phát triển tiếp theo

---

## Tài liệu tham khảo Chương 1

[1] GBD 2017 Disease and Injury Incidence and Prevalence Collaborators. (2018). Global, regional, and national incidence, prevalence, and years lived with disability for 354 diseases and injuries for 195 countries and territories, 1990–2017: a systematic analysis for the Global Burden of Disease Study 2017. *The Lancet*, 392(10159), 1789-1858.

[2] Greene, S. J., Butler, J., & Fonarow, G. C. (2021). Simultaneous or sequential initiation of quadruple therapy for heart failure with reduced ejection fraction. *JACC: Heart Failure*, 9(10), 725-732.

[3] BẢNG DỮ LIỆU BỆNH VIỆN TIM HÀ NỘI (2023). Báo cáo thống kê bệnh suy tim.
