"""
Integração com a API oficial dos Correios (Correios API / CWS).

O token é gerado sob demanda e mantido em memória até perto de expirar
(a resposta da API já informa a validade). Se as credenciais não
estiverem configuradas, o serviço simplesmente não faz nada — não
quebra o resto do sistema.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_token_cache: dict = {"valor": None, "expira_em": None}

CODIGO_EVENTO_ENTREGUE = "BDE"


def correios_configurado() -> bool:
    return bool(settings.correios_usuario and settings.correios_senha and settings.correios_cartao_postagem)


async def _obter_token() -> str | None:
    if not correios_configurado():
        return None

    agora = datetime.now(timezone.utc)
    if _token_cache["valor"] and _token_cache["expira_em"] and agora < _token_cache["expira_em"]:
        return _token_cache["valor"]

    url = f"{settings.correios_base_url}/token/v1/autentica/cartaopostagem"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resposta = await client.post(
                url,
                auth=(settings.correios_usuario, settings.correios_senha),
                json={"numero": settings.correios_cartao_postagem},
            )
            resposta.raise_for_status()
            dados = resposta.json()
    except Exception:
        logger.exception("Falha ao autenticar na API dos Correios.")
        return None

    _token_cache["valor"] = dados["token"]
    # Margem de segurança: renova 10 minutos antes do vencimento real
    expira_em = datetime.fromisoformat(dados["expiraEm"]).replace(tzinfo=timezone.utc)
    _token_cache["expira_em"] = expira_em - timedelta(minutes=10)
    return _token_cache["valor"]


async def consultar_rastreio(codigo_objeto: str) -> dict | None:
    """
    Retorna {"descricao_evento": str, "codigo_evento": str, "entregue": bool}
    do evento mais recente do objeto, ou None se não foi possível consultar.
    """
    token = await _obter_token()
    if token is None:
        return None

    url = f"{settings.correios_base_url}/srorastro/v1/objetos/{codigo_objeto}?resultado=T"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resposta = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resposta.raise_for_status()
            dados = resposta.json()
    except Exception:
        logger.exception("Falha ao consultar rastreio do objeto %s", codigo_objeto)
        return None

    objetos = dados.get("objetos") or []
    if not objetos:
        return None

    eventos = objetos[0].get("eventos") or []
    if not eventos:
        return None

    # A API retorna do mais recente para o mais antigo
    ultimo = eventos[0]
    return {
        "descricao_evento": ultimo.get("descricao", ""),
        "codigo_evento": ultimo.get("codigo", ""),
        "entregue": ultimo.get("codigo") == CODIGO_EVENTO_ENTREGUE,
    }