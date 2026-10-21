"""Fila real no PostgreSQL; WAHA é sempre simulado, sem mensagens externas."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.helpdesk_db import HelpdeskSessionLocal, get_helpdesk_db, helpdesk_engine
from app.main import app
from app.models.chamado import Chamado, NotificacaoPendente
from app.routers import chamados as rotas
from app.routers.auth import limiter
from app.services import chamado_service as chamados
from app.services import notificacao_service as fila
from app.services import sla_monitor_service as sla


pytestmark = pytest.mark.integration
AGORA = datetime(2026, 10, 21, 15, tzinfo=timezone.utc)
AsyncClientReal = httpx.AsyncClient


@pytest.fixture
async def db(aplicar_migracoes):
    async with helpdesk_engine.connect() as conn:
        transaction = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False, autoflush=False, join_transaction_mode="create_savepoint") as session:
            yield session
        await transaction.rollback()


@pytest.fixture
def waha(monkeypatch):
    estado = SimpleNamespace(status=201, requests=[])

    def handler(request):
        estado.requests.append(request)
        return httpx.Response(estado.status, json={"id": "aceite-simulado"})

    monkeypatch.setattr(fila.settings, "waha_api_key", "chave-de-teste")
    monkeypatch.setattr(fila.settings, "waha_grupo_id", "grupo-teste@g.us")
    monkeypatch.setattr(fila.settings, "waha_grupo_diretoria_id", "")
    monkeypatch.setattr(fila, "_dentro_do_horario", lambda: True)
    monkeypatch.setattr(fila, "datetime", SimpleNamespace(now=lambda tz: AGORA.astimezone(tz)))
    monkeypatch.setattr(fila.httpx, "AsyncClient", lambda **kw: AsyncClientReal(transport=httpx.MockTransport(handler), **kw))
    return estado


async def pendente(db, **values):
    row = NotificacaoPendente(**{
        "chat_id": "grupo-teste@g.us", "mensagem": "Mensagem simulada",
        "proxima_tentativa_em": AGORA - timedelta(minutes=1), **values,
    })
    db.add(row)
    await db.commit()
    return row.id


async def chamado(db):
    row = Chamado(
        numero_chamado="F000000001", cliente_codigo=1, cliente_nome_snapshot="Teste",
        titulo="Teste de fila", prioridade_id=1, status_id=1,
        criado_por_codigo=10, criado_por_nome_snapshot="Técnico",
        prazo_sla=AGORA - timedelta(days=1),
    )
    db.add(row)
    await db.commit()
    return row.id


async def quantidade(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_falha_http_permanece_no_banco_e_sucesso_posterior_remove(db, waha):
    item_id = await pendente(db)
    waha.status = 503
    await fila.processar_fila_notificacoes(db)
    row = await db.get(NotificacaoPendente, item_id)
    assert row.tentativas == 1
    assert row.ultimo_erro == "HTTP 503"
    assert row.proxima_tentativa_em == AGORA + timedelta(minutes=1)
    # Ainda não chegou a hora da nova tentativa.
    waha.status = 201
    await fila.processar_fila_notificacoes(db)
    assert len(waha.requests) == 1
    row.proxima_tentativa_em = AGORA
    await db.commit()
    await fila.processar_fila_notificacoes(db)
    assert await db.get(NotificacaoPendente, item_id) is None
    assert len(waha.requests) == 2


async def test_mensagem_com_tentativa_futura_nao_bloqueia_as_demais(db, waha):
    primeiro = await pendente(db, proxima_tentativa_em=AGORA + timedelta(hours=1))
    segundo = await pendente(db)
    await fila.processar_fila_notificacoes(db)
    assert await db.get(NotificacaoPendente, primeiro) is not None
    assert await db.get(NotificacaoPendente, segundo) is None
    assert len(waha.requests) == 1


async def test_lote_limita_trabalho_sem_descartar_o_restante(db, waha, monkeypatch):
    monkeypatch.setattr(fila, "TAMANHO_LOTE", 2)
    for _ in range(3):
        await pendente(db)
    await fila.processar_fila_notificacoes(db)
    assert len(waha.requests) == 2
    assert await quantidade(db, NotificacaoPendente) == 1


async def test_default_da_migracao_aceita_insert_antigo(db):
    row = NotificacaoPendente(chat_id="grupo-teste@g.us", mensagem="Formato anterior")
    db.add(row)
    await db.flush()
    assert row.tentativas == 0
    assert row.proxima_tentativa_em is not None
    assert row.ultima_tentativa_em is None and row.ultimo_erro is None


@pytest.fixture
def sessao_monitor(db, monkeypatch):
    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(sla, "HelpdeskSessionLocal", session)


async def test_alerta_sla_e_fila_sao_confirmados_juntos_e_nao_repetem(db, waha, sessao_monitor):
    chamado_id = await chamado(db)
    await sla.verificar_sla_e_notificar()
    row = await db.get(Chamado, chamado_id)
    assert row.sla_notificado_status == "estourado"
    assert await quantidade(db, NotificacaoPendente) == 1
    await sla.verificar_sla_e_notificar()
    assert await quantidade(db, NotificacaoPendente) == 1
    assert waha.requests == []  # Monitor apenas enfileira, não faz HTTP.


async def test_sem_destino_alerta_sla_nao_e_marcado(db, waha, sessao_monitor, monkeypatch):
    monkeypatch.setattr(fila.settings, "waha_grupo_id", "")
    chamado_id = await chamado(db)
    await sla.verificar_sla_e_notificar()
    assert (await db.get(Chamado, chamado_id)).sla_notificado_status is None
    assert await quantidade(db, NotificacaoPendente) == 0


async def test_commit_falha_reverte_fila_e_marcador_do_sla(db, waha, sessao_monitor, monkeypatch):
    chamado_id = await chamado(db)
    with monkeypatch.context() as patch:
        patch.setattr(db, "commit", AsyncMock(side_effect=RuntimeError("falha simulada de commit")))
        with pytest.raises(RuntimeError):
            await sla.verificar_sla_e_notificar()
        await db.rollback()
    assert (await db.get(Chamado, chamado_id)).sla_notificado_status is None
    assert await quantidade(db, NotificacaoPendente) == 0


@pytest.fixture
def http_db(db):
    async def dependency():
        try:
            yield db
        except Exception:
            await db.rollback()
            raise

    app.dependency_overrides[get_helpdesk_db] = dependency
    app.dependency_overrides[get_current_user] = lambda: {"codigo": 10, "login": "teste", "nome": "Técnico"}
    limiter.reset()
    yield
    app.dependency_overrides.pop(get_helpdesk_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    limiter.reset()


@pytest.mark.parametrize("acao,dados", [("status", {"status_id": "4"}), ("responsavel", {"responsavel_codigo": "10"})])
async def test_erro_ao_enfileirar_reverte_alteracao_do_chamado(client, db, waha, http_db, monkeypatch, acao, dados):
    chamado_id = await chamado(db)
    monkeypatch.setattr(chamados, "listar_usuarios_helpdesk", AsyncMock(return_value=[{"codigo": 10, "nome": "Técnico"}]))
    monkeypatch.setattr(rotas, "buscar_numero_whatsapp", AsyncMock(return_value="550000000000"))
    monkeypatch.setattr(fila, "_enviar", AsyncMock(side_effect=RuntimeError("fila indisponível")))
    with pytest.raises(RuntimeError):
        await client.post(f"/chamados/{chamado_id}/{acao}", data=dados)
    row = await db.get(Chamado, chamado_id)
    assert row.status_id == 1
    assert row.responsavel_codigo is None
    assert await quantidade(db, NotificacaoPendente) == 0


async def test_erro_ao_enfileirar_reverte_criacao_inteira(client, db, waha, http_db, monkeypatch):
    monkeypatch.setattr(chamados, "buscar_cliente_por_codigo", AsyncMock(return_value={"codigo": 1, "nome": "Teste"}))
    monkeypatch.setattr(rotas, "listar_responsaveis_possiveis", AsyncMock(return_value=[{"codigo": 10, "nome": "Técnico"}]))
    monkeypatch.setattr(fila, "_enviar", AsyncMock(side_effect=RuntimeError("fila indisponível")))
    with pytest.raises(RuntimeError):
        await client.post("/chamados/novo", data={
            "cliente_codigo": "1", "titulo": "Teste de criação", "categoria_ids": "1",
            "prioridade_id": "1", "responsavel_codigo": "10", "codigo_rastreio_envio": "AA123456789BR",
        })
    assert await quantidade(db, Chamado) == 0
    assert await quantidade(db, NotificacaoPendente) == 0


async def test_repetir_status_ou_responsavel_nao_enfileira_novo_aviso(client, db, waha, http_db, monkeypatch):
    chamado_id = await chamado(db)
    monkeypatch.setattr(chamados, "listar_usuarios_helpdesk", AsyncMock(return_value=[{"codigo": 10, "nome": "Técnico"}]))
    monkeypatch.setattr(rotas, "buscar_numero_whatsapp", AsyncMock(return_value="550000000000"))
    for acao, dados in [("status", {"status_id": "4"}), ("responsavel", {"responsavel_codigo": "10"})]:
        assert (await client.post(f"/chamados/{chamado_id}/{acao}", data=dados)).status_code == 200
        total = await quantidade(db, NotificacaoPendente)
        assert (await client.post(f"/chamados/{chamado_id}/{acao}", data=dados)).status_code == 200
        assert await quantidade(db, NotificacaoPendente) == total
    assert waha.requests == []


async def test_dois_processadores_nao_enviam_a_mesma_linha(aplicar_migracoes, waha, monkeypatch):
    # Este teste precisa de linhas confirmadas visíveis em duas conexões reais.
    # Os demais usam rollback externo; aqui a limpeza é explícita no finally.
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def handler(request):
        requests.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(201, json={"id": "aceite-simulado"})

    monkeypatch.setattr(fila, "TAMANHO_LOTE", 1)
    monkeypatch.setattr(fila.httpx, "AsyncClient", lambda **kw: AsyncClientReal(transport=httpx.MockTransport(handler), **kw))
    async with HelpdeskSessionLocal() as setup:
        item_id = await pendente(setup)
    task = None
    try:
        async with HelpdeskSessionLocal() as db1, HelpdeskSessionLocal() as db2:
            task = asyncio.create_task(fila.processar_fila_notificacoes(db1))
            await asyncio.wait_for(entered.wait(), timeout=5)
            await asyncio.wait_for(fila.processar_fila_notificacoes(db2), timeout=5)
            assert len(requests) == 1
            release.set()
            await asyncio.wait_for(task, timeout=5)
            assert await db2.get(NotificacaoPendente, item_id) is None
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        async with HelpdeskSessionLocal() as cleanup:
            await cleanup.execute(delete(NotificacaoPendente).where(NotificacaoPendente.id == item_id))
            await cleanup.commit()
