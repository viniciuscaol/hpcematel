"""
Envio de notificações para o WhatsApp via WAHA.

Mensagens entram na fila dentro da transação do chamador. Somente o
processador da fila acessa o WAHA, entre 8h e 19h (horário de Bahia).
Falhas permanecem no banco e são tentadas novamente com intervalo crescente.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.chamado import NotificacaoPendente
from app.utils.datas import FUSO_BAHIA

logger = logging.getLogger(__name__)

HORA_INICIO_PERMITIDA = 8
HORA_FIM_PERMITIDA = 19
TAMANHO_LOTE = 20


def _dentro_do_horario() -> bool:
    agora = datetime.now(FUSO_BAHIA)
    return HORA_INICIO_PERMITIDA <= agora.hour < HORA_FIM_PERMITIDA


def _rotulo_cidade(cidade: str | None) -> str | None:
    if not cidade:
        return None
    if "salvador" in cidade.lower():
        return "Telemedicina"
    return cidade.split("/")[0].strip().title()


async def _enviar(db: AsyncSession, mensagem: str, chat_id: str | None = None) -> bool:
    """Enfileira sem commit: o chamador confirma junto com a alteração de negócio."""
    chat_id = chat_id or settings.waha_grupo_id
    if not chat_id:
        logger.warning("Notificação não enfileirada: destino WhatsApp não configurado.")
        return False

    if not _dentro_do_horario():
        agora = datetime.now(FUSO_BAHIA)
        mensagem = (
            f"{mensagem}\n\n_(ocorrido às {agora.strftime('%d/%m %H:%M')}, "
            f"fora do horário de notificações)_"
        )
    db.add(NotificacaoPendente(chat_id=chat_id, mensagem=mensagem))
    await db.flush()
    return True


def _resumir_erro(erro: Exception) -> str:
    # Não persiste corpo de resposta, mensagem, URL ou credenciais no erro.
    if isinstance(erro, httpx.HTTPStatusError):
        return f"HTTP {erro.response.status_code}"
    if isinstance(erro, httpx.TimeoutException):
        return "Timeout no WAHA"
    if isinstance(erro, httpx.RequestError):
        return "Falha de conexão com WAHA"
    return type(erro).__name__[:120]


async def processar_fila_notificacoes(db: AsyncSession) -> None:
    """Usa sessão própria e confirma cada item; SKIP LOCKED evita envio concorrente."""
    if not _dentro_do_horario() or not settings.waha_api_key:
        return

    url = f"{settings.waha_api_url}/api/sendText"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(TAMANHO_LOTE):
            if not _dentro_do_horario():
                break
            result = await db.execute(
                select(NotificacaoPendente)
                .where(NotificacaoPendente.proxima_tentativa_em <= datetime.now(timezone.utc))
                .order_by(NotificacaoPendente.criado_em, NotificacaoPendente.id)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
                .limit(1)
            )
            pendente = result.scalar_one_or_none()
            if pendente is None:
                await db.commit()
                break
            pendente.tentativas += 1
            pendente.ultima_tentativa_em = datetime.now(timezone.utc)
            try:
                resposta = await client.post(
                    url,
                    headers={"X-Api-Key": settings.waha_api_key},
                    json={"session": settings.waha_sessao, "chatId": pendente.chat_id, "text": pendente.mensagem},
                )
                resposta.raise_for_status()
            except Exception as erro:
                pendente.ultimo_erro = _resumir_erro(erro)
                minutos = min(2 ** min(pendente.tentativas - 1, 5), 30)
                pendente.proxima_tentativa_em = datetime.now(timezone.utc) + timedelta(minutes=minutos)
                logger.warning("Notificação %s falhou na tentativa %s: %s", pendente.id, pendente.tentativas, pendente.ultimo_erro)
            else:
                await db.delete(pendente)
            # Um envio bem-sucedido não depende de processar o restante do lote.
            # Se este commit falhar após o WAHA aceitar, o reenvio pode duplicar.
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
) -> bool:
    if sla_status == "estourado":
        emoji, rotulo = "🔴", "SLA ESTOURADO"
    else:
        emoji, rotulo = "🟡", "SLA próximo do limite"
    mensagem = (
        f"{emoji} *{rotulo}*\n{cliente_nome} — {titulo}\n\n"
        f"Nº: {numero_chamado}\nResponsável: {responsavel_nome or 'Não atribuído'}\n\n🔗 {_link(chamado_id)}"
    )
    return await _enviar(db, mensagem)


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

    # Versão resumida também para o grupo de gerência
    if settings.waha_grupo_diretoria_id:
        mensagem_diretoria = (
            f"📦 {cliente_nome}\n"
            f"Solicitação: {titulo}\n"
            f"Rastreio ({rotulo_tipo}): {descricao_evento}"
        )
        await _enviar(db, mensagem_diretoria, chat_id=settings.waha_grupo_diretoria_id)

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
