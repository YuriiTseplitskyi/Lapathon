from fastapi import APIRouter, HTTPException, status
from app.services.registry_manager.schema_agent import SchemaAgent
from app.services.registry_manager.schema_evolver import SchemaEvolver
from app.services.registry_manager.registry_agent import RegistryManager
from app.services.registry_manager.mongo_processor import MongoDiscoveryProcessor
import logging

logger = logging.getLogger("uvicorn.error")
router = APIRouter()
# agent = SchemaAgent()
# evolver = SchemaEvolver()
# manager = RegistryManager()

processor = MongoDiscoveryProcessor()

@router.post("/process-checkpoint")
async def handle_checkpoint(id: str):
    try:
        config = processor.process_by_checkpoint(id)
        
        save_path = processor.manager.save_config_version(config)
        
        return {
            "status": "success",
            "checkpoint_processed": id,
            "config_saved_to": save_path
        }

    except ValueError as e:
            logger.error(f"Validation failed for checkpoint {id}: {str(e)}")
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "Schema validation failed",
                    "message": str(e)
                }
            )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )