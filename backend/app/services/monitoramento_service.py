"""Coleta SSH sem agente remoto e execução controlada do botão de pânico."""
import asyncio
import hmac
import json
import shlex
import time
from datetime import datetime, timezone
from typing import Any

import paramiko
from sqlalchemy import delete, select

from app.config import settings
from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.monitoramento import MonitoramentoAmostra

_estado: dict[str, Any] = {"online": False, "erro": "Aguardando primeira coleta"}
_ultimo_cpu = None
_ultimo_panic = 0.0
_panic_lock = asyncio.Lock()


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
        comando = r"""bash -lc 'export LC_ALL=C; echo @@HOST; hostname; echo @@STAT; head -1 /proc/stat; echo @@MEM; awk "/MemTotal:|MemAvailable:|SwapTotal:|SwapFree:/ {print}" /proc/meminfo; echo @@LOAD; cat /proc/loadavg; echo @@UPTIME; cat /proc/uptime; echo @@PS; ps -eo pid=,user=,pcpu=,pmem=,comm= --sort=-pcpu | head -n 9'"""
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
    if _ultimo_cpu:
        dt, di = total - _ultimo_cpu[0], idle - _ultimo_cpu[1]
        if dt > 0:
            cpu = round(max(0.0, min(100.0, (dt - di) * 100 / dt)), 1)
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
    load = secoes.get("LOAD", [""])[0].split()
    uptime = float(secoes.get("UPTIME", ["0"])[0].split()[0])
    return {
        "online": True, "erro": None, "host": secoes.get("HOST", ["Servidor"])[0],
        "cpu": cpu, "memoria": memoria, "memoria_total_mb": round(total_mem / 1024),
        "memoria_usada_mb": round((total_mem - disponivel) / 1024),
        "swap_total_mb": round(mem.get("SwapTotal", 0) / 1024),
        "swap_livre_mb": round(mem.get("SwapFree", 0) / 1024),
        "load": load[:3], "uptime_segundos": int(uptime), "processos": processos,
        "coletado_em": datetime.now(timezone.utc).isoformat(),
    }


async def coletar_e_salvar() -> None:
    try:
        dados = await asyncio.to_thread(_coletar_bloqueante)
        _estado.clear()
        _estado.update(dados)
        async with HelpdeskSessionLocal() as db:
            db.add(MonitoramentoAmostra(
                cpu_percentual=dados["cpu"],
                memoria_percentual=dados["memoria"],
                detalhes_json=json.dumps({"load": dados["load"], "host": dados["host"]}),
            ))
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
    return [{"hora": a.coletado_em.isoformat(), "cpu": a.cpu_percentual, "memoria": a.memoria_percentual}
            for a in resultado.scalars().all()]


async def executar_panico(senha: str) -> tuple[bool, str]:
    global _ultimo_panic
    if not settings.monitor_panic_password or not settings.monitor_panic_script:
        return False, "Botão de pânico não configurado no servidor"
    if not hmac.compare_digest(senha, settings.monitor_panic_password):
        return False, "Senha de autorização inválida"
    if not settings.monitor_panic_script.startswith("/") or any(c in settings.monitor_panic_script for c in "\n\r"):
        return False, "Script de pânico inválido na configuração"
    async with _panic_lock:
        agora = time.monotonic()
        if agora - _ultimo_panic < 120:
            return False, "Aguarde 2 minutos antes de um novo acionamento"
        _ultimo_panic = agora
        return await asyncio.to_thread(_executar_panico_bloqueante)


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
    return bool(settings.monitor_panic_password and settings.monitor_panic_script)
