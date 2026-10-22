"""Reenvio e marcadores de SLA sem serviços externos."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest

from app.services import notificacao_service as fila
from app.services import sla_monitor_service as sla


AGORA = datetime(2026, 10, 21, 15, tzinfo=timezone.utc)


def resultado(item):
    return SimpleNamespace(scalar_one_or_none=lambda: item)


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setattr(fila.settings, "waha_grupo_id", "grupo-teste@g.us")
    monkeypatch.setattr(fila.settings, "waha_api_key", "chave-apenas-de-teste")
    monkeypatch.setattr(fila, "_dentro_do_horario", Mock(return_value=True))
    monkeypatch.setattr(fila, "datetime", SimpleNamespace(now=lambda tz: AGORA.astimezone(tz)))
    db = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock(), delete=AsyncMock(), execute=AsyncMock())
    client = AsyncMock()
    client.post.return_value = httpx.Response(201, request=httpx.Request("POST", "http://waha/api/sendText"))
    manager = MagicMock()
    manager.__aenter__.return_value = client
    factory = Mock(return_value=manager)
    monkeypatch.setattr(fila.httpx, "AsyncClient", factory)
    pendente = SimpleNamespace(
        id=7, chat_id="grupo-teste@g.us", mensagem="Mensagem de teste",
        tentativas=0, ultima_tentativa_em=None, ultimo_erro=None, proxima_tentativa_em=AGORA,
    )
    db.execute.side_effect = [resultado(pendente), resultado(None)]
    return SimpleNamespace(db=db, client=client, factory=factory, pendente=pendente)


async def test_enfileira_antes_de_http_e_sem_commit_interno(ambiente):
    assert await fila._enviar(ambiente.db, "Mensagem") is True
    assert ambiente.db.add.call_args.args[0].mensagem == "Mensagem"
    ambiente.db.flush.assert_awaited_once()
    ambiente.db.commit.assert_not_awaited()
    ambiente.factory.assert_not_called()


async def test_sem_chave_conserva_mensagem_para_apos_configuracao(ambiente, monkeypatch):
    monkeypatch.setattr(fila.settings, "waha_api_key", "")
    assert await fila._enviar(ambiente.db, "Mensagem") is True
    await fila.processar_fila_notificacoes(ambiente.db)
    ambiente.db.execute.assert_not_awaited()
    ambiente.factory.assert_not_called()


async def test_sem_destino_nao_afirma_que_enfileirou(ambiente, monkeypatch):
    monkeypatch.setattr(fila.settings, "waha_grupo_id", "")
    assert await fila._enviar(ambiente.db, "Mensagem") is False
    ambiente.db.add.assert_not_called()
    ambiente.db.flush.assert_not_awaited()


async def test_fora_do_horario_guarda_ocorrencia_sem_tentar_envio(ambiente):
    fila._dentro_do_horario.return_value = False
    assert await fila._enviar(ambiente.db, "Mensagem") is True
    assert "21/10 12:00" in ambiente.db.add.call_args.args[0].mensagem
    await fila.processar_fila_notificacoes(ambiente.db)
    ambiente.client.post.assert_not_awaited()


async def test_sucesso_remove_item_e_confirma_sem_esperar_restante_do_lote(ambiente):
    await fila.processar_fila_notificacoes(ambiente.db)
    ambiente.db.delete.assert_awaited_once_with(ambiente.pendente)
    assert ambiente.db.commit.await_count == 2  # envio e consulta final vazia
    assert ambiente.pendente.tentativas == 1


@pytest.mark.parametrize("tipo,esperado", [("http", "HTTP 503"), ("timeout", "Timeout no WAHA"), ("conexao", "Falha de conexão com WAHA")])
async def test_falha_conserva_item_e_agenda_reenvio(ambiente, tipo, esperado):
    request = httpx.Request("POST", "http://waha/api/sendText")
    if tipo == "http":
        ambiente.client.post.return_value = httpx.Response(503, request=request, text="conteúdo que não deve ir para o erro")
    else:
        erro = httpx.ReadTimeout if tipo == "timeout" else httpx.ConnectError
        ambiente.client.post.side_effect = erro("dado sensível que não deve ser persistido", request=request)
    await fila.processar_fila_notificacoes(ambiente.db)
    ambiente.db.delete.assert_not_awaited()
    assert ambiente.pendente.ultimo_erro == esperado
    assert ambiente.pendente.proxima_tentativa_em == AGORA + timedelta(minutes=1)
    assert ambiente.pendente.ultima_tentativa_em == AGORA
    ambiente.db.commit.assert_awaited()


@pytest.mark.parametrize("anteriores,minutos", [(1, 2), (3, 8), (5, 30), (10000, 30)])
async def test_intervalo_cresce_e_tem_limite(ambiente, anteriores, minutos):
    ambiente.pendente.tentativas = anteriores
    ambiente.client.post.side_effect = httpx.ConnectError("offline")
    await fila.processar_fila_notificacoes(ambiente.db)
    assert ambiente.pendente.proxima_tentativa_em == AGORA + timedelta(minutes=minutos)


async def test_erro_do_commit_nao_e_mascarado_como_envio_confirmado(ambiente):
    ambiente.db.commit.side_effect = RuntimeError("banco indisponível")
    with pytest.raises(RuntimeError):
        await fila.processar_fila_notificacoes(ambiente.db)
    assert ambiente.client.post.await_count == 1


async def test_interrompe_lote_ao_terminar_janela_de_envio(ambiente):
    fila._dentro_do_horario.side_effect = [True, False]
    await fila.processar_fila_notificacoes(ambiente.db)
    ambiente.db.execute.assert_not_awaited()
    ambiente.client.post.assert_not_awaited()


@pytest.mark.parametrize("enfileirada", [False, True])
async def test_sla_so_marca_estado_que_entrou_na_fila(monkeypatch, enfileirada):
    chamado = SimpleNamespace(
        id=1, sla_status="estourado", sla_notificado_status=None, cliente_nome_snapshot="Teste",
        titulo="Teste", numero_chamado="TESTE", responsavel_nome_snapshot=None,
    )
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [4, 5])),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [chamado])),
    ]
    manager = MagicMock()
    manager.__aenter__.return_value = db
    monkeypatch.setattr(sla, "HelpdeskSessionLocal", Mock(return_value=manager))
    monkeypatch.setattr(sla, "aplicar_status_sla", AsyncMock())
    monkeypatch.setattr(sla, "notificar_alerta_sla", AsyncMock(return_value=enfileirada))
    await sla.verificar_sla_e_notificar()
    assert chamado.sla_notificado_status == ("estourado" if enfileirada else None)
    db.commit.assert_awaited_once()
