import os
import json
from openai import OpenAI
import xmltodict
from .config import Config

# Configuration
DIRECTORIES = [
    "data/890-ТМ-Д",
    "data/891-ТМ-Д"
]
OUTPUT_FILE = "schemas/entity_types.json"

def get_sample_files(base_dir, samples_per_dir=1):
    samples = []
    if not os.path.exists(base_dir):
        return samples
    
    for root, dirs, files in os.walk(base_dir):
        xml_files = [f for f in files if f.endswith(".xml") or f.endswith(".XML")]
        if xml_files:
            samples.append(os.path.join(root, xml_files[0]))
            
    return samples

    return samples

def extract_schema_heuristic(content):
    print("  Using heuristic extraction (no API key)...")
    types = []
    try:
        # Heuristic for the known XML structure (registry data)
        data = xmltodict.parse(content)
        # Navigate to Body -> SubjectDetail2ExtResponse -> Subject
        # This path is specific to the sample we saw. We'll be robust-ish.
        
        def find_keys(obj, key):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if key in k: # partial match for namespaces
                        yield v
                    if isinstance(v, (dict, list)):
                        yield from find_keys(v, key)
            elif isinstance(obj, list):
                for item in obj:
                    yield from find_keys(item, key)

        # Look for "Subject"
        subjects = list(find_keys(data, "Subject"))
        if subjects:
             types.append({
                 "entity_name": "Subject", 
                 "primary_keys": ["code"], 
                 "description": "Legal Entity or Organization (Heuristic)"
             })
             
             # Check distinct sub-entities in first subject to guess structure
             # parsing founders
             has_founders = list(find_keys(subjects[0], "founder"))
             if has_founders:
                 types.append({
                     "entity_name": "Founder",
                     "primary_keys": ["code"],
                     "description": "Founder of the subject (Heuristic)"
                 })
                 
             has_heads = list(find_keys(subjects[0], "head"))
             if has_heads:
                 types.append({
                     "entity_name": "Head",
                     "primary_keys": ["rnokpp"],
                     "description": "Head/Director of the subject (Heuristic)"
                 })
                 
    except Exception as e:
        print(f"  Heuristic failed: {e}")
    
    return types

def extract_schema_from_content(content, client, existing_types=None):
    if not client:
        return extract_schema_heuristic(content)

    existing_context = ""
    if existing_types:
        names = [t.get("entity_name") for t in existing_types]
        existing_context = f"EXISTING KNOWN ENTITY TYPES: {json.dumps(names)}\nReuse these if they fit the data."

    prompt = f"""
    You are a Data Architect designing a Knowledge Graph for investigative analysis.
    
    GOAL: Define a schema to map this document's content into a Graph.
    - Focus on KEY business entities: Person, Company, Vehicle, RealEstate, Document, Event.
    - IGNORE low-level XML/technical wrappers (e.g., "ResponseHeader", "Body", "Result", "Log").
    - We want to connect "Who did What to Whom".
    
    {existing_context}

    Task:
    1. Analyze the document snippet.
    2. Identify the Key Entity Types (Classes).
    3. For each, determine the Primary Key (unique identifier).
    
    Snippet:
    {content[:10000]}
    
    Output JSON list:
    [
      {{ "entity_name": "Person", "primary_keys": ["rnokpp"], "description": "Physical person involved in transaction" }}
    ]
    """
    model_cfg = Config.MODEL_CONFIGS.get("discovery", {})
    model = model_cfg.get("model", "gpt-5.2")
    temp = model_cfg.get("temperature", 0.0)
    reasoning = model_cfg.get("reasoning_effort")

    params = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temp is not None:
        params["temperature"] = temp
    if reasoning:
        params["reasoning_effort"] = reasoning

    try:
        response = client.chat.completions.create(**params)
        txt = response.choices[0].message.content.strip()
        if txt.startswith("```"):
            txt = txt.strip("`").replace("json\n", "", 1)
        return json.loads(txt)
    except Exception as e:
        print(f"Error: {e}")
        return []

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    client = None
    if not api_key:
        print("Warning: OPENAI_API_KEY not found. Switching to Heuristic Mode.")
        raise Exception("OPENAI_API_KEY not found")
    else:
        client = OpenAI(api_key=api_key)
    
    all_files = []
    for d in DIRECTORIES:
        all_files.extend(get_sample_files(d))
    
    print(f"Found {len(all_files)} potential sample files.")
    
    subset = all_files[:15] 
    print(f"Sampling {len(subset)} files for discovery...")
    
    discovered_types = {}
    
    # Load existing if available
    if os.path.exists(OUTPUT_FILE):
        try:
             with open(OUTPUT_FILE, "r") as f:
                 data = json.load(f)
                 for t in data.get("entity_types", []):
                     discovered_types[t["entity_name"]] = t
             print(f"Loaded {len(discovered_types)} existing types.")
        except Exception as e:
             print(f"Could not load existing schema: {e}")

    for fpath in subset:
        print(f"Analyzing {fpath}...")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            
            entities = extract_schema_from_content(content, client, list(discovered_types.values()))
            for ent in entities:
                name = ent.get("entity_name")
                if name:
                    if name not in discovered_types:
                        discovered_types[name] = ent
        except Exception as e:
            print(f"Failed to read {fpath}: {e}")

    # Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    result = {"entity_types": list(discovered_types.values())}
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"Saved entity types to {OUTPUT_FILE}")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
