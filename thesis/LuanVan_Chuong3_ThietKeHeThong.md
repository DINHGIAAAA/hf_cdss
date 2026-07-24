# CHƯƠNG 3: THIẾT KẾ HỆ THỐNG

## 3.1. Yêu cầu hệ thống

### 3.1.1. Yêu cầu chức năng

Dựa trên phân tích vấn đề và mục tiêu nghiên cứu, hệ thống CDSS cho bệnh suy tim cần đáp ứng các yêu cầu chức năng sau:

**FR-1: Phân tích hồ sơ bệnh nhân**
- Nhận diện và phân tích thông tin bệnh nhân từ tin nhắn chat
- Trích xuất các chỉ số lâm sàng quan trọng (EF, eGFR, Kali, Huyết áp)
- Xây dựng hồ sơ bệnh nhân cấu trúc

**FR-2: Khuyến nghị điều trị GDMT**
- Đánh giá mức độ áp dụng GDMT hiện tại của bệnh nhân
- Đề xuất bổ sung/thay đổi thuốc dựa trên hướng dẫn điều trị
- Giải thích lý do khuyến nghị dựa trên bằng chứng

**FR-3: Kiểm tra tương tác thuốc**
- Phát hiện các tương tác thuốc nguy hiểm
- Cảnh báo về chống chỉ định tuyệt đối
- Đề xuất thay thế hoặc điều chỉnh liều

**FR-4: Tính toán liều lượng thuốc**
- Tính liều khởi đầu và liều mục tiêu theo đặc điểm bệnh nhân
- Điều chỉnh liều dựa trên chức năng thận
- Theo dõi tiến độ tăng liều

**FR-5: Cảnh báo an toàn**
- Cảnh báo dựa trên chức năng thận (eGFR)
- Cảnh báo về mức kali máu
- Cảnh báo về nhịp tim và huyết áp

**FR-6: Giao diện đa ngôn ngữ**
- Hỗ trợ tiếng Việt và tiếng Anh
- Chuyển đổi ngôn ngữ không mất ngữ cảnh hội thoại

### 3.1.2. Yêu cầu phi chức năng

**NFR-1: Hiệu năng**
- Thời gian phản hồi khuyến nghị < 10 giây cho 95% truy vấn
- Hệ thống hỗ trợ đồng thời 50 người dùng

**NFR-2: Độ chính xác**
- Độ chính xác khuyến nghị điều trị ≥ 90% theo hướng dẫn ESC
- Không có cảnh báo tương tác nguy hiểm bị bỏ sót

**NFR-3: Bảo mật**
- Dữ liệu bệnh nhân được mã hóa
- Tuân thủ quy định về bảo mật y tế

**NFR-4: Khả năng mở rộng**
- Kiến trúc modular cho phép mở rộng sang bệnh lý khác
- Dễ dàng cập nhật cơ sở tri thức

## 3.2. Kiến trúc tổng thể

### 3.2.1. Kiến trúc ba lớp

Hệ thống được thiết kế theo kiến trúc ba lớp (Three-Tier Architecture):

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  Doctor Dashboard │  │  Admin Portal   │  │  API Explorer      │  │
│  │  (React + Vite)  │  │  (React)        │  │  (Development)     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI Backend                             │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │   │
│  │  │ Chat Service │ │ Reasoning   │ │ Knowledge Graph Engine │ │   │
│  │  │ (Streaming) │ │ Service    │ │ (GraphRAG)              │ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │   │
│  │  │ Verification │ │ Dose Calc  │ │ Constraint Engine       │ │   │
│  │  │ Service     │ │ Service    │ │ (Safety Rules)          │ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ PostgreSQL  │ │   Redis     │ │  ChromaDB   │ │ File Storage│   │
│  │ (Rules DB) │ │  (Cache)    │ │ (Embeddings)│ │  (JSONL)   │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2.2. Sơ đồ luồng dữ liệu

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERACTION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

User Message
     │
     ▼
┌─────────────────┐
│ Patient Profile │  1. Extract from message
│    Builder      │  2. Parse clinical state
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GraphRAG Engine │  3. Build context from Knowledge Graph
│   (Retrieval)   │  4. Find relevant constraints/drugs
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Reasoning     │  5. Apply GDMT guidelines
│    Service      │  6. Evaluate patient conditions
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Verification    │  7. Cross-reference evidence
│    Agent        │  8. Validate recommendations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Dose Safety     │  9. Check drug interactions
│   Checker       │  10. Validate dosing
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Recommendation │  11. Generate response
│    Generator     │  12. Add plain language summaries
└────────┬────────┘
         │
         ▼
   Chat Response
   (Streaming)
