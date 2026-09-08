"""
Verificação periódica dos rastreios de Correios. Notifica mudanças de
status e, ao detectar entrega, resolve o chamado automaticamente.
Cada chamado é processado isoladamente (try/except por item), para que
uma falha num não impeça os demais de serem verificados no mesmo ciclo.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Chamado, ChamadoRastreio
from app.services.chamado_service import STATUS_RESOLVIDO_ID, atualizar_status
from app.services.correios_service import consultar_rastreio, correios_configurado
from app.services.notificacao_service import notificar_atualizacao_rastreio

logger = logging.getLogger(__name__)

USUARIO_SISTEMA_CODIGO = 0
USUARIO_SISTEMA_NOME = "Sistema (Rastreio Correios)"


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

        chamados_ids_com_mudanca: set[int] = set()

        for rastreio, chamado in pares:
            info = await consultar_rastreio(rastreio.codigo_rastreio)
            if info is None:
                continue

            if info["descricao_evento"] != rastreio.status_atual:
                try:
                    await notificar_atualizacao_rastreio(
                        db, chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
                        titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
                        tipo=rastreio.tipo, codigo_rastreio=rastreio.codigo_rastreio,
                        descricao_evento=info["descricao_evento"],
                        cidade_remetente=info.get("cidade_remetente"),
                        cidade_destinatario=info.get("cidade_destinatario"),
                    )
                except Exception:
                    logger.exception("Falha ao notificar rastreio do chamado %s", chamado.id)

                rastreio.status_atual = info["descricao_evento"]
                rastreio.entregue = info["entregue"]
                if info["entregue"] and rastreio.tipo == "envio":
                    chamados_ids_com_mudanca.add(chamado.id)

            rastreio.ultima_verificacao_em = datetime.now(timezone.utc)

        await db.commit()

        # Auto-resolve: processado em transações isoladas, uma por chamado,
        # para que um erro num não impeça a checagem dos demais.
        for chamado_id in chamados_ids_com_mudanca:
            try:
                todos_result = await db.execute(
                    select(ChamadoRastreio).where(ChamadoRastreio.chamado_id == chamado_id)
                )
                todos = list(todos_result.scalars().all())
                if not all(r.entregue for r in todos):
                    continue

                status_atual = await db.execute(select(Chamado.status_id).where(Chamado.id == chamado_id))
                status_atual_id = status_atual.scalar_one_or_none()
                if status_atual_id == STATUS_RESOLVIDO_ID:
                    continue

                chamado_ref = await db.get(Chamado, chamado_id)
                await atualizar_status(
                    db, chamado_id, STATUS_RESOLVIDO_ID, USUARIO_SISTEMA_CODIGO, USUARIO_SISTEMA_NOME,
                )
            except Exception:
                logger.exception("Falha ao auto-resolver chamado %s apos entrega dos correios", chamado_id)