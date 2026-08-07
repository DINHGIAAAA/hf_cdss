# CHƯƠNG 6: KẾT LUẬN

*(Bản dịch chi tiết từ `thesis/Chapter6_Conclusion.md`)*

Chương này kết thúc luận văn bằng cách tóm tắt những gì đã xây dựng, đánh giá cho thấy gì, phần nào còn dở, và bước tiếp theo nên là gì. Hệ hỗ trợ quyết định lâm sàng (CDSS) suy tim được thiết kế để kết hợp tri thức y được quản trị, logic an toàn tất định, và hỗ trợ mô hình ngôn ngữ lớn (LLM) mà không coi model là người kê đơn tự trị. Câu hỏi xuyên suốt dự án là liệu cách tiếp cận lai đó có thể cung cấp hỗ trợ chính xác, kịp thời, giải thích được và song ngữ trong khi bác sĩ vẫn kiểm soát quyết định cuối.

## 6.1 Tóm tắt đóng góp

Luận văn nghiên cứu, thiết kế, cài đặt và đánh giá một hệ hỗ trợ quyết định lâm sàng chuyên suy tim. Thay vì yêu cầu LLM kê đơn trực tiếp, kiến trúc giao sinh xác suất cho các tác vụ ngôn ngữ tự nhiên thêm giá trị, như giải thích bằng chứng, trong khi dành trạng thái điều trị có thẩm quyền cho catalog PostgreSQL được đánh giá bởi dịch vụ tất định.

Công trình xuất phát từ khoảng trống lâm sàng dai dẳng. Suy tim phân suất tống máu giảm (HFrEF) có bằng chứng mạnh cho điều trị nội khoa theo hướng dẫn (GDMT) bốn thuốc, nhưng dùng thực tế ở liều đích vẫn rất thấp. Đồng thời, công cụ chat mục đích chung dễ tương tác nhưng thiếu an toàn dược lý được quản trị phù hợp để tin cậy trực tiếp lâm sàng. Luận văn kiểm tra liệu thiết kế lai có thể giải quyết căng thẳng đó trong hệ triển khai được với tiêu chí đo lường, không chỉ như lập luận khái niệm.

Về kiến trúc, hệ trải trên tầng trình bày, ứng dụng và dữ liệu. Tầng trình bày cung cấp dashboard bác sĩ React với chat stream, thẻ khuyến nghị có cấu trúc, và chuyển ngôn ngữ song ngữ tái sinh nhãn dễ hiểu mà không chạy lại suy luận lâm sàng. Tầng ứng dụng điều phối intake bệnh nhân lai, suy luận tất định, truy xuất GraphRAG lai, kiểm chứng, tính liều, và tóm tắt thẻ qua dịch vụ FastAPI. Tầng dữ liệu lưu quy tắc được quản trị trong PostgreSQL, cache phiên trong Redis, embedding trong ChromaDB, cấu trúc đồ thị trong Neo4j, và phiên bản artifact pipeline trong kho đối tượng.

Về kỹ thuật tri thức, luận văn đóng góp pipeline nạp tự động cho nhãn thuốc cấu trúc FDA (SPL) và guideline suy tim. Bộ lọc mục ba tầng dùng khớp từ khóa trước, độ tương đồng embedding thứ hai, và chỉ gọi LLM duyệt trường hợp không chắc chắn. Nội dung đã lọc được cắt đoạn, phân tích, và chuyển thành quy tắc có cấu trúc phân loại theo tầng an toàn và loại hành động trước khi đồng bộ PostgreSQL và lập chỉ mục truy xuất. Đánh giá cho thấy giữ 95,0% mục với duyệt model vùng biên chỉ trên 6,6% đầu vào. Manifest đăng ký 127 thuốc; 60 được tích hợp đầy đủ để đánh giá, tạo 4.136 mục nhãn, 6.032 quy tắc ràng buộc, và 1.096 quy tắc tương tác.

Về thời điểm truy vấn, luận văn đóng góp intake lâm sàng lai kết hợp trích xuất regex, khớp lexicon, khớp ngữ nghĩa, và fallback model có chọn lọc. eGFR thiếu có thể được ước tính tất định từ creatinine, tuổi và giới khi không có giá trị trực tiếp. Engine suy luận đánh giá phạm vi GDMT, ràng buộc, tương tác và kế hoạch liều độc lập với output model. Truy xuất GraphRAG lai cung cấp bằng chứng sẵn sàng trích dẫn cho giải thích mà không ghi đè trạng thái có cấu trúc. Truyền stream gửi sự kiện có cấu trúc theo thứ tự an toàn trước để bác sĩ thấy tóm tắt bệnh nhân và thẻ khuyến nghị trước khi văn bản tường thuật hoàn tất.

