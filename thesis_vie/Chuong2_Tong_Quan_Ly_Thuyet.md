# CHƯƠNG 2: TỔNG QUAN LÝ THUYẾT VÀ CƠ SỞ TRI THỨC

*(Bản dịch chi tiết từ `thesis/Chapter2_Literature_Review.md`)*

Chương này giới thiệu khái niệm, nền lâm sàng và công nghệ nền tảng của hệ hỗ trợ quyết định suy tim (HF-CDSS). Mục tiêu giúp người không chuyên y hay AI hiểu vì sao hệ thống được thiết kế như vậy. Mỗi kỹ thuật được giải thích: là gì, dùng để làm gì, giúp gì trong thực tế. Số trích dẫn theo `References.md`.

## 2.0 Bối cảnh và động lực nghiên cứu

Suy tim (Heart Failure, HF) là một trong những bệnh tim mạch mạn tính nghiêm trọng nhất. Ước tính toàn cầu có hơn 64 triệu người sống với suy tim, và số này còn tăng khi dân số già hóa cũng như khi điều trị cấp cứu tốt hơn giúp bệnh nhân sống sót sau nhồi máu cơ tim nhưng sau đó xuất hiện rối loạn chức năng thất kéo dài [1]. Suy tim không phải một bệnh đơn lẻ mà là hội chứng lâm sàng: tim không đổ đầy hoặc bơm máu đủ để đáp ứng nhu cầu cơ thể. Bệnh nhân khó thở, mệt, giữ nước, nhập viện nhiều lần. Với hệ thống y tế, suy tim là nguyên nhân nhập viện hàng đầu ở người trên 65 tuổi; tái nhập viện trong 30 ngày vừa phổ biến vừa tốn kém.

Bác sĩ phân loại suy tim theo phân suất tống máu thất trái (LVEF). HFrEF (LVEF ≤ 40%) là trọng tâm luận văn vì điều trị nội khoa theo hướng dẫn (GDMT) có bằng chứng mạnh nhất về giảm tử vong và nhập viện ở nhóm này [2], [3]. Quản lý ngoại trú cần điều chỉnh cẩn thận thuốc ức chế thần kinh–thể dịch, lợi tiểu và SGLT2i. Mỗi nhóm thuốc có tiêu chí khởi trị, chống chỉ định, tương tác và yêu cầu theo dõi riêng. Khi điều trị thiếu hoặc sai trình tự, bệnh nhân chịu hại có thể tránh được. Cải thiện nhỏ trong việc dùng GDMT có thể đổi kết cục dân số khi nhân lên hàng triệu bệnh nhân [2], [3], [6]. Hệ hỗ trợ quyết định lâm sàng (CDSS) thường được nêu như cách thu hẹp khoảng cách giữa bằng chứng đã công bố và hành động tại giường bệnh [4], [5].

Ở Việt Nam, gánh nặng suy tim theo xu hướng toàn cầu nhưng thêm ràng buộc địa phương. Chuyên khoa tim mạch tập trung ở thành phố lớn; tuyến tỉnh dựa nhiều vào nội khoa tổng quát phải xử lý GDMT phức tạp với ít hỗ trợ chuyên sâu [1]. Hồ sơ tiếng Việt, tên biệt dược địa phương và charting lẫn Việt–Anh khiến hỗ trợ quyết định có cấu trúc khó tiếp cận hơn. CDSS suy tim cho bối cảnh này phải coi tiếp nhận song ngữ và chuẩn hóa thuốc có quản trị là yêu cầu cốt lõi.

Hai xu hướng công nghệ làm nghiên cứu này kịp thời. Đồ thị tri thức y sinh, thuật ngữ chuẩn và kho nhãn thuốc mở đã chín muồi đến mức có thể nạp tự động vào catalog có quản trị mà không chép tay toàn bộ công thức [7]–[11]. Mô hình ngôn ngữ lớn (LLM) làm giao diện ngôn ngữ tự nhiên thực tế, nhưng xu hướng tạo văn bản nghe hợp lý nhưng sai khiến chúng không an toàn nếu dùng một mình để kê đơn [12], [19]. Mô hình mã mở chạy cục bộ giảm phụ thuộc API đám mây khi thí điểm bệnh viện cần giữ vignette bệnh nhân tại chỗ.

