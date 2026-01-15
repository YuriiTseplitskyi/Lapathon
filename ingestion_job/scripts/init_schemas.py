
import os
import sys
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv
from pathlib import Path

# Fix paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Load .env
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

def get_db():
    client = MongoClient(MONGO_URI)
    return client[MONGO_DB]

def now_utc():
    return datetime.now(timezone.utc)

def make_entity_schema(name, props, identity_keys=[]):
    # Convert simple prop list to EntityPropertySchema objects
    properties = []
    for p in props:
        properties.append({
            "name": p,
            "type": "string",
            "is_required": False,
            "change_type": "rarely_changed",
            "normalize": []
        })

    # Prepare Identity Keys with priority
    formatted_id_keys = []
    for idx, ik in enumerate(identity_keys):
        formatted_id_keys.append({
            "priority": (idx + 1) * 10,
            "when": ik.get("when", {}),
            "properties": ik.get("properties", [])
        })
        
    # Build complete structure
    return {
        "entity_name": name,
        "neo4j": {
            "labels": [name],
            "primary_key": "node_id",
            "constraints": []
        },
        "identity_keys": formatted_id_keys,
        "properties": properties,
        "merge_policy": {
            "default": "prefer_non_null",
            "immutable_conflict": "quarantine_and_alert",
            "rarely_changed_conflict": "log_warning_and_keep_existing",
            "dynamic_conflict": "take_latest_by_source_timestamp"
        },
        "source_priority": [],
        "version": 1,
        "status": "active",
        "created_at": now_utc(),
        "updated_at": now_utc()
    }

def init_entities(db):
    print("Initializing Entity Schemas...")
    coll = db["entity_schemas"]
    coll.delete_many({}) # Clear existing
    
    entities = []
    
    # 1. Person
    entities.append(make_entity_schema(
        "Person", 
        ["person_id", "gender", "unzr", "birth_date", "citizenship", "registry_source", 
         "last_name", "birth_place", "middle_name", "rnokpp", "full_name", "first_name"],
        [
            {"properties": ["rnokpp"], "when": {"exists": ["rnokpp"]}},
            {"properties": ["full_name"], "when": {"exists": ["full_name"]}} 
        ]
    ))
    
    # 2. Vehicle
    entities.append(make_entity_schema(
        "Vehicle",
        ["vehicle_id", "year", "color", "registration_number", "vin", "model", "make", "car_id"],
        [{"properties": ["vin"], "when": {"exists": ["vin"]}}]
    ))

    # 3. CivilEvent
    entities.append(make_entity_schema(
        "CivilEvent",
        ["event_id", "response_id", "date", "registry_office", "event_type", "act_number"],
        [{"properties": ["act_number"], "when": {"exists": ["act_number"]}}]
    ))
    
    # 4. CourtCase
    entities.append(make_entity_schema("CourtCase", ["court_id", "case_id", "case_number"]))
    
    # 5. Court
    entities.append(make_entity_schema("Court", ["court_id", "court_name", "court_code"]))
    
    # 6. CourtDecision
    entities.append(make_entity_schema(
        "CourtDecision", 
        ["court_id", "decision_id", "reg_num", "court_name", "case_number", "decision_date", "decision_type"]
    ))
    
    # 7. IncomeRecord
    entities.append(make_entity_schema(
        "IncomeRecord",
        ["person_id", "organization_id", "period_id", "income_id", "tax_amount", "income_type_code",
         "tax_transferred", "response_id", "income_accrued", "income_paid", "income_amount", "tax_charged"]
    ))
    
    # 8. Period
    entities.append(make_entity_schema("Period", ["period_id", "year", "quarter"]))
    
    # 9. Organization
    entities.append(make_entity_schema(
        "Organization", 
        ["name", "organization_id", "org_type", "org_code"],
        [{"properties": ["org_code"], "when": {"exists": ["org_code"]}}]
    ))
    
    # 10. OwnershipRight
    entities.append(make_entity_schema(
        "OwnershipRight",
        ["property_id", "right_id", "rn_num", "registrar", "right_reg_date", "pr_state",
         "doc_type", "doc_type_extension", "right_type", "doc_date", "doc_publisher", "share"]
    ))
    
    # 11. Property
    entities.append(make_entity_schema(
        "Property",
        ["property_id", "reg_num", "registration_date", "re_type", "state", "cad_num", "area", "area_unit"],
        [{"properties": ["reg_num"], "when": {"exists": ["reg_num"]}}]
    ))
    
    # 12. Address
    entities.append(make_entity_schema(
        "Address",
        ["address_id", "street", "region", "house", "apartment", "city", "address_line", "district", "koatuu"]
    ))
    
    # 13. Identifier
    entities.append(make_entity_schema("Identifier", ["identifier_id", "identifier_value", "identifier_type"]))
    
    # 14. TaxAgent
    entities.append(make_entity_schema(
        "TaxAgent",
        ["name", "organization_id", "org_type", "org_code"],
        [{"properties": ["org_code"], "when": {"exists": ["org_code"]}}]
    ))
    
    # 15. VehicleRegistration
    entities.append(make_entity_schema(
        "VehicleRegistration",
        ["vehicle_id", "registration_id", "registration_date", "opercode", "dep_reg_name", "doc_id", "status"]
    ))

    # 16. Document (Passport etc)
    entities.append(make_entity_schema(
        "Document",
        ["document_id", "doc_number", "doc_series", "type", "date_issue", "dep_out", "status", "expiration_date"],
        [{"properties": ["doc_number", "doc_series"], "when": {"exists": ["doc_number"]}}]
    ))

    # 17. Activity (NACE/KVED)
    entities.append(make_entity_schema(
        "Activity",
        ["activity_id", "code", "name", "is_primary"]
    ))

    # Update Organization props
    # (Re-injecting Organization with edrpou)
    # Finding index of Organization... easier to just append, existing `make_entity_schema` creates list.
    # But I should update the existing one if possible, or just add `edrpou` to the list above in `replace_file_content` block?
    # I am replacing lines 161-232 of original file (which contains init_rels too).
    # I will rewrite the end of init_entities and init_relationships fully.

    # Upsert
    for e in entities:
        if e["entity_name"] == "Organization":
            e["properties"].append({
                "name": "edrpou", "type": "string", "is_required": False, "change_type": "rarely_changed", "normalize": []
            })
        coll.replace_one({"entity_name": e["entity_name"]}, e, upsert=True)
    
    print(f"Inserted {len(entities)} entity schemas.")

