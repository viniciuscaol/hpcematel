"""Disputa real por um chamado em conexões PostgreSQL independentes."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Chamado, ChamadoHistorico
from app.services import chamado_service as chamados


pytestmark = pytest.mark.integration


@pytest.fixture
async def chamado_id(aplicar_migracoes):
    # Linhas confirmadas são necessárias para testar visibilidade e locks
    # entre conexões. A limpeza inclui o histórico em caso de falha do teste.
    async with HelpdeskSessionLocal() as db:
        row = Chamado(
            numero_chamado="A" + uuid4().hex[:9], cliente_codigo=1,
            cliente_nome_snapshot="Cliente de teste", titulo="Disputa de atendimento",
            prioridade_id=1, status_id=1, criado_por_codigo=30,
            criado_por_nome_snapshot="Operador", responsavel_codigo=30,
            responsavel_nome_snapshot="Responsável anterior",
            prazo_sla=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(row)
        await db.commit()
        item_id = row.id
    try:
        yield item_id
    finally:
        async with HelpdeskSessionLocal() as db:
            await db.execute(delete(ChamadoHistorico).where(ChamadoHistorico.chamado_id == item_id))
            await db.execute(delete(Chamado).where(Chamado.id == item_id))
            await db.commit()


async def historico(db, chamado_id):
    return list((await db.execute(select(ChamadoHistorico).where(ChamadoHistorico.chamado_id == chamado_id))).scalars())


@pytest.mark.parametrize("segundo_usuario", [10, 20])
async def test_repeticao_nao_troca_responsavel_nem_duplica_historico(chamado_id, segundo_usuario):
    async with HelpdeskSessionLocal() as db:
        vencedor = await chamados.assumir_chamado(db, chamado_id, 10, "Técnico 10")
        assert (vencedor.status_id, vencedor.responsavel_codigo) == (2, 10)
        with pytest.raises(chamados.ChamadoIndisponivel):
            await chamados.assumir_chamado(db, chamado_id, segundo_usuario, "Outro técnico")
        await db.rollback()
        salvo = await db.get(Chamado, chamado_id)
        assert (salvo.status_id, salvo.responsavel_codigo) == (2, 10)
        eventos = await historico(db, chamado_id)
        assert len(eventos) == 2
        assert {e.usuario_codigo for e in eventos} == {10}
        atribuicao = next(e for e in eventos if e.campo_alterado == "responsavel")
        assert (atribuicao.valor_anterior, atribuicao.valor_novo) == ("Responsável anterior", "Técnico 10")


@pytest.mark.parametrize("mudanca", [{"status_id": 2}, {"excluido": True}])
async def test_revalida_estado_mesmo_se_guard_carregou_versao_antiga(chamado_id, mudanca):
    async with HelpdeskSessionLocal() as antigo, HelpdeskSessionLocal() as atual:
        cache = await chamados.obter_chamado(antigo, chamado_id)
        assert cache.status_id == 1 and cache.excluido is False
        await atual.execute(update(Chamado).where(Chamado.id == chamado_id).values(**mudanca))
        await atual.commit()
        with pytest.raises(chamados.ChamadoIndisponivel):
            await chamados.assumir_chamado(antigo, chamado_id, 10, "Técnico 10")
        await antigo.rollback()
        salvo = await antigo.get(Chamado, chamado_id)
        assert salvo.responsavel_codigo == 30
        assert await historico(antigo, chamado_id) == []


async def test_falha_ao_confirmar_reverte_responsavel_status_e_historico(chamado_id, monkeypatch):
    async with HelpdeskSessionLocal() as db:
        async def falhar():
            await db.flush()
            raise RuntimeError("Falha simulada antes do commit")

        monkeypatch.setattr(db, "commit", falhar)
        with pytest.raises(RuntimeError):
            await chamados.assumir_chamado(db, chamado_id, 10, "Técnico 10")
        await db.rollback()
        salvo = await db.get(Chamado, chamado_id)
        assert (salvo.status_id, salvo.responsavel_codigo) == (1, 30)
        assert await historico(db, chamado_id) == []


async def test_dois_tecnicos_simultaneos_tem_apenas_um_vencedor(chamado_id, monkeypatch):
    antes_do_commit, liberar_commit = asyncio.Event(), asyncio.Event()
    async with HelpdeskSessionLocal() as primeiro, HelpdeskSessionLocal() as segundo:
        # Simula a sessão da segunda rota, que já leu o cartão no guard.
        cache = await chamados.obter_chamado(segundo, chamado_id)
        assert cache.status_id == 1
        pid = (await segundo.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        commit_original = primeiro.commit

        async def commit_controlado():
            antes_do_commit.set()
            await liberar_commit.wait()
            await commit_original()

        monkeypatch.setattr(primeiro, "commit", commit_controlado)
        vencedor = asyncio.create_task(chamados.assumir_chamado(primeiro, chamado_id, 10, "Técnico 10"))
        concorrente = None
        try:
            await asyncio.wait_for(antes_do_commit.wait(), timeout=5)
            concorrente = asyncio.create_task(chamados.assumir_chamado(segundo, chamado_id, 20, "Técnico 20"))

            async def aguardar_lock_real():
                async with HelpdeskSessionLocal() as monitor:
                    while True:
                        if concorrente.done():
                            raise AssertionError("O concorrente não esperou a transação vencedora")
                        espera = (await monitor.execute(
                            text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"), {"pid": pid},
                        )).scalar_one_or_none()
                        await monitor.rollback()
                        if espera == "Lock":
                            return
                        await asyncio.sleep(0.02)

            await asyncio.wait_for(aguardar_lock_real(), timeout=5)
            liberar_commit.set()
            assert (await asyncio.wait_for(vencedor, timeout=5)).responsavel_codigo == 10
            with pytest.raises(chamados.ChamadoIndisponivel):
                await asyncio.wait_for(concorrente, timeout=5)
            await segundo.rollback()
            salvo = await segundo.get(Chamado, chamado_id)
            assert (salvo.status_id, salvo.responsavel_codigo) == (2, 10)
            eventos = await historico(segundo, chamado_id)
            assert len(eventos) == 2 and {e.usuario_codigo for e in eventos} == {10}
        finally:
            liberar_commit.set()
            tasks = [task for task in (vencedor, concorrente) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