```

### 3.2.3. Kiến trúc Knowledge Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KNOWLEDGE GRAPH STRUCTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

                          ┌──────────────────┐
                          │   HEART_FAILURE   │
                          │    (Disease)       │
                          └────────┬─────────┘
                                   │treated_by
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
           ▼                       ▼                       ▼
    ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
    │    ACEi      │       │ Beta Blocker │       │   SGLT2i    │
    │  (Drug)      │       │  (Drug)      │       │  (Drug)      │
    └──────┬───────┘       └──────┬───────┘       └──────┬───────┘
           │                       │                       │
           ▼                       ▼                       ▼
    ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
    │ contraindicated │   │   indication  │       │   indication  │
    │    with ARNI   │   │   for HFrEF   │       │   for HFrEF   │
    └──────────────┘       └──────────────┘       └──────────────┘

Entity Types: Drug, Disease, LabValue, DrugClass
Relationship Types: treats, contraindicated_with, indicated_for, interacts_with, metabolized_by
```

## 3.3. Thiết kế module chức năng

### 3.3.1. Module Patient Profile Extraction

**Chức năng:**
Trích xuất và xây dựng hồ sơ bệnh nhân từ tin nhắn chat tự do.

**Đầu vào:**
- Tin nhắn chat của bác sĩ mô tả bệnh nhân

**Đầu ra:**
- Cấu trúc PatientProfile bao gồm:
  - Thông tin cơ bản (tuổi, giới, cân nặng)
  - Chẩn đoán (loại suy tim, EF)
  - Thuốc đang dùng
  - Chỉ số xét nghiệm (eGFR, Kali, BNP)
  - Huyết áp, nhịp tim

**Thuật toán:**
```
1. Parse message với regex patterns cho các giá trị số
2. Extract drug names với NER model
3. Normalize units ( creatinine: mg/dL ↔ µmol/L)
4. Infer missing values từ context
5. Validate against clinical ranges
```

### 3.3.2. Module Knowledge Graph Engine

**Chức năng:**
Truy xuất tri thức y khoa liên quan từ đồ thị tri thức.

**Đầu vào:**
- Patient Profile
- Current medication list

**Đầu ra:**
- Relevant constraints
- Drug interactions
- Guideline recommendations

**Kiến trúc GraphRAG:**

```
Local Search:
├── Entity Extraction: patient → drugs → diseases
├── N-hop neighborhood: drug → interactions → contraindicated drugs
└── Ranking: by relevance score

Global Search:
├── Community Detection: find drug classes
├── Community Summaries: extract patterns
└── Rank Communities: by coverage
```

### 3.3.3. Module Reasoning Service

**Chức năng:**
Đưa ra khuyến nghị điều trị dựa trên GDMT guidelines.

**Luồng xử lý:**

```
1. Evaluate GDMT Status
   ├── Check ACEi/ARB/ARNI: Có/Không/Kontraindicated
   ├── Check Beta Blocker: Có/Không/Kontraindicated
   ├── Check MRA: Có/Không/Chỉ định
   └── Check SGLT2i: Có/Không/Chỉ định

2. Identify Gaps
   └── For each missing component:
       ├── Check contraindications
       ├── Evaluate readiness
       └── Generate recommendation

3. Generate Response
   ├── Status summary
   ├── Priority recommendations
   └── Evidence citations
```

### 3.3.4. Module Dose Calculation

**Chức năng:**
Tính toán liều lượng thuốc cá nhân hóa.

**Các loại tính toán:**

1. **Starting Dose**: Liều khởi đầu an toàn
2. **Target Dose**: Liều mục tiêu theo guideline
3. **Renal Adjustment**: Điều chỉnh theo eGFR
4. **Titration Schedule**: Lịch tăng liều

**Ví dụ cho Bisoprolol:**

```
Base starting dose: 1.25mg once daily
Target dose: 10mg once daily (or highest tolerated)

Renal adjustment (eGFR < 30):
  → Start at 1.25mg, titrate slower

Titration schedule:
  Week 1-2: 1.25mg
  Week 3-4: 2.5mg (if tolerated)
  Week 5-6: 3.75mg (if tolerated)
  Week 7-8: 5mg (if tolerated)
  Week 9-10: 7.5mg (if tolerated)
  Week 11+: 10mg (target)
```

