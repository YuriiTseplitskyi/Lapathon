from __future__ import annotations

import json
import re
from typing import Annotated, Any, Callable, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from agent.config import AgentConfig
from agent.prompts import FAMILY_RELATIONSHIP_BUILDER_PROMPT
from agent.state import CorruptionAgentState
from agent.tools import make_search_graph_db_tool


class FamilyAgentState(TypedDict):
    """Internal state for the family builder sub-agent."""
    messages: Annotated[list, add_messages]


def extract_family_json(messages: list) -> Dict[str, Any]:
    """
    Extract the family relationships JSON from the agent's final response.
    Looks for JSON in the last AI message, either in code blocks or as raw JSON.
    """
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if not isinstance(content, str):
                continue

            # Try to find JSON in markdown code block first
            json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_block_match:
                try:
                    return json.loads(json_block_match.group(1))
                except json.JSONDecodeError as e:
                    print(f"Warning: Found JSON block but failed to parse: {e}")
                    pass

            # Try to find standalone JSON object (look for balanced braces)
            # This will find the first complete JSON object in the text
            brace_count = 0
            start_idx = None
            for i, char in enumerate(content):
                if char == '{':
                    if start_idx is None:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        # Found a complete JSON object
                        json_str = content[start_idx:i+1]
                        try:
                            parsed = json.loads(json_str)
                            # Validate it looks like a family relationships object
                            if isinstance(parsed, dict) and ("target_person" in parsed or "immediate_family" in parsed):
                                return parsed
                        except json.JSONDecodeError:
                            # Reset and try to find another object
                            start_idx = None
                            brace_count = 0

    # Return empty structure if no valid JSON found
    return {
        "target_person": {},
        "immediate_family": {},
        "extended_family": {},
        "in_laws": {},
        "same_person_records": [],
        "uncertain_relationships": [],
        "error": "Could not extract family relationships JSON from agent response"
    }


def extract_person_ids(family_json: Dict[str, Any]) -> list[str]:
    """
    Extract all unique person_ids from the family relationships JSON.
    """
    person_ids = set()

    def extract_from_dict(d: dict):
        if isinstance(d, dict):
            person_id = d.get("person_id")
            # Normalize person_id to a hashable scalar before adding
            if isinstance(person_id, (str, int)):
                person_ids.add(str(person_id))
            elif isinstance(person_id, list):
                for pid in person_id:
                    if isinstance(pid, (str, int)):
                        person_ids.add(str(pid))
            for v in d.values():
                if isinstance(v, dict):
                    extract_from_dict(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            extract_from_dict(item)

    extract_from_dict(family_json)
    return list(person_ids)


def create_family_builder_node(cfg: AgentConfig) -> Callable[[CorruptionAgentState], Dict[str, Any]]:
    """
    Create the family relationship builder node.

    This node uses a ReAct agent pattern to:
    1. Take the target person query from state
    2. Use search_graph_db tool multiple times to build the family tree
    3. Return structured family relationships JSON to state

    Args:
        cfg: Agent configuration with LLM and Neo4j settings.

    Returns:
        A node function that takes CorruptionAgentState and returns state updates.
    """
    # Create the tool
    search_tool = make_search_graph_db_tool(cfg)
    tools = [search_tool]

    # Create the LLM with tools bound
    llm = ChatOpenAI(
        model=cfg.openai_model_name or "gpt-4o",
        api_key=cfg.openai_api_key,
        temperature=cfg.temperature,
    ).bind_tools(tools)

    # Build internal ReAct graph for family building
    def build_family_agent():
        """Build a ReAct agent graph for family relationship discovery."""

        def llm_node(state: FamilyAgentState) -> dict:
            """Call LLM with current messages."""
            response = llm.invoke(state["messages"])
            return {"messages": [response]}

        def should_continue(state: FamilyAgentState) -> str:
            """Check if agent should continue tool calling or finish."""
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        tool_node = ToolNode(tools)

        graph = StateGraph(FamilyAgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "llm")
        graph.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "llm")

        return graph.compile()

    # Compile the internal agent
    family_agent = build_family_agent()

    def node(state: CorruptionAgentState) -> Dict[str, Any]:
        """
        Execute the family builder node.

        Takes target_person_query from state, runs the family building agent,
        and returns family_relationships and person_ids to state.
        """
        target_query = state.get("target_person_query", "")

        # Build the initial messages for the agent
        system_message = SystemMessage(content=FAMILY_RELATIONSHIP_BUILDER_PROMPT)
        user_message = HumanMessage(
            content=f"Build a complete family tree for: {target_query}\n\n"
                    f"Use the search_graph_db tool to query the Neo4j database. "
                    f"Follow the detection strategy phases outlined in the system prompt. "
                    f"Return the final family relationships as a JSON object."
        )

        initial_state = {
            "messages": [system_message, user_message],
        }

        # Run the family building agent
        result = family_agent.invoke(initial_state)

        # Extract the family JSON from the agent's response
        family_json = extract_family_json(result["messages"])
        person_ids = extract_person_ids(family_json)

        # Add status message to main conversation
        status_message = AIMessage(
            content=f"Family relationship analysis complete. "
                    f"Found {len(person_ids)} persons in the family network."
        )

        return {
            "messages": [status_message],
            "family_relationships": family_json,
            "person_ids": person_ids,
        }

    return node
