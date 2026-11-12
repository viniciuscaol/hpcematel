"""Coleta SSH, alertas operacionais e execução controlada do botão de pânico."""
import asyncio
import hmac
import json
import secrets
import shlex
import string
import time
from datetime import datetime, timezone
from typing import Any

import paramiko
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select

from app.config import settings
from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import NotificacaoPendente
from app.models.monitoramento import MonitoramentoAmostra, MonitoramentoEstado
from app.utils.datas import FUSO_BAHIA

_estado: dict[str, Any] = {"online": False, "erro": "Aguardando primeira coleta"}
_ultimo_cpu = None
_ultimo_java_cpu: tuple[str, int] | None = None
_ultimo_panic = 0.0
_panic_lock = asyncio.Lock()


def _calcular_cpu_java(pid: str, ticks: int, delta_total: int) -> float:
    """Calcula a fatia de CPU do processo sobre a capacidade total do host."""
    global _ultimo_java_cpu
    percentual = 0.0
    if _ultimo_java_cpu and _ultimo_java_cpu[0] == pid and delta_total > 0:
        delta_processo = max(0, ticks - _ultimo_java_cpu[1])
        percentual = round(min(100.0, delta_processo * 100 / delta_total), 1)
    _ultimo_java_cpu = (pid, ticks)
    return percentual


def _fernet() -> Fernet:
    chave = settings.monitor_panic_encryption_key
    if not chave:
        raise RuntimeError("Chave de cifragem do monitoramento não configurada")
    return Fernet(chave.encode("ascii"))


def _nova_senha() -> str:
    alfabeto = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(16))


def _enfileirar_mensagem(db, mensagem: str) -> bool:
    destino = settings.waha_grupo_monitoramento_id
    if not destino:
        return False
    db.add(NotificacaoPendente(chat_id=destino, mensagem=mensagem, fora_horario=True))
    return True


async def _obter_estado_persistente(db) -> tuple[MonitoramentoEstado, str]:
    resultado = await db.execute(
        select(MonitoramentoEstado).where(MonitoramentoEstado.id == 1).with_for_update()
    )
    registro = resultado.scalar_one_or_none()
    if registro is None:
        inicial = settings.monitor_panic_password
        if len(inicial) < 16:
            raise RuntimeError("Senha inicial do botão de pânico não configurada")
        registro = MonitoramentoEstado(
            id=1,
            senha_atual_cifrada=_fernet().encrypt(inicial.encode()).decode(),
            faixa_cpu="normal",
        )
        db.add(registro)
        _enfileirar_mensagem(
            db,
            "🔐 *MONITORAMENTO — CREDENCIAL INICIAL*\n"
            "Senha de emergência disponível para ADMIN e TÉCNICOS:\n"
            f"*{inicial}*\nGuarde esta conversa. A senha será renovada após cada acionamento válido.",
        )
        await db.flush()
    try:
        senha = _fernet().decrypt(registro.senha_atual_cifrada.encode()).decode()
    except (InvalidToken, ValueError):
        raise RuntimeError("Não foi possível descriptografar a credencial de emergência")
    return registro, senha


def _ssh_client():
    if not all([settings.monitor_ssh_host, settings.monitor_ssh_user, settings.monitor_ssh_key]):
        raise RuntimeError("Coleta SSH não configurada")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if settings.monitor_ssh_known_hosts:
        client.load_host_keys(settings.monitor_ssh_known_hosts)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=settings.monitor_ssh_host,
        port=settings.monitor_ssh_port,
        username=settings.monitor_ssh_user,
        key_filename=settings.monitor_ssh_key,
        passphrase=settings.monitor_ssh_key_passphrase or None,
        timeout=8,
        banner_timeout=8,
        auth_timeout=8,
    )
    return client


