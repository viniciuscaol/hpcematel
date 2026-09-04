"""
Mapa de atendimentos resolvidos: mostra no mapa onde cada chamado foi
fechado, com um pino colorido por técnico responsável. Acesso restrito
a ADMIN, já que localização é informação sensível.
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import exigir_papel
from app.database.helpdesk_db import get_helpdesk_db
from app.services.chamado_service import (
    contar_resolvidos_sem_local, listar_chamados_resolvidos_com_local, listar_responsaveis_possiveis,
)
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
    usuarios_codigos: list[int] | None = None,
):
    hoje = hoje_local()
    data_inicio_obj = date.fromisoformat(data_inicio) if data_inicio else hoje
    data_fim_obj = date.fromisoformat(data_fim) if data_fim else hoje

    chamados = await listar_chamados_resolvidos_com_local(db, data_inicio_obj, data_fim_obj, usuarios_codigos)
    sem_local = await contar_resolvidos_sem_local(db, data_inicio_obj, data_fim_obj)
    todos_responsaveis = await listar_responsaveis_possiveis()

    codigos_presentes = sorted({c.responsavel_codigo for c in chamados if c.responsavel_codigo})
    cor_por_codigo = {codigo: PALETA_CORES[i % len(PALETA_CORES)] for i, codigo in enumerate(codigos_presentes)}

    pontos, legenda, nomes_vistos = [], [], set()
    for c in chamados:
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
        "pontos": pontos, "legenda": legenda, "sem_local": sem_local,
        "todos_responsaveis": todos_responsaveis,
        "usuarios_selecionados": usuarios_codigos or [],
        "data_inicio": data_inicio_obj.isoformat(), "data_fim": data_fim_obj.isoformat(),
    })