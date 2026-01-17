import re
from app.models.schema import Entity, FieldDefinition, MappingResponse

class SchemaEvolver:
    @staticmethod
    def evolve(analysis: MappingResponse, current_registry: list[Entity]):
        updated_registry = [e.model_copy(deep=True) for e in current_registry]
        cross_reference = {}

        def generalize_path(path: str) -> str:
            if not path:
                return path
            return re.sub(r'\[\d+\]', '[*]', path)

        parent_prefix = ""
        if analysis.mappings:
            sample_path = list(analysis.mappings.keys())[0]
            if "." in sample_path:
                parent_prefix = ".".join(sample_path.split('.')[:-1])

        for doc_path, schema_name in analysis.mappings.items():
            gen_doc_path = generalize_path(doc_path)
            cross_reference[gen_doc_path] = schema_name 

        target_entity = None
        for entity in updated_registry:
            if entity.name == analysis.identified_entity:
                target_entity = entity
                break

        if not target_entity:
            target_entity = Entity(
                name=analysis.identified_entity,
                description="Автоматично створена сутність",
                fields=[]
            )
            updated_registry.append(target_entity)

        for field_info in analysis.proposed_fields:
            orig_path = field_info.original_name
            if not orig_path.startswith("root") and parent_prefix:
                orig_path = f"{parent_prefix}.{orig_path}"

            exists = any(f.name == field_info.system_name for f in target_entity.fields)
            
            if not exists:
                new_field = FieldDefinition(
                    name=field_info.system_name,
                    description=field_info.description,
                    type=field_info.type,
                    nullable=field_info.nullable
                )
                target_entity.fields.append(new_field)
            
            gen_orig_path = generalize_path(orig_path)
            cross_reference[gen_orig_path] =  field_info.system_name

        return updated_registry, cross_reference