from __future__ import annotations
import json
import hashlib
from typing import List, Optional
from pathlib import Path

from ingestion_job.app.models.documents import RawDocument, CanonicalDocument
from ingestion_job.app.services.canonical.base import CanonicalAdapter
from ingestion_job.app.services.canonical.adapter_json import JsonAdapter
from ingestion_job.app.services.canonical.adapter_xml import XmlAdapter

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def detect_content_type(file_path: str, raw: bytes) -> str:
    s = raw.lstrip()[:50]
    if s.startswith(b"{") or s.startswith(b"["):
        return "application/json"
    if s.startswith(b"<"):
        return "application/xml"
        
    lp = file_path.lower()
    if lp.endswith(".json"):
        return "application/json"
    if lp.endswith(".xml"):
        return "application/xml"
    
    return "application/octet-stream"

def read_raw_document(file_path: str) -> RawDocument:
    p = Path(file_path)
    raw = p.read_bytes()
    ct = detect_content_type(str(p), raw)
    return RawDocument(
        file_path=str(p),
        content_type=ct,
        raw_bytes=raw,
        encoding="utf-8",
        content_hash=sha256_bytes(raw),
    )

class CanonicalizerService:
    def __init__(self):
        self.adapters: List[CanonicalAdapter] = [
            JsonAdapter(),
            XmlAdapter(),
        ]

    def canonicalize(self, raw_doc: RawDocument) -> CanonicalDocument:
        for adapter in self.adapters:
            if adapter.can_handle(raw_doc):
                return adapter.process(raw_doc)
        
        # Fallback for unsupported types
        raw_hash = raw_doc.content_hash or sha256_bytes(raw_doc.raw_bytes)
        canonical_bytes = json.dumps({
            "meta": {
                "file_path": raw_doc.file_path, 
                "content_type": raw_doc.content_type
            }, 
            "data": {"_raw_preview": raw_doc.raw_bytes[:500].decode("utf-8", errors="replace")}
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        
        return CanonicalDocument(
            file_path=raw_doc.file_path,
            content_type=raw_doc.content_type,
            raw_hash=raw_hash,
            canonical_hash=sha256_bytes(canonical_bytes),
            meta={"file_path": raw_doc.file_path, "content_type": raw_doc.content_type},
            data={"_raw_preview": raw_doc.raw_bytes[:500].decode("utf-8", errors="replace")},
            parse_error=f"unsupported_content_type: {raw_doc.content_type}"
        )
