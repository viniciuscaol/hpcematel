"""
Envio de notificações para o WhatsApp via WAHA.

Só envia entre 8h e 19h (horário de Bahia). Fora desse horário, a
mensagem fica guardada em NotificacaoPendente e é enviada assim que o
horário permitido chegar, com o horário original registrado no texto.
"""
import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chamado import NotificacaoPendente
from app.utils.datas import FUSO_BAHIA

logger = logging.getLogger(__name__)

HORA_INICIO_PERMITIDA = 8
HORA_FIM_PERMITIDA = 19


def _dentro_do_horario() -> bool:
    agora = datetime.now(FUSO_BAHIA)
    return HORA_INICIO_PERMITIDA <= agora.hour < HORA_FIM_PERMITIDA


def _rotulo_cidade(cidade: str | None) -> str | None:
    if not cidade:
        return None
    if "salvador" in cidade.lower():
        return "Telemedicina"
    return cidade.split("/")[0].strip().title()


async def _enviar(db: AsyncSession, mensagem: str, chat_id: str | None = None) -> None:
    chat_id = chat_id or settings.waha_grupo_id
    if not settings.waha_api_key or not chat_id:
        logger.info("WAHA não configurado, pulando notificação.")
        return

    if not _dentro_do_horario():
        agora = datetime.now(FUSO_BAHIA)
        mensagem_com_hora = (
            f"{mensagem}\n\n_(ocorrido às {agora.strftime('%d/%m %H:%M')}, "
            f"fora do horário de notificações)_"
        )
        db.add(NotificacaoPendente(chat_id=chat_id, mensagem=mensagem_com_hora))
        await db.commit()
        return

    url = f"{settings.waha_api_url}/api/sendText"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resposta = await client.post(
                url,
                headers={"X-Api-Key": settings.waha_api_key},
                json={"session": settings.waha_sessao, "chatId": chat_id, "text": mensagem},
            )
            resposta.raise_for_status()
    except Exception:
        logger.exception("Falha ao enviar notificação para o WhatsApp.")


async def processar_fila_notificacoes(db: AsyncSession) -> None:
    """Envia as mensagens que ficaram na fila, se já estivermos no horário permitido."""
    if not _dentro_do_horario():
        return

    result = await db.execute(select(NotificacaoPendente).order_by(NotificacaoPendente.criado_em))
    pendentes = list(result.scalars().all())
    if not pendentes:
        return

    url = f"{settings.waha_api_url}/api/sendText"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for pendente in pendentes:
            try:
                resposta = await client.post(
                    url,
                    headers={"X-Api-Key": settings.waha_api_key},
                    json={"session": settings.waha_sessao, "chatId": pendente.chat_id, "text": pendente.mensagem},
                )
                resposta.raise_for_status()
                await db.delete(pendente)
            except Exception:
                logger.exception("Falha ao reenviar notificação pendente %s", pendente.id)
    await db.commit()


def _link(chamado_id: int) -> str:
    return f"{settings.app_base_url}/chamados/{chamado_id}"


async def notificar_novo_chamado(
    db: AsyncSession, chamado_id: int, cliente_nome: str, titulo: str, numero_chamado: str,
    prioridade_nome: str, categoria_nome: str, responsavel_nome: str,
) -> None:
    mensagem = (
        f"📋 *{cliente_nome}*\n{titulo}\n\n"
        f"Nº: {numero_chamado}\nCategoria: {categoria_nome}\nPrioridade: {prioridade_nome}\n"
        f"Responsável: {responsavel_nome}\n\n🔗 {_link(chamado_id)}"
    )
    await _enviar(db, mensagem)


async def notificar_mudanca_status(
    db: AsyncSession, chamado_id: int, cliente_nome: str, titulo: str, numero_chamado: str, status_nome: str,
) -> None:
    emoji = "✅" if status_nome.lower() == "resolvido" else "🔒"
    mensagem = (
        f"{emoji} *{cliente_nome}*\n{titulo}\n\nNº: {numero_chamado}\nStatus: {status_nome}\n\n🔗 {_link(chamado_id)}"
    )
    await _enviar(db, mensagem)


async def notificar_alerta_sla(
    db: AsyncSession, chamado_id: int, cliente_nome: str, titulo: str, numero_chamado: str,
    sla_status: str, responsavel_nome: str | None,
) -> None:
    if sla_status == "estourado":
        emoji, rotulo = "🔴", "SLA ESTOURADO"
    else:
        emoji, rotulo = "🟡", "SLA próximo do limite"
    mensagem = (
        f"{emoji} *{rotulo}*\n{cliente_nome} — {titulo}\n\n"
        f"Nº: {numero_chamado}\nResponsável: {responsavel_nome or 'Não atribuído'}\n\n🔗 {_link(chamado_id)}"
    )
    await _enviar(db, mensagem)


async def notificar_atribuicao_individual(
    db: AsyncSession, whatsapp_numero: str, responsavel_nome: str,
    chamado_id: int, cliente_nome: str, titulo: str, numero_chamado: str,
) -> None:
    mensagem = (
        f"👤 Olá, {responsavel_nome}!\nVocê foi atribuído a um chamado.\n\n"
        f"*{cliente_nome}*\n{titulo}\n\nNº: {numero_chamado}\n\n🔗 {_link(chamado_id)}"
    )
    await _enviar(db, mensagem, chat_id=f"{whatsapp_numero}@c.us")


async def notificar_atualizacao_rastreio(
    db: AsyncSession, chamado_id: int, cliente_nome: str, titulo: str, numero_chamado: str,
    tipo: str, codigo_rastreio: str, descricao_evento: str,
    cidade_remetente: str | None = None, cidade_destinatario: str | None = None,
) -> None:
    rotulo_tipo = "Envio" if tipo == "envio" else "Reverso (devolução)"

    remetente_label = _rotulo_cidade(cidade_remetente)
    destinatario_label = _rotulo_cidade(cidade_destinatario)
    linha_rota = ""
    if remetente_label or destinatario_label:
        linha_rota = f"Remetente: {remetente_label or '-'}\nDestinatário: {destinatario_label or '-'}\n"

    mensagem = (
        f"📦 *Atualização de rastreio* ({rotulo_tipo})\n{cliente_nome} — {titulo}\n\n"
        f"Nº chamado: {numero_chamado}\nCódigo: {codigo_rastreio}\n{linha_rota}"
        f"Status: {descricao_evento}\n\n🔗 {_link(chamado_id)}"
    )
    await _enviar(db, mensagem)

async def notificar_diretoria(
    db: AsyncSession, cliente_nome: str, titulo: str, status_nome: str,
) -> None:
    if not settings.waha_grupo_diretoria_id:
        return

    if status_nome.lower() == "resolvido":
        emoji = "✅"
    elif status_nome.lower() == "cancelado":
        emoji = "🔒"
    else:
        emoji = "📋"

    mensagem = (
        f"{emoji} {cliente_nome}\n"
        f"Solicitação: {titulo}\n"
        f"Status: {status_nome}"
    )
    await _enviar(db, mensagem, chat_id=settings.waha_grupo_diretoria_id)