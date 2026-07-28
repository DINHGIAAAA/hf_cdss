# CHAPTER 2: LITERATURE REVIEW AND THEORY

## 2.1 Clinical Decision Support Systems (CDSS)

### 2.1.1 Definition and Scope

A Clinical Decision Support System (CDSS) is software designed to assist clinicians, staff, or patients in making diagnostic or treatment decisions. The Institute of Medicine defines CDSS as "any electronic system designed to aid directly in clinical decision making" [1]. In contemporary practice, CDSS spans passive reference tools, active alerting systems embedded in electronic health records (EHRs), and conversational assistants that synthesize patient context with guideline knowledge. The defining characteristic is not automation of the final clinical judgment but structured augmentation: surfacing relevant evidence, detecting safety conflicts, and proposing actionable options within the clinician's workflow.

The scope of CDSS has widened considerably since early expert systems. Modern implementations may integrate laboratory feeds, medication lists, problem lists, imaging reports, and unstructured clinical notes. They may operate synchronously at the point of order entry—blocking or warning before a prescription is signed—or asynchronously during care planning and medication reconciliation. For chronic diseases such as heart failure, CDSS value often lies in longitudinal therapy optimization rather than one-time diagnostic suggestion: identifying missing guideline-directed drug classes, flagging contraindications before dose escalation, and reminding clinicians of monitoring intervals after therapy changes. This thesis adopts that chronic-disease framing: HF-CDSS is designed to support GDMT titration and safety review across repeated encounters, not to replace cardiology consultation for acute decompensation.

Regulatory bodies distinguish CDSS that inform clinicians from software that autonomously diagnoses or treats; HF-CDSS explicitly falls in the former category through HITL design and non-ordering interfaces. SaMD (Software as a Medical Device) classifications in FDA and EU MDR frameworks depend on intended use and autonomy level—an important boundary when interpreting evaluation results in later chapters as research prototypes rather than cleared medical products. The thesis therefore reports accuracy and safety process metrics on curated cases without claiming regulatory compliance or clinical deployment readiness.

### 2.1.2 Taxonomy and Classification

CDSS can be classified along several dimensions that shape both architecture and evaluation. With respect to the timing of support, passive systems provide information only upon user request—for example, a drug monograph lookup or a guideline search portal—whereas active systems deliver proactive recommendations or alerts derived from patient data at the point of care. Passive tools minimize interruption but depend on clinician initiative; active tools can improve process adherence but risk alert fatigue when specificity is low. By function, systems may address diagnosis (differential generation, test ordering), therapy (medication selection, dosing), alerting (drug–drug interactions, contraindications), or chronic-disease management (longitudinal GDMT optimization). Heart-failure CDSS primarily occupies the therapy and chronic-management quadrants, with alerting as a safety overlay.

By mechanism, implementations range from rule-based expert systems with explicit if–then logic, through machine-learning classifiers trained on observational data, to knowledge-base-driven architectures that combine structured ontologies with retrieval and generation. Rule-based systems offer auditable logic: each recommendation can be traced to a named constraint or guideline clause. Machine-learning systems may capture subtle patterns in large datasets but often lack interpretability and may encode historical prescribing bias. Knowledge-base and retrieval-augmented approaches ground outputs in curated sources, trading some flexibility for traceability. Hybrid systems deliberately combine multiple paradigms: deterministic rule engines for safety-critical constraints, statistical models for risk stratification, and large language models (LLMs) for natural-language explanation—an approach adopted in this thesis because heart-failure therapy requires both auditable logic and readable communication in Vietnamese and English.

A further distinction separates knowledge-driven CDSS (explicit rules, ontologies, drug databases) from data-driven CDSS (predictive models on EHR data). HF-CDSS in this study is predominantly knowledge-driven, with LLMs used for extraction, query expansion, and explanation rather than as the authoritative decision function. Integration context also matters: standalone web applications, EHR-embedded modules, and mobile bedside tools differ in authentication, data availability, and latency expectations. The present system is implemented as a standalone FastAPI/React application with JWT role-based access, suitable for pilot deployment and later FHIR-based integration described in later chapters.

### 2.1.3 Historical Development

The evolution of CDSS reflects decades of progress in medical informatics and shifting expectations about human–computer collaboration. MYCIN (1976) pioneered rule-based sepsis therapy advice at Stanford, demonstrating that encoded clinical heuristics could match expert performance in narrow domains [2]. MYCIN represented knowledge as production rules with certainty factors, consulted the user through a structured dialogue, and explained its reasoning—a design that anticipated modern demands for transparency. Although MYCIN never entered routine clinical use, it established that medical decision logic could be formalized and that explanation mattered as much as conclusion.

DXplain (1986) introduced symptom-driven diagnostic support across a broader internal-medicine scope, linking manifestations to disease hypotheses through weighted associations. Internist-1 and its successor Quick Medical Reference (QMR) extended differential diagnosis through disease–manifestation matrices, handling multiple concurrent conditions more systematically than early single-disease advisors. The 1990s and 2000s saw CDSS embedded in commercial EHRs: drug–allergy checking, duplicate therapy alerts, and basic dosing calculators became standard, though many alerts suffered from low specificity.

More recently, DeepMind Streams (2016) demonstrated acute kidney injury alerts from laboratory time series, showing that predictive models could surface deterioration before clinicians noticed trends. IBM Watson for Oncology (2012) applied knowledge-graph–assisted support in oncology, combining literature and pathway knowledge with patient summaries—though subsequent evaluations highlighted gaps between marketing claims and bedside utility when knowledge curation and local practice norms were insufficient. The current generation adds transformer-based language models, retrieval-augmented generation, and graph-augmented retrieval, enabling natural-language interaction while attempting to preserve source grounding. Each generation reinforced a persistent lesson: clinical acceptability depends as much on workflow integration, alert specificity, and transparency as on raw predictive accuracy.

### 2.1.4 Evaluation Standards: The Five Rights

Osheroff's "Five Rights" of CDSS [3] provide a workflow-centric evaluation framework rather than a single accuracy number. The right information must reach the right person in the right format through the right channel at the right time. A technically correct recommendation delivered after the prescribing decision, buried in an unread alert queue, or phrased in inaccessible jargon fails clinically even when its underlying logic is sound.

For heart-failure GDMT, "right information" includes phenotype (HFrEF versus HFpEF), renal and electrolyte safety, current medication class coverage, and washout constraints when switching between ACE inhibitors and ARNI. It also includes dose-relevant context: whether the patient is on starting dose versus target dose, whether blood pressure and heart rate permit beta-blocker uptitration, and whether potassium and eGFR permit MRA initiation or continuation. "Right person" is typically the treating physician or clinical pharmacist who holds prescribing authority or performs medication reconciliation; in some settings, nurse-led HF clinics may be the primary recipient. "Right format" may combine structured status indicators (continue, consider, avoid) with plain-language rationale and citation links to label or guideline passages. "Right channel" includes EHR-embedded alerts, dedicated CDSS dashboards, or streaming chat interfaces; HF-CDSS uses a doctor-facing web dashboard with progressive SSE disclosure so clinicians see structured recommendations before narrative explanation completes. "Right time" means at medication reconciliation, post-discharge follow-up, or outpatient titration visits when GDMT decisions are actually made—not hours later in an inbox summary.

The Five Rights imply that CDSS evaluation must include usability and workflow studies, not only offline accuracy on curated cases. A system that achieves high guideline concordance in batch testing but requires thirty seconds of reading per alert may still be abandoned in busy clinics.

### 2.1.5 Quantitative Metrics and Alert Fatigue

Quantitative evaluation complements the Five Rights. Sensitivity (recall) measures the proportion of true clinical conditions or recommended actions that the system correctly identifies: sensitivity equals TP divided by (TP + FN), where TP denotes true positives and FN false negatives. High sensitivity is essential for safety alerts—a missed contraindication, such as failing to block ARNI initiation within 36 hours of the last ACE inhibitor dose, is clinically costly and potentially harmful. Specificity measures the proportion of negatives correctly rejected: specificity equals TN divided by (TN + FP), where TN denotes true negatives and FP false positives. High specificity reduces unnecessary interruptions.

