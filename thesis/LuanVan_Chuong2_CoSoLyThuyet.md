# CHƯƠNG 2: CƠ SỞ LÝ THUYẾT VÀ CÔNG NGHỆ LIÊN QUAN

## 2.1. Hệ thống hỗ trợ quyết định lâm sàng (CDSS)

### 2.1.1. Định nghĩa

Hệ thống hỗ trợ quyết định lâm sàng (Clinical Decision Support System - CDSS) là các công cụ phần mềm được thiết kế để hỗ trợ bác sĩ và nhân viên y tế trong việc đưa ra quyết định chẩn đoán và điều trị. Theo định nghĩa của Viện Y học Hoa Kỳ (Institute of Medicine), CDSS là "bất kỳ hệ thống điện tử nào được thiết kế để hỗ trợ trực tiếp quyết định lâm sàng cho bác sĩ, nhân viên y tế, hoặc bệnh nhân" [1].

### 2.1.2. Phân loại CDSS

CDSS có thể được phân loại theo nhiều tiêu chí khác nhau:

**Theo thời điểm hỗ trợ:**
- **Passive CDSS**: Cung cấp thông tin khi được yêu cầu (user-initiated)
- **Active CDSS**: Đưa ra khuyến nghị chủ động dựa trên dữ liệu bệnh nhân (system-initiated)

**Theo chức năng:**
- CDSS chẩn đoán: Hỗ trợ xác định bệnh dựa trên triệu chứng
- CDSS điều trị: Đề xuất phác đồ điều trị
- CDSS cảnh báo: Thông báo về tương tác thuốc, chống chỉ định
- CDSS quản lý: Hỗ trợ quản lý bệnh mạn tính

**Theo cơ chế hoạt động:**
- **Rule-based CDSS**: Sử dụng các quy tắc if-then do chuyên gia định nghĩa
- **ML-based CDSS**: Sử dụng mô hình machine learning để học từ dữ liệu
- **KB-based CDSS**: Dựa trên cơ sở tri thức (Knowledge Base)
- **Hybrid CDSS**: Kết hợp nhiều phương pháp

### 2.1.3. Lịch sử phát triển CDSS

CDSS có lịch sử phát triển lâu dài, bắt đầu từ những năm 1970:

1. **MYCIN (1976)**: Hệ thống CDSS đầu tiên được phát triển tại Đại học Stanford, sử dụng quy tắc if-then để chẩn đoán và đề xuất điều trị nhiễm trùng huyết [2].

2. **DXplain (1986)**: Hệ thống hỗ trợ chẩn đoán dựa trên triệu chứng, phát triển tại Bệnh viện Đa khoa Massachusetts.

3. **Internist-1/QMR (1970s-1980s)**: Hệ thống chẩn đoán đa bệnh lý nội khoa với hơn 600 bệnh và 4.500 triệu chứng.

4. **DeepMind'sStreams (2016)**: CDSS sử dụng AI để phát hiện suy thận cấp từ kết quả xét nghiệm.

5. **IBM Watson for Oncology (2012)**: Hệ thống AI hỗ trợ điều trị ung thư dựa trên Knowledge Graph.

### 2.1.4. Tiêu chuẩn đánh giá CDSS

**Mô hình "Five Rights" của CDSS [3]:**
1. Right information (Thông tin đúng)
2. Right person (Người nhận đúng)
3. Right format (Định dạng đúng)
4. Right channel (Kênh truyền đúng)
5. Right time (Thời điểm đúng)

**Các chỉ số đánh giá:**
- **Sensitivity**: Khả năng phát hiện các trường hợp cần can thiệp
- **Specificity**: Khả năng tránh cảnh báo sai
- **Positive Predictive Value**: Tỷ lệ cảnh báo đúng
- **Alert Burden**: Số cảnh báo trên bệnh nhân
- **User Satisfaction**: Mức độ hài lòng của người dùng

## 2.2. Knowledge Graph và Đồ thị Tri thức

### 2.2.1. Định nghĩa

Knowledge Graph (Đồ thị Tri thức) là một cấu trúc dữ liệu biểu diễn tri thức dưới dạng đồ thị, trong đó các thực thể (entities) được biểu diễn bằng đỉnh (nodes) và các mối quan hệ (relationships) được biểu diễn bằng cạnh (edges). Knowledge Graph cho phép biểu diễn và truy vấn tri thức một cách có cấu trúc và có ngữ cảnh.

Định nghĩa chính thức từ Wikipedia: "A knowledge graph consists of interoperable descriptions of entities—real-world events, situations, or abstract concepts—with formal axioms that provide context and define relationships between those entities" [4].

### 2.2.2. Cấu trúc Knowledge Graph

**Các thành phần cơ bản:**

