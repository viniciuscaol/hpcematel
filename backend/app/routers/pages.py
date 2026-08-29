"""
Rotas que renderizam páginas HTML (login, dashboard).
Usa HTMX para interatividade sem precisar de uma SPA separada.
"""
from fastapi import Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import get_current_user_com_papel, exigir_papel
from app.services.chamado_service import listar_chamados_para_assumir
from app.services.contato_service import PAPEL_ADMIN, PAPEL_TECNICO
from app.auth.dependencies import get_current_user_optional
from app.auth.security import create_access_token
from app.config import settings
from app.database.helpdesk_db import get_helpdesk_db
from app.services.auth_service import (
    autenticar_usuario,
    CredenciaisInvalidas,
    SemPermissaoHelpDesk,
)
from app.services.dashboard_service import (
    contagem_por_categoria,
    contagem_por_prioridade,
    contagem_por_status,
    contar_meus_chamados,
    contar_sla_estourado,
    listar_chamados_recentes,
)
from app.templates_config import templates

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/")
async def raiz(usuario: dict | None = Depends(get_current_user_optional)):
    return RedirectResponse("/dashboard" if usuario else "/login")


@router.get("/login")
async def tela_login(
    request: Request,
    usuario: dict | None = Depends(get_current_user_optional),
    next: str = "/dashboard",
):
    if usuario:
        return RedirectResponse(next if next.startswith("/") else "/dashboard")
    return templates.TemplateResponse("login.html", {"request": request, "next": next})


@router.post("/login")
@limiter.limit("5/minute")
async def processar_login(
    request: Request,
    response: Response,
    login: str = Form(...),
    senha: str = Form(...),
    next: str = Form("/dashboard"),
):
    try:
        usuario = await autenticar_usuario(login, senha)
    except CredenciaisInvalidas:
        return templates.TemplateResponse(
            "partials/login_error.html",
            {"request": request, "mensagem": "Usuário ou senha inválidos."},
        )
    except SemPermissaoHelpDesk:
        return templates.TemplateResponse(
            "partials/login_error.html",
            {"request": request, "mensagem": "Este usuário não tem permissão para acessar o Help Desk."},
        )

    token = create_access_token(
        usuario_codigo=usuario["codigo"], login=usuario["login"], nome=usuario["nome"]
    )

    # Só aceita redirecionar para caminhos internos (começando com "/"),
    # nunca para uma URL externa — evita golpe de "redirecionamento aberto".
    destino = next if next.startswith("/") and not next.startswith("//") else "/dashboard"

    resposta = Response(status_code=200)
    resposta.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.jwt_expire_minutes * 60,
    )
    resposta.headers["HX-Redirect"] = destino
    return resposta


@router.get("/dashboard")
async def tela_dashboard(
    request: Request,
    usuario: dict = Depends(get_current_user_com_papel),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    if usuario is None:
        return RedirectResponse("/login")

    contexto = {
        "request": request,
        "usuario": usuario,
        "por_status": await contagem_por_status(db),
        "por_prioridade": await contagem_por_prioridade(db),
        "por_categoria": await contagem_por_categoria(db),
        "meus_chamados": await contar_meus_chamados(db, usuario["codigo"]),
        "sla_estourado": await contar_sla_estourado(db),
        "recentes": await listar_chamados_recentes(db),
    }
    return templates.TemplateResponse("dashboard.html", contexto)

@router.get("/tecnico")
async def tela_tecnico(
    request: Request,
    usuario: dict = Depends(exigir_papel(PAPEL_TECNICO, PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    chamados = await listar_chamados_para_assumir(db)
    return templates.TemplateResponse("tecnico.html", {"request": request, "usuario": usuario, "chamados": chamados})


@router.post("/logout")
async def processar_logout():
    resposta = Response(status_code=200)
    resposta.delete_cookie("session_token")
    resposta.headers["HX-Redirect"] = "/login"
    return resposta