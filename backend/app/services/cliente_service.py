"""
Busca de clientes na base legada (telemedicina).

A busca ignora maiúsculas/minúsculas e acentos. Como o servidor legado
roda PostgreSQL 8 (sem suporte à extensão `unaccent`, disponível só a
partir do Postgres 9.1) e temos acesso apenas de leitura (não podemos
criar extensões mesmo que existissem), a remoção de acento é feita "na
mão", encadeando REPLACE() — recurso disponível em qualquer versão do
Postgres, tanto na coluna quanto no termo pesquisado.
"""
from app.database.legacy_db import get_legacy_pool

STATUS_CLIENTE_ATIVO = 1

_MAPA_ACENTOS = [
    ("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"), ("ä", "a"),
    ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
    ("í", "i"), ("ì", "i"), ("î", "i"), ("ï", "i"),
    ("ó", "o"), ("ò", "o"), ("õ", "o"), ("ô", "o"), ("ö", "o"),
    ("ú", "u"), ("ù", "u"), ("û", "u"), ("ü", "u"),
    ("ç", "c"), ("ñ", "n"),
]


def _sem_acento_sql(expressao: str) -> str:
    resultado = f"lower({expressao})"
    for com_acento, sem_acento in _MAPA_ACENTOS:
        resultado = f"replace({resultado}, '{com_acento}', '{sem_acento}')"
    return resultado


_NOME_SEM_ACENTO = _sem_acento_sql("nome")
_TERMO_SEM_ACENTO = _sem_acento_sql("$1")

_QUERY_BUSCA = f"""
    SELECT codigo, nome, nome_contato, telefone_contato, email
    FROM cliente
    WHERE status_cliente = {_NOME_SEM_ACENTO} LIKE '%' || {_TERMO_SEM_ACENTO} || '%'
    ORDER BY nome
    LIMIT 20
"""

_QUERY_POR_CODIGO = f"""
    SELECT codigo, nome, nome_contato, telefone_contato, email
    FROM cliente
    WHERE codigo = $1
    LIMIT 1
"""


async def buscar_clientes(termo: str) -> list[dict]:
    termo = termo.strip()
    if len(termo) < 2:
        return []

    pool = await get_legacy_pool()
    async with pool.acquire() as conn:
        registros = await conn.fetch(_QUERY_BUSCA, termo)
    return [dict(r) for r in registros]


async def buscar_cliente_por_codigo(codigo: int) -> dict | None:
    pool = await get_legacy_pool()
    async with pool.acquire() as conn:
        registro = await conn.fetchrow(_QUERY_POR_CODIGO, codigo)
    return dict(registro) if registro else None