from __future__ import annotations
import json
import hashlib
from typing import Any, Dict, Optional

from ingestion_job.app.models.documents import RawDocument, CanonicalDocument
from ingestion_job.app.services.canonical.base import CanonicalAdapter

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def heuristic_meta_from_json(obj: Any) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if isinstance(obj, dict) and "root" in obj and isinstance(obj["root"], dict):
        r = obj["root"]
        if "result" in r and isinstance(r["result"], dict):
            # EIS person-like
            if any(k in r["result"] for k in ("rnokpp", "unzr", "first_name", "last_name", "date_birth")):
                meta["registry_code"] = "EIS"
                meta["service_code"] = "PERSON"
    return meta

class JsonAdapter(CanonicalAdapter):
    def can_handle(self, raw_doc: RawDocument) -> bool:
        return raw_doc.content_type == "application/json"

    def process(self, raw_doc: RawDocument) -> CanonicalDocument:
        raw_hash = raw_doc.content_hash or sha256_bytes(raw_doc.raw_bytes)
        meta: Dict[str, Any] = {"file_path": raw_doc.file_path, "content_type": raw_doc.content_type}
        
        parse_error: Optional[str] = None
        data: Any = None
        
        try:
            raw_str = raw_doc.raw_bytes.decode(raw_doc.encoding, errors="replace")
            # Cleanup trailing commas
            import re
            raw_str = re.sub(r',(\s*[\]}])', r'\1', raw_str)
            obj = json.loads(raw_str)
            data = obj
            meta.update(heuristic_meta_from_json(obj))
        except Exception as e:
            parse_error = f"json_parse_error: {e}"
            data = {"_raw_preview": raw_doc.raw_bytes[:500].decode("utf-8", errors="replace")}
            
        canonical_bytes = json.dumps({"meta": meta, "data": data}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        canonical_hash = sha256_bytes(canonical_bytes)
        
        return CanonicalDocument(
            file_path=raw_doc.file_path,
            content_type=raw_doc.content_type,
            raw_hash=raw_hash,
            canonical_hash=canonical_hash,
            meta=meta,
            data=data,
            parse_error=parse_error,
        )
