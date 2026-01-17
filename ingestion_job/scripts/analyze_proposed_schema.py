import json
from pathlib import Path
from collections import defaultdict

def analyze_schema():
    json_path = Path("docs/proposed_neo4j/neo4j_query_table_data_2026-1-17.json")
    if not json_path.exists():
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    nodes = defaultdict(set)
    relationships = defaultdict(set)
    property_casing = defaultdict(set)

    for entry in data:
        start_label = entry.get('startLabel')
        end_label = entry.get('endLabel')
        rel_type = entry.get('relType')
        
        # Aggregate Node Properties
        for prop in entry.get('startProperties', []):
            nodes[start_label].add(prop)
            property_casing[prop.lower()].add(prop)
            
        for prop in entry.get('endProperties', []):
            nodes[end_label].add(prop)
            property_casing[prop.lower()].add(prop)
            
        # Aggregate Relationships
        relationships[(start_label, end_label)].add(rel_type)

    print("=== NODES & PROPERTIES ===")
    for label, props in sorted(nodes.items()):
        print(f"\n[{label}]")
        sorted_props = sorted(list(props))
        # Print first 10 and last 5 to avoid huge output, or grouped by casing
        print(f"  Count: {len(props)}")
        print(f"  Props: {', '.join(sorted_props)}")

    print("\n=== RELATIONSHIPS ===")
    for (start, end), rels in sorted(relationships.items()):
        print(f"{start} -> {end}: {', '.join(rels)}")

    print("\n=== POTENTIAL PROPERTY CASING ISSUES ===")
    for lower, variants in property_casing.items():
        if len(variants) > 1:
            print(f"'{lower}': {variants}")

if __name__ == "__main__":
    analyze_schema()
