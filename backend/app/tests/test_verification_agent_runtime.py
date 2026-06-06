from app.modules.verification_agents.service import _final_reviewer_guardrail, _guardrail_result
from app.modules.verification_agents.tools import execute_tool
from app.schemas.graphrag import AgentResult


def test_guardrail_does_not_allow_llm_to_downgrade_warning() -> None:
    llm_result = AgentResult(
        agent_name="safety_agent",
        verdict="pass",
        message="No issue.",
        execution_mode="llm_agent",
        model="test-model",
        tools_used=["inspect_safety_constraints"],
    )
    deterministic = AgentResult(
        agent_name="safety_agent",
        verdict="warning",
        message="Caution constraint detected.",
        evidence_refs=["constraint-1"],
    )

    result = _guardrail_result(llm_result, deterministic)

    assert result.verdict == "warning"
    assert result.execution_mode == "llm_agent_with_rule_guardrail"
    assert result.evidence_refs == ["constraint-1"]


def test_execute_tool_parses_json_arguments() -> None:
    from app.modules.verification_agents.tools import AgentTool

    tool = AgentTool(
        name="echo",
        description="Echo arguments",
        parameters={"type": "object"},
        handler=lambda arguments: arguments,
    )

    assert execute_tool(tool, '{"query":"renal"}') == '{"query": "renal"}'


def test_final_reviewer_cannot_invent_a_fail() -> None:
    llm_result = AgentResult(
        agent_name="final_reviewer_agent",
        verdict="fail",
        message="Block case.",
        execution_mode="llm_agent",
        model="test-model",
        tools_used=["inspect_agent_results"],
    )
    deterministic = AgentResult(
        agent_name="final_reviewer_agent",
        verdict="warning",
        message="Specialist warnings remain.",
    )

    result = _final_reviewer_guardrail(llm_result, deterministic)

    assert result.verdict == "warning"
    assert result.execution_mode == "llm_agent_with_rule_guardrail"
