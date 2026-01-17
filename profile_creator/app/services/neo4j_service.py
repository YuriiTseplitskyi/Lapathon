from neo4j import GraphDatabase
from app.core.settings import settings
from app.models.domain import PersonProfile, Vehicle, Property, Income, FamilyMember, NameHistory, CourtCase, AssociatedAddress, CompanyIncome

QUERY = """
MATCH (p:Person {rnokpp: $rnokpp})

// 1. Попередні ПІБ (фільтруємо тільки зміни)
OPTIONAL MATCH (p)-[:INVOLVED_IN]->(ce:CivilEvent)
WHERE ce.event_type CONTAINS 'Зміна' OR ce.old_last_name IS NOT NULL
WITH p, ce ORDER BY ce.date DESC
WITH p, collect(DISTINCT {
    old_name: ce.old_last_name, 
    event_date: ce.date, 
    event_type: ce.event_type
}) AS name_history_raw

// 1. Пошук адрес
OPTIONAL MATCH (p)-[:HAS_ADDRESS]->(addr:Address)
WITH p, collect(DISTINCT addr {.*}) AS addresses

// 2. Пошук доходів від компаній (агрегація за весь час)
OPTIONAL MATCH (org:Organization)-[:PAID_INCOME]->(inc:IncomeRecord)<-[:HAS_INCOME]-(p)
WITH p, addresses, org, sum(toFloat(inc.income_amount)) AS total_income
WITH p, addresses, collect(DISTINCT {
    name: org.name,
    edrpou: org.org_code,
    total_amount: total_income
}) AS companies

// 2. Транспорт (беремо все, що має реєстраційний номер)
OPTIONAL MATCH (p)-[rv:OWNS_VEHICLE]->(v:Vehicle)

// 3. Нерухомість (через OwnershipRight та Address)
OPTIONAL MATCH (p)-[:HAS_RIGHT]->(or:OwnershipRight)-[:RIGHT_TO]->(prop:Property)
OPTIONAL MATCH (prop)-[:LOCATED_AT]->(addr:Address)

// 4. Доходи (через TaxAgent та Period)
OPTIONAL MATCH (p)-[:HAS_INCOME]->(inc:IncomeRecord)-[:FOR_PERIOD]->(per:Period)
OPTIONAL MATCH (agent:TaxAgent {organization_id: inc.organization_id})
OPTIONAL MATCH (p)-[:INVOLVED_IN]->(ce:CivilEvent)<-[ii:INVOLVED_IN]-(relative:Person)
WHERE p <> relative // Виключаємо саму особу

// 5. Суди
OPTIONAL MATCH (p)-[:INVOLVED_IN]->(cd:CourtDecision)-[:FOR_CASE]->(cc:CourtCase)

RETURN p {.*} AS person, 
       collect(DISTINCT v {.*}) AS vehicles,
       collect(DISTINCT {
            re_type: prop.re_type, area: prop.area, area_unit: prop.area_unit,
            address: addr.city + ", " + addr.address_line,
            share: or.share, right_type: or.right_type
        }) AS properties,
    
        collect(DISTINCT {
            amount: inc.income_amount, source: agent.name, 
            year: per.year, type_code: inc.income_type_code
        }) AS incomes,
            
        collect(DISTINCT {
            case_num: cc.case_number, decision_type: cd.decision_type, 
            decision_date: cd.decision_date, court_name: cd.court_name
        }) AS court_cases,

       collect(DISTINCT {
        full_name: relative.full_name,
        rnokpp: relative.rnokpp,
        registry_office: ce.registry_office,
        role: ii.role // Хто цей родич: "Дружина", "Дитина" тощо
        }) AS family,

        addresses, companies
"""

class Neo4jService:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI, 
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def get_profile(self, rnokpp: str) -> PersonProfile | None:
        with self.driver.session() as session:
            result = session.run(QUERY, rnokpp=rnokpp)
            record = result.single()

            if not record:
                return None

            data = record.data()

            print(f"data: {data}")
            
            vehicles = [Vehicle(**v) for v in data['vehicles'] if v.get('registration_number')]

            family = []
            for f in data['family']:
                if f.get('full_name'):
                    role_str = f.get('role', '')
                    f['registry_office'] = f.get('registry_office', '')
                    if role_str == "father":
                        role_str = "чоловік"
                    elif role_str == "mother":
                        role_str = "дружина"
                    elif role_str == "child":
                        role_str = "дитина"
                    f['role_str'] = role_str
                    family.append(FamilyMember(**f))

            current_last_name = data['person'].get('last_name')
            name_history = []
            for h in (data.get('name_history') or []):
                if h.get('old_name') and h['old_name'] != current_last_name:
                    name_history.append(NameHistory(**h))
            
            properties = [Property(**p) for p in data['properties'] if p.get('re_type')]
            
            incomes = [Income(**i) for i in data['incomes'] if i.get('amount') is not None]
            
            court_cases = [CourtCase(**c) for c in data['court_cases'] if c.get('case_num')]
            
            addresses = [
                AssociatedAddress(
                    house=a.get('house', ''),
                    region=a.get('region', ''),
                    appartment=a.get('appartment', ''),
                    street=a.get('street', '')
                ) for a in data.get('addresses', []) if a.get('street')
            ]

            companies = [
                CompanyIncome(
                    name=c.get('name', 'Невідома організація'),
                    edrpou=c.get('edrpou', '---'),
                    total_amount=float(c.get('total_amount', 0))
                ) for c in data.get('companies', []) if c.get('total_amount', 0) > 0
            ]


            return PersonProfile(
                **data['person'],
                vehicles=vehicles,
                properties=properties,
                incomes=incomes,
                court_cases=court_cases,
                family=family,
                name_history=name_history,
                addresses=addresses,
                companies=companies
            )