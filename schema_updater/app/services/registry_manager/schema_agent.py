import json
import re
import logging
from openai import OpenAI
from app.core.settings import settings
from app.models.schema import Entity
from jsonpath_ng import parse

logger = logging.getLogger("uvicorn.error")

class SchemaAgent:
    def __init__(self):
        self.client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)

    def _validate_mapping_locally(self, document_data: dict, registry_config: dict) -> list:
        """
        Перевіряє, чи можна реально дістати дані з документа за допомогою згенерованої схеми.
        Повертає список помилок, якщо шляхи не валідні.
        """
        errors = []
        variant = registry_config.get("variants", [{}])[0]
        mappings = variant.get("mappings", [])

        for m in mappings:
            scope_path = m.get("scope", {}).get("foreach")
            source_path = m.get("source", {}).get("json_path")
            mapping_id = m.get("mapping_id")

            try:
                scope_expr = parse(scope_path)
                scope_matches = scope_expr.find(document_data)
                
                if not scope_matches:
                    errors.append(f"[{mapping_id}] Scope path '{scope_path}' returned no data.")
                    continue

                source_expr = parse(source_path)
                for match in scope_matches:
                    source_matches = source_expr.find(match.value)
                    if not source_matches:
                        errors.append(f"[{mapping_id}] Source path '{source_path}' not found inside scope.")
                        break
            except Exception as e:
                errors.append(f"[{mapping_id}] Path syntax error: {str(e)}")

        return errors

    def _build_prompt(self, document: str, existing_entities: list[Entity], registry_code: str) -> str:
        entities_context = json.dumps([e.model_dump() for e in existing_entities], indent=2, ensure_ascii=False)
        logger.info(document)
        
        return f"""Ти — провідний архітектор систем обміну даними. Твоє завдання: створити декларативну конфігурацію мапінгу (JSON), яка дозволить автоматично витягнути дані з документа в нашу базу сутностей.

### 1. БАЗА ЗНАНЬ СУТНОСТЕЙ (КАТАЛОГ):
{entities_context}

### 2. СТРОГИЙ АЛГОРИТМ ТА ПРАВИЛА ВАЛІДАЦІЇ:

КРОК 1: ІДЕНТИФІКАЦІЯ ТИПІВ ДАНИХ ТА СТРУКТУРИ
- Уважно проаналізуй кожне поле в наданому ДОКУМЕНТІ.
- Визнач, чи є вузол масивом `[...]` (потрібен `[*]`) чи поодиноким об'єктом `{{...}}` (зірочка ЗАБОРОНЕНА).
- Знайди відповідник для коду реєстру: {registry_code}. Обери ОДИН варіант із: [RRP, DRFO, EDR, EIS, DZK, DRACS, ERD, COURT, MVS, IDP, REQUEST].

КРОК 2: ВИЗНАЧЕННЯ ГЛОБАЛЬНОГО КОНТЕКСТУ (SCOPE)
- Для кожної сутності (Person, Organization тощо) визнач точку входу (`foreach`).
- Якщо дані сутності розкидані по різних гілках JSON, створи для кожної гілки окремий `mapping_id` у списку `mappings`.

КРОК 3: ПРАВИЛО "БЕЗПЕРЕРВНОГО ШЛЯХУ" (CRITICAL!)
- Кожен `source.json_path` будується ВІДНОСНО точки, вказаної у `foreach`.
- **ЗАБОРОНЕНО перестрибувати через рівні вкладеності.** - **ПРИКЛАД ПОМИЛКИ:** Якщо `foreach` стоїть на `SourcesOfIncome`, а ти хочеш дістати `period_year`, який лежить всередині `IncomeTaxes`, то шлях `$.period_year` — НЕВІРНИЙ.
- **ЯК ПРАВИЛЬНО:** Ти маєш вказати повний відносний шлях: `$.IncomeTaxes.period_year`.
- Переконайся, що кожен проміжний об'єкт (вузол) згаданий у шляху.

КРОК 4: ЕВОЛЮЦІЯ СХЕМИ ТА СЕМАНТИКА
- Якщо в базі знань вже є поле для цієї сутності (наприклад, для `Person` є `tax_id`), використовуй саме його системну назву.
- Якщо ти знайшов нове цільне поле, якого немає в каталозі:
    1. Придумай йому назву в `snake_case` (напр. `income_accrued_amount`).
    2. Додай його в `proposed_fields` (вкажи сутність з каталогу).
    3. Використай цю назву в `mappings`.

КРОК 5: ТЕСТОВА САМОПЕРЕВІРКА (SIMULATION)
- Візьми один запис із документа. Пройди по ньому своїм шляхом `foreach` -> `json_path`.
- Якщо ти "вперся" в об'єкт, а не в конкретне значення — твій шлях помилковий. Перепиши його.

### 3. ФОРМАТ ВІДПОВІДІ (ONLY VALID JSON):
{{
  "registry_config": {{
    "registry_code": "CODE",
    "variants": [{{
      "variant_id": "v1",
      "match_predicate": {{ "all": [{{ "type": "json_equals", "path": "$.path.to.marker", "value": "expected_val" }}] }},
      "mappings": [
        {{
          "mapping_id": "person_main_info",
          "scope": {{ "foreach": "$.path.to.node" }},
          "source": {{ "json_path": "$.relative.path.to.field" }},
          "targets": [{{ "entity": "EntityName", "property": "system_name" }}]
        }}
      ]
    }}]
  }},
  "proposed_fields": [
    {{ "entity": "Entity", "system_name": "name", "type": "string", "description": "опис" }}
  ],
  "validation_status": "ok",
  "error_details": null
}}

Якщо структура документа занадто складна або пошкоджена — поверни `validation_status: "error"`.

### ДОКУМЕНТ ДЛЯ АНАЛІЗУ:
{document}
"""

    def analyze(self, document_data: any, all_existing_entities: list[Entity], registry_code: str):
        doc_str = json.dumps(document_data, ensure_ascii=False)

        response = self.client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a precise data architect. Return ONLY valid JSON. Accuracy of JSON paths is top priority."},
                {"role": "user", "content": self._build_prompt(doc_str, all_existing_entities, registry_code)}
            ],
            temperature=0
        )

        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

        logger.info(f"usage: {usage}")

        content = re.sub(r'```json\s*|```', '', response.choices[0].message.content).strip()

        try:
            data = json.loads(content)
            
            config = data.get("registry_config")
            if config:
                validation_errors = self._validate_mapping_locally(document_data, config)
                
                if validation_errors:
                    error_msg = "; ".join(validation_errors)
                    logger.error(f"❌ Schema validation failed: {error_msg}")
                    raise ValueError(f"Generated schema is invalid for this document: {error_msg}")
                
                logger.info("✅ Local validation passed: All JSON paths are reachable.")

            return data

        except json.JSONDecodeError:
            logger.error(f"🔥 AI returned invalid JSON. Content: {content}")
            raise ValueError("AI response is not a valid JSON")
        except Exception as e:
            logger.error(f"🔥 Error: {str(e)}")
            raise