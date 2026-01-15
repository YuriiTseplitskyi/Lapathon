from __future__ import annotations
import json
import hashlib
import re
from typing import Any, Dict, Optional, List
import lxml.etree as LET

from ingestion_job.app.models.documents import RawDocument, CanonicalDocument
from ingestion_job.app.services.canonical.base import CanonicalAdapter

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def _xml_to_dict(elem: LET._Element) -> Any:
    children = list(elem)
    if not children:
        txt = elem.text.strip() if elem.text and elem.text.strip() else None
        return txt
    grouped: Dict[str, Any] = {}
    for ch in children:
        key = LET.QName(ch).localname
        val = _xml_to_dict(ch)
        if key in grouped:
            if not isinstance(grouped[key], list):
                grouped[key] = [grouped[key]]
            grouped[key].append(val)
        else:
            grouped[key] = val
    return grouped

def extract_xroad_meta(root: LET._Element) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    try:
        header = root.xpath('/*[local-name()="Envelope"]/*[local-name()="Header"]')
        if not header:
            return meta
        header = header[0]
        
        def _t(path: str) -> Optional[str]:
            r = header.xpath(path)
            if not r:
                return None
            if isinstance(r[0], LET._Element):
                return normalize_ws(r[0].text or "")
            return normalize_ws(str(r[0]))
            
        registry_code = _t('.//*[local-name()="client"]//*[local-name()="subsystemCode"]/text()')
        service_code = _t('.//*[local-name()="service"]//*[local-name()="subsystemCode"]/text()')
        method_code = _t('.//*[local-name()="service"]//*[local-name()="serviceCode"]/text()')
        
        if registry_code: meta["registry_code"] = registry_code
        if service_code: meta["service_code"] = service_code
        if method_code: meta["method_code"] = method_code

        req_id = _t('.//*[local-name()="id"]/text()')
        user_id = _t('.//*[local-name()="userId"]/text()')
        if req_id: meta["xroad_request_id"] = req_id
        if user_id: meta["xroad_user_id"] = user_id
    except Exception:
        return meta
    return meta

class XmlAdapter(CanonicalAdapter):
    def can_handle(self, raw_doc: RawDocument) -> bool:
        return raw_doc.content_type == "application/xml"

    def process(self, raw_doc: RawDocument) -> CanonicalDocument:
        raw_hash = raw_doc.content_hash or sha256_bytes(raw_doc.raw_bytes)
        meta: Dict[str, Any] = {"file_path": raw_doc.file_path, "content_type": raw_doc.content_type}
        
        parse_error: Optional[str] = None
        data: Any = None

        try:
            root = LET.fromstring(raw_doc.raw_bytes)
            meta.update(extract_xroad_meta(root))
            data = {LET.QName(root).localname: _xml_to_dict(root)}
        except Exception as e:
            parse_error = f"xml_parse_error: {e}"
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
