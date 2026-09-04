"""
Integração com a API pública do Seu Rastreio (seurastreio.com.br).
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def correios_configurado() -> bool:
    return bool(settings.seurastreio_api_key)


def _extrair_cidades(dados: dict) -> tuple[str | None, str | None]:
    """
    Tenta achar origem/destino em alguns formatos possíveis da resposta.
    Se não encontrar nada reconhecível, retorna (None, None) sem quebrar —
    nesse caso a notificação simplesmente não mostra essas linhas.
    """
    origem = dados.get("origem") or dados.get("cidadeOrigem") or dados.get("remetente")
    destino = dados.get("destino") or dados.get("cidadeDestino") or dados.get("destinatario")

    if not origem and not destino:
        localizacao = dados.get("localizacao")
        if isinstance(localizacao, str) and "→" in localizacao:
            partes = [p.strip() for p in localizacao.split("→")]
            if len(partes) == 2:
                origem, destino = partes
        elif isinstance(localizacao, dict):
            origem = origem or localizacao.get("origem")
            destino = destino or localizacao.get("destino")

    return origem, destino


async def consultar_rastreio(codigo_objeto: str) -> dict | None:
    """
    Retorna {"descricao_evento", "entregue", "cidade_remetente", "cidade_destinatario"}
    ou None se não foi possível consultar.
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

    evento = dados.get("eventoMaisRecente") or {}
    descricao = evento.get("descricao") or evento.get("status") or dados.get("status") or "Status não informado"
    entregue = "entregue" in descricao.lower()

    cidade_remetente, cidade_destinatario = _extrair_cidades(dados)

    return {
        "descricao_evento": descricao,
        "entregue": entregue,
        "cidade_remetente": cidade_remetente,
        "cidade_destinatario": cidade_destinatario,
    }