1. **Entity (Thực thể)**: Đối tượng cụ thể hoặc trừu tượng
   - Ví dụ: "Bisoprolol", "Suy tim", "eGFR < 30"

2. **Relationship (Quan hệ)**: Kết nối giữa các thực thể
   - Ví dụ: "Bisoprolol" --treats--> "Suy tim"
   - "ACE inhibitor" --contraindicated_with--> "ARNI"

3. **Property (Thuộc tính)**: Thông tin bổ sung về thực thể hoặc quan hệ
   - Ví dụ: Bisoprolol có liều khởi đầu 1.25mg, liều mục tiêu 10mg

4. **Axiom (Tiên đề)**: Các quy tắc suy luận được chấp nhận
   - Ví dụ: "Nếu bệnh nhân đang dùng ARNI, không được dùng ACE inhibitor trong vòng 36 giờ"

### 2.2.3. Knowledge Graph trong Y tế

**Ví dụ ứng dụng:**

```
┌─────────────────┐
│   Drug: ARNI     │
└────────┬────────┘
         │contraindicated_with
         ↓ (within 36 hours)
┌─────────────────┐
│ Drug: ACEi      │────treats────→┌─────────────────┐
└─────────────────┘                │ Heart Failure   │
                                   └─────────────────┘
                                         │treated_by
                                         ↓
                                   ┌─────────────────┐
                                   │ Drug: Beta Blocker│
                                   └─────────────────┘
```

**Các Knowledge Graph y tế nổi tiếng:**

1. **UMLS (Unified Medical Language System)**: Hệ thống 135+ triệu khái niệm y tế
2. **SNOMED CT**: Ngôn ngữ lâm sàng chuẩn hóa với 500.000+ khái niệm
3. **DrugBank**: Cơ sở dữ liệu thuốc với 13.000+ loại thuốc
4. **PubChem**: 110+ triệu hợp chất hóa học

### 2.2.4. Ứng dụng Knowledge Graph trong CDSS

Knowledge Graph được sử dụng trong CDSS để:

1. **Biểu diễn tri thức y khoa**: Đồ thị hóa mối quan hệ thuốc-bệnh-triệu chứng
2. **Hỗ trợ suy luận**: Sử dụng Reasoner để suy ra kết luận mới
3. **Tìm kiếm ngữ cảnh**: Truy vấn đồ thị để tìm thông tin liên quan
4. **Cá nhân hóa**: Kết hợp dữ liệu bệnh nhân với tri thức y khoa

## 2.3. RAG (Retrieval Augmented Generation)

### 2.3.1. Định nghĩa

RAG (Retrieval Augmented Generation - Sinh trợ giúp Tìm kiếm) là một kiến trúc AI kết hợp khả năng truy xuất thông tin (retrieval) với khả năng sinh ngôn ngữ tự nhiên (generation) của Large Language Models. RAG được đề xuất bởi Facebook AI Research (Meta) vào năm 2020 [5].

### 2.3.2. Kiến trúc RAG

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Query     │───→│   Retriever  │───→│    LLM      │
│  (User)    │    │ (Embedding)  │    │  (Generate) │
└─────────────┘    └──────────────┘    └─────────────┘
                          │                   ↑
                          ↓                   │
                   ┌──────────────┐          │
                   │ Vector Store  │──────────┘
                   │ (Knowledge)   │
                   └──────────────┘
```

**Các thành phần:**

1. **Retriever**: Tìm kiếm tài liệu liên quan từ cơ sở tri thức
   - Dense Retrieval: Sử dụng embedding vectors (ví dụ: BM25, DPR)
   - Sparse Retrieval: Sử dụng phương pháp truyền thống (TF-IDF)

2. **Vector Store**: Cơ sở dữ liệu lưu trữ vector embeddings
   - Các hệ thống phổ biến: Pinecone, Weaviate, Milvus, ChromaDB

3. **Generator**: Mô hình ngôn ngữ sinh câu trả lời
   - Sử dụng context từ tài liệu được truy xuất
   - Giảm thiểu hallucination bằng cách dựa trên thông tin thực

### 2.3.3. RAG trong Healthcare

**Ứng dụng trong y tế:**

1. **Hỏi đáp y khoa**: Trả lời câu hỏi dựa trên tài liệu y khoa
2. **Hỗ trợ chẩn đoán**: Truy xuất ca lâm sàng tương tự
3. **Tra cứu thuốc**: Tìm kiếm tương tác, chống chỉ định
4. **Tóm tắt hồ sơ**: Sinh tóm tắt từ dữ liệu bệnh nhân

**Thách thức đặc thù trong y tế:**

1. **Độ chính xác cao**: Sai sót có thể ảnh hưởng đến tính mạng
2. **Thuật ngữ chuyên ngành**: Cần embedding model được fine-tune cho y tế
3. **Ngữ cảnh phức tạp**: Cần hiểu mối quan hệ giữa nhiều yếu tố
4. **Tính cập nhật**: Tri thức y khoa thay đổi liên tục

## 2.4. Large Language Models (LLM)

### 2.4.1. Định nghĩa và Lịch sử

Large Language Models (LLM) là các mô hình ngôn ngữ lớn, được huấn luyện trên lượng dữ liệu văn bản khổng lồ với hàng tỷ đến hàng nghìn tỷ tham số. LLM có khả năng hiểu và sinh ngôn ngữ tự nhiên ở mức độ cao.

**Các mốc quan trọng:**
- **2017**: Transformer architecture được giới thiệu [6]
- **2018**: BERT và GPT-1 ra mắt
- **2019**: GPT-2 với 1.5 tỷ tham số
- **2020**: GPT-3 với 175 tỷ tham số [7]
- **2022**: ChatGPT ra mắt, popularizing LLM applications
- **2023-2024**: GPT-4, Claude, Llama, Gemini...

### 2.4.2. Kiến trúc Transformer

Transformer là kiến trúc nền tảng của hầu hết LLM hiện đại:

**Self-Attention Mechanism:**
```
Attention(Q, K, V) = softmax(QK^T / √d_k) V