def make_rel_schema(name, rel_type, from_ent, to_ent, props=[], from_ref=None, to_ref=None):
    # Default refs if not provided (fallback to Label for simplicity if user didn't specify custom ref)
    # But note: init_registers uses specific refs like "Prop", "Right". 
    # If from_ref is None, we default to from_ent (Label).
    f_ref = from_ref if from_ref else from_ent
    t_ref = to_ref if to_ref else to_ent
    
    return {
        "relationship_name": name,
        "neo4j": {
            "type": rel_type,
            "direction": "out",
            "from_label": from_ent,
            "to_label": to_ent
        },
        "endpoints": {
            "from_entity": from_ent,
            "to_entity": to_ent
        },
        "creation_rules": [
            {
                "rule_id": "default",
                "when": {"all": []},
                "bind": {
                    "from": {"entity_ref": f_ref},
                    "to": {"entity_ref": t_ref}
                },
                "properties": [{"name": p} for p in props]
            }
        ],
        "uniqueness": {
            "strategy": "unique_per_endpoints_and_type",
            "keys": []
        },
        "merge_policy": {},
        "version": 1,
        "status": "active",
        "created_at": now_utc(),
        "updated_at": now_utc()
    }

def init_relationships(db):
    print("Initializing Relationship Schemas...")
    coll = db["relationship_schemas"]
    coll.delete_many({})
    
    rels = []
    
    # RRP Relationships
    # Right -> Property
    rels.append(make_rel_schema("OwnershipRight_RIGHT_TO_Property", "RIGHT_TO", "OwnershipRight", "Property", [], from_ref="Right", to_ref="Prop"))
    # Person (Owner) -> Right
    rels.append(make_rel_schema("Person_HAS_RIGHT_OwnershipRight", "HAS_RIGHT", "Person", "OwnershipRight", ["role"], from_ref="Owner", to_ref="Right"))
    # Property -> Address
    rels.append(make_rel_schema("Property_LOCATED_AT_Address", "LOCATED_AT", "Property", "Address", [], from_ref="Prop", to_ref="Addr"))

    # DRFO Relationships
    # TaxAgent -> Income
    rels.append(make_rel_schema("Organization_PAID_INCOME_IncomeRecord", "PAID_INCOME", "Organization", "IncomeRecord", [], from_ref="TaxAgent", to_ref="IncRec"))
    # Person (Main) -> Income
    # Note: MainPerson is Root scope, IncRec is nested. Needs relationship builder robust enough (which I haven't fixed yet, but let's define it correctly first).
    rels.append(make_rel_schema("Person_HAS_INCOME_IncomeRecord", "HAS_INCOME", "Person", "IncomeRecord", [], from_ref="MainPerson", to_ref="IncRec"))

    # EDR Relationships
    # Org -> Addr
    rels.append(make_rel_schema("Organization_HAS_ADDRESS_Address", "HAS_ADDRESS", "Organization", "Address", [], from_ref="Org", to_ref="OrgAddr"))
    # Org -> Head (Person)
    # We mapped Head (Person). Need relationship.
    # Person_IS_HEAD_OF_Organization? 
    # Or Organization_HAS_HEAD_Person?
    # Let's add one. Labels: Organization, Person.
    rels.append(make_rel_schema("Organization_HAS_HEAD_Person", "HAS_HEAD", "Organization", "Person", [], from_ref="Org", to_ref="Head"))

    # EIS Relationships
    # Person -> Document
    rels.append(make_rel_schema("Person_HAS_DOCUMENT_Document", "HAS_DOCUMENT", "Person", "Document", [], from_ref="EisPerson", to_ref="Passport"))
    # Issuer -> Document?
    rels.append(make_rel_schema("Organization_ISSUED_Document", "ISSUED", "Organization", "Document", [], from_ref="Issuer", to_ref="Passport"))

    # ERD Relationships (Power of Attorney / Vehicle)
    # Grantor -> Vehicle
    rels.append(make_rel_schema("Person_OWNS_VEHICLE_Vehicle", "OWNS_VEHICLE", "Person", "Vehicle", ["role"], from_ref="Grantor", to_ref="ProxyVehicle"))
    
    # Court Relationships
    rels.append(make_rel_schema("CourtCase_IN_COURT_Court", "IN_COURT", "CourtCase", "Court", [], from_ref="CaseNode", to_ref="CourtNode"))
    rels.append(make_rel_schema("CourtDecision_FOR_CASE_CourtCase", "FOR_CASE", "CourtDecision", "CourtCase", [], from_ref="DecisionNode", to_ref="CaseNode"))
    
    # Legacy / Other (can add Period if needed later)
    # rels.append(make_rel_schema("IncomeRecord_FOR_PERIOD_Period", "FOR_PERIOD", "IncomeRecord", "Period"))


    for r in rels:
        coll.replace_one({"relationship_name": r["relationship_name"]}, r, upsert=True)
    
    print(f"Inserted {len(rels)} relationship schemas.")

