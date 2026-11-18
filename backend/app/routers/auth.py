"""
Rotas de autenticação via API (JSON) — úteis para testes e integrações futuras.
A tela de login HTML fica em app/routers/pages.py, usando o mesmo serviço.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.security import create_access_token
from app.config import settings
from app.database.helpdesk_db import get_helpdesk_db
from app.schemas.auth import LoginRequest, UsuarioLogado
from app.services.auditoria_service import registrar_evento_auditoria
from app.services.auth_service import (
    autenticar_usuario,
    CredenciaisInvalidas,
    SemPermissaoHelpDesk,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


def _ip_origem(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_helpdesk_db),
):
    try:
        usuario = await autenticar_usuario(login_data.login, login_data.senha)
    except CredenciaisInvalidas:
        await registrar_evento_auditoria(
            db, tipo_evento="autenticacao", categoria="autenticacao",
            acao="login_api", resultado="falha", usuario_login=login_data.login,
            metodo_http="POST", caminho="/auth/login", status_http=401,
            ip_origem=_ip_origem(request), detalhes="Credenciais inválidas",
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha inválidos.")
    except SemPermissaoHelpDesk:
        await registrar_evento_auditoria(
            db, tipo_evento="autenticacao", categoria="autenticacao",
            acao="login_api", resultado="negado", usuario_login=login_data.login,
            metodo_http="POST", caminho="/auth/login", status_http=403,
            ip_origem=_ip_origem(request), detalhes="Usuário sem permissão para acessar o Help Desk",
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Este usuário não tem permissão para acessar o Help Desk.",
        )

    token = create_access_token(
        usuario_codigo=usuario["codigo"], login=usuario["login"], nome=usuario["nome"]
    )
    await registrar_evento_auditoria(
        db, tipo_evento="autenticacao", categoria="autenticacao",
        acao="login_api", resultado="sucesso",
        usuario_codigo=usuario["codigo"], usuario_login=usuario["login"],
        usuario_nome=usuario["nome"], metodo_http="POST",
        caminho="/auth/login", status_http=200, ip_origem=_ip_origem(request),
    )
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return {"mensagem": "Login realizado com sucesso.", "nome": usuario["nome"]}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    usuario: dict | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    await registrar_evento_auditoria(
        db, tipo_evento="autenticacao", categoria="autenticacao",
        acao="logout_api", resultado="sucesso",
        usuario_codigo=usuario.get("codigo") if usuario else None,
        usuario_login=usuario.get("login") if usuario else None,
        usuario_nome=usuario.get("nome") if usuario else None,
        metodo_http="POST", caminho="/auth/logout", status_http=200,
        ip_origem=_ip_origem(request),
    )
    response.delete_cookie("session_token")
    return {"mensagem": "Sessão encerrada."}


@router.get("/me", response_model=UsuarioLogado)
async def me(usuario: dict = Depends(get_current_user)):
    return usuario
