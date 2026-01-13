#!/usr/bin/env python3
"""
NABU archive -> normalized CSV export (Neo4j-ready).

Fixes vs previous version:
- Correctly decodes response folder names from ZIP mojibake (cp437->cp866) and #UXXXX sequences.
- Detects actual content format by sniffing (JSON inside answer.xml supported).
- Detects service_code by payload signatures when request->service mapping is missing.
- Removes raw truncation (response_raw keeps full payload).
- Fixes DRFO income parsing: reads TaxAgent/NameTaxAgent from SourcesOfIncome and emits one row per IncomeTaxes.
- Fixes EIS person parsing: supports root.result structure; fills full name fields.
- Adds parsing for: vehicles (EIS_TZ_OWNER), civil events (DRACS birth acts), courts (EDRSR).
- Fixes property rights subject & document field mapping (sbjCode/sbjName/dcSbjType; causeDocuments cdType/docDate/publisher).
- Adds registry_service rows (service_code -> registry_name + protocol).

Usage:
  python3 nabu_to_csv_fixed.py --data-dir ./nabu_data --out-dir ./csv_output
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

_ucs_pattern = re.compile(r"#U([0-9A-Fa-f]{4})")
_MOJIBAKE_RESP_RE = re.compile(r"^[ВЗ]-\d{4}-\d{4}-\d{3}-")


def decode_ucs(encoded: str) -> str:
    """Decode #UXXXX sequences (used in some datasets)."""
    def _repl(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)
    return _ucs_pattern.sub(_repl, encoded)


def fix_zip_mojibake(name: str) -> str:
    """Fix ZIP filenames decoded as cp437 when original was cp866 (common for Cyrillic ZIPs)."""
    name = decode_ucs(name)
    try:
        b = name.encode("cp437")
        dec = b.decode("cp866")
        if _MOJIBAKE_RESP_RE.match(dec):
            return dec
        # also accept if it contains Cyrillic and hyphenated ids
        if ("В-" in dec or "З-" in dec) and "-" in dec:
            return dec
    except Exception:
        pass
    return name


