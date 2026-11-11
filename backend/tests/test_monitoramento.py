"""Acesso ao painel e às APIs de monitoramento respeita o papel do Help Desk."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.security import create_access_token
from app.auth import authorization
from app.database.helpdesk_db import get_helpdesk_db
from app.main import app
from app.routers.auth import limiter


@pytest.fixture
def contexto_monitoramento(monkeypatch):
    db = MagicMock()
    db.commit = AsyncMock()
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
    from app.models.monitoramento import MonitoramentoAcao, MonitoramentoAmostra, MonitoramentoEstado

    assert MonitoramentoAmostra.__tablename__ == "monitoramento_amostra"
    assert MonitoramentoAcao.__tablename__ == "monitoramento_acao"
    assert MonitoramentoEstado.__tablename__ == "monitoramento_estado"

async def test_acionamento_panico_audita_usuario_autenticado(client, contexto_monitoramento, monkeypatch):
    from app.routers import monitoramento

    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = "TECNICO"
    executar = AsyncMock(return_value=(True, "Script executado"))
    monkeypatch.setattr(monitoramento, "executar_panico", executar)

    resposta = await client.post(
        "/api/monitoramento/panico",
        data={"confirmacao": "REINICIAR", "senha": "senha-de-teste"},
    )

    assert resposta.status_code == 200
    executar.assert_awaited_once()
    assert executar.await_args.args[0] == "senha-de-teste"
    assert executar.await_args.args[1] is contexto_monitoramento.db
    assert executar.await_args.args[2]["login"] == "teste"
    registro = contexto_monitoramento.db.add.call_args.args[0]
    assert registro.usuario_codigo == 10
    assert registro.usuario_login == "teste"
    assert registro.usuario_nome == "Usuário Teste"
    assert registro.resultado == "sucesso"
    contexto_monitoramento.db.commit.assert_awaited_once()


async def test_confirmacao_invalida_e_auditada_sem_executar_panico(client, contexto_monitoramento, monkeypatch):
    from app.routers import monitoramento

    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = "ADMIN"
    executar = AsyncMock()
    monkeypatch.setattr(monitoramento, "executar_panico", executar)

    resposta = await client.post(
        "/api/monitoramento/panico",
        data={"confirmacao": "SIM", "senha": "senha-de-teste"},
    )

    assert resposta.status_code == 400
    executar.assert_not_awaited()
    registro = contexto_monitoramento.db.add.call_args.args[0]
    assert registro.usuario_codigo == 10
    assert registro.resultado == "falha"
    assert registro.detalhe == "Confirmação textual inválida"
    contexto_monitoramento.db.commit.assert_awaited_once()
