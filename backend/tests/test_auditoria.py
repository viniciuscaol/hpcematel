""""Testes da trilha central de auditoria e do acesso exclusivo ADMIN."""
import pytest
from sqlalchemy import delete, select

from app.auth.security import create_access_token
from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.auditoria import AuditoriaLog
from app.models.chamado import UsuarioContato

pytestmark = pytest.mark.usefixtures("aplicar_migracoes")


async def _definir_papel(codigo: int, papel: str) -> None:
    async with HelpdeskSessionLocal() as db:
        contato = await db.scalar(
            select(UsuarioContato).where(UsuarioContato.usuario_codigo == codigo)
        )
        if contato is None:
            contato = UsuarioContato(
                usuario_codigo=codigo,
                usuario_nome_snapshot=f"Auditoria {papel}",
                papel=papel,
                ativo=True,
            )
            db.add(contato)
        else:
            contato.papel = papel
        await db.commit()


async def _limpar_usuario(codigo: int) -> None:
    async with HelpdeskSessionLocal() as db:
        await db.execute(delete(AuditoriaLog).where(AuditoriaLog.usuario_codigo == codigo))
        await db.execute(delete(UsuarioContato).where(UsuarioContato.usuario_codigo == codigo))
        await db.commit()


def _autenticar(client, codigo: int, papel: str) -> None:
    token = create_access_token(
        usuario_codigo=codigo,
        login=f"auditoria_{papel.lower()}",
        nome=f"Usuário {papel}",
    )
    client.cookies.set("session_token", token)


async def test_pagina_de_logs_e_exclusiva_para_admin(client):
    codigo = 987641
    try:
        await _definir_papel(codigo, "ADMIN")
        _autenticar(client, codigo, "ADMIN")
        resposta_admin = await client.get("/admin/logs")
        assert resposta_admin.status_code == 200
        assert "Logs / Auditoria" in resposta_admin.text

        await _definir_papel(codigo, "TECNICO")
        resposta_tecnico = await client.get("/admin/logs")
        assert resposta_tecnico.status_code == 403
    finally:
        await _limpar_usuario(codigo)


async def test_interacao_autenticada_gera_registro_de_consulta(client):
    codigo = 987642
    try:
        _autenticar(client, codigo, "ADMIN")
        resposta = await client.get("/")
        assert resposta.status_code == 307

        async with HelpdeskSessionLocal() as db:
            registro = await db.scalar(
                select(AuditoriaLog)
                .where(AuditoriaLog.usuario_codigo == codigo)
                .order_by(AuditoriaLog.id.desc())
                .limit(1)
            )
            assert registro is not None
            assert registro.tipo_evento == "consulta"
            assert registro.categoria == "sistema"
            assert registro.acao == "raiz"
            assert registro.resultado == "sucesso"
            assert registro.status_http == 307
    finally:
        await _limpar_usuario(codigo)


async def test_pesquisa_logs_aceita_datas_vazias(client):
    """O formulário HTML envia datas vazias quando nenhum período é informado."""
    codigo = 987643
    try:
        await _definir_papel(codigo, "ADMIN")
        _autenticar(client, codigo, "ADMIN")

        resposta = await client.get(
            "/admin/logs?q=&usuario=&categoria=&tipo_evento=&resultado="
            "&data_inicio=&data_fim="
        )

        assert resposta.status_code == 200
        assert "Logs / Auditoria" in resposta.text
    finally:
        await _limpar_usuario(codigo)
