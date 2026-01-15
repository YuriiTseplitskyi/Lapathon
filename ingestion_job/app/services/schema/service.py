from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from ingestion_job.app.models.schemas import RegisterSchema, RegisterSchemaVariant
from ingestion_job.app.services.schema.utils import eval_predicate

def resolve_variant_impl(canonical_doc: Dict[str, Any], register_schemas: List[RegisterSchema]) -> Tuple[Optional[RegisterSchemaVariant], Dict[str, Any]]:
    # Safely handle canonical_doc having meta or potentially just being meta/data dict
    # Assuming standard structure {meta: ..., data: ...}
    meta = canonical_doc.get("meta", {}) if isinstance(canonical_doc, dict) else {}
    rc = meta.get("registry_code")
    sc = meta.get("service_code")
    mc = meta.get("method_code")

    candidates: List[Tuple[RegisterSchemaVariant, int, List[str], RegisterSchema]] = []
    for rs in register_schemas:
        if rc and rs.registry_code != rc:
            continue
        if rs.service_code and sc and rs.service_code != sc:
            continue
        if rs.method_code and mc and rs.method_code != mc:
            continue
        for v in rs.variants:
            matched, score, reasons = eval_predicate(canonical_doc, v.match_predicate.model_dump())
            if matched:
                candidates.append((v, score, reasons, rs))

    debug: Dict[str, Any] = {
        "meta": {"registry_code": rc, "service_code": sc, "method_code": mc},
        "candidates": [{"variant_id": v.variant_id, "score": score, "reasons": reasons, "registry_code": rs.registry_code, "service_code": rs.service_code, "method_code": rs.method_code}
                       for (v, score, reasons, rs) in candidates]
    }

    if not candidates:
        return None, debug

    candidates.sort(key=lambda t: t[1], reverse=True)
    best_score = candidates[0][1]
    best = [c for c in candidates if c[1] == best_score]
    if len(best) != 1:
        debug["ambiguity"] = [b[0].variant_id for b in best]
        return None, debug
    return best[0][0], debug
