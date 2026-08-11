# CHAPTER 1: INTRODUCTION

<link rel="stylesheet" href="figures/thesis-figures.css">

This chapter states why the heart-failure CDSS project matters, what it aims to build and measure, what falls inside or outside the study, the problem it addresses, three research questions, a brief related-work orientation, and a map of Chapters 2–6. Chapter 2 covers theory; Chapter 3 covers design; Chapters 4–5 cover implementation and measured results.

## 1.1 Background and Motivation

Heart failure (HF) is a chronic condition: the heart pumps or fills poorly, so patients feel short of breath, tired, swollen, and often return to hospital. Global estimates put more than 64 million people living with HF, and the number keeps rising as populations age and more patients survive acute events but keep reduced pump function [1].

Clinicians classify HF by **left ventricular ejection fraction (LVEF)**. When LVEF is 40% or lower, the pattern is **heart failure with reduced ejection fraction (HFrEF)**. This thesis focuses on HFrEF because **guideline-directed medical therapy (GDMT)** has the strongest outcome evidence in this group [2], [3], [6].

GDMT for HFrEF rests on four drug-class pillars: RAAS blockade (ACE inhibitor, ARB, or ARNI), an evidence-based beta blocker, a mineralocorticoid receptor antagonist (MRA), and an SGLT2 inhibitor. In practice, very few eligible patients receive all four classes at target doses [6]. Older patients, renal impairment, and clinicians outside academic centers are often undertreated.

Each visit requires combining HF phenotype, current drugs, labs, vitals, and timing rules (for example ACE inhibitor washout before ARNI). Guidelines are long; labels add renal dosing, potassium warnings, and interactions. In Vietnam, charts often mix Vietnamese and English, and local brand names do not map one-to-one to international drug keys [1]. **Clinical decision support systems (CDSS)** are widely proposed to narrow the gap between published evidence and bedside action [4], [5].

Two technical trends make a governed HF CDSS more feasible now. Biomedical **knowledge graphs**, standard terminologies, and open label repositories support automated ingestion into governed catalogs [7]–[11]. **Large language models (LLMs)** read messy clinical text and write explanations, but fluent text can still state wrong doses or miss hard contraindications unless outputs are constrained [12], [19]. Running open-weight models on premises (Ollama) suits pilots that must keep vignettes inside the hospital network.

## 1.2 Research Purpose, Scope, and Approach

### 1.2.1 Purpose of the Study

The study designs, implements, and evaluates a heart-failure CDSS that combines a medical **knowledge graph**, **GraphRAG** retrieval, fixed clinical rule engines, **verification** agents, and a locally hosted LLM. Authoritative inputs (FDA DailyMed SPL/XML, ESC and AHA/ACC/HFSA guidelines, curated interactions) become governed catalogs that reasoning and explanation can both use without contradiction.

Four technical lines organize the work: (1) an automated **knowledge-construction pipeline**; (2) **hybrid retrieval** (dense, BM25, graph, HyDE, RRF) [12]–[14]; (3) separation of fixed recommendation logic from LLM narrative; (4) end-to-end evaluation against predefined criteria (Chapter 5, Section 5.0). The target is a cardiologist-supervised prototype with hybrid intake, GDMT and safety engines, GraphRAG, verification, and bilingual **Server-Sent Events (SSE)** streaming. The system does not replace an EHR or prescribe without human review.

### 1.2.2 Scope and Delimitations

**In scope:** pharmacologic GDMT for HFrEF (ACEi, ARB, ARNI, beta blocker, MRA, SGLT2i); DailyMed SPL and major HF guidelines; doctor chat intake (not live HL7/FHIR); Vietnamese–English UI; local Docker deployment; evaluation on curated vignettes and structured safety cases.

**Largely out of scope:** HFpEF, acute decompensated HF requiring IV vasoactives, devices, transplant, and a full Vietnamese national formulary with pricing. Recommendations are advisory; the clinician retains prescribing authority.

### 1.2.3 Thesis Statement

A **hybrid CDSS** that couples fixed GDMT and safety rules with GraphRAG and local LLM explanation can deliver accurate, timely, bilingual heart-failure support while clinicians keep final authority. **Accuracy** means agreement between structured recommendation objects and expert-reviewed expectations on test cases. **Timeliness** means typical end-to-end response within about ten seconds on evaluation hardware (Chapter 5). **Safety** means fail-closed handling of hard contraindications in governed catalogs plus verification of structured outputs and citations. The design rejects unconstrained generative chat and rigid rule-only alerts that cannot read free text or cite sources.

### 1.2.4 Knowledge Engineering Approach (Offline)

Raw SPL labels and guideline documents land in versioned object storage. A **three-tier section filter** (keywords, BGE-M3 similarity, LLM only on borderline sections) limits cost. Filtered text is chunked, claims are extracted, and safety tiers are assigned (`hard_block`, `usable_rules`, `needs_condition_refinement`). Approved artifacts sync to PostgreSQL (executable rules), ChromaDB (vectors), and Neo4j (graph). PostgreSQL hard blocks always override retrieved passages used for explanation.

