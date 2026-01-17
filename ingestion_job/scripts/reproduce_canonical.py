import sys
from pathlib import Path
import json

# Setup path to import app
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR.parent))

from ingestion_job.app.models.documents import RawDocument
from ingestion_job.app.services.canonical.service import CanonicalizerService
from ingestion_job.app.services.schema.utils import eval_predicate, jp_first

DATA_DIR = BASE_DIR.parent / "data" / "nabu_data"

def reproduce(rel_path):
    path = DATA_DIR / rel_path
    if not path.exists():
        print(f"File not found: {path}")
        return

    raw_bytes = path.read_bytes()
    raw_doc = RawDocument(
        file_path=str(path),
        content_type="application/xml",
        raw_bytes=raw_bytes,
        encoding="utf-8",
        content_hash="test"
    )
    
    svc = CanonicalizerService()
    canonical = svc.canonicalize(raw_doc)
    
    print(json.dumps(canonical.data, indent=2, ensure_ascii=False))
    
    wrapper = {"data": canonical.data, "meta": canonical.meta}
    path = "$.data.Envelope.Header.service.serviceCode"
    
    val = jp_first(wrapper, path)
    print(f"Extracted Value: '{val}'")
    
    predicate = {
        "all": [
            {"type": "json_equals", "path": path, "value": "InfoIncomeSourcesDRFO2Query"}
        ]
    }
    
    matched, _, _ = eval_predicate(wrapper, predicate)
    print(f"Matched: {matched}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        reproduce(sys.argv[1])
    else:
        reproduce("995-ІБ-Д/З-2025-1615-062-MD4/request.xml")
