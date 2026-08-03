# CHAPTER 1: INTRODUCTION

This chapter states the problem the thesis addresses, summarizes how prior work relates to that problem, and outlines the structure of Part II. Clinical background, research objectives, scope, technical approach, and detailed theory appear in later chapters as indicated below.

## 1.1 Problem Statement

The problem addressed by this thesis sits at the intersection of a persistent clinical care gap, limitations of existing technical approaches, and open research questions about how to combine them responsibly. Heart-failure therapy is simultaneously evidence-rich and operationally fragile. The correct action depends on phenotype, current medications, laboratory values, vital signs, and sequencing constraints that span multiple documents and update cycles.

### 1.1.1 Clinical Problem (GDMT Underuse and Barriers)

For HFrEF, contemporary guidelines organize disease-modifying therapy around four GDMT pillars: renin-angiotensin system inhibitors (ACE inhibitors, ARBs, or ARNIs), evidence-based beta blockers, mineralocorticoid receptor antagonists, and SGLT2 inhibitors [2], [3], [6]. Despite strong trial evidence, real-world implementation remains strikingly incomplete. Observational data indicate that only about 1 to 2 percent of eligible patients receive all four classes at target doses [6]. Underuse is not random. Older patients, those with renal impairment, and patients cared for outside academic centers show larger gaps.

Several barriers explain this gap. Information overload exceeds what busy clinicians can continuously synthesize. Guideline documents span hundreds of pages, and drug labels contain nuanced renal adjustments, potassium warnings, and interaction language. Absolute contraindications depend on dynamic patient state: initiating an ARNI within 36 hours of ACE inhibitor exposure, starting MRAs when potassium or eGFR lies outside safe bounds, or uptitrating beta blockers during symptomatic hypotension or bradycardia each requires integrating scattered medications, labs, and vitals. Dosing complexity adds error risk because starting doses, target doses, and titration schedules must be individualized by eGFR, potassium, blood pressure, and heart rate. Where cardiologist density is low, as in many Vietnamese provincial settings, clinicians lack rapid structured support at the moment titration or class addition is considered.

Consider a representative outpatient vignette. A 68-year-old man with HFrEF (LVEF 30 percent), hypertension, type 2 diabetes, and stage 3 chronic kidney disease presents on lisinopril and carvedilol but not on an MRA or SGLT2 inhibitor. Potassium is 4.9 mmol/L, eGFR is 38 mL/min/1.73 m², and blood pressure is 108/68 mmHg. The correct plan requires simultaneous assessment of whether to add dapagliflozin, whether spironolactone is appropriate, whether beta-blocker uptitration is safe, and whether ACE-to-ARNI transition needs washout planning [2], [3]. A CDSS must surface these dependencies coherently rather than returning isolated monograph snippets.

These barriers produce predictable failure modes: delayed SGLT2 initiation, continued ACE use without ARNI washout planning, MRA prescription without potassium context, beta-blocker uptitration despite hemodynamic instability, and therapeutic inertia after discharge. A CDSS must address what should happen for this patient now, given these labs, drugs, and risks, with explicit safety enforcement where error is unacceptable. Chapter 2 develops the epidemiological and guideline context that motivates these requirements.

### 1.1.2 Technical Problem (LLM Hallucination versus Rigid Rules)

Purely generative LLM chatbots accept messy clinical descriptions and produce fluent explanations that reduce cognitive load [18], [19]. However, probabilistic generation is misaligned with medication decision support when used as the sole authority. LLMs can hallucinate doses, invent interactions, omit hard contraindications, or conflate HFpEF and HFrEF recommendations. In high-stakes prescribing, a single false negative on an absolute avoid rule is clinically catastrophic even if average answer quality appears high.

Retrieval-Augmented Generation (RAG) mitigates but does not eliminate this risk [12]. Even with RAG, a fluent model can contradict retrieved safety text unless hard rules enforce the final recommendation.

Purely rule-based CDSS systems occupy the opposite pole. MYCIN demonstrated that explicit if-then logic could support therapy reasoning with auditable trails [15]. Later EHR-embedded rule engines extended this to interaction alerting and dosing checks. Systematic reviews confirm benefits for practitioner performance and chronic-disease process outcomes [4], [5]. Rule engines excel where knowledge is precise and outputs must be reproducible, but free-text intake is brittle, rule maintenance is labor-intensive, evidence citation requires a separate layer, and alert fatigue erodes trust when specificity is low.

The technical problem is how to combine structured medical knowledge, deterministic safety logic, and LLM-mediated interaction so that heart-failure decision support remains accurate, explainable, and clinically usable. Rules without retrieval struggle with evidence citation and conversational intake. LLMs without governed rules struggle with safety and auditability. The thesis treats this as an integration problem: deterministic engines as authority for recommendations and hard constraints; retrieval and graphs as authority for evidence grounding; LLMs as authority only for explanation, borderline disambiguation, and intake fallback. Chapter 3 states the thesis claim and architectural response; Chapters 4 and 5 report implementation and measured behavior.

### 1.1.3 Research Questions

Three research questions organize the investigation.

