"""
Integração com a API pública do PacoteVicio (api.pacotevicio.dev) —
serviço gratuito de rastreio (1000 requisições/mês), sem precisar de
contrato próprio com os Correios.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def correios_configurado() -> bool:
    return bool(settings.pacotevicio_api_key)


async def consultar_rastreio(codigo_objeto: str) -> dict | None:
    """
    Retorna {"descricao_evento", "entregue", "cidade_remetente", "cidade_destinatario"}
    ou None se não foi possível consultar.
    """
    if not correios_configurado():
        return None

    url = f"https://api.pacotevicio.dev/v1/track/{codigo_objeto}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resposta = await client.get(url, headers={"X-API-Key": settings.pacotevicio_api_key})
            resposta.raise_for_status()
            dados = resposta.json()
    except Exception:
        logger.exception("Falha ao consultar rastreio do objeto %s", codigo_objeto)
        return None

    eventos = dados.get("events") or []
    # A API retorna os eventos em ordem cronológica crescente — o mais
    # recente é o último da lista.
    ultimo_evento = eventos[-1] if eventos else {}
    descricao = (
        ultimo_evento.get("courier_status_label")
        or ultimo_evento.get("description")
        or dados.get("status")
        or "Status não informado"
    )

    entregue = dados.get("status") == "delivered" or dados.get("delivered_at") is not None

    cidade_remetente = (dados.get("origin") or {}).get("city")
    cidade_destinatario = (dados.get("destination") or {}).get("city")

    return {
        "descricao_evento": descricao,
        "entregue": entregue,
        "cidade_remetente": cidade_remetente,
        "cidade_destinatario": cidade_destinatario,
    }