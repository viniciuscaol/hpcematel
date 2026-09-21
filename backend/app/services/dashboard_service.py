"""
Consultas de indicadores para o dashboard.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chamado import Categoria, Chamado, Prioridade, Status, chamado_categoria
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
    """
    Como um chamado pode ter várias categorias, a contagem passa pela
    tabela de associação chamado_categoria (join), não mais por uma
    coluna direta em chamado.
    """
    status_abertos_ids = await _status_abertos_ids(db)

    result = await db.execute(
        select(chamado_categoria.c.categoria_id, func.count(chamado_categoria.c.chamado_id))
        .select_from(chamado_categoria)
        .join(Chamado, Chamado.id == chamado_categoria.c.chamado_id)
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id.in_(status_abertos_ids))
        .group_by(chamado_categoria.c.categoria_id)
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
            selectinload(Chamado.categorias),
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

async def top_unidades_com_mais_chamados(db: AsyncSession, limite: int = 10) -> list[dict]:
    """Unidades (clientes) com mais chamados abertos historicamente, excluindo os apagados."""
    result = await db.execute(
        select(Chamado.cliente_codigo, Chamado.cliente_nome_snapshot, func.count(Chamado.id).label("qtd"))
        .where(Chamado.excluido.is_(False))
        .group_by(Chamado.cliente_codigo, Chamado.cliente_nome_snapshot)
        .order_by(func.count(Chamado.id).desc())
        .limit(limite)
    )
    return [{"nome": nome, "quantidade": qtd} for _, nome, qtd in result.all()]


async def top_categorias_geral(db: AsyncSession, limite: int = 10) -> list[dict]:
    """Categorias com mais chamados no histórico completo (não só os em aberto)."""
    result = await db.execute(
        select(Categoria.nome, func.count(chamado_categoria.c.chamado_id).label("qtd"))
        .select_from(chamado_categoria)
        .join(Chamado, Chamado.id == chamado_categoria.c.chamado_id)
        .join(Categoria, Categoria.id == chamado_categoria.c.categoria_id)
        .where(Chamado.excluido.is_(False))
        .group_by(Categoria.nome)
        .order_by(func.count(chamado_categoria.c.chamado_id).desc())
        .limit(limite)
    )
    return [{"nome": nome, "quantidade": qtd} for nome, qtd in result.all()]


async def ranking_tecnicos_por_resolucao(db: AsyncSession, limite: int = 10) -> list[dict]:
    """Quem mais resolveu chamados, no histórico completo."""
    from app.services.chamado_service import STATUS_RESOLVIDO_ID

    result = await db.execute(
        select(Chamado.responsavel_nome_snapshot, func.count(Chamado.id).label("qtd"))
        .where(Chamado.excluido.is_(False), Chamado.status_id == STATUS_RESOLVIDO_ID)
        .where(Chamado.responsavel_nome_snapshot.isnot(None))
        .group_by(Chamado.responsavel_nome_snapshot)
        .order_by(func.count(Chamado.id).desc())
        .limit(limite)
    )
    return [{"nome": nome, "quantidade": qtd} for nome, qtd in result.all()]


async def tempo_medio_resolucao_horas(db: AsyncSession) -> float | None:
    """Média de horas entre a criação e a resolução, no histórico completo."""
    result = await db.execute(
        select(func.avg(func.extract("epoch", Chamado.resolvido_em - Chamado.criado_em) / 3600.0))
        .where(Chamado.excluido.is_(False), Chamado.resolvido_em.isnot(None))
    )
    media = result.scalar_one_or_none()
    return round(media, 1) if media is not None else None

async def tendencia_abertura_14_dias(db: AsyncSession) -> list[dict]:
    """Quantos chamados foram abertos por dia, nos últimos 14 dias."""
    from datetime import timedelta
    from app.utils.datas import hoje_local, intervalo_utc_do_dia, para_horario_local

    limite_data = hoje_local() - timedelta(days=13)
    inicio_utc, _ = intervalo_utc_do_dia(limite_data)

    result = await db.execute(
        select(Chamado.criado_em).where(Chamado.excluido.is_(False), Chamado.criado_em >= inicio_utc)
    )
    contagem: dict = {}
    for (criado_em,) in result.all():
        dia = para_horario_local(criado_em).date()
        contagem[dia] = contagem.get(dia, 0) + 1

    dias = [limite_data + timedelta(days=i) for i in range(14)]
    return [{"data": d.strftime("%d/%m"), "quantidade": contagem.get(d, 0)} for d in dias]


async def percentual_sla_cumprido(db: AsyncSession) -> dict:
    """De tudo que já foi resolvido, quanto foi dentro do prazo vs. estourado."""
    result = await db.execute(
        select(Chamado.resolvido_em, Chamado.prazo_sla)
        .where(Chamado.excluido.is_(False), Chamado.resolvido_em.isnot(None))
    )
    linhas = result.all()
    total = len(linhas)
    if total == 0:
        return {"percentual": None, "total": 0, "no_prazo": 0}

    no_prazo = sum(1 for resolvido_em, prazo_sla in linhas if resolvido_em <= prazo_sla)
    return {"percentual": round(no_prazo / total * 100, 1), "total": total, "no_prazo": no_prazo}


async def chamados_por_dia_semana(db: AsyncSession) -> list[dict]:
    """Distribuição histórica de chamados por dia da semana (ajuda a planejar escala)."""
    from app.utils.datas import para_horario_local

    result = await db.execute(select(Chamado.criado_em).where(Chamado.excluido.is_(False)))
    nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    contagem = [0] * 7
    for (criado_em,) in result.all():
        contagem[para_horario_local(criado_em).weekday()] += 1

    return [{"nome": nomes[i], "quantidade": contagem[i]} for i in range(7)]