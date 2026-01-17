from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict


class CorruptionAgentState(TypedDict):
    """
    State for the corruption detection agent.

    This state is shared across the graph:
    - Family builder node populates family_relationships and person_ids
    - Income/assets analyzer node populates income_assets_analysis
    """
    # Message history for agent reasoning
    messages: Annotated[List[AnyMessage], add_messages]

    # Input: target person to investigate
    target_person_query: str  # Name or RNOKPP to investigate

    # Family Builder Output
    family_relationships: Optional[Dict[str, Any]]  # Full family JSON structure
    person_ids: List[str]  # All family member IDs for easy querying

    # Income vs Assets Analysis Output
    income_assets_analysis: Optional[Dict[str, Any]]  # Gap analysis and risk scoring
