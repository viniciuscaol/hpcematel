"""
Rotas de autenticação via API (JSON) — úteis para testes e integrações futuras.
A tela de login HTML fica em app/routers/pages.py, usando o mesmo serviço.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token
from app.config import settings
from app.schemas.auth import LoginRequest, UsuarioLogado
from app.services.auth_service import (
    autenticar_usuario,
    CredenciaisInvalidas,
    SemPermissaoHelpDesk,
)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, login_data: LoginRequest, response: Response):
    try:
        usuario = await autenticar_usuario(login_data.login, login_data.senha)
    except CredenciaisInvalidas:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha inválidos.")
    except SemPermissaoHelpDesk:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Este usuário não tem permissão para acessar o Help Desk.",
        )

    token = create_access_token(
        usuario_codigo=usuario["codigo"], login=usuario["login"], nome=usuario["nome"]
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
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {"mensagem": "Sessão encerrada."}


@router.get("/me", response_model=UsuarioLogado)
async def me(usuario: dict = Depends(get_current_user)):
    return usuario