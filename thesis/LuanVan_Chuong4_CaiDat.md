# CHƯƠNG 4: CÀI ĐẶT VÀ TRIỂN KHAI

## 4.1. Môi trường phát triển

### 4.1.1. Cấu hình phần cứng

**Yêu cầu tối thiểu:**

| Thành phần | Máy phát triển | Máy chủ |
|------------|----------------|---------|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Storage | 100 GB SSD | 500 GB SSD |
| GPU | Optional | NVIDIA GPU (8GB VRAM) |

### 4.1.2. Phần mềm yêu cầu

**Backend:**
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Ollama (cho embedding model)

**Frontend:**
- Node.js 18+
- npm hoặc pnpm
- React 18+

**Infrastructure:**
- Docker & Docker Compose
- Nginx (reverse proxy)

### 4.1.3. Cài đặt môi trường

```bash
# Clone repository
git clone https://github.com/your-repo/hf-cdss.git
cd hf-cdss

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend/doctor-dashboard
npm install

# Start infrastructure
cd ../infrastructure
docker-compose up -d postgres redis
```

## 4.2. Kiến trúc Pipeline Xây dựng Tri thức

### 4.2.1. Tổng quan Pipeline

Pipeline xây dựng tri thức là hệ thống tự động trích xuất, xử lý và đồng bộ tri thức y khoa từ các nguồn dữ liệu thô vào cơ sở dữ liệu CDSS.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE PIPELINE ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────────────────┘

Data Sources                    Pipeline Steps                    Output
─────────────                   ─────────────                    ──────

FDA Drug Labels                 ┌─────────────┐
  (XML/SPL)                    │  Acquisition │  Raw Data
         │                     └──────┬──────┘        ↓
         └──────────────────────────▶│             ┌─────────┐
                                    │             │  JSONL  │
Guidelines (PDF/HTML)              │             │  Files  │
         │                         │             └────┬────┘
         └────────────────────────▶├─────────────────┘
                                    │
                                    ▼
                              ┌─────────────┐
                              │  Processing  │
                              │  & Chunking  │────────▶ Chunks
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │  Extraction  │────────▶ Extracted Rules
                              │  & Matching   │
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │ Classification│────────▶ Classified Rules
                              │  & Validation │
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │   Sync to    │────────▶ PostgreSQL
                              │  Postgres    │
                              └─────────────┘
```

### 4.2.2. Module Acquisition (Thu thập dữ liệu)

**Chức năng:** Thu thập dữ liệu từ các nguồn y khoa.

**Nguồn dữ liệu:**

1. **FDA Drug Labels (SPL - Structured Product Labels)**
   - Format: XML (FDA SPL standard)
   - Nguồn: FDA National Library of Medicine
   - URL: https://dailymed.nlm.nih.gov

2. **Clinical Guidelines**
   - Format: PDF, HTML
   - Nguồn: ESC, AHA/ACC, HFSA
   - Ví dụ: 2022 ESC HF Guidelines

3. **Drug Interaction Databases**
   - Format: JSON, CSV
   - Nguồn: DrugBank, RxNorm, Micromedex

**Code Implementation:**

```python
# scraper/acquisition/download_sources.py

