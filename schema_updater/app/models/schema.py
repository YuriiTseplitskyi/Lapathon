from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict

class FieldDefinition(BaseModel):
    # Тепер Pydantic прийме і 'name', і 'system_name'
    name: str = Field(validation_alias="system_name")
    description: str
    type: str
    nullable: bool = True

    # Ця конфігурація дозволяє створювати об'єкт через FieldDefinition(name="...")
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )


class Entity(BaseModel):
    name: str
    description: str
    fields: List[FieldDefinition]
    
    # Це важливо, щоб модель працювала коректно з обома назвами
    model_config = ConfigDict(populate_by_name=True)

class AlignmentRequest(BaseModel):
    # Тепер тут може бути будь-що: JSON, XML або просто текст
    document: Any 
    registry: List[Entity]

class ProposedField(BaseModel):
    original_name: str
    system_name: str
    description: str
    type: str
    nullable: bool = True

# Онови MappingResponse, щоб він очікував саме структуру від ШІ
class MappingResponse(BaseModel):
    identified_entity: str
    is_new_registry: bool
    mappings: dict[str, str]
    proposed_fields: list[ProposedField] # Використовуємо спеціальну модель для розпізнавання відповіді
    usage: dict = None

class UsageStats(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
