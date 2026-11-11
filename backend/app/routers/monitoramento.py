"""Painel de monitoramento integrado ao login do Help Desk."""
import asyncio
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authorization import exigir_papel
from app.database.helpdesk_db import get_helpdesk_db
from app.models.monitoramento import MonitoramentoAcao
from app.services.contato_service import PAPEL_ADMIN, PAPEL_TECNICO
from app.services.monitoramento_service import obter_estado, obter_historico, coletar_e_salvar, executar_panico
from app.templates_config import templates

router = APIRouter()
ACESSO = exigir_papel(PAPEL_ADMIN, PAPEL_TECNICO)


@router.get("/monitoramento", response_class=HTMLResponse)
async def pagina_monitoramento(request: Request, usuario: dict = Depends(ACESSO)):
    return templates.TemplateResponse("monitoramento.html", {"request": request, "usuario": usuario})


@router.get("/api/monitoramento/status")
async def status_monitoramento(usuario: dict = Depends(ACESSO)):
    return obter_estado()


@router.get("/api/monitoramento/historico")
async def historico_monitoramento(
    minutos: int = 60, usuario: dict = Depends(ACESSO),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    return await obter_historico(db, minutos)


@router.post("/api/monitoramento/panico")
async def panico_monitoramento(
    request: Request, confirmacao: str = Form(...), senha: str = Form(...),
    usuario: dict = Depends(ACESSO), db: AsyncSession = Depends(get_helpdesk_db),
):
    if confirmacao != "REINICIAR":
        raise HTTPException(400, "Digite REINICIAR para confirmar.")
    sucesso, detalhe = await executar_panico(senha)
    db.add(MonitoramentoAcao(
        usuario_codigo=usuario["codigo"], usuario_login=usuario["login"],
        usuario_nome=usuario["nome"], resultado="sucesso" if sucesso else "falha",
        detalhe=detalhe,
    ))
    await db.commit()
    if not sucesso:
        raise HTTPException(400, detalhe)
    return {"ok": True, "mensagem": "Comando de emergência executado."}
