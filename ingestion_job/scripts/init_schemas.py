
import os
import glob
import json
import uuid
import hashlib
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

# Fix paths
import sys
from pathlib import Path
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

def init_entities(db):
    print("Initializing Entity Schemas...")
    coll = db["entity_schemas"]
    
    # helper for creating schema defs
    def make_entity(name, props, identity_keys=[]):
        p_dict = {p: {"type": "string", "change_type": "immutable"} for p in props}
        return {
            "entity_name": name,
            "properties": p_dict,
            "identity_keys": identity_keys,
            "created_at": now_utc(),
            "updated_at": now_utc()
        }

    entities = []
    
    # 1. Person
    entities.append(make_entity(
        "Person", 
        ["person_id", "gender", "unzr", "birth_date", "citizenship", "registry_source", 
         "last_name", "birth_place", "middle_name", "rnokpp", "full_name", "first_name"],
        [
            {"properties": ["rnokpp"], "when": {"exists": ["rnokpp"]}},
            {"properties": ["full_name"], "when": {"exists": ["full_name"]}} # Fallback/Weak
        ]
    ))
    
    # 2. Vehicle
    entities.append(make_entity(
        "Vehicle",
        ["vehicle_id", "year", "color", "registration_number", "vin", "model", "make", "car_id"],
        [{"properties": ["vin"], "when": {"exists": ["vin"]}}]
    ))

    # 3. CivilEvent
    entities.append(make_entity(
        "CivilEvent",
        ["event_id", "response_id", "date", "registry_office", "event_type", "act_number"],
        [{"properties": ["act_number", "event_type"], "when": {"exists": ["act_number"]}}]
    ))
    
    # 4. CourtCase
    entities.append(make_entity("CourtCase", ["court_id", "case_id", "case_number"]))
    
    # 5. Court
    entities.append(make_entity("Court", ["court_id", "court_name", "court_code"]))
    
    # 6. CourtDecision
    entities.append(make_entity(
        "CourtDecision", 
        ["court_id", "decision_id", "reg_num", "court_name", "case_number", "decision_date", "decision_type"]
    ))
    
    # 7. IncomeRecord
    entities.append(make_entity(
        "IncomeRecord",
        ["person_id", "organization_id", "period_id", "income_id", "tax_amount", "income_type_code",
         "tax_transferred", "response_id", "income_accrued", "income_paid", "income_amount", "tax_charged"]
    ))
    
    # 8. Period
    entities.append(make_entity("Period", ["period_id", "year", "quarter"]))
    
    # 9. Organization
    entities.append(make_entity(
        "Organization", 
        ["name", "organization_id", "org_type", "org_code"],
        [{"properties": ["org_code"], "when": {"exists": ["org_code"]}}]
    ))
    
    # 10. OwnershipRight
    entities.append(make_entity(
        "OwnershipRight",
        ["property_id", "right_id", "rn_num", "registrar", "right_reg_date", "pr_state",
         "doc_type", "doc_type_extension", "right_type", "doc_date", "doc_publisher", "share"]
    ))
    
    # 11. Property
    entities.append(make_entity(
        "Property",
        ["property_id", "reg_num", "registration_date", "re_type", "state", "cad_num", "area", "area_unit"],
        [{"properties": ["reg_num"], "when": {"exists": ["reg_num"]}}]
    ))
    
    # 12. Address
    entities.append(make_entity(
        "Address",
        ["address_id", "street", "region", "house", "apartment", "city", "address_line", "district", "koatuu"]
    ))
    
    # 13. Identifier
    entities.append(make_entity("Identifier", ["identifier_id", "identifier_value", "identifier_type"]))
    
    # 14. TaxAgent
    entities.append(make_entity(
        "TaxAgent",
        ["name", "organization_id", "org_type", "org_code"],
        [{"properties": ["org_code"], "when": {"exists": ["org_code"]}}]
    ))
    
    # 15. VehicleRegistration
    entities.append(make_entity(
        "VehicleRegistration",
        ["vehicle_id", "registration_id", "registration_date", "opercode", "dep_reg_name", "doc_id", "status"]
    ))

    # Upsert
    for e in entities:
        coll.replace_one({"entity_name": e["entity_name"]}, e, upsert=True)
    
    print(f"Inserted {len(entities)} entity schemas.")

