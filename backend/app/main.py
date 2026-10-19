import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException

from app.api.workspace import router as workspace_router
from app.api.connections import router as connections_router
from app.api.evidence import router as evidence_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.imports import router as imports_router
from app.api.intelligence import router as intelligence_router
from app.api.workflow import router as workflow_router
from app.api.local_ai import router as local_ai_router
from app.api.readiness import router as readiness_router
from app.api.admin import router as admin_router
from app.core.config import settings
from app.core.database import get_db

app = FastAPI(
    title="AdviCue AI API",
    description="Evidence-backed client attention, financial analysis and advisor accountability.",
    version="1.0.0",
    docs_url=None, redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([settings.frontend_origin, *(
        ["http://localhost:5173", "http://127.0.0.1:5173"]
        if settings.app_env.lower() in {"development", "demo", "local"} else []
    )])),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(workspace_router,prefix="/api/v1")
app.include_router(connections_router,prefix="/api/v1")
app.include_router(evidence_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(imports_router, prefix="/api/v1")
app.include_router(intelligence_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(local_ai_router, prefix="/api/v1")
app.include_router(readiness_router, prefix="/api/v1", include_in_schema=False)
app.include_router(admin_router, prefix="/api/v1", include_in_schema=False)


@app.get("/api/v1/health", tags=["System"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database unavailable") from e
    return {"status": "ok", "service": "advicue-ai", "edition":"AdviCue AI", "phase": 9, "database": "connected", "instance_id": os.getenv("ADVICUE_INSTANCE_ID", "")}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers['Permissions-Policy']='microphone=(self), camera=(), geolocation=()'
    response.headers['Content-Security-Policy']="default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response


# Serve the compiled React app from FastAPI. Normal offline operation needs no
# Node server, CDN scripts, web fonts or external API documentation assets.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
_dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if (_dist/'index.html').is_file():
    app.mount('/assets',StaticFiles(directory=_dist/'assets'),name='frontend-assets')
    @app.get('/{path:path}',include_in_schema=False)
    def frontend(path:str):
        if path=='api' or path.startswith('api/'):
            raise HTTPException(status_code=404,detail='API route not found')
        return FileResponse(_dist/'index.html')