Positive predictive value (PPV) is the fraction of system-positive alerts that are truly relevant: PPV equals TP divided by (TP + FP). Negative predictive value (NPV) is the fraction of system-negative cases that are truly safe: NPV equals TN divided by (TN + FN). In alerting contexts, low PPV drives alert fatigue: clinicians override or ignore warnings when most alerts are false alarms or trivial duplicates of information they already considered. Alert burden summarizes the volume and interruption cost of alerts per patient encounter or per prescriber shift; effective CDSS design trades off sensitivity against burden through tiered severity (hard block versus soft caution), contextual suppression (do not re-alert for the same stable finding), and distinction between informational and actionable messages.

User satisfaction, time-to-decision, and guideline concordance audits provide complementary qualitative and process measures. For HF-CDSS, later chapters evaluate recommendation accuracy against cardiologist review, end-to-end latency, safety-alert sensitivity on curated contraindication cases, and bilingual usability—without reporting fabricated performance figures in this theoretical chapter.

Alert fatigue literature emphasizes that override rates above roughly 90% for a given alert type signal poor PPV and imminent clinician desensitization. Mitigation strategies include suppressing duplicate alerts within a time window, tiering alerts by severity so only hard blocks interrupt workflow, presenting actionable alternatives ("consider eplerenone if spironolactone contraindicated by gynecomastia" rather than generic "interaction detected"), and measuring alert acceptance rather than raw fire counts. HF-CDSS maps severity to safety tiers in PostgreSQL (hard_block versus consider_with_caution) and surfaces hard blocks both in structured recommendation cards and verification verdicts before SSE answer completion, aligning quantitative alert metrics with interface design.

### 2.1.6 Heart-Failure-Specific CDSS Challenges

Heart failure imposes domain-specific demands that generic medication-interaction checkers often fail to meet. First, therapy is organized by drug class pillars rather than single-drug optimization: a patient may need an ARNI rather than "any antihypertensive," and the system must reason at class level while still resolving to agent-specific dosing from labels. Second, many constraints are conditional on laboratory and vital-sign thresholds rather than absolute bans—MRAs may be usable with eGFR above 30 mL/min/1.73 m² but require closer monitoring as renal function declines; beta blockers are contraindicated in acute decompensated HF but indicated in stable HFrEF after optimization of diuretics. Third, temporal rules govern class transitions: the 36-hour washout between ACE inhibitor and ARNI reflects overlapping RAAS blockade and angioedema risk, a constraint that flat document retrieval may miss when evidence appears in separate label sections.

Fourth, GDMT underutilization is a process problem as much as a knowledge problem: clinicians may know the guideline yet defer titration because of hypotension, hyperkalemia, or visit-time limits. Effective HF-CDSS therefore combines gap detection ("missing SGLT2i in eligible HFrEF") with actionable dose and monitoring guidance, not merely textbook summaries. Fifth, bilingual and low-resource settings add terminology variance—brand names, Vietnamese clinical shorthand, and mixed-language notes—which motivates hybrid regex-and-LLM intake rather than structured form entry alone. These challenges motivate the hybrid architecture developed in subsequent chapters: deterministic engines for auditable safety, graph and vector retrieval for scattered evidence, and LLMs for flexible language handling under verification.

## 2.2 Knowledge Graphs

### 2.2.1 Definition and Motivation

A Knowledge Graph (KG) represents knowledge as a graph of entities (nodes) and relationships (edges), often with properties and axioms that enable structured, contextual querying [4]. Unlike flat document collections, a KG makes explicit which entities participate in which relations, supporting compositional queries that traverse paths rather than relying on lexical overlap alone. In clinical informatics, graphs unify drug identities across synonyms, attach numeric properties to entities, and encode contraindications as typed edges rather than buried prose.

The motivation for graphs in CDSS is relational fidelity. A physician asking whether spironolactone is safe in a patient on lisinopril with eGFR 35 and potassium 5.1 must integrate drug–drug interaction, renal threshold, and electrolyte risk—three relation types that may appear in different documents. A well-constructed KG binds these facts to canonical drug and lab nodes, enabling multi-hop traversal and consistent retrieval at query time.

### 2.2.2 Structure: Triples, Properties, and Axioms

The atomic unit of a knowledge graph is frequently expressed as a subject–predicate–object triple, analogous to Resource Description Framework (RDF) statements: (Bisoprolol, treats, Heart_Failure), (Sacubitril/Valsartan, contraindicated_with, ACE_inhibitor), (MRA, requires_monitoring, serum_potassium). Nodes represent typed entities—drugs, drug classes, diseases, lab values, populations—while edges represent typed relations such as treats, indicated_for, contraindicated_with, interacts_with, and metabolized_by. Triples are easy to store, version, and audit: each edge can carry provenance pointing to SPL section or guideline clause.

Properties attach literal or structured values to nodes or edges: starting dose 1.25 mg, target dose 10 mg, washout window 36 hours, monitoring interval 1 week after MRA initiation. Properties turn qualitative graph topology into quantitative CDSS inputs for dose calculators and alert thresholds. Axioms encode conditional logic that triples alone cannot express cleanly, for example "do not combine ACEi with ARNI within 36 hours of the last ACEi dose" or "if eGFR < 30 then downgrade MRA recommendation to consider_with_caution." Axioms may be implemented as graph patterns plus rule-engine predicates in PostgreSQL, as shown in later design chapters.

Together, triples, properties, and axioms support both explicit fact retrieval ("What interacts with spironolactone?") and constraint-aware reasoning ("Is this patient eligible for ARNI given recent lisinopril and last dose timestamp?"). For HF-CDSS, the Neo4j graph stores entity–relation structure imported from extracted claims, while PostgreSQL holds executable constraint and dose rules with approval workflow— a deliberate split between exploratory graph traversal and governed production logic.

Axioms may be expressed as SHACL-like shape constraints, SWRL rules, or application-layer predicates; this thesis implements the latter in Python rule engines querying PostgreSQL because clinical leads can review JSON rule artifacts without graph-query expertise. The graph still documents why a rule exists—linking a constraint node to source SPL section identifiers—so explanations remain traceable even when execution lives in SQL.

### 2.2.3 Entity Linking and Normalization

Entity linking (also called entity resolution or normalization) maps surface text—"Entresto," "sacubitril/valsartan," "LCZ696," Vietnamese brand variants—to canonical graph nodes, often via RxNorm concept unique identifiers, UNII codes, or internal drug keys. Without linking, the same medication appears as disconnected nodes and multi-source fusion becomes unreliable: interaction checking might miss an edge because the patient's medication string did not match the graph's preferred label.

Linking pipelines typically combine dictionary lookup, fuzzy string matching, embedding similarity for near synonyms, and disambiguation rules when one string maps to multiple concepts (e.g., "valsartan" alone versus combination products). In ingestion, HF-CDSS normalizes drug mentions extracted from SPL and guidelines to RxNorm-aligned keys before Neo4j import and PostgreSQL rule attachment. At query time, the clinical intake lexicon performs a similar normalization on free-text medication lists so graph neighborhood expansion anchors on the correct nodes.

### 2.2.4 Multi-Hop Path Traversal

Multi-hop path traversal follows chains of relations to answer questions that no single edge resolves. Example: patient on ACEi → contraindicated_with → ARNI → treats → HFrEF reveals why a washout period matters before class switch; drug → interacts_with → potassium_sparing_agent → raises_risk → hyperkalemia connects pharmacology to a lab contraindication when potassium is elevated. Path length and relation types become first-class retrieval features, distinguishing KG-augmented systems from pure vector similarity search, which may retrieve one relevant paragraph about ARNI and another about ACEi without connecting them.

Graph query languages such as Cypher (Neo4j) express such paths declaratively. A local neighborhood query might match `(d:Drug {name: $drug})-[r*1..2]-(related)` returning drugs, conditions, and monitoring requirements within two hops. Parameterized patterns keep queries safe and reusable. Returned subgraphs become evidence context—GraphFact objects—for downstream language models and verification agents. The path structure also supports regression tests during KG construction: if no path connects ACEi to ARNI via contraindicated_with, the pipeline has likely failed to ingest a critical label constraint.

