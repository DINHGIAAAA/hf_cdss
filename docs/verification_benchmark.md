# Verification Flow Benchmark

This document summarizes the verification-flow experiments used to choose the current
Heart Failure CDSS architecture.

## Benchmark Case

The same HFrEF case was used across the main latency checks:

```text
Male, HFrEF, LVEF 28%, eGFR 48, K 4.9, SBP 88, HR 54.
Comorbidities: atrial fibrillation.
Current medications: metoprolol, furosemide, apixaban.
```

Expected clinical behavior:

- The system should not autonomously prescribe.
- Low SBP and low HR should trigger caution.
- Core safety fields are present.
- GraphRAG should retrieve evidence from Neo4j and ChromaDB.
- Final verification should preserve at least `warning`.

## Environment

Benchmarks were run locally with Docker Compose:

- Backend: FastAPI
- LLM runtime: Ollama
- Main explanation model: `qwen2.5:7b`
- Verification model candidates: `qwen2.5:7b`, `qwen2.5:3b`, `qwen2.5:1.5b`
- Graph store: Neo4j
- Vector store: ChromaDB
- Audit store: PostgreSQL

The exact latency depends on CPU, RAM, Ollama model loading state, and whether the request
hits cache. Values below are local observed measurements, not universal performance claims.

## Results

| Flow | Agents Using LLM | Model | Tool Calls | Context Strategy | First Run Latency | Cache Hit | Result |
|---|---:|---|---|---|---:|---:|---|
| Full LLM agents | 5 | `qwen2.5:7b` | Yes | Broad context | ~521s | N/A | Too slow; some agents timed out/fell back |
| Full LLM agents, smaller model | 5 | `qwen2.5:3b` | Yes | Broad context | ~258s | N/A | All agents ran, but final reviewer over-escalated once |
| Full LLM agents + final guardrail | 5 | `qwen2.5:3b` | Yes | Broad context | ~234s | N/A | Correct verdict, still too slow |
| Hybrid, only 2 LLM verifiers | 2 | `qwen2.5:3b` | Yes | Top-k reduced | ~96s | ~0.01s | Better, still high latency |
| Hybrid, smaller verifier model | 2 | `qwen2.5:1.5b` | Yes | Top 3 evidence/facts | ~55s | ~0.01s | Acceptable but still not ideal |
| Current selected flow | 2 | `qwen2.5:1.5b` | No mandatory tool call | Precomputed compact context | ~22s | ~0.01s | Best balance for demo/thesis |

## Why The First Flow Was Too Slow

The initial agent architecture was theoretically clean but inefficient for local CPU
inference:

```text
recommendation
  -> safety LLM agent
  -> missing-data LLM agent
  -> evidence LLM agent
  -> guideline-alignment LLM agent
  -> final-reviewer LLM agent
```

Main bottlenecks:

- Too many LLM calls for checks that are deterministic.
- Tool-calling requires at least two model turns: one to request a tool, one to produce the final verdict.
- Some agents received more context than they needed.
- Local Ollama CPU inference is the dominant latency source.

## Selected Architecture

The current selected flow uses a hybrid verification design:

```text
Patient case
  -> Rule engine
  -> Recommendation
  -> GraphRAG retrieval from Neo4j + ChromaDB
  -> Deterministic safety check
  -> Deterministic missing-data check
  -> Parallel LLM evidence verifier
  -> Parallel LLM guideline verifier
  -> Deterministic final reviewer
  -> PostgreSQL audit
```

Current default configuration:

```env
HF_CDSS_VERIFICATION_AGENT_MODE=hybrid
HF_CDSS_VERIFICATION_AGENT_MODEL=qwen2.5:1.5b
HF_CDSS_VERIFICATION_AGENT_LLM_AGENTS=evidence_agent,guideline_alignment_agent
HF_CDSS_VERIFICATION_AGENT_TOOL_MODE=direct
HF_CDSS_VERIFICATION_RETRIEVAL_TOP_K=3
HF_CDSS_VERIFICATION_CACHE_ENABLED=true
```

## Why This Flow Was Chosen

### 1. Safety Rules Are Better As Code

Safety thresholds such as low blood pressure, bradycardia, hyperkalemia, renal impairment,
and missing safety labs are deterministic. Running them through an LLM adds latency and
hallucination risk without improving reliability.

Therefore:

```text
safety_agent = deterministic
missing_data_agent = deterministic
final_reviewer_agent = deterministic severity aggregation
```

### 2. LLMs Are Used Only Where They Add Value

LLMs are retained for tasks that require qualitative judgment:

- Whether retrieved evidence is relevant enough.
- Whether recommendation status and retrieved evidence appear aligned.

Therefore:

```text
evidence_agent = LLM
guideline_alignment_agent = LLM
```

### 3. Compact Context Is Faster And Safer

Instead of sending all graph facts, chunks, rules, and recommendations to every agent, the
backend builds compact agent-specific packs:

- Evidence verifier receives only top evidence/facts.
- Guideline verifier receives recommendation statuses, constraints, and short evidence snippets.

This reduces token count and lowers hallucination risk.

### 4. Direct Mode Is Faster Than Mandatory Tool Calling

Tool-calling is useful for demonstrating agent behavior, but local CPU latency is much
higher because each tool call requires an extra model turn.

The system keeps both modes:

```env
HF_CDSS_VERIFICATION_AGENT_TOOL_MODE=direct
```

for fast demo use, and:

```env
HF_CDSS_VERIFICATION_AGENT_TOOL_MODE=tool_calling
```

when explicit tool-calling needs to be demonstrated.

### 5. Cache Matches Clinical Decision Support Usage

Many HFrEF cases share repeated risk patterns such as:

- low blood pressure
- renal impairment
- hyperkalemia
- bradycardia
- missing renal or potassium data

Short-term verification caching makes repeated requests nearly instant while preserving
the same structured result.

## Final Recommendation For The Report

The selected architecture is not a pure multi-agent LLM system. It is a safer and faster
hybrid CDSS architecture:

```text
Deterministic rules for hard clinical safety
+ database-backed GraphRAG retrieval
+ lightweight LLM verifiers for evidence and guideline alignment
+ deterministic final severity aggregation
+ audit logging
```

This design was chosen because it reduces latency from approximately 9 minutes to around
22 seconds on the local benchmark case, while preserving clinical guardrails and making
the agentic verification components explicit enough for thesis evaluation.

