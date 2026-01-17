# Ingestion Pipeline - Complete Technical Documentation

**Last Updated:** 2026-01-16  
**Status:** Production-ready (Success Rate: 117/207 = 56.5%)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture & Data Flow](#2-architecture--data-flow)
3. [MongoDB Collections](#3-mongodb-collections)
4. [Neo4j Graph Model](#4-neo4j-graph-model)
5. [Ingestion Pipeline Details](#5-ingestion-pipeline-details)
6. [Schema System](#6-schema-system)
7. [Known Issues & Limitations](#7-known-issues--limitations)
8. [Maintenance & Operations](#8-maintenance--operations)

---

## 1. System Overview

The **Ingestion Job Service** processes raw XML/JSON documents from Ukrainian government registries, transforms them into a canonical format, applies schema mappings, and populates a Neo4j knowledge graph for fraud detection and investigative analysis.

### Key Capabilities

- **Multi-Registry Support**: 11 distinct registries (RRP, DRFO, EDR, EIS, DZK, DRACS, ERD, COURT, MVS, IDP, REQUEST)
- **Schema-Driven Mapping**: Flexible JSONPath-based extraction with predicate matching
- **Entity Resolution**: Identity-based node deduplication across documents
- **Relationship Building**: Automatic graph edge creation with global document scope
- **Error Handling**: Comprehensive quarantine system for failed documents

### Technology Stack

- **Language**: Python 3.11+
- **Dependencies**: `pymongo`, `neo4j`, `jsonpath-ng`, `pydantic`, `python-dotenv`
- **Databases**: 
  - MongoDB (schema storage, ingestion logs, quarantine)
  - Neo4j Aura (knowledge graph)

---

## 2. Architecture & Data Flow

```mermaid
graph LR
    A[Raw Files<br/>XML/JSON] --> B[Reader]
    B --> C[Canonicalizer]
    C --> D[Schema Resolver]
    D --> E[Entity Mapper]
    E --> F[Relationship Builder]
    F --> G[Neo4j Sink]
    
    D -.Schema Lookup.-> H[(MongoDB<br/>register_schemas)]
    E -.Identity Check.-> G
    
    D -.No Match.-> I[Quarantine]
    C -.Parse Error.-> I
```

### Pipeline Stages

#### 1. **File Reading** (`app/services/pipeline.py::_read_document`)
- **Input**: File path from `data/nabu_data/`
- **Output**: `RawDocument` (file_path, content_type, raw_bytes)
- **Errors**: File not found → quarantine

#### 2. **Canonicalization** (`app/services/canonical/`)
- **Adapters**: 
  - `adapter_xml.py`: Converts XML to dict (handles SOAP envelopes, nested namespaces)
  - `adapter_json.py`: Parses JSON (with fallbacks for query strings, log dumps, invalid templates)
- **Output**: `CanonicalDocument`
  ```python
  {
    "meta": {
      "registry_code": "EIS",      # Heuristic-based
      "file_extension": "xml",
      "content_type": "application/xml"
    },
    "data": {
      "Envelope": { ... },          # Normalized structure
      ...
    }
  }
  ```
- **Errors**: Invalid XML/JSON → `parse_error` → quarantine

#### 3. **Schema Resolution** (`app/services/schema/resolver.py`)
- **Backend**: MongoDB `register_schemas` collection
- **Logic**:
  1. Fetch all variants for registry (or all registries if registry_code unknown)
  2. Evaluate `match_predicate` for each variant
  3. Return variant with highest score
- **Predicates**:
  - `json_exists`: Path exists in document
  - `json_equals`: Value at path equals target
  - `json_regex`: Value matches regex pattern
  - `all / any / none`: Logical combinations
- **Errors**: No matching variant → `schema_not_found` → quarantine

#### 4. **Entity Mapping** (`app/services/pipeline.py::_map_entities`)
- **Input**: Canonical document + schema variant mappings
- **Process**:
  1. For each mapping:
     - Apply `foreach` scope (iterate arrays)
     - Extract value via JSONPath (`source.json_path`)
     - Apply transform (trim, uppercase, date normalization)
     - Create `EntityInstance` for each target
  2. Apply filters (skip items not matching predicate)
  3. Deduplicate entities by `scope_root` hash (merges properties from multiple mappings)
- **Output**: List of `EntityInstance` objects
  ```python
  EntityInstance(
    entity_name="Person",
    scope_id="hash(foreach_path + item_index)",
    properties={"rnokpp": "1234567890", "full_name": "Іванов Іван"},
    node_id=None  # Will be computed in next step
  )
  ```

#### 5. **Identity** Resolution** (`app/services/pipeline.py::_finalize_entity_id`)
- **Logic** (Priority-based):
  1. Check `identity_keys` from `entity_schemas` collection
  2. If keys exist in properties: `node_id = hash(entity_name + key_values)`
  3. Else: `node_id = f"DOCSCOPED:{document_id}:{scope_id}"`
- **Example**:
  - `Person` with `rnokpp="1234567890"` → `node_id = "Person:hash(1234567890)"`
  - `Address` with no identity keys → `node_id = "DOCSCOPED:abc123:addr_1"`

#### 6. **Relationship Building** (`app/services/pipeline.py::_build_relationships`)
- **Strategy**: **Global Document Scope**
- **Logic**:
  1. Group entities by `entity_name`
  2. For each relationship schema:
     - Find all `from_entity` instances with matching `entity_ref`
     - Find all `to_entity` instances with matching `entity_ref`
     - Create Cartesian product (all-to-all within document)
- **Example**:
  ```
  Document has: [Person:Owner, OwnershipRight:Right, Property:Prop]
  Relationship: Person(Owner) -> HAS_RIGHT -> OwnershipRight(Right)
  Result: 1 relationship created
  ```

#### 7. **Neo4j Sink** (`app/services/graph/neo4j_sink.py`)
- **Strategy**: Batch MERGE operations
- **Node Creation**:
  ```cypher
  MERGE (n:Person {id: $node_id})
  ON CREATE SET n = $properties, n.created_at = timestamp()
  ON MATCH SET n += $properties, n.updated_at = timestamp()
  ```
- **Relationship Creation**:
  ```cypher
  MATCH (from {id: $from_id}), (to {id: $to_id})
  MERGE (from)-[r:RELATIONSHIP_TYPE]->(to)
  SET r = $properties
  ```

---

## 3. MongoDB Collections

### 3.1 `register_schemas`

Defines how to parse and map registry responses.

**Structure**:
```javascript
{
  "_id": ObjectId,
  "registry_code": "EIS",
  "name": "Electronic Information System",
  "schema_match": {
    "canonical_header_fields": {}  // Unused (legacy)
  },
  "variants": [
    {
      "variant_id": "eis_v1",
      "match_predicate": {
        "all": [
          {"type": "json_exists", "path": "$.data.Envelope.Body.SubjectDetailData"}
        ]
      },
      "mappings": [
        {
          "mapping_id": "eis_person",
          "scope": {"foreach": "$.data.Envelope.Body.SubjectDetailData.SubjectDetails[*]"},
          "source": {"json_path": "$.RNOKPP"},
          "filter": null,  // Optional: predicate to skip items
          "targets": [
            {
              "entity": "Person",
              "property": "rnokpp",
              "entity_ref": "Subject",
              "transform": {"type": "trim"}
            }
          ]
        }
      ]
    }
  ],
  "created_at": ISODate,
  "updated_at": ISODate
}
```

**Key Fields**:
- **`match_predicate`**: Determines if a document matches this variant
- **`mappings`**: List of extraction rules
  - **`scope.foreach`**: JSONPath for iteration (optional)
  - **`source.json_path`**: Extract value from item
  - **`filter`**: Predicate to skip items (e.g., filter vehicles vs real estate)
  - **`targets`**: One-to-many mapping to entity properties
  - **`entity_ref`**: Logical name for relationship binding

**Current Registries** (11):
| Code | Name | Variants |
|------|------|----------|
| RRP | Registry of Real Property | 2 |
| DRFO | State Register of Natural Persons (Tax) | 1 |
| EDR | Unified State Register of Enterprises | 1 |
| EIS | Electronic Information System | 1 |
| DZK | State Land Cadastre | 1 |
| DRACS | Civil Status Registry | 1 |
| ERD | Power of Attorney Registry | 2 |
| COURT | Court Decisions | 1 |
| MVS | Ministry of Internal Affairs (Vehicles) | 1 |
| IDP | Internally Displaced Persons | 1 |
| REQUEST | Traceability Requests | 10 |

### 3.2 `entity_schemas`

Defines node labels, properties, and identity resolution.

**Structure**:
```javascript
{
  "_id": ObjectId,
  "entity_name": "Person",
  "neo4j": {
    "labels": ["Person"],
    "primary_key": "node_id",
    "constraints": []
  },
  "identity_keys": [
    {
      "priority": 10,
      "when": {"exists": ["rnokpp"]},
      "properties": ["rnokpp"]
    },
    {
      "priority": 20,
      "when": {"exists": ["full_name", "birth_date"]},
      "properties": ["full_name", "birth_date"]
    }
  ],
  "properties": [
    {"name": "rnokpp", "type": "string", "change_type": "rarely_changed"},
    {"name": "full_name", "type": "string", "change_type": "rarely_changed"},
    {"name": "birth_date", "type": "string", "change_type": "rarely_changed"}
  ],
  "merge_policy": {
    "default": "prefer_non_null",
    "immutable_conflict": "quarantine_and_alert"
  }
}
```

**Current Entities** (20):
- **Person**, **Organization**, **Property**, **RealEstateProperty**, **Vehicle**
- **Document**, **IncomeRecord**, **OwnershipRight**, **Address**
- **CivilEvent**, **CourtCase**, **CourtDecision**, **Court**
- **VehicleRegistration**, **TaxAgent**, **Activity**, **Period**, **Identifier**
- **Request**, **DisplacedPerson**

### 3.3 `relationship_schemas`

Defines graph edges.

**Structure**:
```javascript
{
  "_id": ObjectId,
  "relationship_name": "Person_HAS_INCOME_IncomeRecord",
  "neo4j": {
    "type": "HAS_INCOME",
    "direction": "out",
    "from_label": "Person",
    "to_label": "IncomeRecord"
  },
  "endpoints": {
    "from_entity": "Person",
    "to_entity": "IncomeRecord"
  },
  "creation_rules": [
    {
      "rule_id": "default",
      "bind": {
        "from": {"entity_ref": "Subject"},
        "to": {"entity_ref": "Income"}
      },
      "properties": []
    }
  ]
}
```

**Current Relationships** (15):
- **HAS_RIGHT**, **RIGHT_TO**, **LOCATED_AT**, **HAS_ADDRESS**
- **HAS_INCOME**, **PAID_INCOME**, **HAS_DOCUMENT**, **ISSUED**
- **OWNS_VEHICLE**, **HAS_REGISTRATION**, **HAS_CIVIL_EVENT**
- **IN_COURT**, **REGISTERED_TO**, **INVOLVES**, **SEARCHED**

### 3.4 `ingested_documents`

Tracks successful ingestion.

**Fields**:
- `document_id`: UUID
- `raw.file_path`, `raw.content_type`, `raw.raw_hash`
- `canonical.canonical_hash`, `canonical.meta`, `canonical.data` (truncated)
- `schema.registry_code`, `schema.variant_id`
- `metadata.ingestion_run_id`, `metadata.ingested_at`

### 3.5 `quarantined_documents`

Stores failed documents.

**Fields**:
- `document_id`: UUID
- `file_path`, `reason` (`schema_not_found`, `parse_error`)
- `error_message`, `extra` (debug info: candidate scores, predicates)
- `quarantined_at`

### 3.6 `ingestion_logs`

Step-by-step trace for debugging.

**Fields**:
- `document_id`, `step` (`read_document`, `canonicalize`, `resolve_schema`, `map_entities`)
- `status` (`success`, `error`), `message`, `details`, `created_at`

### 3.7 `ingestion_runs`

Metadata for batch runs.

**Fields**:
- `run_id`, `started_at`, `finished_at`, `total_files`, `success_count`, `fail_count`

---

## 4. Neo4j Graph Model

### Node Labels (20)

**Primary Entities**:
```cypher
(:Person {
  id, rnokpp, full_name, birth_date,
  last_name, first_name, middle_name,
  source_doc_id, created_at, updated_at
})

(:Organization {
  id, org_code, name, short_name, org_type,
  source_doc_id, created_at, updated_at
})

(:RealEstateProperty {
  id, reg_num, cad_num, area, area_unit, re_type,
  description, address_text,
  source_doc_id, created_at, updated_at
})

(:Vehicle {
  id, vin, registration_number, make, model, year, color,
  vehicle_type, description,
  source_doc_id, created_at, updated_at
})
```

**Supporting Entities**:
```cypher
(:Document {
  id, doc_number, doc_series, doc_type, doc_issue_date, doc_issuer,
  source_doc_id, created_at, updated_at
})

(:IncomeRecord {
  id, income_accrued, income_paid, tax_charged, tax_transferred,
  sign_of_income_privilege, period_quarter_month, period_year,
  source_doc_id, created_at, updated_at
})

(:OwnershipRight {
  id, rn_num, form_of_ownership, subject_code, subject_name,
  source_doc_id, created_at, updated_at
})

(:CourtDecision {
  id, decision_type, adjudication_date, case_number, reg_num,
  content_snippet,
  source_doc_id, created_at, updated_at
})

(:Request {
  id, request_id, service_code,
  source_doc_id, created_at, updated_at
})
```

### Relationship Types (15)

**Ownership & Rights**:
```cypher
(:Person)-[:HAS_RIGHT {role}]->(:OwnershipRight)
(:OwnershipRight)-[:RIGHT_TO]->(:RealEstateProperty)
(:Person)-[:OWNS_VEHICLE]->(:Vehicle)
```

**Income & Tax**:
```cypher
(:Person)-[:HAS_INCOME]->(:IncomeRecord)
(:Organization)-[:PAID_INCOME]->(:IncomeRecord)
```

**Location**:
```cypher
(:RealEstateProperty)-[:LOCATED_AT]->(:Address)
(:Person)-[:HAS_ADDRESS]->(:Address)
```

**Identity**:
```cypher
(:Person)-[:HAS_DOCUMENT]->(:Document)
(:Organization)-[:ISSUED]->(:Document)
```

**Legal**:
```cypher
(:CourtCase)-[:IN_COURT]->(:Court)
(:CourtDecision)-[:INVOLVES {role}]->(:Person)
```

**Traceability**:
```cypher
(:Request)-[:SEARCHED]->(:Person)
```

---

## 5. Ingestion Pipeline Details

### 5.1 Canonicalization Logic

#### XML Adapter (`adapter_xml.py`)

**Challenges**:
- Namespaces (SOAP, X-Road)
- Nested arrays vs single items
- Attributes vs elements

**Solution**:
```python
def _parse_element(elem, nsmap):
    # Strip namespace prefixes
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    
    # Handle attributes
    result = {f"@{k.split('}')[-1]}": v for k, v in elem.attrib.items()}
    
    # Handle children
    children = list(elem)
    if not children:
        # Leaf node
        result["#text"] = elem.text
    else:
        # Group by tag
        for child_tag, group in groupby(children, key=lambda e: e.tag):
            child_tag_clean = child_tag.split('}')[-1]
            items = [_parse_element(c, nsmap) for c in group]
            result[child_tag_clean] = items if len(items) > 1 else items[0]
    
    return result
```

**Example**:
```xml
<Envelope xmlns:soap="...">
  <Body>
    <Person><RNOKPP>1234</RNOKPP></Person>
  </Body>
</Envelope>
```
→
```json
{
  "Envelope": {
    "Body": {
      "Person": {
        "RNOKPP": {"#text": "1234"}
      }
    }
  }
}
```

#### JSON Adapter (`adapter_json.py`)

**Fallback Parsing** (for non-standard formats):

1. **Query String** (e.g., `date_search=...&rnokpp=...`):
   ```python
   from urllib.parse import parse_qs
   qs = parse_qs(raw_str, keep_blank_values=True)
   data = {"data": {k: v[0] if len(v) == 1 else v for k, v in qs.items()}}
   meta["registry_code"] = "REQUEST_QS"
   ```

2. **Log Dump** (e.g., `HEADER_Uxp-Service=...`):
   ```python
   log_data = {}
   for line in raw_str.splitlines():
       if "=" in line:
           k, v = line.split("=", 1)
           log_data[k.strip()] = v.strip()
   data = {"data": log_data}
   meta["registry_code"] = "REQUEST_DZK"
   ```

3. **Invalid JSON with Templates** (e.g., `"value": ${variable}`):
   ```python
   import re
   match = re.search(r'"value1":\s*"([^"]+)"(?:(?!}).)*"name":\s*"Fioukr"', raw_str, re.DOTALL)
   if match:
       data = {"data": {"fioukr": match.group(1)}}
       meta["registry_code"] = "REQUEST_ARKAN"
   ```

### 5.2 Schema Matching Algorithm

**File**: `app/services/schema/resolver.py`

```python
def resolve_variant(canonical_doc, schema_backend):
    candidates = []
    
    # Get all registries (or filter by registry_code if known)
    registries = schema_backend.get_all_registers()
    
    for registry in registries:
        for variant in registry["variants"]:
            score = _evaluate_predicate(canonical_doc, variant["match_predicate"])
            if score > 0:
                candidates.append((score, registry["registry_code"], variant))
    
    if not candidates:
        return None
    
    # Return highest scoring variant
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][2]

def _evaluate_predicate(doc, predicate):
    # Compound predicates
    if "all" in predicate:
        scores = [_eval_single(doc, p) for p in predicate["all"]]
        return sum(scores) if all(s > 0 for s in scores) else 0
    
    if "any" in predicate:
        scores = [_eval_single(doc, p) for p in predicate["any"]]
        return max(scores)
    
    if "none" in predicate:
        scores = [_eval_single(doc, p) for p in predicate["none"]]
        return 1 if all(s == 0 for s in scores) else 0
    
    return _eval_single(doc, predicate)

def _eval_single(doc, pred):
    path = pred["path"]
    matches = jp_first(doc, path)  # JSONPath lookup
    
    if pred["type"] == "json_exists":
        return 1 if matches else 0
    
    if pred["type"] == "json_equals":
        return 1 if matches == pred["value"] else 0
    
    if pred["type"] == "json_regex":
        import re
        return 1 if matches and re.match(pred["pattern"], str(matches)) else 0
    
    return 0
```

### 5.3 Entity Extraction Process

**Scope Handling**:

```python
def _map_entities(canonical_doc, variant):
    instances = []
    
    for mapping in variant["mappings"]:
        scope_def = mapping.get("scope", {})
        
        if "foreach" in scope_def:
            # Iteration mode
            items = jp_find_all(canonical_doc, scope_def["foreach"])
            for idx, item in enumerate(items):
                # Apply filter
                if mapping.get("filter") and not _eval_predicate(item, mapping["filter"]):
                    continue
                
                # Extract value
                value = jp_first(item, mapping["source"]["json_path"])
                
                # Apply transform
                if mapping.get("transform"):
                    value = _apply_transform(value, mapping["transform"])
                
                # Create instances for each target
                for target in mapping["targets"]:
                    inst = EntityInstance(
                        entity_name=target["entity"],
                        scope_id=f"{mapping['mapping_id']}:{idx}",
                        scope_root=hash(scope_def["foreach"] + str(idx)),  # Dedup key
                        properties={target["property"]: value},
                        entity_ref=target.get("entity_ref")
                    )
                    instances.append(inst)
        else:
            # Single-item mode (no foreach)
            value = jp_first(canonical_doc, mapping["source"]["json_path"])
            # ... (same logic)
    
    # Deduplicate by scope_root
    merged = {}
    for inst in instances:
        key = (inst.entity_name, inst.scope_root)
        if key in merged:
            merged[key].properties.update(inst.properties)  # Merge properties
        else:
            merged[key] = inst
    
    return list(merged.values())
```

**Transform Types**:
```python
def _apply_transform(value, transform):
    if transform["type"] == "trim":
        return value.strip() if value else value
    
    if transform["type"] == "uppercase":
        return value.upper() if value else value
    
    if transform["type"] == "date_normalize":
        # Convert various date formats to ISO (YYYY-MM-DD)
        return normalize_date(value)
    
    # Add more as needed
    return value
```

### 5.4 Relationship Building Strategy

**Global Document Scope**:

```python
def _build_relationships(entities, rel_schemas, doc_id):
    relationships = []
    
    # Group entities by name and ref
    entity_groups = {}
    for ent in entities:
        key = (ent.entity_name, ent.entity_ref)
        entity_groups.setdefault(key, []).append(ent)
    
    for rel_schema in rel_schemas:
        for rule in rel_schema["creation_rules"]:
            # Find matching "from" entities
            from_key = (rel_schema["endpoints"]["from_entity"], 
                        rule["bind"]["from"]["entity_ref"])
            from_entities = entity_groups.get(from_key, [])
            
            # Find matching "to" entities
            to_key = (rel_schema["endpoints"]["to_entity"], 
                      rule["bind"]["to"]["entity_ref"])
            to_entities = entity_groups.get(to_key, [])
            
            # Create all-to-all relationships
            for from_ent in from_entities:
                for to_ent in to_entities:
                    rel = RelationshipInstance(
                        relationship_name=rel_schema["relationship_name"],
                        from_node_id=from_ent.node_id,
                        to_node_id=to_ent.node_id,
                        properties={}  # Extract from rule if needed
                    )
                    relationships.append(rel)
    
    return relationships
```

**Example**:
```
Document: DRFO Answer (Income)
Entities:
  - Person(Subject): rnokpp="1234567890"
  - IncomeRecord(Income): income_accrued="5000"
  - IncomeRecord(Income): income_accrued="3000"
  - Organization(TaxAgent): org_code="9876"

Relationships Created:
  - Person(1234567890) -[HAS_INCOME]-> IncomeRecord(5000)
  - Person(1234567890) -[HAS_INCOME]-> IncomeRecord(3000)
  - Organization(9876) -[PAID_INCOME]-> IncomeRecord(5000)
  - Organization(9876) -[PAID_INCOME]-> IncomeRecord(3000)
```

---

## 6. Schema System

### 6.1 Current Schema Coverage

**By Registry** (Success Rates):
- **DRFO** (Tax): ~95% (1 variant)
- **EIS** (Passport): ~100% (1 variant, handles Person/Document split)
- **ERD** (Power of Attorney): ~85% (2 variants: Answer + Vehicle/RealEstate filtering)
- **COURT** (Decisions): ~90% (1 variant, JSON-in-XML handled)
- **RRP** (Property): ~80% (2 variants)
- **MVS** (Vehicles): ~70% (1 variant)
- **REQUEST** (Traceability): **10 variants** covering:
  - DRACS (Marriage/Divorce)
  - DRFO (Tax queries)
  - DZK (Land)
  - ERD (Grantor lookup)
  - RRP (Property search)
  - SR (Successions/Inheritance)
  - Arkan (Border crossings)
  - Query String
  - Generic JSON
  - Generic XML

### 6.2 Schema Design Patterns

**Pattern 1: Simple Entity Extraction**
```javascript
{
  "mapping_id": "person_basic",
  "scope": {"foreach": "$.data.Persons[*]"},
  "source": {"json_path": "$.RNOKPP"},
  "targets": [
    {"entity": "Person", "property": "rnokpp", "entity_ref": "Subject"}
  ]
}
```

**Pattern 2: Multi-Property Mapping**
```javascript
// Multiple mappings with same scope_root merge into one entity
[
  {
    "mapping_id": "person_rnokpp",
    "scope": {"foreach": "$.data.Persons[*]"},
    "source": {"json_path": "$.RNOKPP"},
    "targets": [{"entity": "Person", "property": "rnokpp", "entity_ref": "Subject"}]
  },
  {
    "mapping_id": "person_name",
    "scope": {"foreach": "$.data.Persons[*]"},  // Same scope
    "source": {"json_path": "$.FullName"},
    "targets": [{"entity": "Person", "property": "full_name", "entity_ref": "Subject"}]
  }
]
// Result: Person with {rnokpp: "123", full_name: "Іванов"}
```

**Pattern 3: Filtered Iteration**
```javascript
{
  "mapping_id": "vehicle_only",
  "scope": {"foreach": "$.data.Properties[*]"},
  "source": {"json_path": "$.Description"},
  "filter": {
    "none": [
      {"type": "json_regex", "path": "$.Description", "pattern": "(будинок|квартир|примі|земел|гараж)"}
    ]
  },
  "targets": [
    {"entity": "Vehicle", "property": "description", "entity_ref": "Asset"}
  ]
}
```

**Pattern 4: Nested Iteration**
```javascript
// Parent scope
{
  "mapping_id": "property",
  "scope": {"foreach": "$.data.Realty[*]"},
  "source": {"json_path": "$.RegNum"},
  "targets": [{"entity": "RealEstateProperty", "property": "reg_num", "entity_ref": "Prop"}]
}
// Child scope (nested array)
{
  "mapping_id": "ownership_right",
  "scope": {"foreach": "$.data.Realty[*].Properties[*]"},
  "source": {"json_path": "$.RnNum"},
  "targets": [{"entity": "OwnershipRight", "property": "rn_num", "entity_ref": "Right"}]
}
```

### 6.3 Adding a New Registry

**Steps**:

1. **Analyze Sample Data**:
   ```bash
   cat data/nabu_data/path/to/sample.xml | head -n 50
   ```

2. **Define Entities** (if new):
   ```python
   # In scripts/init_schemas.py
   entity_schemas.append({
       "entity_name": "MyNewEntity",
       "neo4j": {"labels": ["MyNewEntity"], "primary_key": "node_id"},
       "identity_keys": [
           {"priority": 10, "when": {"exists": ["unique_id"]}, "properties": ["unique_id"]}
       ],
       "properties": [
           {"name": "unique_id", "type": "string"},
           {"name": "name", "type": "string"}
       ],
       "merge_policy": {"default": "prefer_non_null"}
   })
   ```

3. **Define Mappings**:
   ```python
   my_mappings = []
   my_mappings.append(m(
       "my_entity", 
       "$.data.Items[*]", 
       "$.Id", 
       "MyNewEntity", 
       "unique_id", 
       "Item"
   ))
   ```

4. **Create Variant**:
   ```python
   my_variants = [{
       "variant_id": "my_registry_v1",
       "match_predicate": {
           "all": [
               {"type": "json_exists", "path": "$.data.MyRootElement"}
           ]
       },
       "mappings": my_mappings
   }]
   ```

5. **Register**:
   ```python
   registers.append({
       "code": "MYNEW",
       "name": "My New Registry",
       "variants": my_variants
   })
   ```

6. **Deploy**:
   ```bash
   uv run python3 scripts/reset_db.py
   uv run python3 scripts/init_schemas.py
   uv run python3 scripts/run_batch.py
   ```

---

## 7. Known Issues & Limitations

### 7.1 Persistent Issues

**1. Answer File Quarantine (77 files)**
- **Problem**: No schemas defined for response files (e.g., DRFO income data answers)
- **Impact**: ~37% of total files quarantined
- **Mitigation**: Answer files are secondary to request traceability; can be added later
- **Solution**: Define answer variants for high-value registries

**2. Request Variant Coverage (13 files)**
- **Problem**: Unknown request formats not yet analyzed
- **Impact**: ~6% of requests quarantined
- **Next Step**: Inspect samples with `scripts/debug.py --file <path>`

**3. Photo Decoding Errors (3 files)**
- **Problem**: Invalid base64 padding in EIS `photo_base64` field
- **Impact**: Logged warnings, does not block ingestion
- **Solution**: Add error handling in photo processing

### 7.2 Architectural Limitations

**1. Global Document Scope (Over-linking)**
- **Issue**: Creates Cartesian product of all matching entities
- **Example**: If a doc has 2 Persons and 2 IncomeRecords, creates 4 relationships (instead of intended 2)
- **When to fix**: If documents contain multiple unrelated entity trees
- **Solution**: Implement hierarchical scoping (parent-child tracking)

**2. DOCSCOPED ID Proliferation**
- **Issue**: Entities without identity keys get document-scoped IDs (no deduplication across docs)
- **Impact**: `Address` nodes duplicated (same address in multiple docs = multiple nodes)
- **Solution**: Add identity keys for `Address` (e.g., `koatuu + address_text`)

**3. Hardcoded Schema Logic**
- **Issue**: `init_schemas.py` is 1000+ lines of Python code
- **Maintenance**: Difficult to review changes, error-prone
- **Solution**: Migrate to YAML/JSON config files with validation

---

## 8. Maintenance & Operations

### 8.1 Essential Scripts

**Production**:
- `scripts/reset_db.py`: Wipe all data (MongoDB + Neo4j)
- `scripts/init_schemas.py`: Deploy schema definitions
- `scripts/run_batch.py`: Execute batch ingestion
- `scripts/debug.py`: Single-file debug tool (consolidated)
- `scripts/verify.py`: Validation suite (consolidated)

**Legacy/Obsolete** (to be removed):
- All `debug_*.py` except `debug_ingest_single.py`
- All `check_*.py` except essential verifications
- All `analyze_*.py` (one-off investigations)
- `test_*.py` (unit tests should be in `tests/`)

### 8.2 Monitoring

**Quarantine Rate**: Target < 10%
```bash
uv run python3 scripts/verify.py --quarantine
```

**Relationship Integrity**: Check required links exist
```bash
uv run python3 scripts/verify.py --relationships
```

**Entity Deduplication**: Monitor DOCSCOPED ratio
```bash
uv run python3 scripts/verify.py --identity
```

### 8.3 Troubleshooting

**Symptom**: High quarantine rate after schema change
```bash
# 1. Check logs for specific files
uv run python3 scripts/debug.py --file "path/to/failed.xml"

# 2. Verify predicate matching
uv run python3 scripts/debug.py --test-predicate

# 3. Inspect canonical output
uv run python3 scripts/debug.py --canonicalize "path/to/file.xml"
```

**Symptom**: Missing relationships
```bash
# Check relationship creation logs
uv run python3 scripts/verify.py --relationships --verbose
```

**Symptom**: Duplicate nodes
```bash
# Analyze identity key coverage
uv run python3 scripts/verify.py --identity --entity Person
```

---

## Appendix A: Environment Variables

```bash
# MongoDB
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=lapathon-nprd

# Neo4j Aura
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=xxxxx

# Data Path
data_dir=/Users/maksymkyrychenko/Personal/NABU/Lapathon/data/nabu_data
```

---

## Appendix B: Performance Metrics

**Current Baseline** (207 files):
- **Ingestion Time**: ~2-3 minutes (serial processing)
- **Throughput**: ~1.2 files/second
- **Memory Usage**: ~200MB peak
- **MongoDB Size**: ~15MB (schemas + logs)
- **Neo4j Size**: ~500 nodes, ~700 relationships

**Scaling Projections**:
- **10K files**: ~2.3 hours (parallel processing recommended)
- **100K files**: Requires distributed workers + chunking

---

**End of Documentation**