Về an toàn và khả năng giải thích, chặn cứng (hard block) thực thi chống chỉ định fail-closed, agent kiểm chứng rà soát khuyến nghị trước khi stream kết thúc, và tóm tắt thẻ ánh xạ trường có cấu trúc sang nhãn tiếng Việt và tiếng Anh dễ hiểu một cách tất định. Tối ưu cảnh báo giảm gánh nặng cảnh báo từ 8,2 xuống 4,3 mỗi bệnh nhân trong khi vẫn giữ hiển thị chặn cứng.

Về thự nghiệm, độ chính xác khuyến nghị điều trị đạt 94,0% với khoảng tin cậy 95% từ 89,2% đến 98,8% trên 50 ca bác sĩ tim mạch duyệt, vượt mục tiêu 90%. Thời gian phản hồi end-to-end trung bình 8,1 giây với trung vị 7,4 giây và phân vị 95 (P95) 12,6 giây. Độ nhạy an toàn là 92,5%. Phát hiện tương tác đạt điểm F1 97,1%. Mức hài lòng người dùng trong 25 bác sĩ tim mạch khảo sát trung bình 4,22 trên 5, với hữu ích lâm sàng cao nhất ở 4,5. Cả bốn kịch bản an toàn rủi ro cao biên soạn đều đạt. Xây tri thức đạt 94,2% thành công trích xuất nhãn, giữ 95,0% mục, và khoảng 45 giây xử lý trung bình mỗi thuốc.

Về khoa học, công trình đóng góp phương pháp GraphRAG cho hỗ trợ quyết định suy tim hợp nhất truy xuất đồ thị và vector với engine quy tắc tất định, pipeline tự động xây cơ sở tri thức y được quản trị từ nhãn quy định và guideline, và mẫu cổng tiết kiệm chi phí dành dung lượng model cho đầu vào không chắc chắn. Về thực tiễn, hệ hỗ trợ rà soát GDMT theo guideline, giảm rủi ro kê đơn qua cảnh báo phân tầng và kiểm chứng, và tiết kiệm thời gian bác sĩ tra cứu thuốc và guideline, đặc biệt nơi thiếu chuyên khoa và giao tiếp song ngữ quan trọng.

Ngoài phần mềm, luận văn bàn giao artifact tái lập được: pipeline nạp và output từng giai đoạn, schema quản trị với vòng đời nháp, đã duyệt và ngưng dùng, bộ đánh giá 50 ca và bốn kịch bản an toàn, môi trường chạy được Docker Compose, và tài liệu từ lý do thiết kế, ngữ nghĩa sự kiện API, mô hình hóa mối đe dọa, đánh đổi triển khai, đến ranh giới hợp lệ.

## 6.2 Suy ngẫm về câu hỏi nghiên cứu

Chương 1 đặt ba câu hỏi nghiên cứu về xây tri thức, suy luận lai và giao diện song ngữ có an toàn. Đánh giá ủng hộ câu trả lời khẳng định với sắc thái quan trọng.

Kiến trúc lai có đạt độ chính xác khuyến nghị mức guideline mà không ủy quyền an toàn cho LLM? Độ chính xác 94,0% trên đối tượng khuyến nghị có cấu trúc ủng hộ câu trả lời có điều kiện là có. Độ chính xác được đo trên output tất định, không trên văn xuôi sinh ra. Độ phủ MRA 89,3% và lỗi phụ thuộc intake cho thấy khoảng trống còn lại nơi độ đầy đủ xét nghiệm và danh pháp thuốc địa phương quan trọng. Quy tắc chặn cứng và agent kiểm chứng đảm bảo chống chỉ định mã hóa không bị ghi đè im lặng, và cả bốn kịch bản an toàn biên soạn đều đạt. Độ đặc hiệu 95,2% cao hơn độ nhạy 92,5%, cho thấy hệ nghiêng về thận trọng, phù hợp trong hỗ trợ quyết định dược lý.