### 3.3.5. Module Safety Constraint Engine

**Chức năng:**
Kiểm tra các ràng buộc an toàn và cảnh báo.

**Loại constraints:**

1. **Hard Constraints (Không thể vi phạm)**
   - Chống chỉ định tuyệt đối
   - Tương tác nguy hiểm có thể gây tử vong

2. **Soft Constraints (Cảnh báo)**
   - Cần theo dõi
   - Cần điều chỉnh liều
   - Cần xem xét

**Ví dụ:**

```
Hard Constraint:
IF drug = ACEi AND recent_ARNI_use = true
THEN status = "avoid" (contraindicated within 36 hours)

Soft Constraint:
IF drug = MRA AND eGFR < 30
THEN status = "consider_with_caution"
AND monitoring = ["Check potassium within 1 week"]
```

## 3.4. Thiết kế cơ sở dữ liệu

### 3.4.1. PostgreSQL Schema

**Bảng Constraints:**

```sql
CREATE TABLE constraint_rules (
    id SERIAL PRIMARY KEY,
    constraint_id VARCHAR(100) UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    target_drug_class VARCHAR(100),
    action VARCHAR(50),  -- 'avoid', 'consider', 'continue', etc.
    reason TEXT,
    risk_names TEXT[],
    severity_any TEXT[],
    evidence_ref TEXT,
    clinical_sources JSONB,
    status VARCHAR(20) DEFAULT 'draft',  -- draft, approved, retired
    source VARCHAR(50),
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);
```

**Bảng Dose Rules:**

```sql
CREATE TABLE dose_rules (
    id SERIAL PRIMARY KEY,
    dose_rule_id VARCHAR(100) UNIQUE NOT NULL,
    version INTEGER DEFAULT 1,
    drug_class VARCHAR(100),
    drug_keys TEXT[],
    calculation_type VARCHAR(50),
    starting_dose JSONB,      -- {"value": 1.25, "unit": "mg"}
    target_dose JSONB,
    renal_adjustment JSONB,
    titration_schedule JSONB,
    evidence_ref TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    safety_tier VARCHAR(50),
    metadata JSONB
);
```

**Bảng Interactions:**

```sql
CREATE TABLE interaction_rules (
    id SERIAL PRIMARY KEY,
    interaction_rule_id VARCHAR(100) UNIQUE NOT NULL,
    drug_set_a TEXT[],
    drug_set_b TEXT[],
    interaction_type VARCHAR(50),
    severity VARCHAR(20),
    description TEXT,
    management TEXT,
    evidence_ref TEXT,
    status VARCHAR(20) DEFAULT 'draft'
);
```

### 3.4.2. Redis Cache Structure

```
# Constraint cache
constraint_cache:{drug_class} → [constraint_json]

# Draft patient cache
draft:{conversation_id} → {patient_profile_json}

# Message history cache
messages:{conversation_id} → [messages_json]

# LLM response cache
llm_cache:{hash(input)} → {response_json}
```

### 3.4.3. Vector Store Schema (ChromaDB)

```python
Collection: "clinical_chunks"

Schema:
{
    "id": str,              # chunk_id
    "embedding": float[384], # embedding vector
    "document": str,         # text content
    "metadata": {
        "source": str,       # drug_label, guideline, etc.
        "drug_class": str,
        "section": str,
        "chunk_type": str    # dosing, warning, indication, etc.
    }
}
```

## 3.5. Thiết kế API

### 3.5.1. Chat API

**Endpoint: POST /api/v1/chat**

```json
Request:
{
    "message": "Nam 65 tuổi, EF 30%, đang dùng bisoprolol 5mg...",
    "conversation_id": "conv_123",
    "patient": {
        "age": 65,
        "sex": "male",
        "diagnosis": {
            "hf_type": "HFrEF",
            "ef": 30
        }
    },
    "language": "vi"
}

Response (SSE):
event: patient_draft
data: { "patient_draft": {...} }

event: recommendation_ready
data: { "recommendation": {...} }

event: verification_ready
data: { "verification": {...} }

event: answer
data: { "content": "..." }
```

### 3.5.2. Admin APIs

**Constraints Management:**