def localname(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def sniff_format(text: str) -> str:
    s = text.lstrip()
    if not s:
        return "text"
    if s.startswith("<"):
        return "xml"
    if s.startswith("{") or s.startswith("["):
        return "json"
    return "text"


def safe_read(path: Path) -> str:
    """Read file as text (utf-8 replace). No truncation."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.read_bytes().decode("utf-8", errors="replace")


def clean_jsonish(text: str) -> str:
    """Remove trailing commas before } or ] to make JSON parseable."""
    return re.sub(r",\s*([}\]])", r"\1", text)


# ---------------------------------------------------------------------------
# Request index parsing (best-effort)
# ---------------------------------------------------------------------------

def load_request_mapping(data_dir: Path) -> Dict[str, str]:
    """Return request_id -> service_code from 995-*/index.xml (if present)."""
    req_dir = next((d for d in data_dir.iterdir() if d.is_dir() and d.name.startswith("995-")), None)
    if not req_dir:
        return {}
    index_path = req_dir / "index.xml"
    if not index_path.exists():
        return {}
    mapping: Dict[str, str] = {}
    try:
        tree = ET.parse(index_path)
        root = tree.getroot()
        for req in root.findall(".//REQUEST"):
            rid = req.get("ID")
            name = req.get("NAME")
            if rid and name:
                mapping[rid] = name
    except Exception as e:
        logging.warning("Failed to parse index.xml: %s", e)
    return mapping


# ---------------------------------------------------------------------------
# Service detection (payload signatures)
# ---------------------------------------------------------------------------

def detect_service(service_from_index: Optional[str], fmt: str, raw: str) -> str:
    """Pick a best service_code. Prefer index mapping when available."""
    if service_from_index and service_from_index != "UNKNOWN":
        return service_from_index

    s = raw
    if fmt == "xml":
        if "InfoIncomeSourcesDRFO2AnswerResponse" in s or ("<SourcesOfIncome>" in s and "<IncomeTaxes>" in s):
            return "REQ_DRFO_INCOME"
        if "ArServiceAnswer" in s:
            if "<BirthAct>" in s:
                return "REQ_DRACS_BD_CHILD"
            # other DRACS act types could be added later
            return "REQ_DRACS"
        # fallback: unknown xml service
        return "UNKNOWN"

    if fmt == "json":
        if '"CARS"' in s and '"VIN"' in s and '"N_REG"' in s:
            return "REQ_EIS_TZ_OWNER"
        if '"root"' in s and '"result"' in s and ('"date_birth"' in s or '"birth_date"' in s) and '"documents"' in s:
            return "REQ_EIS_PERSON"
        if '"realty"' in s and '"properties"' in s and '"realtyAddress"' in s:
            return "REQ_DRRP"
        if '"courtId"' in s and '"caseNum"' in s and '"docTypeName"' in s:
            return "REQ_EDRSR"
        return "UNKNOWN"

    return "UNKNOWN"


def registry_name_from_service(service_code: str) -> str:
    if service_code.startswith("REQ_EIS_"):
        return "EIS"
    if service_code.startswith("REQ_DRFO"):
        return "DRFO"
    if service_code.startswith("REQ_DRACS"):
        return "DRACS"
    if service_code.startswith("REQ_EDRSR"):
        return "EDRSR"
    if service_code.startswith("REQ_DZK"):
        return "DZK"
    if service_code.startswith("REQ_DSR"):
        return "DSR"
    if service_code.startswith("REQ_EDR"):
        return "EDR"
    if service_code.startswith("REQ_DRRP"):
        return "DRRP"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_drfo_income(xml_text: str) -> List[Dict[str, str]]:
    """Parse DRFO income SOAP response.

    Returns one record per <IncomeTaxes> item, enriched with agent data.
    """
    out: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        logging.warning("DRFO XML parse failed: %s", e)
        return out

    rnokpp = ""
    for el in root.iter():
        if localname(el.tag) == "RNOKPP" and (el.text or "").strip():
            rnokpp = el.text.strip()
            break
    if not rnokpp:
        return out

    # Iterate sources
    for src in root.iter():
        if localname(src.tag) != "SourcesOfIncome":
            continue
        tax_agent = ""
        tax_agent_name = ""
        for ch in list(src):
            ln = localname(ch.tag)
            if ln == "TaxAgent":
                tax_agent = (ch.text or "").strip()
            elif ln == "NameTaxAgent":
                tax_agent_name = (ch.text or "").strip()

        for it in src.findall(".//IncomeTaxes"):
            rec = {
                "rnokpp": rnokpp,
                "tax_agent_code": tax_agent,
                "tax_agent_name": tax_agent_name,
                "period_year": "",
                "period_quarter": "",
                "income_accrued": "",
                "income_paid": "",
                "tax_charged": "",
                "tax_transferred": "",
                "military_sum": "",
                "income_type_code": "",
            }
            for child in list(it):
                ln = localname(child.tag)
                val = (child.text or "").strip()
                if ln == "period_year":
                    rec["period_year"] = val
                elif ln == "period_quarter_month":
                    rec["period_quarter"] = val
                elif ln == "IncomeAccrued":
                    rec["income_accrued"] = val
                elif ln == "IncomePaid":
                    rec["income_paid"] = val
                elif ln == "TaxCharged":
                    rec["tax_charged"] = val
                elif ln == "TaxTransferred":
                    rec["tax_transferred"] = val
                elif ln == "MilitaryTax":
                    rec["military_sum"] = val
                elif ln == "SignOfIncomePrivilege":
                    rec["income_type_code"] = val
            out.append(rec)

    return out


def parse_eis_person(json_text: str) -> Optional[Dict[str, Any]]:
    """Parse EIS person response (root.result)."""
    try:
        obj = json.loads(clean_jsonish(json_text))
    except Exception as e:
        logging.warning("EIS person JSON parse failed: %s", e)
        return None

    if not isinstance(obj, dict) or "root" not in obj:
        return None
    root = obj.get("root")
    if not isinstance(root, dict):
        return None

    data = root.get("result") if isinstance(root.get("result"), dict) else root.get("result", None)
    if data is None:
        # sometimes: root itself is the data
        data = root

    if not isinstance(data, dict):
        return None

    person: Dict[str, Any] = {
        "rnokpp": data.get("rnokpp") or data.get("code") or "",
        "unzr": data.get("unzr") or "",
        "last_name": data.get("last_name") or data.get("surname") or data.get("second_name") or "",
        "first_name": data.get("first_name") or data.get("name") or "",
        "middle_name": data.get("middle_name") or data.get("patronymic") or "",
        "birth_date": data.get("date_birth") or data.get("birth_date") or "",
        "gender": data.get("gender") or "",
        "birth_place": data.get("birth_place") or "",
        "citizenship": data.get("citizenship") or "",
        "documents": [],
        "addresses": [],
    }

    docs = data.get("documents") or []
    if isinstance(docs, list):
        for d in docs:
            if not isinstance(d, dict):
                continue
            doc_type = d.get("doc_type") or d.get("type") or ""
            series = d.get("series") or ""
            number = d.get("number") or ""
            if doc_type and (series or number):
                person["documents"].append({
                    "type": doc_type,
                    "series": series,
                    "number": number,
                    "date_issue": d.get("date_issue") or "",
                    "issuer": d.get("issuer") or "",
                })

    addr = data.get("registr_place") or data.get("address")
    if isinstance(addr, dict):
        person["addresses"].append(addr)
    elif isinstance(addr, list):
        person["addresses"].extend([a for a in addr if isinstance(a, dict)])

    return person


def parse_eis_vehicles(json_text: str) -> List[Dict[str, Any]]:
    """Parse EIS TZ owner vehicles: root.CARS[]"""
    try:
        obj = json.loads(clean_jsonish(json_text))
    except Exception as e:
        logging.warning("Vehicle JSON parse failed: %s", e)
        return []
    root = obj.get("root") if isinstance(obj, dict) else None
    if not isinstance(root, dict):
        return []
    cars = root.get("CARS") or []
    if not isinstance(cars, list):
        return []
    out: List[Dict[str, Any]] = []
    for c in cars:
        if isinstance(c, dict):
            out.append(c)
    return out


def parse_dracs_birth(xml_text: str) -> Optional[Dict[str, Any]]:
    """Parse DRACS birth act from ArServiceAnswer (SOAP)."""
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        logging.warning("DRACS XML parse failed: %s", e)
        return None

    # Find BirthAct node
    birth_act = None
    for el in root.iter():
        if localname(el.tag) == "BirthAct":
            birth_act = el
            break
    if birth_act is None:
        return None

    def get_text(parent: ET.Element, tag_name: str) -> str:
        for ch in list(parent):
            if localname(ch.tag) == tag_name:
                return (ch.text or "").strip()
        return ""

    act_number = get_text(birth_act, "ActNumber")
    act_date = get_text(birth_act, "ActDate")
    registrar = get_text(birth_act, "Registrar")

    # People blocks
    def parse_person_block(tag: str) -> Dict[str, str]:
        block = None
        for ch in birth_act.iter():
            if localname(ch.tag) == tag:
                block = ch
                break
        if block is None:
            return {}
        return {
            "last_name": get_text(block, "LastName"),
            "first_name": get_text(block, "FirstName"),
            "middle_name": get_text(block, "MiddleName"),
            "birth_date": get_text(block, "BirthDate"),
            "birth_place": get_text(block, "BirthPlace"),
            "citizenship": get_text(block, "Citizenship"),
            "gender": get_text(block, "Sex"),  # may be M/F or numeric
        }

    return {
        "act_number": act_number,
        "act_date": act_date,
        "registrar": registrar,
        "child": parse_person_block("Child"),
        "father": parse_person_block("Father"),
        "mother": parse_person_block("Mother"),
    }


def parse_property(json_text: str) -> List[Dict[str, Any]]:
    """Parse property rights JSON (DRRP / DZK-like)."""
    try:
        obj = json.loads(clean_jsonish(json_text))
    except Exception as e:
        logging.warning("Property JSON parse failed: %s", e)
        return []

    items: List[Dict[str, Any]] = []

    def extract_realty(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "realty" and isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict):
                            items.append(it)
                else:
                    extract_realty(v)
        elif isinstance(o, list):
            for e in o:
                extract_realty(e)

    extract_realty(obj)
    results: List[Dict[str, Any]] = []

    for re_obj in items:
        record: Dict[str, Any] = {
            "addresses": [],
            "rights": [],
            "re_type": re_obj.get("reType") or "",
            "reg_num": re_obj.get("regNum") or re_obj.get("registrationId") or "",
            "reg_date": re_obj.get("regDate") or re_obj.get("registrationDate") or "",
            "state": re_obj.get("reState") or re_obj.get("status") or "",
            "cad_num": "",
            "area": "",
            "area_unit": "",
        }
        # address
        for a in (re_obj.get("realtyAddress") or []):
            if isinstance(a, dict):
                record["addresses"].append(a)

        # ground area
        ga = re_obj.get("groundArea") or re_obj.get("area") or {}
        if isinstance(ga, list):
            ga = ga[0] if ga else {}
        if isinstance(ga, dict):
            record["area"] = ga.get("area") or ""
            record["area_unit"] = ga.get("areaUM") or ""
            record["cad_num"] = ga.get("cadNum") or re_obj.get("cadastralNum") or ""

        # rights
        for pr in (re_obj.get("properties") or []):
            if not isinstance(pr, dict):
                continue
            right = {
                "rn_num": pr.get("rnNum") or "",
                "registrar": pr.get("registrar") or "",
                "pr_state": pr.get("prState") or "",
                "share": pr.get("partSize") or "",
                "right_reg_date": pr.get("regDate") or "",
                "right_type": pr.get("prKind") or "",
                "subjects": pr.get("subjects") or [],
                "cause_documents": pr.get("causeDocuments") or [],
            }
            record["rights"].append(right)

        results.append(record)

    return results


def parse_edrsr(json_text: str) -> List[Dict[str, Any]]:
    """Parse EDRSR decision list JSON (may contain trailing commas)."""
    try:
        obj = json.loads(clean_jsonish(json_text))
    except Exception as e:
        logging.warning("EDRSR JSON parse failed: %s", e)
        return []
    arr = obj.get("array") if isinstance(obj, dict) else None
    if not isinstance(arr, list):
        return []
    return [x for x in arr if isinstance(x, dict)]


# ---------------------------------------------------------------------------
# CSV writer + in-memory store
# ---------------------------------------------------------------------------

def write_csv(out_dir: Path, name: str, headers: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = out_dir / f"{name}.csv"
    with fp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({h: ("" if r.get(h) is None else str(r.get(h))) for h in headers})


def merge_nonempty(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing dst fields from src (non-empty only)."""
    for k, v in src.items():
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        if dst.get(k) in (None, "", []):
            dst[k] = v
    return dst


