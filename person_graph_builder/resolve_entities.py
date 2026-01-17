import os
import json
import shutil
import argparse
from typing import Dict, List, Any, Set
from collections import defaultdict
from .config import Config

class ResolutionEngine:
    def __init__(self, run_id: str):
        self.config = Config()
        self.run_dir = os.path.join(self.config.BASE_DIR, "outputs", run_id)
        self.input_dir = os.path.join(self.run_dir, "output")
        self.output_dir = os.path.join(self.run_dir, "resolved_graph")
        self.schemas_dir = os.path.join(self.run_dir, "schemas")
        
        # Load Rules
        rules_path = os.path.join(self.schemas_dir, "resolution_rules.json")
        if os.path.exists(rules_path):
            with open(rules_path, "r") as f:
                self.rules = json.load(f)
        else:
            print(f"Warning: No resolution rules found at {rules_path}")
            self.rules = {}

        # Global ID Mapping: old_id -> canonical_id
        self.id_mapping: Dict[str, str] = {}
        
        # Stats
        self.stats = {"merged_nodes": 0, "rewired_edges": 0}

    def run(self):
        print(f"Starting Entity Resolution for run: {self.run_dir}")
        
        # 1. Prepare Output Directory
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir)
        os.makedirs(os.path.join(self.output_dir, "entities"), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, "relationships"), exist_ok=True)
        
        # 2. Load Index
        index_path = os.path.join(self.input_dir, "index.json")
        if not os.path.exists(index_path):
            print("No index.json found. Aborting.")
            return
            
        with open(index_path, "r") as f:
            index = json.load(f)
            
        original_entities = index.get("entities", {})
        original_relationships = index.get("relationships", [])
        
        # Group entities by Label
        entities_by_label = defaultdict(list)
        for uid, meta in original_entities.items():
            path = meta.get("path")
            # If path is absolute, use it. If relative, join with input_dir? 
            # The current JSONStore saves absolute paths in index (which is bad practice but current state).
            # Let's handle both.
            if not os.path.isabs(path):
                path = os.path.join(self.input_dir, path) # Fallback assumption
                
            if os.path.exists(path):
                with open(path, "r") as f:
                    node = json.load(f)
                    label = node.get("_label")
                    entities_by_label[label].append(node)
        
        # 3. Resolve Entities (Per Type)
        final_entities = {} # id -> node
        
        for label, nodes in entities_by_label.items():
            print(f"Resolving {label} ({len(nodes)} nodes)...")
            resolved = self.resolve_type(label, nodes)
            for node in resolved:
                final_entities[node["id"]] = node
                
        # 4. Save Entities
        print(f"Saving {len(final_entities)} unique entities...")
        for node in final_entities.values():
            label = node["_label"]
            node_id = node["id"]
            
            label_dir = os.path.join(self.output_dir, "entities", label)
            os.makedirs(label_dir, exist_ok=True)
            
            out_path = os.path.join(label_dir, f"{node_id}.json")
            with open(out_path, "w") as f:
                json.dump(node, f, indent=2)

        # 5. Rewire and Save Relationships
        print("Rewiring relationships...")
        final_relationships = []
        for rel in original_relationships:
            # Skip malformed relationships
            if "from_id" not in rel or "to_id" not in rel:
                continue
                
            # Map IDs
            from_id = rel["from_id"]
            to_id = rel["to_id"]
            
            new_from = self.id_mapping.get(from_id, from_id)
            new_to = self.id_mapping.get(to_id, to_id)
            
            # Update rel
            rel["from_id"] = new_from
            rel["to_id"] = new_to
            
            # Avoid self-loops if desirable? (Optional)
            # if new_from == new_to: continue 
            
            final_relationships.append(rel)
            
            # Save individual rel file (if we want to mirror structure, though typically they are just in index)
            # But let's follow pattern if needed. Currently JSONStore puts them in relationships/ID.json
            rel_id = rel.get("id") # Assuming rels have IDs
            if rel_id:
                rel_dir = os.path.join(self.output_dir, "relationships") # Flat dir ?
                # Actually JSONStore implementation puts them in output/relationships/{id}.json
                # We should mimic that.
                 
        # 6. Generate New Index
        new_index = {
            "entities": {
                node["id"]: {
                    "label": node["_label"],
                    "path": os.path.abspath(os.path.join(self.output_dir, "entities", node["_label"], f"{node['id']}.json"))
                } for node in final_entities.values()
            },
            "relationships": final_relationships
        }
        
        with open(os.path.join(self.output_dir, "index.json"), "w") as f:
            json.dump(new_index, f, indent=2)
            
        print("Done.")
        print(f"Merged {self.stats['merged_nodes']} nodes.")
        print(f"Output saved to: {self.output_dir}")

    def resolve_type(self, label: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Applies blocking and matching strategies to deduplicate nodes of a specific type.
        """
        strategies = self.rules.get(label, {}).get("identity_strategies", [])
        if not strategies:
            return nodes # No rules, no merge
        
        # Sort strategies by confidence (process highest first)
        strategies.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        # Universal Set of active nodes (we will remove merged ones)
        active_nodes = {n["id"]: n for n in nodes}
        
        # For each strategy, try to merge
        for strategy in strategies:
            keys = strategy.get("keys", [])
            stype = strategy.get("type")
            
            if not keys: continue
            
            # Blocking: Group by key values
            blocks = defaultdict(list)
            for nid, node in active_nodes.items():
                # Extract key value
                val = self._extract_key_value(node, keys, stype)
                if val:
                    blocks[val].append(nid)
            
            # Process blocks with > 1 item
            for key_val, nids in blocks.items():
                if len(nids) < 2: continue
                
                # We have a collision!
                canonical_id = self._select_canonical(nids, active_nodes)
                canonical_node = active_nodes[canonical_id]
                
                for other_id in nids:
                    if other_id == canonical_id: continue
                    
                    victim_node = active_nodes[other_id]
                    
                    # Merge properties
                    self._merge_properties(canonical_node, victim_node)
                    
                    # Record Mapping
                    self.id_mapping[other_id] = canonical_id
                    
                    # Remove victim
                    del active_nodes[other_id]
                    self.stats["merged_nodes"] += 1
                    
        return list(active_nodes.values())

    def _extract_key_value(self, node, keys, stype):
        """Generates a blocking key string from node properties."""
        values = []
        for k in keys:
            # Handle key variants "name|full_name" or ["name", "full_name"]
            if isinstance(k, list):
                search_keys = k
            else:
                search_keys = k.split("|")
            
            val = None
            for sk in search_keys:
                # Check top level
                if sk in node: val = node[sk]
                # Check 'properties' sub-dict if exists (graph schema often puts user props there)
                elif "properties" in node and sk in node["properties"]:
                    val = node["properties"][sk]
                # Check flat (json store flattens usually, but let's be safe)
                
                if val: break
            
            if not val: return None # If any part of composite key is missing, skip
            
            # Normalize
            values.append(str(val).strip().lower())
            
        return "|".join(values)

    def _select_canonical(self, nids, nodes_map):
        """Selects the best node to keep. Prioritize formal IDs."""
        # Simple heuristic: shortest ID (often integer/rnokpp) vs Long Hash/Composite
        # OR: Prefer node with most properties?
        
        def score(nid):
            n = nodes_map[nid]
            val = 0
            # Preference 1: ID is digit (rnokpp)
            if nid.isdigit(): val += 100
            # Preference 2: ID length (shorter is usually 'cleaner' formal id, longer is often composite)
            val -= len(nid) 
            return val

        return max(nids, key=score)

    def _merge_properties(self, target, source):
        """Merges source props into target if missing."""
        for k, v in source.items():
            if k not in target or not target[k]:
                target[k] = v
            elif k == "identifying_keys":
                 # Merge lists
                 target[k] = list(set(target.get(k, []) + v))

def main():
    parser = argparse.ArgumentParser(description="Resolve Entities (Entity Resolution)")
    parser.add_argument("--run-id", required=True, help="Run ID to resolve")
    args = parser.parse_args()
    
    engine = ResolutionEngine(args.run_id)
    engine.run()

if __name__ == "__main__":
    main()