def init_registers(db):
    print("Initializing Register Schemas...")
    coll = db["register_schemas"]
    coll.delete_many({})
    
    variants = []
    
    def m(mid, scope, src_path, target_ent, target_prop, ent_ref):
        return {
            "mapping_id": mid,
            "scope": {"foreach": scope},
            "source": {"json_path": src_path},
            "targets": [{"entity": target_ent, "property": target_prop, "entity_ref": ent_ref}]
        }

    # ==========================
    # 1. MJU EDR Prod
    # ==========================
    edr_mappings = []
    # Founder
    edr_mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.name", "Person", "full_name", "FounderPerson"))
    edr_mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.code", "Person", "rnokpp", "FounderPerson"))
    # Head
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.first_middle_name", "Person", "full_name", "HeadPerson"))
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.last_name", "Person", "last_name", "HeadPerson"))
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.rnokpp", "Person", "rnokpp", "HeadPerson"))

    variants.append({
        "variant_id": "edr_subject_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.meta.registry_code", "value": "Test_ICS_cons"},
                {"type": "json_equals", "path": "$.meta.service_code", "value": "2_MJU_EDR_prod"},
                {"type": "json_equals", "path": "$.meta.method_code", "value": "SubjectDetail2Ext"}
            ]
        },
        "mappings": edr_mappings
    })

