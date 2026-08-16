"""
Upload e download de anexos dos chamados.

Regras de segurança:
- Extensão validada contra lista branca (evita upload de executáveis).
- Nome do arquivo em disco é um UUID gerado pelo servidor — nunca o nome
  original — evitando path traversal e colisão de nomes.
- Tamanho máximo de 15MB por arquivo.
- Arquivos ficam fora de qualquer pasta servida como estático; o download
  só acontece por uma rota autenticada (nunca por link direto).
"""
import os
import uuid

from fastapi import UploadFile

from app.config import settings
from app.models.chamado import ChamadoAnexo

EXTENSOES_PERMITIDAS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}
TAMANHO_MAXIMO_BYTES = 15 * 1024 * 1024  # 15MB


class ArquivoInvalido(Exception):
    pass


def _validar_extensao(nome_original: str) -> str:
    _, ext = os.path.splitext(nome_original.lower())
    if ext not in EXTENSOES_PERMITIDAS:
        raise ArquivoInvalido(
            f"Tipo de arquivo não permitido ({ext or 'sem extensão'}). "
            f"Permitidos: {', '.join(sorted(EXTENSOES_PERMITIDAS))}"
        )
    return ext


async def salvar_anexo(
    chamado_id: int,
    arquivo: UploadFile,
    enviado_por_codigo: int,
    enviado_por_nome: str,
) -> ChamadoAnexo:
    ext = _validar_extensao(arquivo.filename or "")

    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise ArquivoInvalido("Arquivo maior que o limite de 15MB.")

    pasta_chamado = os.path.join(settings.anexos_dir, str(chamado_id))
    os.makedirs(pasta_chamado, exist_ok=True)

    nome_armazenado = f"{uuid.uuid4().hex}{ext}"
    caminho_completo = os.path.join(pasta_chamado, nome_armazenado)
    with open(caminho_completo, "wb") as f:
        f.write(conteudo)

    return ChamadoAnexo(
        chamado_id=chamado_id,
        nome_original=arquivo.filename,
        nome_armazenado=nome_armazenado,
        tipo_mime=arquivo.content_type or "application/octet-stream",
        tamanho_bytes=len(conteudo),
        enviado_por_codigo=enviado_por_codigo,
        enviado_por_nome_snapshot=enviado_por_nome,
    )


def caminho_fisico_anexo(chamado_id: int, nome_armazenado: str) -> str:
    return os.path.join(settings.anexos_dir, str(chamado_id), nome_armazenado)