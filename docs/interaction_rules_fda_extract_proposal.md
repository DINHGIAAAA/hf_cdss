# Đề xuất thay đổi: Interaction rules (extract từ raw → Admin approve)

**Trạng thái:** đã implement theo mục 9 (2026-07-21)  
**Phạm vi:** catalog **interaction rules**  
**Mục tiêu:** không hardcode 20–30 pair vào `hf_interaction_rules_v1.json`; sinh candidate từ **raw FDA label XML**, đưa vào Postgres `draft`, clinician/admin **approve** rồi mới vào runtime.

---

## 1. Hiện trạng

| Thành phần | Đường dẫn / hành vi | Vấn đề |
|------------|---------------------|--------|
| Bundled fallback | `backend/app/modules/interaction_checking/rules/hf_interaction_rules_v1.json` | Chỉ **4** rule; `source=bundled_week7_baseline`; `evidence_ref` dạng `week7_interaction_rule:…` (mốc nội bộ, không phải citation lâm sàng) |
| Runtime loader | `rule_loader.py` → `RuleCache` | Đọc **Postgres approved** trước; JSON chỉ khi DB trống/lỗi |
| Admin | `backend/app/api/routes/admin/interaction_rules.py` + Admin UI | Đã có list / diff / approve / retire / bulk-approve |
| Sync | `scraper/process/sync_governance_catalog.py` | Upsert artifact → Postgres **`draft`**; không auto-approve |
| Pipeline hiện tại | `extract_structured_interaction_claims` → `generate_interaction_rules` → `classify_interaction_rules` | Chủ yếu LLM trên **chunks** (guideline/section); artifact ~59 rule **nhiễu**, chưa đủ tin để approve hàng loạt |
| Raw labels | `data/heart_failure/raw/drug_labels/**/**_label.xml` | Đã có ~169 XML; section **DRUG INTERACTIONS** chưa có extractor chuyên biệt kiểu `xml_dose_extractor` |

**Kết luận kiến trúc:** Admin/Postgres và extract không phải 2 lựa chọn thay thế — là 2 tầng:

1. **Extract từ raw** → candidate  
2. **Admin approve** → runtime  

Bundled JSON giữ vai trò bootstrap/CI, không phải nơi “sống” của catalog production.

---

## 2. Mục tiêu sau khi làm xong

1. Extract DDI từ `*_label.xml` (section Drug Interactions) → claims → rules JSONL.  
2. `sync_governance_catalog --catalog interaction_rules` đưa rule vào Postgres `draft`.  
3. Admin UI hiển thị draft (kèm quote / `source_refs`) để Approve / Reject / Refine.  
4. Runtime `/interaction/check` và `/recommend` chỉ dùng rule **approved**.  
5. Không yêu cầu viết tay từng pair vào `hf_interaction_rules_v1.json`.  
6. (Tuỳ chọn, phase sau) Làm sạch / thu hẹp bundled Week-7; đổi `evidence_ref` sang ref có thể truy vết.

**Out of scope tài liệu này:** hardcode Digoxin+Amiodarone… vào JSON; GDMT phenotype; dose CrCl (P2/P3 roadmap riêng).

---

## 3. Luồng đích

```
raw/drug_labels/{id}/{id}_label.xml
        │
        ▼
[A] Extract DRUG INTERACTIONS section (deterministic + optional LLM normalize)
        │
        ▼
artifacts/interaction_rules/structured_interaction_claims.jsonl
  (+ optional: claims từ guideline chunks — nguồn phụ)
        │
        ▼
[B] generate_interaction_rules  (interaction_rule_builder)
        │
        ▼
artifacts/interaction_rules/interaction_rules.jsonl
        │
        ▼
[C] classify_interaction_rules  (usable / needs_refinement / rejected)
        │
        ▼
[D] sync_governance_catalog --catalog interaction_rules
        │   status = draft
        ▼
Postgres interaction_rules
        │
        ▼
[E] Admin UI: review / edit nhẹ / Approve | Reject
        │   status = approved
        ▼
RuleCache → POST /interaction/check, POST /recommend
```

