"""Indicadores e reabertura com PostgreSQL real, isolados por transação."""
from datetime import datetime, timedelta, timezone
from itertools import count
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.helpdesk_db import helpdesk_engine
from app.models.chamado import Chamado
from app.services import chamado_service as chamados
from app.services import dashboard_service as dashboard


pytestmark = pytest.mark.integration
AGORA = datetime(2026, 10, 21, 15, tzinfo=timezone.utc)


@pytest.fixture
async def db(aplicar_migracoes):
    # Os commits dos serviços liberam savepoints; o rollback externo remove
    # os dados de cada teste, inclusive quando uma asserção falha.
    async with helpdesk_engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, autoflush=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session
        await transaction.rollback()


@pytest.fixture
def criar(db):
    sequencia = count(1)

    async def factory(**values):
        chamado = Chamado(**{
            "numero_chamado": f"T{next(sequencia):09d}",
            "cliente_codigo": 1, "cliente_nome_snapshot": "Cliente de teste",
            "titulo": "Teste de SLA", "prioridade_id": 1, "status_id": 1,
            "criado_por_codigo": 10, "criado_por_nome_snapshot": "Técnico",
            "criado_em": AGORA - timedelta(hours=10),
            "prazo_sla": AGORA - timedelta(hours=1),
            **values,
        })
        db.add(chamado)
        await db.flush()
        return chamado

    return factory


@pytest.fixture
def relogio(monkeypatch):
    clock = {"agora": AGORA}
    fake = SimpleNamespace(now=lambda tz: clock["agora"])
    monkeypatch.setattr(chamados, "datetime", fake)
    monkeypatch.setattr(dashboard, "datetime", fake)
    return clock


async def test_dashboard_nao_conta_pausados_finalizados_ou_excluidos(db, criar, relogio):
    await criar(status_id=1)
    await criar(status_id=2, prazo_sla=AGORA)
    await criar(status_id=3)
    await criar(status_id=6)
    await criar(status_id=4)
    await criar(status_id=5)
    await criar(status_id=1, excluido=True)
    await criar(status_id=1, prazo_sla=AGORA + timedelta(hours=1))
    assert await dashboard.contar_sla_estourado(db) == 2


async def test_metricas_de_resolucao_ignoram_datas_antigas_em_outros_status(db, criar, relogio):
    # Resolvido no prazo (8h) e resolvido atrasado (10h).
    await criar(status_id=4, resolvido_em=AGORA - timedelta(hours=2))
    await criar(status_id=4, resolvido_em=AGORA)
    # Simulam inconsistências antigas sem exigir migração destrutiva dos dados.
    await criar(status_id=1, resolvido_em=AGORA - timedelta(hours=9))
    await criar(status_id=3, resolvido_em=AGORA - timedelta(hours=9))
    await criar(status_id=5, resolvido_em=AGORA - timedelta(hours=9))
    await criar(status_id=4, resolvido_em=AGORA, excluido=True)
    await criar(status_id=4, resolvido_em=None)
    assert await dashboard.tempo_medio_resolucao_horas(db) == 9.0
    assert await dashboard.percentual_sla_cumprido(db) == {"percentual": 50.0, "total": 2, "no_prazo": 1}


async def test_reabrir_e_resolver_novamente_persiste_fechamento_e_historico(db, criar, relogio):
    chamado = await criar(
        status_id=4, resolvido_em=AGORA - timedelta(hours=2),
        fechado_latitude=-12.9, fechado_longitude=-38.5,
        sla_notificado_status="estourado",
    )
    chamado_id, prazo = chamado.id, chamado.prazo_sla
    reaberto = await chamados.atualizar_status(db, chamado_id, 1, 10, "Técnico")
    assert reaberto.resolvido_em is None
    assert reaberto.fechado_latitude is None and reaberto.fechado_longitude is None
    assert reaberto.sla_notificado_status is None
    assert reaberto.prazo_sla == prazo
    assert any(h.campo_alterado == "fechamento_anterior" and "-12.9, -38.5" in h.valor_anterior for h in reaberto.historico)
    assert await dashboard.percentual_sla_cumprido(db) == {"percentual": None, "total": 0, "no_prazo": 0}

    relogio["agora"] = AGORA + timedelta(hours=1)
    resolvido = await chamados.atualizar_status(db, chamado_id, 4, 10, "Técnico")
    assert resolvido.resolvido_em == relogio["agora"]
    assert resolvido.fechado_latitude is None and resolvido.fechado_longitude is None
    assert resolvido.prazo_sla == prazo
    assert await dashboard.percentual_sla_cumprido(db) == {"percentual": 0.0, "total": 1, "no_prazo": 0}


async def test_metricas_de_resolucao_sem_chamados(db, relogio):
    assert await dashboard.tempo_medio_resolucao_horas(db) is None
    assert await dashboard.percentual_sla_cumprido(db) == {"percentual": None, "total": 0, "no_prazo": 0}
