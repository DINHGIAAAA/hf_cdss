# CLAUDE.md

## Project: Heart Failure Medication Decision Support System

**Tên đề tài:** Xây dựng hệ thống hỗ trợ quyết định sử dụng thuốc trong điều trị suy tim đa bệnh nền dựa trên kiến trúc GraphRAG và Multi-agent Verification.

**Thời gian triển khai:** 12 tuần / 3 tháng  
**Định hướng:** Modular Monolith triển khai thực tế trong luận văn, nhưng thiết kế theo hướng Microservices full-scale.  
**Mục tiêu:** Có sản phẩm demo, có dữ liệu đánh giá, có kiến trúc rõ ràng, có báo cáo luận văn và slide bảo vệ chất lượng cao.

---

## 1. Vai trò của Claude Code trong dự án

Claude Code đóng vai trò như AI coding assistant, hỗ trợ:

1. Sinh code backend/frontend theo task được giao.
2. Refactor code theo kiến trúc module.
3. Viết test case.
4. Sinh dữ liệu synthetic patient cases.
5. Viết script ingestion guideline.
6. Viết script build Knowledge Graph.
7. Viết prompt cho GraphRAG và Multi-agent Verification.
8. Viết tài liệu kỹ thuật.
9. Hỗ trợ chuẩn bị báo cáo, slide và demo.

Claude Code **không được tự ý mở rộng scope y khoa ngoài phạm vi luận văn** nếu không có yêu cầu rõ ràng.

---

## 2. Mục tiêu sản phẩm sau 3 tháng

Sau 12 tuần, hệ thống cần có:

### 2.1 Chức năng chính

- Nhập hồ sơ bệnh nhân suy tim.
- Chuẩn hóa dữ liệu lâm sàng: EF, eGFR, K+, SBP, HR, bệnh nền, thuốc đang dùng.
- Phân loại bệnh nhân: HFrEF / HFmrEF / HFpEF ở mức cơ bản.
- Trích xuất risk flags: renal impairment, hyperkalemia, hypotension, bradycardia, diabetes, CKD, polypharmacy.
- Sinh clinical constraints cá thể hóa.
- Truy xuất tri thức từ Knowledge Graph.
- Truy xuất guideline/drug label bằng Vector Search.
- Kết hợp Graph + Vector thành GraphRAG context.
- Sinh khuyến nghị sử dụng thuốc bằng LLM theo constraint.
- Kiểm chứng output bằng nhiều agent:
  - Safety Agent
  - Dose Agent
  - Interaction Agent
  - Guideline Agent
  - Evidence Agent
  - Final Reviewer Agent
- Hiển thị kết quả cho bác sĩ:
  - Recommend / Consider / Caution / Avoid
  - Lý do
  - Evidence
  - Constraint vi phạm hoặc cảnh báo
  - Reasoning path
- Lưu audit log.
- Có dashboard demo.

### 2.2 Chất lượng nghiên cứu

- Có baseline GPT-only.
- Có RAG-only.
- Có GraphRAG.
- Có GraphRAG + Constraint.
- Có Full System + Multi-agent Verification.
- Có synthetic dataset tối thiểu 100 case.
- Có 20 adversarial cases.
- Có gold labels dạng rule-based/expert-inspired.
- Có bảng metric.
- Có ablation study.
- Có phân tích lỗi.

---

## 3. Scope y khoa trong luận văn

### 3.1 Bệnh chính

Tập trung vào suy tim, ưu tiên HFrEF.

### 3.2 Nhóm thuốc chính

Hệ thống tập trung vào các nhóm thuốc GDMT chính:

1. ACEi
2. ARB
3. ARNI
4. Beta-blocker
5. MRA
6. SGLT2 inhibitor
7. Loop diuretic
8. Hydralazine/nitrate ở mức mở rộng
9. Ivabradine ở mức mở rộng
10. Digoxin ở mức cảnh báo/tương tác cơ bản

### 3.3 Bệnh nền cần xét

- Chronic Kidney Disease
- Diabetes Mellitus
- Hypertension
- Atrial Fibrillation
- Hyperkalemia
- Hypotension
- Bradycardia
- COPD/Asthma ở mức cảnh báo beta-blocker

### 3.4 Chỉ số lâm sàng cần dùng

- LVEF
- eGFR
- Creatinine
- Potassium
- Systolic blood pressure
- Heart rate
- NYHA class
- Current medications
- Allergy

### 3.5 Giới hạn an toàn

Hệ thống chỉ là clinical decision support, không thay thế bác sĩ. Mọi output phải có cảnh báo:

> This recommendation is for clinical decision support only and must be reviewed by a licensed physician.

---

## 4. Kiến trúc triển khai trong 3 tháng

Triển khai theo Modular Monolith để kịp tiến độ, nhưng chia module giống microservices.

```text
frontend/
  doctor-dashboard/

backend/
  app/
    api/
    core/
    modules/
      patient/
      clinical_normalization/
      risk_extraction/
      constraint_builder/
      knowledge_graph/
      vector_retrieval/
      graphrag/
      reasoning/
      dose_checking/
      interaction_checking/
      verification_agents/
      explanation/
      audit/
      evaluation/
    schemas/
    tests/

data/
  raw/
  processed/
  synthetic_cases/
  gold_labels/
  guideline_chunks/
  kg_seed/

infrastructure/
  docker-compose.yml
  neo4j/
  chromadb/
  postgres/

docs/
  architecture.md
  api_spec.md
  thesis_notes.md
  evaluation_report.md
```

---

## 5. Công nghệ đề xuất

### Backend

