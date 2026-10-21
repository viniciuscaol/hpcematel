"""Testes HTTP: permissão real no backend, sem depender de botões da tela."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.auth.security import create_access_token
from app.auth import authorization
from app.database.helpdesk_db import get_helpdesk_db
from app.main import app
from app.routers import chamados
from app.routers.auth import limiter


ACOES = [
    ("status", {"status_id": "2"}, "atualizar_status"),
    ("categoria", {"categoria_ids": "1"}, "atualizar_categorias"),
    ("prioridade", {"prioridade_id": "1"}, "atualizar_prioridade"),
    ("responsavel", {"responsavel_codigo": "10"}, "atualizar_responsavel"),
    ("interacao", {"texto": "Andamento de teste"}, "adicionar_interacao"),
    ("excluir", {}, "excluir_chamado"),
    ("anexos", {}, "salvar_anexo"),
    ("anexos/7/excluir", {}, "excluir_anexo"),
    ("assumir", {}, "assumir_chamado"),
    ("rastreio", {"codigo_rastreio_envio": "AA123456789BR"}, "salvar_rastreios"),
]


@pytest.fixture
def contexto(monkeypatch):
    db = AsyncMock()
    papel = AsyncMock(return_value="CAC")
    obter = AsyncMock(return_value=SimpleNamespace(id=1, excluido=False))

    async def banco_fake():
        yield db

    app.dependency_overrides[get_helpdesk_db] = banco_fake
    monkeypatch.setattr(authorization, "buscar_papel_usuario", papel)
    monkeypatch.setattr(chamados, "obter_chamado", obter)
    limiter.reset()
    yield SimpleNamespace(db=db, papel=papel, obter=obter)
    app.dependency_overrides.pop(get_helpdesk_db, None)
    limiter.reset()


def autenticar(client):
    token = create_access_token(usuario_codigo=10, login="teste", nome="Usuário Teste")
    client.cookies.set("session_token", token)


async def enviar(client, acao, dados):
    if acao == "anexos":
        return await client.post("/chamados/1/anexos", files={"arquivo": ("teste.pdf", b"%PDF-teste", "application/pdf")})
    return await client.post(f"/chamados/1/{acao}", data=dados)


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
@pytest.mark.parametrize("acao,servico", [("excluir", "excluir_chamado"), ("anexos/7/excluir", "excluir_anexo")])
async def test_exclusao_exige_papel_no_backend(client, contexto, monkeypatch, papel, esperado, acao, servico):
    autenticar(client)
    contexto.papel.return_value = papel
    executar = AsyncMock(return_value=None)
    monkeypatch.setattr(chamados, servico, executar)

    resposta = await enviar(client, acao, {})

    assert resposta.status_code == esperado
    if esperado == 403:
        executar.assert_not_awaited()
    else:
        executar.assert_awaited_once()


@pytest.mark.parametrize("acao,dados,servico", ACOES)
@pytest.mark.parametrize("ausente,esperado", [(False, 409), (True, 404)])
async def test_nao_altera_chamado_excluido_ou_inexistente(client, contexto, monkeypatch, acao, dados, servico, ausente, esperado):
    autenticar(client)
    contexto.papel.return_value = "ADMIN"
    contexto.obter.return_value = None if ausente else SimpleNamespace(id=1, excluido=True)
    executar = AsyncMock()
    monkeypatch.setattr(chamados, servico, executar)

    resposta = await enviar(client, acao, dados)

    assert resposta.status_code == esperado
    executar.assert_not_awaited()
    contexto.db.commit.assert_not_awaited()


@pytest.mark.parametrize("acao,dados,servico", ACOES)
async def test_alteracoes_exigem_sessao(client, contexto, monkeypatch, acao, dados, servico):
    executar = AsyncMock()
    monkeypatch.setattr(chamados, servico, executar)

    resposta = await enviar(client, acao, dados)

    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith("/login?")
    executar.assert_not_awaited()
    contexto.obter.assert_not_awaited()


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
async def test_assumir_exige_tecnico_ou_admin(client, contexto, monkeypatch, papel, esperado):
    autenticar(client)
    contexto.papel.return_value = papel
    executar = AsyncMock()
    monkeypatch.setattr(chamados, "assumir_chamado", executar)

    resposta = await enviar(client, "assumir", {})

    assert resposta.status_code == esperado
    assert executar.await_count == (0 if esperado == 403 else 1)
