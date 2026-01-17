from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.config import AgentConfig
from agent.prompts import CORRUPTION_SUMMARY_PROMPT
from agent.state import CorruptionAgentState


def parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON from text that may contain markdown code blocks or other content.
    Looks for JSON objects between ```json and ``` or standalone {}.
    """
    json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_block_match:
        json_str = json_block_match.group(1)
        return json.loads(json_str)

    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        return json.loads(json_str)

    raise ValueError("No JSON object found in text")


def create_summary_node(cfg: AgentConfig) -> Callable[[CorruptionAgentState], Dict[str, Any]]:
    """
    Create a summary node that consolidates corruption pattern findings into Ukrainian summaries.

    The node reads previous analysis outputs and returns a JSON object where each corruption
    pattern name is the key and the formatted summary text is the value.
    """

    llm = ChatOpenAI(
        model=cfg.openai_model_name or "gpt-4o",
        api_key=cfg.openai_api_key,
        temperature=cfg.temperature,
    )

    def summary_node(state: CorruptionAgentState) -> Dict[str, Any]:
        income_assets_analysis = state.get("income_assets_analysis") or {}
        proxy_ownership_analysis = state.get("proxy_ownership_analysis") or {}
        shell_company_analysis = state.get("shell_company_analysis") or {}
        family_relationships = state.get("family_relationships") or {}
        target_query = state.get("target_person_query", "")

        system_message = SystemMessage(content=CORRUPTION_SUMMARY_PROMPT)
        context_payload = {
            "target_person_query": target_query,
            "family_relationships": family_relationships,
            "income_assets_analysis": income_assets_analysis,
            "proxy_ownership_analysis": proxy_ownership_analysis,
            "shell_company_analysis": shell_company_analysis,
        }

        user_message = HumanMessage(
            content=(
                "Зроби підсумкові резюме по схемах для цього розслідування.\n\n"
                "Дані для узагальнення (JSON):\n"
                f"{json.dumps(context_payload, ensure_ascii=False, indent=2)[:4000]}"
            )
        )

        response = llm.invoke([system_message, user_message])
        summary_text = response.content if hasattr(response, "content") else str(response)

        try:
            summary_json = parse_json_from_text(summary_text)
        except Exception as e:
            error_summary = (
                "Оцінка: ризик корупційної причетності — даних недостатньо\n"
                f"Опис схеми: не вдалося сформувати резюме (помилка парсингу: {str(e)}).\n"
                "Головний підозрюваний: даних недостатньо\n"
                f"Ключові особи: даних недостатньо. Сира відповідь: {summary_text[:300]}"
            )
            summary_json = {
                "income_vs_assets": error_summary,
                "proxy_ownership": error_summary,
                "shell_company": error_summary,
            }

        return {
            "corruption_summary": summary_json,
            "messages": [HumanMessage(content="Підсумкові резюме по схемах сформовано.")],
        }

    return summary_node