### 2.2.5 Cypher Intuition and HF Example Walkthrough

Consider a simplified heart-failure fragment. A Cypher query to find drugs contraindicated with a patient's current medication might read conceptually: match the patient's drug node, follow contraindicated_with edges to candidate drugs, optionally filter by HFrEF indication on the candidate. Another query might traverse from MRA class to monitoring_requirement nodes listing potassium and renal function checks. Unlike SQL joins on ad hoc tables, Cypher foregrounds relationship types as schema elements, which aligns with clinical thinking about interactions and indications.

Walkthrough: a physician asks whether to start sacubitril/valsartan in a patient currently on enalapril 10 mg twice daily with LVEF 30%, eGFR 45, K+ 4.8. Entity linking maps "enalapril" to an ACEi node and "sacubitril/valsartan" to an ARNI node. Graph traversal finds a contraindicated_with edge annotated with property washout_hours = 36 between ARNI and ACEi. A separate path links ARNI → indicated_for → HFrEF with LVEF threshold context in attached properties or linked guideline nodes. Lab nodes or axioms tied to MRA may not fire here but would fire if the physician also asked about adding spironolactone. The graph thus supplies structured facts for the rule engine and natural-language evidence for the LLM explanation, which must state both GDMT benefit and washout requirement.

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

**Figure 2.1.** Knowledge graph fragment for heart-failure drugs.

### 2.2.6 Biomedical Knowledge Resources

Notable biomedical resources include the Unified Medical Language System (UMLS), which integrates concepts and lexical variants across vocabularies; SNOMED CT for clinical terminology and hierarchical disease classification; DrugBank and PubChem for pharmacology, targets, and structured drug attributes; and RxNorm for medication normalization in prescribing systems. Disease ontologies and guideline corpora provide complementary coverage: ontologies excel at hierarchical classification (HFrEF as a subtype of heart failure with links to comorbidities), while FDA Structured Product Labels and society guidelines supply numeric dosing detail, boxed warnings, and nuanced conditional language.

HF-CDSS draws primarily on DailyMed SPL XML for agent-level dosing and warnings, ESC and AHA/ACC/HFSA guideline documents for class-level GDMT recommendations, and extracted interaction and constraint claims merged into PostgreSQL and Neo4j. UMLS and SNOMED inform terminology alignment where implemented; RxNorm-style keys reduce duplication across sources. The graph does not attempt to replicate entire UMLS—scope is heart-failure pharmacotherapy—but leverages the same normalization principles.

UMLS Metathesaurus concept unique identifiers (CUIs) link synonymous terms across vocabularies, enabling a mention of "CHF," "heart failure," and "cardiac failure" to resolve to one condition node when mapping is available. SNOMED CT provides compositional clinical concepts with IS-A hierarchies: heart failure disorder subtypes, comorbidities such as chronic kidney disease, and finding concepts for laboratory results. DrugBank contributes mechanistic and interaction annotations useful during relation extraction validation; RxNorm supplies prescribable drug names and dose forms essential for matching patient medication lists to label entities. In practice, HF-CDSS prioritizes RxNorm-aligned drug keys and internally curated GDMT class taxonomies because full UMLS/SNOMED licensing and complete imports exceed thesis scope, but the literature foundation assumes these resources when scaling to hospital-wide deployments integrated with FHIR terminology services.

### 2.2.7 Application in CDSS

Knowledge graphs support CDSS by representing drug–disease–lab relations explicitly, enabling multi-hop reasoning over clinical pathways (GDMT class sequencing and interaction chains), providing contextual retrieval grounded in structured semantics rather than embedding chance alone, and supporting personalization when patient state is bound to graph traversals (filtering contraindicated nodes before recommendation). For heart failure, the graph encodes not only which drug classes treat HFrEF but also cross-class constraints that vector retrieval may omit when evidence is scattered across document sections. Graph retrieval in HF-CDSS runs in parallel with dense and sparse chunk retrieval, with ranks fused before generation—developing the GraphRAG pattern in Section 2.5.

## 2.3 Retrieval-Augmented Generation (RAG)

### 2.3.1 Definition and Motivation

Retrieval-Augmented Generation (RAG) combines information retrieval with LLM generation so that answers are conditioned on external evidence rather than parametric memory alone [5]. The central motivation in medicine is grounding: tying each claim to retrievable sources reduces hallucination and supports audit trails required for clinical decision support. Parametric LLM weights encode statistical regularities from training corpora but do not guarantee current label text, local formulary availability, or patient-specific constraint satisfaction.

RAG reframes the LLM as a reader–summarizer over a curated knowledge base updated independently of model weights. When guidelines change—such as expanded SGLT2i indication in HFrEF—updating indexed chunks and graph edges refreshes system behavior without retraining the generator. For regulated or privacy-sensitive environments, RAG also allows knowledge to remain on-premises in PostgreSQL, ChromaDB, and Neo4j while the LLM performs local inference via Ollama.

### 2.3.2 Dense Retrieval and Bi-Encoders

Dense retrieval uses bi-encoder models—two encoders that map queries and documents independently into a shared embedding space—to score candidates by vector similarity. Models such as BGE-M3, E5, and MedCPT produce fixed-dimensional embeddings; at query time, approximate nearest-neighbor search in a vector store returns semantically similar passages even when wording differs. The bi-encoder design encodes query and document separately, enabling precomputation of document vectors at index time and fast query-time lookup—critical for sub-10-second clinical chat targets.

Dense methods excel at synonymy and paraphrase ("reduced EF" versus "low ejection fraction," "ARNI" versus "neprilysin inhibitor") but can miss rare exact tokens such as obscure brand names, numeric lab cutoffs, or regulatory phrases absent from training-like contexts. Domain-specific encoders and metadata filtering mitigate but do not eliminate this gap—motivating hybrid sparse retrieval.

### 2.3.3 Sparse Retrieval: TF-IDF and BM25

Sparse retrieval relies on lexical statistics without neural inference at query time. Term frequency–inverse document frequency (TF-IDF) weights terms by their frequency in a document penalized by corpus rarity: frequent terms in a chunk score highly, but terms common across the entire corpus receive lower inverse-document-frequency weight. TF-IDF is simple and interpretable but treats document length crudely and lacks term saturation—repeating a word indefinitely continues to boost score.

BM25 (Best Matching 25) extends TF-IDF with document-length normalization and term-frequency saturation, yielding robust keyword ranking widely used in search engines and clinical IR baselines. Intuitively, BM25 asks how well a query's terms overlap a document's terms, down-weighting very long documents that accumulate incidental matches and capping the marginal gain from repeated term occurrences. A document that mentions "spironolactone," "hyperkalemia," and "eGFR" twenty times is not twenty times better than one that mentions each once clearly in a contraindications section.

Formally, BM25 scores a document \(d\) for query \(q\) by summing over query terms \(t\): each term contributes an inverse document frequency factor multiplied by a saturated term-frequency function in \(d\), divided by a length-normalization term that prevents long SPL sections from dominating rankings merely because they contain more tokens. Parameters \(k_1\) and \(b\) control saturation and length normalization respectively; default values from classical IR literature perform adequately on clinical chunk corpora without per-deployment tuning. In HF-CDSS, BM25 runs over the same sentence-aware chunks indexed in ChromaDB, so dense and sparse retrievers share provenance metadata—a prerequisite for meaningful RRF fusion and consistent citation in verification. Sparse methods excel at exact entity mentions and regulatory phrases ("contraindicated in severe renal impairment," "36 hours") but weakly connect conceptually related text with different vocabulary.

Hybrid pipelines run dense and sparse retrievers in parallel and fuse ranked lists—a pattern adopted in HF-CDSS because clinical queries blend semantic intent ("Can I start MRA in CKD stage 4?") with lexical anchors (spironolactone, eGFR 22, potassium 5.6).

### 2.3.4 Hybrid Retrieval and Score Fusion