def _coletar_bloqueante() -> dict[str, Any]:
    client = _ssh_client()
    try:
        comando = r"""bash -lc 'export LC_ALL=C; echo @@HOST; hostname; echo @@STAT; head -1 /proc/stat; echo @@MEM; awk "/MemTotal:|MemAvailable:|SwapTotal:|SwapFree:/ {print}" /proc/meminfo; echo @@LOAD; cat /proc/loadavg; echo @@UPTIME; cat /proc/uptime; echo @@PS; ps -eo pid=,user=,pcpu=,pmem=,comm= --sort=-pcpu | head -n 9; echo @@JAVA; java_pid=$(ps -ww -eo pid=,comm=,args= | awk "\$2 == \"java\" && /org.apache.catalina.startup.Bootstrap/ {print \$1; exit}"); if [ -n "$java_pid" ] && [ -r "/proc/$java_pid/stat" ]; then java_ticks=$(awk "{print \$14 + \$15}" "/proc/$java_pid/stat"); java_rss=$(awk "\$1 == \"VmRSS:\" {print \$2}" "/proc/$java_pid/status"); java_threads=$(awk "\$1 == \"Threads:\" {print \$2}" "/proc/$java_pid/status"); printf "%s %s %s %s\\n" "$java_pid" "$java_ticks" "$java_rss" "$java_threads"; fi'"""
        _, stdout, stderr = client.exec_command(comando, timeout=10)
        saida = stdout.read().decode("utf-8", "replace")
        erro = stderr.read().decode("utf-8", "replace")
        if erro and not saida:
            raise RuntimeError("Falha ao executar coleta remota")
    finally:
        client.close()

    secoes: dict[str, list[str]] = {}
    atual = ""
    for linha in saida.splitlines():
        if linha.startswith("@@"):
            atual = linha[2:].strip()
            secoes[atual] = []
        elif atual:
            secoes[atual].append(linha.strip())

    stat = secoes.get("STAT", [""])[0].split()
    valores = [int(x) for x in stat[1:]]
    idle = valores[3] + (valores[4] if len(valores) > 4 else 0)
    total = sum(valores)
    global _ultimo_cpu
    cpu = 0.0
    delta_total = 0
    if _ultimo_cpu:
        delta_total, di = total - _ultimo_cpu[0], idle - _ultimo_cpu[1]
        if delta_total > 0:
            cpu = round(max(0.0, min(100.0, (delta_total - di) * 100 / delta_total)), 1)
    _ultimo_cpu = (total, idle)

    mem = {}
    for linha in secoes.get("MEM", []):
        partes = linha.replace(":", "").split()
        if len(partes) >= 2:
            mem[partes[0]] = int(partes[1])
    total_mem = mem.get("MemTotal", 0)
    disponivel = mem.get("MemAvailable", mem.get("MemFree", 0))
    memoria = round((total_mem - disponivel) * 100 / total_mem, 1) if total_mem else 0
    processos = []
    for linha in secoes.get("PS", []):
        p = linha.split(None, 4)
        if len(p) == 5:
            processos.append({"pid": p[0], "usuario": p[1], "cpu": float(p[2]), "memoria": float(p[3]), "nome": p[4]})
    global _ultimo_java_cpu
    java = None
    linhas_java = secoes.get("JAVA", [])
    if linhas_java:
        partes_java = linhas_java[0].split()
        if len(partes_java) == 4:
            pid_java, ticks_java, rss_kb, threads_java = partes_java
            ticks_java = int(ticks_java)
            cpu_java = _calcular_cpu_java(pid_java, ticks_java, delta_total)
            rss_kb = int(rss_kb or 0)
            java = {
                "pid": int(pid_java),
                "cpu": cpu_java,
                "memoria_mb": round(rss_kb / 1024),
                "memoria_percentual": round(rss_kb * 100 / total_mem, 1) if total_mem else 0.0,
                "threads": int(threads_java or 0),
            }
    else:
        _ultimo_java_cpu = None

    load = secoes.get("LOAD", [""])[0].split()
    uptime = float(secoes.get("UPTIME", ["0"])[0].split()[0])
    return {
        "online": True, "erro": None, "host": secoes.get("HOST", ["Servidor"])[0],
        "cpu": cpu, "memoria": memoria, "java": java, "memoria_total_mb": round(total_mem / 1024),
        "memoria_usada_mb": round((total_mem - disponivel) / 1024),
        "swap_total_mb": round(mem.get("SwapTotal", 0) / 1024),
        "swap_livre_mb": round(mem.get("SwapFree", 0) / 1024),
        "load": load[:3], "uptime_segundos": int(uptime), "processos": processos,
        "coletado_em": datetime.now(timezone.utc).isoformat(),
    }


async def _avaliar_alerta_cpu(db, cpu: float) -> None:
    if not settings.waha_grupo_monitoramento_id:
        return
    try:
        registro, senha = await _obter_estado_persistente(db)
    except RuntimeError:
        return

    faixa_anterior = registro.faixa_cpu
    if cpu > 50:
        faixa_nova = "urgencia"
    elif cpu > 30:
        faixa_nova = "alerta"
    elif cpu < 25:
        faixa_nova = "normal"
    else:
        faixa_nova = faixa_anterior

    if faixa_nova == faixa_anterior:
        return

    agora = datetime.now(FUSO_BAHIA).strftime("%d/%m/%Y %H:%M:%S")
    if faixa_nova == "urgencia":
        mensagem = (
            "🚨 *URGÊNCIA — CPU ACIMA DE 50%*\n"
            f"Servidor: {settings.monitor_ssh_host}\nCPU: *{cpu:.1f}%*\nHorário: {agora}"
        )
    elif faixa_nova == "alerta":
        mensagem = (
            "⚠️ *ALERTA — CPU ACIMA DE 30%*\n"
            f"Servidor: {settings.monitor_ssh_host}\nCPU: *{cpu:.1f}%*\nHorário: {agora}"
        )
    else:
        mensagem = (
            "✅ *CPU NORMALIZADA*\n"
            f"Servidor: {settings.monitor_ssh_host}\nCPU: *{cpu:.1f}%*\nHorário: {agora}"
        )
    mensagem += f"\n\n🔐 Senha vigente do botão de emergência: *{senha}*"
    _enfileirar_mensagem(db, mensagem)
    registro.faixa_cpu = faixa_nova


