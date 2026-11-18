"""Persistência resiliente dos eventos de auditoria."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditoria import AuditoriaLog

logger = logging.getLogger(__name__)


async def registrar_evento_auditoria(
    db: AsyncSession,
    *,
    tipo_evento: str,
    categoria: str,
    acao: str,
    resultado: str = "sucesso",
    usuario_codigo: int | None = None,
    usuario_login: str | None = None,
    usuario_nome: str | None = None,
    metodo_http: str | None = None,
    caminho: str | None = None,
    entidade: str | None = None,
    entidade_id: str | None = None,
    status_http: int | None = None,
    ip_origem: str | None = None,
    user_agent: str | None = None,
    detalhes: str | None = None,
) -> None:
    """Grava somente metadados da ação; nunca recebe corpo, senha ou token."""
    try:
        db.add(
            AuditoriaLog(
                tipo_evento=tipo_evento[:20],
                categoria=categoria[:40],
                acao=acao[:120],
                resultado=resultado[:20],
                usuario_codigo=usuario_codigo,
                usuario_login=usuario_login[:100] if usuario_login else None,
                usuario_nome=usuario_nome[:255] if usuario_nome else None,
                metodo_http=metodo_http[:10] if metodo_http else None,
                caminho=caminho[:500] if caminho else None,
                entidade=entidade[:80] if entidade else None,
                entidade_id=entidade_id[:80] if entidade_id else None,
                status_http=status_http,
                ip_origem=ip_origem[:64] if ip_origem else None,
                user_agent=user_agent[:255] if user_agent else None,
                detalhes=detalhes,
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Não foi possível persistir um evento de auditoria.", exc_info=True)
