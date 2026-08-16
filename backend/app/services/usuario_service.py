"""
Consulta de usuários com acesso ao Help Desk (perfil_codigo = 1),
usada para listar possíveis responsáveis por um chamado.
"""
from app.database.legacy_db import get_legacy_pool

PERFIL_HELPDESK = 1

_QUERY_LISTAR = """
    SELECT codigo, nome
    FROM usuario
    WHERE perfil_codigo = $1 AND ativo = true
    ORDER BY nome
"""


async def listar_usuarios_helpdesk() -> list[dict]:
    pool = await get_legacy_pool()
    async with pool.acquire() as conn:
        registros = await conn.fetch(_QUERY_LISTAR, PERFIL_HELPDESK)
    return [dict(r) for r in registros]