Fallback offline: `hf_interaction_rules_v1.json` (giữ tối thiểu cho test khi không có DB).

---

## 4. Thay đổi cần thực hiện (checklist duyệt)

### Phase A — Extractor từ FDA XML (ưu tiên)

- [ ] **A1.** Thêm module extract DDI từ SPL XML, song song với dose path.  
  - Gợi ý vị trí: `backend/app/modules/interaction_checking/xml_interaction_extractor.py`  
    **hoặc** `scraper/semantic/fda_xml_interaction_extractor.py` (ưu tiên scraper nếu artifact thuộc pipeline).  
  - Input: `raw/drug_labels/**/**_label.xml`.  
  - Nhận diện section: title / LOINC **DRUG INTERACTIONS** (và subsection liên quan).  
  - Output claim tối thiểu:
    - `claim_type`: `structured_interaction_rule` (hoặc `drug_interaction` rồi normalize)
    - `drug_set_a`: thuốc của label (pipeline_id / catalog key)
    - `drug_set_b`: partner drug hoặc `class:*`
    - `message`, `severity` (default `moderate` nếu không suy ra được), `action` (`avoid`|`monitor`|`review`)
    - `monitoring` (list string; không để placeholder `"string"`)
    - `source_refs[]`: `document_id`, `source_type=drug_label`, `source_section`, `evidence` (quote), `set_id`/`folder`
    - `extraction_method`: `fda_xml_drug_interactions` (hoặc `fda_xml_drug_interactions+llm_normalize`)

- [ ] **A2.** CLI / process step, ví dụ:  
  `python -m scraper.process.extract_fda_xml_interaction_claims`  
  → ghi `artifacts/interaction_rules/structured_interaction_claims_fda.jsonl`  
  (hoặc merge vào file claims hiện có với flag `--source fda_xml|chunks|all`).

- [ ] **A3.** Map partner → token runtime:
  - Dùng `drug_aliases.json` / catalog normalize (cùng convention matcher).  
  - Class tokens đã có / cần bổ sung trong `matcher.py`: ví dụ `non_dhp_ccb`, `qt_prolonging`, `insulin`, `statin`, `amiodarone`, `digoxin` (chỉ thêm khi extract thực sự ra class-level).  
  - Partner không map được → giữ raw token + đánh dấu `needs_refinement` (không drop im lặng nếu có quote rõ).

- [ ] **A4.** Ưu tiên chất lượng hơn số lượng lần đầu:
  - Filter theo allowlist thuốc HF/cardio trong scope (aliases / GDMT groups), **hoặc**  
  - Chạy full 169 labels nhưng classify chặt (reject nếu thiếu 2 drug sets rõ, message quá generic, monitoring rỗng).

### Phase B — Nối vào pipeline governance hiện có

- [ ] **B1.** `generate_interaction_rules`: nhận claims FDA XML; giữ `interaction_rule_builder.py`; đảm bảo field runtime:
  - `interaction_rule_id` (ổn định) **hoặc** map `rule_id` → `interaction_rule_id` lúc sync  
  - `drug_set_a`, `drug_set_b`, `severity`, `rule_body`, `evidence_ref` / `source_refs`

- [ ] **B2.** `evidence_ref` chuẩn (thay dần `week7_*` cho rule mới):  
  ví dụ `fda_label:{pipeline_id}:drug_interactions`  
  hoặc `fda_label:{pipeline_id}:{subsection_slug}`.

- [ ] **B3.** `classify_interaction_rules`: bổ sung heuristic cho nguồn FDA:
  - reject: drug_set trống, self-interaction, message &lt; N ký tự, monitoring rác  
  - needs_refinement: severity/action mặc định, class chưa map  
  - usable: đủ field + partner đã normalize

