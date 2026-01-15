
import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from app.models.documents import RawDocument
from app.services.canonical.adapter_xml import XmlAdapter
from app.services.schema.utils import eval_predicate
from app.models.schemas import MatchPredicate

def debug():
    # Sample EDR file
    fpath = "../data/nabu_data/890-ТМ-Д/В-2025-1615-034-TR7/answer.xml"
    
    with open(fpath, "rb") as f:
        content = f.read()
        
    adapter = XmlAdapter()
    raw_doc = RawDocument(
        file_path=fpath, 
        content_type="application/xml", 
        raw_bytes=content, 
        content_hash=""
    )
    
    canon_doc_obj = adapter.process(raw_doc)
    
    # Convert to dict for inspection and eval_predicate if it expects dict
    # eval_predicate uses jp_values which likely works on dicts
    import dataclasses
    canon_doc = dataclasses.asdict(canon_doc_obj)
    
    print("=== Canonical Meta ===")
    print(json.dumps(canon_doc.get("meta", {}), indent=2))
    
    print("\n=== Data Structure ===")
    def print_keys(d, prefix=""):
        if isinstance(d, dict):
            for k, v in d.items():
                print(f"{prefix}{k}")
                if isinstance(v, (dict, list)):
                    print_keys(v, prefix + "  ")
        elif isinstance(d, list):
             if d:
                 print(f"{prefix}[list of {len(d)} items]")
                 print_keys(d[0], prefix + "  ")
    
    print_keys(canon_doc.get("data", {}))
    
    print("\n=== Testing Predicate & Mapping ===")
    pred_dict = {
        "all": [
            {"type": "json_equals", "path": "$.meta.registry_code", "value": "Test_ICS_cons"},
            {"type": "json_equals", "path": "$.meta.service_code", "value": "2_MJU_EDR_prod"},
            {"type": "json_equals", "path": "$.meta.method_code", "value": "SubjectDetail2Ext"}
        ]
    }
    
    try:
        mp = MatchPredicate(**pred_dict)
        result = eval_predicate(canon_doc, mp.model_dump())
        print(f"Match Result: {result}")
        
        # Simulate Mapping
        # Hardcoding the mappings from init_schemas_full for EDR
        def m(mid, scope, src_path, target_ent, target_prop, ent_ref):
             return {"mapping_id": mid, "scope": {"foreach": scope}, "source": {"json_path": src_path}, "targets": [{"entity": target_ent, "property": target_prop, "entity_ref": ent_ref}]}
             
        mappings = []
        mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.name", "Person", "full_name", "FounderPerson"))
        mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.code", "Person", "rnokpp", "FounderPerson"))
        
        from ingestion_job.app.models.schemas import VariantMapping, MappingTarget
        from ingestion_job.app.services.schema.utils import jp_values, jp_first

        print("\n=== Executing Mappings & Tracing ===")
        
        # Trace the failing path
        full_path = "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]"
        parts = [
            "$.data",
            "$.data.Envelope",
            "$.data.Envelope.Body",
            "$.data.Envelope.Body.SubjectDetail2ExtResponse",
            "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*]",
            "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders",
            "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]"
        ]
        
        for p in parts:
             res = jp_values(canon_doc, p)
             print(f"Path '{p}': found {len(res)} items")
             if not res:
                 print("  -> FAILED HERE")
                 break

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug()
