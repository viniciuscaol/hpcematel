"""
Verificação periódica de SLA em segundo plano. Notifica o grupo quando
um chamado entra em "atenção" ou "estourado", evitando repetir o mesmo
alerta (guarda o último estado enfileirado na mesma transação da fila).
"""
from sqlalchemy import select

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Chamado, Status
from app.services.chamado_service import aplicar_status_sla
from app.services.notificacao_service import notificar_alerta_sla

ESTADOS_NOTIFICAVEIS = {"proximo", "estourado"}


async def verificar_sla_e_notificar() -> None:
    async with HelpdeskSessionLocal() as db:
        finalizadores_result = await db.execute(select(Status.id).where(Status.finalizador.is_(True)))
        finalizadores = set(finalizadores_result.scalars().all())

        query = select(Chamado).where(Chamado.excluido.is_(False)).where(Chamado.status_id.notin_(finalizadores)).with_for_update(skip_locked=True)
        result = await db.execute(query)
        chamados = list(result.scalars().all())

        for chamado in chamados:
            await aplicar_status_sla(db, chamado)

            if chamado.sla_status not in ESTADOS_NOTIFICAVEIS:
                continue
            if chamado.sla_notificado_status == chamado.sla_status:
                continue

            # Sem HTTP aqui: só marca o estado se a mensagem entrou na fila.
            # Uma falha de banco aborta a transação e permite repetir o ciclo.
            enfileirada = await notificar_alerta_sla(
                db, chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
                titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
                sla_status=chamado.sla_status, responsavel_nome=chamado.responsavel_nome_snapshot,
            )
            if enfileirada:
                chamado.sla_notificado_status = chamado.sla_status

        await db.commit()
