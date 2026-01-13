#!/usr/bin/env python3
"""neo4j_load_from_csv.py

Entity-only Neo4j loader for NABU CSV exports.

This script loads normalized CSV files produced by your ETL (e.g. `nabu_to_csv_fixed.py`)
into Neo4j using the Bolt driver (works with Neo4j Aura).

IMPORTANT
---------
- This loader intentionally does NOT create Request/Response/ResponseRaw nodes.
- It loads ONLY entities + relationships between those entities.

Requirements
------------
    pip install neo4j

Usage
-----
1) Edit the config placeholders below (NEO4J_URI, NEO4J_PASSWORD, CSV_DIR).
2) Run:

    python3 neo4j_load_from_csv.py

Notes
-----
Neo4j Aura cannot access your local filesystem for LOAD CSV, so this script pushes
rows via Bolt using UNWIND batching.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


# ==============================
# CONFIG — EDIT THESE
# ==============================

# Neo4j connection (placeholders — fill them in)
NEO4J_URI = "neo4j+ssc://"  # must be neo4j+ssc:// for Aura, won't work with neo4j:// or neo4j+s://
NEO4J_USER = "neo4j" 
NEO4J_PASSWORD = ""  

# Folder produced by the ETL (contains person.csv, income_record.csv, ...)
CSV_DIR = "csv_out"  # or absolute path

# Batch size for UNWIND writes
BATCH_SIZE = 1000

# Safety switches
CLEAR_DB = True
DRY_RUN = False  # True = don't connect to Neo4j; just validate CSV presence + row counts


# ==============================
# Helpers
# ==============================


def clean_value(v: Optional[str]) -> Optional[Any]:
    """Convert CSV string values into Python values.

    - empty string -> None
    - keep other values as-is (strings)

    We intentionally DO NOT auto-cast numbers to avoid breaking IDs with leading zeros.
    """

    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def read_csv_rows(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {k: clean_value(v) for k, v in row.items()}


def chunked(it: Iterable[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    buf: List[Dict[str, Any]] = []
    for row in it:
        buf.append(row)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def csv_path(csv_dir: Path, name: str) -> Path:
    return csv_dir / f"{name}.csv"


def exists(csv_dir: Path, name: str) -> bool:
    return csv_path(csv_dir, name).exists()


def count_csv_rows(path: Path) -> int:
    """Count data rows (excluding header)."""
    with path.open("r", encoding="utf-8", newline="") as f:
        n = -1
        for n, _ in enumerate(f):
            pass
    return max(0, n)


# ==============================
# Loader
# ==============================


@dataclass
class LoaderConfig:
    uri: str = NEO4J_URI
    user: str = NEO4J_USER
    password: str = NEO4J_PASSWORD
    csv_dir: str = CSV_DIR
    batch_size: int = BATCH_SIZE
    clear_db: bool = CLEAR_DB
    dry_run: bool = DRY_RUN


class Neo4jEntityCsvLoader:
    def __init__(self, cfg: LoaderConfig):
        self.cfg = cfg
        self.csv_dir = Path(cfg.csv_dir).expanduser().resolve()
        if not self.csv_dir.exists():
            raise FileNotFoundError(f"CSV_DIR not found: {self.csv_dir}")

        self.driver = None
        if not cfg.dry_run:
            try:
                from neo4j import GraphDatabase  # type: ignore
            except ModuleNotFoundError as e:
                raise SystemExit(
                    "neo4j python driver is not installed. Install it with: pip install neo4j"
                ) from e
            self.driver = GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password))

    def close(self) -> None:
        if self.driver is not None:
            self.driver.close()

    # ---------- DB setup ----------

    def clear_db(self) -> None:
        if not self.driver:
            return
        logging.info("Clearing Neo4j database (DETACH DELETE)…")
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))

    def create_constraints(self) -> None:
        if not self.driver:
            return

        logging.info("Creating constraints (IF NOT EXISTS)…")

        stmts = [
            # Core
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.person_id IS UNIQUE",
            "CREATE CONSTRAINT identifier_id IF NOT EXISTS FOR (i:Identifier) REQUIRE i.identifier_id IS UNIQUE",
            "CREATE CONSTRAINT address_id IF NOT EXISTS FOR (a:Address) REQUIRE a.address_id IS UNIQUE",
            "CREATE CONSTRAINT org_id IF NOT EXISTS FOR (o:Organization) REQUIRE o.organization_id IS UNIQUE",
            "CREATE CONSTRAINT period_id IF NOT EXISTS FOR (t:Period) REQUIRE t.period_id IS UNIQUE",
            "CREATE CONSTRAINT income_id IF NOT EXISTS FOR (ir:IncomeRecord) REQUIRE ir.income_id IS UNIQUE",
            "CREATE CONSTRAINT property_id IF NOT EXISTS FOR (pr:Property) REQUIRE pr.property_id IS UNIQUE",
            "CREATE CONSTRAINT right_id IF NOT EXISTS FOR (rr:OwnershipRight) REQUIRE rr.right_id IS UNIQUE",
            # Added entities
            "CREATE CONSTRAINT vehicle_id IF NOT EXISTS FOR (v:Vehicle) REQUIRE v.vehicle_id IS UNIQUE",
            "CREATE CONSTRAINT veh_reg_id IF NOT EXISTS FOR (vr:VehicleRegistration) REQUIRE vr.registration_id IS UNIQUE",
            "CREATE CONSTRAINT civil_event_id IF NOT EXISTS FOR (ce:CivilEvent) REQUIRE ce.event_id IS UNIQUE",
            "CREATE CONSTRAINT court_id IF NOT EXISTS FOR (c:Court) REQUIRE c.court_id IS UNIQUE",
            "CREATE CONSTRAINT court_case_id IF NOT EXISTS FOR (cc:CourtCase) REQUIRE cc.case_id IS UNIQUE",
            "CREATE CONSTRAINT court_decision_id IF NOT EXISTS FOR (cd:CourtDecision) REQUIRE cd.decision_id IS UNIQUE",
            "CREATE CONSTRAINT service_code IF NOT EXISTS FOR (sv:RegistryService) REQUIRE sv.service_code IS UNIQUE",
        ]

        with self.driver.session() as session:
            for stmt in stmts:
                session.execute_write(lambda tx, s=stmt: tx.run(s))

    # ---------- Generic batch writer ----------

    def _write_unwind(self, cypher: str, rows: List[Dict[str, Any]]) -> None:
        if not self.driver:
            return
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run(cypher, rows=rows))

    # ---------- CSV checks ----------

    def validate_csv_presence(self) -> None:
        expected = [
            # Nodes
            "registry_service",
            "person",
            "identifier",
            "address",
            "organization",
            "period",
            "income_record",
            "property",
            "ownership_right",
            "vehicle",
            "vehicle_registration",
            "civil_event",
            "court",
            "court_case",
            "court_decision",
            # Relationship tables
            "person_identifier",
            "person_address",
            "address_property",
            "person_property_right",
            "organization_property_right",
            "person_vehicle",
            "person_civil_event",
        ]

        logging.info("CSV folder: %s", self.csv_dir)
        present = 0
        for name in expected:
            fp = csv_path(self.csv_dir, name)
            if fp.exists():
                present += 1
                logging.info("Found %-28s rows=%d", f"{name}.csv", count_csv_rows(fp))
            else:
                logging.info("Missing %-28s (skipping)", f"{name}.csv")
        logging.info("CSV presence: %d/%d listed files found", present, len(expected))

    # ---------- Load nodes ----------

    def load_registry_services(self) -> int:
        name = "registry_service"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (s:RegistryService {service_code: row.service_code})
        SET s += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded RegistryService: %d", total)
        return total

    def load_persons(self) -> int:
        name = "person"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (p:Person {person_id: row.person_id})
        SET p += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Person: %d", total)
        return total

    def load_identifiers(self) -> int:
        name = "identifier"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (i:Identifier {identifier_id: row.identifier_id})
        SET i += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Identifier: %d", total)
        return total

    def load_addresses(self) -> int:
        name = "address"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (a:Address {address_id: row.address_id})
        SET a += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Address: %d", total)
        return total

    def load_organizations(self) -> int:
        name = "organization"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (o:Organization {organization_id: row.organization_id})
        SET o += row
        FOREACH (_ IN CASE WHEN row.org_type = 'tax_agent' THEN [1] ELSE [] END |
          SET o:TaxAgent
        )
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Organization: %d", total)
        return total

    def load_periods(self) -> int:
        name = "period"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (t:Period {period_id: row.period_id})
        SET t += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Period: %d", total)
        return total

    def load_income_records(self) -> int:
        name = "income_record"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (ir:IncomeRecord {income_id: row.income_id})
        SET ir += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded IncomeRecord: %d", total)
        return total

    def load_properties(self) -> int:
        name = "property"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (pr:Property {property_id: row.property_id})
        SET pr += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Property: %d", total)
        return total

    def load_ownership_rights(self) -> int:
        name = "ownership_right"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (r:OwnershipRight {right_id: row.right_id})
        SET r += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded OwnershipRight: %d", total)
        return total

    def load_vehicles(self) -> int:
        name = "vehicle"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (v:Vehicle {vehicle_id: row.vehicle_id})
        SET v += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Vehicle: %d", total)
        return total

    def load_vehicle_registrations(self) -> int:
        name = "vehicle_registration"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (vr:VehicleRegistration {registration_id: row.registration_id})
        SET vr += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded VehicleRegistration: %d", total)
        return total

    def load_civil_events(self) -> int:
        name = "civil_event"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (ce:CivilEvent {event_id: row.event_id})
        SET ce += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded CivilEvent: %d", total)
        return total

    def load_courts(self) -> int:
        name = "court"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (c:Court {court_id: row.court_id})
        SET c += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded Court: %d", total)
        return total

    def load_court_cases(self) -> int:
        name = "court_case"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (cc:CourtCase {case_id: row.case_id})
        SET cc += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded CourtCase: %d", total)
        return total

    def load_court_decisions(self) -> int:
        name = "court_decision"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MERGE (cd:CourtDecision {decision_id: row.decision_id})
        SET cd += row
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded CourtDecision: %d", total)
        return total

    # ---------- Load relationships ----------

    def load_person_identifier_rels(self) -> int:
        name = "person_identifier"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (i:Identifier {identifier_id: row.identifier_id})
        MERGE (p)-[:HAS_IDENTIFIER]->(i)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Person)-[:HAS_IDENTIFIER]->(:Identifier): %d", total)
        return total

    def load_person_address_rels(self) -> int:
        name = "person_address"  # person_id,address_id,relationship_type
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (a:Address {address_id: row.address_id})
        MERGE (p)-[rel:HAS_ADDRESS]->(a)
        SET rel.relationship_type = row.relationship_type
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Person)-[:HAS_ADDRESS]->(:Address): %d", total)
        return total

    def load_property_address_rels(self) -> int:
        name = "address_property"  # property_id,address_id
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (pr:Property {property_id: row.property_id})
        MATCH (a:Address {address_id: row.address_id})
        MERGE (pr)-[:LOCATED_AT]->(a)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Property)-[:LOCATED_AT]->(:Address): %d", total)
        return total

    def link_ownership_rights_to_property(self) -> int:
        name = "ownership_right"  # contains property_id
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (r:OwnershipRight {right_id: row.right_id})
        MATCH (pr:Property {property_id: row.property_id})
        MERGE (r)-[:RIGHT_TO]->(pr)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            batch2 = [b for b in batch if b.get("property_id")]
            if not batch2:
                continue
            self._write_unwind(cypher, batch2)
            total += len(batch2)
        logging.info("Loaded (:OwnershipRight)-[:RIGHT_TO]->(:Property): %d", total)
        return total

    def load_person_property_right_rels(self) -> int:
        name = "person_property_right"  # right_id,person_id,role
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (r:OwnershipRight {right_id: row.right_id})
        MERGE (p)-[rel:HAS_RIGHT]->(r)
        SET rel.role = row.role
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Person)-[:HAS_RIGHT]->(:OwnershipRight): %d", total)
        return total

    def load_organization_property_right_rels(self) -> int:
        name = "organization_property_right"  # right_id,organization_id,role
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (o:Organization {organization_id: row.organization_id})
        MATCH (r:OwnershipRight {right_id: row.right_id})
        MERGE (o)-[rel:HAS_RIGHT]->(r)
        SET rel.role = row.role
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Organization)-[:HAS_RIGHT]->(:OwnershipRight): %d", total)
        return total

    def link_income_relationships(self) -> int:
        name = "income_record"
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (ir:IncomeRecord {income_id: row.income_id})
        OPTIONAL MATCH (p:Person {person_id: row.person_id})
        OPTIONAL MATCH (t:Period {period_id: row.period_id})
        OPTIONAL MATCH (o:Organization {organization_id: row.organization_id})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
          MERGE (p)-[:HAS_INCOME]->(ir)
        )
        FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END |
          MERGE (ir)-[:FOR_PERIOD]->(t)
        )
        FOREACH (_ IN CASE WHEN o IS NULL THEN [] ELSE [1] END |
          MERGE (o)-[:PAID_INCOME]->(ir)
        )
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Linked income relationships: %d", total)
        return total

    def load_person_vehicle_rels(self) -> int:
        name = "person_vehicle"  # person_id,vehicle_id,role
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (v:Vehicle {vehicle_id: row.vehicle_id})
        MERGE (p)-[rel:OWNS_VEHICLE]->(v)
        SET rel.role = row.role
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Person)-[:OWNS_VEHICLE]->(:Vehicle): %d", total)
        return total

    def link_vehicle_registrations_to_vehicle(self) -> int:
        name = "vehicle_registration"  # contains vehicle_id
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (v:Vehicle {vehicle_id: row.vehicle_id})
        MATCH (vr:VehicleRegistration {registration_id: row.registration_id})
        MERGE (v)-[:HAS_REGISTRATION]->(vr)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            batch2 = [b for b in batch if b.get("vehicle_id")]
            if not batch2:
                continue
            self._write_unwind(cypher, batch2)
            total += len(batch2)
        logging.info("Loaded (:Vehicle)-[:HAS_REGISTRATION]->(:VehicleRegistration): %d", total)
        return total

    def load_person_civil_event_rels(self) -> int:
        name = "person_civil_event"  # event_id,person_id,role
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (p:Person {person_id: row.person_id})
        MATCH (ce:CivilEvent {event_id: row.event_id})
        MERGE (p)-[rel:INVOLVED_IN]->(ce)
        SET rel.role = row.role
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            self._write_unwind(cypher, batch)
            total += len(batch)
        logging.info("Loaded (:Person)-[:INVOLVED_IN]->(:CivilEvent): %d", total)
        return total

    def link_court_case_to_court(self) -> int:
        name = "court_case"  # contains court_id
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (cc:CourtCase {case_id: row.case_id})
        MATCH (c:Court {court_id: row.court_id})
        MERGE (cc)-[:IN_COURT]->(c)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            batch2 = [b for b in batch if b.get("court_id")]
            if not batch2:
                continue
            self._write_unwind(cypher, batch2)
            total += len(batch2)
        logging.info("Loaded (:CourtCase)-[:IN_COURT]->(:Court): %d", total)
        return total

    def link_court_decision_to_case(self) -> int:
        name = "court_decision"  # contains case_id
        if not exists(self.csv_dir, name):
            logging.warning("Missing %s.csv, skipping", name)
            return 0

        cypher = """
        UNWIND $rows AS row
        MATCH (cd:CourtDecision {decision_id: row.decision_id})
        MATCH (cc:CourtCase {case_id: row.case_id})
        MERGE (cd)-[:FOR_CASE]->(cc)
        """

        total = 0
        for batch in chunked(read_csv_rows(csv_path(self.csv_dir, name)), self.cfg.batch_size):
            batch2 = [b for b in batch if b.get("case_id")]
            if not batch2:
                continue
            self._write_unwind(cypher, batch2)
            total += len(batch2)
        logging.info("Loaded (:CourtDecision)-[:FOR_CASE]->(:CourtCase): %d", total)
        return total

    # ---------- Orchestration ----------

    def run(self) -> None:
        self.validate_csv_presence()

        if self.cfg.dry_run:
            logging.info("DRY_RUN=True, skipping Neo4j connection + writes.")
            return

        if self.cfg.clear_db:
            self.clear_db()

        self.create_constraints()

        # Nodes
        self.load_registry_services()
        self.load_persons()
        self.load_identifiers()
        self.load_addresses()
        self.load_organizations()
        self.load_periods()
        self.load_income_records()
        self.load_properties()
        self.load_ownership_rights()
        self.load_vehicles()
        self.load_vehicle_registrations()
        self.load_civil_events()
        self.load_courts()
        self.load_court_cases()
        self.load_court_decisions()

        # Relationships
        self.load_person_identifier_rels()
        self.load_person_address_rels()
        self.load_property_address_rels()
        self.link_ownership_rights_to_property()
        self.load_person_property_right_rels()
        self.load_organization_property_right_rels()
        self.link_income_relationships()
        self.load_person_vehicle_rels()
        self.link_vehicle_registrations_to_vehicle()
        self.load_person_civil_event_rels()
        self.link_court_case_to_court()
        self.link_court_decision_to_case()

        logging.info("Done.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    cfg = LoaderConfig()

    placeholders_present = (
        "<" in cfg.uri
        or "<" in cfg.password
        or cfg.uri.strip() == ""
        or cfg.password.strip() == ""
    )

    if placeholders_present and not cfg.dry_run:
        raise SystemExit(
            "NEO4J_URI/NEO4J_PASSWORD are still placeholders. "
            "Edit this file and set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (or set DRY_RUN=True)."
        )

    loader = Neo4jEntityCsvLoader(cfg)
    try:
        loader.run()
    finally:
        loader.close()


if __name__ == "__main__":
    main()
