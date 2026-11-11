"""Acesso ao painel e às APIs de monitoramento respeita o papel do Help Desk."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.auth.security import create_access_token
from app.auth import authorization
from app.database.helpdesk_db import get_helpdesk_db
from app.main import app
from app.routers.auth import limiter


@pytest.fixture
def contexto_monitoramento(monkeypatch):
    db = AsyncMock()
    papel = AsyncMock(return_value="CAC")

    async def banco_fake():
        yield db

    app.dependency_overrides[get_helpdesk_db] = banco_fake
    monkeypatch.setattr(authorization, "buscar_papel_usuario", papel)
    limiter.reset()
    yield SimpleNamespace(db=db, papel=papel)
    app.dependency_overrides.pop(get_helpdesk_db, None)
    limiter.reset()


def autenticar_monitoramento(client):
    token = create_access_token(usuario_codigo=10, login="teste", nome="Usuário Teste")
    client.cookies.set("session_token", token)


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
async def test_painel_monitoramento_restringe_por_papel(client, contexto_monitoramento, papel, esperado):
    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = papel

    resposta = await client.get("/monitoramento")

    assert resposta.status_code == esperado
    if esperado == 200:
        assert "Botão de pânico" in resposta.text
        assert "/static/js/monitoramento.js" in resposta.text


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
async def test_api_status_monitoramento_restringe_por_papel(client, contexto_monitoramento, papel, esperado):
    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = papel

    resposta = await client.get("/api/monitoramento/status")

    assert resposta.status_code == esperado


async def test_painel_monitoramento_exige_sessao(client, contexto_monitoramento):
    resposta = await client.get("/monitoramento")

    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith("/login?")


def test_modelos_monitoramento_estao_registrados():
    from app.models.monitoramento import MonitoramentoAcao, MonitoramentoAmostra

    assert MonitoramentoAmostra.__tablename__ == "monitoramento_amostra"
    assert MonitoramentoAcao.__tablename__ == "monitoramento_acao"
