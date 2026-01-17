from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from agent.config import AgentConfig
from agent.prompts import PROXY_OWNERSHIP_ANALYZER_PROMPT
from agent.state import CorruptionAgentState
from agent.tools.search_graph_db import make_search_graph_db_tool
from langgraph.graph.message import add_messages


# Define state at module level to avoid scoping issues with type hints
class ProxyOwnershipAgentState(TypedDict):
    """Internal state for proxy ownership analyzer agent."""
    messages: Annotated[list, add_messages]


def parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON from text that may contain markdown code blocks or other content.
    Looks for JSON objects between ```json and ``` or standalone {}.
    """
    # Try to find JSON in markdown code block
    json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_block_match:
        json_str = json_block_match.group(1)
        return json.loads(json_str)

    # Try to find standalone JSON object
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        return json.loads(json_str)

    # If no JSON found, raise error
    raise ValueError("No JSON object found in text")


def create_proxy_ownership_node(cfg: AgentConfig) -> Callable[[CorruptionAgentState], Dict[str, Any]]:
    """
    Create proxy ownership analyzer node with ReAct sub-agent.

    This node detects proxy/nominee ownership patterns where assets are registered
    to low-income family members to hide actual beneficial owners.
    It uses a ReAct agent with search_graph_db tool to query Neo4j and analyze patterns.

    Architecture:
    - Internal StateGraph with llm_node + tool_node (ReAct pattern)
    - LLM decides what queries to run and how to analyze results
    - Returns structured JSON with proxy ownership assessment
    """

    # 1. Create tool
    search_tool = make_search_graph_db_tool(cfg)
    tools = [search_tool]

    # 2. Create LLM with tools bound
    llm = ChatOpenAI(
        model=cfg.openai_model_name or "gpt-4o",
        api_key=cfg.openai_api_key,
        temperature=cfg.temperature,
    ).bind_tools(tools)

    # 3. Build internal ReAct graph
    def build_proxy_ownership_agent():
        """Build a ReAct agent graph for proxy ownership analysis."""

        def llm_node(state: ProxyOwnershipAgentState) -> dict:
            """Call LLM with current messages."""
            response = llm.invoke(state["messages"])
            return {"messages": [response]}

        def should_continue(state: ProxyOwnershipAgentState) -> str:
            """Check if agent should continue tool calling or finish."""
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        tool_node = ToolNode(tools)

        graph = StateGraph(ProxyOwnershipAgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "llm")
        graph.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "llm")

        return graph.compile()

    proxy_ownership_agent = build_proxy_ownership_agent()

    # 5. Create outer node function
    def proxy_ownership_node(state: CorruptionAgentState) -> Dict[str, Any]:
        """
        Outer node function that integrates with main corruption agent graph.
        Takes family network and income/assets analysis from state and detects proxy ownership patterns.
        """
        person_ids = state.get("person_ids", [])
        target_query = state.get("target_person_query", "")
        family_relationships = state.get("family_relationships", {})
        income_assets_analysis = state.get("income_assets_analysis", {})

        if not person_ids:
            return {
                "proxy_ownership_analysis": {
                    "error": "No person_ids available from family builder",
                    "proxy_ownership_detected": False,
                    "confidence_level": "NONE"
                },
                "messages": [HumanMessage(content="Proxy ownership analysis skipped: no person_ids")]
            }

        # Create messages for ReAct agent
        system_message = SystemMessage(content=PROXY_OWNERSHIP_ANALYZER_PROMPT)

        # Prepare context from previous analyses
        context = f"""Analyze proxy ownership patterns for: {target_query}

Family member person_ids to analyze: {person_ids}

CONTEXT FROM PREVIOUS ANALYSES:

Family Relationships Summary:
{json.dumps(family_relationships, indent=2, ensure_ascii=False)[:2000]}

Income vs Assets Analysis Summary:
{json.dumps(income_assets_analysis, indent=2, ensure_ascii=False)[:2000]}

Remember: person_id fields in the graph are stored as lists,
so use 'WHERE $person_id IN p.person_id' in your queries.

Please:
1. Identify proxy candidates (low-income persons with high-value assets)
2. Find potential beneficial owners (family members with government/business employment)
3. Analyze asset distribution patterns across the family network
4. Cross-reference acquisition timing with employment/income changes
5. Return your analysis as JSON following the output format in your instructions
"""

        user_message = HumanMessage(content=context)

        initial_state = {"messages": [system_message, user_message]}

        # Invoke ReAct agent
        result = proxy_ownership_agent.invoke(initial_state)

        # Extract analysis from final message
        final_message = result["messages"][-1]
        analysis_text = final_message.content if hasattr(final_message, 'content') else str(final_message)

        # Parse JSON from response
        try:
            analysis_json = parse_json_from_text(analysis_text)
        except Exception as e:
            # If JSON parsing fails, return raw output with error
            analysis_json = {
                "error": f"Failed to parse JSON: {str(e)}",
                "raw_output": analysis_text[:1000],  # Limit to first 1000 chars
                "proxy_ownership_detected": False,
                "confidence_level": "NONE"
            }

        return {
            "proxy_ownership_analysis": analysis_json,
            "messages": [HumanMessage(content="Proxy ownership analysis complete.")]
        }

    return proxy_ownership_node
