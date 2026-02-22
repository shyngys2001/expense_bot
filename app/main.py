from fastapi import FastAPI

from app.api.accounts import router as accounts_router
from app.api.categories import router as categories_router
from app.api.imports import rollback_router as imports_rollback_router
from app.api.imports import router as imports_router
from app.api.pages import router as pages_router
from app.api.reports import router as reports_router
from app.api.rules import router as rules_router
from app.api.transfers import router as transfers_router
from app.api.transactions import router as transactions_router
from app.db.seed import seed_initial_data
from app.db.session import AsyncSessionLocal
from app.db.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
async def on_startup() -> None:
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session, seed_demo=settings.seed_demo)


@app.get("/health", tags=["health"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(pages_router)
app.include_router(transactions_router)
app.include_router(accounts_router)
app.include_router(rules_router)
app.include_router(reports_router)
app.include_router(imports_router)
app.include_router(imports_rollback_router)
app.include_router(categories_router)
app.include_router(transfers_router)
