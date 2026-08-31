"""
Regras de negócio para chamados: criação, listagem, detalhe,
mudança de status (com pausa/retomada de SLA), categorias múltiplas,
edição de campos, anexos, exclusão lógica.
"""
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chamado import Categoria, Chamado, ChamadoHistorico, ChamadoInteracao, Prioridade, Status
from app.services.cliente_service import buscar_cliente_por_codigo
from app.services.usuario_service import listar_usuarios_helpdesk
from app.utils.datas import para_horario_local
from app.utils.sla import calcular_prazo_sla, calcular_status_sla

STATUS_INICIAL_ID = 1
STATUS_EM_ANDAMENTO_ID = 2
STATUS_AGUARDANDO_ID = 3
STATUS_RESOLVIDO_ID = 4
STATUS_CANCELADO_ID = 5

POR_PAGINA_PADRAO = 20


class ClienteNaoEncontrado(Exception):
    pass


async def _status_finalizadores(db: AsyncSession) -> set[int]:
    result = await db.execute(select(Status.id).where(Status.finalizador.is_(True)))
    return set(result.scalars().all())


async def _status_pausa(db: AsyncSession) -> set[int]:
    result = await db.execute(select(Status.id).where(Status.pausa_sla.is_(True)))
    return set(result.scalars().all())


async def _status_abertos_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(Status.id).where(Status.finalizador.is_(False)))
    return list(result.scalars().all())


async def _proximo_numero_chamado(db: AsyncSession, data_local: date) -> str:
    resultado = await db.execute(
        text("""
            INSERT INTO chamado_contador_diario (data, contador)
            VALUES (:data, 1)
            ON CONFLICT (data) DO UPDATE SET contador = chamado_contador_diario.contador + 1
            RETURNING contador
        """),
        {"data": data_local},
    )
    return f"{data_local.strftime('%d%m%y')}{resultado.scalar_one():04d}"


async def aplicar_status_sla(db: AsyncSession, chamado: Chamado) -> Chamado:
    finalizadores = await _status_finalizadores(db)
    pausa = await _status_pausa(db)
    chamado.sla_status = calcular_status_sla(chamado.prazo_sla, chamado.status_id, finalizadores, pausa)
    return chamado


