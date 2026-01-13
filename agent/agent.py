from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict

from agent.config import AgentConfig, configure_langsmith_env
from agent.prompts import SYSTEM_PROMPT_EN, SYSTEM_PROMPT_UK
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
            api_key=cfg.lapa_api_key,
            temperature=cfg.temperature,
        ).bind_tools([self.tool])

        self.graph = self._build_graph()

    def _build_graph(self):
        def llm_node(state: AgentState) -> Dict[str, Any]:
            resp = self.llm.invoke(state["messages"])
            return {"messages": [resp]}

        def parse_tool_call_node(state: AgentState) -> Dict[str, Any]:
            last = state["messages"][-1]
            tc = parse_tool_call(last)
            return {"pending_tool": tc}

        def run_tool_node(state: AgentState) -> Dict[str, Any]:
            tc = state.get("pending_tool")
            if not tc:
                return {}

            query = tc["arguments"]["query"]
            tool_out = self.tool.invoke({"query": query})  # JSON string

            tool_result_msg = HumanMessage(
                content=(
                    "Результат:\n"
                    f"{tool_out}\n\n"
                    "Використай отримані дані для формування відповіді користувачу.\n"
                    "Якщо результат виклику інструмента вказує на некоректний запит, проаналізуй цей і виконай повторний запит до графа з випривленням помилки.\n"
                    "Якщо результат інструменту - порожній ([]), значить попередній результат некоректний. Повтори запит з виправленням помилки.\n"
                    "Якщо вирішив повторити запит, дотримуйся правил виклику інструмента та написання Cypher-запитів, зазначених вище."
                )
            )
            return {"messages": [tool_result_msg], "pending_tool": None}

        def route_after_parse(state: AgentState) -> str:
            return "run_tool" if state.get("pending_tool") else END

        graph = StateGraph(AgentState)
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

    def invoke(self, user_text: str) -> str:
        init_messages: List[AnyMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_text),
        ]
        out = self.graph.invoke({"messages": init_messages, "pending_tool": None})
        final_msg = out["messages"][-1]
        return getattr(final_msg, "content", str(final_msg))
