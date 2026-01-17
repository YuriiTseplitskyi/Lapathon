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
    - Proxy ownership analyzer node populates proxy_ownership_analysis
    - Shell company analyzer node populates shell_company_analysis
    - Summary node aggregates corruption_summary in Ukrainian
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

    # Proxy Ownership Analysis Output
    proxy_ownership_analysis: Optional[Dict[str, Any]]  # Proxy/nominee ownership detection

    # Shell Company Analysis Output
    shell_company_analysis: Optional[Dict[str, Any]]  # Shell/front company detection

    # Final Ukrainian summaries by corruption pattern
    corruption_summary: Optional[Dict[str, Any]]