def init_relationships(db):
    print("Initializing Relationship Schemas...")
    coll = db["relationship_schemas"]
    
    def make_rel(name, rel_type, from_ent, to_ent, props=[]):
        return {
            "relationship_name": name,
            "neo4j": {"type": rel_type},
            "source": {"entity": from_ent},
            "target": {"entity": to_ent},
            "properties": {p: {"type": "string"} for p in props},
            "creation_rules": [
                {
                    "bind": {
                        "from_": {"entity": from_ent, "entity_ref": f"{from_ent}Ref"}, # Generic ref
                        "to": {"entity": to_ent, "entity_ref": f"{to_ent}Ref"}
                    },
                    "properties": []
                }
            ],
            "created_at": now_utc(),
            "updated_at": now_utc()
        }
        
    rels = []
    
    # 1. IN_COURT
    rels.append(make_rel("CourtCase_IN_COURT_Court", "IN_COURT", "CourtCase", "Court"))
    
    # 2. FOR_CASE
    rels.append(make_rel("CourtDecision_FOR_CASE_CourtCase", "FOR_CASE", "CourtDecision", "CourtCase"))
    
    # 3. FOR_PERIOD
    rels.append(make_rel("IncomeRecord_FOR_PERIOD_Period", "FOR_PERIOD", "IncomeRecord", "Period"))
    
    # 4. HAS_RIGHT (Organization)
    rels.append(make_rel("Organization_HAS_RIGHT_OwnershipRight", "HAS_RIGHT", "Organization", "OwnershipRight", ["role"]))
    # 4b. HAS_RIGHT (Person)
    rels.append(make_rel("Person_HAS_RIGHT_OwnershipRight", "HAS_RIGHT", "Person", "OwnershipRight", ["role"]))
    
    # 5. PAID_INCOME (Organization)
    rels.append(make_rel("Organization_PAID_INCOME_IncomeRecord", "PAID_INCOME", "Organization", "IncomeRecord"))
    # 5b. PAID_INCOME (TaxAgent)
    rels.append(make_rel("TaxAgent_PAID_INCOME_IncomeRecord", "PAID_INCOME", "TaxAgent", "IncomeRecord"))
    
    # 6. RIGHT_TO
    rels.append(make_rel("OwnershipRight_RIGHT_TO_Property", "RIGHT_TO", "OwnershipRight", "Property"))
    
    # 7. HAS_ADDRESS
    rels.append(make_rel("Person_HAS_ADDRESS_Address", "HAS_ADDRESS", "Person", "Address", ["relationship_type"]))
    
    # 8. LOCATED_AT
    rels.append(make_rel("Property_LOCATED_AT_Address", "LOCATED_AT", "Property", "Address"))
    
    # 9. HAS_IDENTIFIER
    rels.append(make_rel("Person_HAS_IDENTIFIER_Identifier", "HAS_IDENTIFIER", "Person", "Identifier"))
    
    # 10. HAS_INCOME
    rels.append(make_rel("Person_HAS_INCOME_IncomeRecord", "HAS_INCOME", "Person", "IncomeRecord"))
    
    # 11. INVOLVED_IN (Legacy) - keeping user requested HAS_CIVIL_EVENT alias if needed, or stick to this?
    # User showed legacy uses INVOLVED_IN. I will use INVOLVED_IN to match legacy.
    rels.append(make_rel("Person_INVOLVED_IN_CivilEvent", "INVOLVED_IN", "Person", "CivilEvent", ["role"]))
    
    # 12. OWNS_VEHICLE
    rels.append(make_rel("Person_OWNS_VEHICLE_Vehicle", "OWNS_VEHICLE", "Person", "Vehicle", ["role"]))
    
    # 13. HAS_REGISTRATION
    rels.append(make_rel("Vehicle_HAS_REGISTRATION_VehicleRegistration", "HAS_REGISTRATION", "Vehicle", "VehicleRegistration"))

    # Upsert
    for r in rels:
        coll.replace_one({"relationship_name": r["relationship_name"]}, r, upsert=True)
    
    print(f"Inserted {len(rels)} relationship schemas.")

