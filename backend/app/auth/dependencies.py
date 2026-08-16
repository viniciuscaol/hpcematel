"""
Dependências do FastAPI que validam o cookie de sessão.

get_current_user: usada em rotas de página/HTMX — se a sessão estiver
ausente ou expirada, levanta NaoAutenticado, capturada globalmente em
main.py para redirecionar ao /login (em vez de devolver um JSON cru).

get_current_user_optional: usada em rotas onde "não logado" é um estado
válido (ex: tela de login decidir se redireciona para o dashboard).
"""
from fastapi import Cookie

from app.auth.security import decode_access_token


class NaoAutenticado(Exception):
    """Sessão ausente ou expirada — tratada globalmente para redirecionar ao /login."""


def _payload_para_usuario(payload: dict) -> dict:
    return {
        "codigo": int(payload["sub"]),
        "login": payload["login"],
        "nome": payload["nome"],
    }


async def get_current_user(session_token: str | None = Cookie(default=None)) -> dict:
    if session_token is None:
        raise NaoAutenticado()

    payload = decode_access_token(session_token)
    if payload is None:
        raise NaoAutenticado()

    return _payload_para_usuario(payload)


async def get_current_user_optional(session_token: str | None = Cookie(default=None)) -> dict | None:
    if session_token is None:
        return None
    payload = decode_access_token(session_token)
    if payload is None:
        return None
    return _payload_para_usuario(payload)