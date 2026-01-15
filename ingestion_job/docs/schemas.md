MongoDB collection: register_schemas
shape:
{
  "_id": "ObjectId",
  "registry_code": "Test_ICS_cons",
  "service_code": "3_MJU_DRACS_prod",
  "method_code": "GetBirthArByChildNameAndBirthDate",

  "source": {
    "raw_formats": ["soap_xml"],
    "canonical_format": "canonical_json_v1"
  },

  "status": "active|draft|deprecated",
  "version": 3,

  "schema_match": {
    "canonical_header_fields": {
      "registry_code": "$.meta.registry_code",
      "service_code": "$.meta.service_code",
      "method_code": "$.meta.method_code"
    }
  },

  "variants": [
    {
      "variant_id": "v3_main",
      "priority": 100,

    "match_predicate": {
        "all": [
          { "type": "json_exists", "path": "$.document.birthAct" },
          { "type": "json_equals", "path": "$.meta.result_code", "value": "1" }
        ],
        "none": [
          { "type": "json_exists", "path": "$.meta.error" }
        ]
      },

    "mappings": [
        {
          "mapping_id": "birthact_actnumber",
          "scope": { "foreach": "$.document.birthAct[*]" },
          "source": { "json_path": "$.actNumber" },

    "targets": [
            { "entity": "BirthAct", "property": "actNumber" },
            {
              "entity": "Person",
              "property": "birthActNumber",
              "entity_ref": "ChildPerson"
            }
          ],

    "required": false,
          "on_missing": "skip"
        }
      ],

    "emits": {
        "entities": ["Person", "BirthAct", "RegistryService"],
        "relationships": ["PERSON_HAS_CIVIL_EVENT"]
      }
    }
  ],

  "entity_schema_refs": ["Person", "BirthAct", "RegistryService"],
  "relationship_schema_refs": ["PERSON_HAS_CIVIL_EVENT"],

  "created_at": "ISODate",
  "updated_at": "ISODate"
}


MongoDB collection: entity_schemas
shape:
{
  "_id": "ObjectId",
  "entity_name": "Person",
  "neo4j": {
    "labels": ["Person"],
    "primary_key": "person_id",
    "constraints": [
      { "type": "unique", "property": "person_id" },
      { "type": "index", "property": "rnokpp" }
    ]
  },

  "identity_keys": [
    { "priority": 1, "when": { "exists": ["rnokpp"] }, "properties": ["rnokpp"] },
    { "priority": 2, "when": { "exists": ["unzr"] }, "properties": ["unzr"] },
    { "priority": 3, "when": { "exists": ["docType", "docSeries", "docNumber"] }, "properties": ["docType", "docSeries", "docNumber"] }
  ],

  "properties": [
    { "name": "rnokpp", "type": "string", "is_required": false, "change_type": "immutable", "normalize": ["trim"] },
    { "name": "fullName", "type": "string", "is_required": false, "change_type": "rarely_changed", "normalize": ["trim", "collapse_spaces"] },
    { "name": "firstName", "type": "string", "is_required": false, "change_type": "rarely_changed" },
    { "name": "lastName", "type": "string", "is_required": false, "change_type": "rarely_changed" },
    { "name": "birthDate", "type": "date", "is_required": false, "change_type": "immutable" }
  ],

  "merge_policy": {
    "default": "prefer_non_null",
    "immutable_conflict": "quarantine_and_alert",
    "rarely_changed_conflict": "log_warning_and_keep_existing",
    "dynamic_conflict": "take_latest_by_source_timestamp"
  },

  "source_priority": [
    { "registry_code": "Test_ICS_cons", "weight": 10 }
  ],

  "version": 1,
  "status": "active|draft|deprecated",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}



MongoDB collection: relationship_schemas
shape:
{
  "_id": "ObjectId",
  "relationship_name": "PERSON_HAS_VEHICLE",
  "neo4j": {
    "type": "HAS_VEHICLE",
    "direction": "out",
    "from_label": "Person",
    "to_label": "Vehicle"
  },

  "endpoints": {
    "from_entity": "Person",
    "to_entity": "Vehicle"
  },

  "creation_rules": [
    {
      "rule_id": "link_by_doc_context",
      "when": { "all": [
        { "type": "entity_exists", "entity_ref": "GrantorPerson" },
        { "type": "entity_exists", "entity_ref": "VehicleFromPropertiesBlock" }
      ]},

    "bind": {
        "from": { "entity_ref": "GrantorPerson" },
        "to": { "entity_ref": "VehicleFromPropertiesBlock" }
      },

    "properties": [
        { "name": "sourceDocumentId", "value_from": { "context": "document_id" } },
        { "name": "confidence", "value": 0.8 }
      ]
    }
  ],

  "uniqueness": {
    "strategy": "unique_per_endpoints_and_type",
    "keys": ["from.person_id", "to.vehicle_id", "neo4j.type"]
  },

  "merge_policy": {
    "on_existing": "merge_properties_prefer_non_null"
  },

  "version": 1,
  "status": "active|draft|deprecated",
  "created_at": "ISODate",
  "updated_at": "ISODate"
}