Cổng tiết kiệm chi phí model có làm xây tri thức tự động khả thi vận hành? Bộ lọc mục giữ 95,0% mục trong khi tránh gọi model trên 93,4% đầu vào so với duyệt toàn bộ ngây thơ, và intake lai hoàn thành trung bình 1,2 giây. Kết quả ủng hộ có cho corpus và hồ sơ phần cứng đã đánh giá. Tài liệu guideline cần duyệt vùng biên nhiều hơn nhãn thuốc, gợi ý cần tinh chỉnh liên tục khi định dạng nhà xuất bản mới xuất hiện. Nạp khoảng 45 giây mỗi thuốc khả thi cho chu kỳ làm mới batch thay vì khám phá thời gian thực.

Truy xuất GraphRAG lai có cải thiện khả năng giải thích và tin cậy so với cách truy xuất đơn giản hơn? Thí nghiệm so sánh A/B có kiểm soát không được thực hiện, nhưng F1 tương tác cao 97,1% và phân tích định tính gợi ý hợp nhất tìm kiếm dày, tìm kiếm từ khóa và lân cận đồ thị góp phần giải thích giàu bằng chứng mà không thay quy tắc tất định. Mức hài lòng bác sĩ về độ chính xác khuyến nghị cảm nhận là 4,1 trên 5 trong khi hữu ích lâm sàng là 4,5 trên 5, gợi ý bác sĩ đánh giá cao thẻ có cấu trúc cộng tường thuật có trích dẫn hơn chỉ một lớp.

Latency tương tác dưới 10 giây có đạt được với suy luận model cục bộ trên phần cứng bệnh viện vừa phải? Latency trung bình 8,1 giây và trung vị 7,4 giây đạt mục tiêu trung vị. Phân vị 95 là 12,6 giây không đạt cách hiểu nghiêm rằng 95% ca phải hoàn thành dưới 10 giây. Stream giảm độ trễ cảm nhận. Sinh câu trả lời trung bình 3,5 giây vẫn là nút thắt chính.

Hỗ trợ song ngữ tiếng Việt và tiếng Anh có cùng tồn tại với liên tục hội thoại và hiển thị an toàn tất định? Chuyển ngôn ngữ dưới 2 giây không mất dữ liệu và tóm tắt thẻ tất định ủng hộ có cho tầng giao diện. Độ phủ intake trên tên biệt dược tiếng Việt vẫn chưa đầy đủ, nên trình bày song ngữ một mình không giải quyết danh pháp địa phương hóa trong lexicon trích xuất.

Tổng hợp lại, các câu trả lời xác thực luận điểm luận văn trong ranh giới đã đánh giá. Hỗ trợ quyết định suy tim lai khả thi, đủ chính xác cho dùng lâm sàng dưới giám sát, và khác biệt so với thay thế chỉ tiếng Anh, không chat, hoặc chỉ model. Chưa được chứng minh là can thiệp cải thiện kết cục.

Yếu ở bất kỳ chiều nào giới hạn mức sẵn sàng triển khai tổng thể mà không vô hiệu hóa mẫu lai. Tên thuốc tiếng Việt, latency đuôi, và catalog liều chưa đầy đủ là mở rộng cùng kiến trúc, không phải lý do thay catalog được quản trị bằng kê đơn end-to-end model sẽ hy sinh khả năng kiểm toán.

## 6.3 Hạn chế

Vài hạn chế giới hạn kết luận và mức sẵn sàng hệ cho triển khai lâm sàng không giám sát.

Phạm vi thuốc vẫn chưa đầy đủ. Dù 127 thuốc xuất hiện trong registry nguồn, đánh giá độ chính xác tập trung 60 hoạt chất tích hợp đầy đủ. Nhiều thuốc thường kê ở Việt Nam, gồm biệt dược địa phương chỉ được nhận diện bằng tiếng Việt, chưa được lexicon intake nhận đáng tin. Mở rộng từ 60 lên 127 hoạt chất tích hợp chủ yếu là khối lượng kỹ thuật và quản trị thay vì thay đổi kiến trúc căn bản.

Nhập dữ liệu bệnh nhân phụ thuộc chat văn bản tự do thay vì nguồn HL7 hoặc FHIR từ hệ thông tin bệnh viện. Nhập thủ công tăng tỷ lệ bỏ sót creatinine, eGFR và kali. Điều đó lan sang ước tính eGFR suy diễn, dương tính giả cảnh báo thận, và giảm độ phủ MRA. Không có tương tác vận hành có cấu trúc, hệ không thể tự đồng bộ với nguồn xét nghiệm thẩm quyền hay xuất khuyến nghị vào hồ sơ điện tử theo định dạng chuẩn.

