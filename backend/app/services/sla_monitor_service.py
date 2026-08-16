"""
Verificação periódica de SLA em segundo plano. Notifica o grupo quando
um chamado entra em "atenção" ou "estourado", evitando repetir o mesmo
alerta (guarda o último estado notificado no próprio chamado).
"""
import logging

from sqlalchemy import select

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Chamado, Status
from app.services.chamado_service import aplicar_status_sla
from app.services.notificacao_service import notificar_alerta_sla

logger = logging.getLogger(__name__)

ESTADOS_NOTIFICAVEIS = {"proximo", "estourado"}


async def verificar_sla_e_notificar() -> None:
    async with HelpdeskSessionLocal() as db:
        finalizadores_result = await db.execute(select(Status.id).where(Status.finalizador.is_(True)))
        finalizadores = set(finalizadores_result.scalars().all())

        query = select(Chamado).where(Chamado.excluido.is_(False)).where(Chamado.status_id.notin_(finalizadores))
        result = await db.execute(query)
        chamados = list(result.scalars().all())

        for chamado in chamados:
            await aplicar_status_sla(db, chamado)

            if chamado.sla_status not in ESTADOS_NOTIFICAVEIS:
                continue
            if chamado.sla_notificado_status == chamado.sla_status:
                continue

            try:
                await notificar_alerta_sla(
                    chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
                    titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
                    sla_status=chamado.sla_status, responsavel_nome=chamado.responsavel_nome_snapshot,
                )
                chamado.sla_notificado_status = chamado.sla_status
            except Exception:
                logger.exception("Falha ao notificar alerta de SLA do chamado %s", chamado.id)

        await db.commit()