- Python 3.11+
- FastAPI
- Pydantic
- SQLAlchemy
- PostgreSQL hoặc SQLite cho MVP
- Neo4j
- ChromaDB hoặc FAISS
- Redis optional

### Frontend

- React hoặc Next.js
- TailwindCSS
- shadcn/ui nếu dùng React hiện đại
- Axios / TanStack Query

### LLM / RAG

- OpenAI API hoặc model local tùy điều kiện
- LangChain hoặc LlamaIndex nếu cần orchestration
- Có thể tự viết pipeline nếu muốn kiểm soát tốt hơn

### Evaluation

- Python scripts
- pandas
- scikit-learn
- pytest
- matplotlib

### Deployment

- Docker
- Docker Compose
- Kubernetes chỉ thiết kế trong báo cáo, không bắt buộc triển khai thật.

---

## 6. Nguyên tắc code

1. Tất cả response API phải dùng Pydantic schema.
2. Không hardcode logic y khoa trong controller.
3. Logic y khoa phải nằm trong clinical modules hoặc rule files.
4. Mỗi module phải có README ngắn.
5. Mỗi module quan trọng phải có unit test.
6. Mọi recommendation phải có evidence hoặc constraint reference.
7. Không sinh output y khoa không có căn cứ.
8. Output của reasoning phải là JSON có cấu trúc.
9. Agent verification phải có pass/fail/warning rõ ràng.
10. Audit log phải lưu input, context, output, agent results.

---

## 7. Output chuẩn của API /recommend

```json
{
  "case_id": "CASE_001",
  "patient_summary": {
    "hf_type": "HFrEF",
    "lvef": 30,
    "egfr": 28,
    "potassium": 5.4,
    "sbp": 92,
    "heart_rate": 58,
    "comorbidities": ["CKD", "Diabetes"]
  },
  "risk_flags": [
    {
      "name": "renal_impairment",
      "severity": "high",
      "evidence": "eGFR = 28"
    }
  ],
  "constraints": {
    "hard_constraints": [],
    "soft_constraints": [],
    "dose_constraints": [],
    "monitoring_constraints": []
  },
  "recommendations": [
    {
      "drug_class": "MRA",
      "status": "avoid",
      "reason": "High hyperkalemia and renal impairment risk",
      "evidence_ids": ["AHA_2022_MRA_001"],
      "constraint_ids": ["HC_MRA_EGFR_K"]
    }
  ],
  "verification": {
    "overall_status": "approved_with_warnings",
    "agents": []
  },
  "explanation": {
    "summary": "...",
    "reasoning_path": [],
    "evidence_trace": []
  },
  "disclaimer": "Clinical decision support only. Physician review required."
}
```

---

# 8. Roadmap 12 tuần bản nâng cấp công việc nhiều hơn

## Tuần 1: Chốt scope, thiết kế hệ thống, chuẩn bị nền tảng

### Mục tiêu

Tạo nền móng chắc cho toàn bộ dự án. Tuần này phải ra được tài liệu thiết kế, repo, skeleton backend/frontend và schema dữ liệu ban đầu.

### Công việc kỹ thuật

- Tạo repository chính.
- Tạo cấu trúc thư mục chuẩn.
- Tạo backend FastAPI skeleton.
- Tạo frontend dashboard skeleton.
- Tạo docker-compose ban đầu gồm:
  - backend
  - frontend
  - postgres/sqlite
  - neo4j
  - chromadb
- Tạo file `.env.example`.
- Tạo health check API.
- Tạo API `/version`.
- Tạo API `/health`.
- Tạo config management.
- Tạo logging cơ bản.
- Tạo error response format chuẩn.

### Công việc dữ liệu

- Chốt patient schema.
- Chốt medication schema.
- Chốt observation schema.
- Chốt diagnosis schema.
- Chốt recommendation schema.
- Tạo 10 patient cases mẫu thủ công.

### Công việc nghiên cứu

- Tổng hợp phạm vi guideline cần dùng.
- Tạo danh sách nhóm thuốc GDMT.
- Tạo danh sách bệnh nền trọng tâm.
- Tạo bảng rủi ro lâm sàng cần kiểm tra.

### Công việc báo cáo

- Viết nháp Chương 1:
  - Lý do chọn đề tài.
  - Mục tiêu.
  - Phạm vi.
  - Đối tượng nghiên cứu.
  - Phương pháp thực hiện.
- Viết nháp Chương 3 phần tổng quan kiến trúc.

### Công việc kiểm thử

- Test backend chạy được.
- Test frontend gọi được `/health`.
- Test docker-compose up/down.

### Deliverables cuối tuần

- Repo chạy được local.
- Backend skeleton.
- Frontend skeleton.
- Docker Compose bản đầu.
- `docs/architecture.md` bản v1.
- `docs/data_schema.md` bản v1.
- 10 sample patient cases.

### Definition of Done

- Chạy một lệnh có thể start toàn bộ hệ thống.
- Mở browser thấy dashboard trống.
- Gọi API health thành công.
- Có tài liệu kiến trúc tối thiểu 5 trang markdown.

---

## Tuần 2: Clinical normalization, risk extraction và constraint rules v1

### Mục tiêu

Biến dữ liệu bệnh nhân thô thành clinical profile có risk flags và constraints.

### Công việc kỹ thuật

- Xây module `clinical_normalization`.
- Xây module `risk_extraction`.
- Xây module `constraint_builder`.
- Tạo rule engine đơn giản dạng YAML/JSON.
- Tạo API `/normalize`.
- Tạo API `/risks`.
- Tạo API `/constraints`.
- Tạo service function:
  - classify_hf_type
  - classify_renal_status
  - classify_potassium_status
  - classify_bp_status
  - classify_hr_status
  - detect_polypharmacy