Luận văn xuất phát từ nhận định: CDSS suy tim phải vượt cả engine chỉ có rule cứng và chat LLM không ràng buộc. Kiến trúc lai ghép tri thức được quản trị, engine GDMT/an toàn tất định, GraphRAG và LLM giải thích cục bộ là phản ứng có nguyên tắc. Công trình xây hệ hỗ trợ GDMT cho HFrEF, giao diện Việt–Anh, xây tri thức tự động từ nhãn SPL FDA và guideline suy tim chính, đánh giá trên vignette do bác sĩ tim mạch duyệt. Chương 1 nêu vấn đề và câu hỏi nghiên cứu; các mục dưới cung cấp nền lý thuyết cho thiết kế ở Chương 3 và 4.

## 2.1 Hệ hỗ trợ quyết định lâm sàng (CDSS)

CDSS là phần mềm giúp bác sĩ, dược sĩ hoặc bệnh nhân quyết định sức khỏe tốt hơn. Viện Y học Hoa Kỳ định nghĩa CDSS là mọi hệ điện tử hỗ trợ trực tiếp quyết định lâm sàng [16]. Nói đơn giản: CDSS không thay bác sĩ; nó sắp xếp sự kiện liên quan, kiểm vấn đề an toàn và gợi ý lựa chọn để quyết định nhanh hơn, ít sót hơn. Với bệnh mạn như suy tim, giá trị thường nằm ở các lần tái khám: phát hiện thuốc thiếu, gắn cờ phối hợp nguy hiểm, nhắc theo dõi xét nghiệm sau đổi liều.

CDSS khác nhau về cách và thời điểm can thiệp. Hệ thụ động chờ người hỏi (tra tương tác thuốc). Hệ chủ động đẩy cảnh báo vào workflow (cảnh trước khi ký đơn). Cơ chế cũng khác: rule if–then tường minh có thể truy vết; học máy bắt pattern từ dữ liệu lớn nhưng khó giải thích; hệ tri thức/truy xuất neo câu trả lời vào tài liệu và sự kiện có cấu trúc. Hỗ trợ suy tim hiện đại ngày càng kết hợp: rule tất định cho an toàn, tri thức cấu trúc cho quan hệ thuốc–lab, mô hình ngôn ngữ để đọc văn bản tự do và viết giải thích rõ.

Lịch sử CDSS lặp lại chủ đề minh bạch và khớp workflow. MYCIN (1976) là hệ rule sớm về trị liệu nhiễm khuẩn tại Stanford: mã hóa heuristic thành production rule, hỏi có cấu trúc, giải thích lý do [15]. MYCIN không vào thực hành thường quy nhưng chứng minh logic y có thể hình thức hóa và bác sĩ cần thấy vì sao có khuyến nghị. Hệ sau như DXplain, QMR mở rộng hỗ trợ chẩn đoán. Từ thập niên 1990, kiểm dị ứng thuốc và máy tính liều phổ biến trong EHR thương mại, dù nhiều cảnh báo bị bỏ qua vì quá nhiều hoặc quá mơ hồ.

Dự án gần hơn dùng đồ thị tri thức và mô hình dự báo quy mô lớn. Watson for Oncology minh họa vừa tiềm năng vừa giới hạn khi curation và chuẩn thực hành địa phương yếu. Thế hệ hiện tại thêm RAG và truy xuất tăng cường đồ thị để hỏi bằng ngôn ngữ tự nhiên và cố trích dẫn nguồn có thẩm quyền. Qua mọi thế hệ: chỉ accuracy không đủ. Khuyến nghị đúng nhưng muộn, sai định dạng, hoặc chìm trong cảnh báo giả sẽ không đổi chăm sóc.

Khung “Five Rights” của Osheroff nắm góc nhìn workflow [17]: đúng thông tin, đúng người, đúng định dạng, đúng kênh, đúng thời điểm. Với GDMT suy tim, thông tin đúng gồm kiểu suy tim, nhóm thuốc hiện có, chức năng thận, kali, huyết áp, quy tắc thời gian khi chuyển nhóm liên quan. Người đúng thường là bác sĩ kê đơn hoặc dược sĩ lâm sàng. Định dạng đúng có thể là nhãn trạng thái đơn giản (tiếp tục, cân nhắc, tránh) kèm lý do ngắn và liên kết guideline/nhãn. Kênh đúng có thể là cảnh báo EHR, dashboard riêng hoặc giao diện hội thoại. Thời điểm đúng là lúc quyết định thuốc (tái khám, đối chiếu thuốc), không phải giờ sau trong hộp thư chưa đọc.

