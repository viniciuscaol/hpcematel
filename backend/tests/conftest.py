"""
Configuração compartilhada dos testes. Define as variáveis de ambiente
ANTES de qualquer módulo da aplicação ser importado (o config.py lê o
ambiente no momento do import), aplica as migrações do Alembic contra
um Postgres de teste, e disponibiliza um AsyncClient para testar rotas.
"""
import os
import subprocess

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test_user:test_pass@localhost:5433/test_helpdesk")
os.environ.setdefault("LEGACY_DATABASE_URL", "postgresql://placeholder:placeholder@localhost:5433/test_helpdesk")
os.environ.setdefault("JWT_SECRET_KEY", "chave-de-teste-nao-usar-em-producao")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def aplicar_migracoes():
    """Roda `alembic upgrade head` uma única vez, no início da sessão de testes."""
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=os.path.dirname(os.path.dirname(__file__)))
    yield


@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac