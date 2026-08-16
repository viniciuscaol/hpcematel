"""
Cálculo de prazo de SLA. O número de horas vem da própria prioridade
(configurável pelo painel de admin), não mais fixo no código.
"""
from datetime import datetime, timedelta, timezone

from app.utils.datas import para_horario_local

STATUS_ESTOURADO = "estourado"
STATUS_PROXIMO = "proximo"
STATUS_OK = "ok"


def calcular_prazo_sla(criado_em: datetime, sla_horas: int) -> datetime:
    inicio_local = para_horario_local(criado_em)
    prazo_local = inicio_local + timedelta(hours=sla_horas)

    while prazo_local.weekday() in (5, 6):
        prazo_local += timedelta(days=1)

    return prazo_local.astimezone(timezone.utc)


def calcular_status_sla(prazo_sla: datetime, status_id: int, status_finalizadores: set[int]) -> str | None:
    if status_id in status_finalizadores:
        return None

    agora = datetime.now(timezone.utc)
    prazo = prazo_sla if prazo_sla.tzinfo else prazo_sla.replace(tzinfo=timezone.utc)
    restante = prazo - agora

    if restante.total_seconds() <= 0:
        return STATUS_ESTOURADO
    if restante.total_seconds() <= 4 * 3600:
        return STATUS_PROXIMO
    return STATUS_OK