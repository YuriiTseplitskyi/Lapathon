import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / "data" / "nabu_data"

def dump_file(rel_path):
    path = DATA_DIR / rel_path
    print(f"Reading {path}")
    if not path.exists():
        print("File not found")
        return
        
    with open(path, "r", encoding="utf-8") as f:
        print(f.read())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        dump_file(sys.argv[1])
    else:
        # Default
        dump_file("995-ІБ-Д/З-2025-1615-062-MD4/request.xml")
