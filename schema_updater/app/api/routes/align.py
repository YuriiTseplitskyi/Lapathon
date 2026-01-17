from fastapi import APIRouter
from app.services.registry_manager.schema_agent import SchemaAgent
from app.services.registry_manager.schema_evolver import SchemaEvolver
from app.services.registry_manager.registry_agent import RegistryManager

router = APIRouter()
agent = SchemaAgent()
evolver = SchemaEvolver()
manager = RegistryManager()


@router.post("/process-document")
async def process_document(document: dict):
    current_registry = manager.get_latest_registry()
    
    analysis = agent.analyze(document, current_registry)
    
    updated_registry, cross_reference = SchemaEvolver.evolve(analysis, current_registry)
    
    version_folder = manager.save_version(updated_registry, cross_reference)
    
    return {
        "status": "success",
        "version_directory": version_folder,
        "mapping_dictionary": cross_reference, 
        "raw_analysis": {
            "mappings": analysis.mappings,
            "proposed_fields": analysis.proposed_fields
        },
        "new_schema_preview": updated_registry, 
        "usage": analysis.usage
    }