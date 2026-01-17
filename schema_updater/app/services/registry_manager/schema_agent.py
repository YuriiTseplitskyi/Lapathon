import json
import re
from openai import OpenAI
from app.core.settings import settings
from app.models.schema import Entity, MappingResponse, FieldDefinition


class SchemaAgent:
    def __init__(self):
        self.client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)

    def _build_prompt(self, document: str, existing_entities: list[Entity]) -> str:
        registry_context = json.dumps([e.model_dump() for e in existing_entities], indent=2, ensure_ascii=False)
        
        return f"""Ти — провідний архітектор даних та OSINT-аналітик. Твоє завдання — інтегрувати вхідний документ у систему, забезпечивши ідеальний мапінг і розвиток схеми.

### 1. КОНТЕКСТ РЕЄСТРУ (Існуюча схема):
{registry_context}

### 2. ПРАВИЛА АНАЛІЗУ:
- **Ідентифікація сутності:** Визнач, яка Entity з реєстру найкраще описує документ. Якщо документ містить дані, яких взагалі немає в реєстрі — познач `is_new_registry: true`.
- **Точний Мапінг (Mappings):** - Знайди відповідність між полями документа та полями в існуючій схемі.
    - Враховуй семантику: наприклад, `N_BODY` або `VIN_CODE` у документі — це `vin` у схемі. `SUMA` — це `price` або `cost`.
    - Ключ у `mappings` — це повний шлях у JSON (dot notation), Значення — назва поля зі схеми.
- **Розвиток схеми (Proposed Fields):**
    - Знайди нові поля, які мають антикорупційну або бізнес-цінність (фінанси, власники, технічні параметри, що впливають на ціну, як-от площа чи рік).
    - **Трансформація імен:** Для кожного нового поля створи `system_name` у форматі snake_case (напр. `registration_authority`, `owner_tax_id`). Це ім'я має бути зрозумілим для розробників.
    - **Ігноруй технічний шум:** Не пропонуй поля як-от колір, тип палива чи системні ID транзакцій, якщо вони не несуть цінності для розслідування.
    - **Описи:** Напиши детальний опис українською: що це за дані та чому вони важливі для моніторингу активів.

### 3. СУВОРА ВИМОГА:
Одне і те саме поле НЕ може бути одночасно і в `mappings`, і в `proposed_fields`. Якщо воно замаплене на існуючу схему — воно тільки в `mappings`.

### 4. ФОРМАТ ВІДПОВІДІ (JSON ONLY):
{{
  "identified_entity": "НазваСутності",
  "is_new_registry": false,
  "mappings": {{
    "root.CARS[0].VIN": "vin_code",
    "root.CARS[0].MAKE_YEAR": "production_year"
  }},
  "proposed_fields": [
    {{
      "original_name": "SUMA",
      "system_name": "transaction_value",
      "description": "Повна вартість об'єкта на момент реєстрації, необхідна для контролю заниження ціни та перевірки доходів.",
      "type": "number",
      "nullable": true
    }}
  ]
}}

### ДОКУМЕНТ ДЛЯ АНАЛІЗУ:
{document}
"""

    def analyze(self, document_data: any, existing_registry: list[Entity]) -> MappingResponse:
        doc_str = json.dumps(document_data, ensure_ascii=False)

        response = self.client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a professional OSINT data investigator. Return ONLY valid JSON."},
                {"role": "user", "content": self._build_prompt(doc_str, existing_registry)}
            ],
            temperature=0
        )

        usage = response.usage
        content = re.sub(r'```json\s*|```', '', response.choices[0].message.content).strip()
        
        try:
            data = json.loads(content)
            
            mapped_paths = set(data.get('mappings', {}).keys())
            mapped_original_names = {path.split('.')[-1] for path in mapped_paths}
            
            data['proposed_fields'] = [
                f for f in data.get('proposed_fields', []) 
                if f.get('original_name') not in mapped_original_names
            ]

            data['usage'] = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
            
            return MappingResponse(**data)
        except Exception as e:
            print(f"DEBUG - Raw AI Content: {content}")
            raise ValueError(f"AI response parsing failed: {str(e)}")
        