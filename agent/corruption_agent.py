from __future__ import annotations

from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agent.config import AgentConfig
from agent.nodes import create_family_builder_node, create_income_assets_node, create_proxy_ownership_node, create_shell_company_node
from agent.state import CorruptionAgentState


class CorruptionDetectionAgent:
    """
    Corruption detection agent with family relationship discovery, income/assets analysis, proxy ownership detection, and shell company detection.

    Architecture:
    START -> family_builder -> income_assets_analyzer -> proxy_ownership_analyzer -> shell_company_analyzer -> END
    """

    def __init__(self, cfg: AgentConfig):
        """
        Initialize the agent.

        Args:
            cfg: Agent configuration with LLM and Neo4j settings.
        """
        self.cfg = cfg
        self.graph = self._build_graph()

    def _build_graph(self):
        """
        Build the LangGraph state machine for corruption detection.

        Returns:
            Compiled LangGraph state machine.
        """
        builder = StateGraph(CorruptionAgentState)

        # Create nodes
        family_node = create_family_builder_node(self.cfg)
        income_assets_node = create_income_assets_node(self.cfg)
        proxy_ownership_node = create_proxy_ownership_node(self.cfg)
        shell_company_node = create_shell_company_node(self.cfg)

        # Add nodes to graph
        builder.add_node("family_builder", family_node)
        builder.add_node("income_assets_analyzer", income_assets_node)
        builder.add_node("proxy_ownership_analyzer", proxy_ownership_node)
        builder.add_node("shell_company_analyzer", shell_company_node)

        # Define sequential edges
        builder.add_edge(START, "family_builder")
        builder.add_edge("family_builder", "income_assets_analyzer")
        builder.add_edge("income_assets_analyzer", "proxy_ownership_analyzer")
        builder.add_edge("proxy_ownership_analyzer", "shell_company_analyzer")
        builder.add_edge("shell_company_analyzer", END)

        return builder.compile()

    def invoke(self, target_person_query: str) -> Dict[str, Any]:
        """
        Run the corruption detection analysis for a target person.

        Args:
            target_person_query: Name, RNOKPP, or other identifier for the target person.

        Returns:
            Dictionary containing family relationships, income/assets analysis, proxy ownership analysis, shell company analysis, and person_ids.
        """
        initial_state: CorruptionAgentState = {
            "messages": [HumanMessage(content=f"Analyze corruption patterns for: {target_person_query}")],
            "target_person_query": target_person_query,
            "family_relationships": None,
            "person_ids": [],
            "income_assets_analysis": None,
            "proxy_ownership_analysis": None,
            "shell_company_analysis": None,
        }

        result = self.graph.invoke(initial_state)
        return result

    def get_family_data(self, target_person_query: str) -> Dict[str, Any]:
        """
        Convenience method to get only family relationships and person ids.

        Args:
            target_person_query: Name, RNOKPP, or other identifier for the target person.

        Returns:
            The extracted family relationships and related person ids.
        """
        result = self.invoke(target_person_query)
        return {
            "family_relationships": result.get("family_relationships"),
            "person_ids": result.get("person_ids", []),
        }

    def get_graph_visualization(self) -> str:
        """
        Get ASCII visualization of the agent graph.

        Returns:
            ASCII art representation of the graph structure.
        """
        return self.graph.get_graph().draw_ascii()


def build_corruption_detection_graph(cfg: AgentConfig):
    """
    Factory function to build just the graph without the agent wrapper.

    Args:
        cfg: Agent configuration.

    Returns:
        Compiled LangGraph state machine.
    """
    agent = CorruptionDetectionAgent(cfg)
    return agent.graph