Chỉ số định lượng bổ sung Five Rights. Độ nhạy đo bắt đúng vấn đề thật. Độ đặc hiệu đo đúng bỏ qua tình huống an toàn. PPV hỏi trong mọi cảnh báo, bao nhiêu thật sự cần. PPV thấp → bác sĩ override → mệt mỏi cảnh báo. Với CDSS suy tim, bỏ sót chống chỉ định cứng (ví dụ khởi ARNI quá sớm sau ACEi) có thể hại bệnh nhân nên kiểm an toàn hướng độ nhạy cao; đồng thời cảnh báo mềm bắn trên mọi bệnh nhân ổn định làm mất tin. Thiết kế tốt phân tầng mức độ, ức chế trùng lặp, và ghép chỉ số số với đánh giá usability [4], [5].

Suy tim thêm yêu cầu miền mà bộ kiểm thuốc chung thường bỏ sót. Trị liệu theo trụ nhóm thuốc (ức chế RAAS, beta blocker, MRA, SGLT2i), không tối ưu từng thuốc đơn. Nhiều rule phụ thuộc lab/sinh hiệu hơn lệnh cấm tuyệt đối. Rule thời gian chi phối chuyển nhóm (washout ACEi–ARNI). Thiếu GDMT vừa là vấn đề quy trình vừa là tri thức: bác sĩ có thể biết guideline nhưng trì tăng liều vì hạ huyết áp, tăng kali hoặc thời gian khám hạn chế. Bối cảnh song ngữ và nguồn lực thấp thêm phức tạp biệt dược, ghi chú lẫn ngôn ngữ, thuật ngữ địa phương. Những thách thức này thúc đẩy kiến trúc lai ở các chương sau.

## 2.2 Đồ thị tri thức (Knowledge Graph)

Đồ thị tri thức (KG) lưu tri thức như mạng sự vật (thực thể) và liên kết (quan hệ) [7]. Thay vì chôn sự kiện trong tài liệu dài, đồ thị làm cấu trúc tường minh: thuốc nào điều trị bệnh nào, thuốc nào tương tác thuốc nào, lab nào kích hoạt thận trọng. Điều này quan trọng vì suy luận lâm sàng mang tính quan hệ. Câu hỏi spironolactone có an toàn khi dùng cùng lisinopril và thận giảm đòi hỏi nối tương tác thuốc–thuốc, ngưỡng thận và rủi ro điện giải — có thể nằm ở mục/tài liệu khác nhau. Đồ thị tốt gắn chúng vào nút thuốc/lab chuẩn để phần mềm duyệt nối lúc truy vấn.

Khối xây dựng cơ bản thường là bộ ba: chủ thể–vị ngữ–đối tượng, ví dụ (Bisoprolol, điều trị, Suy_tim), (ARNI, chống_chỉ_định_với, ACEi), (MRA, cần_theo_dõi, kali_máu). Nút là thực thể có kiểu; cạnh là quan hệ; thuộc tính gắn số và chữ (liều khởi 1,25 mg, cửa sổ washout 36 giờ…). Tiên đề diễn đạt logic điều kiện mà bộ ba thuần khó nắm gọn. Trong luận văn, Neo4j lưu cấu trúc thực thể–quan hệ trong khi PostgreSQL giữ rule thực thi kèm workflow duyệt, tách duyệt đồ thị khám phá khỏi logic sản xuất được quản trị.

Liên kết thực thể (chuẩn hóa) ánh xạ chữ bề mặt sang nút chuẩn. Hồ sơ có thể ghi “Entresto”, “sacubitril/valsartan” hoặc biệt dược địa phương. Không liên kết thì cùng thuốc thành nút rời và kiểm tương tác thất bại thầm lặng. Pipeline liên kết kết hợp từ điển, khớp mờ, embedding gần đồng nghĩa và giải mơ hồ. Khi nạp, mention thuốc từ SPL và guideline chuẩn hóa về khóa kiểu RxNorm trước import đồ thị; lúc chat, intake làm tương tự trên danh sách thuốc tự do.

Duyệt đường nhiều bước đi theo chuỗi quan hệ để trả lời câu không một cạnh nào giải quyết hết. Từ ACEi của bệnh nhân có thể đi chống_chỉ_định_với tới ARNI rồi chỉ_định_cho HFrEF, vừa giải thích vì sao cần washout vừa vì sao ARNI vẫn có giá trị sau chờ. Cypher (Neo4j) diễn đạt đường này khai báo. Đồ thị con trả về trở thành bằng chứng có cấu trúc cho LLM và agent kiểm chứng. Cấu trúc đường cũng hỗ trợ kiểm hồi quy khi xây: nếu không có đường ACEi–ARNI qua chống chỉ định, có thể đã sót ràng buộc nhãn quan trọng lúc nạp.