Hybrid retrieval acknowledges that neither dense nor sparse methods dominates all query types. Clinical questions may arrive as short telegraphic prompts, long pasted discharge summaries, or bilingual mixed text. Running ChromaDB dense search and BM25 over the same chunk corpus, then merging with Reciprocal Rank Fusion (Section 2.5.4), avoids calibrating incompatible raw score scales. Optional second-stage reranking further sharpens the top of the fused list when latency budget permits.

Metadata pre-filtering narrows retrieval to relevant corpora subsets: chunks tagged as contraindications, dosing, or guideline class recommendations for HFrEF. Pre-filtering before similarity search reduces noise and mirrors clinician behavior of opening the WARNINGS section first rather than reading the entire label.

### 2.3.5 Chunking Strategies

Chunking splits long guidelines and drug labels into retrieval units sized to embedding model limits and reader attention. Naive fixed-length splits break clinical sentences mid-thought, separating conditions from consequences ("Do not use if..." in one chunk, "...eGFR below 30" in the next). Sentence-aware chunking with controlled overlap preserves local context while keeping chunks within practical bounds; HF-CDSS uses approximately 512-token windows with overlap so contraindications spanning two sentences appear intact in at least one chunk.

Section headers from SPL XML or PDF outlines define natural boundaries: DOSAGE AND ADMINISTRATION, WARNINGS AND PRECAUTIONS, DRUG INTERACTIONS. Section-aware chunking also supports provenance: retrieved passages cite source document and section code for verification agents. Overlap size trades storage cost against recall; heart-failure labels repeat critical warnings in multiple sections, so modest overlap reduces missed retrieval when the same fact appears in both interactions and warnings.

Parent-child chunk hierarchies represent an advanced pattern not fully deployed in initial HF-CDSS but common in literature: a short summary chunk points to longer child chunks for detail retrieval. For GDMT guidelines, a parent chunk might summarize class recommendations while children hold trial citations and dosing tables. Flat sentence-aware chunking was chosen for implementation simplicity and because SPL sections already provide logical boundaries; hierarchical indexing remains a documented extension when corpus size grows beyond single-collection search latency thresholds.

### 2.3.6 Vector Stores and HNSW Indexing

Vector stores (ChromaDB, FAISS, Milvus, pgvector) persist embedding vectors with metadata filters. Index structures such as HNSW (Hierarchical Navigable Small World) graphs enable sub-linear approximate nearest-neighbor search over large corpora by maintaining a multi-layer graph where greedy search along edges rapidly approaches true nearest neighbors. HNSW trades exact recall for speed and memory efficiency—acceptable in CDSS when top-k is small and reranking follows.

Metadata—source type, drug class, document section, chunk type—supports pre-filtering before similarity scoring. ChromaDB in HF-CDSS stores BGE-M3 embeddings over clinical chunks filtered during ingestion, with collection metadata enabling scope limits (single drug label versus full GDMT guideline set) at query time.

### 2.3.7 Classical RAG Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Query     │───→│   Retriever  │───→│    LLM      │
│  (User)     │    │ (Embedding)  │    │  (Generate) │
└─────────────┘    └──────────────┘    └─────────────┘
                          │                   ↑
                          ↓                   │
                   ┌──────────────┐          │
                   │ Vector Store  │──────────┘
                   │ (Knowledge)   │
                   └──────────────┘
