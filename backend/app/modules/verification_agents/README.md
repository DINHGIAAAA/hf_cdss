# Verification Agents

Coordinates safety, dose, interaction, guideline, evidence, and final reviewer agents.

Verification uses five role-specific agents:

- `safety_agent`
- `missing_data_agent`
- `evidence_agent`
- `guideline_alignment_agent`
- `final_reviewer_agent`

In optimized `hybrid` mode:

- Safety thresholds and missing-data checks remain deterministic.
- Evidence and guideline-alignment agents run as lightweight LLM agents in parallel.
- Final severity aggregation remains deterministic.
- Each LLM agent has a separate prompt, compact role-specific context, and limited tools.
- Deterministic checks remain mandatory guardrails and fallbacks.

Set `HF_CDSS_VERIFICATION_AGENT_MODE=rule_based` to disable LLM agent execution.
Docker defaults agents to the smaller `qwen2.5:1.5b` model while keeping the larger model
for the final physician-facing explanation.

`HF_CDSS_VERIFICATION_AGENT_LLM_AGENTS` controls which agents use the LLM. Enabling all
five agents is supported but substantially slower on CPU-only Ollama. Exact verification
requests are cached briefly in memory to avoid repeated model calls.

`HF_CDSS_VERIFICATION_AGENT_TOOL_MODE` controls latency:

- `direct` is the default fast path. The backend precomputes compact evidence/guideline
  packs and each verifier produces a JSON verdict in one model call.
- `tool_calling` keeps explicit OpenAI-style tool calls for demos, but each verifier needs
  at least two model turns and is much slower on CPU.