Tài nguyên y sinh cung cấp từ vựng và dược lý để đồ thị tích hợp [8]: UMLS [9], SNOMED CT [10], DrugBank/PubChem [11], RxNorm. Ontology bệnh mạnh về phân loại; nhãn FDA và guideline cung cấp liều số, boxed warning và ngôn ngữ điều kiện. HF-CDSS chủ yếu lấy DailyMed SPL cho chi tiết thuốc và guideline ESC/AHA/ACC/HFSA cho khuyến cáo GDMT cấp nhóm [2], [3]. Đồ thị không sao chép toàn bộ thuật ngữ; phạm vi là dược trị liệu suy tim.

Trong CDSS, KG hỗ trợ suy luận thuốc–bệnh–lab, truy xuất nhiều bước trên lộ trình lâm sàng và bằng chứng ngữ cảnh mà tìm từ khóa/embedding thuần có thể bỏ sót khi sự kiện phân tán. Với suy tim, đồ thị mã hóa không chỉ nhóm nào điều trị HFrEF mà cả ràng buộc xuyên nhóm. Truy xuất đồ thị chạy song song dense/sparse, hạng được gộp trước khi sinh — phát triển mẫu GraphRAG ở mục 2.5.

## 2.3 Retrieval-Augmented Generation (RAG)

RAG kết hợp tìm kiếm với sinh ngôn ngữ để câu trả lời neo vào bằng chứng ngoài thay vì chỉ nhớ trong model [12]. LLM học pattern rộng từ văn bản huấn luyện nhưng không bảo đảm wording nhãn hiện tại, quy tắc công thức địa phương hay an toàn theo bệnh nhân. Trong y, khoảng trống đó nguy hiểm: liều trôi chảy nhưng lỗi thời hoặc thiếu chống chỉ định có thể đánh lừa bác sĩ bận. RAG đặt LLM như người đọc/tóm tắt trên kho tri thức có thể cập nhật độc lập trọng số model. Khi guideline mở rộng SGLT2i trong HFrEF, cập nhật chunk và cạnh đồ thị làm mới hành vi hệ mà không huấn luyện lại generator.

RAG thường gồm: lập chỉ mục tài liệu thành chunk, embedding thành vector, truy xuất chunk liên quan nhất theo câu hỏi, rồi prompt LLM trả lời chỉ dùng ngữ cảnh đó. Hai họ truy xuất thường kết hợp.

Dense retrieval dùng mô hình embedding (bi-encoder) đưa truy vấn và tài liệu vào không gian số chung; nghĩa gần → vector gần dù wording khác (“EF giảm” và “phân suất tống máu thấp”). Lúc lập chỉ mục, vector tài liệu tính sẵn; lúc truy vấn, tìm lân cận gần nhất. BGE-M3, MedCPT dùng trong môi trường lâm sàng. Dense mạnh đồng nghĩa/diễn đạt lại nhưng có thể bỏ token hiếm: biệt dược, ngưỡng số, cụm “36 hours”.

Sparse retrieval dùng thống kê từ vựng. BM25 là bộ xếp hạng sparse chuẩn: điểm theo chồng từ truy vấn–tài liệu, có điều chỉnh để tài liệu dài/lặp từ không thắng oan. BM25 mạnh mention thực thể đúng chữ và ngôn ngữ quy định nhưng yếu nối văn bản liên quan khái niệm mà từ vựng khác. Câu hỏi lâm sàng thường trộn cả hai nhu cầu; pipeline lai chạy dense và sparse song song rồi gộp danh sách xếp hạng.

Chunking chia guideline/nhãn dài thành mảnh kích thước truy xuất. Cắt độ dài cố định ngây thơ làm gãy câu lâm sàng giữa chừng. Chunk theo câu có chồng lấn giữ ngữ cảnh cục bộ. Tiêu đề mục SPL XML hoặc outline guideline cung cấp biên tự nhiên và provenance. Vector store như ChromaDB lưu embedding kèm metadata; cấu trúc kiểu HNSW cho tìm gần đúng nhanh trên corpus lớn.

RAG y tế đòi hỏi độ chính xác nghiêm, thuật ngữ chuyên, ngữ cảnh đa yếu tố và cập nhật tri thức liên tục. RAG không xóa lỗi; nó đổi dạng thất bại: sót truy xuất, xếp hạng sai, model bỏ qua đoạn đã lấy. CDSS lâm sàng vì thế ghép RAG với rule tất định và người duyệt. Trong HF-CDSS, agent kiểm chứng kiểm ID chunk được trích dẫn thật sự đã truy xuất và ràng buộc hard-block đã được engine rule đánh giá, không chỉ suy từ LLM.

