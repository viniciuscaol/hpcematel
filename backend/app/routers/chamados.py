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
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contato_service import PAPEL_ADMIN, PAPEL_TECNICO, buscar_numero_whatsapp
from app.services.notificacao_service import notificar_atribuicao_individual, notificar_mudanca_status, notificar_novo_chamado
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

router = APIRouter(prefix="/chamados", tags=["chamados"])


def _redirect_para_chamado(chamado_id: int) -> Response:
    resposta = Response(status_code=200)
    resposta.headers["HX-Redirect"] = f"/chamados/{chamado_id}"
    return resposta


def _parse_data_filtro(data: str | None) -> tuple[date | None, str]:
    if data is None:
        hoje = hoje_local()
        return hoje, hoje.isoformat()
    if data == "":
        return None, ""
    return date.fromisoformat(data), data


def _query_string(filtro: str, data: str, busca: str, cliente_codigo: int | None) -> str:
    partes = {"filtro": filtro}
    if data:
        partes["data"] = data
    if busca:
        partes["busca"] = busca
    if cliente_codigo:
        partes["cliente_codigo"] = cliente_codigo
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
    db: AsyncSession, filtro: str, data: str, busca: str, cliente_codigo: int | None, pagina: int,
) -> dict:
    data_filtro, data_exibicao = _parse_data_filtro(data)
    apenas_abertos = filtro == "abertos"

    total = await contar_chamados(db, apenas_abertos, data_filtro, busca, cliente_codigo)
    total_paginas = max(math.ceil(total / POR_PAGINA_PADRAO), 1)
    pagina = min(max(pagina, 1), total_paginas)

    chamados = await listar_chamados(
        db, apenas_abertos, data_filtro, busca, cliente_codigo, pagina, POR_PAGINA_PADRAO,
    )

    cliente_nome = chamados[0].cliente_nome_snapshot if (cliente_codigo and chamados) else None

    return {
        "chamados": chamados,
        "filtro": filtro,
        "data_filtro": data_exibicao,
        "busca": busca,
        "cliente_codigo": cliente_codigo,
        "cliente_nome": cliente_nome,
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total_registros": total,
        "query_string": _query_string(filtro, data_exibicao, busca, cliente_codigo),
    }


@router.get("")
async def tela_lista_chamados(
    request: Request,
    usuario: dict = Depends(get_current_user_com_papel),
    db: AsyncSession = Depends(get_helpdesk_db),
    filtro: str = "abertos",
    data: str | None = None,
    busca: str = "",
    cliente_codigo: int | None = None,
    pagina: int = 1,
):
    contexto = await _contexto_tabela(db, filtro, data or "", busca, cliente_codigo, pagina)
    if data is None and cliente_codigo is None:
        contexto["data_filtro"] = hoje_local().isoformat()
    return templates.TemplateResponse(
        "chamados_lista.html", {"request": request, "usuario": usuario, **contexto},
    )


@router.get("/tabela")
async def tabela_chamados(
    request: Request,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    filtro: str = "abertos",
    data: str = "",
    busca: str = "",
    cliente_codigo: int | None = None,
    pagina: int = 1,
):
    contexto = await _contexto_tabela(db, filtro, data, busca, cliente_codigo, pagina)
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
async def processar_novo_chamado(
    request: Request,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
    cliente_codigo: int = Form(...),
    titulo: str = Form(...),
    descricao: str = Form(""),
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
async def alterar_status(
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
    
    chamado = await atualizar_status(db, chamado_id, status_id, usuario["codigo"], usuario["nome"], latitude, longitude)

    if chamado is not None and status_id in (STATUS_RESOLVIDO_ID, STATUS_CANCELADO_ID):
        await notificar_mudanca_status(
            db,
            chamado_id=chamado.id, cliente_nome=chamado.cliente_nome_snapshot,
            titulo=chamado.titulo, numero_chamado=chamado.numero_chamado, status_nome=chamado.status.nome,
        )
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/categoria")
async def alterar_categorias(
    chamado_id: int,
    usuario: dict = Depends(exigir_papel(PAPEL_TECNICO, PAPEL_ADMIN)),
    db: AsyncSession = Depends(get_helpdesk_db),
    categoria_ids: list[int] = Form(default=[]),
):
    await atualizar_categorias(db, chamado_id, categoria_ids, usuario["codigo"], usuario["nome"])
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/prioridade")
async def alterar_prioridade(
    chamado_id: int,
    usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    prioridade_id: int = Form(...),
):
    await atualizar_prioridade(db, chamado_id, prioridade_id, usuario["codigo"], usuario["nome"])
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/responsavel")
async def alterar_responsavel(
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
async def registrar_interacao(
    chamado_id: int,
    usuario: dict = Depends(get_current_user), db: AsyncSession = Depends(get_helpdesk_db),
    texto: str = Form(...),
):
    await adicionar_interacao(db, chamado_id, usuario["codigo"], usuario["nome"], texto)
    return _redirect_para_chamado(chamado_id)


@router.post("/{chamado_id}/excluir")
async def excluir(
    chamado_id: int,
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
):
    await excluir_chamado(db, chamado_id, usuario["codigo"], usuario["nome"])
    resposta = Response(status_code=200)
    resposta.headers["HX-Redirect"] = "/chamados"
    return resposta


@router.post("/{chamado_id}/anexos")
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