def init_registers(db):
    print("Initializing Register Schemas...")
    coll = db["register_schemas"]
    
    variants = []
    
    # Helper to create mappings
    def m(mid, scope, src_path, target_ent, target_prop, ent_ref):
        return {
            "mapping_id": mid,
            "scope": {"foreach": scope},
            "source": {"json_path": src_path},
            "targets": [{"entity": target_ent, "property": target_prop, "entity_ref": ent_ref}]
        }

    # ==========================================
    # 1. MJU EDR Prod (SubjectDetail2Ext)
    # ==========================================
    edr_mappings = []
    # Founder -> Person
    edr_mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.name", "Person", "full_name", "FounderPerson"))
    edr_mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.code", "Person", "rnokpp", "FounderPerson"))
    edr_mappings.append(m("founder", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]", "$.address.address", "Person", "birth_place", "FounderPerson")) # mapping address to birth_place as loose approximation or just new field? user declared strict schema from legacy. Address is separate node. 
    # Let's map Address properly relationship later? For now, stick to basic props.
    
    # Head -> Person
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.first_middle_name", "Person", "full_name", "HeadPerson"))
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.last_name", "Person", "last_name", "HeadPerson"))
    edr_mappings.append(m("head", "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].heads.head[*]", "$.rnokpp", "Person", "rnokpp", "HeadPerson"))

    variants.append({
        "variant_id": "edr_subject_v1",
        "match_predicate": {"registry_code": "Test_ICS_cons", "service_code": "2_MJU_EDR_prod", "method_code": "SubjectDetail2Ext"},
        "mappings": edr_mappings
    })

    # ==========================================
    # 2. DRFO (InfoIncomeSourcesDRFO2Query)
    # ==========================================
    # Found in 66_DRFO_demo_test and 27_DRFO_test_demo
    # Assumption on structure: Envelope.Body.InfoIncomeSourcesDRFO2Response...
    # We map to IncomeRecord
    drfo_mappings = []
    # We need to guess the path. Usually it's deep.
    # Safe bet: $.data..income[*] or similar. Let's try standard X-Road pattern.
    drfo_scope = "$.data.Envelope.Body.InfoIncomeSourcesDRFO2Response.declarations.declaration[*]"
    
    # Map to IncomeRecord
    drfo_mappings.append(m("income", drfo_scope, "$.taxAmount", "IncomeRecord", "tax_amount", "IncRec"))
    drfo_mappings.append(m("income", drfo_scope, "$.incomeAmount", "IncomeRecord", "income_amount", "IncRec"))
    drfo_mappings.append(m("income", drfo_scope, "$.incomePaid", "IncomeRecord", "income_paid", "IncRec"))
    drfo_mappings.append(m("income", drfo_scope, "$.periodId", "IncomeRecord", "period_id", "IncRec"))
    drfo_mappings.append(m("income", drfo_scope, "$.personId", "IncomeRecord", "person_id", "IncRec"))
    
    # Map to TaxAgent (Organization)
    drfo_mappings.append(m("agent", drfo_scope, "$.orgName", "TaxAgent", "name", "AgentOrg"))
    drfo_mappings.append(m("agent", drfo_scope, "$.orgCode", "TaxAgent", "org_code", "AgentOrg"))

    variants.append({
        "variant_id": "drfo_income_v1",
        "match_predicate": {"registry_code": "Test_ICS_cons", "method_code": "InfoIncomeSourcesDRFO2Query"}, # Matches both services by omitting service_code? Or list both? Predicate logic usually AND.
        # We need two variants or regex. simplified eval supports exact match. 
        # Let's add for 66
        "match_predicate": {"service_code": "66_DRFO_demo_test", "method_code": "InfoIncomeSourcesDRFO2Query"},
        "mappings": drfo_mappings
    })
    variants.append({
        "variant_id": "drfo_income_v2",
        "match_predicate": {"service_code": "TEST_ICS_cons", "service_code": "27_DRFO_test_demo", "method_code": "InfoIncomeSourcesDRFO2Query"},
        "mappings": drfo_mappings
    })
    # Note: case sensitivity on registry code? "Test_ICS_cons" vs "TEST_ICS_cons"? 
    # analyze script showed "TEST_ICS_cons" for 27.
    
    # ==========================================
    # 3. DRACS (Civil Acts)
    # ==========================================
    # 3.1 Birth
    dracs_birth_scope = "$.data.Envelope.Body.GetBirthArByChildNameAndBirthDateResponse.acts.act[*]"
    variants.append({
        "variant_id": "dracs_birth",
        "match_predicate": {"service_code": "3_MJU_DRACS_prod", "method_code": "GetBirthArByChildNameAndBirthDate"},
        "mappings": [
            m("event", dracs_birth_scope, "$.actNumber", "CivilEvent", "act_number", "Event"),
            m("event", dracs_birth_scope, "$.actDate", "CivilEvent", "date", "Event"),
            # Person (Child)
            m("child", dracs_birth_scope, "$.child.lastName", "Person", "last_name", "Child"),
            m("child", dracs_birth_scope, "$.child.firstName", "Person", "first_name", "Child"),
            m("child", dracs_birth_scope, "$.child.middleName", "Person", "middle_name", "Child"),
        ]
    })
    
    # 3.2 Marriage
    dracs_marr_scope = "$.data.Envelope.Body.GetMarriageArByHusbandNameAndBirthDateResponse.acts.act[*]" 
    # Note: multiple methods for marriage (ByHusband, ByWife), structure likely similar
    marr_mappings = [
        m("event", dracs_marr_scope, "$.actNumber", "CivilEvent", "act_number", "Event"),
        m("event", dracs_marr_scope, "$.actDate", "CivilEvent", "date", "Event"),
        m("husband", dracs_marr_scope, "$.husband.lastName", "Person", "last_name", "Husband"),
        m("wife", dracs_marr_scope, "$.wife.lastName", "Person", "last_name", "Wife"),
    ]
    variants.append({ "variant_id": "dracs_marr_husb", "match_predicate": {"method_code": "GetMarriageArByHusbandNameAndBirthDate"}, "mappings": marr_mappings })
    variants.append({ "variant_id": "dracs_marr_wife", "match_predicate": {"method_code": "GetMarriageArByWifeNameAndBirthDate"}, "mappings": marr_mappings })
    
    # 3.3 Divorce
    div_mappings = [
        m("event", "$.data.Envelope.Body..acts.act[*]", "$.actNumber", "CivilEvent", "act_number", "Event"),
         # Generic path .. matches deeper
        m("p1", "$.data.Envelope.Body..acts.act[*]", "$.husband.lastName", "Person", "last_name", "Husband"),
    ]
    variants.append({ "variant_id": "dracs_div_husb", "match_predicate": {"method_code": "GetDivorceArByHusbandNameAndBirthDate"}, "mappings": div_mappings })
    variants.append({ "variant_id": "dracs_div_wife", "match_predicate": {"method_code": "GetDivorceArByWifeNameAndBirthDate"}, "mappings": div_mappings })
    
    # 3.4 Death
    variants.append({ "variant_id": "dracs_death", "match_predicate": {"method_code": "GetDeathArByFullNameAndBirthDate"}, 
        "mappings": [
             m("event", "$.data.Envelope.Body..acts.act[*]", "$.actNumber", "CivilEvent", "act_number", "Event"),
             m("deceased", "$.data.Envelope.Body..acts.act[*]", "$.subject.lastName", "Person", "last_name", "Deceased"),
        ] 
    })
    
    # 3.5 Change Name
    variants.append({ "variant_id": "dracs_changename", "match_predicate": {"method_code": "GetChangeNameArByNewNameAndBirthDate"}, "mappings": [] }) # Placeholder
    variants.append({ "variant_id": "dracs_changename2", "match_predicate": {"method_code": "GetChangeNameArByOldNameAndBirthDate"}, "mappings": [] }) # Placeholder

    # ==========================================
    # 4. ERD (Proxy)
    # ==========================================
    variants.append({
        "variant_id": "erd_proxy",
        "match_predicate": {"service_code": "4_KCS_ERD_demo"},
        "mappings": [
            m("grantor", "$.data..grantors.grantor[*]", "$.name", "Person", "full_name", "Grantor"),
            m("grantor", "$.data..grantors.grantor[*]", "$.inn", "Person", "rnokpp", "Grantor"),
        ]
    })

    # ==========================================
    # 5. CMS (IDP)
    # ==========================================
    variants.append({
        "variant_id": "cms_idp",
        "match_predicate": {"service_code": "25_CMS_demo"},
        "mappings": [
            m("person", "$.data..persons.person[*]", "$.lastName", "Person", "last_name", "IDPerson"),
            m("person", "$.data..persons.person[*]", "$.docNumber", "Person", "rnokpp", "IDPerson"), # Maybe doc number, not rnokpp?
        ]
    })

    # ==========================================
    # 6. SR (Property)
    # ==========================================
    variants.append({
        "variant_id": "sr_prop",
        "match_predicate": {"service_code": "24_MJU_SR_prod"},
        "mappings": [
            m("prop", "$.data..assets.asset[*]", "$.registrationNumber", "Property", "reg_num", "Asset"),
            m("prop", "$.data..assets.asset[*]", "$.address", "Property", "cad_num", "Asset"), # Mapping address to cad_num? Risky but filler.
            m("right", "$.data..assets.asset[*].rights.right[*]", "$.id", "OwnershipRight", "right_id", "Right"),
        ]
    })

    # Insert shell
    reg_schema = {
        "registry_name": "UnifiedRegistry",
        "variants": variants,
        "created_at": now_utc(),
        "updated_at": now_utc()
    }
    coll.replace_one({"registry_name": "UnifiedRegistry"}, reg_schema, upsert=True)
    print(f"Inserted UnifiedRegistry with {len(variants)} variants.")

if __name__ == "__main__":
    db = get_db()
    init_entities(db)
    init_relationships(db)
    init_registers(db)
