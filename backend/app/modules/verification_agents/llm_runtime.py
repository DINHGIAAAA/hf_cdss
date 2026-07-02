import json
import logging
import re
from typing import Any

from app.core.http_client import get_async_client
from app.core.config import settings
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.prompts.verification_agents import AGENT_PROMPTS
from app.schemas.graphrag import AgentResult
from app.modules.verification_agents.tools import AgentTool, execute_tool


logger = logging.getLogger(__name__)
VALID_VERDICTS = {"pass", "warning", "fail"}


def _agent_model() -> str:
    return settings.verification_agent_model or settings.llm_model


def _headers() -> dict[str, str]:
    return llm_auth_headers()


def _parse_result(agent_name: str, content: str, tools_used: list[str]) -> AgentResult:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("Agent did not return a JSON object")
    payload = json.loads(match.group(0))
    verdict = str(payload.get("verdict", "")).lower()
    if verdict not in VALID_VERDICTS:
        raise ValueError("Agent returned an invalid verdict")
    return AgentResult(
        agent_name=agent_name,
        verdict=verdict,
        message=str(payload.get("message", "")).strip() or "LLM agent completed verification.",
        evidence_refs=[str(item) for item in payload.get("evidence_refs", [])][:12],
        execution_mode="llm_agent",
        model=_agent_model(),
        tools_used=tools_used,
    )


async def run_llm_agent(
    agent_name: str,
    case_payload: dict[str, Any],
    tools: list[AgentTool],
) -> AgentResult:
    if not llm_chat_completions_enabled():
        raise RuntimeError("Verification agents require an Ollama chat_completions endpoint")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_PROMPTS[agent_name]},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "agent": agent_name,
                    "case": case_payload,
                    "instruction": (
                        "Use the supplied compact verification pack and return the required JSON verdict."
                        if not tools
                        else "Call one available tool, then return the required JSON verdict."
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]
    tool_map = {tool.name: tool for tool in tools}
    tools_used: list[str] = []

    client = get_async_client("verification_agent", settings.verification_agent_timeout_seconds)
    for _ in range(max(1, settings.verification_agent_max_iterations)):
        response = await client.post(
            chat_completions_url(),
            headers=_headers(),
            json={
                "model": _agent_model(),
                "messages": messages,
                **({"tools": [tool.openai_schema() for tool in tools], "tool_choice": "auto"} if tools else {}),
                "temperature": 0.0,
                "max_tokens": settings.verification_agent_max_tokens,
            },
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return _parse_result(agent_name, message.get("content") or "", tools_used)

        messages.append(message)
        for call in tool_calls:
            function = call.get("function", {})
            tool_name = function.get("name")
            if tool_name not in tool_map:
                tool_output = json.dumps({"error": f"Tool {tool_name} is not allowed"})
            else:
                tools_used.append(tool_name)
                tool_output = execute_tool(tool_map[tool_name], function.get("arguments"))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": tool_name,
                    "content": tool_output,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": "Return the final JSON verdict now using the tool results. Do not call another tool.",
            }
        )
        response = await client.post(
            chat_completions_url(),
            headers=_headers(),
            json={
                "model": _agent_model(),
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": settings.verification_agent_max_tokens,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content") or ""
        return _parse_result(agent_name, content, tools_used)
