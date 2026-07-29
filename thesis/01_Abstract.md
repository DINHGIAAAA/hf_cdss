# ABSTRACT

**Title:** Development of a Clinical Decision Support System for Heart Failure Using Knowledge Graph and GraphRAG

**Field:** Information Technology  
**Code:** 9480104  
**Keywords:** Clinical Decision Support System, Heart Failure, Knowledge Graph, GraphRAG, Large Language Model

---

Heart failure is a serious long-term heart condition that affects tens of millions of people worldwide. Even though clear treatment guidelines exist, many patients still do not receive the full set of medicines that have been proven to help them live longer and feel better. This thesis presents a Clinical Decision Support System (CDSS) that helps doctors apply those guidelines more safely and consistently. The system combines a medical Knowledge Graph, GraphRAG retrieval, deterministic safety rules, and a large language model. In plain terms, it stores medical facts in a structured web of relationships, finds supporting evidence from drug labels and guidelines, checks hard safety constraints with fixed rules, and then explains the result in clear Vietnamese or English. An automated pipeline reads FDA drug labels and heart-failure guidelines and turns them into searchable rules, text passages, and graph links. Doctors can describe a patient in chat; the system then suggests guideline-directed therapy changes, warns about dangerous drug combinations or unsafe doses, and shows the evidence behind each suggestion. Evaluation on curated clinical cases reached 94.0% recommendation accuracy, an average response time of 8.1 seconds, and a user satisfaction score of 4.22 out of 5.0. These results suggest that combining knowledge graphs with grounded retrieval can support safer and faster heart-failure decisions while keeping the clinician in control of the final judgment.