- Tạo Pydantic schema cho normalized profile.

### Công việc y khoa/rule

- Viết rule cho HFrEF theo LVEF.
- Viết rule cho CKD theo eGFR mức cơ bản.
- Viết rule hyperkalemia theo potassium.
- Viết rule hypotension theo SBP.
- Viết rule bradycardia theo HR.
- Viết hard constraint cho MRA khi eGFR thấp hoặc K+ cao.
- Viết caution constraint cho ARNI/ACEi/ARB khi SBP thấp hoặc K+ cao.
- Viết caution constraint cho beta-blocker khi HR thấp.
- Viết monitoring constraint cho RAASi/MRA.

### Công việc dữ liệu

- Tạo 30 synthetic cases bao phủ:
  - HFrEF bình thường.
  - HFrEF + CKD.
  - HFrEF + hyperkalemia.
  - HFrEF + hypotension.
  - HFrEF + bradycardia.
  - HFrEF + diabetes.
  - HFrEF + polypharmacy.
- Gắn expected risks cho 30 case.

### Công việc kiểm thử

- Unit test cho normalization.
- Unit test cho risk extraction.
- Unit test cho constraint builder.
- Test edge cases:
  - Missing eGFR.
  - Missing potassium.
  - LVEF null.
  - Medication list empty.
  - Extremely abnormal values.

### Công việc báo cáo

- Viết phần Clinical Constraint Modeling.
- Vẽ bảng phân loại constraint:
  - Hard
  - Soft
  - Dose
  - Monitoring
- Viết ví dụ case minh họa constraint.

### Deliverables cuối tuần

- Module normalization chạy ổn.
- Module risk extraction chạy ổn.
- Module constraint builder v1.
- 30 synthetic cases.
- 30 expected risk labels.
- 15+ unit tests.

### Definition of Done

- API nhận patient JSON và trả normalized profile + risks + constraints.
- Test pass tối thiểu 80% cho module clinical.
- Có ví dụ output JSON rõ ràng trong docs.

---

## Tuần 3: Knowledge Graph v1 với Neo4j

### Mục tiêu

Xây dựng tri thức có cấu trúc giữa bệnh, thuốc, chống chỉ định, cảnh báo, tương tác và guideline recommendation.

### Công việc kỹ thuật

- Thiết kế Neo4j schema.
- Tạo script seed KG.
- Tạo module `knowledge_graph`.
- Tạo Neo4j connection manager.
- Tạo repository/query layer.
- Tạo API `/kg/drug-classes`.
- Tạo API `/kg/recommendations/{hf_type}`.
- Tạo API `/kg/constraints/{drug_class}`.
- Tạo API `/kg/interactions`.
- Tạo graph query cho patient context.

### Graph nodes cần có

- Disease
- HeartFailureType
- Comorbidity
- DrugClass
- Drug
- LabCondition
- Contraindication
- Caution
- DoseRule
- Interaction
- Guideline
- Evidence

### Relationships cần có

- TREATS
- RECOMMENDED_FOR
- CONTRAINDICATED_IN
- CAUTION_IN
- HAS_DOSE_RULE
- INTERACTS_WITH
- SUPPORTED_BY
- HAS_RISK
- REQUIRES_MONITORING

### Công việc dữ liệu

- Seed tối thiểu:
  - 3 HF types.
  - 8 drug classes.
  - 20 individual drugs.
  - 10 comorbidities/risk conditions.
  - 20 contraindication/caution relationships.
  - 15 dose/monitoring rules.
  - 10 interaction rules.

### Công việc kiểm thử

- Test Neo4j connection.
- Test seed script idempotent.
- Test query recommended drug classes for HFrEF.
- Test query contraindications for MRA.
- Test graph path từ patient risk sang drug caution.

### Công việc báo cáo

- Viết phần Knowledge Graph Design.
- Vẽ graph schema.
- Viết ví dụ reasoning path:
  - Patient → HFrEF → GDMT → MRA
  - Patient → eGFR thấp/K cao → hyperkalemia risk → avoid MRA

### Deliverables cuối tuần

- Neo4j chạy trong docker.
- KG seed script.
- Graph query API.
- Docs graph schema.
- 10 Cypher query mẫu.

### Definition of Done

- Query được danh sách thuốc theo HFrEF.
- Query được contraindication/caution theo patient risks.
- Có ảnh/sơ đồ graph để đưa vào báo cáo/slide.

---

## Tuần 4: Guideline ingestion, chunking và Vector Search v1

### Mục tiêu

Tạo pipeline đưa guideline/drug knowledge vào vector database để phục vụ RAG.

### Công việc kỹ thuật

- Tạo module `vector_retrieval`.
- Tạo pipeline ingest tài liệu markdown/text/PDF đã trích xuất.
- Tạo chunking strategy.
- Tạo metadata schema cho guideline chunks.
- Tạo embedding script.
- Tạo ChromaDB collection.
- Tạo API `/retrieval/search`.
- Tạo API `/retrieval/context`.
- Tạo function hybrid retrieval đơn giản:
  - semantic similarity
  - metadata filter
  - keyword boost

### Công việc dữ liệu

- Chuẩn bị tài liệu guideline dạng text/markdown.
- Tách guideline theo nhóm:
  - HFrEF general treatment.
  - ACEi/ARB/ARNI.
  - Beta-blocker.
  - MRA.
  - SGLT2i.
  - Diuretics.
  - CKD caution.
  - Hyperkalemia caution.
  - Hypotension caution.
