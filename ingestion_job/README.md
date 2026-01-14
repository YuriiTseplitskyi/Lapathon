### **Step 1 — Read Documents**

* Input: Raw files from drive / S3 / FS.
* Action:
  1. Read raw document.
  2. Store raw metadata (`file_path`, `content_type`, `encoding`, `content_hash`) in `ingested_documents.raw`.
* Output: `raw_document` object.

---

### **Step 2 — Convert to Canonical JSON**

* Input: `raw_document`.
* Action:
  1. Convert raw document (XML/CSV/JSON) → Canonical JSON.
  2. Preserve **RAW** layer for audit.
  3. Compute `canonical_hash`.
* Output: `canonical_document` object.
* Logging: Write start/end events to `ingestion_logs`.

---

### **Step 3 — Resolve Registry Schema**

* Input: `canonical_document`.
* Action:
  1. Query `register_schemas` in MongoDB.
  2. Use **`canonical_header_fields`** (`$.meta.registry_code`, etc.) to select candidate schema variants.
  3. Evaluate `match_predicate` on canonical JSON.
* Output:
  * Selected variant → used for mapping.
  * Ambiguities → log in `quarantined_documents`.
* Logging: Record candidate scores and selection in `ingestion_logs`.

---

### **Step 4 — Variant Selection**

* Input: Schema variants for canonical document.
* Action:
  1. Check `match_predicate` against document.
  2. If **one variant matches** → select.
  3. If **multiple variants match and they are incompatible** → fallback to quarantine, log error, notify developers.
  4. If **no variants match** → fallback to quarantine.
* Output: `selected_variant` or `quarantined_document`.
* Logging: `ingestion_logs` with severity and next_action.

---

### **Step 5 — Map to Entities**

* Input: `canonical_document + selected_variant`.
* Action:
  1. For each `mappings` entry in variant:
     * Apply `json_path` extraction.
     * Transform data (`trim`, `collapse_spaces`).
     * Map to target entities (`entity`, `property`, `entity_ref`).
  2. Merge entity with Neo4j:
     * If entity exists → apply merge policy (`immutable`, `rarely_changed`, `dynamic`).
     * If merge fails → fallback to quarantine + notify devs.
     * If entity new → insert into Neo4j.
* Output: Neo4j nodes.
* Logging: Metrics (`entities_extracted`, `entities_upserted`) in `ingestion_logs`.

---

### **Step 6 — Resolve Relationships**

* Input: Neo4j entities.
* Action:
  1. Read `relationship_schemas`.
  2. Apply `creation_rules` for each relationship:
     * Check `when` conditions.
     * Bind entities.
     * Set relationship properties.
  3. Ensure uniqueness (`keys`) and merge policy.
* Output: Neo4j relationships.
* Logging: Record `rels_created`/`rels_updated` in `ingestion_logs`.

---

### **Step 7 — Write Result Metrics**

* Input: Processed document + entities + relationships.
* Action:
  1. Update `ingested_documents`:
     * `parse_status`
     * `ingestion_status`
     * `failure` info if applicable
     * `neo4j_write_summary`
  2. Update `ingestion_runs` for batch-level metrics:
     * `entities_extracted`
     * `entities_upserted`
     * `relationships_created`
     * Conflicts.
* Logging: Consolidate run-level metrics.

---

### **Step 8 — Fallback / Quarantine**

* Input: Errors or ambiguous results from previous steps.
* Action:
  1. Insert document in `quarantined_documents` with reason.
  2. Notify developers (optional `schema_change_requests`).
  3. Set `next_action` in `ingestion_logs`.

---

### **Step 9 — Post-Processing / Notifications**

* Input: `ingestion_runs` + `ingestion_logs`.
* Action:
  1. Trigger alerts for critical errors.
  2. Summarize ingestion batch.
  3. Optionally trigger **schema updater LLM** if new patterns detected.