Trong đó:
- Q (Query): Vector biểu diễn câu hỏi
- K (Key): Vector biểu diễn khóa
- V (Value): Vector biểu diễn giá trị
- d_k: Chiều của key vectors
```

**Đặc điểm:**
- Parallel processing: Xử lý song song, không cần sequential
- Long-range dependencies: Hiểu được mối quan hệ xa trong văn bản
- Scalability: Dễ dàng mở rộng với nhiều tham số hơn

### 2.4.3. LLM trong Y tế

**Các LLM y tế chuyên biệt:**

1. **BioBERT**: Fine-tuned từ BERT cho biomedical NLP
2. **ClinicalBERT**: BERT cho clinical notes
3. **Med-PaLM**: LLM chuyên về y khoa của Google
4. **Mediterranean**: Mô hình đa ngôn ngữ cho y tế
5. **GatorTron**: LLM y tế của Đại học Florida

**Ứng dụng:**
- Sinh báo cáo lâm sàng
- Hỗ trợ chẩn đoán
- Tra cứu tài liệu y khoa
- Đào tạo y khoa

### 2.4.4. Rủi ro và Hạn chế

**Hallucination:**
LLM có thể sinh ra thông tin sai một cách tự tin, đặc biệt nguy hiểm trong y tế.

**Mitigation strategies:**
1. RAG: Cung cấp context từ nguồn đáng tin cậy
2. Chain-of-Thought: Yêu cầu LLM giải thích lý luận
3. Few-shot prompting: Cung cấp ví dụ đúng
4. Human-in-the-loop: Bác sĩ xem xét trước khi áp dụng

**Bias:**
LLM có thể mang theo bias từ dữ liệu huấn luyện, cần được đánh giá cẩn thận.

## 2.5. GraphRAG - Kết hợp Knowledge Graph và RAG

### 2.5.1. Định nghĩa

GraphRAG là phương pháp kết hợp Knowledge Graph với RAG, sử dụng đồ thị tri thức để tăng cường khả năng truy xuất và sinh của LLM. Phương pháp này được phát triển bởi Microsoft Research vào năm 2024 [8].

### 2.5.2. Ưu điểm so với RAG truyền thống

| Tiêu chí | Vector RAG | GraphRAG |
|----------|------------|----------|
| Hiểu mối quan hệ | Hạn chế | Tốt |
| Truy xuất đa hop | Khó | Dễ dàng |
| Suy luận ngữ cảnh | Yếu | Mạnh |
| Handling global queries | Khó | Tốt |
| Semantic similarity | Cao | Cao |

### 2.5.3. Kiến trúc GraphRAG

```
┌──────────────────────────────────────────────────────────────┐
│                     GraphRAG Pipeline                         │
├──────────────────────────────────────────────────────────────┤
│  1. Knowledge Graph Construction                              │
│     Source Documents → Entity Extraction → Relation Extract   │
│                                    ↓                          │
│  2. Graph Indexing                                           │
│     Entities → Community Detection → Summaries                │
│                                    ↓                          │
│  3. Query Processing                                         │
│     User Query → Local Search (entity-level)                 │
│              → Global Search (community-level)               │
│                                    ↓                          │
│  4. Response Generation                                      │
│     Retrieved Context → LLM Generation                        │
└──────────────────────────────────────────────────────────────┘
```

### 2.5.4. Ứng dụng trong CDSS

GraphRAG đặc biệt phù hợp cho CDSS vì:

1. **Biểu diễn tri thức phức tạp**: Thuốc-bệnh-triệu chứng có nhiều mối quan hệ
2. **Suy luận đa bước**: Từ chẩn đoán → điều trị → theo dõi
3. **Tìm kiếm ngữ cảnh rộng**: Cần hiểu toàn bộ bối cảnh bệnh nhân
4. **Cập nhật tri thức**: Đồ thị dễ dàng mở rộng khi có thông tin mới

## 2.6. Đồ thị Tri thức Y khoa (Medical Knowledge Graph)

### 2.6.1. Đặc điểm

Đồ thị tri thức y khoa có những đặc điểm riêng biệt:

1. **Đa dạng thực thể**: Thuốc, bệnh, triệu chứng, xét nghiệm, thủ thuật
2. **Quan hệ phức tạp**: Nhiều loại quan hệ (treats, causes, interacts, contraindicates)
3. **Thuộc tính số**: Liều lượng, ngưỡng xét nghiệm, chỉ số sinh hóa
4. **Ràng buộc thời gian**: Thời gian washout, thời gian theo dõi
5. **Độ tin cậy**: Phân biệt nguồn từ RCT, guidelines, case reports

### 2.6.2. Nguồn dữ liệu xây dựng

**Nguồn cấu trúc:**
- DrugBank: Thông tin thuốc
- UMLS/SNOMED: Thuật ngữ y khoa chuẩn hóa
- FDA Drug Labels: Nhãn thuốc chính thức

**Nguồn không cấu trúc:**
- Clinical Guidelines: Hướng dẫn điều trị
- Scientific Papers: Bài báo khoa học
- Clinical Notes: Ghi chú lâm sàng

**Nguồn lai:**
- Drug Labels XML: Structured Product Labels
- Clinical Trial Data: Dữ liệu thử nghiệm lâm sàng

### 2.6.3. Các bước xây dựng

```
1. Data Acquisition
   ├── Crawl FDA Drug Labels
   ├── Download Clinical Guidelines
   └── Collect Interaction Databases