- Mỗi chunk phải có metadata:
  - source
  - version
  - section
  - drug_class
  - condition
  - evidence_level nếu có
  - chunk_id

### Công việc kiểm thử

- Test search query:
  - HFrEF GDMT
  - MRA hyperkalemia eGFR potassium
  - ARNI low blood pressure
  - SGLT2i renal function
  - beta blocker bradycardia
- Đánh giá retrieval thủ công top-k.
- Ghi lại top-k relevant/not relevant.

### Công việc báo cáo

- Viết phần Guideline Ingestion Pipeline.
- Viết phần Vector Retrieval.
- Vẽ pipeline:
  - raw guideline → cleaning → chunking → embedding → vector db.

### Deliverables cuối tuần

- ChromaDB/FAISS chạy được.
- Có ít nhất 50 guideline chunks.
- Retrieval API hoạt động.
- Bảng test retrieval top-5 cho 10 query.

### Definition of Done

- Query y khoa trả về chunks liên quan.
- Chunk có metadata rõ ràng.
- Có thể lọc theo drug class/source.

---

## Tuần 5: GraphRAG Orchestrator v1

### Mục tiêu

Kết hợp patient context + constraints + graph facts + vector evidence thành unified context cho reasoning.

### Công việc kỹ thuật

- Tạo module `graphrag`.
- Tạo GraphRAG Orchestrator.
- Pipeline:
  1. Nhận patient case.
  2. Normalize.
  3. Extract risks.
  4. Build constraints.
  5. Query KG.
  6. Query Vector DB.
  7. Merge context.
  8. Remove duplicate evidence.
  9. Rank evidence.
  10. Return unified context.
- Tạo API `/graphrag/context`.
- Tạo structured context schema.
- Tạo context compression cơ bản.

### Công việc prompt/context

- Thiết kế format context cho LLM.
- Tách rõ:
  - patient_summary
  - constraints
  - graph_facts
  - retrieved_evidence
  - missing_data
  - safety_notes

### Công việc dữ liệu

- Test GraphRAG trên 30 case.
- Ghi lại retrieved graph facts và guideline chunks.
- Tạo file debug context cho từng case.

### Công việc kiểm thử

- Test GraphRAG không mất constraint.
- Test case có MRA risk phải retrieve MRA evidence.
- Test case có hypotension phải retrieve ARNI/RAAS caution.
- Test case có bradycardia phải retrieve beta-blocker caution.

### Công việc báo cáo

- Viết phần GraphRAG workflow.
- Viết giải thích vì sao cần kết hợp KG + Vector.
- Vẽ luồng GraphRAG.

### Deliverables cuối tuần

- GraphRAG context builder.
- API `/graphrag/context`.
- 30 debug context files.
- Docs GraphRAG workflow.

### Definition of Done

- Với một patient case, hệ thống trả đầy đủ patient summary, risks, constraints, graph facts, guideline evidence.
- Có thể dùng context này cho LLM reasoning ở tuần 6.

---

## Tuần 6: Constraint-aware Reasoning Engine v1

### Mục tiêu

Sinh khuyến nghị thuốc có cấu trúc, có constraint, có evidence và không vi phạm hard constraints.

### Công việc kỹ thuật

- Tạo module `reasoning`.
- Tạo prompt template cho constraint-aware reasoning.
- Tạo output parser JSON.
- Tạo retry nếu JSON invalid.
- Tạo candidate drug generation.
- Tạo ranking rule đơn giản.
- Tạo API `/recommend` bản v1.
- Tạo fallback nếu LLM lỗi.
- Tạo validation layer cho output.

### Output cần sinh

- drug_class
- status: recommend / consider / caution / avoid / insufficient_data
- reason
- evidence_ids
- constraint_ids
- monitoring_required
- physician_review_required

### Công việc y khoa/rule

- Hard constraint phải override LLM.
- Nếu LLM recommend thuốc bị hard constraint, hệ thống phải chuyển thành avoid hoặc flag violation.
- Nếu thiếu dữ liệu quan trọng, output phải là insufficient_data/caution.

### Công việc kiểm thử

- Test 30 cases.
- Test JSON validity.
- Test no hard constraint violation.
- Test evidence IDs có tồn tại trong retrieved context.
- Test missing data behavior.

### Công việc báo cáo

- Viết phần Constraint-aware Reasoning.
- Trình bày prompt strategy.
- Trình bày structured output.

### Deliverables cuối tuần

- `/recommend` v1 chạy được.
- Sinh recommendation có JSON chuẩn.
- 30 case có output.
- Log lại input/context/output.

### Definition of Done

- Ít nhất 90% output là valid JSON.
- Không có recommendation trực tiếp vi phạm hard constraint sau validation.
- Có evidence trace cho từng recommendation chính.

---

## Tuần 7: Dose Checking và Drug Interaction Service

### Mục tiêu

Tăng chất lượng y khoa bằng kiểm tra liều và tương tác thuốc/bệnh/xét nghiệm.

### Công việc kỹ thuật

- Tạo module `dose_checking`.
- Tạo module `interaction_checking`.
- Tạo rule file cho dose warnings.
- Tạo rule file cho interaction warnings.
- Tạo API `/dose/check`.
- Tạo API `/interaction/check`.
- Tích hợp dose + interaction vào `/recommend`.
- Tạo severity scoring:
  - low
  - medium
  - high
  - critical

### Rules cần có

- MRA + eGFR thấp/K cao → avoid/hold warning.
- ACEi/ARB/ARNI + K cao → hyperkalemia monitoring/caution.
- ACEi/ARB/ARNI + SBP thấp → hypotension caution.
- Beta-blocker + HR thấp → bradycardia caution.
- Loop diuretic → monitor electrolytes/renal function.
- Digoxin + renal impairment → dose caution.
- ACEi + ARB combination → avoid combination warning.
- RAASi + MRA + K cao → high hyperkalemia risk.

