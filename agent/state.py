from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict


class CorruptionAgentState(TypedDict):
    """
    State for the family-relationship-only agent.

    This state is shared across the minimal graph:
    - Family builder node populates family_relationships and person_ids
    """
    # Message history for agent reasoning
    messages: Annotated[List[AnyMessage], add_messages]

    # Input: target person to investigate
    target_person_query: str  # Name or RNOKPP to investigate

    # Family Builder Output
    family_relationships: Optional[Dict[str, Any]]  # Full family JSON structure
    person_ids: List[str]  # All family member IDs for easy querying