## 2.4 Mô hình ngôn ngữ lớn (LLM)

LLM là mạng nơ-ron huấn luyện trên corpus văn bản khổng lồ để dự đoán và sinh ngôn ngữ. Chúng có thể viết văn lâm sàng, trích trường có cấu trúc từ tường thuật và trả lời câu hỏi y bằng ngôn ngữ tự nhiên. Cột mốc gồm kiến trúc Transformer (2017) [18] và GPT-3 (2020) [19]. Trong CDSS, LLM phù hợp giải thích, trích ngữ nghĩa, mở rộng truy vấn và kiểm chứng — không phải kê đơn tự trị không biên. HF-CDSS dùng Qwen2.5 qua Ollama cục bộ cho câu trả lời bác sĩ và tác vụ nhẹ như HyDE, duyệt mục biên.

Transformer dựa trên attention: mỗi token cân nhắc token khác khi tạo biểu diễn. Multi-head attention chạy nhiều mẫu chú ý song song, nối ngữ cảnh xa (ví dụ “eGFR 22” với “suy thận” trong ghi chú dài). Model lưu sự kiện y rộng trong trọng số — vừa năng lực vừa rủi ro: có thể nêu trôi chảy liều sai hoặc bịa tương tác.

Kỹ thuật prompt điều khiển hành vi không đổi trọng số: chain-of-thought yêu cầu bước trung gian; few-shot đưa ví dụ input–output. HITL giữ bác sĩ là thẩm quyền cuối: hệ đề xuất nháp và đưa bằng chứng chứ không tự đặt lệnh. HF-CDSS áp HITL ở duyệt rule, khuyến nghị chat và bỏ qua cảnh báo không chặn (tùy chọn).

Model miền như BioBERT/ClinicalBERT cải thiện NER và QA y sinh so với model tổng quát. Với truy xuất, bi-encoder lâm sàng căn không gian embedding với cặp câu hỏi–đoạn y. LLM y vẫn chịu cutoff tri thức, thiếu corpus không Anh, phủ thực hành kê đơn địa phương không đều. HF-CDSS giảm bằng RAG trên nhãn/guideline nạp cục bộ và engine GDMT tất định không phụ thuộc nhớ tham số cho an toàn cốt lõi.

Ảo giác (hallucination) — văn bản trôi chảy nhưng không có hỗ trợ — là rủi ro LLM chính. Nội tại: mâu thuẫn ngữ cảnh đã cho. Ngoại tại: đưa sự kiện không có trong bằng chứng truy xuất. Giảm thiểu trong HF-CDSS: bắt buộc trích dẫn chunk ID đã truy xuất, schema output Pydantic, hậu kiểm tất định qua rule và agent, phân tầng an toàn (hard_block vs thận trọng), người duyệt trước hành động. Suy luận cục bộ Ollama hỗ trợ môi trường air-gap/nhạy cảm quyền riêng tư.

## 2.5 GraphRAG

GraphRAG tăng cường truy xuất và sinh bằng cấu trúc đồ thị để trả lời câu cần ngữ cảnh quan hệ, không chỉ văn bản giống [13]. RAG vector lấy đoạn nghĩa gần truy vấn — tốt với “lịch chuẩn liều bisoprolol trong HFrEF theo nhãn?” nhưng kém khi cần nối hai thực thể qua quan hệ có kiểu, ví dụ “vì sao phải chờ trước khi đổi ramipril sang Entresto?” (cạnh chống chỉ định ACEi–ARNI kèm thuộc tính washout). GraphRAG không thay RAG vector; nó bổ sung sự kiện và đồ thị con rồi hợp với bằng chứng chữ trước khi sinh.

So với RAG chỉ vector: GraphRAG hiểu quan hệ và truy xuất nhiều bước mạnh hơn nhưng chi phí kỹ thuật cao hơn. HF-CDSS triển khai tập con thực dụng: duyệt Neo4j quanh thực thể + truy xuất chunk lai, chưa làm tóm tắt cộng đồng offline đầy đủ lúc triển khai đầu.

Hai chế độ tìm trong tài liệu GraphRAG: local search bắt đầu từ thực thể trong hồ sơ/truy vấn rồi mở rộng lân cận (phù hợp kiểm an toàn theo bệnh nhân); global search dùng tóm tắt cụm đồ thị cho câu hỏi chủ đề (“bó dược trị HFrEF chuẩn?”). HF-CDSS nhấn local search và engine GDMT tất định vì phân tích khoảng trống và an toàn mang tính cá thể.

