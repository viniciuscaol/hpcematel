"""
Testa o cálculo de prazo de SLA, incluindo a extensão para o próximo
dia útil quando o prazo cai em fim de semana.
"""
from datetime import datetime, timezone

from app.utils.sla import calcular_prazo_sla, calcular_status_sla


def test_prazo_sla_em_dia_util_nao_e_estendido():
    # Segunda-feira às 10h, SLA de 4h -> vence na própria segunda, 14h
    criado_em = datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc)  # 10h em Salvador (UTC-3)
    prazo = calcular_prazo_sla(criado_em, sla_horas=4)
    assert prazo.weekday() == 0  # ainda segunda-feira


def test_prazo_sla_que_cairia_no_fim_de_semana_e_estendido():
    # Sexta-feira à noite, SLA de 24h -> cairia no sábado, deve empurrar pra segunda
    criado_em = datetime(2026, 8, 14, 22, 0, tzinfo=timezone.utc)
    prazo = calcular_prazo_sla(criado_em, sla_horas=24)
    assert prazo.weekday() not in (5, 6), "Prazo não deveria cair em sábado ou domingo"


def test_status_sla_finalizado_retorna_none():
    prazo_no_passado = datetime(2020, 1, 1, tzinfo=timezone.utc)
    resultado = calcular_status_sla(prazo_no_passado, status_id=4, status_finalizadores={4, 5}, status_pausa=set())
    assert resultado is None


def test_status_sla_pausado_nao_conta_como_estourado():
    prazo_no_passado = datetime(2020, 1, 1, tzinfo=timezone.utc)
    resultado = calcular_status_sla(prazo_no_passado, status_id=3, status_finalizadores={4, 5}, status_pausa={3, 6})
    assert resultado == "pausado"


def test_status_sla_estourado_quando_prazo_passou():
    prazo_no_passado = datetime(2020, 1, 1, tzinfo=timezone.utc)
    resultado = calcular_status_sla(prazo_no_passado, status_id=1, status_finalizadores={4, 5}, status_pausa=set())
    assert resultado == "estourado"