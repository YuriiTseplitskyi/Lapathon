import os
import json
import random
import argparse
from typing import List, Dict, Any
from openai import OpenAI
from .config import Config

class RuleGenerator:
    def __init__(self, run_id: str):
        self.config = Config()
        self.run_dir = os.path.join(self.config.BASE_DIR, "outputs", run_id)
        self.output_dir = os.path.join(self.run_dir, "output")
        self.schemas_dir = os.path.join(self.run_dir, "schemas")  # Target for rules
        
        # Load Model Config
        self.model_config = self.config.MODEL_CONFIGS.get("rule_generator", {})
        self.model = self.model_config.get("model", "gpt-5.2")
        self.temperature = self.model_config.get("temperature", 0.2)
        self.reasoning_effort = self.model_config.get("reasoning_effort")

        if self.config.OPENAI_API_KEY:
             self.client = OpenAI(api_key=self.config.OPENAI_API_KEY)
        else:
             raise ValueError("OPENAI_API_KEY not found in Config")

    def load_samples(self, entity_type: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Loads random sample of entities of a given type."""
        entity_dir = os.path.join(self.output_dir, "entities", entity_type)
        if not os.path.exists(entity_dir):
            return []
        
        files = [f for f in os.listdir(entity_dir) if f.endswith(".json")]
        if not files:
            return []
            
        # Random sample
        selected_files = random.sample(files, min(len(files), limit))
        
        samples = []
        for fname in selected_files:
            try:
                with open(os.path.join(entity_dir, fname), "r") as f:
                    data = json.load(f)
                    # Remove internal fields to clean up context for LLM
                    clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
                    samples.append(clean_data)
            except Exception as e:
                print(f"Error reading {fname}: {e}")
                
        return samples

    def generate_rules_for_type(self, entity_type: str, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prompts LLM to deduce resolution rules."""
        
        system_prompt = """
You are a Data Architect Expert.
Your task is to analyze a sample of JSON entities and deduce the "Identity Resolution Rules".

Goal: Identify how to determine if two JSON objects represent the SAME real-world entity.

Output a JSON object with this structure:
{
  "identity_strategies": [
    {
      "type": "exact",
      "keys": ["tax_id"], 
      "confidence": 1.0,
      "description": "Unique Government ID"
    },
    {
      "type": "composite",
      "keys": ["first_name", "last_name", "birth_date"],
      "confidence": 0.9,
      "description": "Combination of name and dob when ID is missing"
    }
  ]
}

- "exact": A single field that is globally unique (ID, Code, UUID). Confidence usually 1.0.
- "composite": A list of fields that, when combined, strongly imply identity. Confidence usually 0.8-0.9.
- IGNORE fields that are clearly content/data (e.g. "status", "date_created", "notes") unless they are part of the identity.
- Look for common patterns in differences (e.g. one record has "id", another has "rnokpp" - if they mean the same, list them as valid keys).
"""
        
        user_prompt = f"""
Entity Type: {entity_type}
Sample Data ({len(samples)} records):
{json.dumps(samples, indent=2)}

Analyze the structure. Which fields indicate identity?
Note: Some records might have an ID, some might be missing it. We need rules that cover both cases if possible.
"""

        try:
            params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            if self.temperature is not None:
                params["temperature"] = self.temperature
            # if self.reasoning_effort:
            #     params["reasoning_effort"] = self.reasoning_effort

            print(f"  Thinking about {entity_type}...")
            response = self.client.chat.completions.create(**params)
            txt = response.choices[0].message.content
            print(f"  [DEBUG] LLM Output for {entity_type}: {txt[:200]}...") # Debug print
            return json.loads(txt)
        except Exception as e:
            print(f"LLM Error for {entity_type}: {e}")
            return {"identity_strategies": []}

    def run(self):
        # 1. discover entity types in output
        entities_root = os.path.join(self.output_dir, "entities")
        if not os.path.exists(entities_root):
             print(f"No entities found in {entities_root}")
             return

        entity_types = [d for d in os.listdir(entities_root) if os.path.isdir(os.path.join(entities_root, d))]
        print(f"Found types: {entity_types}")
        
        all_rules = {}
        
        for etype in entity_types:
            print(f"Sampling {etype}...")
            samples = self.load_samples(etype)
            if not samples:
                print(f"  No samples for {etype}, skipping.")
                continue
                
            rules = self.generate_rules_for_type(etype, samples)
            all_rules[etype] = rules
            
        # Save to schemas
        os.makedirs(self.schemas_dir, exist_ok=True)
        out_path = os.path.join(self.schemas_dir, "resolution_rules.json")
        with open(out_path, "w") as f:
            json.dump(all_rules, f, indent=2)
            
        print(f"Generated resolution rules at: {out_path}")
        print(json.dumps(all_rules, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Generate Resolution Rules using AI")
    parser.add_argument("--run-id", required=True, help="Run ID to analyze")
    args = parser.parse_args()
    
    gen = RuleGenerator(args.run_id)
    gen.run()

if __name__ == "__main__":
    main()