```
GET    /api/v1/admin/constraints/rules
POST   /api/v1/admin/constraints/rules/{id}/approve
POST   /api/v1/admin/constraints/rules/{id}/retire
GET    /api/v1/admin/constraints/rules/{id}/history
```

**Dose Rules Management:**

```
GET    /api/v1/admin/dose-rules
POST   /api/v1/admin/dose-rules/{id}/approve
GET    /api/v1/admin/dose-rules/active  # For runtime
```

**System Health:**

```
GET    /api/v1/health
GET    /api/v1/health/ready
GET    /api/v1/health/dependencies
```

## 3.6. Giao diện người dùng

### 3.6.1. Doctor Dashboard

**Bố cục:**

```
┌────────────────────────────────────────────────────────────────────┐
│ Header: Logo | Navigation | Language Toggle | User               │
├───────────────────────────────┬────────────────────────────────────┤
│                               │                                    │
│   Chat Interface              │    Clinical Panel                  │
│   ┌───────────────────────┐  │    ┌────────────────────────────┐ │
│   │ Message History       │  │    │ Patient Summary           │ │
│   │                       │  │    │ • Age: 65, Male          │ │
│   │ User: Bệnh nhân nam   │  │    │ • EF: 30%                │ │
│   │                       │  │    │ • eGFR: 45               │ │
│   │ Assistant: Đã phân    │  │    │ Current Medications:     │ │
│   │ tích hồ sơ bệnh nhân │  │    │ • Bisoprolol 5mg         │ │
│   │                       │  │    └────────────────────────────┘ │
│   └───────────────────────┘  │                                    │
│   ┌───────────────────────┐  │    ┌────────────────────────────┐ │
│   │ Input: Nhập tin nhắn  │  │    │ GDMT Status               │ │
│   │ [Send]                │  │    │ ✓ ACEi/ARB/ARNI: Missing  │ │
│   └───────────────────────┘  │    │ ✓ Beta Blocker: On target │ │
│                               │    │ ✗ MRA: Not on list       │ │
│                               │    │ ✗ SGLT2i: Not on list   │ │
│                               │    └────────────────────────────┘ │
│                               │                                    │
│                               │    ┌────────────────────────────┐ │
│                               │    │ Recommendations           │ │
│                               │    │ ⚠️ Consider starting MRA   │ │
│                               │    │ ⚠️ Consider SGLT2i       │ │
│                               │    └────────────────────────────┘ │
└───────────────────────────────┴────────────────────────────────────┘
```

### 3.6.2. Admin Portal

**Chức năng:**

1. **Rules Management**: Duyệt, chỉnh sửa, phê duyệt các rules
2. **System Monitoring**: Theo dõi health và performance
3. **Data Import**: Import dữ liệu từ pipeline

## 3.7. Bảo mật và Quyền truy cập

### 3.7.1. Xác thực (Authentication)

- JWT-based authentication
- Role-based access control (RBAC)
- Session management với Redis

### 3.7.2. Phân quyền (Authorization)

```
Roles:
├── doctor: Read-only access to chat, view recommendations
├── clinical_lead: Approve/reject rules, manage constraints
└── admin: Full system access

Permissions Matrix:
│ Action              │ doctor │ clinical_lead │ admin │
│---------------------│--------│---------------│-------│
│ Chat                │ ✓      │ ✓             │ ✓     │
│ View recommendations│ ✓      │ ✓             │ ✓     │
│ Approve rules       │ ✗      │ ✓             │ ✓     │
│ Manage users        │ ✗      │ ✗             │ ✓     │
│ System config       │ ✗      │ ✗             │ ✓     │
```

### 3.7.3. Mã hóa dữ liệu

- TLS 1.3 cho truyền thông
- At-rest encryption cho PostgreSQL
- Encrypted patient data in cache

---

## Tài liệu tham khảo Chương 3

[1] Fowler, M. (2003). *Patterns of Enterprise Application Architecture*. Addison-Wesley.

[2] Richards, M. (2015). *Fundamentals of Software Architecture*. O'Reilly Media.

[3] Microsoft. (2024). *Azure Architecture Center - Healthcare*. Microsoft Docs.

[4] Oussous, A., Benhaddou, D., & Ghenima, S. (2018). Big Data technologies: A comparative study. *2018 International Conference on Selected Topics in Mobile and Wireless Networking (MoWNeT)*.
