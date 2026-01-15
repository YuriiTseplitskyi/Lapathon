
import os
import sys
import glob
from collections import defaultdict
from pathlib import Path
import lxml.etree as LET

# Add parent dir to path if needed, or just run standalone
# We just need simple XML parsing

def normalize_ws(s):
    if not s: return ""
    return " ".join(s.split())

def extract_meta(file_path):
    try:
        tree = LET.parse(file_path)
        root = tree.getroot()
        
        # Namespaces are annoying in lxml so we use local-name()
        def _t(xpath):
            r = root.xpath(xpath)
            if r:
                return normalize_ws(r[0].text if hasattr(r[0], 'text') else str(r[0]))
            return None

        # Standard X-Road header paths (as seen in adapter_xml or debug output)
        # We look for service/subsystemCode
        
        # Note: root is usually Envelope
        registry = _t('/*[local-name()="Envelope"]/*[local-name()="Header"]/*[local-name()="client"]/*[local-name()="subsystemCode"]')
        service = _t('/*[local-name()="Envelope"]/*[local-name()="Header"]/*[local-name()="service"]/*[local-name()="subsystemCode"]')
        method = _t('/*[local-name()="Envelope"]/*[local-name()="Header"]/*[local-name()="service"]/*[local-name()="serviceCode"]')
        
        return registry, service, method
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None, None, None

def analyze(data_dirs):
    stats = defaultdict(list)
    
    files = []
    for d in data_dirs:
        # Recursive search for answer.xml
        path = Path(d)
        files.extend(path.rglob("answer.xml"))
        
    print(f"Found {len(files)} answer.xml files.")
    
    for f in files:
        r, s, m = extract_meta(str(f))
        if r and s and m:
            key = (r, s, m)
            stats[key].append(str(f))
        else:
            # print(f"Missing meta in {f}")
            pass

    print("\n=== Discovered Services ===")
    for (r, s, m), fs in stats.items():
        print(f"Registry: {r} | Service: {s} | Method: {m} | Count: {len(fs)}")
        print(f"  Sample: {fs[0]}")

if __name__ == "__main__":
    dirs = [
        "../data/nabu_data/890-ТМ-Д",
        "../data/nabu_data/891-ТМ-Д"
    ]
    analyze(dirs)
