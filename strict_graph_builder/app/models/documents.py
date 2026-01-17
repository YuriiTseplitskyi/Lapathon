from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class RawDocument:
    file_path: str
    content_type: str
    raw_bytes: bytes
    encoding: str = "utf-8"
    content_hash: str = ""

@dataclass
class CanonicalDocument:
    file_path: str
    content_type: str
    raw_hash: str
    canonical_hash: str
    meta: Dict[str, Any]
    data: Any
    parse_error: Optional[str] = None