Truy xuất lai gộp danh sách bằng RRF (thường k = 60), tránh hiệu chỉnh điểm cosine dense với điểm BM25 không tương thích. HyDE xử lý lệch từ vựng giữa câu hỏi ngắn và văn nhãn trang trọng [14]: LLM nhỏ sinh tài liệu trả lời giả định, embedding tài liệu đó để dense retrieval. HyDE có thể sai nếu bịa sự kiện — vì thế HF-CDSS kết hợp BM25, sự kiện đồ thị, rule tất định và kiểm chứng, không tin HyDE một mình. Rerank tùy chọn dùng scorer đắt hơn trên top ứng viên; phân rã truy vấn tách câu ghép thành truy vấn con trước khi gộp.

GraphRAG khớp CDSS suy tim vì tri thức thuốc–bệnh–lab vốn quan hệ; suy luận lâm sàng thường nhiều bước; ngữ cảnh bệnh nhân nhiều biến tương tác. HF-CDSS chạy GraphRAG chủ yếu như lớp bằng chứng/giải thích song song engine GDMT tất định: trạng thái khuyến nghị có cấu trúc từ PostgreSQL; GraphRAG cung cấp đoạn và sự kiện đồ thị để LLM phải trích dẫn khi giải thích.

## 2.6 Xây dựng tri thức y

Xây KG y cho CDSS cần kết hợp nguồn cấu trúc và không cấu trúc, trích thực thể/quan hệ, liên kết định danh chuẩn, quản trị chất lượng trước sản xuất. Đồ thị y đa kiểu thực thể, từ vựng quan hệ phong phú, thuộc tính số, ràng buộc thời gian, độ tin cậy bằng chứng phân cấp. Đồ thị suy tim phải hòa giải tường thuật guideline về bốn trụ GDMT với chi tiết số nhãn FDA từng thuốc. Khi độ mạnh guideline và wording nhãn lệch, workflow quản trị đánh dấu rule nháp đến khi clinical lead giải quyết [8].

Nguồn: cấu trúc (DrugBank, UMLS/SNOMED, SPL XML, RxNorm) và không cấu trúc (guideline ESC/AHA/HFSA, thử nghiệm, tài liệu). HF-CDSS nạp nhãn DailyMed và guideline hội vào artifact có phiên bản trước quản trị PostgreSQL và import Neo4j. Pipeline điển hình: parse/tách mục → chuẩn hóa thuật ngữ → NER → trích quan hệ → liên kết thực thể → hợp nhất tri thức → đảm bảo chất lượng với chuyên gia trước khi rule đạt approved.

NER nhắm tên thuốc/nhóm, bệnh (HFrEF, CKD), lab và giá trị, điều kiện quần thể. Trích quan hệ ánh xạ câu tự nhiên sang cạnh có kiểu. LLM hỗ trợ với ràng buộc JSON schema bổ sung extractor mẫu trên câu guideline mơ hồ. QA gồm phát hiện mâu thuẫn, báo cáo thực thể mồ côi, kiểm điểm bởi clinical lead.

Sync hạ nguồn tách theo mục đích: rule → PostgreSQL; bundle thực thể–quan hệ → Neo4j; chunk → ChromaDB kèm metadata nguồn. Bộ lọc mục lúc nạp dùng cascade 3 tầng: từ khóa tiêu đề chuẩn (không GPU) → tương đồng embedding với prototype mục lâm sàng → LLM biên cho phân loại liên quan lâm sàng nhị phân; dưới ngưỡng thấp thì bỏ (boilerplate hành chính). Cascade giảm gọi LLM mà giữ recall: chỉ dùng model đắt nơi phương pháp rẻ từ chối quyết định.

## 2.7 Nền tảng lâm sàng suy tim

Bạn đọc CNTT cần đủ ngữ cảnh lâm sàng để hiểu vì sao rule và phạm vi truy xuất được định hình vậy. Suy tim là hội chứng bất thường cấu trúc/chức năng tim kèm triệu chứng/dấu hiệu. Phân loại theo LVEF: HFrEF (thường ≤ 40%), HFmrEF, HFpEF (thường ≥ 50%). Trụ GDMT hiện đại có bằng chứng kết cục mạnh nhất ở HFrEF [2], [3]. HF-CDSS tập trung tối ưu GDMT HFrEF nơi rule cấp nhóm và nhãn chuẩn hóa nhất. Kiểu hình cổng khuyến nghị: intake trích LVEF khi có và suy ra đủ điều kiện HFrEF trước khi gợi ý ARNI hoặc một số khởi nhóm.

