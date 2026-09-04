"""
Verificação periódica dos rastreios de Correios. Notifica mudanças de
status e, ao detectar entrega, resolve o chamado automaticamente.
"""
import logging

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

        for rastreio, chamado in pares:
            info = await consultar_rastreio(rastreio.codigo_rastreio)
            if info is None:
                continue

            mudou = info["descricao_evento"] != rastreio.status_atual
            if mudou:
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

            from datetime import datetime, timezone
            rastreio.ultima_verificacao_em = datetime.now(timezone.utc)

        await db.commit()

        # Auto-resolve: só quando TODOS os rastreios de envio do chamado
        # estiverem entregues (evita resolver com reverso ainda em trânsito).
        for rastreio, chamado in pares:
            if rastreio.tipo != "envio" or not rastreio.entregue:
                continue
            todos_result = await db.execute(select(ChamadoRastreio).where(ChamadoRastreio.chamado_id == chamado.id))
            todos = list(todos_result.scalars().all())
            if all(r.entregue for r in todos) and chamado.status_id != STATUS_RESOLVIDO_ID:
                await atualizar_status(db, chamado.id, STATUS_RESOLVIDO_ID, USUARIO_SISTEMA_CODIGO, USUARIO_SISTEMA_NOME)