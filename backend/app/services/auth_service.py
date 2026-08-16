"""
Serviço de autenticação: consulta o usuário na base legada e valida
usuário/senha/perfil. Não conhece nada sobre HTTP, cookies ou JSON —
é usado tanto pela API (app/routers/auth.py) quanto pelas telas HTML
(app/routers/pages.py).
"""
from app.database.legacy_db import get_legacy_pool

PERFIL_HELPDESK = 1


class CredenciaisInvalidas(Exception):
    """Usuário não encontrado, senha errada ou usuário inativo."""


class SemPermissaoHelpDesk(Exception):
    """Usuário válido, mas sem perfil_codigo = 1."""


async def autenticar_usuario(login: str, senha: str) -> dict:
    pool = await get_legacy_pool()

    async with pool.acquire() as conn:
        usuario = await conn.fetchrow(
            """
            SELECT codigo, perfil_codigo, nome, login, senha, ativo
            FROM usuario
            WHERE login = $1
            LIMIT 1
            """,
            login,
        )

    if usuario is None:
        raise CredenciaisInvalidas()

    if usuario["senha"] != senha:
        raise CredenciaisInvalidas()

    if not usuario["ativo"]:
        raise CredenciaisInvalidas()

    if usuario["perfil_codigo"] != PERFIL_HELPDESK:
        raise SemPermissaoHelpDesk()

    return dict(usuario)