MongoDB collection: ingestion_runs
shape:
{
  "_id": "ObjectId",
  "run_id": "uuid",
  "trigger": "file_drop|manual_replay|scheduler",

  "started_at": "ISODate",
  "finished_at": "ISODate",
  "status": "running|success|warning|failed|quarantined",

  "input": {
    "document_id": "uuid",

    "raw": {
      "file_path": "data/A/V/a.xml",
      "content_type": "text/xml",
      "content_hash": "sha256:..."
    },

    "canonical": {
      "format": "canonical_json_v1",
      "document_ref": "ObjectId",
      "hash": "sha256:..."
    }
  },

  "schema_resolution": {
    "registry_code": "Test_ICS_cons",
    "service_code": "4_KCS_ERD_demo",
    "method_code": "getProxyGrantorNameOrIDN",
    "register_schema_id": "ObjectId",
    "variant_id": "v3_main"
  },

  "metrics": {
    "entities_extracted": 12,
    "entities_upserted": 12,
    "relationships_created": 9,
    "immutable_conflicts": 0
  },

  "next_action": "none|define_schema|fix_variant|investigate_merge"
}



MongoDB collection: ingested_documents
shape:
{
  "_id": "ObjectId",
  "document_id": "uuid",

  "raw": {
    "file_path": "data/A/V/a.xml",
    "source_system": "drive|s3|fs",
    "content_type": "text/xml",
    "encoding": "utf-8",
    "content_hash": "sha256:..."
  },

  "canonical": {
    "format": "canonical_json_v1",
    "document_ref": "ObjectId",
    "hash": "sha256:..."
  },

  "discovered_at": "ISODate",

  "classification": {
    "registry_code": "Test_ICS_cons",
    "service_code": "4_KCS_ERD_demo",
    "method_code": "getProxyGrantorNameOrIDN"
  },

  "schema_ref": {
    "register_schema_id": "ObjectId",
    "variant_id": "v3"
  },

  "parse_status": "ok|parse_error|corrupt|unsupported",
  "ingestion_status": "pending|processed|quarantined|failed|skipped",

  "failure": {
    "category": "schema_not_found|variant_ambiguous|access_denied|immutable_conflict",
    "message": "string",
    "details": {}
  },

  "neo4j_write_summary": {
    "nodes_created": 0,
    "nodes_updated": 0,
    "rels_created": 0,
    "rels_updated": 0
  },

  "run_id": "uuid",
  "last_updated_at": "ISODate"
}



MongoDB collection: ingestion_logs
shape:
{
  "_id": "ObjectId",
  "run_id": "uuid",
  "document_id": "uuid",
  "ts": "ISODate",

  "step": "schema_lookup",
  "stage": "start|end",
  "status": "success|warning|error|skipped",

  "message": "Selected register schema ...",
  "details": {
    "registry_code": "Test_ICS_cons",
    "service_code": "3_MJU_DRACS_prod",
    "candidates": [
      { "schema_id": "ObjectId", "variant_id": "v3_main", "score": 0.97 }
    ]
  },

  "lineage": {
    "input_ref": { "file_path": "...", "content_hash": "sha256:..." },
    "output_ref": { "neo4j_tx_id": "optional", "entity_count": 12 }
  },

  "next_action": {
    "type": "none|notify_dev|open_ticket|quarantine_document|add_schema_variant",
    "severity": "info|low|medium|high|critical",
    "suggested_owner": "data_eng|backend|ml",
    "suggested_text": "Variant ambiguous: 2 variants matched..."
  }
}


MongoDB collection: quarantined_documents
shape:
{
  "document_id": "uuid",
  "content_hash": "sha256:...",
  "reason": "variant_ambiguous",
  "excerpt": "`<BirthAct>`...`</BirthAct>`",
  "created_at": "ISODate",
  "status": "open|resolved|ignored",
  "owner": "data_eng"
}

MongoDB collection: schema_change_requests
shape:
{
  "request_id": "uuid",
  "registry_code": "Test_ICS_cons",
  "service_code": "4_KCS_ERD_demo",
  "method_code": "getProxyGrantorNameOrIDN",
  "proposed_changes": { "add_variant": { "...": "..." } },
  "evidence": { "documents": ["uuid1", "uuid2"] },
  "status": "proposed|approved|rejected|merged",
  "created_at": "ISODate"
}