def init_registers(db: Database):
    print("Initializing Register Schemas...")
    coll = db["register_schemas"]
    coll.drop()
    
    # helper for mapping
    # m(mapping_id, scope_str, source_str, label, prop, ent_ref)
    def m(mid, scope_path, src_path, lbl, prop, ent_ref):
        return {
            "mapping_id": mid,
            "scope": {"foreach": scope_path},
            "source": {"json_path": src_path},
            "targets": [
                {
                    "entity": lbl,
                    "property": prop,
                    "entity_ref": ent_ref
                }
            ]
        }

    # ==========================================
    # 1. RRP (State Register of Rights to Real Estate)
    # ==========================================
    rrp_variants = []
    rrp_mappings = []
    base_scope = "$.data.array.resultData.result[*].realty[*]"
    
    # Property Node
    rrp_mappings.append(m("prop_main", base_scope, "$.regNum", "Property", "reg_num", "Prop"))
    rrp_mappings.append(m("prop_main", base_scope, "$.reType", "Property", "re_type", "Prop"))
    rrp_mappings.append(m("prop_main", base_scope, "$.regDate", "Property", "registration_date", "Prop"))
    
    # Area (nested list usually 1 item, flatten via path)
    # Path: groundArea[0].area etc.
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].area", "Property", "area", "Prop"))
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].areaUM", "Property", "area_unit", "Prop"))
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].cadNum", "Property", "cad_num", "Prop"))

    # Address Node
    rrp_mappings.append(m("prop_addr", base_scope, "$.realtyAddress[0].addressDetail", "Address", "full_address", "Addr"))
    rrp_mappings.append(m("prop_addr", base_scope, "$.realtyAddress[0].koatuu", "Address", "koatuu", "Addr"))
    
    # 1.2 Ownership & Subjects (Scope: properties -> subjects)
    right_scope = "$.data.array.resultData.result[*].realty[*].properties[*]"
    rrp_mappings.append(m("right_node", right_scope, "$.rnNum", "OwnershipRight", "rn_num", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.prKind", "OwnershipRight", "type", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.partSize", "OwnershipRight", "share", "Right"))
    
    # Subjects (Owners) - flattened first subject for simplicity
    rrp_mappings.append(m("right_owner_0", right_scope, "$.subjects[0].sbjName", "Person", "full_name", "Owner"))
    rrp_mappings.append(m("right_owner_0", right_scope, "$.subjects[0].sbjCode", "Person", "rnokpp", "Owner"))

    rrp_variants.append({
        "variant_id": "rrp_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.data.array.entity", "value": "rrpExch_external"}
            ]
        },
        "mappings": rrp_mappings
    })

    # ==========================================
    # 2. DRFO (Tax Income)
    # ==========================================
    drfo_variants = []
    drfo_mappings = []
    inc_scope = "$.data.Envelope.Body.InfoIncomeSourcesDRFO2AnswerResponse.SourcesOfIncome[*]"
    
    # Income Node
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.IncomeAccrued", "IncomeRecord", "amount", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.period_year", "IncomeRecord", "year", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.period_quarter_month", "IncomeRecord", "period", "IncRec"))
    
    # TaxAgent Node
    drfo_mappings.append(m("tax_agent", inc_scope, "$.TaxAgent", "Organization", "tax_id", "TaxAgent"))
    drfo_mappings.append(m("tax_agent", inc_scope, "$.NameTaxAgent", "Organization", "name", "TaxAgent"))
    
    # Person (Subject) - Root level
    root_scope = "$.data.Envelope.Body.InfoIncomeSourcesDRFO2AnswerResponse.Info"
    drfo_mappings.append(m("main_subj", root_scope, "$.RNOKPP", "Person", "rnokpp", "MainPerson"))

    drfo_variants.append({
        "variant_id": "drfo_income_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.InfoIncomeSourcesDRFO2AnswerResponse"}
            ]
        },
        "mappings": drfo_mappings
    })

    # ==========================================
    # 3. EDR (Unified Registry of Enterprises)
    # ==========================================
    edr_variants = []
    edr_mappings = []
    edr_scope = "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject"
    
    # Organization
    edr_mappings.append(m("edr_org", edr_scope, "$.code", "Organization", "edrpou", "Org"))
    edr_mappings.append(m("edr_org", edr_scope, "$.names.name", "Organization", "name", "Org"))
    edr_mappings.append(m("edr_org", edr_scope, "$.state_text", "Organization", "status", "Org"))
    edr_mappings.append(m("edr_org", edr_scope, "$.address.address", "Address", "full_address", "OrgAddr"))
    
    # CEO (Head) - list
    head_scope = "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject.heads[*]"
    edr_mappings.append(m("edr_head", head_scope, "$.l_name", "Person", "last_name", "Head"))
    edr_mappings.append(m("edr_head", head_scope, "$.f_name", "Person", "first_name", "Head"))

    edr_variants.append({
        "variant_id": "edr_subject_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.SubjectDetail2ExtResponse"}
            ]
        },
        "mappings": edr_mappings
    })

    # ==========================================
    # 4. EIS (Passport/Person)
    # ==========================================
    eis_variants = []
    eis_mappings = []
    eis_scope = "$.data.root.result"
    
    # Person
    eis_mappings.append(m("eis_person", eis_scope, "$.unzr", "Person", "unzr", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.last_name", "Person", "last_name", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.name_transliteration.first_name_latin", "Person", "first_name_en", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.date_birth", "Person", "dob", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.citizenship", "Person", "citizenship", "EisPerson"))
    
    # Document (Passport) - nested list
    doc_scope = "$.data.root.result.documents[*]"
    eis_mappings.append(m("eis_doc", doc_scope, "$.number", "Document", "doc_number", "Passport"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.series", "Document", "doc_series", "Passport"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.doc_type", "Document", "type", "Passport"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.date_issue", "Document", "date_issue", "Passport"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.dep_out", "Organization", "name", "Issuer"))

    eis_variants.append({
        "variant_id": "eis_person_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.root.result.unzr"}
            ]
        },
        "mappings": eis_mappings
    })

    # ==========================================
    # 5. Land Cadastre (DZK)
    # ==========================================
    dzk_variants = []
    dzk_mappings = []
    dzk_scope = "$.data.result.cadNum[*]"
    dzk_mappings.append(m("dzk_prop", dzk_scope, "$", "Property", "cad_num", "LandProp"))

    dzk_variants.append({
        "variant_id": "dzk_land_simple_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.result.cadNum"}
            ]
        },
        "mappings": dzk_mappings
    })

    # ==========================================
    # 6. Civil Status Registry (DRACS)
    # ==========================================
    dracs_variants = []
    dracs_mappings = []
    
    # Note: Most DRACS responses in dataset are empty (ResultData is empty XML)
    # But we define the schema for when data exists
    # Service: GetMarriageAr, GetDivorceAr, GetBirthAr, etc.
    # These return AR_LIST with ACT records
    
    # Simplified: We'll just detect DRACS and skip for now since data is empty
    # Legacy likely had manual CSV data
    dracs_variants.append({
        "variant_id": "dracs_empty_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.ArServiceAnswer"}
            ]
        },
        "mappings": []  # Empty - no data to extract
    })

    # ==========================================
    # 7. Power of Attorney / Vehicle (ERD)
    # ==========================================
    erd_variants = []
    erd_mappings = []
    
    # Grantor/Representative
    grantor_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Grantor"
    erd_mappings.append(m("erd_grantor", grantor_scope, "$.Name", "Person", "full_name", "Grantor"))
    erd_mappings.append(m("erd_grantor", grantor_scope, "$.Code", "Person", "rnokpp", "Grantor"))
    
    rep_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Representative"
    erd_mappings.append(m("erd_rep", rep_scope, "$.Name", "Person", "full_name", "Representative"))
    erd_mappings.append(m("erd_rep", rep_scope, "$.Code", "Person", "rnokpp", "Representative"))
    
    # Vehicle Property
    veh_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Properties.Property[?(@.Property_type=='1')]"
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Government_registration_number", "Vehicle", "registration_number", "ProxyVehicle"))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Serial_number", "Vehicle", "vin", "ProxyVehicle"))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Description", "Vehicle", "description", "ProxyVehicle"))
    
    erd_variants.append({
        "variant_id": "erd_poa_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse"}
            ]
        },
        "mappings": erd_mappings
    })

    # ==========================================
    # 8. Court Decisions
    # ==========================================
    court_variants = []
    court_mappings = []
    
    # Court
    court_scope = "$.data.array[*]"
    court_mappings.append(m("court_node", court_scope, "$.courtId", "Court", "court_id", "CourtNode"))
    court_mappings.append(m("court_node", court_scope, "$.courtName", "Court", "court_name", "CourtNode"))
    
    # CourtCase
    court_mappings.append(m("case_node", court_scope, "$.caseNum", "CourtCase", "case_number", "CaseNode"))
    court_mappings.append(m("case_node", court_scope, "$.courtId", "CourtCase", "court_id", "CaseNode"))
    
    # CourtDecision
    court_mappings.append(m("decision_node", court_scope, "$.regNum", "CourtDecision", "reg_num", "DecisionNode"))
    court_mappings.append(m("decision_node", court_scope, "$.docDate", "CourtDecision", "decision_date", "DecisionNode"))
    court_mappings.append(m("decision_node", court_scope, "$.docTypeName", "CourtDecision", "decision_type", "DecisionNode"))
    court_mappings.append(m("decision_node", court_scope, "$.judgeFio", "CourtDecision", "judge_name", "DecisionNode"))
    court_mappings.append(m("decision_node", court_scope, "$.caseNum", "CourtDecision", "case_number", "DecisionNode"))
    
    # Person (involved)
    court_mappings.append(m("involved_person", court_scope, "$.PIB", "Person", "full_name", "CourtPerson"))
    court_mappings.append(m("involved_person", court_scope, "$.rnokpp", "Person", "rnokpp", "CourtPerson"))
    
    court_variants.append({
        "variant_id": "court_decision_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.array[0].courtId"}
            ]
        },
        "mappings": court_mappings
    })

    # ==========================================
    # REGISTER INSERTION
    # ==========================================
    
    registers = [
        {"code": "RRP", "name": "Registry of Real Property", "variants": rrp_variants},
        {"code": "DRFO", "name": "State Register of Natural Persons (Tax)", "variants": drfo_variants},
        {"code": "EDR", "name": "Unified State Register of Enterprises", "variants": edr_variants},
        {"code": "EIS", "name": "Electronic Information System", "variants": eis_variants},
        {"code": "DZK", "name": "State Land Cadastre", "variants": dzk_variants},
        {"code": "DRACS", "name": "Civil Status Registry", "variants": dracs_variants},
        {"code": "ERD", "name": "Power of Attorney Registry", "variants": erd_variants},
        {"code": "COURT", "name": "Court Decisions", "variants": court_variants}
    ]

    for reg in registers:
        reg_schema = {
            "registry_code": reg["code"],
            "name": reg["name"],
            "schema_match": {
                "canonical_header_fields": {}
            },
            "variants": reg["variants"],
            "created_at": now_utc(),
            "updated_at": now_utc()
        }
        coll.replace_one({"registry_code": reg["code"]}, reg_schema, upsert=True)
        print(f"Inserted Register: {reg['code']} with {len(reg['variants'])} variants.")

if __name__ == "__main__":
    db = get_db()
    init_entities(db)
    init_relationships(db)
    init_registers(db)
