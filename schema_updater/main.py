from fastapi import FastAPI
import uvicorn
from app.api.routes.align import router as align_router

app = FastAPI(title="Schema Updater Agent")
app.include_router(align_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"status": "ok", "service": "Profile Creator"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)