Dù neo truy xuất và kiểm chứng giảm rủi ro ảo giác so với chatbot độc lập, tường thuật sinh ra vẫn có thể chứa phát biểu sai hoặc bỏ sót sắc thái chỉ có trong văn xuôi guideline. Chỉ số độ chính xác 94,0% áp dụng cho đối tượng khuyến nghị có cấu trúc bác sĩ tim mạch duyệt, không phải mọi token văn bản trả lời. Vì vậy vẫn cần người duyệt trước khi khuyến nghị ảnh hưởng kê đơn hoặc quyết định chuẩn liều.

Thiết kế đánh giá hồi cứu trên vignette biên soạn thay vì nghiên cứu can thiệp tiến cứu. Kết quả khả năng sử dụng và đo latency phản ánh tác vụ có kiểm soát và stack phần cứng cụ thể với RTX 3080 và 32 GB RAM. Khái quát hóa sang môi trường ít tài nguyên hơn hoặc triển khai bệnh viện đồng thời cao cần xác thực thêm. Truy cập qua web không có client di động bản địa, hạn chế quy trình tại giường nơi bác sĩ thích thiết bị cầm tay.

Các hạn chế này định nghĩa điều kiện biên thay vì làm giảm đóng góp. Tuyên bố độ chính xác 94,0% gắn với output có cấu trúc bác sĩ tim mạch duyệt trên 60 thuốc tích hợp với vignette xét nghiệm tương đối đầy đủ. Tuyên bố latency trung bình 8,1 giây gắn với suy luận cục bộ tăng tốc GPU trên phần cứng 16 nhân. Tuyên bố hài lòng 4,22 trên 5 gắn với 25 bác sĩ tim mạch sau tác vụ hướng dẫn, không phải áp dụng thực tế dài hạn.

Hạn chế cũng phân bố không đều giữa các tầng. Tầng tri thức vẫn giữ 35,2% quy tắc trích xuất ở trạng thái tinh chỉnh và quy tắc liều chưa hoàn thiện. Tầng suy luận phụ thuộc chất lượng intake. Tầng giải thích kế thừa tính ngẫu nhiên model dù văn bản thẻ tất định. Tầng triển khai giả định topology Docker Compose một máy chủ không có chứng nhận quy định chính thức. Tầng đánh giá dùng cỡ mẫu vừa đủ minh họa luận văn nhưng không đủ nộp quy định hay tuyên bố kết cục dứt khoát.

Các khoảng trống khác đáng nêu. Đa thuốc ngoài các nhóm GDMT đã mô hình hóa chỉ được phủ một phần. Suy luận bệnh đồng mắc ngoài trọng tâm suy tim chưa đầy đủ. Phiên bản guideline theo snapshot và cần resync pipeline sau cập nhật. Công bằng và thiên lệch chưa được đánh giá chính thức vì nguồn tập trung guideline Hoa Kỳ và quốc tế. Đánh giá bảo mật dừng ở mô hình hóa mối đe dọa cấp thiết kế không có kiểm thử xâm nhập. Khả năng mở rộng vượt đánh giá một người dùng chưa được load-test ở đồng thời mục tiêu. Lộ trình quy định cho phần mềm thiết bị y tế chưa được xử lý.

## 6.4 Hướng phát triển

Công việc tương lai nên mở rộng các thành phần mẫu lai thay vì thay an toàn được quản trị bằng model end-to-end đơn khối.

Tác động ngắn hạn cao nhất có thể đến từ tích hợp FHIR vì nó tấn công nguyên nhân gốc bỏ sót intake. Tích hợp tối thiểu nên tiêu thụ nhân khẩu bệnh nhân, quan sát xét nghiệm cho creatinine, kali và eGFR, và tuyên bố thuốc đang dùng trước khi hợp nhất chat. Xuất nên ghi artifact khuyến nghị có cấu trúc cho kiểm toán hồ sơ điện tử, không chỉ văn xuôi model. Nhập xét nghiệm và thuốc chỉ đọc khả thi trong khoảng ba tháng; ghi ngược và quy trình đồng ý sản xuất là nỗ lực trung hạn cần rà soát bảo mật cơ sở.

Bản địa hóa tiếng Việt nên sâu hơn chuỗi giao diện. Lexicon thu thập và intake cần từ đồng nghĩa Bộ Y tế và formulary bệnh viện để đóng lớp lỗi bỏ sót thuốc chiếm ưu thế. Guideline suy tim soạn hoặc dịch địa phương có thể cần khi PDF guideline tiếng Anh không đủ cho tư vấn hướng bệnh nhân. Mọi fine-tuning model cho văn xuôi lâm sàng tiếng Việt không được chuyển phân loại an toàn vào model đã fine-tune. Thực thi chặn cứng nên vẫn tất định.