### Công việc dữ liệu

- Mở rộng synthetic dataset lên 60 cases.
- Tạo 10 cases tương tác thuốc.
- Tạo 10 cases dose caution.

### Công việc kiểm thử

- Unit test dose rules.
- Unit test interaction rules.
- Test severity sorting.
- Test recommendation có interaction warnings.

### Công việc báo cáo

- Viết phần Dose Adjustment Engine.
- Viết phần Drug Interaction Checker.
- Nêu rõ phạm vi giới hạn: chỉ kiểm tra các nhóm thuốc trọng tâm trong HFrEF.

### Deliverables cuối tuần

- Dose Checking module.
- Interaction Checking module.
- 60 cases.
- 20 new tests.
- Recommendation output có dose/interactions.

### Definition of Done

- Hệ thống phát hiện được ít nhất các interaction/risk chính đã định nghĩa.
- Output phân biệt rõ avoid/caution/monitoring.

---

## Tuần 8: Multi-agent Verification v1

### Mục tiêu

Xây dựng lớp kiểm chứng đa tác nhân để giảm hallucination và tăng độ an toàn.

### Công việc kỹ thuật

- Tạo module `verification_agents`.
- Tạo base agent interface.
- Tạo các agent:
  - SafetyAgent
  - DoseAgent
  - InteractionAgent
  - GuidelineAgent
  - EvidenceAgent
  - FinalReviewerAgent
- Mỗi agent nhận:
  - patient profile
  - constraints
  - retrieved evidence
  - recommendation draft
- Mỗi agent trả:
  - status: pass / warning / fail
  - issues
  - severity
  - suggested_revision
- Tạo agent aggregator.
- Tạo rule:
  - any critical/high hard violation → reject/revise
  - evidence missing → warning/fail tùy mức độ
  - only soft warning → approve_with_warnings
- Tích hợp vào `/recommend`.

### Công việc prompt

- Viết prompt riêng cho từng agent.
- Agent không được sinh khuyến nghị mới tùy tiện.
- Agent chỉ được verify dựa trên context.
- Final Reviewer tổng hợp, không thay thế bác sĩ.

### Công việc dữ liệu

- Mở rộng synthetic dataset lên 80 cases.
- Tạo 15 adversarial cases:
  - K+ rất cao nhưng LLM recommend MRA.
  - eGFR rất thấp nhưng recommend MRA/digoxin không caution.
  - SBP rất thấp nhưng recommend ARNI mạnh.
  - HR thấp nhưng recommend beta-blocker tăng liều.
  - Evidence thiếu nhưng claim chắc chắn.

### Công việc kiểm thử

- Test từng agent độc lập.
- Test aggregator.
- Test adversarial cases.
- Test agent disagreement.
- Test revision mechanism.

### Công việc báo cáo

- Viết phần Multi-agent Verification.
- Vẽ luồng agents.
- Viết bảng vai trò từng agent.
- Viết rule tổng hợp kết quả.

### Deliverables cuối tuần

- Multi-agent Verification v1.
- 80 synthetic cases.
- 15 adversarial cases.
- Agent output JSON chuẩn.
- `/recommend` có verification_result.

### Definition of Done

- SafetyAgent bắt được hard constraint violation.
- EvidenceAgent bắt được recommendation không có evidence.
- FinalReviewer có overall_status rõ ràng.

---

## Tuần 9: Frontend Dashboard, Explanation và Audit Log

### Mục tiêu

Hoàn thiện giao diện demo cho bác sĩ và khả năng giải thích/truy vết.

### Công việc frontend

- Tạo patient input form:
  - age
  - sex
  - LVEF
  - eGFR
  - potassium
  - SBP
  - HR
  - NYHA
  - comorbidities
  - current medications
- Tạo recommendation panel.
- Tạo risk flags panel.
- Tạo constraints panel.
- Tạo evidence panel.
- Tạo agent verification panel.
- Tạo reasoning path panel.
- Tạo audit/debug panel cho demo.
- Tạo sample case loader.
- Tạo UI trạng thái loading/error.

### Công việc backend

- Tạo module `explanation`.
- Tạo module `audit`.
- Lưu audit log:
  - request
  - normalized profile
  - constraints
  - graph facts
  - retrieved chunks
  - LLM output
  - agent output
  - final output
- Tạo API `/audit/{case_id}`.
- Tạo API `/cases/sample`.
- Tạo API `/cases/{case_id}/explanation`.

### Công việc explanation

- Sinh final summary.
- Sinh reasoning path dạng bullet.
- Sinh evidence trace.
- Sinh warning summary.
- Sinh missing data summary.

### Công việc dữ liệu

- Mở rộng dataset lên 100 synthetic cases.
- Tạo 20 adversarial cases.
- Tạo 10 demo cases đẹp cho presentation.

### Công việc kiểm thử

- E2E test từ frontend nhập case đến backend trả recommendation.
- Test audit log được lưu.
- Test sample case loader.
- Test UI không crash khi thiếu data.

### Công việc báo cáo

- Viết phần Explainability.
- Viết phần Auditability.
- Chụp màn hình giao diện đưa vào báo cáo.

### Deliverables cuối tuần

- Dashboard demo usable.
- Explanation output.
- Audit log.
- 100 synthetic cases.
- 20 adversarial cases.
- 10 demo cases.

### Definition of Done

- Có thể demo end-to-end bằng UI.
- Bấm một sample case và nhận recommendation + evidence + agents.
- Audit log truy xuất được theo case_id.

