"""
Rotas de chamados: listagem (filtros, busca, paginação), criação,
detalhe, edição de campos e exclusão lógica.

Padrão de UX: toda ação de edição (status, categoria, prioridade,
responsável, interação, anexo) recarrega a página do chamado inteira
após salvar, em vez de atualizar só um trecho. Isso evita duplo envio
acidental (ex: clicar várias vezes em "Enviar anexo" antes da resposta
voltar) e garante que a tela sempre mostre o estado mais recente.
"""
import math
from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response as PDFResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contato_service import PAPEL_ADMIN, PAPEL_TECNICO, buscar_numero_whatsapp
from app.services.notificacao_service import notificar_atribuicao_individual, notificar_mudanca_status, notificar_novo_chamado, notificar_diretoria
from app.auth.dependencies import get_current_user
from app.auth.authorization import exigir_papel, get_current_user_com_papel
from app.database.helpdesk_db import get_helpdesk_db
from app.models.chamado import Categoria, ChamadoAnexo, Prioridade
from app.services.anexo_service import ArquivoInvalido, caminho_fisico_anexo, salvar_anexo
from app.services.chamado_service import (
    POR_PAGINA_PADRAO,
    STATUS_CANCELADO_ID,
    STATUS_RESOLVIDO_ID,
    assumir_chamado,
    listar_chamados_para_assumir,
    ClienteNaoEncontrado,
    adicionar_interacao,
    atualizar_categorias,
    atualizar_prioridade,
    atualizar_responsavel,
    atualizar_status,
    contar_chamados,
    criar_chamado,
    excluir_anexo,
    excluir_chamado,
    listar_chamados,
    listar_responsaveis_possiveis,
    listar_status_ativos,
    obter_chamado,
    salvar_rastreios,
)
from app.templates_config import templates
from app.utils.datas import hoje_local
from app.services.os_service import gerar_pdf_os
from typing import Annotated
from app.routers.auth import limiter

router = APIRouter(prefix="/chamados", tags=["chamados"])


def _redirect_para_chamado(chamado_id: int) -> Response:
    resposta = Response(status_code=200)
    resposta.headers["HX-Redirect"] = f"/chamados/{chamado_id}"
    return resposta


def _parse_periodo(data_inicio: str | None, data_fim: str | None) -> tuple[date | None, date | None, str, str]:
    """
    Se os dois parâmetros vierem ausentes (primeiro carregamento da página),
    usa os últimos 3 dias como padrão. String vazia em qualquer um dos dois
    remove o filtro daquele lado (equivalente a "sem limite").
    """
    if data_inicio is None and data_fim is None:
        hoje = hoje_local()
        inicio = hoje - timedelta(days=2)
        return inicio, hoje, inicio.isoformat(), hoje.isoformat()

    inicio_obj = date.fromisoformat(data_inicio) if data_inicio else None
    fim_obj = date.fromisoformat(data_fim) if data_fim else None
    return inicio_obj, fim_obj, (data_inicio or ""), (data_fim or "")


def _query_string(filtro: str, data_inicio: str, data_fim: str, busca: str, cliente_codigo: int | None, categoria_id: int | None) -> str:
    partes = {"filtro": filtro}
    if data_inicio:
        partes["data_inicio"] = data_inicio
    if data_fim:
        partes["data_fim"] = data_fim
    if busca:
        partes["busca"] = busca
    if cliente_codigo:
        partes["cliente_codigo"] = cliente_codigo
    if categoria_id:
        partes["categoria_id"] = categoria_id
    return urlencode(partes)


async def _opcoes_edicao(db: AsyncSession) -> dict:
    categorias = (await db.execute(
        select(Categoria).where(Categoria.ativo.is_(True)).order_by(Categoria.nome)
    )).scalars().all()
    prioridades = (await db.execute(
        select(Prioridade).where(Prioridade.ativo.is_(True)).order_by(Prioridade.ordem)
    )).scalars().all()
    status_list = await listar_status_ativos(db)
    responsaveis = await listar_responsaveis_possiveis()
    return {
        "categorias": categorias, "prioridades": prioridades,
        "status_list": status_list, "responsaveis": responsaveis,
    }


