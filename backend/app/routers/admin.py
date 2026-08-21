"""
Painel de administração: categorias, prioridades, status e contatos
de WhatsApp para notificação individual. Acessível a qualquer usuário
logado (mesmo grupo que já acessa o Help Desk).
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import exigir_papel
from app.auth.dependencies import get_current_user
from app.database.helpdesk_db import get_helpdesk_db
from app.models.chamado import Categoria, Prioridade, Status
from app.services.chamado_service import listar_responsaveis_possiveis
from app.services.contato_service import PAPEL_ADMIN, PAPEL_CAC, PAPEL_TECNICO, PAPEIS_VALIDOS, listar_contatos, salvar_contato
from app.templates_config import templates

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("")
async def painel_admin(request: Request, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN))):
    return templates.TemplateResponse("admin/painel.html", {"request": request, "usuario": usuario})


# --- Categorias ---

@router.get("/categorias")
async def listar_categorias(
    request: Request, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    categorias = (await db.execute(select(Categoria).order_by(Categoria.nome))).scalars().all()
    return templates.TemplateResponse(
        "admin/categorias.html", {"request": request, "usuario": usuario, "categorias": categorias},
    )


@router.post("/categorias")
async def criar_categoria(
    usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db), nome: str = Form(...),
):
    db.add(Categoria(nome=nome.strip(), ativo=True))
    await db.commit()
    return RedirectResponse("/admin/categorias", status_code=303)


@router.post("/categorias/{categoria_id}/toggle")
async def alternar_categoria(
    categoria_id: int, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    categoria = await db.get(Categoria, categoria_id)
    if categoria:
        categoria.ativo = not categoria.ativo
        await db.commit()
    return RedirectResponse("/admin/categorias", status_code=303)


# --- Prioridades ---

@router.get("/prioridades")
async def listar_prioridades(
    request: Request, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    prioridades = (await db.execute(select(Prioridade).order_by(Prioridade.ordem))).scalars().all()
    return templates.TemplateResponse(
        "admin/prioridades.html", {"request": request, "usuario": usuario, "prioridades": prioridades},
    )


@router.post("/prioridades")
async def criar_prioridade(
    usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
    nome: str = Form(...), ordem: int = Form(...), cor: str = Form(...), sla_horas: int = Form(...),
):
    db.add(Prioridade(nome=nome.strip(), ordem=ordem, cor=cor, sla_horas=sla_horas, ativo=True))
    await db.commit()
    return RedirectResponse("/admin/prioridades", status_code=303)


@router.post("/prioridades/{prioridade_id}/editar")
async def editar_prioridade(
    prioridade_id: int, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
    sla_horas: int = Form(...), cor: str = Form(...),
):
    prioridade = await db.get(Prioridade, prioridade_id)
    if prioridade:
        prioridade.sla_horas = sla_horas
        prioridade.cor = cor
        await db.commit()
    return RedirectResponse("/admin/prioridades", status_code=303)


@router.post("/prioridades/{prioridade_id}/toggle")
async def alternar_prioridade(
    prioridade_id: int, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    prioridade = await db.get(Prioridade, prioridade_id)
    if prioridade:
        prioridade.ativo = not prioridade.ativo
        await db.commit()
    return RedirectResponse("/admin/prioridades", status_code=303)


# --- Status (edição apenas — criação de status novo ainda exige migração) ---

@router.get("/status")
async def listar_status_admin(
    request: Request, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    status_list = (await db.execute(select(Status).order_by(Status.ordem))).scalars().all()
    return templates.TemplateResponse(
        "admin/status.html", {"request": request, "usuario": usuario, "status_list": status_list},
    )


@router.post("/status/{status_id}/editar")
async def editar_status(
    status_id: int, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
    cor: str = Form(...),
):
    status = await db.get(Status, status_id)
    if status:
        status.cor = cor
        await db.commit()
    return RedirectResponse("/admin/status", status_code=303)


# --- Contatos de WhatsApp ---

@router.get("/contatos")
async def listar_contatos_admin(
    request: Request, usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)), db: AsyncSession = Depends(get_helpdesk_db),
):
    responsaveis = await listar_responsaveis_possiveis()
    contatos = await listar_contatos(db)
    numero_por_codigo = {c.usuario_codigo: c.whatsapp_numero for c in contatos}
    papel_por_codigo = {c.usuario_codigo: c.papel for c in contatos}

    linhas = [
        {
            "codigo": r["codigo"], "nome": r["nome"],
            "numero": numero_por_codigo.get(r["codigo"], ""),
            "papel": papel_por_codigo.get(r["codigo"], PAPEL_CAC),
        }
        for r in responsaveis
    ]

    return templates.TemplateResponse(
        "admin/contatos.html",
        {"request": request, "usuario": usuario, "linhas": linhas, "papeis": [PAPEL_CAC, PAPEL_TECNICO, PAPEL_ADMIN]},
    )


@router.post("/contatos/{usuario_codigo}")
async def salvar_contato_admin(
    usuario_codigo: int,
    usuario: dict = Depends(exigir_papel(PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
    nome: str = Form(...),
    whatsapp_numero: str = Form(""),
    papel: str = Form(PAPEL_CAC),
):
    await salvar_contato(db, usuario_codigo, nome, whatsapp_numero or None, papel)
    return RedirectResponse("/admin/contatos", status_code=303)