---

## Tuần 10: Evaluation pipeline và ablation study

### Mục tiêu

Tạo phần đánh giá thực nghiệm đủ mạnh để luận văn có giá trị nghiên cứu.

### Công việc kỹ thuật

- Tạo module `evaluation`.
- Tạo script run evaluation.
- Tạo các mode:
  - GPT-only
  - RAG-only
  - GraphRAG
  - GraphRAG + Constraint
  - Full System
- Tạo metric calculator.
- Tạo report generator.
- Tạo confusion matrix cho constraint detection nếu phù hợp.
- Tạo CSV/JSON result.

### Metrics cần tính

- Safety violation rate.
- Contraindication detection accuracy/F1.
- Guideline adherence score.
- Evidence coverage.
- Retrieval Precision@k.
- Retrieval Recall@k nếu có gold evidence.
- Agent detection rate.
- JSON validity rate.
- Latency trung bình.
- Recommendation completeness.

### Công việc dữ liệu

- Hoàn thiện gold labels cho 100 synthetic cases.
- Gold label gồm:
  - expected risks
  - expected avoid drug classes
  - expected caution drug classes
  - expected monitoring
  - expected evidence topic
- Chạy evaluation toàn bộ 5 mode.

### Công việc phân tích

- So sánh baseline GPT-only với full system.
- Phân tích lỗi:
  - lỗi retrieval
  - lỗi reasoning
  - lỗi missing data
  - lỗi agent false positive/false negative
- Chọn 5 case điển hình để trình bày.

### Công việc báo cáo

- Viết Chương 4 phần Evaluation Setup.
- Viết bảng dataset.
- Viết bảng metrics.
- Viết bảng kết quả ablation.
- Viết phần error analysis.

### Deliverables cuối tuần

- Evaluation script.
- Kết quả ablation study.
- File `evaluation_report.md`.
- Bảng kết quả CSV.
- Biểu đồ đơn giản.

### Definition of Done

- Chạy một lệnh ra evaluation report.
- Có bảng chứng minh GraphRAG + Constraint + Agents giảm safety violation so với GPT-only.
- Có ít nhất 3 biểu đồ/bảng dùng cho báo cáo.

---

## Tuần 11: Hoàn thiện hệ thống, refactor, test, viết báo cáo chính

### Mục tiêu

Biến prototype thành sản phẩm demo ổn định và báo cáo luận văn gần hoàn chỉnh.

### Công việc kỹ thuật

- Refactor code.
- Chuẩn hóa folder structure.
- Chuẩn hóa naming.
- Thêm docstring cho module quan trọng.
- Thêm error handling.
- Thêm validation input.
- Thêm seed/reset script.
- Thêm `Makefile` hoặc scripts:
  - start
  - stop
  - test
  - seed
  - evaluate
- Tối ưu latency nếu quá chậm.
- Cache retrieval nếu cần.
- Đóng gói demo cases.

### Công việc test

- Unit test cho module critical.
- Integration test cho `/recommend`.
- E2E test demo flow.
- Test docker setup trên máy sạch.
- Test 10 demo cases nhiều lần.
- Test lỗi thiếu service Neo4j/Chroma.

### Công việc báo cáo

Hoàn thiện bản nháp:

- Chương 1: Giới thiệu.
- Chương 2: Cơ sở lý thuyết.
  - Heart failure.
  - GDMT.
  - RAG.
  - Knowledge Graph.
  - GraphRAG.
  - Clinical constraints.
  - Multi-agent verification.
- Chương 3: Phân tích và thiết kế hệ thống.
  - Architecture.
  - Data model.
  - KG design.
  - RAG design.
  - Agents.
  - Microservice full-scale design.
- Chương 4: Cài đặt và đánh giá.
- Chương 5: Kết luận và hướng phát triển.

### Công việc tài liệu kỹ thuật

- Viết README.
- Viết API spec.
- Viết setup guide.
- Viết demo script.
- Viết troubleshooting guide.

### Deliverables cuối tuần

- System stable v1.0.
- Báo cáo luận văn draft 80-90%.
- README hoàn chỉnh.
- API docs.
- Demo script.

### Definition of Done

- Người khác clone repo và chạy được theo README.
- Demo flow không lỗi với 10 sample cases.
- Báo cáo đã có đầy đủ hình, bảng và kết quả chính.

---

## Tuần 12: Slide, demo, polish và chuẩn bị phản biện

### Mục tiêu

Chuẩn bị bảo vệ: slide đẹp, demo chắc, câu trả lời phản biện tốt.

### Công việc slide

Tạo slide gồm:

1. Title.
2. Problem statement.
3. Motivation.
4. Research objectives.
5. Scope.
6. Background: Heart failure + GDMT.
7. Challenge: multimorbidity + medication safety.
8. Proposed architecture.
9. Data architecture.
10. Knowledge Graph design.
11. Vector retrieval design.
12. GraphRAG workflow.
13. Constraint-aware reasoning.
14. Multi-agent verification.
15. Demo UI.
16. Evaluation dataset.
17. Ablation study.
18. Results.
19. Error analysis.
20. Limitations.
21. Future work.
22. Conclusion.

### Công việc demo

- Chuẩn bị 3 demo scenarios:
  1. HFrEF không có rủi ro lớn → recommend GDMT.
  2. HFrEF + CKD + K cao → avoid/caution MRA/RAASi.
  3. HFrEF + hypotension/bradycardia/polypharmacy → nhiều warning + agent verification.
- Viết demo script từng bước.
- Ghi video demo dự phòng.
- Chuẩn bị screenshot dự phòng nếu mạng/API lỗi.

