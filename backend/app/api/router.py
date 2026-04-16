from fastapi import APIRouter

from app.api.routes import admin, alerts, devices, health, payments, print_jobs, test_assets

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(print_jobs.router, prefix="/print-jobs", tags=["Print Jobs"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(test_assets.router, prefix="/test-assets", tags=["Test Assets"])
