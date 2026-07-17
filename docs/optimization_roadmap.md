# HF CDSS — Optimization & Security Roadmap

Bảng ưu tiên optimize theo kiến trúc hiện tại (ingestion → index → query → verify → explain).
Dùng **Impact** (H/M/L) và **Effort** (H/M/L) để chọn thứ tự làm.

---

## MỤC LỤC

1. [Xác nhận thực hiện](#1--xác-nhận-trước-khi-thực-hiện)
2. [Ma trận tổng hợp](#2--ma-trận-tổng-hợp)
3. [Chi tiết Security Issues](#3--chi-tiết-security-issues)
4. [Chi tiết Production Readiness](#4--chi-tiết-production-readiness)
5. [Chi tiết Evaluation Framework](#5--chi-tiết-evaluation-framework)
6. [Ingestion pipeline](#6--ingestion-pipeline-offline)
7. [Index bootstrap](#7--index-bootstrap)
8. [Query path](#7--query-path-online)
9. [Retrieval quality vs cost](#8--retrieval-quality-vs-cost)
10. [LLM & embedding model strategy](#9--llm--embedding-model-strategy)
11. [Hạ tầng & ops](#10--hạ-tầng--ops)
12. [Kế hoạch thực hiện](#11--kế-hoạch-thực-hiện)
13. [Cách đo success](#12--cách-đo-success)
14. [Tham chiếu code](#13--tham-chiếu-code)

---

## 1. XÁC NHẬN TRƯỚC KHI THỰC HIỆN

Đánh dấu `[x]` các item bạn muốn implement. File này sẽ được update sau mỗi buổi confirm.

### S0 — Security (Ưu tiên cao nhất)
- [ ] **S1**: Fix SQL LIKE injection (`_escape_like()`)
- [ ] **S2**: JWT secret fail-fast in production
- [ ] **S3**: PHI redaction in audit logs
- [ ] **S4**: Redis-backed rate limiting
- [ ] **S5**: Input sanitization for LLM calls
- [ ] **S6**: HTTPS cookie enforcement

### S1 — Production Readiness
- [ ] **S7**: Graceful degradation khi LLM unavailable
- [ ] **S8**: Comprehensive health checks (Redis, ChromaDB, Neo4j, S3)
- [ ] **S9**: Idempotency keys for requests
- [ ] **S10**: Retry logic with exponential backoff
- [ ] **S11**: Circuit breakers for external services
- [ ] **S12**: In-memory state → Redis/DB

### P0 — Performance Optimization
- [ ] **O1**: LLM claim extraction — tăng regex coverage + model nhỏ
- [ ] **O2**: Embedding batch + cache
- [ ] **O3**: Pipeline retry checkpoint
- [ ] **O4**: Chroma incremental upsert
- [ ] **O5**: Rerank tối ưu (cross-encoder hoặc giảm candidates)

### P1 — Performance Optimization
- [ ] **O6**: HyDE conditional gate
- [ ] **O7**: GraphRAG cache
- [ ] **O8**: Verification agent mode defaults
- [ ] **O9**: Governance parallel catalogs
- [ ] **O10**: Negative filter tuning
- [ ] **O11**: Explanation payload slim
- [ ] **O15**: Ollama/GPU split

### P2 — Lower Priority
- [ ] **O12**: Prompt consistency
- [ ] **O13**: Neo4j incremental
- [ ] **O14**: Lost-in-the-middle reorder eval

### E0 — Evaluation Framework (User-Requested)
- [ ] **E1**: Evaluation Framework với golden test set (~100 cases)
- [ ] **E2**: Contradiction Detection giữa guidelines
- [ ] **E3**: Dose Ceiling/Floor Safety Check
- [ ] **E4**: RAGAS-style automated evaluation (faithfulness, answer_relevancy)
- [ ] **E5**: Intake extraction confidence gating
- [ ] **E6**: Drug name normalization fuzzy matching + logging
- [ ] **E7**: Prometheus metrics expansion

---

## 2. Ma trận tổng hợp

### 2.1 Security (S0)

| ID | Vấn đề | File | Hiện trạng | Hành động đề xuất | Impact | Effort | Ưu tiên |
|----|---------|------|------------|-------------------|--------|--------|---------|
| S1 | SQL LIKE Injection | `datastores/postgres.py` | `%` và `_` không escape | Thêm `_escape_like()` helper; escape input trước ILIKE | H | L | **S0** |
| S2 | JWT Secret Default | `config.py`, `security_startup.py` | Chỉ warning, không fail | Raise exception/exit trong production nếu secret insecure | H | L | **S0** |
| S3 | PHI Exposure in Logs | `chat/service.py`, `middleware.py` | Audit logs chứa full message | Redact PHI trước khi log; chỉ lưu structured metadata | H | M | **S0** |
| S4 | Rate Limit Bypass | `middleware.py` | In-memory, per-worker | Redis-backed rate limiting | H | M | **S0** |
| S5 | LLM Injection | `clinical_intake_extraction/service.py` | Direct user input to LLM | Input sanitization + prompt isolation | H | M | **S0** |
| S6 | HTTPS Cookie | `config.py` | `jwt_cookie_secure=False` default | Default = True; add production check | M | L | **S0** |

### 2.2 Production Readiness (S1)

| ID | Vấn đề | File | Hiện trạng | Hành động đề xuất | Impact | Effort | Ưu tiên |
|----|---------|------|------------|-------------------|--------|--------|---------|
| S7 | LLM Fail = Hardcoded Fallback | `explanation/llm_service.py` | Vietnamese only | Detect user language; multiple language fallbacks | H | M | **S1** |
| S8 | Missing Health Checks | `api/routes/health.py` | Chỉ basic check | Check Redis, ChromaDB, Neo4j, S3 | M | M | **S1** |
| S9 | No Idempotency | `chat/service.py` | Retry = duplicate | Thêm idempotency key support | M | M | **S1** |
| S10 | No Retry Logic | `core/http_client.py` | Fail immediately | Retry with exponential backoff for external calls | M | M | **S1** |
| S11 | No Circuit Breaker | Global | Fail cascade | Implement circuit breaker pattern | M | M | **S1** |
| S12 | In-Memory State | `chat/service.py:31-32` | `_drafts`, `_messages` global | Move to Redis/DB; add cleanup | M | M | **S1** |

### 2.3 Performance Optimization (P0-P2)

| ID | Pha | Vấn đề / cơ hội | Hiện trạng | Hành động đề xuất | Impact | Effort | Ưu tiên |
|----|-----|-----------------|------------|-------------------|--------|--------|---------|
| O1 | Ingestion | LLM claim extraction chậm (sections × timeout) | Regex trước, LLM fallback; concurrency=2, timeout=45s, cache SQLite | Tăng regex coverage; skip LLM khi ≥N pattern hits; model nhỏ riêng cho extract (`qwen2.5:3b`) | H | M | **P0** |
| O2 | Ingestion | Embedding section filter + semantic chunk | LRU + SQLite cache; batch Ollama `/api/embed` | Pre-warm prototypes; tăng `EMBEDDING_BATCH_SIZE`; dedup MinHash trước embed | H | L | **P0** |
| O3 | Ingestion | Pipeline retry mất progress | Checkpoint + S3 per-step sync + volume mount | Monitor step ETA logs; alert Airflow trước 48h; snapshot S3 sau mỗi major step | H | L | **P0** |
| O4 | Index | Chroma bootstrap embed toàn corpus | Batch upsert tại `initialize_chroma()` | Incremental upsert (delta chunks only); reuse ingestion SQLite cache khi index | H | M | **P0** |
| O5 | Query | Bi-encoder rerank embed N candidates/request | Ollama embed query + N docs mỗi request | Cross-encoder local (MiniLM); hoặc Cohere rerank; giảm `semantic_rerank_candidates` 50→24 | H | M | **P0** |
| O6 | Query | HyDE + multi-query thêm LLM/embed latency | HyDE optional; query decomposition enabled | Gate HyDE: chỉ query phức tạp / thiếu terms; cache HyDE theo query hash | M | L | **P1** |
| O7 | Query | GraphRAG cold path | Prefetch song song với reasoning (đã có trong chat) | Cache GraphRAG `(patient_fingerprint, query)` TTL 5–10 phút | M | M | **P1** |
| O8 | Query | Verification LLM agents | Rule fallback + optional LLM list | Mặc định rule-only; bật LLM agent selective theo `overall_status` | M | L | **P1** |
| O9 | Ingestion | Governance 4× LLM catalogs | extract→generate→classify per catalog | Chạy song song catalogs; share LLM cache; merge steps nếu schema cho phép | M | M | **P1** |
| O10 | Query | Negative filter quá aggressive | `min_quality=0.38`, require patient entity | Tune theo eval set; log rejected chunks để calibrate | M | L | **P1** |
| O11 | Explain | Explanation LLM token lớn | Compact JSON payload (đã có) | Template ngắn hơn; stream sớm; Redis cache câu hỏi lặp | M | L | **P1** |
| O12 | Ingestion | Claim/governance prompt consistency | Few-shot claim prompt; zero-shot catalogs | Few-shot cho dose/interaction prompts; JSON schema validation strict | M | L | **P2** |
| O13 | Index | Neo4j init full rebuild | Batch load từ JSONL | Incremental MERGE; index constraints trên entity_id | L | M | **P2** |
| O14 | Query | Lost-in-the-Middle reorder | Reorder best-first edges | A/B eval: có/không reorder trên explanation quality | L | L | **P2** |
| O15 | Ops | Single Ollama instance bottleneck | Local docker ollama | Queue + rate limit; tách embed server vs chat model; GPU node riêng | H | H | **P1** |

### 2.4 Evaluation Framework (E0)

| ID | Vấn đề | File | Hiện trạng | Hành động đề xuất | Impact | Effort | Ưu tiên |
|----|---------|------|------------|-------------------|--------|--------|---------|
| E1 | Không có Evaluation Framework | `modules/evaluation/` | Trống | Tạo golden test set ~100 cases; run after code changes | H | H | **E0** |
| E2 | Contradiction Detection | `verification_agents/` | Không có | Thêm contradiction detector; LLM answer phải acknowledge | H | M | **E0** |
| E3 | Dose Ceiling/Floor | `dose_safety/` | Đã có constants.py | Implement full check logic | M | M | **E0** |
| E4 | RAGAS Metrics | `modules/evaluation/` | Không có | Thêm faithfulness & answer_relevancy metrics | H | H | **E0** |
| E5 | Confidence Gating | `clinical_intake_extraction/` | Confidence không gate | Critical fields < 0.7 → ask clinician confirm | M | M | **E0** |
| E6 | Drug Normalization Logging | `drug_normalization/service.py` | Có fuzzy nhưng yếu | Improve fuzzy; log unmatched drugs | M | L | **E0** |
| E7 | Prometheus Metrics | `core/metrics.py` | Cơ bản | Thêm verification fail rate, evidence chunk count, LLM timeout rate, recommendation distribution | M | M | **E0** |

---

## 3. Chi tiết Security Issues

### S1: SQL LIKE Injection 🔴 CRITICAL

**File:** `backend/app/modules/datastores/postgres.py`

```python
# Lines ~686-689
conditions.append("target_drug_class ILIKE %s")
params.append(f"%{target_drug_class}%")  # ⚠️ Không escape %, _
```

**Tấn công mẫu:**
```
POST /api/v1/admin/constraints?target_drug_class=%_admin%' OR '1'='1
```

**Fix đề xuất:**
```python
def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

params.append(f"%{_escape_like(target_drug_class)}%")
```

---

### S2: JWT Secret Hardcoded Default 🔴 CRITICAL

**Files:** `backend/app/core/config.py:24`, `backend/app/core/security_startup.py`

```python
# config.py
jwt_secret_key: str = "change-me-in-production"

# security_startup.py
def validate_security_configuration() -> None:
    if settings.environment != "production":
        return  # ⚠️ Chỉ warning, không fail
```

**Vấn đề:** Server vẫn khởi động với insecure secret trong production.

**Fix đề xuất:**
```python
def validate_security_configuration() -> None:
    if settings.environment == "production":
        if settings.jwt_secret_key in INSECURE_JWT_SECRETS:
            logger.error("HF_CDSS_JWT_SECRET_KEY is insecure in production")
            raise SystemExit(1)  # Fail hard
```

---

### S3: PHI Exposure in Audit Logs 🔴 CRITICAL

**File:** `backend/app/modules/chat/service.py:308-320`

```python
write_audit_event(
    merged.case_id,
    "chat_recommendation_completed",
    {
        "message": request.message,  # ⚠️ Full PHI content
        "patient": merged.model_dump(mode="json"),  # ⚠️ Full patient data
        ...
    },
)
```

**Fix đề xuất:** Chỉ lưu structured metadata, redact PHI:
```python
def _safe_audit_payload(case_id: str, event_type: str, patient: PatientProfile, ...) -> dict:
    return {
        "case_id": case_id,
        "event_type": event_type,
        "timestamp": datetime.now().isoformat(),
        "fields_extracted": list(patient.labs.model_dump(exclude_none=True).keys()),
        # Không lưu: message, patient full data
    }
```

---

### S4: In-Memory Rate Limiting Bypass 🟠 HIGH

**File:** `backend/app/core/middleware.py:53-55`

```python
_rate_windows: dict[str, deque[float]] = defaultdict(deque)  # ⚠️ Per-process
```

**Vấn đề:** Multi-worker = bypass rate limit × N workers.

**Fix đề xuất:** Redis-backed rate limiting:
```python
async def _is_rate_limited_redis(request: Request) -> bool:
    key = f"rate_limit:{_client_id(request)}:{request.url.path}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    return count > limit
```

---

### S5: LLM Prompt Injection 🟠 HIGH

**File:** `backend/app/modules/clinical_intake_extraction/service.py:377-379`

```python
"messages": [
    {"role": "system", "content": CLINICAL_INTAKE_SYSTEM_PROMPT},
    {"role": "user", "content": message[:12000]},  # ⚠️ Direct injection
]
```

**Fix đề xuất:**
```python
def _sanitize_llm_input(text: str) -> str:
    # Remove potential prompt injection patterns
    dangerous = ["ignore previous", "disregard", "system prompt", "# Instructions"]
    sanitized = text
    for pattern in dangerous:
        sanitized = re.sub(rf"(?i){re.escape(pattern)}.*$", "", sanitized, flags=re.MULTILINE)
    return sanitized[:12000]
```

---

### S6: HTTPS Cookie Not Enforced 🟠 HIGH

**File:** `backend/app/core/config.py:28`

```python
jwt_cookie_secure: bool = False  # ⚠️ Default không secure
```

**Fix đề xuất:** Default = True, thêm production validation:
```python
if settings.environment == "production" and not settings.jwt_cookie_secure:
    logger.warning("jwt_cookie_secure=False in production - cookies may be intercepted")
```

---

## 4. Chi tiết Production Readiness

### S7: LLM Fail = Hardcoded Vietnamese Fallback

**File:** `backend/app/modules/explanation/llm_service.py`

```python
# Hardcoded Vietnamese fallback
"Kết luận", "Thuốc và liều gợi ý"
```

**Fix đề xuất:** Multi-language fallbacks:
```python
FALLBACK_TEMPLATES = {
    "vi": {"conclusion": "Kết luận", "medications": "Thuốc và liều gợi ý"},
    "en": {"conclusion": "Conclusion", "medications": "Medications and dosages"},
    # ...
}
```

---

### S8: Missing Health Checks

**File:** `backend/app/api/routes/health.py`

Hiện tại chỉ check app alive. Cần thêm:
- Redis connectivity
- ChromaDB availability  
- Neo4j connectivity
- S3/MinIO accessibility

**Fix đề xuất:**
```python
@router.get("/health/ready")
async def readiness_check():
    checks = {
        "postgres": await check_postgres(),
        "redis": await check_redis(),
        "chromadb": await check_chromadb(),
        "neo4j": await check_neo4j(),
        "s3": await check_s3(),
    }
    all_healthy = all(checks.values())
    return JSONResponse({"status": "ok" if all_healthy else "degraded", "checks": checks})
```

---

### S9-S12: Other Production Gaps

| ID | Vấn đề | Chi tiết | Fix đề xuất |
|----|---------|----------|-------------|
| S9 | No Idempotency | Retry = duplicate messages | Thêm `X-Idempotency-Key` header, check trước khi process |
| S10 | No Retry Logic | External calls fail immediately | Thêm retry với exponential backoff |
| S11 | No Circuit Breaker | Fail cascade possible | Implement CB pattern cho Redis, LLM, ChromaDB |
| S12 | In-Memory State | `_drafts`, `_messages` global → lost on restart | Move to Redis, add TTL + cleanup |

---

## 5. Chi tiết Evaluation Framework

### E1: Evaluation Framework

**File:** `backend/app/modules/evaluation/`

**Mục tiêu:** Tạo golden test set ~100 clinical cases để đo accuracy.

**Cấu trúc đề xuất:**
```
backend/app/modules/evaluation/
├── golden_test_set.json    # 100 clinical cases với expected outputs
├── runner.py              # Chạy evaluation
├── metrics.py             # Faithfulness, AnswerRelevancy, etc.
├── faithfulness.py        # Kiểm tra LLM không bịa thông tin
└── answer_relevancy.py    # Kiểm tra câu trả lời có liên quan
```

**Golden case format:**
```json
{
  "case_id": "eval_001",
  "patient_profile": {...},
  "question": "Bệnh nhân có HFREF với EF 30%, eGFR 45...",
  "expected_recommendations": ["Entresto 49/51mg bid", "..."],
  "expected_warnings": ["Chú ý thận suy"],
  "evaluation_notes": "..."
}
```

---

### E2: Contradiction Detection

**Vấn đề:** ESC 2021 vs 2023, ADA vs KDIGO mâu thuẫn về ngưỡng eGFR cho SGLT2i.

**Fix đề xuất:** Thêm contradiction detector trong verification layer:
```python
# backend/app/modules/verification_agents/contradiction.py
async def detect_contradictions(chunks: list[EvidenceChunk]) -> list[Contradiction]:
    """
    Phát hiện mâu thuẫn giữa các guidelines.
    Khi phát hiện → thêm vào verification_result.
    """
    contradictions = []
    # So sánh chunks từ các guidelines khác nhau
    # Nếu cùng topic nhưng khác threshold → contradiction
    return contradictions
```

**LLM prompt cần acknowledge:**
```
"Lưu ý: ESC và ADA có quan điểm khác nhau về ngưỡng eGFR này.
Bác sĩ cần xem xét thêm dựa trên bệnh sử cụ thể."
```

---

### E3: Dose Ceiling/Floor Safety Check

**File:** `backend/app/modules/dose_safety/constants.py`

**Đã tạo** constants.py. Cần implement full logic:

```python
# constants.py
DOSE_CEILING = {
    "Entresto": {"max_daily_mg": 400, "starting_mg": 49},
    "Jardiance": {"max_daily_mg": 25, "starting_mg": 10},
    # ...
}

DOSE_FLOOR = {
    "Lisinopril": {"min_daily_mg": 2.5},
    "Carvedilol": {"min_daily_mg": 3.125},
    # ...
}

def check_dose_safety(prescription: Prescription) -> list[SafetyWarning]:
    warnings = []
    if prescription.daily_dose > DOSE_CEILING.get(prescription.drug, {}).get("max_daily_mg", float('inf')):
        warnings.append(f"Cảnh báo: Liều {prescription.drug} vượt ngưỡng an toàn")
    # ...
    return warnings
```

---

### E4: RAGAS-style Evaluation

**Metrics cần implement:**

| Metric | Mô tả | Implementation |
|--------|-------|---------------|
| Faithfulness | LLM không bịa thông tin | Compare LLM answer vs evidence chunks |
| Answer Relevancy | Câu trả liên quan đến câu hỏi | Compare question vs generated questions from answer |
| Context Precision | Evidence chunks relevant | Precision of retrieved chunks |
| Context Recall | Evidence đầy đủ | Recall of ground truth facts |

---

### E5: Confidence Gating

**Vấn đề:** Confidence thấp (<0.7) nhưng vẫn recommend.

**Fix đề xuất:**
```python
# backend/app/modules/clinical_intake_extraction/service.py
CRITICAL_FIELDS = ["egfr", "lvef", "potassium"]

def check_critical_confidence(extraction_result: ExtractionResult) -> list[str]:
    low_confidence_fields = []
    for field in CRITICAL_FIELDS:
        if extraction_result.confidence.get(field, 1.0) < 0.7:
            low_confidence_fields.append(field)
    return low_confidence_fields

# Trong chat flow:
low_confidence = check_critical_confidence(extraction)
if low_confidence:
    return build_confirmation_prompt(low_confidence)
    # "Tôi không chắc về giá trị eGFR. Bác sĩ có thể xác nhận lại không?"
```

---

### E6: Drug Normalization Improvements

**File:** `backend/app/modules/drug_normalization/service.py`

**Hiện tại:** Có fuzzy matching với threshold 0.75

**Cần cải thiện:**
```python
# Log unmatched drugs để improve catalog
UNMATCHED_DRUGS_LOG = "logs/unmatched_drugs.jsonl"

def normalize_drug_name(value: str | None) -> str | None:
    result = _normalize_with_fuzzy(value)
    if result is None:
        # Log for improvement
        log_unmatched_drug(value)
    return result
```

---

### E7: Prometheus Metrics Expansion

**Cần thêm metrics:**

```python
# backend/app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Verification metrics
verification_fail_rate = Counter(
    'hf_cdss_verification_failures_total',
    'Verification failures by agent',
    ['agent', 'verdict']
)

# Evidence retrieval metrics
evidence_chunk_count = Histogram(
    'hf_cdss_evidence_chunks_retrieved',
    'Number of evidence chunks per query',
    buckets=[1, 3, 5, 8, 10, 15, 20]
)

# LLM metrics
llm_timeout_rate = Counter(
    'hf_cdss_llm_timeouts_total',
    'LLM timeout count',
    ['endpoint']
)

# Recommendation distribution
recommendation_distribution = Counter(
    'hf_cdss_recommendations_total',
    'Recommendation distribution',
    ['drug_class', 'status']  # avoid/caution/recommend
)
```

---

## 6. Ingestion pipeline (offline)

| Step | Bottleneck | Metric theo dõi | Quick win | Structural fix |
|------|------------|-----------------|-----------|----------------|
| Section filter | Embed haystack | embed calls / section | Keyword alias mở rộng | Prototype cache warm at step start |
| Semantic chunk | Embed per block | sec/chunk batch | `SEMANTIC_CHUNK_MIN_TOKENS` ↑ | Skip semantic cho sections ngắn |
| create_claims | LLM per section | sec/section, cache hit % | `CLAIM_LLM_MIN_PATTERN_MATCHES` tune | Batch prompts (multi-section) nếu model hỗ trợ |
| Governance extract | 4× LLM pipelines | wall time per catalog | Parallel catalogs (4 workers) | Unified extraction schema |
| Embedding cache | Disk I/O SQLite | cache hit rate | Default path `data_root/.cache` | Shared cache volume Docker |
| Airflow | Task timeout 48h | step duration logs | `--auto-resume` + S3 restore | Horizontal: split DAG sub-DAGs |

**Mục tiêu ingestion:** full run < 8h trên CPU-only Ollama (hiện có thể 12–24h+ tùy corpus).

---

## 7. Index bootstrap

| Component | Bottleneck | Quick win | Structural fix |
|-----------|------------|-----------|----------------|
| ChromaDB | Embed all chunks at bootstrap | Skip if `source_sha256` unchanged (đã có) | Incremental upsert from delta manifest |
| Neo4j | Full graph load | Load only published artifacts | Versioned graph + delta relationships |
| Postgres seed | Governance sync | Warm cache at bootstrap (đã có) | Read-through cache in app layer |
| BM25 (runtime) | Index build on first query | Fingerprint cache (đã có) | Persist BM25 index to disk |

**Mục tiêu bootstrap:** < 45 phút sau ingestion mới (~2k chunks scale).

---

## 7. Query path (online)

| Stage | Latency driver | Config knobs | Target p95 |
|-------|----------------|--------------|------------|
| Intake LLM | 1 chat call | `llm_model`, cache | < 3s |
| Reasoning | Rule engine | Postgres cache warm | < 200ms |
| GraphRAG hybrid | Chroma + BM25 parallel + RRF | `top_k`, pool_k | < 1.5s |
| Rerank | N × embed | `semantic_rerank_candidates`, Cohere | < 2s |
| HyDE | +1 LLM | `hyde_retrieval_enabled`, min chars | +1–2s if enabled |
| Verification | RAG + agents | `verification_agent_mode`, cache | < 3s |
| Explanation stream | LLM tokens | max tokens, compact payload | TTFB < 2s |

**Mục tiêu end-to-end chat:** p95 < 12s (không HyDE), < 15s (có HyDE).

---

## 8. Retrieval quality vs cost

| Technique | Cost | Quality gain | Khuyến nghị |
|-----------|------|--------------|-------------|
| Chroma + BM25 + RRF | Medium | High (lexical + semantic) | **Giữ — core** |
| HyDE | +LLM | Medium on vague queries | Conditional enable |
| Multi-query decomposition | +Chroma calls | Medium on multi-class | Giữ; cap số queries ≤ 4 |
| Bi-encoder rerank | +N embeds | Medium | Thay cross-encoder hoặc Cohere |
| Entity boosting | Low | High for patient-specific | Giữ; ensure patient passed |
| Negative filter | Low | Reduce noise | Tune threshold on eval set |
| Chunk window expand | Low | Context completeness | `graphrag_chunk_window_size=1` |
| Lost-in-the-Middle | Zero | LLM attention | Giữ enabled |

---

## 9. LLM & embedding model strategy

| Use case | Model hiện tại | Optimize option |
|----------|----------------|-----------------|
| Chat explain | qwen2.5:7b | Giữ — quality critical |
| Verification agents | configurable | qwen2.5:7b hoặc rule-only |
| HyDE | same as chat | qwen2.5:1.5b |
| Claim/governance extract | ingestion model | qwen2.5:3b / 1.5b |
| Embeddings | bge-m3 | Giữ; không đổi thường xuyên |

**Nguyên tắc:** model lớn cho clinician-facing; model nhỏ cho extract/index aux tasks.

---

## 10. Hạ tầng & ops

| Item | Action | Priority |
|------|--------|----------|
| Ollama GPU | `nvidia-runtime` + compose deploy | P1 nếu ingestion thường xuyên |
| S3 artifacts | Lifecycle + versioning on processed bucket | P0 data safety |
| Airflow | Email/Slack on task fail + retry count | P1 |
| Metrics | `hf_cdss_retrieval_latency`, verification totals | P1 — dashboard Grafana |
| Redis | Explanation + HyDE cache | P2 |
| **Security** | SQL injection fix, JWT validation, PHI redaction | **S0** |

---

## 11. Kế hoạch thực hiện

> **Hướng dẫn:** Mỗi sprint, confirm các item bạn muốn làm. Sau khi implement xong, update `[ ]` → `[x]`.

### Sprint 0 — Security Hardening (1-2 tuần)
- [ ] **S1**: Fix SQL LIKE injection
- [ ] **S2**: JWT secret fail-fast
- [ ] **S3**: PHI redaction in audit logs
- [ ] **S4**: Redis-backed rate limiting
- [ ] **S5**: Input sanitization for LLM
- [ ] **S6**: HTTPS cookie enforcement

### Sprint 1 — Production Readiness (2-3 tuần)
- [ ] **S7**: Graceful LLM degradation
- [ ] **S8**: Comprehensive health checks
- [ ] **S9**: Idempotency keys
- [ ] **S10**: Retry logic
- [ ] **S11**: Circuit breakers
- [ ] **S12**: In-memory state → Redis

### Sprint 2 — Ingestion throughput (P0)
- [ ] **O1**: Tune regex vs LLM gate + model nhỏ cho extract
- [ ] **O2**: Embedding batch + cache hit monitoring
- [ ] **O3**: Verify auto-resume end-to-end trên Airflow

### Sprint 3 — Query latency (P0)
- [ ] **O5**: Cross-encoder rerank hoặc giảm candidates
- [ ] **O6**: HyDE conditional gate
- [ ] **O7**: GraphRAG response cache

### Sprint 4 — Quality calibration (P1)
- [ ] **O10**: Negative filter eval + threshold tune
- [ ] **O8**: Verification agent mode defaults
- [ ] **O11**: Explanation payload slim + Redis

### Sprint 5 — Evaluation Framework (E0)
- [ ] **E1**: Evaluation Framework + Golden Test Set
- [ ] **E2**: Contradiction Detection
- [ ] **E4**: RAGAS metrics

### Sprint 6 — Index & ops (P1/P2)
- [ ] **O4**: Incremental Chroma upsert
- [ ] **O15**: Ollama/GPU or split embed service
- [ ] **E3**: Dose Ceiling/Floor
- [ ] **E5**: Confidence Gating
- [ ] **E7**: Prometheus expansion

---

## 12. Cách đo success

| KPI | Baseline (ghi khi đo) | Target |
|-----|----------------------|--------|
| Ingestion wall time | ___ h | < 8h |
| create_claims step | ___ h | < 3h |
| LLM cache hit rate (ingestion) | ___ % | > 60% on retry |
| Embedding cache hit rate | ___ % | > 80% on retry |
| Chat p95 latency | ___ s | < 12s |
| Retrieval p95 | ___ ms | < 1500ms |
| Citation support rate (eval) | ___ % | +5% vs baseline |
| Verification fail rate (false fail) | ___ % | -3% |
| **Security incidents** | 0 | 0 |
| **PHI exposure incidents** | 0 | 0 |

Điền baseline bằng cách chạy một DAG run + 20 chat queries synthetic trước khi optimize.

---

## 13. Tham chiếu code

| Area | Path |
|------|------|
| Ingestion orchestration | `scraper/orchestration/run_ingestion_pipeline.py` |
| Ingestion tuning | `scraper/semantic/config.py` |
| Hybrid retrieval | `backend/app/modules/graphrag/service.py` |
| Chroma candidates | `backend/app/modules/datastores/chroma.py` |
| Verification | `backend/app/modules/verification_agents/service.py` |
| Chat flow | `backend/app/modules/chat/service.py` |
| SQL datastore | `backend/app/modules/datastores/postgres.py` |
| Auth/JWT | `backend/app/core/auth_credentials.py`, `jwt.py` |
| Middleware | `backend/app/core/middleware.py` |
| Prompts (backend) | `backend/app/prompts/` |
| Prompts (scraper) | `scraper/prompts/` |
| Security config | `backend/app/core/config.py`, `security_startup.py` |

---

## 📝 Session Log

| Date | Confirmed Items | Status |
|------|-----------------|--------|
| 2026-07-17 | Initial setup — added S0-S12 security, E1-E7 evaluation, updated matrices | ✅ |
