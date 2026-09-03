"""
Integração com a API pública do Seu Rastreio (seurastreio.com.br) —
serviço gratuito de rastreio, sem precisar de contrato próprio com os
Correios. Basta o código de rastreio informado pela agência parceira.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def correios_configurado() -> bool:
    return bool(settings.seurastreio_api_key)


async def consultar_rastreio(codigo_objeto: str) -> dict | None:
    """
    Retorna {"descricao_evento": str, "entregue": bool} com base no
    evento mais recente do objeto, ou None se não foi possível consultar.
    """
    if not correios_configurado():
        return None

    url = f"https://seurastreio.com.br/api/public/rastreio/{codigo_objeto}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resposta = await client.get(
                url, headers={"Authorization": f"Bearer {settings.seurastreio_api_key}"},
            )
            resposta.raise_for_status()
            dados = resposta.json()
    except Exception:
        logger.exception("Falha ao consultar rastreio do objeto %s", codigo_objeto)
        return None

    if not dados.get("success"):
        return None

    evento = dados.get("eventoMaisRecente") or {}
    descricao = evento.get("descricao") or evento.get("status") or "Status não informado"
    entregue = "entregue" in descricao.lower()

    return {"descricao_evento": descricao, "entregue": entregue}