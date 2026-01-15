import os
import sys
from datetime import datetime
from pymongo import MongoClient

# Ensure app is in python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from ingestion_job.app.core.settings import get_settings
from ingestion_job.app.models.schemas import (
    EntitySchema, EntityPropertySchema, Neo4jEntityConfig, IdentityKey, MergePolicy,
    RelationshipSchema, Neo4jRelConfig, RelEndpoints, CreationRule, RelWhen, RelBind, RelBindRef, RelCondition, RelPropertyMap, RelUniqueness,
    RegisterSchema, RegisterSchemaVariant, MatchPredicate, JsonPredicate, VariantMapping, MappingTarget, SchemaMatchConfig, CanonicalHeaderFields, VariantEmits
)

def init_schemas():
    settings = get_settings()
    if not settings.mongo_uri or not settings.mongo_db:
        print("MONGO_URI or MONGO_DB not set")
        return

    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    # Clean existing
    db.entity_schemas.delete_many({})
    db.relationship_schemas.delete_many({})
    db.register_schemas.delete_many({})

    print("Cleared existing schemas.")

    # -------------------------------------------------------------------------
    # 1. Entity Schemas
    # -------------------------------------------------------------------------

    # Person
    person_schema = EntitySchema(
        entity_name="Person",
        neo4j=Neo4jEntityConfig(
            labels=["Person"],
            primary_key="person_id",
            constraints=[{"type": "unique", "property": "person_id"}, {"type": "index", "property": "rnokpp"}]
        ),
        identity_keys=[
            IdentityKey(priority=1, when={"exists": ["rnokpp"]}, properties=["rnokpp"]),
            IdentityKey(priority=2, when={"exists": ["fullName", "birthDate"]}, properties=["fullName", "birthDate"])
        ],
        properties=[
            EntityPropertySchema(name="rnokpp", type="string", is_required=False, change_type="immutable", normalize=["trim"]),
            EntityPropertySchema(name="fullName", type="string", is_required=False, change_type="rarely_changed", normalize=["trim", "collapse_spaces"]),
            EntityPropertySchema(name="firstName", type="string", is_required=False, change_type="rarely_changed", normalize=["trim"]),
            EntityPropertySchema(name="lastName", type="string", is_required=False, change_type="rarely_changed", normalize=["trim"]),
            EntityPropertySchema(name="birthDate", type="date", is_required=False, change_type="immutable")
        ],
        merge_policy=MergePolicy()
    )

    # Vehicle
    vehicle_schema = EntitySchema(
        entity_name="Vehicle",
        neo4j=Neo4jEntityConfig(
            labels=["Vehicle"],
            primary_key="vehicle_id",
            constraints=[{"type": "unique", "property": "vehicle_id"}, {"type": "index", "property": "vin"}]
        ),
        identity_keys=[
            IdentityKey(priority=1, when={"exists": ["vin"]}, properties=["vin"]),
            IdentityKey(priority=2, when={"exists": ["plate"]}, properties=["plate"])
        ],
        properties=[
            EntityPropertySchema(name="vin", type="string", is_required=False, change_type="immutable", normalize=["trim", "upper"]),
            EntityPropertySchema(name="plate", type="string", is_required=False, change_type="rarely_changed", normalize=["trim", "upper", "collapse_spaces"]),
            EntityPropertySchema(name="make", type="string", is_required=False, change_type="rarely_changed"),
            EntityPropertySchema(name="model", type="string", is_required=False, change_type="rarely_changed"),
            EntityPropertySchema(name="year", type="int", is_required=False, change_type="immutable")
        ],
        merge_policy=MergePolicy()
    )

    # CivilEvent
    # Representing generic civil acts (Birth, Marriage, etc.) or just "CivilEvent"
    civil_event_schema = EntitySchema(
        entity_name="CivilEvent",
        neo4j=Neo4jEntityConfig(
            labels=["CivilEvent"],
            primary_key="event_id",
            constraints=[{"type": "unique", "property": "event_id"}, {"type": "index", "property": "actNumber"}]
        ),
        identity_keys=[
            IdentityKey(priority=1, when={"exists": ["actNumber"]}, properties=["actNumber"])
        ],
        properties=[
            EntityPropertySchema(name="actNumber", type="string", is_required=True, change_type="immutable", normalize=["trim"]),
            EntityPropertySchema(name="eventDate", type="date", is_required=False, change_type="immutable"),
            EntityPropertySchema(name="eventType", type="string", is_required=False, change_type="immutable"), # e.g. Birth, Marriage
            EntityPropertySchema(name="details", type="string", is_required=False, change_type="rarely_changed")
        ],
        merge_policy=MergePolicy()
    )

    db.entity_schemas.insert_many([
        person_schema.model_dump(),
        vehicle_schema.model_dump(),
        civil_event_schema.model_dump()
    ])
    print("Inserted Entity Schemas: Person, Vehicle, CivilEvent")

    # -------------------------------------------------------------------------
    # 2. Relationship Schemas
    # -------------------------------------------------------------------------

    # NAME: PERSON_HAS_VEHICLE (Maps to OWNS_VEHICLE requirement)
    rel_owns_vehicle = RelationshipSchema(
        relationship_name="PERSON_HAS_VEHICLE",
        neo4j=Neo4jRelConfig(type="OWNS_VEHICLE", from_label="Person", to_label="Vehicle"),
        endpoints=RelEndpoints(from_entity="Person", to_entity="Vehicle"),
        creation_rules=[
            CreationRule(
                rule_id="default_ownership",
                when=RelWhen(all=[
                    RelCondition(type="entity_exists", entity_ref="OwnerPerson"),
                    RelCondition(type="entity_exists", entity_ref="OwnedVehicle")
                ]),
                bind=RelBind(
                    **{"from": RelBindRef(entity_ref="OwnerPerson"), "to": RelBindRef(entity_ref="OwnedVehicle")}
                ),
                properties=[
                    RelPropertyMap(name="source", value="registry")
                ]
            )
        ],
        uniqueness=RelUniqueness(keys=["from.person_id", "to.vehicle_id", "neo4j.type"])
    )

    # NAME: PERSON_HAS_CIVIL_EVENT
    rel_civil_event = RelationshipSchema(
        relationship_name="PERSON_HAS_CIVIL_EVENT",
        neo4j=Neo4jRelConfig(type="HAS_CIVIL_EVENT", from_label="Person", to_label="CivilEvent"),
        endpoints=RelEndpoints(from_entity="Person", to_entity="CivilEvent"),
        creation_rules=[
            CreationRule(
                rule_id="participant_link",
                when=RelWhen(all=[
                    RelCondition(type="entity_exists", entity_ref="SubjectPerson"),
                    RelCondition(type="entity_exists", entity_ref="TheEvent")
                ]),
                bind=RelBind(
                    **{"from": RelBindRef(entity_ref="SubjectPerson"), "to": RelBindRef(entity_ref="TheEvent")}
                ),
                properties=[
                    RelPropertyMap(name="role", value="subject")
                ]
            )
        ],
        uniqueness=RelUniqueness(keys=["from.person_id", "to.event_id", "neo4j.type"])
    )

    # NAME: PARENT_OF
    rel_parent_of = RelationshipSchema(
        relationship_name="PARENT_OF",
        neo4j=Neo4jRelConfig(type="PARENT_OF", from_label="Person", to_label="Person"),
        endpoints=RelEndpoints(from_entity="Person", to_entity="Person"),
        creation_rules=[
            CreationRule(
                rule_id="parent_child_link",
                when=RelWhen(all=[
                    RelCondition(type="entity_exists", entity_ref="ParentPerson"),
                    RelCondition(type="entity_exists", entity_ref="ChildPerson")
                ]),
                bind=RelBind(
                    **{"from": RelBindRef(entity_ref="ParentPerson"), "to": RelBindRef(entity_ref="ChildPerson")}
                ),
                properties=[]
            )
        ],
        uniqueness=RelUniqueness(keys=["from.person_id", "to.person_id", "neo4j.type"])
    )

    db.relationship_schemas.insert_many([
        rel_owns_vehicle.model_dump(),
        rel_civil_event.model_dump(),
        rel_parent_of.model_dump()
    ])
    print("Inserted Relationship Schemas: PERSON_HAS_VEHICLE, PERSON_HAS_CIVIL_EVENT, PARENT_OF")

    # -------------------------------------------------------------------------
    # 3. Register Schemas (Registry Mapping)
    # -------------------------------------------------------------------------
    
    # We need a schema that matches the 'answer.xml' structure and maps to the entities above.
    # The XML has:
    # <tns:SubjectDetail2ExtResponse> ... <tns:Subject> ...
    # Within Subject:
    #  <tns:names><tns:name> ... </tns:name></tns:names>  (Company name, but let's treat as Person/Org for demo or extract founders as Person)
    #  <tns:founders><tns:founder> ... <tns:name> ... <tns:code> ... </tns:founder></tns:founders>
    #
    # Wait, the XML provided in `data/nabu_data/890-ТМ-Д/В-2025-1615-034-TR7/answer.xml` seems to be about Companies ("ВІННИЦЯ-ПРОМ-ІНВЕСТ") and their founders ("СВІФТ МАГДАЛЕНА СИГІЗМУНДОВНА").
    # The requirements asked for Person, Vehicle, CivilEvent.
    # The XML provided doesn't strictly look like a BirthAct or Vehicle registry.
    # BUT, I must implement what's declared in docs AND what is needed for the XML if I want to test it.
    #
    # Let's see if there are other XMLs. The user said "Input: Raw files...".
    # I should try to map what I see in `answer.xml` to `Person` (Founders) and maybe map the Company to something or ignore it if `Company` schema is not requested.
    # I will map Founders to `Person`.
    # I will assume `answer.xml` corresponds to `Test_ICS_cons` (from header).
    
    reg_schema = RegisterSchema(
        registry_code="Test_ICS_cons",
        service_code="2_MJU_EDR_prod", # From XML: <id:subsystemCode>2_MJU_EDR_prod</id:subsystemCode>
        method_code="SubjectDetail2Ext", # From XML: <id:serviceCode>SubjectDetail2Ext</id:serviceCode>
        schema_match=SchemaMatchConfig(
            canonical_header_fields=CanonicalHeaderFields()
        ),
        variants=[
            RegisterSchemaVariant(
                variant_id="v1_edr_founders",
                match_predicate=MatchPredicate(
                    all=[
                        JsonPredicate(type="json_exists", path="$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject"),
                    ]
                ),
                mappings=[
                    # Map Founders to Person
                    VariantMapping(
                        mapping_id="map_founders",
                        scope={"foreach": "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject.founders.founder[*]"},
                        source={}, 
                        targets=[
                            MappingTarget(entity="Person", property="fullName", entity_ref="FounderPerson"),
                            MappingTarget(entity="Person", property="rnokpp", entity_ref="FounderPerson")
                        ],
                        # In the loop, we map properties directly
                    )
                ],
                emits=VariantEmits(entities=["Person"])
            )
        ]
    )
    
    # We need to specify the property mapping details for the Mapping above.
    # Wait, `VariantMapping` in `schemas.py` has `source` as Dict[str, str].
    # But usually we need per-target source path.
    # My `pipeline.py` logic (and the `schemas.md` example) assumes:
    # "source": { "json_path": "$.actNumber" } applies to ALL targets.
    # But here I have `fullName` coming from `name` and `rnokpp` coming from `code`.
    # So I need TWO mappings for the same scope?
    # Yes.
    
    # Refined Mappings for Founders:
    
    # Mapping 1: Full Name
    m1 = VariantMapping(
        mapping_id="founder_name",
        scope={"foreach": "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]"}, # Assuming multiple Subjects
        # Wait, XML structure: Envelope -> Body -> SubjectDetail2ExtResponse -> Subject (list?)
        # `_xml_to_dict` usually handles lists.
        # Let's assume Subject is a list or single.
        # JSONPath `..Subject[*].founders.founder[*]` should work if I normalize list handling.
        
        source={"json_path": "$.name"},
        targets=[MappingTarget(entity="Person", property="fullName", entity_ref="FounderPerson")]
    )
    
    # Mapping 2: RNOKPP
    m2 = VariantMapping(
         mapping_id="founder_code",
         scope={"foreach": "$.data.Envelope.Body.SubjectDetail2ExtResponse.Subject[*].founders.founder[*]"},
         source={"json_path": "$.code"},
         targets=[MappingTarget(entity="Person", property="rnokpp", entity_ref="FounderPerson")]
    )
    
    # Updating schema variant with correct mappings
    reg_schema.variants[0].mappings = [m1, m2]

    db.register_schemas.insert_one(reg_schema.model_dump())
    print("Inserted Register Schema: Test_ICS_cons")

if __name__ == "__main__":
    init_schemas()