async def coletar_e_salvar() -> None:
    try:
        dados = await asyncio.to_thread(_coletar_bloqueante)
        _estado.clear()
        _estado.update(dados)
        async with HelpdeskSessionLocal() as db:
            db.add(MonitoramentoAmostra(
                cpu_percentual=dados["cpu"],
                memoria_percentual=dados["memoria"],
                detalhes_json=json.dumps({
                    "load": dados["load"], "host": dados["host"], "java": dados.get("java")
                }),
            ))
            await _avaliar_alerta_cpu(db, dados["cpu"])
            await db.execute(delete(MonitoramentoAmostra).where(
                MonitoramentoAmostra.coletado_em < datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            ))
            await db.commit()
    except Exception:
        _estado.clear()
        _estado.update({"online": False, "erro": "Servidor indisponível ou coleta SSH não configurada"})


def obter_estado() -> dict[str, Any]:
    return dict(_estado)


async def obter_historico(db, minutos: int = 60) -> list[dict[str, Any]]:
    from datetime import timedelta
    desde = datetime.now(timezone.utc) - timedelta(minutes=max(5, min(minutos, 1440)))
    resultado = await db.execute(
        select(MonitoramentoAmostra).where(MonitoramentoAmostra.coletado_em >= desde)
        .order_by(MonitoramentoAmostra.coletado_em).limit(2000)
    )
    amostras = []
    for amostra in resultado.scalars().all():
        try:
            detalhes = json.loads(amostra.detalhes_json or "{}")
        except (TypeError, ValueError):
            detalhes = {}
        java = detalhes.get("java") or {}
        amostras.append({
            "hora": amostra.coletado_em.isoformat(),
            "cpu": amostra.cpu_percentual,
            "memoria": amostra.memoria_percentual,
            "java_cpu": java.get("cpu"),
            "java_memoria": java.get("memoria_percentual"),
        })
    return amostras


async def executar_panico(senha: str, db, usuario: dict) -> tuple[bool, str]:
    global _ultimo_panic
    if not panico_configurado():
        return False, "Botão de pânico não configurado corretamente no servidor"
    async with _panic_lock:
        agora_monotonic = time.monotonic()
        if agora_monotonic - _ultimo_panic < 120:
            return False, "Aguarde 2 minutos antes de um novo acionamento"
        try:
            registro, senha_atual = await _obter_estado_persistente(db)
        except RuntimeError:
            return False, "Credencial de emergência indisponível"
        if not hmac.compare_digest(senha, senha_atual):
            return False, "Senha de autorização inválida"

        _ultimo_panic = agora_monotonic
        sucesso, detalhe = await asyncio.to_thread(_executar_panico_bloqueante)
        # A senha é de uso único: após qualquer tentativa autenticada, ela é renovada.
        nova_senha = _nova_senha()
        registro.senha_atual_cifrada = _fernet().encrypt(nova_senha.encode()).decode()
        horario = datetime.now(FUSO_BAHIA).strftime("%d/%m/%Y %H:%M:%S")
        resultado = "Script executado com sucesso" if sucesso else f"Falha na execução: {detalhe}"
        mensagem = (
            "🚨 *BOTÃO DE PÂNICO ACIONADO*\n"
            f"Servidor: {settings.monitor_ssh_host}\n"
            f"Acionado por: *{usuario.get('nome') or usuario.get('login')}*\n"
            f"Horário: {horario}\nResultado: {resultado}\n\n"
            f"🔐 *NOVA SENHA DE EMERGÊNCIA:*\n*{nova_senha}*\n"
            "A senha anterior foi invalidada. Esta senha será usada no próximo acionamento."
        )
        _enfileirar_mensagem(db, mensagem)
        return sucesso, detalhe


def _executar_panico_bloqueante() -> tuple[bool, str]:
    client = None
    try:
        client = _ssh_client()
        alvo = shlex.quote(settings.monitor_panic_script)
        comando = f"sudo -n {alvo}" if settings.monitor_panic_sudo else alvo
        _, stdout, stderr = client.exec_command(comando, timeout=30)
        codigo = stdout.channel.recv_exit_status()
        detalhe = stderr.read().decode("utf-8", "replace")[:1000]
        return (codigo == 0, "Comando executado" if codigo == 0 else (detalhe or f"Comando retornou código {codigo}"))
    except Exception:
        return False, "Não foi possível executar o script remoto"
    finally:
        if client:
            client.close()


def panico_configurado() -> bool:
    script = settings.monitor_panic_script
    return bool(
        len(settings.monitor_panic_password) >= 16
        and settings.monitor_panic_encryption_key
        and settings.waha_api_key
        and settings.waha_grupo_monitoramento_id
        and script.startswith("/")
        and "\n" not in script and "\r" not in script
    )
