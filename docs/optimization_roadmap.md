# HF CDSS — Optimization Roadmap

Bảng ưu tiên optimize theo kiến trúc hiện tại (ingestion → index → query → verify → explain).
Dùng **Impact** (H/M/L) và **Effort** (H/M/L) để chọn thứ tự làm.

---

## 1. Ma trận tổng hợp (P0 → P2)

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

---

## 2. Ingestion pipeline (offline)

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

## 3. Index bootstrap

| Component | Bottleneck | Quick win | Structural fix |
|-----------|------------|-----------|----------------|
| ChromaDB | Embed all chunks at bootstrap | Skip if `source_sha256` unchanged (đã có) | Incremental upsert from delta manifest |
| Neo4j | Full graph load | Load only published artifacts | Versioned graph + delta relationships |
| Postgres seed | Governance sync | Warm cache at bootstrap (đã có) | Read-through cache in app layer |
| BM25 (runtime) | Index build on first query | Fingerprint cache (đã có) | Persist BM25 index to disk |

**Mục tiêu bootstrap:** < 30 phút sau ingestion mới (736 chunks scale).

---

## 4. Query path (online)

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

## 5. Retrieval quality vs cost

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

## 6. LLM & embedding model strategy

| Use case | Model hiện tại | Optimize option |
|----------|----------------|-----------------|
| Chat explain | qwen2.5:7b | Giữ — quality critical |
| Verification agents | configurable | qwen2.5:7b hoặc rule-only |
| HyDE | same as chat | qwen2.5:1.5b |
| Claim/governance extract | ingestion model | qwen2.5:3b / 1.5b |
| Embeddings | bge-m3 | Giữ; không đổi thường xuyên |

**Nguyên tắc:** model lớn cho clinician-facing; model nhỏ cho extract/index aux tasks.

---

## 7. Hạ tầng & ops

| Item | Action | Priority |
|------|--------|----------|
| Ollama GPU | `nvidia-runtime` + compose deploy | P1 nếu ingestion thường xuyên |
| S3 artifacts | Lifecycle + versioning on processed bucket | P0 data safety |
| Airflow | Email/Slack on task fail + retry count | P1 |
| Metrics | `hf_cdss_retrieval_latency`, verification totals | P1 — dashboard Grafana |
| Redis | Explanation + HyDE cache | P2 |

---

## 8. Kế hoạch thực hiện đề xuất (4 sprint)

### Sprint 1 — Ingestion throughput (P0)
- [ ] O1: Tune regex vs LLM gate + model nhỏ cho extract
- [ ] O2: Embedding batch + cache hit monitoring
- [ ] O3: Verify auto-resume end-to-end trên Airflow

### Sprint 2 — Query latency (P0)
- [ ] O5: Cross-encoder rerank hoặc giảm candidates
- [ ] O6: HyDE conditional gate
- [ ] O7: GraphRAG response cache

### Sprint 3 — Quality calibration (P1)
- [ ] O10: Negative filter eval + threshold tune
- [ ] O8: Verification agent mode defaults
- [ ] O11: Explanation payload slim + Redis

### Sprint 4 — Index & ops (P1/P2)
- [ ] O4: Incremental Chroma upsert
- [ ] O15: Ollama/GPU or split embed service
- [ ] Metrics dashboard

---

## 9. Cách đo success

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

Điền baseline bằng cách chạy một DAG run + 20 chat queries synthetic trước khi optimize.

---

## 10. Tham chiếu code

| Area | Path |
|------|------|
| Ingestion orchestration | `scraper/orchestration/run_ingestion_pipeline.py` |
| Ingestion tuning | `scraper/semantic/config.py` |
| Hybrid retrieval | `backend/app/modules/graphrag/service.py` |
| Chroma candidates | `backend/app/modules/datastores/chroma.py` |
| Verification | `backend/app/modules/verification_agents/service.py` |
| Chat flow | `backend/app/modules/chat/service.py` |
| Prompts (backend) | `backend/app/prompts/` |
| Prompts (scraper) | `scraper/prompts/` |