Bốn trụ GDMT HFrEF: (1) ức chế RAAS qua ACEi/ARB/ARNI; (2) beta blocker có bằng chứng (bisoprolol, carvedilol, metoprolol succinate); (3) MRA (spironolactone, eplerenone); (4) SGLT2i (dapagliflozin, empagliflozin) [2], [3], [6]. Mỗi nhóm giảm bệnh suất/tử suất qua cơ chế huyết động và thần kinh–thể dịch chồng một phần. ARNI kết hợp valsartan với sacubitril (ức chế neprilysin), bằng chứng kết cục vượt ACEi đơn trong thử nghiệm then chốt nhưng rule washout nghiêm khi chuyển từ ACEi. Beta blocker đối kháng kích hoạt giao cảm mạn ở HFrEF ổn định; tăng liều dần; tránh khi mất bù cấp chưa ổn. MRA giảm tái cấu trúc và nhập viện nhưng tăng nguy cơ tăng kali, đặc biệt khi phong tỏa RAAS đồng thời. SGLT2i giảm nhập viện HF và tử vong tim mạch ở HFrEF kể cả không ĐTĐ. CDSS phải suy luận cấp nhóm (“thiếu MRA”) đồng thời phân giải liều theo sản phẩm từ catalog SPL.

Lab và sinh hiệu then chốt: eGFR cổng dùng MRA và chỉnh liều nhiều thuốc; kali máu thiết yếu khi kết hợp ức chế RAAS với MRA; huyết áp giới hạn tăng liều RAAS/beta blocker; nhịp tim ảnh hưởng dung nạp beta blocker. HF-CDSS trích các trường này bằng intake lai, suy eGFR từ creatinine khi cần bằng công thức tất định, và đưa vào engine ràng buộc/liều thay vì chỉ dựa LLM.

Ràng buộc đặc trưng HFrEF: khoảng washout bắt buộc giữa ACEi và khởi ARNI, thường 36 giờ, vì kết hợp ức chế ACE với ức chế neprilysin tăng nguy cơ phù mạch [2], [3]. Đây là rule thời gian, không phải chống chỉ định vĩnh viễn. CDSS phải nắm thời điểm liều ACEi cuối khi có và phát trạng thái hard-block hoặc thận trọng tương ứng. Cạnh đồ thị mã hóa quan hệ nhóm thuốc; rule PostgreSQL mã hóa logic washout thực thi. Truy xuất vector đơn thường lấy lợi ích ARNI và cảnh báo ACEi ở chunk khác nhau; lớp đồ thị và rule tồn tại để cưỡng chế ràng buộc tổ hợp đó.

Lợi ích GDMT tích lũy khi tăng tới liều đích dung nạp được, không chỉ khởi ở liều bắt đầu [6]. Nhãn nêu liều khởi, khoảng nhân đôi, liều tối đa; guideline nhấn đánh giá lại huyết áp, nhịp, kali, thận sau mỗi lần đổi. Catalog liều HF-CDSS mã hóa lịch này thành đối tượng có cấu trúc cho engine liều, tách khỏi truy xuất tường thuật. Khoảng theo dõi (kali trong một tuần sau khởi MRA) xuất hiện như quan hệ theo dõi trên đồ thị và lời nhắc thận trọng khi lab cũ/thiếu. Hỗ trợ chuẩn liều cần hồ sơ có trạng thái (bước liều hiện tại, ngày đổi gần nhất) hơn QA không trạng thái — vì thế phát hiện khoảng trống GDMT, kiểm ràng buộc và tính liều là dịch vụ tất định trong khi GraphRAG cung cấp bằng chứng giải thích.

## 2.8 Công nghệ triển khai dùng trong luận văn

PostgreSQL: CSDL quan hệ lưu rule được quản trị, tài khoản, audit, trạng thái duyệt; cột JSONB giữ lịch liều và chỉnh thận truy vấn runtime mà không migration schema mỗi biến thể thuốc mới.  
Neo4j: CSDL đồ thị truy vấn Cypher cho mở rộng lân cận và lấy sự kiện có kiểu.  
ChromaDB: kho vector lưu embedding chunk kèm metadata; hỗ trợ dense retrieval lai với job nạp Python.  
FastAPI: khung web Python async, validate Pydantic, OpenAPI; handler async cho truy xuất đồng thời; SSE stream sự kiện pipeline có kiểu.  
React: UI dashboard; chuỗi song ngữ, lịch sử hội thoại, lộ dần draft/an toàn/kiểm chứng/token trả lời; ClinicalPanel trình thẻ khuyến nghị tách khỏi văn xuôi LLM.  
Redis: cache snapshot rule đã duyệt, draft hội thoại, output LLM lặp.  
Docker Compose: điều phối backend, CSDL, vector, đồ thị, Ollama GPU tùy chọn để triển khai cục bộ tái lập được.

