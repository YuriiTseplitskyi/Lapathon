from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class NodeRecord:
    label: str
    node_id: str
    properties: Dict[str, Any]
    source_doc: str
    scope_root: str
    entity_ref: str

@dataclass
class RelRecord:
    rel_type: str
    from_label: str
    from_id: str
    to_label: str
    to_id: str
    properties: Dict[str, Any]
    source_doc: str
    scope_root: str
    name: str

@dataclass
class EntityInstance:
    label: str
    entity_ref: str
    scope_root: str
    # scope_id is unique per instance (nested foreach). scope_root is top-level grouping.
    scope_id: str
    properties: Dict[str, Any]
    node_id: Optional[str] = None