2. Preprocessing
   ├── Parse XML/JSON structures
   ├── Extract text sections
   └── Normalize terminology

3. Knowledge Extraction
   ├── NER: Identify medical entities
   ├── RE: Extract relationships
   └── Entity Linking: Map to standard vocabularies

4. Knowledge Fusion
   ├── Deduplicate entities
   ├── Resolve conflicts
   └── Merge from multiple sources

5. Quality Assurance
   ├── Validate extracted facts
   ├── Expert review
   └── Consistency checking
```

## 2.7. Công nghệ triển khai

### 2.7.1. Backend

**Python Framework:**
- **FastAPI**: Framework web async, hỗ trợ RESTful APIs
- **Pydantic**: Data validation và serialization
- **SQLAlchemy**: ORM cho PostgreSQL

**Database:**
- **PostgreSQL**: Cơ sở dữ liệu quan hệ cho tri thức cấu trúc
- **Redis**: Caching và session management
- **ChromaDB/Pgvector**: Vector storage cho embedding

### 2.7.2. Frontend

**React-based:**
- **React 18**: UI framework
- **Tailwind CSS**: Utility-first styling
- **Lucide React**: Icon library

**State Management:**
- React Context/hooks cho local state
- Server state management với React Query

### 2.7.3. Infrastructure

**Containerization:**
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration

**Deployment:**
- **uvicorn**: ASGI server cho FastAPI
- **Nginx**: Reverse proxy

---

## Tài liệu tham khảo Chương 2

[1] Institute of Medicine. (2012). *Health IT and Patient Safety: Building Safer Systems for Better Care*. Washington, DC: The National Academies Press.

[2] Shortliffe, E. H., & Buchanan, B. G. (1975). A model of inexact reasoning in medicine. *Mathematical Biosciences*, 23(3-4), 351-379.

[3] Osheroff, J. A., Teich, J. M., Middleton, B., Steen, E. B., Wright, A., & Detmer, D. E. (2007). A roadmap for national action on clinical decision support. *Journal of the American Medical Informatics Association*, 14(2), 141-145.

[4] Ehrlinger, L., & Wöß, W. (2016). Towards a definition of knowledge graphs. *SEMANTiCS (Posters, Demos, SuCCESS)*, 48(1-4), 2.

[5] Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., ... & Koutrakis, M. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems*, 33, 9459-9474.

[6] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., ... & Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing Systems*, 30.

[7] Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., ... & Amodei, D. (2020). Language models are few-shot learners. *Advances in Neural Information Processing Systems*, 33, 1877-1901.

[8] Edgeworth, M., Jin, J., Li, Y., Luo, D., Menghani, G., & Ruggeri, M. (2024). GraphRAG: Unlocking llm genai to transform private enterprise reasoning. *Microsoft Research Blog*.
