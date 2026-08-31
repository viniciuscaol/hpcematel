"""
Ponto de entrada da aplicação Chamados Cematel.
"""
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.dependencies import NaoAutenticado
from app.config import settings
from app.database.legacy_db import init_legacy_pool, close_legacy_pool
from app.routers import admin, auth, chamados, clientes, pages
from app.routers.auth import limiter
from app.services.sla_monitor_service import verificar_sla_e_notificar
from app.templates_config import templates
from app.services.rastreio_monitor_service import verificar_rastreios_e_notificar

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_legacy_pool()
    scheduler.add_job(verificar_rastreios_e_notificar, "interval", minutes=60, id="verificar_rastreios")
    scheduler.add_job(verificar_sla_e_notificar, "interval", minutes=15, id="verificar_sla")
    scheduler.start()
    yield
    scheduler.shutdown()
    await close_legacy_pool()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(NaoAutenticado)
async def nao_autenticado_handler(request: Request, exc: NaoAutenticado):
    from urllib.parse import quote

    destino_original = request.url.path
    url_login = f"/login?next={quote(destino_original)}"

    if request.headers.get("HX-Request") == "true":
        resposta = Response(status_code=200)
        resposta.headers["HX-Redirect"] = url_login
        return resposta
    return RedirectResponse(url_login, status_code=303)


app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates.env.globals["app_name"] = settings.app_name

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(chamados.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}