"""Consulta administrativa da trilha central de auditoria."""
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import exigir_papel
from app.database.helpdesk_db import get_helpdesk_db
from app.models.auditoria import AuditoriaLog
from app.services.contato_service import PAPEL_ADMIN
from app.templates_config import templates

router = APIRouter(prefix="/admin", tags=["admin"])
FUSO_LOCAL = ZoneInfo("America/Bahia")
TAMANHO_PAGINA = 50

CATEGORIAS = [
    ("autenticacao", "Autenticação"),
    ("chamados", "Chamados"),
    ("clientes", "Clientes"),
    ("usuarios", "Usuários"),
    ("administracao", "Administração"),
    ("monitoramento", "Monitoramento"),
    ("mapa", "Mapa"),
    ("sistema", "Sistema"),
]
TIPOS = [
    ("consulta", "Consulta"),
    ("alteracao", "Alteração"),
    ("autenticacao", "Autenticação"),
]
RESULTADOS = [
    ("sucesso", "Sucesso"),
    ("falha", "Falha"),
    ("negado", "Acesso negado"),
]


@router.get("/logs")
async def pagina_logs(
    request: Request,
    usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
    q: str | None = Query(None, max_length=100),
    usuario_filtro: str | None = Query(None, max_length=100, alias="usuario"),
    categoria: str | None = None,
    tipo_evento: str | None = None,
    resultado: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    pagina: int = Query(1, ge=1),
):
    filtros = []
    termo = (q or "").strip()
    if termo:
        padrao = f"%{termo}%"
        filtros.append(
            or_(
                AuditoriaLog.usuario_nome.ilike(padrao),
                AuditoriaLog.usuario_login.ilike(padrao),
                AuditoriaLog.acao.ilike(padrao),
                AuditoriaLog.caminho.ilike(padrao),
                AuditoriaLog.entidade_id.ilike(padrao),
            )
        )

    nome_usuario = (usuario_filtro or "").strip()
    if nome_usuario:
        padrao_usuario = f"%{nome_usuario}%"
        filtros.append(
            or_(
                AuditoriaLog.usuario_nome.ilike(padrao_usuario),
                AuditoriaLog.usuario_login.ilike(padrao_usuario),
            )
        )

    categorias_validas = {item[0] for item in CATEGORIAS}
    tipos_validos = {item[0] for item in TIPOS}
    resultados_validos = {item[0] for item in RESULTADOS}
    if categoria in categorias_validas:
        filtros.append(AuditoriaLog.categoria == categoria)
    if tipo_evento in tipos_validos:
        filtros.append(AuditoriaLog.tipo_evento == tipo_evento)
    if resultado in resultados_validos:
        filtros.append(AuditoriaLog.resultado == resultado)

    if data_inicio:
        inicio_local = datetime.combine(data_inicio, time.min, tzinfo=FUSO_LOCAL)
        filtros.append(AuditoriaLog.criado_em >= inicio_local.astimezone(timezone.utc))
    if data_fim:
        fim_exclusivo = datetime.combine(
            data_fim + timedelta(days=1), time.min, tzinfo=FUSO_LOCAL
        )
        filtros.append(AuditoriaLog.criado_em < fim_exclusivo.astimezone(timezone.utc))

    total = await db.scalar(select(func.count(AuditoriaLog.id)).where(*filtros)) or 0
    total_paginas = max(1, ceil(total / TAMANHO_PAGINA))
    pagina = min(pagina, total_paginas)

    consulta = (
        select(AuditoriaLog)
        .where(*filtros)
        .order_by(AuditoriaLog.criado_em.desc(), AuditoriaLog.id.desc())
        .offset((pagina - 1) * TAMANHO_PAGINA)
        .limit(TAMANHO_PAGINA)
    )
    registros = (await db.execute(consulta)).scalars().all()

    logs = []
    for registro in registros:
        criado_em = registro.criado_em
        if criado_em.tzinfo is None:
            criado_em = criado_em.replace(tzinfo=timezone.utc)
        logs.append(
            {
                "data_hora": criado_em.astimezone(FUSO_LOCAL).strftime("%d/%m/%Y %H:%M:%S"),
                "usuario": registro.usuario_nome or registro.usuario_login or "Não identificado",
                "login": registro.usuario_login or "—",
                "categoria": registro.categoria.replace("_", " ").capitalize(),
                "tipo": registro.tipo_evento.capitalize(),
                "acao": registro.acao.replace("_", " "),
                "recurso": (
                    f"{registro.entidade} #{registro.entidade_id}"
                    if registro.entidade_id
                    else (registro.entidade or registro.caminho or "—")
                ),
                "resultado": registro.resultado,
                "status_http": registro.status_http,
                "ip": registro.ip_origem or "—",
            }
        )

    parametros = {
        "q": termo or None,
        "usuario": nome_usuario or None,
        "categoria": categoria or None,
        "tipo_evento": tipo_evento or None,
        "resultado": resultado or None,
        "data_inicio": data_inicio.isoformat() if data_inicio else None,
        "data_fim": data_fim.isoformat() if data_fim else None,
    }
    parametros = {chave: valor for chave, valor in parametros.items() if valor}
    anterior_url = (
        "/admin/logs?" + urlencode({**parametros, "pagina": pagina - 1})
        if pagina > 1 else None
    )
    proxima_url = (
        "/admin/logs?" + urlencode({**parametros, "pagina": pagina + 1})
        if pagina < total_paginas else None
    )

    return templates.TemplateResponse(
        "admin/logs.html",
        {
            "request": request,
            "usuario": usuario,
            "logs": logs,
            "total": total,
            "pagina": pagina,
            "total_paginas": total_paginas,
            "anterior_url": anterior_url,
            "proxima_url": proxima_url,
            "q": termo,
            "usuario_filtro": nome_usuario,
            "categoria_selecionada": categoria or "",
            "tipo_selecionado": tipo_evento or "",
            "resultado_selecionado": resultado or "",
            "data_inicio": data_inicio.isoformat() if data_inicio else "",
            "data_fim": data_fim.isoformat() if data_fim else "",
            "categorias": CATEGORIAS,
            "tipos": TIPOS,
            "resultados": RESULTADOS,
        },
    )