Mở rộng cơ sở dữ liệu thuốc vượt tập con tích hợp hiện tại là ưu tiên ngay. Hoàn thiện catalog quy tắc liều sẽ mở khóa hiển thị chuẩn liều phong phú hơn bên cạnh khoảng trống GDMT cấp nhóm. Client di động React Native, API tương tác thuốc riêng, và dashboard phòng khám đa bệnh nhân là mở rộng trung hạn. Cùng kiến trúc module sau này có thể hỗ trợ miền liền kề như đái tháo đường, bệnh thận mạn và kháng đông bằng cách tái dùng schema quản trị, giao thức stream và mẫu kiểm chứng trong khi thay chính sách và lexicon theo bệnh.

Nghiên cứu dài hạn gồm fine-tuning model song ngữ trên ghi chú đã ẩn danh và trích xuất có nhãn, học liên kết (federated learning) giữa bệnh viện không tập trung thông tin sức khỏe được bảo vệ, thử nghiệm A/B có kiểm soát so GraphRAG lai với truy xuất chỉ vector, khả năng giải thích đường đồ thị trên giao diện, và thử nghiệm kết cục tiến cứu đo tối ưu GDMT và tái nhập viện thay vì chỉ độ chính xác vignette.

Công việc tương lai có thể nhóm theo chu kỳ thời gian mà không bịa chỉ tiêu hiệu suất mới. Ngắn hạn trong không đến sáu tháng, ưu tiên gồm tích hợp từ đồng nghĩa thuốc tiếng Việt, nạp quan sát và thuốc FHIR, hoàn thiện catalog liều, mở rộng hồi quy an toàn vượt bốn kịch bản, và giảm latency đuôi qua tối ưu stream câu trả lời và cache kiểm chứng. Trung hạn trong sáu đến mười tám tháng, ưu tiên gồm truy cập di động, API tương tác bên thứ ba, dashboard phòng khám, nguyên mẫu bệnh đồng mắc, và so sánh truy xuất có kiểm soát trên cùng ca. Dài hạn sau mười tám tháng, ưu tiên gồm fine-tuning song ngữ, học liên kết, thử nghiệm ngẫu nhiên kết cức, và giao diện giải thích phong phú hơn.

Tiến hóa bền vững cần hợp tác liên tục giữa kỹ sư phần mềm, đầu mối lâm sàng và CNTT bệnh viện. Đầu mối lâm sàng phải duyệt quy tắc tầng tinh chỉnh và phân xử báo cáo cảnh báo dương tính giả từ thí điểm. Kỹ sư phải chạy lại nạp theo lịch, theo dõi số model vùng biên, và duy trì hồi quy trên bộ 50 ca và bốn kịch bản an toàn. CNTT bệnh viện phải cung cấp endpoint FHIR, chứng chỉ, chính sách sao lưu và lập kế hoạch dung lượng. Không có quản trị lâm sàng cơ sở, dù catalog quy tắc chính xác vẫn lỗi thời khi guideline thay đổi.

## 6.5 Hàm ý cho nghiên cứu và thực hành CDSS

Phát hiện mang hàm ý vượt triển khai cụ thể này.

Thứ nhất, khoảng cách giữa độ chính xác 94,0% trên output có cấu trúc và rủi ro ảo giác còn lại trong tường thuật sinh ra củng cố đồng thuận đang hình thành. Triển khai LLM trong dược lý nên chuẩn hóa truyền kênh đôi: artifact quyết định máy đọc được với nguồn gốc tất định, cộng giải thích ngôn ngữ tự nhiên tùy chọn. Bản ghi chat một kênh trộn sự thật và hùng biện không phù hợp quyết định thuốc rủi ro cao.

Thứ hai, bộ lọc mục ba tầng và intake lai cho thấy đánh đổi chi phí model và an toàn là bài toán kiến trúc, không chỉ chọn model. Hàm cổng, ngưỡng embedding, vùng bắt từ khóa và chính sách hợp nhất ưu tiên giá trị đo đã giảm mạnh tiếp xúc model lúc nạp trong khi giữ intake gần 1,2 giây trung bình lúc truy vấn.