async def _contexto_tabela(
    db, filtro: str, data_inicio: str | None, data_fim: str | None,
    busca: str, cliente_codigo: int | None, categoria_id: int | None, pagina: int,
) -> dict:
    data_inicio_obj, data_fim_obj, data_inicio_exibicao, data_fim_exibicao = _parse_periodo(data_inicio, data_fim)
    apenas_abertos = filtro == "abertos"

    total = await contar_chamados(db, apenas_abertos, data_inicio_obj, data_fim_obj, busca, cliente_codigo, categoria_id)
    total_paginas = max(math.ceil(total / POR_PAGINA_PADRAO), 1)
    pagina = min(max(pagina, 1), total_paginas)

    chamados = await listar_chamados(
        db, apenas_abertos, data_inicio_obj, data_fim_obj, busca, cliente_codigo, categoria_id, pagina, POR_PAGINA_PADRAO,
    )

    cliente_nome = chamados[0].cliente_nome_snapshot if (cliente_codigo and chamados) else None
    categoria_nome = None
    if categoria_id and chamados:
        for cat in chamados[0].categorias:
            if cat.id == categoria_id:
                categoria_nome = cat.nome
                break

    return {
        "chamados": chamados, "filtro": filtro,
        "data_inicio": data_inicio_exibicao, "data_fim": data_fim_exibicao,
        "busca": busca, "cliente_codigo": cliente_codigo, "cliente_nome": cliente_nome,
        "categoria_id": categoria_id, "categoria_nome": categoria_nome,
        "pagina": pagina, "total_paginas": total_paginas, "total_registros": total,
        "query_string": _query_string(filtro, data_inicio_exibicao, data_fim_exibicao, busca, cliente_codigo, categoria_id),
    }


@router.get("")
async def tela_lista_chamados(
    request: Request, usuario: dict = Depends(get_current_user_com_papel), db: AsyncSession = Depends(get_helpdesk_db),
    filtro: str = "abertos", data_inicio: str | None = None, data_fim: str | None = None,
    busca: str = "", cliente_codigo: int | None = None, categoria_id: int | None = None, pagina: int = 1,
):
    contexto = await _contexto_tabela(db, filtro, data_inicio, data_fim, busca, cliente_codigo, categoria_id, pagina)
    return templates.TemplateResponse("chamados_lista.html", {"request": request, "usuario": usuario, **contexto})


@router.get("/tabela")
async def tabela_chamados(
    request: Request, usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    filtro: str = "abertos", data_inicio: str = "", data_fim: str = "",
    busca: str = "", cliente_codigo: int | None = None, categoria_id: int | None = None, pagina: int = 1,
):
    contexto = await _contexto_tabela(db, filtro, data_inicio, data_fim, busca, cliente_codigo, categoria_id, pagina)
    return templates.TemplateResponse("partials/chamados_tabela.html", {"request": request, **contexto})


