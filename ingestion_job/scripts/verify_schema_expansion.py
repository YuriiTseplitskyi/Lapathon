import os
import sys
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Setup path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def verify_schema_expansion():
    print("🔍 Verifying Schema Expansion...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # 1. Services
        svc_count = session.run("MATCH (s:Service) RETURN count(s) as c").single()['c']
        print(f"✅ Services found: {svc_count}")
        if svc_count > 0:
             sample_svc = session.run("MATCH (s:Service) RETURN s.code, s.member_code LIMIT 1").single()
             print(f"   Sample SVC: Code={sample_svc['s.code']}, Member={sample_svc['s.member_code']}")

        # 2. PowerOfAttorney
        poa_count = session.run("MATCH (p:PowerOfAttorney) RETURN count(p) as c").single()['c']
        print(f"✅ PowerOfAttorney found: {poa_count}")
        if poa_count > 0:
            sample_poa = session.run("MATCH (p:PowerOfAttorney) RETURN p.reg_number, p.date, p.status LIMIT 1").single()
            print(f"   Sample PoA: Reg#{sample_poa['p.reg_number']}, Date={sample_poa['p.date']}")

        # 3. NotarialBlank
        blank_count = session.run("MATCH (n:NotarialBlank) RETURN count(n) as c").single()['c']
        print(f"✅ NotarialBlank found: {blank_count}")
        if blank_count > 0:
            sample_blank = session.run("MATCH (n:NotarialBlank) RETURN n.series, n.number LIMIT 1").single()
            print(f"   Sample Blank: {sample_blank['n.series']} {sample_blank['n.number']}")

        # 4. IncomeRecord
        inc_count = session.run("MATCH (i:IncomeRecord) RETURN count(i) as c").single()['c']
        print(f"✅ IncomeRecord found: {inc_count}")
        if inc_count > 0:
             sample_inc = session.run("MATCH (i:IncomeRecord) RETURN i.income_accrued, i.year LIMIT 1").single()
             print(f"   Sample Income: {sample_inc['i.income_accrued']} ({sample_inc['i.year']})")

        # 5. Organization
        org_count = session.run("MATCH (o:Organization) RETURN count(o) as c").single()['c']
        print(f"✅ Organization found: {org_count}")

        if org_count > 0:
             sample_org = session.run("MATCH (o:Organization) RETURN o.name LIMIT 1").single()
             print(f"   Sample Org: {sample_org['o.name']}")

        # 6. BirthCertificate
        bc_count = session.run("MATCH (b:BirthCertificate) RETURN count(b) as c").single()['c']
        print(f"✅ BirthCertificate found: {bc_count}")
        if bc_count > 0:
             sample_bc = session.run("MATCH (b:BirthCertificate) RETURN b.series, b.number, b.issue_date LIMIT 1").single()
             print(f"   Sample BC: {sample_bc['b.series']} {sample_bc['b.number']} ({sample_bc['b.issue_date']})")

        # 7. Relationships
        rels = session.run("""
            MATCH ()-[r]->() 
            WHERE type(r) IN ['GRANTED', 'REPRESENTATIVE_IN', 'USES_BLANK', 'USED_SERVICE', 'PAID_INCOME', 'HAS_INCOME', 'HAS_CERTIFICATE', 'PARENT_OF'] 
            RETURN type(r) as type, count(r) as c
        """)
        print("\nRelationships:")
        for record in rels:
            print(f"   {record['type']}: {record['c']}")

    driver.close()

if __name__ == "__main__":
    verify_schema_expansion()