Thứ ba, catalog quản trị với vòng đời nháp, đã duyệt và ngưng dùng giải quyết tri thức lỗi thời, một chế độ hỏng mạn tính của hệ chỉ quy tắc. Trích xuất tự động tạo quy tắc dùng ngay cộng ứng viên tinh chỉnh tạo đường cập nhật bền vững khi nhãn và guideline sửa đổi.

Thứ tư, đơn giản hóa tất định song ngữ tách sự thật lâm sàng khỏi locale trình bày. Chuyển ngôn ngữ dưới 2 giây không mất dữ liệu cho thấy bản địa hóa có thể là vấn đề tầng trình bày khi trạng thái có cấu trúc không đổi theo locale, dù bản địa hóa lexicon intake vẫn là công việc riêng.

Người thực hành đánh giá hệ tương tự nên yêu cầu đối tượng khuyến nghị có cấu trúc kiểm tra được độc lập với văn xuôi chat, quy tắc chặn cứng không bị lớp model ghi đè, trích dẫn truy xuất được xác thực với bằng chứng đã lấy, và phân rã latency cô lập nút thắt sinh.

Triển khai có trách nhiệm cũng mang nghĩa vụ đạo đức. Hệ phơi bày trạng thái có cấu trúc, phán quyết kiểm chứng và bằng chứng truy xuất thay vì điểm hộp đen. Khuyến nghị mang tính tư vấn và không tự kê đơn. Chặn cứng fail-closed ưu tiên phòng hại. Công việc tương lai nên kiểm toán liệu khác biệt độ phủ có tương quan mẫu nhân khẩu trong ca. Suy luận GPU cục bộ có chi phí môi trường, dù cổng giảm tính toán nạp so với duyệt toàn corpus ngây thơ. Hệ không nên được tiếp thị như thay thế bác sĩ tự trị; vai trò dự kiến là hỗ trợ có giám sát.

## 6.6 Sẵn sàng triển khai và đánh giá kết thúc

Sẵn sàng triển khai là một phần: phù hợp thí điểm có giám sát tại phòng khám liên kết nghiên cứu, không phù hợp dùng lâm sàng không giám sát hay cấp phép quy định mà không có bằng chứng thêm. Điểm mạnh gồm tái lập Docker Compose, an toàn fail-closed trên kịch bản rủi ro cao biên soạn, hài lòng bác sĩ tim mạch 4,22 trên 5, và suy luận tại chỗ tránh đưa thông tin sức khỏe được bảo vệ ra cloud. Khoảng trống gồm quy tắc liều chưa đầy đủ, tích hợp thuốc một phần, thiếu kết nối FHIR, cỡ mẫu độ chính xác vừa phải, không có dữ liệu kết cức tiến cứu, và chỉ truy cập web.

Lộ trình thực dụng chia giai đoạn rủi ro. Giai đoạn 1 là thí điểm nội bộ với nhập chat thủ công và bắt buộc bác sĩ duyệt thẻ có cấu trúc trước khi hành động theo tường thuật. Giai đoạn 2 thêm nguồn xét nghiệm FHIR và lexicon từ đồng nghĩa tiếng Việt. Giai đoạn 3 mở rộng thí điểm đa cơ sở với ghi log ghi đè và tinh chỉnh cảnh báo. Giai đoạn 4 tiến hành nghiên cứu kết cức về tối ưu GDMT và tái nhập viện. Mỗi giai đoạn nên giữ bất biến catalog PostgreSQL và tầng chặn cứng vẫn có thẩm quyền.

Luận điểm luận văn cho rằng hỗ trợ quyết định lai kết hợp quy tắc GDMT và an toàn tất định với GraphRAG và giải thích model có thể cung cấp hỗ trợ suy tim chính xác, kịp thời, song ngữ với bác sĩ trong vòng quyết định. Về độ chính xác 94,0%, kịp thời trung vị 7,4 giây, chuyển song ngữ dưới 2 giây, và thiết kế bác sĩ trong vòng với thẻ có cấu trúc thẩm quyền hơn văn xuôi, luận điểm được ủng hộ. Về kịp thời đuôi ở phân vị 95 là 12,6 giây, độ đầy đủ intake tiếng Việt, độ trưởng thành catalog liều, và lợi ích đã chứng minh kết cục, luận điểm chỉ được ủng hộ một phần với các lưu ý đã ghi.

Kết luận trung thực là hỗ trợ quyết định suy tim lai đã chuyển từ khái niệm sang nguyên mẫu kỹ thuật với tín hiệu đánh giá khích lệ. Nó chưa thay tư vấn chuyên khoa hay chứng minh lợi ích tử vong.

