"""
Verificação periódica dos rastreios de Correios. Roda em segundo plano
e notifica o grupo do WhatsApp quando o status de um objeto mudar.
"""
import logging

from sqlalchemy import select

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Chamado, ChamadoRastreio
from app.services.correios_service import consultar_rastreio, correios_configurado
from app.services.notificacao_service import notificar_atualizacao_rastreio

logger = logging.getLogger(__name__)


async def verificar_rastreios_e_notificar() -> None:
    if not correios_configurado():
        return

    async with HelpdeskSessionLocal() as db:
        result = await db.execute(
            select(ChamadoRastreio, Chamado)
            .join(Chamado, Chamado.id == ChamadoRastreio.chamado_id)
            .where(ChamadoRastreio.entregue.is_(False))
            .where(Chamado.excluido.is_(False))
        )
        pares = result.all()

        for rastreio, chamado in pares:
            info = await consultar_rastreio(rastreio.codigo_rastreio)
            if info is None:
                continue

            if info["descricao_evento"] != rastreio.status_atual:
                try:
                    await notificar_atualizacao_rastreio(
                        chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
                        titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
                        tipo=rastreio.tipo, codigo_rastreio=rastreio.codigo_rastreio,
                        descricao_evento=info["descricao_evento"],
                    )
                except Exception:
                    logger.exception("Falha ao notificar rastreio do chamado %s", chamado.id)

                rastreio.status_atual = info["descricao_evento"]
                rastreio.entregue = info["entregue"]

            from datetime import datetime, timezone
            rastreio.ultima_verificacao_em = datetime.now(timezone.utc)

        await db.commit()