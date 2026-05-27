from fastapi import APIRouter

from app.api.v1 import auth, datasets, jobs, dashboards
from app.api.v1.admin import router as admin_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(admin_router.router, prefix="/admin", tags=["admin"])