### Công việc phản biện

Chuẩn bị trả lời các câu hỏi:

- Vì sao dùng GraphRAG thay vì RAG thường?
- Vì sao cần Knowledge Graph?
- Vì sao cần Multi-agent Verification?
- Dữ liệu lấy từ đâu?
- Hệ thống có thay bác sĩ không?
- Làm sao đảm bảo an toàn?
- Full-scale data nghĩa là gì?
- Có làm microservice thật không?
- Giới hạn của đề tài là gì?
- Nếu guideline thay đổi thì cập nhật thế nào?
- Nếu bệnh nhân thiếu dữ liệu thì hệ thống xử lý ra sao?

### Công việc polish

- Sửa UI cho đẹp.
- Làm màu risk severity.
- Làm badge status.
- Làm bảng recommendation dễ đọc.
- Làm graph/path visualization nếu kịp.
- Sửa typo trong report.
- Đồng bộ thuật ngữ trong báo cáo và slide.

### Deliverables cuối tuần

- Slide final.
- Report final.
- Demo video.
- Demo script.
- Q&A document.
- Source code cleaned.

### Definition of Done

- Có thể trình bày 10-15 phút mạch lạc.
- Demo chạy được hoặc có video backup.
- Có câu trả lời cho ít nhất 20 câu hỏi phản biện.

---

# 9. Checklist công việc lặp lại mỗi tuần

Mỗi tuần phải làm đủ 5 nhóm việc sau:

## 9.1 Development

- Implement feature chính của tuần.
- Viết unit test.
- Viết integration test nếu có API mới.
- Refactor code cuối tuần.
- Cập nhật README/module docs.

## 9.2 Data

- Thêm hoặc làm sạch dữ liệu.
- Kiểm tra data schema.
- Cập nhật synthetic cases.
- Cập nhật gold labels nếu cần.

## 9.3 Research

- Ghi lại cơ sở lý thuyết liên quan.
- Ghi lại lý do thiết kế.
- Ghi lại limitation.
- Ghi lại decision log.

## 9.4 Evaluation

- Tạo test cases mới.
- Chạy regression test.
- Ghi nhận lỗi.
- So sánh kết quả trước/sau.

## 9.5 Thesis/Presentation

- Cập nhật báo cáo ít nhất 2-3 trang/tuần.
- Cập nhật hình/sơ đồ nếu có module mới.
- Lưu screenshot hoặc output mẫu.
- Ghi lại điểm có thể đưa vào slide.

---

# 10. Weekly workload target

Để nâng chất lượng, mỗi tuần nên đạt tối thiểu:

- 1 module hoặc feature lớn.
- 2-4 API endpoints mới hoặc cải tiến.
- 10-20 unit/integration tests.
- 10-20 synthetic cases mới trong các tuần data-heavy.
- 1 phần tài liệu kỹ thuật.
- 2-3 trang báo cáo.
- 1 bảng hoặc hình minh họa.
- 1 buổi tự review/demo cuối tuần.

---

# 11. Daily working rhythm đề xuất

## Thứ 2

- Chốt mục tiêu tuần.
- Chia task.
- Thiết kế schema/API.
- Viết issue checklist.

## Thứ 3

- Implement core backend/module.
- Viết unit test đầu tiên.

## Thứ 4

- Tiếp tục implement.
- Tích hợp database/retrieval/LLM nếu có.
- Test case thủ công.

## Thứ 5

- Tích hợp UI/API.
- Viết thêm test.
- Fix lỗi chính.

## Thứ 6

- Chạy regression test.
- Refactor.
- Cập nhật docs.

## Thứ 7

- Viết báo cáo.
- Tạo hình/bảng.
- Chạy demo thử.

## Chủ nhật

- Review toàn tuần.
- Ghi lỗi/tồn đọng.
- Chuẩn bị task tuần sau.
- Backup source/data/report.

---

# 12. Prompt chuẩn cho Claude Code khi làm task

## 12.1 Prompt tạo module mới

```text
You are working on a heart failure medication clinical decision support system.
Implement the module [MODULE_NAME] following the existing project architecture.
Requirements:
- Use FastAPI/Pydantic-compatible schemas.
- Keep business logic outside API routers.
- Add unit tests.
- Add README for the module.
- Return structured JSON.
- Do not make unsupported medical claims.
- If clinical data is missing, return insufficient_data or warning.
```

## 12.2 Prompt viết rule y khoa

```text
Create rule definitions for [DRUG_CLASS/RISK] in JSON/YAML.
Each rule must include:
- id
- target
- condition
- action: recommend/consider/caution/avoid/monitor
- severity
- reason
- required_patient_fields
- evidence_topic
- limitation
Keep the rules conservative and suitable for clinical decision support only.
```

## 12.3 Prompt viết test

```text
Write unit tests for [MODULE_NAME].
Cover:
- normal cases
- missing data
- boundary values
- abnormal clinical values
- hard constraint violation
- expected JSON schema
Use pytest.
```

## 12.4 Prompt refactor

```text
Refactor this module for clarity and maintainability.
Do not change external API behavior.
Improve:
- type hints
- error handling
- separation of concerns
- testability
- docstrings
Then update or add tests if needed.
```

## 12.5 Prompt evaluation

```text
Create an evaluation script for the heart failure CDSS project.
It should compare these modes:
- GPT-only
- RAG-only
- GraphRAG
- GraphRAG + Constraints
- Full System
Metrics:
- safety_violation_rate
- contraindication_detection_accuracy
- evidence_coverage
- json_validity_rate
- recommendation_completeness
Output CSV and markdown report.
```

