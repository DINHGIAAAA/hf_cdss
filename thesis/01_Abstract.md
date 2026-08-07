# ABSTRACT

**Title:** Development of a Clinical Decision Support System for Heart Failure Using Knowledge Graph and GraphRAG

**Field:** Information Technology  
**Code:** 9480104  
**Keywords:** Clinical Decision Support System, Heart Failure, Knowledge Graph, GraphRAG, Large Language Model

---

Heart failure is a serious long-term condition that affects tens of millions of people worldwide. Clear treatment guidelines exist, yet many patients still do not receive the full set of medicines shown to improve survival and symptoms. This thesis presents a Clinical Decision Support System (CDSS) that helps clinicians apply those guidelines more safely and consistently. The system combines a medical Knowledge Graph, GraphRAG retrieval, deterministic safety rules, and a locally hosted large language model. Medical facts live in a structured graph; retrieval pulls supporting passages from drug labels and guidelines; fixed rules enforce hard safety constraints; the model explains results in Vietnamese or English without owning the final recommendation. An automated pipeline ingests FDA drug labels and heart-failure guidelines into searchable rules, text chunks, and graph links. Clinicians describe a patient in chat and receive guideline-directed therapy suggestions, interaction and dose warnings, and citations for each card. On 50 curated clinical cases, recommendation accuracy reached 94.0%, mean response time was 8.1 seconds, and user satisfaction averaged 4.22 out of 5.0. The evaluation supports hybrid graph-and-rule decision support for supervised heart-failure care, with the clinician retaining final judgment.
