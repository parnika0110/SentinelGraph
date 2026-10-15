"""API route modules (FastAPI routers)."""

from app.routes.actions import router as actions_router
from app.routes.alerts import router as alerts_router
from app.routes.demo import router as demo_router
from app.routes.graph import router as graph_router
from app.routes.health import router as health_router
from app.routes.incidents import router as incidents_router
from app.routes.investigations import router as investigations_router
from app.routes.memories import router as memories_router

ALL_ROUTERS = [
    health_router,
    alerts_router,
    investigations_router,
    graph_router,
    memories_router,
    actions_router,
    incidents_router,
    demo_router,
]
