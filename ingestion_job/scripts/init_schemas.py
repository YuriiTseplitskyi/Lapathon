
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
    client = MongoClient(
        MONGO_URI,
        tlsAllowInvalidCertificates=True,
        connectTimeoutMS=60000,
        socketTimeoutMS=60000,
        serverSelectionTimeoutMS=60000
    )
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
    
    # 1. Person - COMPREHENSIVE
    entities.append(make_entity_schema(
        "Person", 
        ["person_id", "gender", "unzr", "birth_date", "citizenship", "registry_source", "registry_place",
         "last_name", "birth_place", "middle_name", "rnokpp", "full_name", "first_name", "first_name_en",
         # Passport / Document fields merged
         "passport_series", "passport_number", "passport_issue_date", "passport_issuer", "photo_url", "has_photo"],
        [
            {"properties": ["rnokpp"], "when": {"exists": ["rnokpp"]}},
            {"properties": ["full_name"], "when": {"exists": ["full_name"]}} 
        ]
    ))
    
    # 2. Vehicle - COMPREHENSIVE
    entities.append(make_entity_schema(
        "Vehicle",
        ["vehicle_id", "year", "color", "registration_number", "vin", "model", "make", "car_id",
         "description", "vehicle_type", "property_type", "asset_type"],
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
        ["court_id", "decision_id", "reg_num", "court_name", "case_number", "decision_date", "decision_type",
         "content_url", "content_hash", "content_snippet"]
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

    # 10b. Request (Traceability)
    entities.append(make_entity_schema(
        "Request",
        ["request_id", "date", "source_system", "user_id"],
        [{"properties": ["request_id"], "when": {"exists": ["request_id"]}}]
    ))
    
    # 11. RealEstateProperty (Buildings, Apartments)
    entities.append(make_entity_schema(
        "RealEstateProperty",
        ["property_id", "reg_num", "registration_date", "re_type", "state", "area", "area_unit", "description", "asset_type"],
        [{"properties": ["reg_num"], "when": {"exists": ["reg_num"]}}]
    ))

    # 12. LandParcel (Land)
    entities.append(make_entity_schema(
        "LandParcel",
        ["property_id", "cad_num", "area", "area_unit", "purpose", "asset_type"],
        [{"properties": ["cad_num"], "when": {"exists": ["cad_num"]}}]
    ))
    
    # 13. Property (Generic / Unclassified - Deprecated but kept for fallback)
    entities.append(make_entity_schema(
        "Property",
        ["property_id", "reg_num", "registration_date", "re_type", "state", "cad_num", "area", "area_unit", "asset_type"],
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
    # RRP Relationships
    # Right -> Property (RealEstateProperty or LandParcel or Property)
    # Since we can have multiple targets for "Prop" ref in pipeline (based on label), we should ideally support multiple matching.
    # But init_schemas relationship definition is strict on labels (Neo4j Type definition).
    # We will define relationships for RealEstateProperty.
    
    # OwnershipRight -> RealEstateProperty
    rels.append(make_rel_schema("OwnershipRight_RIGHT_TO_RealEstateProperty", "RIGHT_TO", "OwnershipRight", "RealEstateProperty", [], from_ref="Right", to_ref="Prop"))
    
    # Person (Owner) -> Right
    rels.append(make_rel_schema("Person_HAS_RIGHT_OwnershipRight", "HAS_RIGHT", "Person", "OwnershipRight", ["role"], from_ref="Owner", to_ref="Right"))
    
    # RealEstateProperty -> Address
    rels.append(make_rel_schema("RealEstateProperty_LOCATED_AT_Address", "LOCATED_AT", "RealEstateProperty", "Address", [], from_ref="Prop", to_ref="Addr"))

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

    # EIS Relationships - Converted to Attributes
    # Person -> Document (Removed, now attributes)
    # Issuer -> Document (Removed)

    # Request Relationships
    rels.append(make_rel_schema("Request_SEARCHED_Person", "SEARCHED", "Request", "Person", [], from_ref="Req", to_ref="Subject"))
    
    # Request -> Result (Answer)
    # Linking distinct roles in ERD answer
    rels.append(make_rel_schema("Request_RETURNED_Grantor", "RETURNED", "Request", "Person", [], from_ref="Req", to_ref="Grantor"))
    rels.append(make_rel_schema("Request_RETURNED_Representative", "RETURNED", "Request", "Person", [], from_ref="Req", to_ref="Representative"))

    # ERD Relationships (Power of Attorney / Vehicle)
    # Grantor -> Vehicle
    rels.append(make_rel_schema("Person_OWNS_VEHICLE_Vehicle", "OWNS_VEHICLE", "Person", "Vehicle", ["role"], from_ref="Grantor", to_ref="ProxyVehicle"))
    
    # Court Relationships
    rels.append(make_rel_schema("CourtCase_IN_COURT_Court", "IN_COURT", "CourtCase", "Court", [], from_ref="CaseNode", to_ref="CourtNode"))
    rels.append(make_rel_schema("CourtDecision_FOR_CASE_CourtCase", "FOR_CASE", "CourtDecision", "CourtCase", [], from_ref="DecisionNode", to_ref="CaseNode"))
    rels.append(make_rel_schema("CourtDecision_INVOLVES_Person", "INVOLVES", "CourtDecision", "Person", ["role"], from_ref="DecisionNode", to_ref="CourtPerson"))

    # Person -> Document (EIS)
    rels.append(make_rel_schema("Person_HAS_DOCUMENT_Document", "HAS_DOCUMENT", "Person", "Document", [], from_ref="EisPerson", to_ref="EisDoc"))
    
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
    
    def m(mid, scope, src_path, target_ent, target_prop, ent_ref, use_root_context=False):
        source = {"json_path": src_path}
        if use_root_context:
            source["use_root_context"] = True
        return {
            "mapping_id": mid,
            "scope": {"foreach": scope},
            "source": source,
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
    # m(mapping_id, scope_str, source_str, label, prop, ent_ref, transform)
    def m(mid, scope_path, src_path, lbl, prop, ent_ref, transform=None, use_root_context=False, filter_rules=None):
        source = {"json_path": src_path}
        if use_root_context:
            source["use_root_context"] = True
        
        mapping = {
            "mapping_id": mid,
            "scope": {"foreach": scope_path},
            "source": source,
            "targets": [
                {
                    "entity": lbl,
                    "property": prop,
                    "entity_ref": ent_ref,
                    "transform": transform
                }
            ]
        }
        if filter_rules:
            mapping["filter"] = filter_rules
        return mapping

    # ==========================================
    # 1. RRP (State Register of Rights to Real Estate)
    # ==========================================
    rrp_variants = []
    rrp_mappings = []
    base_scope = "$.data.array.resultData.result[*].realty[*]"
    
    # Property Node -> RealEstateProperty
    rrp_mappings.append(m("prop_main", base_scope, "$.regNum", "RealEstateProperty", "reg_num", "Prop"))
    rrp_mappings.append(m("prop_main", base_scope, "$.reType", "RealEstateProperty", "re_type", "Prop"))
    rrp_mappings.append(m("prop_main", base_scope, "$.regDate", "RealEstateProperty", "registration_date", "Prop"))
    
    # Static asset_type
    rrp_mappings.append(m("prop_static", base_scope, "$.regNum", "RealEstateProperty", "asset_type", "Prop", 
                          transform={"type": "constant", "value": "real_estate"}))
    
    # Area (nested list usually 1 item, flatten via path)
    # Path: groundArea[0].area etc.
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].area", "RealEstateProperty", "area", "Prop"))
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].areaUM", "RealEstateProperty", "area_unit", "Prop"))
    # Note: RRP sometimes has cadNum inside groundArea, but if it has regNum it's primarily RealEstate.
    # We could map cadNum as a property of RealEstateProperty too.
    rrp_mappings.append(m("prop_area", base_scope, "$.groundArea[0].cadNum", "RealEstateProperty", "cad_num", "Prop"))

    # Address Node
    # Splitting Full Address
    # Example: "Вінницька обл., Вінницький р., с. Агрономічне, вул. Лісова, земельна ділянка 7-Б"
    # Mapping full string to full_address
    rrp_mappings.append(m("prop_addr", base_scope, "$.realtyAddress[0].addressDetail", "Address", "full_address", "Addr"))
    
    # Address Source
    rrp_mappings.append(m("prop_addr_src", base_scope, "$.realtyAddress[0].addressDetail", "Address", "address_source", "Addr",
                          transform={"type": "constant", "value": "rrp"}))
    
    # Split region (index 0)
    rrp_mappings.append(m("prop_addr_region", base_scope, "$.realtyAddress[0].addressDetail", "Address", "region", "Addr", 
                          transform={"type": "split", "delimiter": ",", "index": 0}))
    # Split district (index 1)
    rrp_mappings.append(m("prop_addr_dist", base_scope, "$.realtyAddress[0].addressDetail", "Address", "district", "Addr", 
                          transform={"type": "split", "delimiter": ",", "index": 1}))
    # Split city (index 2)
    rrp_mappings.append(m("prop_addr_city", base_scope, "$.realtyAddress[0].addressDetail", "Address", "city", "Addr", 
                          transform={"type": "split", "delimiter": ",", "index": 2}))

    rrp_mappings.append(m("prop_addr", base_scope, "$.realtyAddress[0].koatuu", "Address", "koatuu", "Addr"))
    
    # 1.2 Ownership & Subjects (Scope: properties -> subjects)
    right_scope = "$.data.array.resultData.result[*].realty[*].properties[*]"
    rrp_mappings.append(m("right_node", right_scope, "$.rnNum", "OwnershipRight", "rn_num", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.prKind", "OwnershipRight", "right_type", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.partSize", "OwnershipRight", "share", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.regDate", "OwnershipRight", "right_reg_date", "Right"))
    rrp_mappings.append(m("right_node", right_scope, "$.prState", "OwnershipRight", "pr_state", "Right"))
    
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
    
    # 1.3 Empty / No Data Response (GetInheritedPropertiesByNameOrIDN)
    rrp_variants.append({
        "variant_id": "rrp_empty_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.GetInheritedPropertiesByNameOrIDNResponse"}
            ]
        },
        "mappings": [] # No data to extract, valid empty response
    })

    # ==========================================
    # 2. DRFO (Tax Income) - COMPREHENSIVE
    # ==========================================
    drfo_variants = []
    drfo_mappings = []
    inc_scope = "$.data.Envelope.Body.InfoIncomeSourcesDRFO2AnswerResponse.SourcesOfIncome[*]"
    
    # Income Node - ALL FIELDS from Опис_полів.xlsx
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.IncomeAccrued", "IncomeRecord", "income_accrued", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.IncomePaid", "IncomeRecord", "income_paid", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.TaxCharged", "IncomeRecord", "tax_charged", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.TaxTransferred", "IncomeRecord", "tax_transferred", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.period_year", "IncomeRecord", "year", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.period_quarter_month", "IncomeRecord", "period", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.IncomeTaxes.SignOfIncomePrivilege", "IncomeRecord", "income_type_code", "IncRec"))
    drfo_mappings.append(m("inc_rec", inc_scope, "$.DateOfEmployment", "IncomeRecord", "employment_date", "IncRec"))
    
    # TaxAgent Node
    drfo_mappings.append(m("tax_agent", inc_scope, "$.TaxAgent", "Organization", "edrpou", "TaxAgent"))
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
    
    # Person - COMPREHENSIVE
    eis_mappings.append(m("eis_person", eis_scope, "$.unzr", "Person", "unzr", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.last_name", "Person", "last_name", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.first_name", "Person", "first_name", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.middle_name", "Person", "middle_name", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.name_transliteration.first_name_latin", "Person", "first_name_en", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.date_birth", "Person", "birth_date", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.citizenship", "Person", "citizenship", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.gender", "Person", "gender", "EisPerson"))
    eis_mappings.append(m("eis_person", eis_scope, "$.registr_place.address", "Person", "registry_place", "EisPerson"))
    
    # Document (Passport) - nested list
    # Mapped to separate Document entity
    doc_scope = "$.data.root.result.documents[*]"
    eis_mappings.append(m("eis_doc", doc_scope, "$.number", "Document", "doc_number", "EisDoc"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.series", "Document", "doc_series", "EisDoc"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.date_issue", "Document", "doc_issue_date", "EisDoc"))
    eis_mappings.append(m("eis_doc", doc_scope, "$.dep_out", "Document", "doc_issuer", "EisDoc"))
    
    # Static doc type
    eis_mappings.append(m("eis_doc_type", doc_scope, "$.number", "Document", "doc_type", "EisDoc",
                          transform={"type": "constant", "value": "passport"}))
    
    # Photo - Handling Base64
    # We map 'photo' from JSON to a temporary property 'photo_base64' (or just 'photo')
    # The pipeline will intercept 'photo_base64' field, upload to MinIO, and set 'photo_url'
    eis_mappings.append(m("eis_photo", eis_scope, "$.photo", "Person", "photo_base64", "EisPerson"))

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
    dzk_mappings.append(m("dzk_prop", dzk_scope, "$", "LandParcel", "cad_num", "LandProp"))
    dzk_mappings.append(m("dzk_asset", dzk_scope, "$", "LandParcel", "asset_type", "LandProp",
                          transform={"type": "constant", "value": "land"}))

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
    
    # Grantor Response Scopes
    grantor_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Grantor"
    rep_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Representative"
    veh_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*].Properties.Property[*]"
    
    # Persons Response Scopes (New for Linkage)
    persons_scope_grantor = "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse.getProxyPersonsNameOrIDNResult.Result_data.ResultDataType[*].Grantor"
    persons_scope_rep = "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse.getProxyPersonsNameOrIDNResult.Result_data.ResultDataType[*].Representative" 
    persons_scope_veh = "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse.getProxyPersonsNameOrIDNResult.Result_data.ResultDataType[*].Properties.Property[*]"

    # --- Mappings for Grantor Response ---
    erd_mappings.append(m("erd_grantor", grantor_scope, "$.Name", "Person", "full_name", "Grantor"))
    erd_mappings.append(m("erd_grantor", grantor_scope, "$.Code", "Person", "rnokpp", "Grantor"))
    
    erd_mappings.append(m("erd_rep", rep_scope, "$.Name", "Person", "full_name", "Representative"))
    erd_mappings.append(m("erd_rep", rep_scope, "$.Code", "Person", "rnokpp", "Representative"))
    
    # Filters for ERD (Vehicle vs Real Estate mix)
    # Exclude Real Estate keywords from Vehicle mappings
    veh_filter = {
        "none": [{
            "type": "json_regex",
            "path": "$.Description",
            "pattern": "(?i)(будинок|квартира|житло|земельна|кімната|приміщення|споруда|майновий)"
        }]
    }
    # Include ONLY Real Estate keywords for RealEstate mappings
    re_filter = {
        "all": [{
            "type": "json_regex",
            "path": "$.Description",
            "pattern": "(?i)(будинок|квартира|житло|земельна|кімната|приміщення|споруда|майновий)"
        }]
    }

    # Vehicles (With Filter)
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Government_registration_number", "Vehicle", "registration_number", "ProxyVehicle", filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Serial_number", "Vehicle", "vin", "ProxyVehicle", filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Description", "Vehicle", "description", "ProxyVehicle", filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle_model", veh_scope, "$.Description", "Vehicle", "model", "ProxyVehicle",
                          transform={"type": "regex", "pattern": r"моделі ([^,]+)", "group": 1}, filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle_year", veh_scope, "$.Description", "Vehicle", "year", "ProxyVehicle",
                          transform={"type": "regex", "pattern": r"рік випуску (\d{4})", "group": 1}, filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Vht_id", "Vehicle", "vehicle_type", "ProxyVehicle", filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle", veh_scope, "$.Property_type", "Vehicle", "property_type", "ProxyVehicle", filter_rules=veh_filter))
    erd_mappings.append(m("erd_vehicle_asset", veh_scope, "$.Vht_id", "Vehicle", "asset_type", "ProxyVehicle",
                          transform={"type": "constant", "value": "vehicle"}, filter_rules=veh_filter))

    # Real Estate (New mappings for same scope)
    erd_mappings.append(m("erd_re", veh_scope, "$.Description", "RealEstateProperty", "description", "ProxyProperty", filter_rules=re_filter))
    erd_mappings.append(m("erd_re", veh_scope, "$.Vht_id", "RealEstateProperty", "re_type", "ProxyProperty", filter_rules=re_filter))
    # Map Vht_id (e.g. "Житловий будинок") to asset_type as "real_estate"
    erd_mappings.append(m("erd_re_asset", veh_scope, "$.Vht_id", "RealEstateProperty", "asset_type", "ProxyProperty", 
                          transform={"type": "constant", "value": "real_estate"}, filter_rules=re_filter))
    # Map registration number if applicable to Reg Num? 
    # Usually "Government_registration_number" is license plate. For house? Maybe registry number.
    erd_mappings.append(m("erd_re", veh_scope, "$.Government_registration_number", "RealEstateProperty", "reg_num", "ProxyProperty", filter_rules=re_filter))

    # Request ID - Map at ResultDataType level so it shares scope with Grantor/Representative
    # Use root_context flag to access parent-level Request_ID while iterating nested array
    result_data_scope = "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Result_data.ResultDataType[*]"
    erd_mappings.append(m("erd_req_result", result_data_scope, "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse.getProxyGrantorNameOrIDNResult.Request_ID", "Request", "request_id", "Req", use_root_context=True))

    # --- Mappings for Persons Response ---
    erd_persons_mappings = []
    erd_persons_mappings.append(m("erd_p_grantor", persons_scope_grantor, "$.Name", "Person", "full_name", "Grantor"))
    erd_persons_mappings.append(m("erd_p_grantor", persons_scope_grantor, "$.Code", "Person", "rnokpp", "Grantor"))
    
    erd_persons_mappings.append(m("erd_p_rep", persons_scope_rep, "$.Name", "Person", "full_name", "Representative"))
    erd_persons_mappings.append(m("erd_p_rep", persons_scope_rep, "$.Code", "Person", "rnokpp", "Representative"))
    
    erd_persons_mappings.append(m("erd_p_vehicle", persons_scope_veh, "$.Government_registration_number", "Vehicle", "registration_number", "ProxyVehicle", filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle", persons_scope_veh, "$.Serial_number", "Vehicle", "vin", "ProxyVehicle", filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle", persons_scope_veh, "$.Description", "Vehicle", "description", "ProxyVehicle", filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle_model", persons_scope_veh, "$.Description", "Vehicle", "model", "ProxyVehicle",
                          transform={"type": "regex", "pattern": r"моделі ([^,]+)", "group": 1}, filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle_year", persons_scope_veh, "$.Description", "Vehicle", "year", "ProxyVehicle",
                          transform={"type": "regex", "pattern": r"рік випуску (\d{4})", "group": 1}, filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle", persons_scope_veh, "$.Vht_id", "Vehicle", "vehicle_type", "ProxyVehicle", filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle", persons_scope_veh, "$.Property_type", "Vehicle", "property_type", "ProxyVehicle", filter_rules=veh_filter))
    erd_persons_mappings.append(m("erd_p_vehicle_asset", persons_scope_veh, "$.Vht_id", "Vehicle", "asset_type", "ProxyVehicle",
                          transform={"type": "constant", "value": "vehicle"}, filter_rules=veh_filter))

    # Real Estate (Persons Response)
    erd_persons_mappings.append(m("erd_p_re", persons_scope_veh, "$.Description", "RealEstateProperty", "description", "ProxyProperty", filter_rules=re_filter))
    erd_persons_mappings.append(m("erd_p_re", persons_scope_veh, "$.Vht_id", "RealEstateProperty", "re_type", "ProxyProperty", filter_rules=re_filter))
    erd_persons_mappings.append(m("erd_p_re_asset", persons_scope_veh, "$.Vht_id", "RealEstateProperty", "asset_type", "ProxyProperty", 
                          transform={"type": "constant", "value": "real_estate"}, filter_rules=re_filter))
    erd_persons_mappings.append(m("erd_p_re", persons_scope_veh, "$.Government_registration_number", "RealEstateProperty", "reg_num", "ProxyProperty", filter_rules=re_filter))

    # Request ID at ResultDataType level for Persons response with root context access
    persons_result_data_scope = "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse.getProxyPersonsNameOrIDNResult.Result_data.ResultDataType[*]"
    erd_persons_mappings.append(m("erd_req_p_result", persons_result_data_scope, "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse.getProxyPersonsNameOrIDNResult.Request_ID", "Request", "request_id", "Req", use_root_context=True))

    erd_variants.append({
        "variant_id": "erd_poa_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.getProxyGrantorNameOrIDNResponse"}
            ]
        },
        "mappings": erd_mappings
    })
    
    erd_variants.append({
        "variant_id": "erd_persons_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.getProxyPersonsNameOrIDNResponse"}
            ]
        },
        "mappings": erd_persons_mappings
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
    
    # CourtDecision - Content
    # Map raw base64 content to 'content_base64' property. Pipeline will process it.
    court_mappings.append(m("decision_node", court_scope, "$.docText", "CourtDecision", "content_base64", "DecisionNode"))
    
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
    # 9. MVS/NAIS Vehicles (answer.json structure)
    # ==========================================
    mvs_variants = []
    mvs_mappings = []
    mvs_scope = "$.data.root.CARS[*]"
    
    # Vehicle
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.VIN", "Vehicle", "vin", "Car"))
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.N_REG", "Vehicle", "registration_number", "Car"))
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.BRAND_NAME", "Vehicle", "make", "Car"))
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.MODEL_NAME", "Vehicle", "model", "Car"))
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.MAKE_YEAR", "Vehicle", "year", "Car", transform={"type": "to_int"})) 
    mvs_mappings.append(m("mvs_veh", mvs_scope, "$.COLOR_NAME", "Vehicle", "color", "Car"))
    
    # Owner
    mvs_mappings.append(m("mvs_owner", mvs_scope, "$.OWNER.CODE", "Person", "rnokpp", "Owner"))
    mvs_mappings.append(m("mvs_owner", mvs_scope, "$.OWNER.LNAME", "Person", "last_name", "Owner"))
    mvs_mappings.append(m("mvs_owner", mvs_scope, "$.OWNER.FNAME", "Person", "first_name", "Owner"))
    
    # Address
    # "ADDRESS_NAME": "м. ВІННИЦЯ, Вінницький р-н"
    addr_path = "$.OWNER.ADDRESS.ADDRESS_NAME"
    mvs_mappings.append(m("mvs_addr", mvs_scope, addr_path, "Address", "full_address", "OwnerAddr"))
    
    # Transform: Split City (Index 0) -> "м. ВІННИЦЯ"
    mvs_mappings.append(m("mvs_addr_city", mvs_scope, addr_path, "Address", "city", "OwnerAddr",
                          transform={"type": "split", "delimiter": ",", "index": 0}))
    
    # Transform: Split District (Index 1) -> " Вінницький р-н"
    mvs_mappings.append(m("mvs_addr_dist", mvs_scope, addr_path, "Address", "district", "OwnerAddr",
                          transform={"type": "split", "delimiter": ",", "index": 1}))

    mvs_variants.append({
        "variant_id": "mvs_cars_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.root.CARS"}
            ]
        },
        "mappings": mvs_mappings
    })

    # ==========================================
    # 10. IDP (Internally Displaced Persons)
    # ==========================================
    idp_variants = []
    
    # Empty / No Data Response (IDPByItn)
    idp_variants.append({
        "variant_id": "idp_empty_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.Response.ResponseCode"}
            ]
        },
        "mappings": [] # No data
    })

    # ==========================================
    # 11. Requests (Traceability)
    # ==========================================
    req_variants = []
    
    # Request XML (SEVDEIR/getProxyPersonsNameOrIDN)
    req_xml_mappings = []
    req_xml_scope = "$"
    
    # Request Node
    req_xml_mappings.append(m("req_node", req_xml_scope, "$.data.Envelope.Body.getProxyPersonsNameOrIDN.Request_ID", "Request", "request_id", "Req"))
    # Subject Person (The one being searched for)
    req_xml_mappings.append(m("req_subject", req_xml_scope, "$.data.Envelope.Body.getProxyPersonsNameOrIDN.Search_nam", "Person", "full_name", "Subject", transform={"type": "trim"}))
    req_xml_mappings.append(m("req_subject", req_xml_scope, "$.data.Envelope.Body.getProxyPersonsNameOrIDN.Search_code", "Person", "rnokpp", "Subject"))
    
    req_variants.append({
        "variant_id": "request_xml_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.getProxyPersonsNameOrIDN.Request_ID"}
            ]
        },
        "mappings": req_xml_mappings
    })

    # Request JSON
    req_json_mappings = []
    req_json_scope = "$"
    # Request Node
    req_json_mappings.append(m("req_node_json", req_json_scope, "$.data.REQUESTID", "Request", "request_id", "Req"))
    # Subject Person
    req_json_mappings.append(m("req_subject_json", req_json_scope, "$.data.CRITERIA.PNAME", "Person", "middle_name", "Subject"))
    req_json_mappings.append(m("req_subject_json", req_json_scope, "$.data.CRITERIA.FNAME", "Person", "first_name", "Subject"))
    req_json_mappings.append(m("req_subject_json", req_json_scope, "$.data.CRITERIA.LNAME", "Person", "last_name", "Subject"))
    req_json_mappings.append(m("req_subject_json", req_json_scope, "$.data.CRITERIA.IPN", "Person", "rnokpp", "Subject"))
    
    req_variants.append({
        "variant_id": "request_json_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.REQUESTID"}
            ]
        },
        "mappings": req_json_mappings
    })

    # Request XML (DRACS)
    req_dracs_mappings = []
    # Use Body as scope, but access fields directly
    dracs_scope = "$"
    # Request Node (ID in Header)
    req_dracs_mappings.append(m("req_dracs", dracs_scope, "$.data.Envelope.Header.id", "Request", "request_id", "Req"))
    
    # Subject Person (Husband)
    dracs_body = "$.data.Envelope.Body.ArMarriageDivorceServiceRequest"
    req_dracs_mappings.append(m("req_dracs_subj", dracs_scope, f"{dracs_body}.HusbandSurname", "Person", "last_name", "Subject"))
    req_dracs_mappings.append(m("req_dracs_subj", dracs_scope, f"{dracs_body}.HusbandName", "Person", "first_name", "Subject"))
    req_dracs_mappings.append(m("req_dracs_subj", dracs_scope, f"{dracs_body}.HusbandPatronymic", "Person", "middle_name", "Subject"))
    req_dracs_mappings.append(m("req_dracs_subj", dracs_scope, f"{dracs_body}.HusbandBirthDate", "Person", "birth_date", "Subject"))
    
    req_variants.append({
        "variant_id": "request_dracs_v1",
        "match_predicate": {
            "all": [
                {"type": "json_regex", "path": "$.data.Envelope.Header.service.serviceCode", "pattern": "Get.*ArBy.*"}
            ]
        },
        "mappings": req_dracs_mappings
    })

    # Request XML (DRFO)
    # ... (Keep existing DRFO mappings)

    # Request Arkan (Border)
    req_arkan_mappings = []
    req_arkan_mappings.append(m("req_arkan", "$.data", "$.fioukr", "Person", "full_name", "Subject", transform={"type": "trim"}))
    
    req_variants.append({
        "variant_id": "request_arkan_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.meta.registry_code", "value": "REQUEST_ARKAN"}
            ]
        },
        "mappings": req_arkan_mappings
    })

    # Request XML (ERD Generic - getProxy*)
    req_erd_mappings = []
    # Wildcard body path using [*] or specialized logic?
    # Helper to map strictly? Let's use specific variants for safety or regex path mapping?
    # Simple regex path support in Adapter isn't there for keys, but jsonpath-ng supports it.
    # Let's add variants for known types: Grantor, Representative.
    
    # Grantor
    erd_grantor_scope = "$"
    req_erd_mappings.append(m("req_erd_g", erd_grantor_scope, "$.data.Envelope.Body.getProxyGrantorNameOrIDN.Request_ID", "Request", "request_id", "Req"))
    req_erd_mappings.append(m("req_erd_g", erd_grantor_scope, "$.data.Envelope.Body.getProxyGrantorNameOrIDN.Search_nam", "Person", "full_name", "Subject", transform={"type": "trim"}))
    req_erd_mappings.append(m("req_erd_g", erd_grantor_scope, "$.data.Envelope.Body.getProxyGrantorNameOrIDN.Search_code", "Person", "rnokpp", "Subject"))
    
    req_variants.append({
        "variant_id": "request_erd_grantor_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.getProxyGrantorNameOrIDN"}
            ]
        },
        "mappings": req_erd_mappings
    })

    # Request JSON (RRP)
    req_rrp_mappings = []
    rrp_scope = "$"
    req_rrp_mappings.append(m("req_rrp", rrp_scope, "$.data.entity", "Request", "service_code", "Req")) # No ID, map entity/service
    req_rrp_mappings.append(m("req_rrp", rrp_scope, "$.data.searchParams.subjectSearchInfo.sbjName", "Person", "full_name", "Subject"))
    req_rrp_mappings.append(m("req_rrp", rrp_scope, "$.data.searchParams.subjectSearchInfo.sbjCode", "Person", "rnokpp", "Subject"))

    req_variants.append({
        "variant_id": "request_rrp_json_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.data.entity", "value": "rrpExch_external"}
            ]
        },
        "mappings": req_rrp_mappings
    })

    # Request XML (SR - Successions/Inheritance Registry)
    req_sr_mappings = []
    sr_scope = "$"
    req_sr_mappings.append(m("req_sr", sr_scope, "$.data.Envelope.Body.GetInheritedPropertiesByNameOrIDN.Request_ID", "Request", "request_id", "Req"))
    req_sr_mappings.append(m("req_sr", sr_scope, "$.data.Envelope.Body.GetInheritedPropertiesByNameOrIDN.Code", "Person", "rnokpp", "Subject"))

    req_variants.append({
        "variant_id": "request_sr_v1",
        "match_predicate": {
            "all": [
                {"type": "json_exists", "path": "$.data.Envelope.Body.GetInheritedPropertiesByNameOrIDN"}
            ]
        },
        "mappings": req_sr_mappings
    })

    # Request XML (DRFO)
    req_drfo_mappings = []
    drfo_body = "$.data.Envelope.Body.InfoIncomeSourcesDRFO2QueryRequest"
    # Use Header ID for consistency
    req_drfo_mappings.append(m("req_drfo", "$", "$.data.Envelope.Header.id", "Request", "request_id", "Req"))
    
    # Subject Person
    req_drfo_mappings.append(m("req_drfo_subj", "$", f"{drfo_body}.person.RNOKPP", "Person", "rnokpp", "Subject"))
    req_drfo_mappings.append(m("req_drfo_subj", "$", f"{drfo_body}.person.last_name", "Person", "last_name", "Subject"))
    req_drfo_mappings.append(m("req_drfo_subj", "$", f"{drfo_body}.person.first_name", "Person", "first_name", "Subject"))
    req_drfo_mappings.append(m("req_drfo_subj", "$", f"{drfo_body}.person.middle_name", "Person", "middle_name", "Subject"))
    req_drfo_mappings.append(m("req_drfo_subj", "$", f"{drfo_body}.person.date_birth", "Person", "birth_date", "Subject"))

    req_variants.append({
        "variant_id": "request_drfo_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.data.Envelope.Header.service.serviceCode", "value": "InfoIncomeSourcesDRFO2Query"}
            ]
        },
        "mappings": req_drfo_mappings
    })

    # Request QueryString (Parsed by Adapter)
    req_qs_mappings = []
    qs_scope = "$.data"
    # No Request ID usually in params? Map content as ID if needed or skip Request Node if ID missing?
    # Ideally link Person.
    # User file snippet: date_search=... rnokpp=...
    # Let's map Person.
    req_qs_mappings.append(m("req_qs_subj", qs_scope, "$.last_name", "Person", "last_name", "Subject"))
    req_qs_mappings.append(m("req_qs_subj", qs_scope, "$.first_name", "Person", "first_name", "Subject"))
    req_qs_mappings.append(m("req_qs_subj", qs_scope, "$.middle_name", "Person", "middle_name", "Subject"))
    req_qs_mappings.append(m("req_qs_subj", qs_scope, "$.rnokpp", "Person", "rnokpp", "Subject"))
    req_qs_mappings.append(m("req_qs_subj", qs_scope, "$.date_birth", "Person", "birth_date", "Subject"))

    req_variants.append({
        "variant_id": "request_qs_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.meta.registry_code", "value": "REQUEST_QS"}
            ]
        },
        "mappings": req_qs_mappings
    })

    # Request DZK (Log Format)
    req_dzk_mappings = []
    # Just map Request node if possible, or empty mappings to avoid quarantine
    req_dzk_mappings.append(m("req_dzk", "$.data", "$.HEADER_Uxp-Service", "Request", "service_code", "Req")) # Dummy map

    req_variants.append({
        "variant_id": "request_dzk_v1",
        "match_predicate": {
            "all": [
                {"type": "json_equals", "path": "$.meta.registry_code", "value": "REQUEST_DZK"}
            ]
        },
        "mappings": req_dzk_mappings
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
        {"code": "COURT", "name": "Court Decisions", "variants": court_variants},
        {"code": "MVS", "name": "Ministry of Internal Affairs (Vehicles)", "variants": mvs_variants},
        {"code": "IDP", "name": "Internally Displaced Persons", "variants": idp_variants},
        {"code": "REQUEST", "name": "Traceability Requests", "variants": req_variants}
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
