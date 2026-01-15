
import sys
import json
from pathlib import Path

# Fix paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from ingestion_job.app.services.canonical.service import read_raw_document, CanonicalizerService

from ingestion_job.app.services.schema.utils import jp_values

def debug(file_path):
    raw = read_raw_document(file_path)
    service = CanonicalizerService()
    canonical = service.canonicalize(raw)
    
    canonical_dict = {"meta": canonical.meta, "data": canonical.data}
    print("Canonical Dict keys:", canonical_dict.keys())
    
    paths = [
        "$.data",
        "$.data.Envelope",
        "$.data.Envelope.Body",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*]",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder",
        "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]"
    ]
    
    for p in paths:
        print(f"Testing path: {p}")
        try:
            items = jp_values(canonical_dict, p)
            print(f"  -> Found {len(items)} items.")
            if items and len(items) > 0:
                 print(f"  -> Type of first item: {type(items[0])}")
        except Exception as e:
            print(f"  -> Error: {e}")



if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        debug(sys.argv[1])
