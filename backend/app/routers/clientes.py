"""
Rotas de busca e seleção de cliente, usadas no formulário de novo chamado (HTMX).
"""
from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import get_current_user
from app.services.cliente_service import buscar_clientes, buscar_cliente_por_codigo
from app.templates_config import templates

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("/buscar")
async def buscar(
    request: Request,
    termo: str = "",
    usuario: dict = Depends(get_current_user),
):
    clientes = await buscar_clientes(termo)
    return templates.TemplateResponse(
        "partials/clientes_resultado.html",
        {"request": request, "clientes": clientes},
    )


@router.get("/selecionar/{codigo}")
async def selecionar(codigo: int, request: Request, usuario: dict = Depends(get_current_user)):
    cliente = await buscar_cliente_por_codigo(codigo)
    return templates.TemplateResponse(
        "partials/cliente_selecionado.html",
        {"request": request, "cliente": cliente},
    )