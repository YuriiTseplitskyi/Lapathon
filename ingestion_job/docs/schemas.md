# Schema Documentation (v2)

This document describes the schema architecture for the Ingestion Service, stored in MongoDB collections.

> **CHANGES vs LEGACY (Jan 2026)**
> *   **Registries**: Replaced single `Test_ICS_cons` with 5 real registries: **RRP** (Property), **DRFO** (Tax), **EDR** (Business), **EIS** (Passport), **DZK** (Land).
> *   **Entities**: Added `IncomeRecord`, `OwnershipRight`, `Property`, `Document`, `Address`, `VehicleRegistration`, `Activity`, `TaxAgent`, `Identifier`.
> *   **Relationships**: Added domain-specific edges like `PAID_INCOME`, `HAS_RIGHT`, `LOCATED_AT`, `HAS_DOCUMENT`, `ISSUED`, `HAS_ADDRESS`.
> *   **Predicates**: Switched from strict header matching to `json_exists` predicates for robust detection of legacy `answer.xml` files.

---

## 1. MongoDB Collection: `register_schemas`

Defines how to parse and map raw registry responses into Canonical JSON and then into Entities.

### Shape

```json
{
  "_id": "ObjectId",
  "registry_code": "RRP",
  "name": "Registry of Real Property",
  
  "variants": [
    {
      "variant_id": "rrp_v1",
      "match_predicate": {
        "all": [
          { "type": "json_equals", "path": "$.data.array.entity", "value": "rrpExch_external" }
        ]
      },
      
      "mappings": [
        {
          "mapping_id": "prop_main",
          "scope": { "foreach": "$.data.array.resultData.result[*].realty[*]" },
          "source": { "json_path": "$.regNum" },
          "targets": [
            { "entity": "Property", "property": "reg_num", "entity_ref": "Prop" }
          ]
        },
        {
          "mapping_id": "right_node",
          "scope": { "foreach": "$.data.array.resultData.result[*].realty[*].properties[*]" },
          "source": { "json_path": "$.rnNum" },
          "targets": [
            { "entity": "OwnershipRight", "property": "rn_num", "entity_ref": "Right" }
          ]
        }
      ]
    }
  ],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

## 2. MongoDB Collection: `entity_schemas`

Defines the node labels, properties, and identity resolution rules.

### Current Entities (17)

| Entity | Description | Identity Key(s) |
| :--- | :--- | :--- |
| **Person** | Natural Person | `rnokpp` (Tax ID), `full_name` |
| **Organization** | Legal Entity (Company) | `org_code` (EDRPOU) |
| **Property** | Real Estate | `reg_num` |
| **OwnershipRight** | Right to Property | *Composite* |
| **IncomeRecord** | Tax/Income details | *Composite* |
| **Address** | Physical Address | *None* (Log-only) |
| **Document** | Passport/ID Card | `doc_number` + `doc_series` |
| **Vehicle** | Car/Vehicle | `vin` |
| **VehicleRegistration** | Vehicle Reg Event | *None* |
| **CivilEvent** | Marriage/Birth/Death | `act_number` |
| **CourtCase** | Judicial Case | *None* |
| **CourtDecision** | Judgment | *None* |
| **TaxAgent** | Org paying tax | `org_code` |
| **Activity** | NACE/KVED Code | *None* |
| **Period** | Time Period | *None* |
| **Identifier** | Generic ID | *None* |
| **Court** | Court Entity | *None* |

### Shape Example

```json
{
  "_id": "ObjectId",
  "entity_name": "Person",
  "neo4j": {
    "labels": ["Person"],
    "primary_key": "node_id",
    "constraints": []
  },
  "identity_keys": [
    { 
      "priority": 10, 
      "when": { "exists": ["rnokpp"] }, 
      "properties": ["rnokpp"] 
    },
    { 
      "priority": 20, 
      "when": { "exists": ["full_name"] }, 
      "properties": ["full_name"] 
    }
  ],
  "properties": [
    { "name": "rnokpp", "type": "string", "change_type": "rarely_changed" },
    { "name": "full_name", "type": "string", "change_type": "rarely_changed" },
    { "name": "birth_date", "type": "string", "change_type": "rarely_changed" }
  ],
  "merge_policy": {
    "default": "prefer_non_null",
    "immutable_conflict": "quarantine_and_alert"
  }
}
```

## 3. MongoDB Collection: `relationship_schemas`

Defines how entities are linked in the graph.

### Current Relationships

| Relationship | From | To | Use Case |
| :--- | :--- | :--- | :--- |
| **RIGHT_TO** | OwnershipRight | Property | Connects a right (e.g. Ownership) to the Asset |
| **HAS_RIGHT** | Person / Org | OwnershipRight | Connects the Owner to their Right |
| **PAID_INCOME** | Organization / TaxAgent | IncomeRecord | Source of income |
| **HAS_INCOME** | Person | IncomeRecord | Recipient of income |
| **LOCATED_AT** | Property | Address | Physical location |
| **HAS_ADDRESS** | Person / Org | Address | Registered address |
| **HAS_DOCUMENT** | Person | Document | Passport/ID ownership |
| **ISSUED** | Organization | Document | Issuer of ID |
| **OWNS_VEHICLE** | Person | Vehicle | Vehicle ownership |
| **HAS_REGISTRATION** | Vehicle | VehicleRegistration | Registration history |
| **IN_COURT** | CourtCase | Court | Case jurisdiction |

### Shape Example

```json
{
  "_id": "ObjectId",
  "relationship_name": "Person_HAS_RIGHT_OwnershipRight",
  "neo4j": {
    "type": "HAS_RIGHT",
    "direction": "out",
    "from_label": "Person",
    "to_label": "OwnershipRight"
  },
  "endpoints": {
    "from_entity": "Person",
    "to_entity": "OwnershipRight"
  },
  "creation_rules": [
    {
      "rule_id": "default",
      "bind": {
        "from": { "entity_ref": "Owner" },
        "to": { "entity_ref": "Right" }
      },
      "properties": [
        { "name": "role" }
      ]
    }
  ]
}
```

## 4. Ingestion & Quarantine

### `ingestion_runs`
Tracks the lifecycle of a single file execution.

### `quarantined_documents`
Stores documents that failed schema resolution or parsing.
*   **Reason**: `No matching schema variant found` (common for unknown legacy files), `json_parse_error`, etc.
*   **Debug**: Check the `extra` field for candidate scores and predicates evaluated.
