"""
Ponto de entrada da aplicação Chamados Cematel.
"""
import datetime
import logging

from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.dependencies import NaoAutenticado
from app.auth.security import decode_access_token
from app.config import settings
from app.database.helpdesk_db import HelpdeskSessionLocal
from app.database.legacy_db import init_legacy_pool, close_legacy_pool
from app.routers import admin, admin_logs, auth, chamados, clientes, mapa, pages, monitoramento
from app.routers.auth import limiter
from app.services.auditoria_service import registrar_evento_auditoria
from app.services.sla_monitor_service import verificar_sla_e_notificar
from app.services.notificacao_service import processar_fila_notificacoes
from app.templates_config import templates
from app.services.rastreio_monitor_service import verificar_rastreios_e_notificar
from app.services.monitoramento_service import coletar_e_salvar

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _verificar_fila_notificacoes():
    async with HelpdeskSessionLocal() as db:
        await processar_fila_notificacoes(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_legacy_pool()
    scheduler.add_job(verificar_rastreios_e_notificar, "interval", minutes=90, id="verificar_rastreios")
    scheduler.add_job(coletar_e_salvar, "interval", seconds=settings.monitor_poll_interval, id="monitoramento_coleta", max_instances=1, coalesce=True)
    scheduler.add_job(verificar_sla_e_notificar, "interval", minutes=15, id="verificar_sla")
    scheduler.add_job(_verificar_fila_notificacoes, "interval", minutes=1, id="fila_notificacoes", max_instances=1, coalesce=True)
    scheduler.start()
    yield
    scheduler.shutdown()
    await close_legacy_pool()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _categoria_auditoria(caminho: str) -> str:
    if caminho.startswith(("/login", "/logout", "/auth/")):
        return "autenticacao"
    if caminho.startswith("/chamados"):
        return "chamados"
    if caminho.startswith("/clientes"):
        return "clientes"
    if caminho.startswith("/admin/contatos"):
        return "usuarios"
    if caminho.startswith("/admin"):
        return "administracao"
    if caminho.startswith(("/monitoramento", "/api/monitoramento")):
        return "monitoramento"
    if caminho.startswith("/mapa"):
        return "mapa"
    return "sistema"


async def _auditar_requisicao(request: Request, status_http: int) -> None:
    caminho_real = request.url.path
    if (
        caminho_real.startswith("/static/")
        or caminho_real in {
            "/health", "/favicon.ico", "/favicon.svg", "/openapi.json",
            "/docs", "/redoc", "/login", "/logout", "/auth/login", "/auth/logout",
        }
    ):
        return
    # A leitura normal da própria auditoria não gera outro registro. Tentativas
    # negadas de acesso, porém, são registradas para fins de segurança.
    if caminho_real.startswith("/admin/logs") and status_http < 400:
        return
    if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return

    token = request.cookies.get("session_token")
    payload = decode_access_token(token) if token else None
    if not payload:
        return
    try:
        usuario_codigo = int(payload.get("sub"))
    except (TypeError, ValueError):
        return

    rota = request.scope.get("route")
    caminho = getattr(rota, "path", caminho_real)
    nome_rota = getattr(rota, "name", None)
    acao = str(nome_rota or f"{request.method} {caminho}")
    parametros = request.path_params or {}
    entidade = None
    entidade_id = None
    for chave, rotulo in (
        ("chamado_id", "chamado"),
        ("usuario_codigo", "usuario"),
        ("categoria_id", "categoria"),
        ("prioridade_id", "prioridade"),
        ("status_id", "status"),
    ):
        if chave in parametros:
            entidade = rotulo
            entidade_id = str(parametros[chave])
            break

    resultado = "negado" if status_http == 403 else ("falha" if status_http >= 400 else "sucesso")
    tipo_evento = "consulta" if request.method == "GET" else "alteracao"
    cliente = request.client
    user_agent = request.headers.get("user-agent", "")
    async with HelpdeskSessionLocal() as db:
        await registrar_evento_auditoria(
            db,
            usuario_codigo=usuario_codigo,
            usuario_login=payload.get("login"),
            usuario_nome=payload.get("nome"),
            tipo_evento=tipo_evento,
            categoria=_categoria_auditoria(caminho_real),
            acao=acao,
            resultado=resultado,
            metodo_http=request.method,
            caminho=caminho,
            entidade=entidade,
            entidade_id=entidade_id,
            status_http=status_http,
            ip_origem=cliente.host if cliente else None,
            user_agent=user_agent,
        )


@app.middleware("http")
async def registrar_interacoes(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:
        try:
            await _auditar_requisicao(request, 500)
        except Exception:
            logger.warning("Falha ao auditar requisição que terminou em exceção.", exc_info=True)
        raise

    try:
        await _auditar_requisicao(request, response.status_code)
    except Exception:
        # A indisponibilidade da auditoria não pode derrubar uma operação do Help Desk.
        logger.warning("Falha ao auditar requisição HTTP.", exc_info=True)
    return response


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
templates.env.globals["ano_atual"] = datetime.datetime.now().year

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(chamados.router)
app.include_router(admin.router)
app.include_router(admin_logs.router)
app.include_router(mapa.router)
app.include_router(monitoramento.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
