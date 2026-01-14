from typing import List, Optional, Union
from pydantic import BaseModel, field_validator

class Vehicle(BaseModel):
    make: str = "н/д"
    model: str = ""
    year: Optional[int] = None
    registration_number: str = "---"
    color: Optional[str] = ""

class Property(BaseModel):
    re_type: str = "Нерухомість"
    area: Optional[float] = 0.0
    area_unit: Optional[str] = "кв.м"
    address: str = "Адреса не вказана"
    share: str = "1/1"
    right_type: str = "Власність"

class Income(BaseModel):
    amount: float = 0.0
    source: str = "Невідомо"
    year: int
    type_code: str = ""

class CourtCase(BaseModel):
    case_num: str
    decision_type: str
    decision_date: str
    court_name: str

class NameHistory(BaseModel):
    old_name: str
    event_date: str
    event_type: str

class AssociatedAddress(BaseModel):
    region: Optional[str] = ""
    house: Optional[str] = ""
    street: Optional[str] = ""
    appartment: Optional[str] = ""
    address_type: str = "Пов'язана адреса" 

class CompanyIncome(BaseModel):
    name: str = "Невідома організація"
    edrpou: str = "---"
    total_amount: float = 0.0
    years_count: Optional[int] = None

class FamilyMember(BaseModel):
    full_name: str
    rnokpp: Optional[str] = "---"
    registry_office: str
    role_str: str
    person_id: Optional[str] = ""


class PersonProfile(BaseModel):
    first_name: str
    last_name: str
    middle_name: str
    full_name: str
    rnokpp: str
    unzr: Optional[str] = "---"
    birth_date: Optional[str] = "н/д"
    birth_place: Optional[str] = "н/д"
    gender: Optional[str] = ""
    citizenship: Optional[Union[str, List[str]]] = "Україна"

    addresses: List[AssociatedAddress] = []
    companies: List[CompanyIncome] = []
    
    vehicles: List[Vehicle] = []
    properties: List[Property] = []
    incomes: List[Income] = []
    court_cases: List[CourtCase] = []
    name_history: List[NameHistory] = []

    family: List[FamilyMember] = []


    @field_validator('citizenship', mode='before')
    @classmethod
    def validate_citizenship(cls, v):
        if isinstance(v, list): return ", ".join(set(v))
        return v