from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from agent.config import AgentConfig
from agent.prompts import SYSTEM_PROMPT_OPENAI, SYSTEM_PROMPT_UK
from agent.tools import make_search_graph_db_tool


TOOL_CALL_RE = re.compile(r"(?s)<tool_call>\s*(\{.*?\})\s*</tool_call>")


def parse_tool_call(message: AnyMessage) -> Optional[Dict[str, Any]]:
    """
    Parse tool call from <tool_call>{...}</tool_call> XML format in message content.
    """
    content = getattr(message, "content", "")
    if not isinstance(content, str) or not content:
        return None

    match = TOOL_CALL_RE.search(content)
    if not match:
        return None

    payload_raw = match.group(1).strip()

    try:
        payload = ast.literal_eval(payload_raw)
    except Exception:
        try:
            payload = json.loads(payload_raw)
        except Exception:
            return None

    if not isinstance(payload, dict):
        return None
    if payload.get("name") != "search_graph_db":
        return None

    args = payload.get("arguments")
    if not isinstance(args, dict):
        return None

    q = args.get("query")
    if not isinstance(q, str) or not q.strip():
        return None

    return payload


class LapaAgentState(TypedDict):
    """State for LAPA agent with manual tool call parsing."""
    messages: Annotated[List[AnyMessage], add_messages]
    pending_tool: Optional[Dict[str, Any]]


class OpenAIAgentState(TypedDict):
    """State for OpenAI agent with native tool calling."""
    messages: Annotated[List[AnyMessage], add_messages]


class Agent:
    """
    Agent that guides an LLM to query a Neo4j graph database via function calling.

    Supports two agent types:
    - LAPA: Uses custom XML-based tool call parsing for LAPA models
    - OpenAI: Uses native OpenAI function calling with simpler graph structure

    The agent type is determined by the `agent_type` field in AgentConfig.
    """

    def __init__(
        self,
        cfg: AgentConfig,
        system_prompt: Optional[str] = None,
    ):

        self.cfg = cfg
        self.agent_type = cfg.agent_type
        self.tool = make_search_graph_db_tool(cfg)

        match self.agent_type:
            case "openai":
                self.system_prompt = system_prompt or SYSTEM_PROMPT_OPENAI
                self.llm = ChatOpenAI(
                    model=cfg.openai_model_name or "gpt-4o",
                    api_key=cfg.openai_api_key,
                    temperature=cfg.temperature,
                ).bind_tools([self.tool])
                self.graph = self._build_openai_graph()
            case _:
                self.system_prompt = system_prompt or SYSTEM_PROMPT_UK
                self.llm = ChatOpenAI(
                    model=cfg.lapa_model_name,
                    base_url=cfg.base_url,
                    api_key=cfg.lapa_api_key,
                    temperature=cfg.temperature,
                ).bind_tools([self.tool])
                self.graph = self._build_lapa_graph()

    def _build_lapa_graph(self):
        """Build graph for LAPA models with XML tool call parsing."""

        def llm_node(state: LapaAgentState) -> Dict[str, Any]:
            resp = self.llm.invoke(state["messages"])
            return {"messages": [resp]}

        def parse_tool_call_node(state: LapaAgentState) -> Dict[str, Any]:
            last = state["messages"][-1]
            tc = parse_tool_call(last)
            return {"pending_tool": tc}

        def run_tool_node(state: LapaAgentState) -> Dict[str, Any]:
            tc = state.get("pending_tool")
            if not tc:
                return {}

            query = tc["arguments"]["query"]
            tool_name = tc["name"]
            tool_result = self.tool.invoke({"query": query})

            tool_result_msg = HumanMessage(
                content=(
                    f"Результат виклику інструмента {tool_name}:\n"
                    f"{tool_result}\n\n"
                    "Використай отримані дані для формування відповіді користувачу.\n"
                    "Якщо результат виклику інструмента вказує на некоректний запит, проаналізуй цей і повтори виклик тула з випривленням помилки.\n"
                    "Якщо результат інструменту - порожній ([]), значить попередній запит некоректний. Повтори виклик тула з виправленням помилки.\n"
                    "Завжди дотримуйся правил **виклику інструмента** та **написання Cypher-запитів**, зазначених вище."
                )
            )
            return {"messages": [tool_result_msg], "pending_tool": None}

        def route_after_parse(state: LapaAgentState) -> str:
            return "run_tool" if state.get("pending_tool") else END

        graph = StateGraph(LapaAgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("parse_tool_call", parse_tool_call_node)
        graph.add_node("run_tool", run_tool_node)

        graph.add_edge(START, "llm")
        graph.add_edge("llm", "parse_tool_call")
        graph.add_conditional_edges(
            "parse_tool_call", route_after_parse, {"run_tool": "run_tool", END: END}
        )
        graph.add_edge("run_tool", "llm")

        return graph.compile()

    def _build_openai_graph(self):
        """Build simplified graph for OpenAI models with native tool calling."""
        tools = [self.tool]
        tool_node = ToolNode(tools)

        def llm_node(state: OpenAIAgentState) -> Dict[str, Any]:
            resp = self.llm.invoke(state["messages"])
            return {"messages": [resp]}

        def should_continue(state: OpenAIAgentState) -> str:
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        graph = StateGraph(OpenAIAgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("tools", tool_node)

        graph.add_edge(START, "llm")
        graph.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "llm")

        return graph.compile()

    def invoke(self, user_text: str) -> str:
        """
        Process a user query and return the agent's response.

        Args:
            user_text: The user's question or request.

        Returns:
            The final response from the agent as a string.
        """
        init_messages: List[AnyMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_text),
        ]

        match self.agent_type:
            case "openai":
                out = self.graph.invoke({"messages": init_messages})
            case _:
                out = self.graph.invoke({"messages": init_messages, "pending_tool": None})

        final_msg = out["messages"][-1]
        return getattr(final_msg, "content", str(final_msg))