- [ ] **B4.** Wiring orchestration: thêm/đổi step trong `governance_catalog_steps.py` (hoặc flag) để extract FDA XML **trước hoặc thay** LLM-on-chunks làm nguồn chính interaction.

- [ ] **B5.** `sync_governance_catalog --catalog interaction_rules`: xác nhận mọi row sync với `status=draft`; không auto-approve; content_hash tránh version rác.

### Phase C — Admin (chỉ bổ sung nếu thiếu UX)

Pipeline Admin cơ bản **đã có**. Cần xác nhận / bổ sung nhẹ:

- [ ] **C1.** List draft filter theo `extraction_method` / `source_type=drug_label`.  
- [ ] **C2.** Detail hiển thị `source_refs` (quote + document_id) — nếu UI chưa đủ thì bổ sung `InteractionRuleDetail`.  
- [ ] **C3.** Cho phép sửa nhẹ `drug_set_*`, `severity`, `action`, `message` trước approve (nếu chưa có).  
- [ ] **C4.** Bulk-approve chỉ trên tập đã filter `usable` (tránh approve nhầm rejected).  
- [ ] **C5.** Sau approve: `invalidate_interaction_rules_cache()` (đã có trên một số endpoint — kiểm tra đủ path).

**Không** thêm form “tạo rule từ đầu” như nguồn chính; tạo tay chỉ là escape hatch.

### Phase D — Runtime & bundled JSON

- [ ] **D1.** Giữ matcher/evaluator hiện tại; không đổi API public `/interaction/check`.  
- [ ] **D2.** `hf_interaction_rules_v1.json`:  
  - **Ngắn hạn:** giữ 4 rule Week-7 làm fallback CI/offline.  
  - **Sau khi Postgres có ≥N approved:** cân nhắc thu hẹp JSON hoặc đổi `evidence_ref` khỏi `week7_*` (PR riêng, tránh phá `test_medication_safety` / docs API).  
- [ ] **D3.** Cập nhật `interaction_checking/README.md`: mô tả extract → draft → approve; bỏ mô tả “Week-7 = toàn bộ scope”.

### Phase E — Tests & tài liệu

- [ ] **E1.** Unit: parse 1–2 XML thật (vd. digoxin, amiodarone, warfarin) → claim có partner mong đợi.  
- [ ] **E2.** Builder: claim → rule có đủ field sync.  
- [ ] **E3.** Classify: case reject / usable.  
- [ ] **E4.** (Integration, optional) sync draft mock + approve → `load_executable_interaction_rules` chứa rule.  
- [ ] **E5.** Không làm fail các test phụ thuộc 4 rule bundled hiện có trừ khi chủ đích migrate.  
- [ ] **E6.** Cập nhật ngắn `docs/data_sources.md` hoặc `docs/architecture.md` (link tới tài liệu này).

---

## 5. Việc **không** làm trong scope này

- Viết 20–30 interaction vào `hf_interaction_rules_v1.json` như nguồn production.  
- Auto-load toàn bộ `interaction_rules.jsonl` LLM hiện tại vào runtime không qua admin.  
- Thay thế dose calculation / GDMT policy.  
- Đòi hỏi clinician approve 100% DDI trên mọi label trước khi ship extractor (ship extractor + draft trước; approve theo ưu tiên lâm sàng).

---

## 6. Ưu tiên lâm sàng khi approve (gợi ý backlog Admin)

Không hardcode vào JSON; dùng làm **checklist duyệt draft** sau extract:

| Pair / nhóm | Kỳ vọng action |
|-------------|----------------|
| Digoxin + Amiodarone | monitor (level / toxicity) |
| Beta-blocker + non-DHP CCB (verapamil/diltiazem) | avoid / review |
| Warfarin + Amiodarone | monitor INR |
| Triple RAAS (ACEi + ARB + ARNI/MRA) | avoid |
| SGLT2i + insulin | monitor hypoglycemia |
| QT-prolonging combos (amiodarone + …) | avoid / monitor |
| Statin (simva/lova) + Amiodarone | avoid / dose limit messaging |
| ACEi+ARB, RAASi+MRA, RAASi+NSAID, anticoag+antiplatelet | đã có bundled; xác nhận còn sau migrate |

