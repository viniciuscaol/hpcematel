"""
Envio de notificações para o grupo de WhatsApp via WAHA.

Uma falha aqui NUNCA deve impedir a criação/atualização de um chamado —
é uma notificação "melhor esforço": se o WhatsApp estiver fora do ar,
o chamado continua sendo criado/atualizado normalmente, só não notifica.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _enviar(mensagem: str) -> None:
    if not settings.waha_api_key or not settings.waha_grupo_id:
        logger.info("WAHA não configurado, pulando notificação.")
        return

    url = f"{settings.waha_api_url}/api/sendText"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resposta = await client.post(
                url,
                headers={"X-Api-Key": settings.waha_api_key},
                json={
                    "session": settings.waha_sessao,
                    "chatId": settings.waha_grupo_id,
                    "text": mensagem,
                },
            )
            resposta.raise_for_status()
    except Exception:
        logger.exception("Falha ao enviar notificação para o WhatsApp.")


def _link(chamado_id: int) -> str:
    return f"{settings.app_base_url}/chamados/{chamado_id}"


async def notificar_novo_chamado(
    chamado_id: int,
    cliente_nome: str,
    titulo: str,
    numero_chamado: str,
    prioridade_nome: str,
    categoria_nome: str,
    responsavel_nome: str,
) -> None:
    mensagem = (
        f"📋 *{cliente_nome}*\n"
        f"{titulo}\n\n"
        f"Nº: {numero_chamado}\n"
        f"Categoria: {categoria_nome}\n"
        f"Prioridade: {prioridade_nome}\n"
        f"Responsável: {responsavel_nome}\n\n"
        f"🔗 {_link(chamado_id)}"
    )
    await _enviar(mensagem)


async def notificar_mudanca_status(
    chamado_id: int,
    cliente_nome: str,
    titulo: str,
    numero_chamado: str,
    status_nome: str,
) -> None:
    emoji = "✅" if status_nome.lower() == "resolvido" else "🔒"
    mensagem = (
        f"{emoji} *{cliente_nome}*\n"
        f"{titulo}\n\n"
        f"Nº: {numero_chamado}\n"
        f"Status: {status_nome}\n\n"
        f"🔗 {_link(chamado_id)}"
    )
    await _enviar(mensagem)


async def notificar_alerta_sla(
    chamado_id: int,
    cliente_nome: str,
    titulo: str,
    numero_chamado: str,
    sla_status: str,
    responsavel_nome: str | None,
) -> None:
    if sla_status == "estourado":
        emoji, rotulo = "🔴", "SLA ESTOURADO"
    else:
        emoji, rotulo = "🟡", "SLA próximo do limite"

    mensagem = (
        f"{emoji} *{rotulo}*\n"
        f"{cliente_nome} — {titulo}\n\n"
        f"Nº: {numero_chamado}\n"
        f"Responsável: {responsavel_nome or 'Não atribuído'}\n\n"
        f"🔗 {_link(chamado_id)}"
    )
    await _enviar(mensagem)

async def notificar_atribuicao_individual(
    whatsapp_numero: str,
    responsavel_nome: str,
    chamado_id: int,
    cliente_nome: str,
    titulo: str,
    numero_chamado: str,
) -> None:
    mensagem = (
        f"👤 Olá, {responsavel_nome}!\n"
        f"Você foi atribuído a um chamado.\n\n"
        f"*{cliente_nome}*\n{titulo}\n\n"
        f"Nº: {numero_chamado}\n\n"
        f"🔗 {_link(chamado_id)}"
    )
    chat_id = f"{whatsapp_numero}@c.us"

    if not settings.waha_api_key:
        logger.info("WAHA não configurado, pulando notificação individual.")
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
        logger.exception("Falha ao enviar notificação individual para %s", whatsapp_numero)