## 2.9 Kỹ thuật được luận văn chọn dùng

Hệ chọn lọc kỹ thuật đã khảo sát, không áp mọi phương pháp trong tài liệu. HyDE mở rộng truy vấn ngắn qua LLM nhỏ trước embedding BGE-M3, cải thiện recall khi câu ngắn nhưng không thay chunk và sự kiện đồ thị đối chiếu [14]. BM25 bảo đảm biệt dược, ngưỡng số và cụm “36 hours” vào danh sách ứng viên. BGE-M3 dùng chung cho lọc mục lúc nạp và dense lúc truy vấn. RRF k = 60 gộp kênh Chroma, BM25 và bằng chứng Neo4j.

Bộ lọc mục 3 tầng: từ khóa → embedding → LLM biên lúc nạp. Intake lai regex+lexicon lúc truy vấn; LLM lấp khoảng trống khi tin cậy thấp, merge ưu số đo được hơn suy diễn. Engine GDMT thực thi chính sách khoảng trống và kiểm an toàn ACEi/ARB/ARNI/beta blocker/MRA/SGLT2i trong PostgreSQL. Agent kiểm chứng: fail-closed trên chặn cứng, kiểm trích dẫn tham chiếu chunk ID đã truy xuất, gắn cờ thiếu trường bệnh nhân quan trọng trước trả lời cuối.

Tìm đồ thị local Neo4j cung cấp sự kiện lân cận cho ngữ cảnh GraphRAG. SSE lộ dần khớp tải nhận thức bác sĩ. RBAC tách bác sĩ giường bệnh khỏi clinical lead duyệt rule. Phân rã truy vấn và rerank API tùy chọn khi cấu hình bật. Cố ý không dùng làm cơ chế quyết định chính: kê đơn neural end-to-end, LLM cloud không ràng buộc, RAG vector thuần không đồ thị/rule — đều thiếu khả năng kiểm toán đủ cho an toàn thuốc suy tim.

Lúc truy vấn: chat → intake lai → reasoning GDMT/ràng buộc tất định → GraphRAG song song (HyDE, dense, BM25, sự kiện Neo4j, RRF, rerank tùy chọn) → kiểm chứng đa agent → giải thích song ngữ SSE. Kết hợp khả năng kiểm toán của CDSS rule với linh hoạt từ vựng của truy xuất/sinh hiện đại.

## 2.10 Tóm tắt chương

Chương khảo sát nền tảng lý thuyết HF-CDSS: CDSS như công cụ tăng cường phán đoán bác sĩ [15]–[17]; Five Rights và chỉ số cảnh báo; thách thức suy tim thúc đẩy kết hợp rule–đồ thị–truy xuất. KG như mạng thực thể–quan hệ [7], [8]. RAG từ dense/BM25 tới hợp nhất lai và chỉ mục vector, kèm failure mode y tế thúc đẩy lớp an toàn tất định [12]. LLM trên Transformer, rủi ro ảo giác và suy luận cục bộ [18], [19]. GraphRAG như truy xuất tăng cường đồ thị hợp với bằng chứng chữ, gồm RRF, HyDE, tìm local [13], [14].

Xây tri thức y: nguồn nạp, pipeline trích/liên kết, sync đa kho, lọc mục 3 tầng. Nền lâm sàng HFrEF, trụ GDMT, lab/sinh hiệu then chốt, washout ACEi–ARNI, theo dõi chuẩn liều [2], [3], [6]. Công nghệ triển khai giải thích ngắn. Kỹ thuật được chọn ánh xạ sang vai trò hệ thống cụ thể.

Đường xuyên suốt là tính lai: không kỹ thuật đơn nào đủ cho an toàn thuốc suy tim ở giao diện hội thoại. Module tất định cung quyết định kiểm toán được; truy xuất cung trích dẫn; đồ thị cung ràng buộc quan hệ; LLM cung giải thích song ngữ linh hoạt dưới kiểm chứng và quản trị. Chương 3 chuyển nền tảng này thành yêu cầu, biên module, lược đồ CSDL và hợp đồng API cho triển khai HF-CDSS.
