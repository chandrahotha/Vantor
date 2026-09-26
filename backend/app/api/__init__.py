"""API v1 router aggregation — all routes live under /api/v1."""
from fastapi import APIRouter

from ..routers.ai import router as ai_router
from ..routers.audit import router as audit_router
from ..routers.catalog import router as catalog_router
from ..routers.contracts import router as contracts_router
from ..routers.documents import router as documents_router
from ..routers.health import router as health_router
from ..routers.identity import router as identity_router
from ..routers.integrations import router as integrations_router
from ..routers.notifications import router as notifications_router
from ..routers.sourcing import router as sourcing_router
from ..routers.purchase import router as purchase_router
from ..routers.spend import router as spend_router
from ..routers.suppliers import router as suppliers_router

v1 = APIRouter(prefix="/api/v1")
v1.include_router(health_router)
v1.include_router(identity_router)
v1.include_router(integrations_router)
v1.include_router(notifications_router)
v1.include_router(audit_router)
v1.include_router(catalog_router)
v1.include_router(ai_router)
v1.include_router(suppliers_router)
v1.include_router(sourcing_router)
v1.include_router(contracts_router)
v1.include_router(documents_router)
v1.include_router(purchase_router)
v1.include_router(spend_router)
