import uvicorn
from fastapi import FastAPI
from app.api.routes.profiles import router as profiles_router
from app.core.settings import settings

app = FastAPI(title=settings.APP_NAME)
app.include_router(profiles_router, prefix="/api/v1/profiles", tags=["Profiles"])

@app.get("/")
def root():
    return {"status": "ok", "service": "Profile Creator"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)