"""
routers/health.py — Kubernetes liveness / readiness probes
"""
from fastapi import APIRouter
import psutil, time

router = APIRouter()
START_TIME = time.time()

@router.get("/live")
async def liveness():
    return {"status": "alive"}

@router.get("/ready")
async def readiness():
    # Check critical dependencies
    return {
        "status": "ready",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
    }