**RQ1 (Knowledge pipeline):** How can an automated pipeline ingest FDA SPL labels, ESC/AHA/ACC/HFSA heart-failure guidelines, and interaction sources into governed constraint, dose, interaction, GDMT, and dose-safety catalogs, indexed for both vector and graph retrieval, while controlling extraction cost and preserving clinical specificity through tiered filtering and human-reviewable artifacts?

**RQ2 (Hybrid reasoning):** How can deterministic GDMT and safety rule engines be combined with hybrid GraphRAG retrieval (HyDE expansion, BM25 sparse search, BGE-M3 dense search, Neo4j neighborhood traversal, RRF fusion, optional reranking) and verification agents so that structured recommendations remain guideline-concordant and fail-closed on hard contraindications while LLM-generated explanations stay grounded in retrieved evidence?

**RQ3 (Bilingual UX and safety):** How can a chat-based, Vietnamese-English clinical interface stream structured recommendation cards and plain-language summaries over SSE without losing conversation context, and how do accuracy, latency, alert sensitivity, and clinician satisfaction compare against predefined success criteria when evaluated on curated HFrEF vignettes?

## 1.2 Related Work

Heart-failure CDSS design builds on four research lines. Chapter 2 reviews each in depth; here we state how they relate to the problem above and where this thesis fits.

**Classical CDSS.** Rule-based systems from MYCIN onward showed that encoded clinical logic can be auditable and effective in narrow domains [15], [4], [5]. Osheroff's Five Rights and workflow-oriented evaluation remain relevant [17]. Enterprise EHR tools often excel at generic interaction checking but provide limited HFrEF-specific GDMT gap analysis and struggle with bilingual, chat-first intake.

**Biomedical knowledge graphs and terminologies.** Knowledge graphs express drugs, conditions, labs, and relations explicitly, supporting multi-hop reasoning that flat documents obscure [7], [8]. UMLS, SNOMED CT, and DrugBank support normalization and pharmacology [9]-[11]. Automated extraction requires governance because noise and stale edges accumulate without human approval workflows [8].

**RAG, GraphRAG, and hybrid retrieval.** RAG grounds LLM outputs in retrieved passages [12]. Dense embeddings handle paraphrase; BM25 handles exact regulatory language; Reciprocal Rank Fusion merges heterogeneous rankers. GraphRAG adds neighborhood traversal for relational constraints [13]. HyDE improves recall on short clinical queries [14]. Few deployed CDSS products combine these techniques with fail-closed rule tiers for GDMT.

**Heart-failure guidelines.** ESC and AHA/ACC/HFSA guidelines define the normative backbone for HFrEF quadruple therapy, washout rules, and monitoring [2], [3], [6]. FDA Structured Product Labels add product-specific dosing and warnings. Operational CDSS must reconcile prose guidelines with executable catalogs.

**Research gap.** Many systems remain English-only, oncology-focused, or limited to passive lookup. LLM-centric prototypes prioritize fluency over structured GDMT analysis and hard contraindication enforcement. Vector-only RAG may miss interaction chains better expressed as graph paths or SQL rules. Rule-only systems may alert correctly without citing evidence clinicians expect. This thesis targets an integrated architecture: multi-store governed ingestion, hybrid GraphRAG, deterministic GDMT engines independent of generative narrative, verification agents, and bilingual streaming chat with structured cards, evaluated against explicit criteria defined in Chapter 5.

## 1.3 Thesis Outline

The manuscript is divided into two parts. **Part I** (this chapter) introduces the problem and related work. **Part II** develops theory, design, implementation, results, and conclusions.

**Chapter 2, Literature Review and Theory**, provides clinical background and motivation, classical CDSS foundations, knowledge graphs, RAG and GraphRAG, large language models, medical knowledge construction, heart-failure clinical foundations, implementation technologies, and a mapping of adopted techniques to architectural roles.

**Chapter 3, System Design**, states research purpose, scope, and technical approach; functional and non-functional requirements; three-tier architecture; knowledge graph schema; and module designs for hybrid intake, GraphRAG, reasoning, safety, verification, and chat streaming.

**Chapter 4, Implementation and Deployment**, documents the Python/FastAPI backend, data stores, Ollama-served models, React frontend, knowledge pipeline modules, query-time services, and Docker Compose deployment.

**Chapter 5, Results and Evaluation**, defines predefined success criteria, reports knowledge-base statistics, recommendation accuracy on cardiologist-reviewed vignettes, latency, safety-alert sensitivity, bilingual usability, and error analysis against those criteria.

**Chapter 6, Conclusion**, summarizes contributions, reflects on RQ1–RQ3, discusses limitations, and outlines future work including formulary expansion, FHIR interoperability, and prospective clinical studies.

References lists primary sources. **Chapter 3** and **Chapter 4** embed interactive architecture and pipeline figures (Figures 3.1–3.6 and 4.1–4.2); **Appendix A** repeats the same diagrams as Figures A.1–A.8 with component tables. See [figures/README.md](figures/README.md) for file paths. Together, Part II develops a coherent case that hybrid Knowledge Graph-augmented CDSS can support heart-failure GDMT decisions when authority is assigned correctly, knowledge is governed rather than improvised, and clinicians remain the final decision makers.
