"""Regressões de estado e validação, sem acesso ao banco legado."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.chamado import Prioridade, Status
from app.services import chamado_service as service
from app.templates_config import templates


AGORA = datetime(2026, 10, 21, 15, tzinfo=timezone.utc)


@pytest.fixture
def contexto(monkeypatch):
    chamado = SimpleNamespace(
        id=1, status_id=4, prioridade_id=1, prazo_sla=AGORA - timedelta(hours=2),
        resolvido_em=AGORA - timedelta(hours=1), encerrado_em=None,
        fechado_latitude=-12.9, fechado_longitude=-38.5,
        sla_pausado_em=None, sla_notificado_status="estourado",
    )
    statuses = {
        1: SimpleNamespace(id=1, nome="Aberto", ativo=True, pausa_sla=False, finalizador=False),
        3: SimpleNamespace(id=3, nome="Aguardando cliente", ativo=True, pausa_sla=True, finalizador=False),
        4: SimpleNamespace(id=4, nome="Resolvido", ativo=True, pausa_sla=False, finalizador=True),
        5: SimpleNamespace(id=5, nome="Cancelado", ativo=True, pausa_sla=False, finalizador=True),
        6: SimpleNamespace(id=6, nome="Aguardando Correios", ativo=True, pausa_sla=True, finalizador=False),
    }
    priorities = {
        1: SimpleNamespace(id=1, nome="Baixa", ativo=True, sla_horas=48),
        2: SimpleNamespace(id=2, nome="Alta", ativo=True, sla_horas=8),
    }

    async def get(model, item_id):
        return (statuses if model is Status else priorities).get(item_id)

    db = SimpleNamespace(get=AsyncMock(side_effect=get), add=Mock(), commit=AsyncMock(), expire_all=Mock())
    monkeypatch.setattr(service, "obter_chamado", AsyncMock(return_value=chamado))
    monkeypatch.setattr(service, "datetime", SimpleNamespace(now=lambda tz: AGORA))
    return SimpleNamespace(chamado=chamado, db=db, statuses=statuses, priorities=priorities)


async def test_reabertura_limpa_fechamento_e_permite_novo_alerta_sem_novo_prazo(contexto):
    c, db = contexto.chamado, contexto.db
    prazo = c.prazo_sla
    await service.atualizar_status(db, 1, 1, 10, "Técnico")
    assert c.resolvido_em is None and c.encerrado_em is None
    assert c.fechado_latitude is None and c.fechado_longitude is None
    assert c.prazo_sla == prazo
    assert c.sla_notificado_status is None
    eventos = [call.args[0] for call in db.add.call_args_list]
    anterior = next(e for e in eventos if e.campo_alterado == "fechamento_anterior")
    assert "Resolvido" in anterior.valor_anterior
    assert "21/10/2026 11:00:00" in anterior.valor_anterior
    assert "-12.9, -38.5" in anterior.valor_anterior
    db.commit.assert_awaited_once()


async def test_reabrir_cancelado_limpa_data_de_cancelamento(contexto):
    c = contexto.chamado
    c.status_id, c.resolvido_em, c.encerrado_em = 5, None, AGORA - timedelta(days=1)
    await service.atualizar_status(contexto.db, 1, 1, 10, "Técnico")
    assert c.encerrado_em is None and c.resolvido_em is None


@pytest.mark.parametrize("latitude,longitude", [(None, None), (-13.0, -38.0)])
async def test_nova_resolucao_registra_data_e_local_atuais(contexto, latitude, longitude):
    c = contexto.chamado
    await service.atualizar_status(contexto.db, 1, 1, 10, "Técnico")
    await service.atualizar_status(contexto.db, 1, 4, 10, "Técnico", latitude, longitude)
    assert c.resolvido_em == AGORA
    assert c.encerrado_em is None
    assert (c.fechado_latitude, c.fechado_longitude) == (latitude, longitude)


async def test_resolvido_para_cancelado_preserva_historico_sem_continuar_resolvido(contexto):
    c = contexto.chamado
    await service.atualizar_status(contexto.db, 1, 5, 10, "Técnico")
    assert c.resolvido_em is None
    assert c.encerrado_em == AGORA
    assert c.fechado_latitude is None and c.fechado_longitude is None


async def test_repetir_status_nao_modifica_fechamento_nem_duplica_historico(contexto):
    anterior = contexto.chamado.resolvido_em
    await service.atualizar_status(contexto.db, 1, 4, 10, "Técnico")
    assert contexto.chamado.resolvido_em == anterior
    contexto.db.add.assert_not_called()
    contexto.db.commit.assert_not_awaited()


async def test_troca_entre_pausas_preserva_inicio_e_retomada_estende_uma_vez(contexto):
    c = contexto.chamado
    c.status_id = 3
    c.sla_pausado_em = AGORA - timedelta(hours=6)
    inicio, prazo = c.sla_pausado_em, c.prazo_sla
    await service.atualizar_status(contexto.db, 1, 6, 10, "Técnico")
    assert c.sla_pausado_em == inicio and c.prazo_sla == prazo
    await service.atualizar_status(contexto.db, 1, 1, 10, "Técnico")
    assert c.prazo_sla == prazo + timedelta(hours=6)
    assert c.sla_pausado_em is None
    await service.atualizar_status(contexto.db, 1, 1, 10, "Técnico")
    assert c.prazo_sla == prazo + timedelta(hours=6)


async def test_entrada_em_pausa_registra_inicio_sem_recalcular_prazo(contexto):
    c = contexto.chamado
    c.status_id = 1
    prazo = c.prazo_sla
    await service.atualizar_status(contexto.db, 1, 3, 10, "Técnico")
    assert c.sla_pausado_em == AGORA and c.prazo_sla == prazo


@pytest.mark.parametrize("inativo", [False, True])
async def test_status_inexistente_ou_inativo_nao_salva(contexto, inativo):
    if inativo:
        contexto.statuses[3].ativo = False
    with pytest.raises(service.OpcaoChamadoInvalida):
        await service.atualizar_status(contexto.db, 1, 3 if inativo else 999, 10, "Técnico")
    assert contexto.chamado.status_id == 4
    contexto.db.add.assert_not_called()
    contexto.db.commit.assert_not_awaited()


@pytest.mark.parametrize("tipo", ["inexistente", "inativa", "sla_zero", "sla_negativo"])
async def test_prioridade_invalida_nao_salva(contexto, tipo):
    if tipo == "inativa":
        contexto.priorities[2].ativo = False
    if tipo in {"sla_zero", "sla_negativo"}:
        contexto.priorities[2].sla_horas = 0 if tipo == "sla_zero" else -1
    with pytest.raises(service.OpcaoChamadoInvalida):
        await service.atualizar_prioridade(contexto.db, 1, 999 if tipo == "inexistente" else 2, 10, "Técnico")
    assert contexto.chamado.prioridade_id == 1
    contexto.db.add.assert_not_called()
    contexto.db.commit.assert_not_awaited()


async def test_trocar_prioridade_preserva_prazo_e_registra_historico(contexto):
    prazo = contexto.chamado.prazo_sla
    await service.atualizar_prioridade(contexto.db, 1, 2, 10, "Técnico")
    assert contexto.chamado.prazo_sla == prazo
    assert contexto.chamado.prioridade_id == 2
    evento = contexto.db.add.call_args.args[0]
    assert (evento.campo_alterado, evento.valor_anterior, evento.valor_novo) == ("prioridade", "Baixa", "Alta")


async def test_criacao_com_prioridade_inexistente_falha_antes_de_gravar(contexto, monkeypatch):
    monkeypatch.setattr(service, "buscar_cliente_por_codigo", AsyncMock(return_value={"codigo": 1, "nome": "Teste"}))
    with pytest.raises(service.OpcaoChamadoInvalida):
        await service.criar_chamado(
            contexto.db, cliente_codigo=1, titulo="Teste", descricao=None,
            categoria_ids=[1], prioridade_id=999, responsavel_codigo=10,
            responsavel_nome="Técnico", criado_por_codigo=10, criado_por_nome="Técnico",
        )
    contexto.db.add.assert_not_called()
    contexto.db.commit.assert_not_awaited()


@pytest.mark.parametrize("papel,exibe_local", [("CAC", False), ("TECNICO", False), ("ADMIN", True)])
def test_local_do_fechamento_anterior_so_aparece_para_admin(papel, exibe_local):
    evento = SimpleNamespace(
        criado_em=AGORA, usuario_nome_snapshot="Técnico", campo_alterado="fechamento_anterior",
        valor_anterior="Resolvido; Resolvido em: 21/10/2026 11:00:00; Local: -12.9, -38.5", valor_novo="Aberto",
    )
    html = templates.env.get_template("partials/chamado_timeline.html").render(
        usuario={"papel": papel}, chamado=SimpleNamespace(historico=[evento], interacoes=[], anexos=[]),
    )
    assert "Resolvido em: 21/10/2026 11:00:00" in html
    assert ("-12.9, -38.5" in html) is exibe_local
