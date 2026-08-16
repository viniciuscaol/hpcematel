"""
Criação e validação do token de sessão (JWT).
"""
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from app.config import settings


def create_access_token(*, usuario_codigo: int, login: str, nome: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(usuario_codigo),
        "login": login,
        "nome": nome,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None