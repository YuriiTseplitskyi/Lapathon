from app.models.schema import Entity, FieldDefinition, RegistryConfig

class SchemaEvolver:
    @staticmethod
    def evolve(ai_analysis: dict, current_registry: list[Entity]):
        """
        Повертає: (updated_entities, final_registry_config)
        """
        updated_entities = [e.model_copy(deep=True) for e in current_registry]
        
        for new_f in ai_analysis.get('proposed_fields', []):
            target_entity_name = new_f['entity']
            
            entity = next((e for e in updated_entities if e.entity_name == target_entity_name), None)
            if not entity:
                entity = Entity(entity_name=target_entity_name, description="Auto-created", fields=[])
                updated_entities.append(entity)
            
            if not any(f.name == new_f['system_name'] for f in entity.properties):
                entity.properties.append(FieldDefinition(
                    name=new_f['system_name'],
                    description=new_f['description'],
                    type=new_f['type']
                ))

        final_config = RegistryConfig(**ai_analysis['registry_config'])

        return updated_entities, final_config