```

**Figure 2.2.** Classical RAG architecture.

Typical components include one or more retrievers (dense bi-encoder, sparse BM25), a vector store (ChromaDB in this project), optional rerankers (cross-encoder or API-based), and a generator LLM instructed to cite retrieved passages. Classical RAG does not include graph traversal; Section 2.5 extends this diagram with Neo4j facts and RRF fusion.

### 2.3.8 RAG in Healthcare: Challenges and Failure Modes

Healthcare applications include medical question answering, similar-case retrieval, drug lookup, and clinical note summarization. Challenges arise from high accuracy requirements (errors can harm patients), specialized terminology requiring domain embeddings, multi-factor patient context that must filter evidence, and the need for continuous knowledge updates as labels and guidelines revise. RAG does not eliminate error—it shifts failure modes from parametric hallucination to retrieval omission (the right passage was not in top-k), mis-ranking (a generic HF overview outranks a specific contraindication), or misinterpretation (the LLM ignores retrieved text).

Clinical CDSS therefore pairs RAG with deterministic safety rules and human review. Verification agents in HF-CDSS check that cited chunk identifiers were actually retrieved and that hard-block constraints were evaluated by the rule engine, not inferred by the LLM alone.

Cross-encoders, mentioned again in Section 2.5.4, differ from bi-encoders by jointly encoding query and candidate passage in a single forward pass, producing a scalar relevance score that captures fine-grained token interactions. They are too expensive to score entire corpora at index time but effective as rerankers over fused top-50 lists. The engineering trade-off—bi-encoder for recall, cross-encoder or API reranker for precision at the top of the list—is standard in modern clinical IR stacks and matches HF-CDSS configuration options documented in later chapters.

## 2.4 Large Language Models (LLM)

### 2.4.1 Definition and Historical Context

Large language models are neural language models trained on large text corpora with billions of parameters, optimized to predict token sequences. Milestones include the Transformer architecture (2017) [6], GPT-3 (2020) [7], and subsequent instruction-tuned and reinforcement-learning–aligned systems that follow natural-language directives. Scale, self-supervised pretraining on diverse text, and alignment fine-tuning produced general-purpose models capable of drafting clinical prose, extracting structured fields from narratives, and answering exam-style medical questions—while still requiring external grounding for prescribing decisions.

In CDSS, LLMs primarily serve explanation, semantic extraction, query expansion, and verification—not unbounded autonomous prescribing. HF-CDSS assigns Qwen2.5-7B-Instruct to clinician-facing answers and Qwen2.5-1.5B to lighter tasks (HyDE, borderline section review, verification agents), all via local Ollama inference.

### 2.4.2 Transformer Architecture and Governing Equations

Scaled dot-product attention is the core governing equation of modern LLMs:

\[
\mathrm{Attention}(Q, K, V) = \mathrm{softmax}\!\left(\frac{QK^{\mathsf{T}}}{\sqrt{d_k}}\right) V
\]

where \(Q\), \(K\), and \(V\) are query, key, and value matrices derived from input embeddings, and \(d_k\) is the key dimension. The scaling factor \(\sqrt{d_k}\) stabilizes gradients as dimension grows. Each query vector attends over all keys, producing a convex combination of values that weights context tokens by relevance—allowing the model to relate "eGFR 22" to "renal impairment" across distance in the token sequence.

Multi-head attention concatenates \(h\) parallel heads with distinct learned projections:

\[
\mathrm{MultiHead}(Q, K, V) = \mathrm{Concat}(\mathrm{head}_1,\ldots,\mathrm{head}_h)\,W^{O}
\]

\[
\mathrm{head}_i = \mathrm{Attention}(QW_i^{Q}, KW_i^{K}, VW_i^{V})
\]

Stacked encoder and decoder blocks (in encoder–decoder models) or decoder-only stacks (GPT-style) compose depth; feed-forward sublayers and residual connections enable training at scale. Positional encodings (sinusoidal or rotary) inject order information because attention alone is permutation-invariant. These formulations enable parallelizable computation during training, long-range dependency modeling critical for clinical narratives, and parameter scalability that stores broad medical facts implicitly—while also creating hallucination risk when implicit memory contradicts retrieved evidence.

### 2.4.3 Prompting Techniques

Chain-of-thought (CoT) prompting elicits intermediate reasoning steps before a final answer ("First identify HF phenotype; then list missing GDMT classes; then check renal contraindications…"), improving multi-step clinical tasks at the cost of latency and token usage. CoT traces support clinician inspection when aligned with retrieved evidence, though models may produce plausible-sounding but incorrect reasoning chains—motivating verification agents.

Few-shot prompting supplies exemplar input–output pairs in the context window to steer format and clinical tone without weight updates. HF-CDSS uses schema-constrained JSON extraction prompts with examples for structured rule extraction during ingestion, reducing format errors compared to zero-shot requests.

Human-in-the-loop (HITL) workflows keep physicians as the final decision authority: the system proposes drafts, surfaces evidence, and records verification verdicts rather than placing orders autonomously. Clinical leads approve or retire rules in PostgreSQL governance workflows; bedside clinicians review recommendation cards and may override soft cautions. HF-CDSS applies HITL at multiple points—rule approval, chat recommendations, and optional dismissal of non-blocking alerts.

### 2.4.4 Medical and Biomedical Language Models

Domain models include BioBERT, ClinicalBERT, BlueBERT, Med-PaLM, and GatorTron, adapted through continued pretraining on biomedical and clinical text. They improve entity recognition, entailment, and domain QA benchmarks relative to general models. Applications span report generation, diagnostic assistance, literature search, and medical education. For retrieval, MedCPT and similar bi-encoders align embedding space with clinical question–passage pairs; BGE-M3 provides multilingual dense retrieval used in this thesis for section filtering and Chroma indexing.

Medical LLMs remain subject to knowledge cutoffs, underrepresentation of non-English corpora, and uneven coverage of local prescribing practices. HF-CDSS mitigates these limits by RAG over locally ingested SPL and guideline artifacts and by deterministic GDMT engines that do not depend on model parametric memory for core safety.

### 2.4.5 Hallucination: Taxonomy and Mitigations

Hallucination—fluent but factually incorrect or unsupported statements—is the primary LLM risk in clinical use. A useful taxonomy distinguishes intrinsic hallucinations (contradicting provided context or retrieved passages) from extrinsic hallucinations (introducing facts not present in context, such as invented drug doses or fabricated trial citations). Another axis separates factual errors from unwarranted certainty ("definitely start 49 mg twice daily" when labeling specifies titration).

Mitigations layered in HF-CDSS include RAG grounding with mandatory citations to retrieved chunk identifiers; CoT for inspectable reasoning traces; few-shot exemplars demonstrating conservative language; structured output schemas (JSON patient profiles, constraint objects validated by Pydantic); deterministic post-checks (rule engine, verification agents comparing recommendations to retrieved evidence); tiered safety classification (hard_block versus consider_with_caution); and mandatory human review before action. Training bias and knowledge cutoffs further require versioned knowledge bases and governance workflows for rule updates when labels change.

### 2.4.6 Local Inference with Ollama

Local inference via Ollama supports air-gapped or privacy-sensitive environments where cloud API routing is unacceptable. Ollama serves quantized model weights on hospital GPUs or workstations, exposing HTTP endpoints compatible with application code. Benefits include data residency, predictable per-deployment cost, and immunity to external API rate limits or policy changes. Trade-offs include operator responsibility for model updates, hardware sizing, and typically smaller models than frontier cloud APIs—acceptable when LLMs are not the sole decision authority. HF-CDSS configures Ollama for BGE-M3 embeddings and Qwen2.5 generation models, with Redis caching of repeated LLM responses to reduce load during multi-turn conversations.

Quantization (4-bit or 8-bit weight representations) reduces VRAM requirements so 7B-parameter instruct models fit consumer-grade GPUs such as the RTX 3080 used in thesis evaluation, at modest perplexity cost. Embedding models impose separate memory footprints; pipeline design batches embedding calls during ingestion while interleaving chat generation and retrieval at query time to avoid GPU contention. These operational considerations belong in literature review because they constrain which LLM roles—explanation versus extraction versus verification—can run concurrently under a 10-second latency target.

## 2.5 GraphRAG — Combining Knowledge Graphs and RAG

### 2.5.1 Definition and Rationale

GraphRAG augments retrieval and generation with graph structure and, in community-based variants, cluster-level summaries, as popularized by Microsoft Research [8]. The unifying idea is that some clinical questions require relational context—interactions, class hierarchies, temporal constraints—that flat chunk retrieval approximates poorly. GraphRAG does not replace vector RAG; it complements it by supplying structured facts and subgraphs fused with textual evidence before generation.

For heart failure, questions like "Why must I wait before switching from ramipril to Entresto?" require linking two drug nodes through a typed contraindication with temporal property—a graph-native query. Questions like "What titration schedule does the label recommend for bisoprolol in HFrEF?" may be answered by a single dense-retrieved dosing chunk. GraphRAG pipelines orchestrate both.

### 2.5.2 Comparison with Vector RAG

| Criterion | Vector RAG | GraphRAG |
|-----------|------------|----------|
| Relationship understanding | Limited | Strong |
| Multi-hop retrieval | Difficult | Natural |
| Contextual reasoning | Weaker | Stronger |
| Global / thematic queries | Hard | Better |
| Semantic similarity | High | High |
| Engineering complexity | Lower | Higher |

**Table 2.1.** Comparison of Vector RAG and GraphRAG.

Vector RAG retrieves similar text; GraphRAG additionally retrieves structured facts and subgraphs, then fuses them with textual evidence before generation. HF-CDSS implements a pragmatic subset: local entity-centric Neo4j traversal plus hybrid chunk retrieval, without full offline community summarization at initial deployment—though community summaries remain an extensibility path as the graph grows.

### 2.5.3 Local versus Global Search

Local search begins from entities mentioned in the patient profile or query—medications, conditions, lab abnormalities—and expands their \(N\)-hop neighborhood in the graph. For heart failure, local expansion from "spironolactone" might retrieve interacts_with edges to ACEi, contraindication predicates tied to eGFR and potassium, and class membership in MRA. Local search is patient-specific and supports personalized safety checks and explanation ("given your current enalapril and potassium, note hyperkalemia risk when adding MRA").

Global search (in community GraphRAG) aggregates community summaries over densely connected subgraphs—for example, a "GDMT four pillars" community—to answer thematic questions ("What is the standard HFrEF pharmacotherapy bundle?") without anchoring on a single drug node. Global summaries are precomputed during indexing by clustering related entities and summarizing clusters with an LLM. HF-CDSS emphasizes local entity-centric graph retrieval synchronized with hybrid chunk search for query-time latency and because GDMT gap analysis is already handled deterministically; global summaries would add value for educational overviews and nurse onboarding flows in future work.

Community detection algorithms (Louvain, Leiden) optimize modularity on the entity graph to find clusters such as RAAS-inhibitor families, diuretic adjuncts, or device therapy nodes. Each community receives an LLM-generated summary stored as a pseudo-document retrievable alongside text chunks. The construction cost is offline and amortized over many queries; the risk is summary staleness when guidelines change, requiring re-clustering when major graph updates occur. For a focused HF pilot, local search plus deterministic GDMT engines cover the highest-priority query types; community GraphRAG remains documented as the scaling path when the knowledge graph expands beyond pharmacotherapy into comorbidity and device domains.

### 2.5.4 Ranking Equations and Query Enhancement

Hybrid retrieval fuses ranked lists with Reciprocal Rank Fusion (RRF):

\[
\mathrm{Score}_{\mathrm{RRF}}(d) = \sum_{r \in R} \frac{1}{k + \mathrm{rank}_r(d)}
\]

where \(R\) is the set of retrievers (dense embedding search, BM25, graph-derived evidence channels), \(\mathrm{rank}_r(d)\) is the rank of document or chunk \(d\) under retriever \(r\), and \(k\) is a smoothing constant (commonly 60, configurable as `graphrag_rrf_k` in HF-CDSS). RRF avoids calibrating incompatible score scales across retrievers—a practical advantage when cosine similarities and BM25 scores coexist. Documents that rank highly in multiple lists accumulate larger RRF scores; documents strong in only one modality still surface if that retriever ranks them first.

Cosine similarity for dense retrieval is:

\[
\mathrm{sim}(q, d) = \frac{\mathbf{e}_q \cdot \mathbf{e}_d}{\|\mathbf{e}_q\|\,\|\mathbf{e}_d\|}
\]

where \(\mathbf{e}_q\) and \(\mathbf{e}_d\) are query and document embeddings from a bi-encoder such as BGE-M3. Embeddings are typically L2-normalized so cosine similarity equals dot product, simplifying index search.

Hypothetical Document Embeddings (HyDE) expand short or ambiguous clinical queries by prompting a small LLM to generate a hypothetical answer document, then embedding that document for dense retrieval [9]. The hypothetical text occupies the same semantic neighborhood as true guideline passages, improving recall when physicians ask brief questions ("start ARNI?") that poorly match label wording. HyDE can misfire if the hypothetical document invents incorrect facts; combining HyDE with BM25, graph facts, and verification reduces but does not zero that risk—another reason deterministic rules remain authoritative.

Query decomposition splits a compound clinical question into sub-queries—medication class, renal safety, interaction check—each retrieved independently before fusion, reducing single-query embedding averaging effects where one embedding must represent multiple intents. Decomposition adds latency proportional to sub-query count and is applied selectively when enabled in configuration.

Reranking applies a second-stage scorer to the top-\(k\) candidate pool: a bi-encoder rescore combining semantic similarity with first-stage scores, or a cross-encoder/API reranker (Cohere rerank-v3.5 optional in HF-CDSS) that jointly encodes query and document for finer discrimination at higher compute cost. Cross-encoders are more accurate than bi-encoders for pairwise relevance but cannot precompute document representations—hence two-stage retrieve-then-rerank pipelines.

```
Construction → Indexing → Hybrid Query → Generation
     │              │            │
     KG build    Communities   Local + Global
     Chunk embed  Summaries    RRF + Rerank
