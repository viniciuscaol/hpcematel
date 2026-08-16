"""
Consultas de indicadores para o dashboard.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chamado import Categoria, Chamado, Prioridade, Status
from app.services.chamado_service import aplicar_status_sla


async def _status_abertos_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(Status.id).where(Status.finalizador.is_(False)))
    return list(result.scalars().all())


async def _status_finalizadores(db: AsyncSession) -> set[int]:
    result = await db.execute(select(Status.id).where(Status.finalizador.is_(True)))
    return set(result.scalars().all())


async def contagem_por_status(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Chamado.status_id, func.count(Chamado.id))
        .where(Chamado.excluido.is_(False))
        .group_by(Chamado.status_id)
    )
    contagem = dict(result.all())

    status_list = (await db.execute(
        select(Status).where(Status.ativo.is_(True)).order_by(Status.ordem)
    )).scalars().all()

    return [{"nome": s.nome, "cor": s.cor, "quantidade": contagem.get(s.id, 0)} for s in status_list]


async def contagem_por_prioridade(db: AsyncSession) -> list[dict]:
    status_abertos_ids = await _status_abertos_ids(db)

    result = await db.execute(
        select(Chamado.prioridade_id, func.count(Chamado.id))
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id.in_(status_abertos_ids))
        .group_by(Chamado.prioridade_id)
    )
    contagem = dict(result.all())

    prioridade_list = (await db.execute(
        select(Prioridade).where(Prioridade.ativo.is_(True)).order_by(Prioridade.ordem)
    )).scalars().all()

    return [{"nome": p.nome, "cor": p.cor, "quantidade": contagem.get(p.id, 0)} for p in prioridade_list]


async def contagem_por_categoria(db: AsyncSession) -> list[dict]:
    status_abertos_ids = await _status_abertos_ids(db)

    result = await db.execute(
        select(Chamado.categoria_id, func.count(Chamado.id))
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id.in_(status_abertos_ids))
        .group_by(Chamado.categoria_id)
    )
    contagem = dict(result.all())

    categoria_list = (await db.execute(
        select(Categoria).where(Categoria.ativo.is_(True)).order_by(Categoria.nome)
    )).scalars().all()

    return [{"nome": c.nome, "quantidade": contagem.get(c.id, 0)} for c in categoria_list]


async def contar_meus_chamados(db: AsyncSession, usuario_codigo: int) -> int:
    status_abertos_ids = await _status_abertos_ids(db)

    result = await db.execute(
        select(func.count(Chamado.id))
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id.in_(status_abertos_ids))
        .where(Chamado.responsavel_codigo == usuario_codigo)
    )
    return result.scalar_one()


async def contar_sla_estourado(db: AsyncSession) -> int:
    finalizadores = await _status_finalizadores(db)
    agora = datetime.now(timezone.utc)

    result = await db.execute(
        select(func.count(Chamado.id))
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id.notin_(finalizadores))
        .where(Chamado.prazo_sla < agora)
    )
    return result.scalar_one()


async def listar_chamados_recentes(db: AsyncSession, limite: int = 6) -> list[Chamado]:
    query = (
        select(Chamado)
        .where(Chamado.excluido.is_(False))
        .options(
            selectinload(Chamado.categoria),
            selectinload(Chamado.prioridade),
            selectinload(Chamado.status),
        )
        .order_by(Chamado.criado_em.desc())
        .limit(limite)
    )
    result = await db.execute(query)
    chamados = list(result.scalars().all())
    for c in chamados:
        await aplicar_status_sla(db, c)
    return chamados