# ---------------------------------------------------------------------------
# Main ETL
# ---------------------------------------------------------------------------

def process_responses(data_dir: Path, out_dir: Path) -> None:
    schemas: Dict[str, List[str]] = {
        "response": ["response_id", "request_id", "service_code", "format", "file_path", "service_detected_by"],
        "response_raw": ["response_id", "service_code", "raw_data"],

        "registry_service": ["service_code", "registry_name", "protocol"],

        "person": ["person_id", "rnokpp", "unzr", "first_name", "middle_name", "last_name",
                   "full_name", "birth_date", "gender", "birth_place", "citizenship", "registry_source"],
        "identifier": ["identifier_id", "identifier_type", "identifier_value"],
        "person_identifier": ["person_id", "identifier_id"],

        "address": ["address_id", "address_line", "region", "district", "city", "street", "house", "apartment", "postal_code", "koatuu"],
        "person_address": ["person_id", "address_id", "relationship_type"],

        "organization": ["organization_id", "org_code", "name", "org_type"],
        "period": ["period_id", "year", "quarter"],

        "income_record": ["income_id", "person_id", "organization_id", "period_id",
                          "income_amount", "income_accrued", "income_paid",
                          "tax_amount", "tax_charged", "tax_transferred",
                          "military_amount", "income_type_code", "response_id"],

        "property": ["property_id", "cad_num", "re_type", "reg_num", "state", "registration_date", "area", "area_unit"],
        "address_property": ["property_id", "address_id"],
        "ownership_right": ["right_id", "property_id", "right_type", "share", "registrar",
                            "rn_num", "pr_state", "right_reg_date",
                            "doc_type", "doc_type_extension", "doc_publisher", "doc_date"],
        "person_property_right": ["right_id", "person_id", "role"],
        "organization_property_right": ["right_id", "organization_id", "role"],

        "vehicle": ["vehicle_id", "vin", "registration_number", "make", "model", "year", "color", "car_id"],
        "vehicle_registration": ["registration_id", "vehicle_id", "registration_date", "status", "opercode", "doc_id", "dep_reg_name"],
        "person_vehicle": ["person_id", "vehicle_id", "role"],

        "civil_event": ["event_id", "event_type", "date", "act_number", "registry_office", "response_id"],
        "person_civil_event": ["event_id", "person_id", "role"],

        "court": ["court_id", "court_name", "court_code"],
        "court_case": ["case_id", "case_number", "court_id"],
        "court_decision": ["decision_id", "case_id", "case_number", "decision_date", "court_id", "court_name", "decision_type", "outcome", "reg_num"],
    }

    # In-memory stores (dedup by key tuples)
    rows: Dict[str, Dict[Tuple[str, ...], Dict[str, Any]]] = {k: {} for k in schemas}
    seq = {
        "person": 0,
        "identifier": 0,
        "address": 0,
        "organization": 0,
        "period": 0,
        "income": 0,
        "property": 0,
        "right": 0,
        "event": 0,
    }

    # Person identity maps + aliasing (to avoid duplicates and allow updates)
    person_by_rnokpp: Dict[str, str] = {}
    person_by_unzr: Dict[str, str] = {}
    person_by_passport: Dict[str, str] = {}
    person_alias: Dict[str, str] = {}  # old -> new canonical

    def canonical_person_id(pid: str) -> str:
        while pid in person_alias:
            pid = person_alias[pid]
        return pid

    def get_or_create_person(rnokpp: str = "", unzr: str = "", passport_key: str = "", seed_source: str = "") -> str:
        nonlocal seq
        candidates: List[str] = []
        if rnokpp and rnokpp in person_by_rnokpp:
            candidates.append(person_by_rnokpp[rnokpp])
        if unzr and unzr in person_by_unzr:
            candidates.append(person_by_unzr[unzr])
        if passport_key and passport_key in person_by_passport:
            candidates.append(person_by_passport[passport_key])

        candidates = [canonical_person_id(x) for x in candidates]
        person_id = candidates[0] if candidates else ""

        if not person_id:
            seq["person"] += 1
            person_id = f"P{seq['person']}"

        # unify if multiple ids discovered
        for c in candidates[1:]:
            if c != person_id:
                person_alias[c] = person_id

        # bind keys
        if rnokpp:
            person_by_rnokpp[rnokpp] = person_id
        if unzr:
            person_by_unzr[unzr] = person_id
        if passport_key:
            person_by_passport[passport_key] = person_id

        # ensure person row exists
        pk = (person_id,)
        if pk not in rows["person"]:
            rows["person"][pk] = {
                "person_id": person_id,
                "rnokpp": rnokpp,
                "unzr": unzr,
                "first_name": "",
                "middle_name": "",
                "last_name": "",
                "full_name": "",
                "birth_date": "",
                "gender": "",
                "birth_place": "",
                "citizenship": "",
                "registry_source": "",
            }
        else:
            # merge identifiers
            merge_nonempty(rows["person"][pk], {"rnokpp": rnokpp, "unzr": unzr})

        # append registry source (keep unique, semicolon-separated)
        if seed_source:
            cur = rows["person"][pk].get("registry_source") or ""
            parts = [p for p in cur.split(";") if p]
            if seed_source not in parts:
                parts.append(seed_source)
            rows["person"][pk]["registry_source"] = ";".join(parts)

        return person_id

    # Other dedup maps
    identifier_by_key: Dict[Tuple[str, str], str] = {}
    address_by_key: Dict[str, str] = {}
    org_by_key: Dict[Tuple[str, str, str], str] = {}  # (org_code, name, org_type) -> org_id
    period_by_key: Dict[Tuple[str, str], str] = {}
    property_by_key: Dict[str, str] = {}
    vehicle_by_key: Dict[str, str] = {}  # vehicle_id -> vehicle_id (dedup helper)
    court_case_by_key: Dict[Tuple[str, str], str] = {}  # (court_id, case_number) -> case_id

    def get_or_create_identifier(id_type: str, value: str) -> str:
        nonlocal seq
        k = (id_type, value)
        if k in identifier_by_key:
            return identifier_by_key[k]
        seq["identifier"] += 1
        ident_id = f"ID{seq['identifier']}"
        identifier_by_key[k] = ident_id
        rows["identifier"][(ident_id,)] = {
            "identifier_id": ident_id,
            "identifier_type": id_type,
            "identifier_value": value,
        }
        return ident_id

    def link_person_identifier(person_id: str, ident_id: str) -> None:
        person_id = canonical_person_id(person_id)
        rows["person_identifier"][(person_id, ident_id)] = {"person_id": person_id, "identifier_id": ident_id}

    def get_or_create_address(addr: Dict[str, Any]) -> str:
        nonlocal seq
        address_line = addr.get("address") or addr.get("addressDetail") or ""
        region = addr.get("regionName") or addr.get("region") or ""
        district = addr.get("districtName") or addr.get("district") or ""
        city = addr.get("cityName") or addr.get("city") or ""
        street = addr.get("street_name") or addr.get("street") or ""
        house = addr.get("building_number") or addr.get("house") or ""
        apartment = addr.get("apartment") or ""
        postal_code = addr.get("zip") or addr.get("postal_code") or ""
        koatuu = addr.get("koatuu") or addr.get("koatuu_code") or ""
        key = ";".join([address_line, region, district, city, street, house, apartment, postal_code, koatuu])
        if key in address_by_key:
            return address_by_key[key]
        seq["address"] += 1
        aid = f"A{seq['address']}"
        address_by_key[key] = aid
        rows["address"][(aid,)] = {
            "address_id": aid,
            "address_line": address_line,
            "region": region,
            "district": district,
            "city": city,
            "street": street,
            "house": house,
            "apartment": apartment,
            "postal_code": postal_code,
            "koatuu": koatuu,
        }
        return aid

    def get_or_create_org(code: str, name: str, org_type: str) -> str:
        nonlocal seq
        k = (code or "", name or "", org_type or "")
        if k in org_by_key:
            return org_by_key[k]
        seq["organization"] += 1
        oid = f"O{seq['organization']}"
        org_by_key[k] = oid
        rows["organization"][(oid,)] = {"organization_id": oid, "org_code": code, "name": name, "org_type": org_type}
        return oid

    def get_or_create_period(year: str, quarter: str) -> str:
        nonlocal seq
        k = (year or "", quarter or "")
        if k in period_by_key:
            return period_by_key[k]
        seq["period"] += 1
        pid = f"T{seq['period']}"
        period_by_key[k] = pid
        rows["period"][(pid,)] = {"period_id": pid, "year": year, "quarter": quarter}
        return pid

    req_map = load_request_mapping(data_dir)

    # Registry service collector (unique by service_code+protocol)
    regsvc_seen: set = set()

    # Walk responses
    for top in data_dir.iterdir():
        if not top.is_dir() or not (top.name.startswith("890-") or top.name.startswith("891-")):
            continue

        for resp_dir in top.iterdir():
            if not resp_dir.is_dir():
                continue

            response_id = fix_zip_mojibake(resp_dir.name)

            # pick answer file (either answer.xml or answer.json)
            candidate = None
            for fn in ("answer.xml", "answer.json"):
                p = resp_dir / fn
                if p.exists():
                    candidate = p
                    break
            if not candidate:
                continue

            raw = safe_read(candidate)
            fmt = sniff_format(raw)

            # best-effort request id guess (may be missing in this dataset)
            request_id_guess = ""
            if response_id.startswith("В-"):
                request_id_guess = "З" + response_id[1:]
            # service from mapping if exists
            svc_from_index = req_map.get(request_id_guess) if request_id_guess else None
            service_code = detect_service(svc_from_index, fmt, raw)
            detected_by = "index" if (svc_from_index and svc_from_index == service_code) else "signature"

            # response + raw
            rows["response"][(response_id,)] = {
                "response_id": response_id,
                "request_id": request_id_guess,
                "service_code": service_code,
                "format": fmt,
                "file_path": str(candidate.relative_to(data_dir)),
                "service_detected_by": detected_by,
            }
            rows["response_raw"][(response_id,)] = {"response_id": response_id, "service_code": service_code, "raw_data": raw}

            # registry_service
            reg_name = registry_name_from_service(service_code)
            regsvc_key = (service_code, reg_name, fmt)
            if service_code != "UNKNOWN" and regsvc_key not in regsvc_seen:
                regsvc_seen.add(regsvc_key)
                rows["registry_service"][(service_code,)] = {"service_code": service_code, "registry_name": reg_name, "protocol": fmt}

            # Dispatch parsing
            if service_code == "REQ_DRFO_INCOME" and fmt == "xml":
                for inc in parse_drfo_income(raw):
                    rnokpp = inc.get("rnokpp") or ""
                    person_id = get_or_create_person(rnokpp=rnokpp, seed_source="REQ_DRFO_INCOME")
                    # identifier
                    if rnokpp:
                        iid = get_or_create_identifier("RNOKPP", rnokpp)
                        link_person_identifier(person_id, iid)

                    # org
                    tax_code = inc.get("tax_agent_code") or ""
                    tax_name = inc.get("tax_agent_name") or ""
                    org_id = get_or_create_org(tax_code, tax_name, "tax_agent") if (tax_code or tax_name) else ""

                    # period
                    year = inc.get("period_year") or ""
                    quarter = inc.get("period_quarter") or ""
                    period_id = get_or_create_period(year, quarter) if (year or quarter) else ""

                    # income record
                    seq["income"] += 1
                    income_id = f"INC{seq['income']}"
                    rows["income_record"][(income_id,)] = {
                        "income_id": income_id,
                        "person_id": person_id,
                        "organization_id": org_id,
                        "period_id": period_id,
                        # "income_amount" kept for compatibility: prefer paid, else accrued
                        "income_amount": inc.get("income_paid") or inc.get("income_accrued") or "",
                        "income_accrued": inc.get("income_accrued") or "",
                        "income_paid": inc.get("income_paid") or "",
                        "tax_amount": inc.get("tax_transferred") or inc.get("tax_charged") or "",
                        "tax_charged": inc.get("tax_charged") or "",
                        "tax_transferred": inc.get("tax_transferred") or "",
                        "military_amount": inc.get("military_sum") or "",
                        "income_type_code": inc.get("income_type_code") or "",
                        "response_id": response_id,
                    }

            elif service_code == "REQ_EIS_PERSON" and fmt == "json":
                pdata = parse_eis_person(raw)
                if pdata:
                    rnokpp = pdata.get("rnokpp") or ""
                    unzr = pdata.get("unzr") or ""
                    person_id = get_or_create_person(rnokpp=rnokpp, unzr=unzr, seed_source="REQ_EIS_PERSON")

                    # update person fields
                    pk = (person_id,)
                    full_name = " ".join([x for x in [pdata.get("last_name"), pdata.get("first_name"), pdata.get("middle_name")] if x and str(x).strip()])
                    merge_nonempty(rows["person"][pk], {
                        "first_name": pdata.get("first_name") or "",
                        "middle_name": pdata.get("middle_name") or "",
                        "last_name": pdata.get("last_name") or "",
                        "full_name": full_name,
                        "birth_date": pdata.get("birth_date") or "",
                        "gender": pdata.get("gender") or "",
                        "birth_place": pdata.get("birth_place") or "",
                        "citizenship": pdata.get("citizenship") or "",
                        "registry_source": "REQ_EIS_PERSON",
                    })

                    # identifiers
                    if rnokpp:
                        iid = get_or_create_identifier("RNOKPP", rnokpp)
                        link_person_identifier(person_id, iid)
                    if unzr:
                        iid = get_or_create_identifier("UNZR", unzr)
                        link_person_identifier(person_id, iid)

                    # documents identifiers
                    for d in pdata.get("documents") or []:
                        doc_type = (d.get("type") or "document").strip()
                        series = (d.get("series") or "").strip()
                        number = (d.get("number") or "").strip()
                        if not (series or number):
                            continue
                        value = f"{series}:{number}" if series else number
                        iid = get_or_create_identifier(doc_type, value)
                        link_person_identifier(person_id, iid)

                        # also allow passport-based merge for other sources (vehicles)
                        passport_key = f"{doc_type}:{value}"
                        person_by_passport[passport_key] = person_id

                    # address
                    for addr in pdata.get("addresses") or []:
                        aid = get_or_create_address(addr)
                        rows["person_address"][(person_id, aid, "registered")] = {
                            "person_id": person_id, "address_id": aid, "relationship_type": "registered"
                        }

            elif service_code == "REQ_EIS_TZ_OWNER" and fmt == "json":
                cars = parse_eis_vehicles(raw)
                for c in cars:
                    vin = (c.get("VIN") or "").strip()
                    car_id = str(c.get("CAR_ID") or "").strip()
                    vehicle_id = ""
                    if vin:
                        vehicle_id = f"VIN:{vin}"
                    elif car_id:
                        vehicle_id = f"CAR_ID:{car_id}"
                    else:
                        # fallback: deterministic on registration+brand+model+year
                        vehicle_id = f"VEH:{(c.get('N_REG') or '')}_{(c.get('BRAND_NAME') or '')}_{(c.get('MODEL_NAME') or '')}_{(c.get('MAKE_YEAR') or '')}"

                    rows["vehicle"][(vehicle_id,)] = {
                        "vehicle_id": vehicle_id,
                        "vin": vin,
                        "registration_number": str(c.get("N_REG") or "").strip(),
                        "make": str(c.get("BRAND_NAME") or "").strip(),
                        "model": str(c.get("MODEL_NAME") or "").strip(),
                        "year": str(c.get("MAKE_YEAR") or "").strip(),
                        "color": str(c.get("COLOR_NAME") or "").strip(),
                        "car_id": car_id,
                    }

                    # vehicle_registration ~ operation record
                    oper_date = str(c.get("OPER_DATE") or "").strip()
                    opercode = str(c.get("OPERCODE") or "").strip()
                    doc_id = str(c.get("DOC_ID") or "").strip()
                    reg_id = f"VR:{vehicle_id}:{oper_date}:{opercode}:{doc_id}"
                    rows["vehicle_registration"][(reg_id,)] = {
                        "registration_id": reg_id,
                        "vehicle_id": vehicle_id,
                        "registration_date": oper_date or str(c.get("PRIMARY_DATE") or "").strip(),
                        "status": str(c.get("OPERNAME") or "").strip(),
                        "opercode": opercode,
                        "doc_id": doc_id,
                        "dep_reg_name": str(c.get("DEP_REG_NAME") or "").strip(),
                    }

                    # owner person
                    owner = c.get("OWNER") if isinstance(c.get("OWNER"), dict) else {}
                    owner_code = (owner.get("CODE") or "").strip()
                    owner_rnokpp = owner_code if (owner_code.isdigit() and len(owner_code) == 10) else ""
                    passport_series = (owner.get("PASSPORTSERIES") or "").strip()
                    passport_number = (owner.get("PASSPORTNUMBER") or "").strip()
                    passport_key = ""
                    if passport_series or passport_number:
                        passport_key = f"PASSPORT:{passport_series}:{passport_number}"

                    person_id = get_or_create_person(rnokpp=owner_rnokpp, passport_key=passport_key, seed_source="REQ_EIS_TZ_OWNER")
                    pk = (person_id,)
                    full_name = " ".join([x for x in [(owner.get("LNAME") or "").strip(),
                                                     (owner.get("FNAME") or "").strip(),
                                                     (owner.get("PNAME") or "").strip()] if x])
                    merge_nonempty(rows["person"][pk], {
                        "rnokpp": owner_rnokpp,
                        "first_name": (owner.get("FNAME") or "").strip(),
                        "middle_name": (owner.get("PNAME") or "").strip(),
                        "last_name": (owner.get("LNAME") or "").strip(),
                        "full_name": full_name,
                        "birth_date": (owner.get("BIRTHDAY") or "").strip(),
                        "registry_source": "REQ_EIS_TZ_OWNER",
                    })

                    if owner_rnokpp:
                        iid = get_or_create_identifier("RNOKPP", owner_rnokpp)
                        link_person_identifier(person_id, iid)
                    if passport_series or passport_number:
                        iid = get_or_create_identifier("PASSPORT", f"{passport_series}:{passport_number}")
                        link_person_identifier(person_id, iid)

                    rows["person_vehicle"][(person_id, vehicle_id, "owner")] = {
                        "person_id": person_id,
                        "vehicle_id": vehicle_id,
                        "role": "owner",
                    }

            elif service_code.startswith("REQ_DRACS") and fmt == "xml":
                birth = parse_dracs_birth(raw)
                if birth:
                    seq["event"] += 1
                    event_id = f"CE{seq['event']}"
                    rows["civil_event"][(event_id,)] = {
                        "event_id": event_id,
                        "event_type": "birth",
                        "date": birth.get("act_date") or "",
                        "act_number": birth.get("act_number") or "",
                        "registry_office": birth.get("registrar") or "",
                        "response_id": response_id,
                    }

                    for role in ("child", "father", "mother"):
                        pd = birth.get(role) or {}
                        if not pd:
                            continue
                        # DRACS usually lacks rnokpp; use name+bdate fallback key only for internal consistency
                        # Here we create a synthetic passport_key-like key to avoid collapsing unrelated people with same name.
                        synth_key = f"DRACS:{role}:{pd.get('last_name','')}:{pd.get('first_name','')}:{pd.get('middle_name','')}:{pd.get('birth_date','')}"
                        person_id = get_or_create_person(passport_key=synth_key, seed_source="REQ_DRACS_BD_CHILD")
                        pk = (person_id,)
                        full_name = " ".join([x for x in [pd.get("last_name"), pd.get("first_name"), pd.get("middle_name")] if x and str(x).strip()])
                        merge_nonempty(rows["person"][pk], {
                            "first_name": pd.get("first_name") or "",
                            "middle_name": pd.get("middle_name") or "",
                            "last_name": pd.get("last_name") or "",
                            "full_name": full_name,
                            "birth_date": pd.get("birth_date") or "",
                            "gender": pd.get("gender") or "",
                            "birth_place": pd.get("birth_place") or "",
                            "citizenship": pd.get("citizenship") or "",
                            "registry_source": "REQ_DRACS_BD_CHILD",
                        })
                        rows["person_civil_event"][(event_id, person_id, role)] = {"event_id": event_id, "person_id": person_id, "role": role}

            elif service_code.startswith("REQ_EDRSR") and fmt == "json":
                for d in parse_edrsr(raw):
                    court_id = str(d.get("courtId") or "").strip()
                    court_name = str(d.get("courtName") or "").strip()
                    if court_id:
                        rows["court"][(court_id,)] = {"court_id": court_id, "court_name": court_name, "court_code": court_id}

                    case_number = str(d.get("caseNum") or "").strip()
                    if court_id and case_number:
                        case_id = court_case_by_key.get((court_id, case_number))
                        if not case_id:
                            safe_case = re.sub(r"[^0-9A-Za-zА-Яа-я_\-\.]", "_", case_number)
                            case_id = f"CASE:{court_id}:{safe_case}"
                            court_case_by_key[(court_id, case_number)] = case_id
                        rows["court_case"][(case_id,)] = {"case_id": case_id, "case_number": case_number, "court_id": court_id}

                        reg_num = str(d.get("regNum") or "").strip()
                        if reg_num:
                            decision_id = f"DEC:{reg_num}"
                        else:
                            decision_id = f"DEC:{court_id}:{safe_case}:{str(d.get('docDate') or '').strip()}:{str(d.get('docTypeId') or '').strip()}"

                        rows["court_decision"][(decision_id,)] = {
                            "decision_id": decision_id,
                            "case_id": case_id,
                            "case_number": case_number,
                            "decision_date": str(d.get("docDate") or "").strip(),
                            "court_id": court_id,
                            "court_name": court_name,
                            "decision_type": str(d.get("docTypeName") or "").strip(),
                            "outcome": "",
                            "reg_num": reg_num,
                        }

            elif service_code in ("REQ_DRRP", "REQ_DZK_PARCEL_OWNER") and fmt == "json":
                for pr in parse_property(raw):
                    key = (pr.get("cad_num") or pr.get("reg_num") or "").strip()
                    if not key:
                        seq["property"] += 1
                        property_id = f"PR{seq['property']}"
                    else:
                        if key in property_by_key:
                            property_id = property_by_key[key]
                        else:
                            seq["property"] += 1
                            property_id = f"PR{seq['property']}"
                            property_by_key[key] = property_id

                    rows["property"][(property_id,)] = {
                        "property_id": property_id,
                        "cad_num": pr.get("cad_num") or "",
                        "re_type": pr.get("re_type") or "",
                        "reg_num": pr.get("reg_num") or "",
                        "state": pr.get("state") or "",
                        "registration_date": pr.get("reg_date") or "",
                        "area": pr.get("area") or "",
                        "area_unit": pr.get("area_unit") or "",
                    }

                    # addresses
                    for addr in pr.get("addresses") or []:
                        if not isinstance(addr, dict):
                            continue
                        aid = get_or_create_address(addr)
                        rows["address_property"][(property_id, aid)] = {"property_id": property_id, "address_id": aid}

                    # rights
                    for r in pr.get("rights") or []:
                        seq["right"] += 1
                        right_id = f"R{seq['right']}"
                        # cause docs
                        doc_type = ""
                        doc_type_ext = ""
                        doc_pub = ""
                        doc_date = ""
                        cds = r.get("cause_documents") or []
                        if isinstance(cds, list) and cds:
                            d0 = cds[0] if isinstance(cds[0], dict) else {}
                            doc_type = str(d0.get("cdType") or d0.get("type") or d0.get("doc_type") or "").strip()
                            doc_type_ext = str(d0.get("cdTypeExtension") or "").strip()
                            doc_pub = str(d0.get("publisher") or d0.get("issuer") or "").strip()
                            doc_date = str(d0.get("docDate") or d0.get("doc_date") or d0.get("date") or "").strip()

                        rows["ownership_right"][(right_id,)] = {
                            "right_id": right_id,
                            "property_id": property_id,
                            "right_type": r.get("right_type") or "",
                            "share": r.get("share") or "",
                            "registrar": r.get("registrar") or "",
                            "rn_num": r.get("rn_num") or "",
                            "pr_state": r.get("pr_state") or "",
                            "right_reg_date": r.get("right_reg_date") or "",
                            "doc_type": doc_type,
                            "doc_type_extension": doc_type_ext,
                            "doc_publisher": doc_pub,
                            "doc_date": doc_date,
                        }

                        for sub in (r.get("subjects") or []):
                            if not isinstance(sub, dict):
                                continue
                            # dataset uses sbjCode/sbjName + dcSbjType
                            code = str(sub.get("sbjCode") or sub.get("code") or "").strip()
                            name = str(sub.get("sbjName") or sub.get("name") or "").strip()
                            dc_type = str(sub.get("dcSbjType") or sub.get("type") or "").strip()
                            role = "owner"

                            # Heuristics:
                            # - if 10 digits -> person
                            # - if dcSbjType == "2" -> legal entity/organization
                            is_person = (code.isdigit() and len(code) == 10) and dc_type != "2"
                            if is_person:
                                pid = get_or_create_person(rnokpp=code, seed_source=service_code)
                                link_person_identifier(pid, get_or_create_identifier("RNOKPP", code))
                                # if name is present but not split, keep as last_name field if empty
                                pk = (pid,)
                                if name and not rows["person"][pk].get("full_name"):
                                    rows["person"][pk]["full_name"] = name
                                    rows["person"][pk]["last_name"] = rows["person"][pk].get("last_name") or name
                                rows["person_property_right"][(right_id, pid, role)] = {"right_id": right_id, "person_id": pid, "role": role}
                            else:
                                oid = get_or_create_org(code, name, "owner")
                                rows["organization_property_right"][(right_id, oid, role)] = {"right_id": right_id, "organization_id": oid, "role": role}

            # else: leave raw only

    # Apply person aliasing to all tables that reference person_id
    person_ref_entities = [
        "income_record", "person_identifier", "person_address", "person_property_right",
        "person_vehicle", "person_civil_event"
    ]
    for ent in person_ref_entities:
        new_rows: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        for k, r in rows[ent].items():
            r2 = dict(r)
            if "person_id" in r2:
                r2["person_id"] = canonical_person_id(str(r2["person_id"]))
            # rebuild key tuple according to schema if needed
            key_tuple = tuple(str(r2.get(h, "")) for h in schemas[ent])
            # But for link tables we want dedup on natural keys, not all columns.
            # We'll keep the original key if it matches length; else use key_tuple.
            if isinstance(k, tuple) and len(k) == len(key_tuple):
                new_k = key_tuple
            else:
                new_k = key_tuple
            new_rows[new_k] = r2
        rows[ent] = new_rows

    # Ensure full_name for persons
    for pk, p in rows["person"].items():
        if not p.get("full_name"):
            full = " ".join([x for x in [p.get("last_name"), p.get("first_name"), p.get("middle_name")] if x and str(x).strip()])
            p["full_name"] = full

    # Write all CSVs
    for name, hdrs in schemas.items():
        write_csv(out_dir, name, hdrs, rows[name].values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Export NABU responses to normalized CSV files")
    parser.add_argument("--data-dir", required=True, help="Path to extracted NABU archive directory")
    parser.add_argument("--out-dir", required=True, help="Directory to write CSV files")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not data_dir.exists() or not data_dir.is_dir():
        raise SystemExit(f"Data directory {data_dir} does not exist or is not a directory")

    process_responses(data_dir, out_dir)
    logging.info("CSV export completed: %s", out_dir)


if __name__ == "__main__":
    main()