```

**Figure 2.3.** GraphRAG pipeline overview (construction → indexing → hybrid query → generation).

### 2.5.5 Why GraphRAG for Heart-Failure CDSS

GraphRAG fits CDSS because drug–disease–lab knowledge is inherently relational, clinical reasoning is often multi-step (washout → class switch → dose titration), patient context spans many interacting variables, and graph structures are extensible when guidelines update without re-embedding entire corpora. Heart-failure therapy explicitly references class relationships (ACEi/ARB/ARNI interchange rules), combination effects (RAAS blockade plus MRA plus SGLT2i), and monitoring dependencies (potassium after MRA, creatinine after RAAS inhibitor)—all natural graph edges.

The HF-CDSS implementation runs GraphRAG primarily as an evidence and explanation layer parallel to a deterministic GDMT rule engine, preserving safety audibility while improving narrative grounding. Structured recommendation status (continue, consider, avoid) comes from PostgreSQL rules; GraphRAG supplies passages and graph facts the LLM must cite when explaining why. This separation implements a design pattern increasingly recommended in clinical AI literature: small, verifiable modules for decisions; larger models for language interfaces.

## 2.6 Medical Knowledge Graph Construction

### 2.6.1 Characteristics of Medical Knowledge Graphs

Medical KGs feature diverse entity types (drugs, classes, conditions, labs, procedures), rich relation vocabularies (contraindication, dose_adjustment, monitoring, indicated_for), numeric properties (doses in mg, thresholds in mEq/L or mL/min/1.73 m²), temporal constraints (36-hour washout, 1-week potassium recheck), and graded evidence reliability (randomized trial versus case report versus label text). Heart-failure KGs must reconcile guideline narrative ("four pillars of GDMT") with FDA SPL numeric detail (starting and target doses per agent). Conflicts may arise when guideline strength class and label wording differ; governance workflows mark rules as draft until clinical leads resolve discrepancies.

Quality dimensions include completeness (are all GDMT classes represented?), correctness (do edges match authoritative sources?), consistency (no contradictory contraindication edges), and currency (updated after label revisions). Automated extraction accelerates construction but increases false-positive relation risk—motivating human approval before production use.

### 2.6.2 Construction Sources

Construction draws on structured sources such as DrugBank, UMLS/SNOMED, FDA SPL XML, and RxNorm; unstructured sources including ESC/AHA/HFSA guidelines, clinical trials registries, and literature; and hybrid pipelines that parse SPL section codes alongside HTML guideline excerpts. HF-CDSS ingests DailyMed SPL labels and society guideline documents into versioned JSONL artifacts before PostgreSQL governance and Neo4j import. Raw XML/PDF/HTML resides in object storage; processed chunks, claims, and relationships sync to runtime data directories for reproducible pipeline reruns.

Structured sources provide identifiers and sometimes pre-curated interactions; unstructured sources provide narrative rationale and class-level recommendations less likely to exist as ready-made triples. The pipeline must therefore support both regex-friendly SPL sections and noisier PDF guideline layouts.

### 2.6.3 Construction Pipeline Stages

The typical workflow proceeds from data acquisition and preprocessing (XML/HTML/PDF parsing, section extraction) through terminology normalization (drug name canonicalization, unit standardization to SI/clinical conventions). Named entity recognition (NER) identifies drugs, conditions, labs, and populations in text—via lexicons, regular expressions, or transformer taggers. Relation extraction (RE) classifies statements into typed edges: contraindication, interaction, indication, dose adjustment. Entity linking maps mentions to canonical identifiers. Knowledge fusion merges duplicate nodes and resolves conflicts across sources (label versus guideline strength differences). Quality assurance includes automated consistency checks and expert review before rules reach approved status. Question answering (QA) over the finished KG validates multi-hop reachability and supports regression tests ("Is ARNI reachable from ACEi via contraindicated_with?").

Downstream sync splits artifacts: constraint, dose, interaction, and GDMT policy rules into PostgreSQL with version and approval columns; entity–relation bundles into Neo4j; chunks into ChromaDB with metadata linking back to source SPL or guideline identifiers. This multi-store pattern matches how different query operations optimize: SQL filters for governed rules, graph traversal for relational exploration, vector search for free-text evidence.

Named entity recognition in heart-failure corpora targets drug names (generic and brand), drug classes (ACEi, MRA, SGLT2i), conditions (HFrEF, CKD, diabetes), laboratory names and values (eGFR 38, K+ 5.3), and population qualifiers (pregnancy, angioedema history). Relation extraction maps natural-language statements to typed edges: "avoid concurrent use" becomes contraindicated_with; "reduce starting dose in renal impairment" becomes dose_adjustment with eGFR predicate; "monitor serum potassium" becomes requires_monitoring. LLM-assisted extraction with JSON schema constraints supplements pattern-based extractors on ambiguous guideline sentences where multiple relations co-occur in one clause. Quality assurance includes pairwise contradiction detection (two sources asserting incompatible washout windows), orphan entity reports (drug nodes without indication or class membership), and spot checks by clinical leads before approval—mirroring pharmacovigilance workflows adapted to knowledge engineering.

### 2.6.4 Three-Tier Section Filter Theory

Section filtering during ingestion uses a three-tier cascade aligned with cost-aware clinical NLP design. Tier 1 applies high-precision keyword matching on clinical headings and SPL section codes (DOSAGE AND ADMINISTRATION, WARNINGS AND PRECAUTIONS, CONTRAINDICATIONS, DRUG INTERACTIONS). Keyword matching is fast, deterministic, and incurs no GPU cost; it captures the majority of clearly labeled clinical content in structured SPL XML.

Tier 2 scores remaining sections with dense semantic similarity: section text is embedded with BGE-M3 and compared to prototype embeddings of clinical section types. Sections with cosine similarity at or above a keep threshold (0.52 in HF-CDSS configuration) are retained without LLM review. This tier recovers paraphrased or inconsistently titled sections common in guideline PDFs where headings do not match SPL vocabulary.

Tier 3 sends borderline sections—similarity in the uncertain band between low threshold 0.40 and keep threshold 0.52—to a small LLM (Qwen2.5-1.5B) for binary clinical-relevance classification. Sections below 0.40 are dropped as likely administrative, copyright, or non-clinical boilerplate. This cascade minimizes LLM calls while preserving recall: evaluation in Chapter 5 reports that roughly 96.6% of sections avoid LLM review, with 95.0% overall retention of clinically relevant content. The three-tier design embodies a general principle for medical AI pipelines: deploy expensive models only on inputs where cheaper methods abstain.

## 2.7 Heart Failure Clinical Foundations for CDSS

Computer-science readers require sufficient clinical context to understand why HF-CDSS rules and retrieval scopes are shaped as they are. This section summarizes HFrEF phenotype, GDMT pillars, key monitoring variables, and class-transition constraints at a depth adequate for thesis design without reproducing a full cardiology curriculum.

### 2.7.1 Phenotype: HFrEF versus HFpEF

Heart failure is a clinical syndrome of structural or functional cardiac abnormality with symptoms and signs; classification by left ventricular ejection fraction (LVEF) separates HF with reduced EF (HFrEF, typically LVEF ≤ 40%), mildly reduced EF (HFmrEF), and preserved EF (HFpEF, typically LVEF ≥ 50%). GDMT pillars emphasized in contemporary guidelines—RAAS inhibition with ACEi/ARB/ARNI, beta blockers, MRAs, and SGLT2 inhibitors—have strongest outcome evidence in HFrEF. HF-CDSS focuses on HFrEF GDMT optimization where class-level rules and labeling are most standardized; HFpEF pharmacotherapy is less uniform and often centers on comorbidity management (e.g., SGLT2i benefits in selected populations). Phenotype therefore gates recommendations: the intake pipeline extracts LVEF when documented and derives HFrEF eligibility before suggesting ARNI or certain class starts.

### 2.7.2 Four GDMT Pillars and Brief Pharmacology

The four pillars of HFrEF GDMT are (1) renin–angiotensin system inhibition via ACE inhibitor, ARB, or ARNI; (2) evidence-based beta blockers (bisoprolol, carvedilol, metoprolol succinate); (3) mineralocorticoid receptor antagonists (spironolactone, eplerenone); and (4) SGLT2 inhibitors (dapagliflozin, empagliflozin). Each reduces morbidity and mortality through partially overlapping hemodynamic and neurohormonal mechanisms.

ACE inhibitors and ARBs block angiotensin II effects and reduce afterload; ARNI combines valsartan with sacubitril, a neprilysin inhibitor that elevates natriuretic peptides while blocking angiotensin signaling—superior to ACEi alone in pivotal trials but constrained by washout rules when switching from ACEi. Beta blockers antagonize chronic sympathetic activation in stable HFrEF; they require gradual uptitration and are avoided in decompensated acute HF with volume overload until stabilization. MRAs antagonize aldosterone, reducing remodeling and hospitalization but increasing hyperkalemia risk, especially with concurrent RAAS blockade. SGLT2 inhibitors originally for diabetes reduce HF hospitalizations and cardiovascular death in HFrEF even in non-diabetic patients, with diuretic-like and metabolic effects. CDSS must reason at class level ("missing MRA") while resolving to agent-specific doses from SPL catalogs.

### 2.7.3 Key Laboratories and Vitals: eGFR, Potassium, Blood Pressure, Heart Rate

Renal function (eGFR) gates MRA and dose adjustment for many agents; severe renal impairment increases hyperkalemia and toxicity risk. Serum potassium (K+) monitoring is essential when combining RAAS inhibitors with MRAs; thresholds near 5.0–5.5 mEq/L often trigger caution or hold per label and guideline excerpts. Blood pressure limits uptitration of RAAS agents, ARNI, and beta blockers; symptomatic hypotension may require dose delay or diuretic adjustment before GDMT intensification. Heart rate affects beta-blocker tolerance; bradycardia may cap dose. HF-CDSS extracts these fields via hybrid intake, derives eGFR from creatinine when needed using deterministic formulas, and feeds values into constraint and dose engines—not into the LLM alone.

### 2.7.4 Washout: ACEi to ARNI Transition

A distinctive HFrEF constraint is the mandatory washout period between ACE inhibitor and ARNI initiation—typically 36 hours—because combined ACE inhibition with neprilysin inhibition increases angioedema risk. This is a temporal rule, not a permanent contraindication: ARNI is appropriate after washout in eligible HFrEF. CDSS must capture last ACEi dose timing when available and emit hard-block or consider_with_caution statuses accordingly; graph edges encode the drug-class relationship while PostgreSQL rules encode executable washout logic. Vector retrieval alone often retrieves ARNI benefits and ACEi–ARNI warnings in separate chunks; graph and rule layers exist precisely to enforce such compositional constraints.

### 2.7.5 Titration, Monitoring, and CDSS Implications

GDMT benefits accrue when agents are uptitrated toward target doses tolerated by the patient, not merely initiated at starting dose. Labels specify starting doses, doubling intervals, and maximum recommended doses for bisoprolol, carvedilol, sacubitril/valsartan, spironolactone, and SGLT2i agents; guidelines emphasize reassessment of blood pressure, heart rate, potassium, and renal function after each change. HF-CDSS dose-rule catalogs encode these schedules as JSONB objects queried by the dosing engine, separate from narrative retrieval. Monitoring intervals—such as potassium within one week of MRA initiation or creatinine after RAAS inhibitor dose increase—appear as monitoring_requirement relations in the graph and as consider_with_caution prompts when recent labs are stale or missing.

From a computer-science perspective, titration support requires stateful patient profiles (current dose step, date of last change) rather than stateless question answering. The hybrid intake pipeline therefore extracts not only drug names but dose strings and units where documented, normalizing "half a 49/51 tablet" and "1.25 mg bisoprolol" into structured fields when patterns allow. Missing temporal fields trigger clarification or conservative recommendations rather than silent assumption—consistent with HITL and safety-tier design. These clinical foundations explain why the thesis treats GDMT gap detection, constraint checking, and dose calculation as deterministic services while GraphRAG supplies explanatory evidence rather than inventing titration schedules.

## 2.8 Implementation Technologies

### 2.8.1 Backend Services

FastAPI provides async HTTP APIs with OpenAPI schema generation, Pydantic validation, and dependency-injected authentication—fitting CDSS needs for typed clinical payloads, low-latency streaming endpoints, and automatic request documentation. Async handlers allow concurrent retrieval over ChromaDB, BM25, Neo4j, and Ollama without blocking worker threads during I/O-bound inference and database calls.

PostgreSQL stores governance artifacts—constraint rules, dose rules, interaction rules, GDMT policies—with version history and approval workflow; JSONB columns hold structured dose schedules and renal adjustment objects queryable at runtime without schema migration for every new agent variant. Relational storage suits transactional rule approval, audit logs, and RBAC-linked user records.

Redis caches approved rule snapshots, conversation drafts, message history, and LLM response hashes—reducing repeated database and inference load during multi-turn chat. Cache TTLs balance freshness after rule updates against latency; rule snapshots invalidate when clinical leads publish new approved versions.

ChromaDB persists BGE-M3 embedding vectors over clinical chunks with metadata filters for hybrid dense retrieval. It integrates cleanly with Python ingestion jobs and supports collection-per-corpus or unified collection strategies; HF-CDSS indexes filtered chunks with drug and section metadata for scoped queries.

Neo4j hosts the clinical knowledge graph queried via Cypher for neighborhood expansion and typed fact retrieval. Property graph models align naturally with drug–interaction–disease relations; Neo4j's mature tooling supports batch import from JSONL relationship files produced by the ingestion pipeline.

Ollama serves local Qwen2.5 models for chat generation, HyDE expansion, selective intake extraction, borderline section review, and verification agents—supporting deployment without mandatory cloud LLM routing. Embedding and generation models can share GPU with sequential scheduling or run on separate instances depending on hardware.

### 2.8.2 Frontend and Streaming Delivery

React 18 with Vite delivers a responsive clinician dashboard; utility CSS supports rapid layout iteration. Component hooks manage server state, conversation history, and bilingual UI strings. Server-Sent Events (SSE) stream typed pipeline events (`draft_ready`, `recommendation_ready`, `verification_ready`, `answer_delta`, `done`) so physicians see patient parsing and safety checks complete before narrative tokens arrive—preserving situational awareness during multi-second inference. SSE is unidirectional server-to-client, simpler than WebSockets for one-way answer streaming, and passes standard HTTP proxies when configured with appropriate buffering disabled for TLS terminators.

The ClinicalPanel presents structured recommendation cards (drug class, status, dose guidance, plain-language summaries) decoupled from LLM prose, implementing the Five Rights' "right format" principle.

### 2.8.3 Infrastructure and Deployment

Docker Compose orchestrates backend, PostgreSQL, Redis, Neo4j, ChromaDB, LocalStack (S3-compatible storage in development), and optional GPU-enabled Ollama containers. Containerization reproduces environments across developer laptops and evaluation servers documented in Chapter 5. Nginx terminates TLS and reverse-proxies to FastAPI, setting headers for SSE compatibility. S3-compatible storage holds versioned ingestion artifacts (raw SPL, chunks, claims, relationships JSONL) synchronized into runtime data directories on deploy or pipeline completion—supporting reproducibility and rollback when a bad extraction batch is detected.

Security and compliance considerations follow from CDSS handling clinical narratives even in research pilots. JWT authentication with role-based access control limits rule approval to clinical_lead roles and chat access to authenticated clinicians; TLS termination protects data in transit; local LLM inference avoids sending patient text to third-party APIs by default. Audit logs on rule version changes support governance forensics. These measures do not constitute full regulatory clearance for unsupervised clinical use—they establish a baseline architecture consistent with hospital IT expectations and extensible toward HL7 FHIR integration and formal risk management in future deployment chapters.

## 2.9 Techniques Adopted in This Thesis

The HF-CDSS system selectively implements the techniques surveyed above rather than adopting every method described in the research literature. Table 2.2 maps literature concepts to concrete deployment choices; the following discussion elaborates rationale and interaction at query time.

| Literature technique | Role in HF-CDSS |
|---------------------|-----------------|
| HyDE query expansion | Short physician queries expanded via Qwen2.5-1.5B before BGE-M3 embedding |
| BM25 sparse retrieval | Lexical recall over clinical chunks, fused with dense and graph lists |
| BGE-M3 bi-encoder | Chunk embedding and dense query similarity (Ollama provider) |
| Reciprocal Rank Fusion (RRF) | Merges Chroma, BM25, and Neo4j candidate rankings (\(k=60\)) |
| Three-tier section filter | Keyword → BGE-M3 similarity → borderline LLM review at ingestion |
| Hybrid regex + LLM intake | Regex/lexicon primary extraction; LLM merge when confidence low |
| GDMT rule engine | Executable policies for ACEi/ARB/ARNI, beta blocker, MRA, SGLT2i gaps |
| Verification agents | Safety, missing-data, evidence, and optional LLM agent cross-checks |
| SSE streaming API | Progressive disclosure of draft, recommendation, verification, answer tokens |
| RBAC governance | JWT roles (doctor/clinician, clinical_lead, admin) gate rule approval |
| Optional query decomposition | Splits compound questions for parallel retrieval when enabled |
| Optional Cohere rerank | Second-stage semantic reranking over fused top-\(k\) candidates |
| Redis LLM response cache | Idempotent caching of HyDE and verification outputs within TTL |
| JSONB dose catalogs | PostgreSQL stores agent-specific titration and renal adjustment objects |
| Neo4j local graph search | Entity-centric neighborhood facts for GraphRAG context |
| Bilingual card summarizer | Deterministic VI/EN plain-language labels on recommendation cards |

**Table 2.2.** Techniques adopted in HF-CDSS.

HyDE addresses vocabulary mismatch between terse clinical questions and formal label prose, but its output is never trusted without corroborating retrieved chunks and graph facts. BM25 ensures brand names, numeric cutoffs, and "36 hours" appear in candidate lists even when dense embeddings underweight them. BGE-M3 provides a single embedding model for both ingestion section filtering and query-time dense retrieval, reducing operational complexity versus maintaining separate models. RRF with \(k=60\) follows common defaults from the literature and avoids normalizing heterogeneous scores.

The three-tier section filter embodies the thesis's cost-aware LLM usage pattern: deterministic and embedding methods handle the bulk of ingestion; small models adjudicate borderline sections only. Hybrid intake mirrors this at query time—regex and lexicons extract vitals, labs, and common medications reliably; LLM extraction fills gaps when confidence is low, with merge policy preferring measured numeric values over inferred ones.

The GDMT rule engine and PostgreSQL constraint catalogs implement the safety core. GraphRAG and LLM explanation sit parallel to—not inside—this core. Verification agents enforce fail-closed behavior on hard blocks, check that evidence citations reference retrieved chunk IDs, and flag missing critical patient fields before final answer delivery. SSE streaming implements progressive disclosure aligned with clinician cognitive load: structured recommendations appear before verbose explanation finishes generating.

RBAC separates bedside clinicians from clinical leads who approve rules, supporting governance required in real deployments. Techniques deliberately not adopted as primary decision mechanisms include end-to-end neural prescribing, unconstrained cloud-only LLMs, and pure vector RAG without graph or rule layers—each rejected for insufficient audibility in HF medication safety.

At query time, physician chat triggers hybrid intake, deterministic GDMT and constraint reasoning, parallel GraphRAG retrieval (HyDE, optional query decomposition, Chroma dense search, BM25, Neo4j neighborhood facts, RRF fusion, optional Cohere or bi-encoder rerank), multi-agent verification, and SSE-delivered explanation—combining the audibility of rule-based CDSS with the lexical flexibility of modern retrieval and generation. Subsequent chapters detail requirements, module boundaries, and implementation mappings introduced here.

## 2.10 Chapter Summary

This chapter surveyed the theoretical foundations underlying the HF-CDSS thesis. Clinical decision support systems were defined and classified by timing, function, and mechanism; historical development from MYCIN to modern hybrid systems illustrated recurring themes of transparency, workflow fit, and alert specificity. Osheroff's Five Rights and quantitative metrics—including sensitivity, specificity, PPV, NPV, and alert burden—provided evaluation lenses; heart-failure-specific challenges motivated combining rules, graphs, and retrieval rather than any single paradigm.

The literature review deliberately spans computer-science methods and heart-failure clinical content so that later design chapters can reference a single foundational chapter rather than scattering definitions across implementation notes. Equations for attention, cosine similarity, and RRF are retained because they govern modules instantiated in code; ASCII figures and comparison tables anchor abstract concepts to the HF-CDSS architecture described in Chapters 3–4. Readers seeking implementation detail should proceed to Chapter 3; those seeking empirical validation should proceed to Chapter 5 after understanding the metric definitions introduced in Section 2.1.5.

Knowledge graphs were presented as triples, properties, and axioms supporting entity linking and multi-hop traversal, with Cypher-style intuition and an HF drug-interaction walkthrough. Biomedical resources (UMLS, SNOMED, DrugBank, RxNorm) and graph roles in CDSS set the stage for GraphRAG. Retrieval-augmented generation was developed from dense bi-encoders and sparse BM25 through hybrid fusion, chunking, HNSW-indexed vector stores, and healthcare failure modes. Transformer attention equations grounded LLM capabilities and risks; prompting (CoT, few-shot, HITL), medical LLMs, hallucination taxonomy, mitigations, and local Ollama inference completed the LLM foundation.

GraphRAG was contrasted with vector-only RAG (Table 2.1), with local versus global search, RRF and cosine similarity equations, HyDE, query decomposition, reranking, and HF-specific rationale. Medical KG construction covered sources, NER/RE/linking/fusion/QA, and the three-tier section filter theory. A new clinical section summarized HFrEF phenotype, GDMT pillars, key labs and vitals, ACEi–ARNI washout, and titration monitoring—minimal cardiology for computer-science implementation. Implementation technologies (FastAPI, PostgreSQL JSONB, Redis, ChromaDB, Neo4j, React SSE, Docker) were justified by CDSS requirements. Table 2.2 mapped adopted techniques to system roles.

The chapter's through-line is hybridism: no single technique—rules, graphs, vectors, or LLMs—is sufficient alone for heart-failure medication safety at conversational interfaces. Deterministic modules supply auditable decisions; retrieval supplies citations; graphs supply relational constraints; LLMs supply language flexibility under verification and governance. Chapter 3 translates these foundations into concrete requirements, module boundaries, database schemas, and API contracts for the HF-CDSS implementation.