---

## 7. Tiêu chí chấp nhận (Definition of Done)

1. Chạy extract trên raw labels → ra claims/rules JSONL với `source_refs` trỏ về XML.  
2. Sync → Admin thấy **draft** interaction rules từ FDA.  
3. Approve ≥ một rule mới (không có trong Week-7) → xuất hiện trong executable rules / warning trên patient test.  
4. Reject rule nhiễu → không vào runtime.  
5. CI: test extract + bundled fallback vẫn xanh khi không có Postgres.  
6. Không phụ thuộc sửa tay `hf_interaction_rules_v1.json` để có rule mới trên môi trường có DB.

---

## 8. Ước lượng & thứ tự PR

| PR | Nội dung | Phụ thuộc |
|----|----------|-----------|
| **PR1** | Extractor FDA XML + CLI + unit tests (digoxin/amiodarone/warfarin) | — |
| **PR2** | Merge vào generate/classify + sync draft; README pipeline | PR1 |
| **PR3** | Admin UX nhỏ (filter nguồn, hiện quote) nếu thiếu | PR2 |
| **PR4** | (Tuỳ chọn) Dọn `week7` evidence_ref / thu hẹp bundled | Sau khi approved ổn định |

---

## 9. Quyết định cần duyệt

Đánh dấu lựa chọn trước khi implement:

1. **Nguồn extract chính lần 1**  
   - [ ] Chỉ FDA XML Drug Interactions  
   - [x] FDA XML + giữ LLM guideline chunks (hai nguồn, classify chung)

2. **Chỗ đặt extractor**  
   - [ ] Trong `scraper/` (pipeline artifact)  
   - [x] Trong `backend/.../interaction_checking/` (giống dose_calculation)  
   - [ ] Shared lib gọi từ cả hai

3. **Phạm vi label lần 1**  
   - [x] Toàn bộ ~169 aliases có XML  
   - [ ] Allowlist HF/cardio core trước (khuyến nghị nếu muốn draft sạch hơn)

4. **Bundled JSON**  
   - [ ] Giữ 4 rule Week-7 nguyên đến khi Postgres đủ  
   - [x] Đổi `evidence_ref` ngay (cosmetic)  
   - [ ] Thu hẹp/xóa dần sau khi có approved

5. **Normalize partner**  
   - [ ] Deterministic dictionary/alias only (an toàn hơn)  
   - [x] Deterministic + LLM normalize khi không match (nhiều recall hơn, cần classify chặt)

---

## 10. Liên quan file chính (tham chiếu)

| Vai trò | File |
|---------|------|
| Bundled fallback | `backend/app/modules/interaction_checking/rules/hf_interaction_rules_v1.json` |
| Loader | `backend/app/modules/interaction_checking/rule_loader.py` |
| Matcher | `backend/app/modules/interaction_checking/matcher.py` |
| Admin API | `backend/app/api/routes/admin/interaction_rules.py` |
| Sync draft | `scraper/process/sync_governance_catalog.py` |
| Extract hiện tại (chunks) | `scraper/process/extract_structured_interaction_claims.py` |
| Builder | `scraper/semantic/interaction_rule_builder.py` |
| Orchestration | `scraper/orchestration/governance_catalog_steps.py` |
| Raw labels | `data/heart_failure/raw/drug_labels/` |
| Aliases | `data/heart_failure/config/drug_aliases.json` |

---

*Tài liệu đề xuất; implementation theo mục 9 đã land trong repo (extractor + pipeline + Admin filter + tests). Đồng bộ Postgres vẫn cần chạy sync trên môi trường có DB.*
