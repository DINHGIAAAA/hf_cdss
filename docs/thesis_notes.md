# Thesis Notes

Use this file for design decisions, experiment notes, and report-ready explanations.

## Chapter 1 Draft: Introduction

Heart failure is a chronic clinical syndrome with high morbidity, repeated hospitalization risk, and complex medication management. Modern guideline-directed medical therapy can improve outcomes, but practical use requires physicians to balance multiple drug classes, renal function, potassium, blood pressure, heart rate, comorbidities, allergies, and current medications. This creates a suitable setting for a clinical decision support system that can surface candidate therapies, safety cautions, and supporting evidence in a structured way.

The proposed thesis builds a heart failure medication decision support system using a GraphRAG-oriented architecture and multi-agent verification. The system is not designed to replace a clinician. Its role is to organize patient facts, retrieve relevant guideline context, reason over medication classes, check constraints, and explain recommendations so that a physician can review them efficiently.

### Problem Motivation

Medication decisions in heart failure often involve interactions between guideline indications and patient-specific risks. A patient with reduced ejection fraction may be eligible for several GDMT classes, but renal impairment or hyperkalemia can change whether a class should be recommended, delayed, monitored closely, or avoided. A purely generative system can miss these constraints if retrieval and verification are weak. A rule-only system can be transparent but brittle when evidence context expands. The thesis therefore explores a hybrid design: structured patient constraints, graph relationships, vector retrieval, and verification agents.

### Objectives

- Build a runnable MVP for heart failure medication support.
- Represent patient profiles, observations, diagnoses, medication classes, risks, constraints, evidence, recommendations, and audit logs.
- Retrieve guideline and drug-context evidence through graph and vector components in later milestones.
- Produce structured recommendation outputs with risk flags, rationale, warnings, and a clinical disclaimer.
- Evaluate the system using synthetic patient cases and ablation experiments.

### Scope

The MVP focuses on adult heart failure medication decision support, especially HFrEF GDMT. It covers medication class recommendation, caution, and avoidance reasoning. It does not perform autonomous prescribing, emergency care management, or EHR integration. Week 1 is limited to a runnable foundation and stable contracts.

### Research Object

The research object is a modular clinical decision support pipeline for heart failure medication selection. The main observed outputs are structured recommendation decisions, extracted risk flags, evidence references, verification results, and explanation quality.

### Method

The project follows an engineering research method: define requirements, build a modular prototype, create synthetic cases, run baseline and ablation experiments, and compare safety and explanation metrics. The implementation is organized as a modular monolith first so that core data contracts can stabilize before optional service extraction.

## Chapter 3 Draft: Architecture Overview

The system uses a modular monolith architecture with clear internal boundaries. The backend is built with FastAPI and Pydantic models. The frontend is a React/Vite doctor dashboard skeleton. Supporting containers for PostgreSQL, Neo4j, and ChromaDB are included from the beginning to keep the local runtime close to the planned final architecture.

The backend flow begins with patient profile ingestion. Later modules normalize clinical values, extract risk flags, build patient-specific medication constraints, retrieve graph and vector evidence, assemble GraphRAG context, generate a structured recommendation, verify safety through specialized agents, and produce an explanation plus audit trail.

Week 1 intentionally implements only the stable outer shell: API routes, config, logging, error format, schema contracts, sample data, and a placeholder recommendation service. This prevents later work from being built on loose contracts. Each later week can replace placeholder internals while preserving the public API shape.

The frontend is currently a doctor dashboard skeleton that checks backend health and shows a sample patient case. It exists to confirm the system can run end to end and to provide a surface for later recommendation, evidence, explanation, and audit-log views.

The data layer is staged. Synthetic patient profiles are stored as JSON for quick iteration. PostgreSQL will later store structured cases, recommendations, and audit logs. Neo4j will represent clinical entities and relationships. ChromaDB will store embedded guideline chunks for semantic retrieval.

The initial architecture prioritizes traceability. Every medical output must include a disclaimer, structured rationale, and later an evidence path. This aligns with the thesis goal: evaluate whether GraphRAG plus verification can make clinical recommendation support more grounded and safer than a direct generation baseline.

## Clinical Constraint Modeling Draft

The clinical constraint layer converts normalized patient facts into medication-specific safety constraints. It is intentionally separated from the language-model reasoning layer so that basic safety rules remain inspectable, testable, and reproducible.

The week-2 model uses four constraint categories. Hard constraints represent strong avoid or defer signals, such as avoiding MRA when renal impairment is severe or potassium is high. Soft constraints represent caution or sequencing concerns, such as low blood pressure affecting RAAS-inhibiting therapy. Dose constraints indicate that dose or eligibility must be reviewed, especially when renal function is reduced. Monitoring constraints indicate the need for follow-up labs or vital signs.

Example: a patient with HFrEF, eGFR 12, potassium 5.8, SBP 86, HR 52, and six active medications produces high renal impairment, high hyperkalemia, high hypotension, bradycardia, and polypharmacy flags. The constraint builder then emits an `avoid` constraint for MRA, caution constraints for ARNI/ACEi/ARB and beta blocker therapy, and review constraints for SGLT2 inhibitor eligibility and polypharmacy.

This approach gives the thesis a transparent intermediate representation between patient input and final recommendation. Later GraphRAG and verification modules can cite guideline evidence, but they should not erase the rule-derived constraints.