async def criar_chamado(
    db: AsyncSession, *, cliente_codigo: int, titulo: str, descricao: str | None,
    categoria_ids: list[int], prioridade_id: int, responsavel_codigo: int, responsavel_nome: str,
    criado_por_codigo: int, criado_por_nome: str,
) -> Chamado:
    cliente = await buscar_cliente_por_codigo(cliente_codigo)
    if cliente is None:
        raise ClienteNaoEncontrado()

    prioridade = await db.get(Prioridade, prioridade_id)
    agora = datetime.now(timezone.utc)
    data_local = para_horario_local(agora).date()
    numero_chamado = await _proximo_numero_chamado(db, data_local)
    prazo_sla = calcular_prazo_sla(agora, prioridade.sla_horas)

    categorias_result = await db.execute(select(Categoria).where(Categoria.id.in_(categoria_ids)))
    categorias = list(categorias_result.scalars().all())

    chamado = Chamado(
        numero_chamado=numero_chamado,
        cliente_codigo=cliente["codigo"], cliente_nome_snapshot=cliente["nome"],
        cliente_contato_snapshot=cliente.get("nome_contato"), cliente_telefone_snapshot=cliente.get("telefone_contato"),
        titulo=titulo, descricao=descricao or None,
        categorias=categorias, prioridade_id=prioridade_id, status_id=STATUS_INICIAL_ID,
        responsavel_codigo=responsavel_codigo, responsavel_nome_snapshot=responsavel_nome,
        criado_por_codigo=criado_por_codigo, criado_por_nome_snapshot=criado_por_nome,
        criado_em=agora, prazo_sla=prazo_sla,
    )
    db.add(chamado)
    await db.flush()
    chamado_id = chamado.id  # captura antes do expire_all, evita reler atributo expirado fora de contexto async

    nomes = ", ".join(c.nome for c in categorias)
    db.add(ChamadoHistorico(
        chamado_id=chamado_id, usuario_codigo=criado_por_codigo, usuario_nome_snapshot=criado_por_nome,
        campo_alterado="criacao", valor_anterior=None, valor_novo=f"Chamado criado ({nomes})",
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def listar_responsaveis_possiveis() -> list[dict]:
    return await listar_usuarios_helpdesk()


def _query_base_chamados(apenas_abertos, status_abertos_ids, data_local, busca, cliente_codigo):
    from app.utils.datas import intervalo_utc_do_dia
    condicoes = [Chamado.excluido.is_(False)]
    if apenas_abertos:
        condicoes.append(Chamado.status_id.in_(status_abertos_ids))
    if data_local is not None:
        inicio_utc, fim_utc = intervalo_utc_do_dia(data_local)
        condicoes.append(Chamado.criado_em >= inicio_utc)
        condicoes.append(Chamado.criado_em < fim_utc)
    if busca:
        termo = f"%{busca.strip()}%"
        condicoes.append(or_(
            Chamado.titulo.ilike(termo), Chamado.cliente_nome_snapshot.ilike(termo),
            Chamado.responsavel_nome_snapshot.ilike(termo), Chamado.numero_chamado.ilike(termo),
        ))
    if cliente_codigo is not None:
        condicoes.append(Chamado.cliente_codigo == cliente_codigo)
    return condicoes


async def contar_chamados(db, apenas_abertos=True, data_local=None, busca=None, cliente_codigo=None) -> int:
    status_abertos_ids = await _status_abertos_ids(db) if apenas_abertos else []
    condicoes = _query_base_chamados(apenas_abertos, status_abertos_ids, data_local, busca, cliente_codigo)
    result = await db.execute(select(func.count(Chamado.id)).where(*condicoes))
    return result.scalar_one()


async def listar_chamados(db, apenas_abertos=True, data_local=None, busca=None, cliente_codigo=None,
                           pagina=1, por_pagina=POR_PAGINA_PADRAO) -> list[Chamado]:
    status_abertos_ids = await _status_abertos_ids(db) if apenas_abertos else []
    condicoes = _query_base_chamados(apenas_abertos, status_abertos_ids, data_local, busca, cliente_codigo)
    offset = max(pagina - 1, 0) * por_pagina
    query = (
        select(Chamado).where(*condicoes)
        .options(selectinload(Chamado.categorias), selectinload(Chamado.prioridade), selectinload(Chamado.status))
        .order_by(Chamado.criado_em.asc()).offset(offset).limit(por_pagina)
    )
    result = await db.execute(query)
    chamados = list(result.scalars().all())
    for c in chamados:
        await aplicar_status_sla(db, c)
    return chamados


async def obter_chamado(db: AsyncSession, chamado_id: int) -> Chamado | None:
    query = (
        select(Chamado).where(Chamado.id == chamado_id)
        .options(
            selectinload(Chamado.categorias), selectinload(Chamado.prioridade), selectinload(Chamado.status),
            selectinload(Chamado.historico), selectinload(Chamado.interacoes), selectinload(Chamado.anexos),
        )
    )
    result = await db.execute(query)
    chamado = result.scalar_one_or_none()
    if chamado is not None:
        await aplicar_status_sla(db, chamado)
    return chamado


async def listar_status_ativos(db: AsyncSession) -> list[Status]:
    result = await db.execute(select(Status).where(Status.ativo.is_(True)).order_by(Status.ordem))
    return list(result.scalars().all())


async def atualizar_status(
    db, chamado_id, novo_status_id, usuario_codigo, usuario_nome,
    latitude: float | None = None, longitude: float | None = None,
) -> Chamado | None:
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return None
    if chamado.status_id == novo_status_id:
        return chamado

    status_anterior = await db.get(Status, chamado.status_id)
    status_novo = await db.get(Status, novo_status_id)
    agora = datetime.now(timezone.utc)

    if status_novo.pausa_sla and not status_anterior.pausa_sla:
        chamado.sla_pausado_em = agora
    if status_anterior.pausa_sla and not status_novo.pausa_sla and chamado.sla_pausado_em is not None:
        chamado.prazo_sla = chamado.prazo_sla + (agora - chamado.sla_pausado_em)
        chamado.sla_pausado_em = None

    chamado.status_id = novo_status_id
    if status_novo.finalizador:
        if novo_status_id == STATUS_RESOLVIDO_ID and chamado.resolvido_em is None:
            chamado.resolvido_em = agora
            if latitude is not None and longitude is not None:
                chamado.fechado_latitude = latitude
                chamado.fechado_longitude = longitude
        if novo_status_id == STATUS_CANCELADO_ID and chamado.encerrado_em is None:
            chamado.encerrado_em = agora

    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="status",
        valor_anterior=status_anterior.nome if status_anterior else None,
        valor_novo=status_novo.nome if status_novo else None,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def atualizar_categorias(db, chamado_id, categoria_ids, usuario_codigo, usuario_nome) -> Chamado | None:
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return None

    nomes_antigos = ", ".join(c.nome for c in chamado.categorias)
    result = await db.execute(select(Categoria).where(Categoria.id.in_(categoria_ids)))
    novas = list(result.scalars().all())
    nomes_novos = ", ".join(c.nome for c in novas)

    if nomes_antigos == nomes_novos:
        return chamado

    chamado.categorias = novas
    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="categoria", valor_anterior=nomes_antigos or None, valor_novo=nomes_novos or None,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def atualizar_prioridade(db, chamado_id, nova_prioridade_id, usuario_codigo, usuario_nome) -> Chamado | None:
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return None
    if chamado.prioridade_id == nova_prioridade_id:
        return chamado
    prioridade_anterior = await db.get(Prioridade, chamado.prioridade_id)
    prioridade_nova = await db.get(Prioridade, nova_prioridade_id)
    chamado.prioridade_id = nova_prioridade_id
    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="prioridade",
        valor_anterior=prioridade_anterior.nome if prioridade_anterior else None,
        valor_novo=prioridade_nova.nome if prioridade_nova else None,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def atualizar_responsavel(db, chamado_id, novo_responsavel_codigo, usuario_codigo, usuario_nome) -> Chamado | None:
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return None
    if chamado.responsavel_codigo == novo_responsavel_codigo:
        return chamado
    nome_anterior = chamado.responsavel_nome_snapshot or "Não atribuído"
    novo_nome = "Não atribuído"
    if novo_responsavel_codigo:
        responsaveis = await listar_usuarios_helpdesk()
        encontrado = next((r for r in responsaveis if r["codigo"] == novo_responsavel_codigo), None)
        novo_nome = encontrado["nome"] if encontrado else "Não atribuído"
    chamado.responsavel_codigo = novo_responsavel_codigo
    chamado.responsavel_nome_snapshot = novo_nome if novo_responsavel_codigo else None
    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="responsavel", valor_anterior=nome_anterior, valor_novo=novo_nome,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def adicionar_interacao(db, chamado_id, usuario_codigo, usuario_nome, texto) -> Chamado | None:
    db.add(ChamadoInteracao(
        chamado_id=chamado_id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome, texto=texto,
    ))
    await db.flush()
    chamado = await obter_chamado(db, chamado_id)
    if chamado is not None and chamado.responsavel_codigo != usuario_codigo:
        nome_anterior = chamado.responsavel_nome_snapshot or "Não atribuído"
        chamado.responsavel_codigo = usuario_codigo
        chamado.responsavel_nome_snapshot = usuario_nome
        db.add(ChamadoHistorico(
            chamado_id=chamado_id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
            campo_alterado="responsavel", valor_anterior=nome_anterior, valor_novo=usuario_nome,
        ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def excluir_anexo(db, chamado_id, anexo_id, usuario_codigo, usuario_nome) -> Chamado | None:
    from app.models.chamado import ChamadoAnexo
    from app.services.anexo_service import caminho_fisico_anexo
    import os

    anexo = await db.get(ChamadoAnexo, anexo_id)
    if anexo is None or anexo.chamado_id != chamado_id:
        return await obter_chamado(db, chamado_id)
    nome_original = anexo.nome_original
    caminho = caminho_fisico_anexo(chamado_id, anexo.nome_armazenado)
    if os.path.exists(caminho):
        os.remove(caminho)
    await db.delete(anexo)
    db.add(ChamadoHistorico(
        chamado_id=chamado_id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="anexo_excluido", valor_anterior=nome_original, valor_novo=None,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)


async def excluir_chamado(db, chamado_id, usuario_codigo, usuario_nome) -> Chamado | None:
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None or chamado.excluido:
        return chamado
    chamado.excluido = True
    chamado.excluido_em = datetime.now(timezone.utc)
    chamado.excluido_por_codigo = usuario_codigo
    chamado.excluido_por_nome_snapshot = usuario_nome
    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="exclusao", valor_anterior=None, valor_novo="Chamado excluído",
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)

async def listar_chamados_para_assumir(db) -> list[Chamado]:
    """Chamados no status inicial 'Aberto', disponíveis para um técnico assumir."""
    query = (
        select(Chamado)
        .where(Chamado.excluido.is_(False))
        .where(Chamado.status_id == STATUS_INICIAL_ID)
        .options(selectinload(Chamado.categorias), selectinload(Chamado.prioridade), selectinload(Chamado.status))
        .order_by(Chamado.criado_em.asc())
    )
    result = await db.execute(query)
    chamados = list(result.scalars().all())
    for c in chamados:
        await aplicar_status_sla(db, c)
    return chamados


async def assumir_chamado(db, chamado_id, usuario_codigo, usuario_nome) -> Chamado | None:
    """Associa o chamado ao técnico e move de 'Aberto' para 'Em andamento'."""
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return None
    if chamado.status_id != STATUS_INICIAL_ID:
        return chamado  # já foi assumido/alterado por outra pessoa nesse meio tempo

    responsavel_anterior = chamado.responsavel_nome_snapshot or "Não atribuído"
    status_anterior = await db.get(Status, chamado.status_id)
    status_novo = await db.get(Status, STATUS_EM_ANDAMENTO_ID)

    chamado.responsavel_codigo = usuario_codigo
    chamado.responsavel_nome_snapshot = usuario_nome
    chamado.status_id = STATUS_EM_ANDAMENTO_ID

    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="responsavel", valor_anterior=responsavel_anterior, valor_novo=usuario_nome,
    ))
    db.add(ChamadoHistorico(
        chamado_id=chamado.id, usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
        campo_alterado="status", valor_anterior=status_anterior.nome, valor_novo=status_novo.nome,
    ))
    await db.commit()
    db.expire_all()
    return await obter_chamado(db, chamado_id)

from app.models.chamado import ChamadoRastreio
from app.services.correios_service import consultar_rastreio


async def salvar_rastreios(db, chamado_id: int, codigo_envio: str | None, codigo_reverso: str | None) -> None:
    """Cria/atualiza os códigos de rastreio informados no formulário do chamado."""
    result = await db.execute(select(ChamadoRastreio).where(ChamadoRastreio.chamado_id == chamado_id))
    existentes = {r.tipo: r for r in result.scalars().all()}

    for tipo, codigo in (("envio", codigo_envio), ("reverso", codigo_reverso)):
        codigo = (codigo or "").strip().upper()
        if not codigo:
            continue
        if tipo in existentes:
            if existentes[tipo].codigo_rastreio != codigo:
                existentes[tipo].codigo_rastreio = codigo
                existentes[tipo].entregue = False
                existentes[tipo].status_atual = None
        else:
            db.add(ChamadoRastreio(chamado_id=chamado_id, tipo=tipo, codigo_rastreio=codigo))

    # Se algum código foi cadastrado, pausa o SLA reaproveitando "Aguardando cliente"
    if codigo_envio or codigo_reverso:
        chamado = await obter_chamado(db, chamado_id)
        if chamado is not None and not chamado.status.finalizador and not chamado.status.pausa_sla:
            await atualizar_status(db, chamado_id, STATUS_AGUARDANDO_ID, chamado.criado_por_codigo, chamado.criado_por_nome_snapshot)

    await db.commit()