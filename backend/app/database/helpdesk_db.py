"""
Conexão com o banco novo (helpdesk) — leitura e escrita.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

helpdesk_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

HelpdeskSessionLocal = async_sessionmaker(
    bind=helpdesk_engine,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_helpdesk_db():
    async with HelpdeskSessionLocal() as session:
        yield session