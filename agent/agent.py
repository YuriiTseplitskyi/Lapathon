from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from agent.config import AgentConfig, configure_langsmith_env
from agent.prompts import SYSTEM_PROMPT_UK
from agent.tools import make_search_graph_db_tool


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


class Agent:
    """
    Agent that iteratively queries Neo4j via native LangChain tool calling.
    """

    def __init__(
        self,
        cfg: AgentConfig,
        system_prompt: Optional[str] = None,
    ):
        configure_langsmith_env()

        self.cfg = cfg
        self.system_prompt = system_prompt or SYSTEM_PROMPT_UK
        self.tools = [
            make_search_graph_db_tool(cfg)
        ]

        # Model for tool calling (forces tool use)
        self.llm_tools = ChatOpenAI(
            model=cfg.model_name,
            base_url=cfg.base_url,
            api_key=SecretStr(cfg.lapa_api_key),
            temperature=cfg.temperature,
            stop=["<|eot_id|>", "<|end_of_text|>"],
        ).bind_tools(self.tools, tool_choice="required")

        # Model for text generation (after tool results)
        self.llm_text = ChatOpenAI(
            model="lapa",
            base_url=cfg.base_url,
            api_key=SecretStr(cfg.lapa_api_key),
            temperature=cfg.temperature,
            stop=["<|eot_id|>", "<|end_of_text|>"],
        )

        self.graph = self._build_graph()

    def _build_graph(self):
        def llm_node(state: AgentState) -> Dict[str, Any]:
            # Check if we have tool results in messages
            has_tool_results = any(
                hasattr(m, "type") and m.type == "tool" for m in state["messages"]
            )

            if has_tool_results:
                # After tool results: use text model for final answer
                resp = self.llm_text.invoke(state["messages"])
            else:
                # No tool results yet: use tool-calling model
                resp = self.llm_tools.invoke(state["messages"])

            return {"messages": [resp]}

        def should_continue(state: AgentState) -> str:
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        graph = StateGraph(AgentState)
        graph.add_node("llm", llm_node)
        graph.add_node("tools", ToolNode(tools=self.tools))

        graph.set_entry_point("llm")
        graph.add_conditional_edges(
            "llm",
            should_continue,
            {
                "tools": "tools", 
                END: END
            },
        )
        graph.add_edge("tools", "llm")

        return graph.compile()

    def invoke(self, user_text: str) -> str:
        init_messages: List[BaseMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_text),
        ]
        out = self.graph.invoke({"messages": init_messages})
        final_msg = out["messages"][-1]
        return getattr(final_msg, "content", str(final_msg))
