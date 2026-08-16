"""
Utilitários de data/hora para exibição e filtro na interface.

O PostgreSQL armazena os horários em UTC. Como a operação é em
Salvador/BA (UTC-3, sem horário de verão desde 2019), convertemos
para o horário local apenas na exibição e nos filtros por dia.
"""
from datetime import date, datetime, time, timedelta, timezone

FUSO_BAHIA = timezone(timedelta(hours=-3))


def para_horario_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(FUSO_BAHIA)


def formatar_data_br(dt: datetime | None) -> str:
    dt_local = para_horario_local(dt)
    if dt_local is None:
        return "-"
    return dt_local.strftime("%d/%m/%Y %H:%M")


def hoje_local() -> date:
    return datetime.now(FUSO_BAHIA).date()


def intervalo_utc_do_dia(data_local: date) -> tuple[datetime, datetime]:
    """Devolve (início, fim) em UTC correspondentes ao dia local informado."""
    inicio_local = datetime.combine(data_local, time.min, tzinfo=FUSO_BAHIA)
    fim_local = inicio_local + timedelta(days=1)
    return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)