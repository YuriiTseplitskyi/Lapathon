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
from agent.prompts import SHELL_COMPANY_ANALYZER_PROMPT
from agent.state import CorruptionAgentState
from agent.tools.search_graph_db import make_search_graph_db_tool
from langgraph.graph.message import add_messages


# Define state at module level to avoid scoping issues with type hints
class ShellCompanyAgentState(TypedDict):
    """Internal state for shell company analyzer agent."""
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


def create_shell_company_node(cfg: AgentConfig) -> Callable[[CorruptionAgentState], Dict[str, Any]]:
    """
    Create shell company analyzer node with ReAct sub-agent.

    This node detects shell companies and business entities used for corruption.
    It uses a ReAct agent with search_graph_db tool to query Neo4j and analyze data.

    Architecture:
    - Internal StateGraph with llm_node + tool_node (ReAct pattern)
    - LLM decides what queries to run and how to analyze results
    - Returns structured JSON with shell company detection and risk assessment
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
    def build_shell_company_agent():
        """Build a ReAct agent graph for shell company analysis."""

        def llm_node(state: ShellCompanyAgentState) -> dict:
            """Call LLM with current messages."""
            response = llm.invoke(state["messages"])
            return {"messages": [response]}

        def should_continue(state: ShellCompanyAgentState) -> str:
            """Check if agent should continue tool calling or finish."""
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        tool_node = ToolNode(tools)

        graph = StateGraph(ShellCompanyAgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "llm")
        graph.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "llm")

        return graph.compile()

    shell_company_agent = build_shell_company_agent()

    # 5. Create outer node function
    def shell_company_node(state: CorruptionAgentState) -> Dict[str, Any]:
        """
        Outer node function that integrates with main corruption agent graph.
        Takes family network from state and analyzes shell company patterns.
        """
        person_ids = state.get("person_ids", [])
        target_query = state.get("target_person_query", "")
        income_assets_analysis = state.get("income_assets_analysis", {})
        proxy_ownership_analysis = state.get("proxy_ownership_analysis", {})

        if not person_ids:
            return {
                "shell_company_analysis": {
                    "error": "No person_ids available from family builder",
                    "shell_companies_detected": False,
                    "confidence_level": "NONE"
                },
                "messages": [HumanMessage(content="Shell company analysis skipped: no person_ids")]
            }

        # Create messages for ReAct agent
        system_message = SystemMessage(content=SHELL_COMPANY_ANALYZER_PROMPT)

        # Provide context from previous analyses
        context_info = f"Previous analysis context:\n"
        context_info += f"- Income/assets analysis available: {bool(income_assets_analysis and not income_assets_analysis.get('error'))}\n"
        context_info += f"- Proxy ownership analysis available: {bool(proxy_ownership_analysis and not proxy_ownership_analysis.get('error'))}\n"

        user_message = HumanMessage(
            content=f"Analyze shell company patterns for: {target_query}\n\n"
                    f"Family member person_ids to analyze: {person_ids}\n\n"
                    f"{context_info}\n"
                    f"Remember: person_id fields in the graph are stored as lists, "
                    f"so use 'WHERE $person_id IN p.person_id' in your queries.\n\n"
                    f"Please:\n"
                    f"1. Find organizations paying income to family members (check for self-named entities)\n"
                    f"2. Identify organizations with minimal employees (0-1 employees)\n"
                    f"3. Find organizations owning assets but with no business activity\n"
                    f"4. Check which family members receive income from these organizations\n"
                    f"5. Cross-reference with proxy ownership findings if available\n"
                    f"6. Return your analysis as JSON following the output format in your instructions"
        )

        initial_state = {"messages": [system_message, user_message]}

        # Invoke ReAct agent
        result = shell_company_agent.invoke(initial_state)

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
                "shell_companies_detected": False,
                "confidence_level": "NONE"
            }

        return {
            "shell_company_analysis": analysis_json,
            "messages": [HumanMessage(content="Shell company analysis complete.")]
        }

    return shell_company_node