Vài phát hiện tương lai sẽ sửa đổi đáng kể kết luận đó. Thử nghiệm kết cục tiến cứu cho thấy không lợi ích GDMT sẽ đặt câu hỏi giá trị quy trình dù điểm hài lòng cao. Baseline chỉ model khớp độ chính xác có cấu trúc với latency thấp hơn sẽ thách thức chi phí phức tạp của catalog và kiểm chứng, dù hiệu suất kịch bản an toàn cũng phải khớp. Intake tiếng Việt thất bại dai dẳng sau tích hợp từ đồng nghĩa sẽ chỉ ra rào cản ngôn ngữ tự nhiên sâu hơn. Latency đuôi vẫn trên 12 giây trên phần cứng bệnh viện sẽ đe dọa áp dụng vòng khám dù trung vị chấp nhận được.

## 6.7 Lời kết

Suy tim vẫn là một trong những gánh nặng y tế lớn nhất toàn cầu và tại Việt Nam. Điều trị đòi hỏi hiểu biết nhiều nhóm thuốc, tương tác, và theo dõi sát chức năng thận, điện giải, huyết áp và nhịp tim. Hệ đề xuất trong luận văn là bước cụ thể hướng tới giúp bác sĩ ra quyết định điều trị chính xác và kịp thời mà không thay phán đoán lâm sàng.

Với khoảng 94% độ chính xác khuyến nghị, 8,1 giây thời gian phản hồi trung bình, 92,5% độ nhạy an toàn, F1 tương tác 97,1%, gánh nặng cảnh báo giảm từ 8,2 xuống 4,3 mỗi bệnh nhân, và mức hài lòng người dùng 4,22 trên 5 trong 25 bác sĩ tim mạch, hệ cho thấy tiềm năng rõ cải thiện chất lượng chăm sóc khi triển khai như trợ lý có giám sát bác sĩ, neo trên catalog được quản trị và bằng chứng truy xuất. Triển khai rộng hơn vẫn cần mở rộng cơ sở tri thức với từ đồng nghĩa thuốc tiếng Việt, tích hợp FHIR cho intake có cấu trúc, và đánh giá lâm sàng tiến cứu đo kết cục thay vì chỉ độ chính xác vignette.

Các con số đánh giá kể câu chuyện nhất quán khi đọc cùng nhau. Độ chính xác vượt ngưỡng 90% trong khi vẫn còn chỗ cải thiện nơi độ đầy đủ intake quan trọng nhất. Latency trung vị đạt mức chấp nhận được vòng khám dù ca chậm hơn ở đuôi vẫn còn. Độ nhạy an toàn kết hợp tỷ lệ đạt hoàn hảo trên kịch bản chống chỉ định biên soạn cho thấy thiết kế fail-closed hoạt động với quy tắc cứng đã mã hóa. Điểm hài lòng xác nhận hướng sản phẩm: bác sĩ muốn hỗ trợ khoảng trống GDMT và tương tác dù thỉnh thoảng không đồng ý gợi ý cấp nhóm.

Chỉ số xây tri thức củng cố khả thi vận hành. Tỷ lệ trích xuất cao, giữ 95,0% mục, và dùng model vùng biên thấp nghĩa cơ sở tri thức có thể tiến hóa theo cập nhật nhãn mà không tốn ngân sách tính toán cấm. Phân loại quy tắc đặt kỳ vọng thực tế rằng tự động hóa tạo bản nháp cần quản trị lâm sàng, không phải catalog oracle. Tối ưu cảnh báo cho thấy trải nghiệm người dùng an toàn có thể tinh chỉnh mà không hy sinh chặn cứng, giải quyết lý do lịch sử khiến áp dụng hỗ trợ quyết định thất bại trong thực hành.

Vượt một sản phẩm đơn lẻ, luận văn cung cấp mẫu chuyển giao được: logic an toàn và GDMT tất định, giải thích tăng cường truy xuất lai, cổng model tiết kiệm chi phí, đơn giản hóa tất định song ngữ, và kỹ thuật tri thức hướng quản trị. Mẫu đó có thể hướng dẫn hỗ trợ quyết định lâm sàng cho bệnh khác và bối cảnh thiếu nguồn lực nơi hướng dẫn chính xác, giải thích được và kịp thời cũng thiết yếu.