@router.get("/novo")
async def tela_novo_chamado(
    request: Request,
    usuario: dict = Depends(get_current_user_com_papel),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    opcoes = await _opcoes_edicao(db)
    return templates.TemplateResponse(
        "chamado_novo.html",
        {
            "request": request, "usuario": usuario,
            "categorias": opcoes["categorias"], "prioridades": opcoes["prioridades"],
            "responsaveis": opcoes["responsaveis"],
        },
    )


@router.post("/novo")
@limiter.limit("20/minute")
async def processar_novo_chamado(
    request: Request,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    cliente_codigo: int = Form(...),
    titulo: str = Form(..., max_length=255),
    descricao: str = Form("", max_length=5000),
    categoria_ids: list[int] = Form(...),
    prioridade_id: int = Form(...),
    responsavel_codigo: int = Form(...),
    codigo_rastreio_envio: str = Form(""),
):
    responsaveis = await listar_responsaveis_possiveis()
    encontrado = next((r for r in responsaveis if r["codigo"] == responsavel_codigo), None)
    responsavel_nome = encontrado["nome"] if encontrado else usuario["nome"]

    try:
        chamado = await criar_chamado(
            db,
            cliente_codigo=cliente_codigo, titulo=titulo, descricao=descricao,
            categoria_ids=categoria_ids, prioridade_id=prioridade_id,
            responsavel_codigo=responsavel_codigo, responsavel_nome=responsavel_nome,
            criado_por_codigo=usuario["codigo"], criado_por_nome=usuario["nome"],
        )
    except ClienteNaoEncontrado:
        return templates.TemplateResponse(
            "partials/form_erro.html",
            {"request": request, "mensagem": "Cliente selecionado não foi encontrado."},
        )

    chamado = await obter_chamado(db, chamado.id)

    await salvar_rastreios(db, chamado.id, codigo_rastreio_envio, None)

    await notificar_novo_chamado(
        db,
        chamado_id=chamado.id,
        cliente_nome=chamado.cliente_nome_snapshot,
        titulo=chamado.titulo,
        numero_chamado=chamado.numero_chamado,
        prioridade_nome=chamado.prioridade.nome,
        categoria_nome=", ".join(c.nome for c in chamado.categorias),
        responsavel_nome=chamado.responsavel_nome_snapshot,
    )

    await notificar_diretoria(
        db, cliente_nome=chamado.cliente_nome_snapshot, titulo=chamado.titulo, status_nome="Aberto",
    )

    numero = await buscar_numero_whatsapp(db, responsavel_codigo)
    if numero:
        await notificar_atribuicao_individual(
            db,
            whatsapp_numero=numero, responsavel_nome=chamado.responsavel_nome_snapshot,
            chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
            titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
        )

    resposta = Response(status_code=200)
    resposta.headers["HX-Redirect"] = "/chamados"
    return resposta


@router.get("/{chamado_id}")
async def tela_detalhe_chamado(
    chamado_id: int,
    request: Request,
    usuario: dict = Depends(get_current_user_com_papel),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return RedirectResponse("/chamados", status_code=303)

    opcoes = await _opcoes_edicao(db)
    return templates.TemplateResponse(
        "chamado_detalhe.html",
        {"request": request, "usuario": usuario, "chamado": chamado, "status_resolvido_id": STATUS_RESOLVIDO_ID, **opcoes},
    )


@router.post("/{chamado_id}/status")
@limiter.limit("30/minute")
async def alterar_status(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    status_id: int = Form(...),
    latitude: str | None = Form(None),
    longitude: str | None = Form(None),
):
    def _para_float_ou_none(valor: str | None) -> float | None:
        if not valor:
            return None
        try:
            return float(valor)
        except ValueError:
            return None

    latitude_num = _para_float_ou_none(latitude)
    longitude_num = _para_float_ou_none(longitude)

    chamado = await atualizar_status(db, chamado_id, status_id, usuario["codigo"], usuario["nome"], latitude_num, longitude_num)

    if chamado is not None and status_id in (STATUS_RESOLVIDO_ID, STATUS_CANCELADO_ID):
        await notificar_mudanca_status(
            db, chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
            titulo=chamado.titulo, numero_chamado=chamado.numero_chamado, status_nome=chamado.status.nome,
        )
        if status_id == STATUS_RESOLVIDO_ID:
            await notificar_diretoria(
                db, cliente_nome=chamado.cliente_nome_snapshot, titulo=chamado.titulo, status_nome=chamado.status.nome,
            )
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/categoria")
@limiter.limit("30/minute")
async def alterar_categorias(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(exigir_papel(PAPEL_TECNICO, PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
    categoria_ids: Annotated[list[int], Form()] = [],
):
    chamado_atual = await obter_chamado(db, chamado_id)
    if chamado_atual is None:
        return RedirectResponse("/chamados", status_code=303)

    # Categorias ficam travadas quando o chamado está finalizado (Resolvido/
    # Cancelado) — só volta a poder editar se o chamado for reaberto.
    if chamado_atual.status.finalizador:
        return RedirectResponse(f"/chamados/{chamado_id}", status_code=303)

    # Segurança extra: nunca aceita lista vazia (evita o 422 que gerava a
    # tela em branco se o formulário chegasse a ser enviado sem nada marcado).
    if not categoria_ids:
        return RedirectResponse(f"/chamados/{chamado_id}", status_code=303)

    await atualizar_categorias(db, chamado_id, categoria_ids, usuario["codigo"], usuario["nome"])
    return RedirectResponse(f"/chamados/{chamado_id}", status_code=303)


@router.post("/{chamado_id}/prioridade")
@limiter.limit("30/minute")
async def alterar_prioridade(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    prioridade_id: int = Form(...),
):
    await atualizar_prioridade(db, chamado_id, prioridade_id, usuario["codigo"], usuario["nome"])
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/responsavel")
@limiter.limit("30/minute")
async def alterar_responsavel(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    responsavel_codigo: int | None = Form(None),
):
    chamado = await atualizar_responsavel(db, chamado_id, responsavel_codigo, usuario["codigo"], usuario["nome"])

    if chamado is not None and responsavel_codigo:
        numero = await buscar_numero_whatsapp(db, responsavel_codigo)
        if numero:
            await notificar_atribuicao_individual(
                db,
                whatsapp_numero=numero, responsavel_nome=chamado.responsavel_nome_snapshot,
                chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
                titulo=chamado.titulo, numero_chamado=chamado.numero_chamado,
            )

    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/interacao")
@limiter.limit("30/minute")
async def registrar_interacao(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    texto: str = Form(..., max_length=3000),
):
    await adicionar_interacao(db, chamado_id, usuario["codigo"], usuario["nome"], texto)
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/excluir")
@limiter.limit("10/minute")
async def excluir(
    request: Request,
    chamado_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    await excluir_chamado(db, chamado_id, usuario["codigo"], usuario["nome"])
    resposta = Response(status_code=200)
    resposta.headers["HX-Redirect"] = "/chamados"
    return resposta


@router.post("/{chamado_id}/anexos")
@limiter.limit("10/minute")
async def upload_anexo(
    chamado_id: int,
    request: Request,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    arquivo: UploadFile = File(...),
):
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return RedirectResponse("/chamados", status_code=303)

    try:
        anexo = await salvar_anexo(chamado_id, arquivo, usuario["codigo"], usuario["nome"])
    except ArquivoInvalido as erro:
        opcoes = await _opcoes_edicao(db)
        return templates.TemplateResponse(
            "chamado_detalhe.html",
            {
                "request": request, "usuario": usuario, "chamado": chamado,
                "erro_anexo": str(erro), **opcoes,
            },
        )

    db.add(anexo)
    await db.commit()
    return _redirect_para_chamado(chamado_id)

@router.post("/{chamado_id}/anexos/{anexo_id}/excluir")
async def excluir_anexo_rota(
    chamado_id: int,
    anexo_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    await excluir_anexo(db, chamado_id, anexo_id, usuario["codigo"], usuario["nome"])
    return _redirect_para_chamado(chamado_id)


@router.get("/{chamado_id}/anexos/{anexo_id}")
async def baixar_anexo(
    chamado_id: int,
    anexo_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    anexo = await db.get(ChamadoAnexo, anexo_id)
    if anexo is None or anexo.chamado_id != chamado_id:
        return RedirectResponse("/chamados", status_code=303)

    caminho = caminho_fisico_anexo(chamado_id, anexo.nome_armazenado)
    return FileResponse(caminho, filename=anexo.nome_original, media_type=anexo.tipo_mime)

@router.post("/{chamado_id}/assumir")
async def assumir(
    chamado_id: int,
    usuario: dict = Depends(exigir_papel(PAPEL_TECNICO, PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    await assumir_chamado(db, chamado_id, usuario["codigo"], usuario["nome"])
    return _redirect_para_chamado(chamado_id)

@router.post("/{chamado_id}/rastreio")
async def salvar_rastreio_rota(
    chamado_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    codigo_rastreio_envio: str = Form(""),
):
    await salvar_rastreios(db, chamado_id, codigo_rastreio_envio, None)
    return _redirect_para_chamado(chamado_id)

@router.get("/{chamado_id}/os")
async def gerar_os_pdf(
    chamado_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    chamado = await obter_chamado(db, chamado_id)
    if chamado is None:
        return RedirectResponse("/chamados", status_code=303)

    pdf_bytes = gerar_pdf_os(chamado)
    return PDFResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="os-{chamado.numero_chamado}.pdf"'},
    )