### 1.2.5 Query-Time Approach (Online)

Each doctor message passes through **hybrid intake** (regex for labs and vitals, medication lexicon with negation, selective LLM when confidence is low). A **reasoning engine** evaluates GDMT gaps, constraints, interactions, and dose plans without LLM generation for core statuses. In parallel, **GraphRAG** runs HyDE expansion, dense and sparse search, Neo4j neighborhood expansion, and RRF fusion. Verification agents and SSE deliver structured cards before narrative text finishes streaming.

### 1.2.6 Design Principle: LLM as Explanation Layer, Rules as Authority

PostgreSQL catalogs set recommendation status, hard blocks, and doses. Citable chunks must match retrieved evidence. LLMs parse ambiguous intake and write explanation; they cannot downgrade `hard_block`, invent therapy, or present unsourced label facts. Chapter 3, Section 3.2.1 restates this in the full runtime architecture.

## 1.3 Problem Statement and Research Questions

### 1.3.1 Clinical Problem

GDMT gaps and unsafe sequencing remain common: delayed SGLT2i, ACE inhibitor continued without ARNI washout plan, MRA started without potassium or eGFR context, beta-blocker uptitration despite unstable blood pressure. A CDSS must answer what to do next for this patient’s labs, drugs, and risks, with explicit safety enforcement.

**Example:** a 68-year-old man with HFrEF (LVEF 30%) on lisinopril and carvedilol but no MRA or SGLT2i; K+ 4.9 mEq/L, eGFR 38 mL/min/1.73 m², BP 108/68 mmHg. A sound plan must weigh adding dapagliflozin, spironolactone, beta-blocker uptitration, and an ACEi-to-ARNI pathway with washout [2], [3] together, not as isolated monograph snippets.

### 1.3.2 Technical Problem

Pure LLM chat reads messy prose but is unsafe as the sole prescribing authority [18], [19]. **Retrieval-augmented generation (RAG)** grounds answers in documents [12] but does not by itself enforce fail-closed rules. Classical rule engines are auditable [15], [4], [5] but weak at chat intake and readable citations. The technical problem is integration: governed catalogs, fixed logic, hybrid retrieval, and LLMs with a narrow role.

### 1.3.3 Research Questions

**RQ1 (Knowledge pipeline):** How can an automated pipeline ingest FDA SPL labels, ESC/AHA/ACC/HFSA heart-failure guidelines, and interaction sources into governed catalogs indexed for vector and graph retrieval, while controlling extraction cost and preserving clinical specificity?

**RQ2 (Hybrid reasoning):** How can fixed GDMT and safety engines be combined with hybrid GraphRAG retrieval and verification agents so structured recommendations stay guideline-concordant and fail closed on hard contraindications while LLM explanations stay grounded in retrieved evidence?

**RQ3 (Bilingual UX and safety):** How can a Vietnamese–English chat interface stream structured recommendation cards over SSE without losing context on language switch, and how do accuracy, latency, safety, and satisfaction compare with predefined success criteria on HFrEF vignettes?

## 1.4 Related Work (Summary)

Chapter 2 reviews prior work in full. At introductory level the thesis sits at four lines:

- **Classical CDSS** [15], [4], [5], [17]: auditable rules and workflow-aware alerts; commercial EHR checks are strong on generic interactions but weak on HFrEF GDMT gaps and bilingual chat intake.
- **Biomedical knowledge graphs** [7]–[11]: relational reasoning; automated extraction needs governance [8].
- **RAG and GraphRAG** [12]–[14]: document-grounded generation; few deployed HF CDSS products pair this with fail-closed GDMT rules.
- **HF guidelines and FDA SPL labels** [2], [3], [6]: normative therapy and product-specific dosing and warnings.

The gap is an integrated, HFrEF-focused, bilingual chat CDSS with governed ingestion, hybrid GraphRAG, fixed engines, verification agents, and evaluation on structured recommendation objects (not free-text plausibility alone), with targets in Chapter 5, Section 5.0.

## 1.5 Thesis Outline

**Part I** (this chapter): background, purpose, scope, approach, problem, research questions, related-work summary, and roadmap.

**Part II:**

| Chapter | Main content |
|---------|----------------|
| 2 | CDSS, knowledge graphs, RAG, LLMs, GraphRAG, HFrEF foundations (no implementation detail) |
| 3 | Requirements, architecture, modules, schemas, APIs, UI |
| 4 | Implementation, ingestion pipeline, Docker, tests |
| 5 | Success criteria (5.0), accuracy, latency, safety, usability |
| 6 | Contributions, answers to RQs, limitations, future work |

References and figure appendices follow the main chapters. Figures 3.1–3.6 and 4.1–4.2 appear in Chapters 3–4; Appendix A repeats them as Figures A.1–A.8. See [figures/README.md](figures/README.md) and [tables/README.md](tables/README.md) for numbering conventions.