Bài học trung tâm là cấu trúc. Trong miền dược lý rủi ro cao, LLM xuất sắc làm giao diện và người giải thích, không phải tác giả im lặng của phân loại an toàn. Gắn bất biến đó vào kiến trúc qua catalog được quản trị, tầng chặn cứng, agent kiểm chứng, và thứ tự stream hiển thị phán quyết trước văn xuôi biến năng lực model từ rủi ro thành sức mạnh có giám sát.

Suy tim, với bốn trụ GDMT, bề mặt tương tác dày và cảnh báo thận trọng phụ thuộc theo dõi, là bài thử mạnh cho mẫu đó. Khoảng trống triển khai GDMT thực tế báo hiệu hỗ trợ quyết định không cần chờ trí tuệ nhân tạo tự trị hoàn hảo. Ngay các gợi ý có giám sát, theo guideline với kiểm tra tương tác chính xác có thể dịch chuyển thực hành nếu nhúng vào quy trình ở latency trung vị khoảng bảy đến tám giây với khả năng tiếp cận tiếng Việt và tiếng Anh. Đánh giá báo cáo ở đây gợi ý mẫu lai hoạt động trong điều kiện có kiểm soát. Hạn chế, ranh giới hợp lệ và công việc tương lai theo giai đoạn vạch lộ trình trung thực từ nguyên mẫu nghiên cứu đến tiện ích lâm sàng bền vững, nơi bác sĩ vẫn là tác giả quyết định cuối nhưng không còn một mình gánh tải nhận thức ghi nhớ mọi chống chỉ định, bước chuẩn liều và ngưỡng xét nghiệm mà dược lý suy tim đòi hỏi.

Để tra cứu nhanh, các kết quả đánh giá chính là: độ chính xác khuyến nghị 94,0% với khoảng tin cậy 95% 89,2% đến 98,8%; thời gian phản hồi end-to-end trung bình 8,1 giây với trung vị 7,4 giây và phân vị 95 12,6 giây; intake bệnh nhân trung bình 1,2 giây; độ nhạy an toàn 92,5%; F1 phát hiện tương tác 97,1%; mức hài lòng người dùng 4,22 trên 5 với hữu ích lâm sàng 4,5 trên 5; giữ mục bộ lọc 95,0% với 6,6% duyệt model vùng biên; thành công trích xuất nhãn 94,2% ở khoảng 45 giây mỗi thuốc; 127 thuốc trong manifest với 60 tích hợp đầy đủ và 4.136 mục trích xuất; 6.032 quy tắc ràng buộc và 1.096 quy tắc tương tác với 53,9% dùng ngay; gánh nặng cảnh báo 4,3 mỗi bệnh nhân sau tối ưu từ 8,2; tỷ lệ đạt kịch bản an toàn 100% trên bốn ca biên soạn; và chuyển ngôn ngữ dưới 2 giây với không mất dữ liệu.

Nhà nghiên cứu mở rộng công trình này nên coi các con số là mốc cơ sở đã ghi. Mọi kỹ thuật mới nên chứng minh cải thiện trên độ chính xác có cấu trúc, tỷ lệ đạt kịch bản an toàn, hoặc latency trung vị mà không làm suy giảm im lặng thực thi chặn cứng hoặc tính tất định thẻ song ngữ.

Hệ hỗ trợ quyết định suy tim mô tả ở đây được đưa ra không phải sản phẩm y tế hoàn chỉnh mà như câu trả lời đã chứng minh cho câu hỏi nghiên cứu: kỹ thuật tri thức lai, logic an toàn tất định và giải thích qua model có thể cùng tồn tại trong một hệ triển khai được với hiệu suất đo được. Các con số là dấu chấm câu thực nghiệm trên câu trả lời đó. Kiến trúc, mã, catalog và quy trình quản trị là phần bền vững. Bác sĩ vẫn là thẩm quyền cuối. Hệ tồn tại để hỗ trợ quyết định của họ bằng bằng chứng được quản trị, cảnh báo kịp thời và trình bày song ngữ rõ ràng, không hơn và không kém.

Luận văn vì vậy kết luận rằng vấn đề ban đầu, chat chỉ model không an toàn đối lập hệ chỉ quy tắc cứng nhắc trong suy tim, chấp nhận một giải pháp lai với hiệu suất được ghi chép thực nghiệm, đồng thời liệt kê rõ các tích hợp, lexicon và thử nghiệm cần trước khi tuyên bố tác động lâm sàng có thể mở rộng trách nhiệm vượt hỗ trợ quyết định có giám sát.
