"""
Conexão SOMENTE LEITURA com o banco legado (telemedicina), via asyncpg puro.

Por que não usamos SQLAlchemy aqui: o servidor legado roda uma versão muito
antiga do PostgreSQL (v8), anterior à introdução do tipo `jsonb` (adicionado
só na versão 9.4). O dialeto asyncpg do SQLAlchemy tenta, ao abrir qualquer
conexão, registrar automaticamente um codec para o tipo `pg_catalog.jsonb` —
como esse tipo não existe nesse servidor, a conexão falha com
`ValueError: unknown type: pg_catalog.jsonb`, mesmo sem usarmos jsonb em
nenhuma query. Usando asyncpg diretamente evitamos essa checagem.
"""
import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def init_legacy_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.legacy_database_url,
            min_size=1,
            max_size=5,
        )


async def close_legacy_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_legacy_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool do banco legado não foi inicializado.")
    return _pool