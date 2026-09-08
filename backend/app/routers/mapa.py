"""
Mapa de atendimentos resolvidos: pinos coloridos por técnico, com
relatório completo abaixo (incluindo chamados sem localização). Acesso
restrito a ADMIN, já que localização é informação sensível.
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import exigir_papel
from app.database.helpdesk_db import get_helpdesk_db
from app.services.chamado_service import listar_chamados_resolvidos
from app.services.contato_service import PAPEL_ADMIN
from app.templates_config import templates
from app.utils.datas import hoje_local

router = APIRouter(prefix="/mapa", tags=["mapa"])

PALETA_CORES = [
    "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c", "#4f46e5",
]


@router.get("")
async def tela_mapa(
    request: Request,
    usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
    data_inicio: str | None = None,
    data_fim: str | None = None,
    usuarios_codigos: Annotated[list[int], Query()] = [],
):
    hoje = hoje_local()
    data_inicio_obj = date.fromisoformat(data_inicio) if data_inicio else hoje
    data_fim_obj = date.fromisoformat(data_fim) if data_fim else hoje

    # Busca SEM filtro de usuário primeiro, só pra saber quem de fato
    # resolveu algo no período — isso monta as opções do filtro.
    todos_do_periodo = await listar_chamados_resolvidos(db, data_inicio_obj, data_fim_obj, None)
    responsaveis_com_registro = {}
    for c in todos_do_periodo:
        if c.responsavel_codigo:
            responsaveis_com_registro[c.responsavel_codigo] = c.responsavel_nome_snapshot
    opcoes_filtro = [
        {"codigo": codigo, "nome": nome}
        for codigo, nome in sorted(responsaveis_com_registro.items(), key=lambda item: item[1])
    ]

    # Agora sim aplica o filtro escolhido (se houver) — direto no banco.
    chamados = await listar_chamados_resolvidos(db, data_inicio_obj, data_fim_obj, usuarios_codigos or None)

    com_local = [c for c in chamados if c.fechado_latitude is not None and c.fechado_longitude is not None]
    sem_local_count = len(chamados) - len(com_local)

    codigos_presentes = sorted({c.responsavel_codigo for c in com_local if c.responsavel_codigo})
    cor_por_codigo = {codigo: PALETA_CORES[i % len(PALETA_CORES)] for i, codigo in enumerate(codigos_presentes)}

    pontos, legenda, nomes_vistos = [], [], set()
    for c in com_local:
        cor = cor_por_codigo.get(c.responsavel_codigo, "#6b7280")
        pontos.append({
            "id": c.id, "numero": c.numero_chamado, "titulo": c.titulo,
            "cliente": c.cliente_nome_snapshot,
            "responsavel": c.responsavel_nome_snapshot or "Não atribuído",
            "lat": c.fechado_latitude, "lon": c.fechado_longitude, "cor": cor,
        })
        nome = c.responsavel_nome_snapshot
        if nome and nome not in nomes_vistos:
            nomes_vistos.add(nome)
            legenda.append({"nome": nome, "cor": cor})

    return templates.TemplateResponse("mapa.html", {
        "request": request, "usuario": usuario, "chamados": chamados,
        "pontos": pontos, "legenda": legenda, "sem_local_count": sem_local_count,
        "todos_responsaveis": opcoes_filtro,
        "usuarios_selecionados": usuarios_codigos or [],
        "data_inicio": data_inicio_obj.isoformat(), "data_fim": data_fim_obj.isoformat(),
    })