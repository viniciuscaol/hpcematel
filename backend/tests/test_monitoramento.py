"""Acesso ao painel e às APIs de monitoramento respeita o papel do Help Desk."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.security import create_access_token
from app.auth import authorization
from app.database.helpdesk_db import get_helpdesk_db
from app.main import app
from app.routers.auth import limiter


@pytest.fixture
def contexto_monitoramento(monkeypatch):
    db = MagicMock()
    db.commit = AsyncMock()
    papel = AsyncMock(return_value="CAC")

    async def banco_fake():
        yield db

    app.dependency_overrides[get_helpdesk_db] = banco_fake
    monkeypatch.setattr(authorization, "buscar_papel_usuario", papel)
    limiter.reset()
    yield SimpleNamespace(db=db, papel=papel)
    app.dependency_overrides.pop(get_helpdesk_db, None)
    limiter.reset()


def autenticar_monitoramento(client):
    token = create_access_token(usuario_codigo=10, login="teste", nome="Usuário Teste")
    client.cookies.set("session_token", token)


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
async def test_painel_monitoramento_restringe_por_papel(client, contexto_monitoramento, papel, esperado):
    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = papel

    resposta = await client.get("/monitoramento")

    assert resposta.status_code == esperado
    if esperado == 200:
        assert "Botão de pânico" in resposta.text
        assert "/static/js/monitoramento.js" in resposta.text


@pytest.mark.parametrize("papel,esperado", [("CAC", 403), ("TECNICO", 200), ("ADMIN", 200)])
async def test_api_status_monitoramento_restringe_por_papel(client, contexto_monitoramento, papel, esperado):
    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = papel

    resposta = await client.get("/api/monitoramento/status")

    assert resposta.status_code == esperado


async def test_painel_monitoramento_exige_sessao(client, contexto_monitoramento):
    resposta = await client.get("/monitoramento")

    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith("/login?")


def test_modelos_monitoramento_estao_registrados():
    from app.models.monitoramento import MonitoramentoAcao, MonitoramentoAmostra, MonitoramentoEstado

    assert MonitoramentoAmostra.__tablename__ == "monitoramento_amostra"
    assert MonitoramentoAcao.__tablename__ == "monitoramento_acao"
    assert MonitoramentoEstado.__tablename__ == "monitoramento_estado"

async def test_acionamento_panico_audita_usuario_autenticado(client, contexto_monitoramento, monkeypatch):
    from app.routers import monitoramento

    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = "TECNICO"
    executar = AsyncMock(return_value=(True, "Script executado"))
    monkeypatch.setattr(monitoramento, "executar_panico", executar)

    resposta = await client.post(
        "/api/monitoramento/panico",
        data={"confirmacao": "REINICIAR", "senha": "senha-de-teste"},
    )

    assert resposta.status_code == 200
    executar.assert_awaited_once()
    assert executar.await_args.args[0] == "senha-de-teste"
    assert executar.await_args.args[1] is contexto_monitoramento.db
    assert executar.await_args.args[2]["login"] == "teste"
    registro = contexto_monitoramento.db.add.call_args.args[0]
    assert registro.usuario_codigo == 10
    assert registro.usuario_login == "teste"
    assert registro.usuario_nome == "Usuário Teste"
    assert registro.resultado == "sucesso"
    contexto_monitoramento.db.commit.assert_awaited_once()


async def test_confirmacao_invalida_e_auditada_sem_executar_panico(client, contexto_monitoramento, monkeypatch):
    from app.routers import monitoramento

    autenticar_monitoramento(client)
    contexto_monitoramento.papel.return_value = "ADMIN"
    executar = AsyncMock()
    monkeypatch.setattr(monitoramento, "executar_panico", executar)

    resposta = await client.post(
        "/api/monitoramento/panico",
        data={"confirmacao": "SIM", "senha": "senha-de-teste"},
    )

    assert resposta.status_code == 400
    executar.assert_not_awaited()
    registro = contexto_monitoramento.db.add.call_args.args[0]
    assert registro.usuario_codigo == 10
    assert registro.resultado == "falha"
    assert registro.detalhe == "Confirmação textual inválida"
    contexto_monitoramento.db.commit.assert_awaited_once()


def test_senha_rotativa_tem_formato_aleatorio():
    from app.services.monitoramento_service import _nova_senha

    primeira = _nova_senha()
    segunda = _nova_senha()

    assert len(primeira) == 16
    assert primeira.isalnum()
    assert primeira.isupper()
    assert primeira != segunda


def test_notificacao_monitoramento_e_enfileirada_para_24h(monkeypatch):
    from app.services.monitoramento_service import _enfileirar_mensagem
    from app.config import settings

    monkeypatch.setattr(settings, "waha_grupo_monitoramento_id", "grupo-operacional@g.us")
    db = MagicMock()

    assert _enfileirar_mensagem(db, "alerta de teste") is True
    notificacao = db.add.call_args.args[0]
    assert notificacao.chat_id == "grupo-operacional@g.us"
    assert notificacao.mensagem == "alerta de teste"
    assert notificacao.fora_horario is True



def test_cpu_java_e_calculada_por_delta_de_ticks(monkeypatch):
    from app.services import monitoramento_service as servico

    monkeypatch.setattr(servico, "_ultimo_java_cpu", None)
    # A primeira amostra apenas estabelece a linha de base.
    primeira = servico._calcular_cpu_java("21432", 1000, 0)
    segunda = servico._calcular_cpu_java("21432", 1040, 1000)
    terceira = servico._calcular_cpu_java("21432", 1060, 1000)

    assert primeira == 0.0
    assert segunda == 4.0
    assert terceira == 2.0


def test_cpu_java_reinicia_linha_de_base_quando_pid_muda(monkeypatch):
    from app.services import monitoramento_service as servico

    monkeypatch.setattr(servico, "_ultimo_java_cpu", ("21432", 1000))
    resultado = servico._calcular_cpu_java("30000", 5000, 1000)

    assert resultado == 0.0
    assert servico._ultimo_java_cpu == ("30000", 5000)



def test_coleta_identifica_tomcat_com_argumentos_longos(monkeypatch):
    from app.services import monitoramento_service as servico

    class Saida:
        def __init__(self, conteudo):
            self.conteudo = conteudo

        def read(self):
            return self.conteudo.encode()

    class ClienteSSH:
        comando = ""

        def exec_command(self, comando, timeout):
            self.comando = comando
            saida = """@@HOST
servidor-teste
@@STAT
cpu 100 0 50 1000 0 0 0 0 0 0
@@MEM
MemTotal: 8000000 kB
MemAvailable: 6000000 kB
SwapTotal: 0 kB
SwapFree: 0 kB
@@LOAD
0.10 0.20 0.30 1/100 123
@@UPTIME
1000.00 2000.00
@@PS
21432 root 2.7 19.5 java
@@JAVA
21432 485875 1565288 167
"""
            return None, Saida(saida), Saida("")

        def close(self):
            pass

    cliente = ClienteSSH()
    monkeypatch.setattr(servico, "_ssh_client", lambda: cliente)
    monkeypatch.setattr(servico, "_ultimo_cpu", None)
    monkeypatch.setattr(servico, "_ultimo_java_cpu", None)

    resultado = servico._coletar_bloqueante()

    assert "ps -ww -eo pid=,comm=,args=" in cliente.comando
    assert resultado["java"] == {
        "pid": 21432,
        "cpu": 0.0,
        "memoria_mb": 1529,
        "memoria_percentual": 19.6,
        "threads": 167,
    }