class DrugLabelAcquirer:
    """Acquire FDA drug labels from DailyMed."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.session = httpx.AsyncClient()

    async def download_drug_labels(self, drug_names: list[str]):
        """Download SPL labels for specified drugs."""
        for drug_name in drug_names:
            spl_id = await self._find_spl_id(drug_name)
            xml_content = await self._download_spl(spl_id)
            self._save_xml(drug_name, xml_content)

    async def _find_spl_id(self, drug_name: str) -> str:
        """Find SPL set ID from DailyMed."""
        search_url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
        response = await self.session.get(search_url, params={"name": drug_name})
        data = response.json()
        return data["data"][0]["setid"]
```

### 4.2.3. Module Processing (Xử lý dữ liệu)

**Chức năng:** Parse và chia nhỏ dữ liệu thô thành các phần có thể xử lý.

**Các bước xử lý:**

```
1. Parse XML/HTML/PDF
   └── Extract text content and metadata

2. Section Identification
   └── Identify clinical sections (DOSAGE, WARNINGS, etc.)

3. Text Chunking
   └── Split into semantically coherent chunks
   └── Overlap for context preservation

4. Normalization
   └── Standardize drug names (RxNorm CUI)
   └── Normalize units (mg, mEq/L, etc.)
```

**Chunking Strategy:**

```python
# scraper/transform/chunk_sections.py

class SectionChunker:
    """Split clinical documents into semantically coherent chunks."""

    def chunk_guideline(self, text: str, max_tokens: int = 512) -> list[Chunk]:
        """Split guideline into chunks with overlap."""
        sentences = self._split_sentences(text)
        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = self._estimate_tokens(sentence)

            if current_size + sentence_size > max_tokens:
                # Save current chunk
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk))
                # Keep overlap
                current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else current_chunk
                current_size = sum(self._estimate_tokens(s) for s in current_chunk)

            current_chunk.append(sentence)
            current_size += sentence_size

        # Add final chunk
        if current_chunk:
            chunks.append(self._create_chunk(current_chunk))

        return chunks
```

### 4.2.4. Module Extraction (Trích xuất tri thức)

**Chức năng:** Trích xuất các thực thể và quan hệ y khoa từ text.

**Loại trích xuất:**

1. **Named Entity Recognition (NER)**
   - Drug names
   - Dosage values
   - Lab values
   - Clinical conditions

2. **Relationship Extraction**
   - Drug → Indication
   - Drug → Contraindication
   - Drug → Interaction
   - Drug → Side effect

3. **Constraint Rules**
   - IF conditions THEN actions
   - With evidence citations

**Extraction với LLM:**

```python
# scraper/semantic/rule_builder.py

class ClinicalRuleExtractor:
    """Extract clinical decision rules using LLM."""

    SYSTEM_PROMPT = """
    Bạn là chuyên gia y khoa. Trích xuất các quy tắc lâm sàng từ văn bản.
    Mỗi quy tắc có:
    - drug_class: Loại thuốc (VD: ACE inhibitor, Beta blocker)
    - action: Hành động (VD: avoid, consider, continue)
    - conditions: Điều kiện áp dụng (VD: eGFR < 30)
    - rationale: Giải thích ngắn gọn
    - evidence_ref: Tham chiếu bằng chứng
    """

    async def extract_rules(self, text: str) -> list[ClinicalRule]:
        """Extract rules from clinical text."""
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Trích xuất quy tắc từ:\n{text}"}
            ],
            response_format=ClinicalRuleList
        )
        return response.rules
```

### 4.2.5. Module Classification (Phân loại)

**Chức năng:** Phân loại và gắn nhãn các quy tắc đã trích xuất.

**Phân loại theo:**

1. **Safety Tier**
   - `hard_block`: Không được phép vi phạm
   - `usable_rules`: Có thể sử dụng ngay
   - `needs_condition_refinement`: Cần cải thiện điều kiện

2. **Action Type**
   - `avoid`: Chống chỉ định
   - `consider`: Có thể cân nhắc
   - `consider_with_caution`: Cần thận trọng
   - `continue`: Tiếp tục dùng

**Classification Logic:**

```python
# scraper/process/classify_rules.py

class RuleClassifier:
    """Classify extracted rules by safety tier and action type."""

    def classify(self, rule: ClinicalRule) -> ClassificationResult:
        """Classify a single rule."""
        safety_tier = self._determine_safety_tier(rule)
        action_type = self._determine_action_type(rule)
        confidence = self._calculate_confidence(rule)

        return ClassificationResult(
            safety_tier=safety_tier,
            action=action_type,
            confidence=confidence,
            needs_review=safety_tier == "needs_condition_refinement"
        )

    def _determine_safety_tier(self, rule: ClinicalRule) -> str:
        """Determine safety tier based on rule characteristics."""
        if not rule.conditions:
            return "needs_condition_refinement"

        if self._has_absolute_contraindication(rule):
            return "hard_block"

        if self._has_complete_dosing_info(rule):
            return "usable_rules"

        return "needs_condition_refinement"
```

### 4.2.6. Module Section Filtering (Lọc phần quan trọng)

**Chức năng:** Lọc các sections quan trọng từ tài liệu dựa trên semantic similarity.

**Luồng lọc:**

```
Input: All parsed sections from documents
         │
         ▼
┌─────────────────┐
│  Keyword Match │──── Match found ────▶ KEEP
└────────┬────────┘
         │ No match
         ▼
┌─────────────────┐
│ Embedding Score│──── Score ≥ 0.52 ────▶ KEEP
│   (BGE-M3)     │
└────────┬────────┘
         │ Score < 0.52
         ▼
┌─────────────────┐
│ Borderline Zone │─── Score ∈ [0.40, 0.52) ───┐
│    (LLM Call)  │                              │
└────────┬────────┘                              │
         │                                        ▼
         │                              ┌─────────────────┐
         │                              │  LLM Review     │
         │                              │  Keep/Drop?     │
         │                              └────────┬────────┘
         │                                        │
         └──── Score < 0.40 ────▶ DROP            │
                                           ┌──────┴──────┐
                                           │             │
                                           ▼             ▼
                                        KEEP          DROP
```

**Implementation:**

```python
# scraper/semantic/section_filter.py

class SectionFilter:
    """Filter important clinical sections using multi-tier approach."""

    def __init__(self, llm_client):
        self.llm = llm_client
        self.prototypes = self._load_prototypes()

    async def filter_sections(self, sections: list[Section]) -> list[Section]:
        """Filter sections through three-tier cascade."""
        important = []

        for section in sections:
            # Tier 1: Keyword matching
            if self._keyword_match(section):
                important.append(section)
                continue

            # Tier 2: Semantic embedding
            score = await self._compute_similarity(section)
            if score >= config.SECTION_SIMILARITY_THRESHOLD:
                important.append(section)
                continue

            # Tier 3: Borderline LLM review
            if score >= config.SECTION_BORDERLINE_LOW_THRESHOLD:
                should_keep = await self._llm_review(section)
                if should_keep:
                    important.append(section)

        return important

    async def _llm_review(self, section: Section) -> bool:
        """Ask LLM whether borderline section is important."""
        prompt = f"""
        Đánh giá section sau có quan trọng cho điều trị suy tim không?

        Title: {section.title}
        Content: {section.text[:500]}

        Trả lời YES nếu section chứa:
        - Thông tin về thuốc điều trị suy tim
        - Liều lượng, cách dùng
        - Cảnh báo, tương tác
        - Chống chỉ định

        Trả lời NO nếu:
        - Không liên quan đến suy tim
        - Chỉ là thông tin hành chính
        """
        response = await self.llm.chat(prompt)
        return "YES" in response.upper()
```

## 4.3. Cài đặt Backend

### 4.3.1. Cấu trúc Project Backend

```
backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── admin/
│   │       │   ├── constraint_rules.py
│   │       │   ├── dose_rules.py
│   │       │   ├── dose_safety_warnings.py
│   │       │   ├── gdmt_policies.py
│   │       │   └── interaction_rules.py
│   │       ├── chat.py
│   │       └── health.py
│   ├── modules/
│   │   ├── chat/
│   │   │   ├── service.py
│   │   │   └── clinical_state.py
│   │   ├── clinical_intake_extraction/
│   │   │   └── service.py
│   │   ├── constraint_builder/
│   │   │   └── service.py
│   │   ├── dose_calculation/
│   │   │   └── xml_dose_extractor.py
│   │   ├── dose_safety/
│   │   │   └── evaluator.py
│   │   ├── explanation/
│   │   │   ├── card_summarizer.py
│   │   │   └── llm_service.py
│   │   ├── graphrag/
│   │   │   └── service.py
│   │   ├── reasoning/
│   │   │   └── service.py
│   │   ├── verification_agents/
│   │   │   └── service.py
│   │   └── datastores/
│   │       ├── postgres.py
│   │       └── redis_client.py
│   ├── schemas/
│   │   ├── chat.py
│   │   ├── recommendation.py
│   │   └── patient.py
│   ├── prompts/
│   │   ├── card_summary.py
│   │   └── explanation.py
│   └── core/
│       ├── config.py
│       └── llm_runtime.py
├── tests/
│   └── test_*.py
├── requirements.txt
└── main.py
```

### 4.3.2. Chat Service Implementation

```python
# app/modules/chat/service.py

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

class ChatService:
    """Main chat service handling clinical decision support."""

    async def process_message(self, request: ChatRequest):
        """Process a chat message and stream responses."""
        # 1. Extract patient profile
        patient = await extract_patient_from_message(request.message)

        # 2. Build clinical state
        clinical_state = build_clinical_state(patient, request.clinical_attachments)

        # 3. Get GraphRAG context
        context = await build_graphrag_context(clinical_state)

        # 4. Generate recommendations
        recommendation = await build_recommendation(clinical_state, context)

        # 5. Verify against constraints
        verification = await verify_recommendation(recommendation)

        # 6. Add plain language summaries
        recommendation = await attach_plain_language_summaries(
            recommendation,
            language=request.language or "vi"
        )

        # 7. Generate LLM answer
        answer = await build_llm_answer(patient, recommendation, verification)

        return {
            "patient_draft": patient,
            "recommendation": recommendation,
            "verification": verification,
            "answer": answer
        }
```

### 4.3.3. GraphRAG Service Implementation

```python
# app/modules/graphrag/service.py

class GraphRAGService:
    """GraphRAG service for clinical knowledge retrieval."""

    def __init__(self, constraint_loader, embedding_model):
        self.constraints = constraint_loader
        self.embedder = embedding_model
        self.vector_store = ChromaDBClient()

    async def get_relevant_context(
        self,
        patient: PatientProfile,
        medications: list[str]
    ) -> GraphRAGContext:
        """Get relevant clinical context using GraphRAG."""

        # 1. Build entity query
        query_entities = self._extract_entities(patient, medications)

        # 2. Local search: Find relevant constraints
        local_constraints = await self._local_search(query_entities)

        # 3. Global search: Find community patterns
        global_insights = await self._global_search(query_entities)

        # 4. Merge and rank
        context = self._merge_context(local_constraints, global_insights)

        return context

    async def _local_search(self, entities: list[str]) -> list[Constraint]:
        """Search constraints by entity similarity."""
        query_embedding = self.embedder.encode(" ".join(entities))

        # Search vector store
        results = self.vector_store.search(
            query_vector=query_embedding,
            n_results=20,
            filter={"type": "constraint"}
        )

        # Fetch full constraints
        constraints = [
            self.constraints.get_by_id(r["id"])
            for r in results
        ]

        return constraints
```

### 4.3.4. Card Summarizer Implementation

```python
# app/modules/explanation/card_summarizer.py

class CardSummarizer:
    """Generate plain language summaries for recommendation cards."""

    # Drug class mappings
    DRUG_CLASS_PLAIN = {
        "vi": {
            "ACE inhibitor": "Thuốc hạ huyết áp",
            "SGLT2 inhibitor": "Thuốc đái tháo đường, bảo vệ thận",
            "Beta blocker": "Thuốc giảm nhịp tim, bảo vệ tim",
            "MRA": "Thuốc lợi tiểu giữ kali",
            "ARNI": "Thuốc tim mạch (ARNI)",
        },
        "en": {
            "ACE inhibitor": "Blood pressure medication",
            "SGLT2 inhibitor": "Diabetes & kidney protection medication",
            "Beta blocker": "Heart rate & heart protection medication",
            "MRA": "Potassium-sparing diuretic",
            "ARNI": "Heart medication (ARNI)",
        }
    }

    # Status mappings
    STATUS_LABELS = {
        "vi": {
            "avoid": "Nên tránh hoặc hoãn",
            "consider_with_caution": "Cân nhắc thận trọng",
            "consider": "Có thể cân nhắc",
            "continue": "Tiếp tục",
            "blocked": "Bị chặn",
        },
        "en": {
            "avoid": "Avoid or delay",
            "consider_with_caution": "Use with caution",
            "consider": "Consider",
            "continue": "Continue",
            "blocked": "Blocked",
        }
    }

    def simplify_structured_field(
        self,
        raw_value: str,
        field_type: str,
        language: str
    ) -> str:
        """Simplify structured fields using predefined mappings."""
        if field_type == "status":
            return self.STATUS_LABELS.get(language, self.STATUS_LABELS["en"]).get(
                raw_value, raw_value
            )
        if field_type == "drug_class":
            return self.DRUG_CLASS_PLAIN.get(language, self.DRUG_CLASS_PLAIN["en"]).get(
                raw_value, raw_value
            )
        return raw_value

    def simplify_recommendation_fields(
        self,
        item: MedicationRecommendation,
        language: str = "vi"
    ) -> dict:
        """Generate simplified versions of recommendation fields."""
        return {
            "drug_class_plain": {
                "vi": self.simplify_structured_field(item.drug_class, "drug_class", "vi"),
                "en": self.simplify_structured_field(item.drug_class, "drug_class", "en"),
            },
            "status_plain": {
                "vi": self.simplify_structured_field(item.status, "status", "vi"),
                "en": self.simplify_structured_field(item.status, "status", "en"),
            },
        }
```

## 4.4. Cài đặt Frontend

### 4.4.1. Cấu trúc Project Frontend

```
frontend/
├── doctor-dashboard/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ClinicalChatThread.jsx
│   │   │   ├── ClinicalPanel.jsx
│   │   │   ├── ChatInput.jsx
│   │   │   ├── DosePlanDisplay.jsx
│   │   │   └── LanguageToggle.jsx
│   │   ├── pages/
│   │   │   ├── ChatPage.jsx
│   │   │   ├── EvidencePage.jsx
│   │   │   └── ApiExplorerPage.jsx
│   │   ├── hooks/
│   │   │   ├── useChat.js
│   │   │   ├── useConversations.js
│   │   │   └── useApiHealth.js
│   │   ├── lib/
│   │   │   ├── clinicalChatStream.js
│   │   │   └── recommendationDisplay.js
│   │   ├── i18n/
│   │   │   ├── LanguageProvider.jsx
│   │   │   └── messages.js
│   │   └── api/
│   │       └── index.js
│   └── package.json
├── admin/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   └── package.json
└── shared/
    ├── governance/
    │   ├── catalogConfig.js
    │   └── displayNames.js
    └── api/
        └── client.js
```

### 4.4.2. ClinicalPanel Component

```jsx
// frontend/doctor-dashboard/src/components/ClinicalPanel.jsx

import { useLanguage } from "../i18n/LanguageProvider.jsx";

function RecommendationCard({ item, evidenceChunks = [], sharedVitals = [] }) {
  const { language } = useLanguage();
  const simplified = item.simplified || {};

  // Helper to get simplified field with fallback
  const getSimplified = (field, fallback = []) => {
    const simplifiedList = simplified[field];
    if (Array.isArray(simplifiedList) && simplifiedList.length > 0) {
      return simplifiedList.map(item => item?.[language] || item?.vi || "").filter(Boolean);
    }
    return fallback;
  };

  // Simplified fields: use simplified_* if available, fallback
  const displayDrugClass =
    simplified.drug_class_plain?.[language] ||
    simplified.drug_class_plain?.vi ||
    item.drug_class;

  const displayStatus =
    simplified.status_plain?.[language] ||
    simplified.status_plain?.vi ||
    item.status;

  const reasoningItems = getSimplified(
    "reasoning_plain",
    item.clinical_reasoning
  );
  const actionItems = getSimplified(
    "action_items_plain",
    item.action_items
  );

  return (
    <article className="recommendation-card">
      <header>
        <h3>{displayDrugClass}</h3>
        <Badge tone={displayStatus}>{displayStatus}</Badge>
      </header>

      <div className="clinical-details">
        {reasoningItems.map((item, i) => (
          <RecommendationBlock key={i} title="Clinical Reasoning">
            <p>{item}</p>
          </RecommendationBlock>
        ))}
      </div>
    </article>
  );
}
```

### 4.4.3. Language Toggle Implementation

```jsx
// frontend/doctor-dashboard/src/i18n/LanguageProvider.jsx

import { createContext, useCallback, useContext, useState } from "react";

const LANGUAGE_STORAGE_KEY = "hf_cdss_chat_language";

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(() => {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored || "vi";
  });

  const setLanguage = useCallback((code) => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    setLanguageState(code);
    document.documentElement.lang = code;
  }, []);

  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return context;
}
```

## 4.5. Triển khai hệ thống

### 4.5.1. Docker Configuration

```yaml
# infrastructure/docker-compose.yml

version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: hf_cdss
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  backend:
    build: ../backend
    environment:
      DATABASE_URL: postgresql://postgres:${DB_PASSWORD}@postgres:5432/hf_cdss
      REDIS_URL: redis://redis:6379
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on:
      - postgres
      - redis
      - ollama
    ports:
      - "8000:8000"

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

  frontend:
    build: ../frontend/doctor-dashboard
    ports:
      - "3000:3000"
    depends_on:
      - backend

  admin:
    build: ../frontend/admin
    ports:
      - "3001:3000"
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - frontend
      - admin
      - backend

volumes:
  postgres_data:
  redis_data:
  ollama_data:
```

### 4.5.2. Nginx Configuration

```nginx
# infrastructure/nginx.conf

events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    upstream frontend {
        server frontend:3000;
    }

    upstream admin {
        server admin:3000;
    }

    server {
        listen 80;

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_cache_bypass $http_upgrade;
        }

        # Admin Portal
        location /admin {
            rewrite ^/admin(.*)$ $1 break;
            proxy_pass http://admin;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
        }

        # API Backend
        location /api {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

### 4.5.3. Environment Configuration

```bash
# infrastructure/.env.example

# Database
DB_PASSWORD=your_secure_password_here

# Redis
REDIS_URL=redis://redis:6379

# Ollama (Local LLM)
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b
EMBEDDING_MODEL=bge-m3

# Application
SECRET_KEY=your_secret_key_here
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Feature Flags
HF_CDSS_SECTION_BORDERLINE_LLM_ENABLED=true
HF_CDSS_SECTION_SIMILARITY_THRESHOLD=0.52
HF_CDSS_SECTION_BORDERLINE_LOW_THRESHOLD=0.40
HF_CDSS_SECTION_BORDERLINE_LLM_MAX=400
```

## 4.6. Testing

### 4.6.1. Unit Tests

```python
# backend/app/tests/test_card_summarizer.py

import pytest
from app.modules.explanation.card_summarizer import (
    CardSummarizer,
    MedicationRecommendation
)

@pytest.fixture
def summarizer():
    return CardSummarizer()

@pytest.fixture
def sample_recommendation():
    return MedicationRecommendation(
        drug_class="ACE inhibitor",
        status="consider",
        rationale="Patient not on ACEi",
        clinical_reasoning=[
            "No current ACE inhibitor detected",
            "HFrEF patient eligible for ACEi"
        ],
        action_items=[
            "Consider starting low-dose ACE inhibitor",
            "Monitor blood pressure after initiation"
        ]
    )

def test_simplify_drug_class_vi(summarizer, sample_recommendation):
    result = summarizer.simplify_structured_field(
        sample_recommendation.drug_class,
        "drug_class",
        "vi"
    )
    assert result == "Thuốc hạ huyết áp"

def test_simplify_drug_class_en(summarizer, sample_recommendation):
    result = summarizer.simplify_structured_field(
        sample_recommendation.drug_class,
        "drug_class",
        "en"
    )
    assert result == "Blood pressure medication"

def test_simplify_status(summarizer, sample_recommendation):
    assert summarizer.simplify_structured_field("avoid", "status", "vi") == "Nên tránh hoặc hoãn"
    assert summarizer.simplify_structured_field("avoid", "status", "en") == "Avoid or delay"
```

### 4.6.2. Integration Tests

```python
# backend/app/tests/test_chat_flow.py

import pytest
from app.modules.chat.service import ChatService

@pytest.mark.asyncio
async def test_chat_message_processing():
    """Test full chat message processing flow."""
    service = ChatService()

    request = ChatRequest(
        message="Bệnh nhân nam 65 tuổi, EF 30%, đang dùng bisoprolol 5mg. eGFR 45, Kali 4.2",
        conversation_id="test_conv",
        language="vi"
    )

    result = await service.process_message(request)

    assert result.patient_draft is not None
    assert result.recommendation is not None
    assert len(result.recommendation.recommendations) > 0
    assert result.patient_draft.demographics.age == 65
```

## 4.7. Vận hành và Bảo trì

### 4.7.1. Monitoring

**Health Checks:**
```bash
# Check system health
curl http://localhost:8000/api/v1/health

# Check database connection
curl http://localhost:8000/api/v1/health/ready

# Check dependencies
curl http://localhost:8000/api/v1/health/dependencies
```

**Logging:**
- Application logs: stdout → Docker logs
- Structured logging với JSON format
- Log levels: DEBUG, INFO, WARNING, ERROR

### 4.7.2. Backup và Restore

```bash
# Backup database
docker exec hf_cdss-postgres-1 pg_dump -U postgres hf_cdss > backup.sql

# Restore database
docker exec -i hf_cdss-postgres-1 psql -U postgres hf_cdss < backup.sql
```

### 4.7.3. Update Knowledge Base

```bash
# Run pipeline
cd scraper
python -m scraper.orchestration.run_ingestion_pipeline --from-step kg_base

# Sync to database
python -m scraper.process.sync_governance_catalog --catalog all

# Verify counts
python -m scraper.orchestration.data_quality_report
```

---

## Tài liệu tham khảo Chương 4

[1] Richardson, L., & Ruby, S. (2007). *RESTful Web Services*. O'Reilly Media.

[2] FastAPI. (2024). FastAPI Documentation. https://fastapi.tiangolo.com/

[3] Docker. (2024). Docker Documentation. https://docs.docker.com/

[4] PostgreSQL Global Development Group. (2024). PostgreSQL 15 Documentation.

[5] Redis. (2024). Redis Documentation. https://redis.io/docs/
