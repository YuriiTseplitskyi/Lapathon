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
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

from agent.app.core.settings import AgentConfig, configure_langsmith_env
from agent.app.services.agent.prompts import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_UK
from agent.app.tools.search_graph_db import make_search_graph_db_tool


TOOL_CALL_RE = re.compile(r"(?s)<tool_call>\s*(\{.*?\})\s*</tool_call>")


def _maybe_parse_custom_tool_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Fallback parser for the legacy inline <tool_call>{...}</tool_call> format.
    """
    if not text:
        return None
    match = TOOL_CALL_RE.search(text)
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


def extract_tool_call_from_text(message: AnyMessage) -> Optional[Dict[str, Any]]:
    """
    Support both native tool-calls (AIMessage.tool_calls) and the legacy inline format.
    """
    if isinstance(message, AIMessage) and message.tool_calls:
        call = message.tool_calls[0]
        args = call.get("args") or call.get("arguments") or {}
        if not isinstance(args, dict):
            return None
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return None
        return {"id": call.get("id") or "tool-call-0", "name": call.get("name"), "arguments": args}

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return _maybe_parse_custom_tool_text(content)
    return None


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    pending_tool: Optional[Dict[str, Any]]


class Agent:
    """
    Agent that guides an LLM to issue a single Neo4j Cypher query via a LangChain tool.
    """

    def __init__(
        self,
        cfg: AgentConfig,
        system_prompt: Optional[str] = None,
    ):
        configure_langsmith_env()

        self.cfg = cfg
        self.system_prompt = system_prompt or SYSTEM_PROMPT_UK
        self.tool = make_search_graph_db_tool(cfg)

        self.llm = ChatOpenAI(
            model=cfg.model_name,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            temperature=cfg.temperature,
        ).bind_tools([self.tool])

        self.graph = self._build_graph()

    def _build_graph(self):
        def assistant_node(state: AgentState) -> Dict[str, Any]:
            resp = self.llm.invoke(state["messages"])
            return {"messages": [resp]}

        def parse_tool_call_node(state: AgentState) -> Dict[str, Any]:
            last = state["messages"][-1]
            tc = extract_tool_call_from_text(last)
            return {"pending_tool": tc}

        def run_tool_node(state: AgentState) -> Dict[str, Any]:
            tc = state.get("pending_tool")
            if not tc:
                return {}

            query = tc["arguments"]["query"]
            tool_out = self.tool.invoke({"query": query})  # JSON string

            tool_result_msg = HumanMessage(
                content=(
                    "TOOL RESULT (search_graph_db):\n"
                    f"{tool_out}\n\n"
                    "Use this tool result to answer the request."
                )
            )
            return {"messages": [tool_result_msg], "pending_tool": None}

        def route_after_parse(state: AgentState) -> str:
            return "run_tool" if state.get("pending_tool") else END

        graph = StateGraph(AgentState)
        graph.add_node("assistant", assistant_node)
        graph.add_node("parse_tool_call", parse_tool_call_node)
        graph.add_node("run_tool", run_tool_node)

        graph.add_edge(START, "assistant")
        graph.add_edge("assistant", "parse_tool_call")
        graph.add_conditional_edges(
            "parse_tool_call", route_after_parse, {"run_tool": "run_tool", END: END}
        )
        graph.add_edge("run_tool", "assistant")  # loop back; assistant may decide to call tool again

        return graph.compile()

    def invoke(self, user_text: str) -> str:
        init_messages: List[AnyMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_text),
        ]
        out = self.graph.invoke({"messages": init_messages, "pending_tool": None})
        final_msg = out["messages"][-1]
        return getattr(final_msg, "content", str(final_msg))
