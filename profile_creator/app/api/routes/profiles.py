from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from app.services.neo4j_service import Neo4jService
from app.services.pdf_service import generate_pdf
from app.models.domain import PersonProfile

router = APIRouter()

def get_db():
    db = Neo4jService()
    try:
        yield db
    finally:
        db.close()

@router.get("/{rnokpp}", response_model=PersonProfile)
def get_person_profile(rnokpp: str, db: Neo4jService = Depends(get_db)):
    """Fetch raw JSON profile data"""
    profile = db.get_profile(rnokpp)
    if not profile:
        raise HTTPException(status_code=404, detail="Person not found")
    return profile

@router.get("/{rnokpp}/pdf")
def download_profile_pdf(rnokpp: str, db: Neo4jService = Depends(get_db)):
    """Generate and download PDF report"""
    profile = db.get_profile(rnokpp)
    if not profile:
        raise HTTPException(status_code=404, detail="Person not found")
    
    pdf_path = generate_pdf(profile)
    return FileResponse(pdf_path, media_type='application/pdf', filename=f"Profile_{rnokpp}.pdf")