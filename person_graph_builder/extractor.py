import json
from typing import List, Dict, Any
from .config import Config

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class Extractor:
    def __init__(self, config: Config):
        self.config = config
        self.model_config = config.MODEL_CONFIGS.get("extractor", {})
        self.model = self.model_config.get("model", "gpt-5.2")
        self.temperature = self.model_config.get("temperature", 0.0)
        self.reasoning_effort = self.model_config.get("reasoning_effort")
        
        self.client = None
        if config.OPENAI_API_KEY and OpenAI:
            base_url = self.model_config.get("base_url")
            self.client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=base_url)

    def extract(self, content: str, entity_types: List[Dict[str, Any]], doc_name: str = "doc") -> Dict[str, Any]:
        """
        Extracts entities and relationships from content using LLM.
        """
        if not self.client:
            print("No LLM Client available. Skipping extraction.")
            return {"entities": [], "relationships": []}

        # Prepare context (catalogue)
        catalogue_str = json.dumps([{
            "type": e.get("entity_name"),
            "pk": e.get("primary_keys")
        } for e in entity_types], indent=2)

        system_prompt = """
You are a Knowledge Graph extraction expert.
Extract entities and relationships from the provided document content.

1. Match entities against the provided Entity Catalogue (Types and Primary Keys).
2. If you find an entity that fits a catalogue type, extract it using that Label.
3. If you find a clear entity concept that is NOT in the catalogue, YOU MUST CREATE A NEW TYPE for it.
4. Extract relationships between these entities. 
5. CRITICAL: Identify a stable ID (Primary Key) for each entity.
   - If a formal ID exists (e.g. 'code', 'rnokpp', 'passport', 'vin'), use it.
   - If NO formal ID exists, CONSTRUCT a deterministic ID from stable attributes (e.g. 'Series+Number', 'Name+DateOfBirth', 'Street+City').
   - Ideally, the 'id' should be unique enough to deduplicate the entity across documents.
   - Normalize this value to the field 'id'.
   - ALSO return a field 'identifying_keys': ["col1", "col2"] indicating which properties formed the ID.

6. RULES for Nested/Hidden Entities:
   - If an entity (e.g., "Owner", "Grantor", "Witness", "Representative") is embedded inside another object, YOU MUST EXTRACT IT AS A SEPARATE NODE.
   - Do NOT just verify the "data"; convert it into a Graph Node.
   - Create a RELATIONSHIP between the parent and the child (e.g., Vehicle -> OWNS -> Person).
   - Look for attributes like "SUMA", "PRICE", "VALUE" at any level and attach them to the relevant entity (e.g. Property).

Feature Examples:

Input (JSON):
{
  "CARS": [
    {
       "VIN": "ABC12345",
       "SUMA": 50000,
       "OWNER": { "NAME": "JOHN DOE", "TAX_ID": "998877" }
    }
  ]
}

Output (JSON):
{
  "entities": [
    {
      "label": "Property",
      "id": "ABC12345",
      "properties": { "vin": "ABC12345", "suma": 50000, "type": "Car" }
    },
    {
      "label": "Person",
      "id": "998877",
      "properties": { "name": "JOHN DOE", "tax_id": "998877" }
    }
  ],
  "relationships": [
    {
      "type": "OWNED_BY",
      "from_label": "Property",
      "from_id": "ABC12345",
      "to_label": "Person",
      "to_id": "998877"
    }
  ]
}

Input (XML):
<Grantor>
  <Name>Jane Smith</Name>
  <Code>112233</Code>
</Grantor>
<Property>
  <Vin>XYZ987</Vin>
</Property>

Output (JSON):
{
  "entities": [
     { "label": "Person", "id": "112233", "properties": { "name": "Jane Smith", "code": "112233", "role": "Grantor" } },
     { "label": "Property", "id": "XYZ987", "properties": { "vin": "XYZ987" } }
  ],
  "relationships": [
     { "type": "GRANTOR_OF", "from_label": "Person", "from_id": "112233", "to_label": "Property", "to_id": "XYZ987" }
  ]
}

Output Format (JSON):
{
  "entities": [ ... ],
  "relationships": [ ... ],
  "schema_updates": [ ... ]
}
"""
        user_prompt = f"""
Entity Catalogue:
{catalogue_str}

Document Content (Truncated):
{content}
"""
        try:
            # Prepare params
            params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            
            # Add optional params
            if self.temperature is not None:
                params["temperature"] = self.temperature
                
            if self.reasoning_effort:
                # Note: reasoning_effort is supported in newer models/APIs. 
                # If API rejects it for standard models, we should catch or conditionalize.
                # Assuming user knows it works for selected model.
                params["reasoning_effort"] = self.reasoning_effort

            response = self.client.chat.completions.create(**params)
            txt = response.choices[0].message.content
            
            # Logging
            if self.config.STORE_LOGS:
                import os
                os.makedirs(self.config.LOGS_DIR, exist_ok=True)
                log_data = {
                    "doc_name": doc_name,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "response": txt
                }
                log_path = os.path.join(self.config.LOGS_DIR, f"{doc_name}.json")
                with open(log_path, "w") as f:
                    json.dump(log_data, f, indent=2)
            
            return json.loads(txt)
        except Exception as e:
            print(f"Extraction failed: {e}")
            return {"entities": [], "relationships": []}