---

# 13. Task priority rules

Khi thiếu thời gian, ưu tiên theo thứ tự:

1. Hệ thống demo end-to-end.
2. Safety constraints.
3. GraphRAG retrieval.
4. Multi-agent verification.
5. Evaluation/ablation.
6. Báo cáo có hình/bảng/kết quả.
7. UI polish.
8. Microservice full-scale chỉ trình bày trong thiết kế nếu không đủ thời gian.

Không được hy sinh safety/evaluation để làm UI quá đẹp.

---

# 14. Definition of MVP thành công

MVP được xem là thành công nếu:

- Nhập patient case và nhận recommendation.
- Có ít nhất 100 synthetic cases.
- Có Knowledge Graph cơ bản.
- Có Vector Retrieval guideline.
- Có Constraint Builder.
- Có ít nhất 4 verification agents.
- Có evaluation so sánh baseline.
- Có báo cáo giải thích rõ thiết kế.
- Có demo UI.
- Có audit/explanation.

---

# 15. Definition of High-quality Thesis Version

Phiên bản chất lượng cao cần thêm:

- 100 synthetic cases + 20 adversarial cases.
- Ablation study 5 phiên bản.
- Error analysis.
- Full-scale microservice architecture trong báo cáo.
- Data architecture 3 tầng: raw, processed, serving.
- Discussion về safety, explainability, limitation.
- Demo có 3 scenario rõ ràng.
- Slide có kiến trúc và kết quả thực nghiệm.

---

# 16. Risk management

## Rủi ro 1: LLM output không ổn định

Giải pháp:

- Bắt JSON schema.
- Retry parser.
- Post-validation bằng rules.
- Multi-agent verification.
- Fallback output conservative.

## Rủi ro 2: Scope quá lớn

Giải pháp:

- Triển khai modular monolith.
- Microservices chỉ trình bày full-scale.
- Tập trung HFrEF.
- Tập trung 6-8 nhóm thuốc chính.

## Rủi ro 3: Không đủ dữ liệu thật

Giải pháp:

- Dùng synthetic cases.
- Dùng guideline/drug knowledge curated.
- MIMIC-IV chỉ đưa vào hướng mở rộng hoặc demo nhỏ nếu kịp.

## Rủi ro 4: Hội đồng hỏi độ tin cậy y khoa

Giải pháp:

- Nhấn mạnh CDSS không thay bác sĩ.
- Có constraint, evidence, agents, audit.
- Có limitation rõ ràng.
- Không claim chẩn đoán/điều trị tự động.

## Rủi ro 5: Demo lỗi

Giải pháp:

- Có sample cases offline.
- Có video demo backup.
- Có screenshot output.
- Có fallback nếu LLM/API lỗi.

---

# 17. Q&A chuẩn bị bảo vệ

## Hỏi: Vì sao dùng GraphRAG thay vì RAG thường?

Trả lời:

RAG thường truy xuất văn bản tốt nhưng thiếu tri thức có cấu trúc và khó biểu diễn quan hệ thuốc-bệnh-chống chỉ định. GraphRAG kết hợp Knowledge Graph để truy xuất quan hệ y khoa rõ ràng với Vector Retrieval để lấy bằng chứng từ guideline, giúp output vừa có cấu trúc vừa có căn cứ.

## Hỏi: Vì sao cần Multi-agent Verification?

Trả lời:

Vì output của LLM có thể sai hoặc thiếu bằng chứng. Multi-agent Verification chia quá trình kiểm tra thành nhiều góc nhìn: an toàn, liều, tương tác, guideline và evidence. Điều này giúp phát hiện lỗi trước khi đưa ra khuyến nghị cuối cùng.

## Hỏi: Có làm microservice thật không?

Trả lời:

Trong phạm vi 3 tháng, hệ thống được triển khai theo modular monolith để đảm bảo ổn định khi demo. Tuy nhiên, các module được thiết kế theo ranh giới service rõ ràng, nên có thể tách thành microservices trong bản full-scale.

## Hỏi: Full-scale data là gì?

Trả lời:

Full-scale data gồm guideline, drug label, drug interaction, dữ liệu bệnh nhân giả lập và có khả năng mở rộng sang EHR dataset như MIMIC-IV. Dữ liệu được thiết kế theo pipeline raw data, processed data và serving data với PostgreSQL, Neo4j và Vector Database.

## Hỏi: Hệ thống có thay bác sĩ không?

Trả lời:

Không. Hệ thống chỉ hỗ trợ quyết định lâm sàng, cung cấp khuyến nghị, cảnh báo, bằng chứng và reasoning path để bác sĩ xem xét. Quyết định cuối cùng vẫn thuộc về bác sĩ.

---

# 18. Final success strategy

Chiến lược để đạt điểm cao:

1. Không cố làm production hospital system hoàn chỉnh.
2. Làm MVP chắc, demo được, evaluation được.
3. Thiết kế full-scale rõ ràng trong báo cáo.
4. Nhấn mạnh safety, constraints, evidence và verification.
5. Có ablation study để chứng minh đóng góp.
6. Có UI đủ đẹp để hội đồng hiểu nhanh.
7. Có limitation trung thực.
8. Có hướng phát triển thuyết phục.

Câu chốt khi bảo vệ:

> Điểm chính của đề tài không chỉ là sử dụng LLM, mà là kiểm soát LLM bằng dữ liệu có cấu trúc, ràng buộc lâm sàng, truy xuất bằng chứng và kiểm chứng đa tác nhân nhằm giảm rủi ro trong hỗ trợ sử dụng thuốc cho bệnh nhân suy tim đa bệnh nền.
