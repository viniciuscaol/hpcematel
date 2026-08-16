"""
Gerencia os números de WhatsApp associados a cada usuário do Help Desk,
usados para notificações individuais.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chamado import UsuarioContato


async def buscar_numero_whatsapp(db: AsyncSession, usuario_codigo: int) -> str | None:
    result = await db.execute(
        select(UsuarioContato).where(
            UsuarioContato.usuario_codigo == usuario_codigo, UsuarioContato.ativo.is_(True)
        )
    )
    contato = result.scalar_one_or_none()
    return contato.whatsapp_numero if contato else None


async def listar_contatos(db: AsyncSession) -> list[UsuarioContato]:
    result = await db.execute(select(UsuarioContato).order_by(UsuarioContato.usuario_nome_snapshot))
    return list(result.scalars().all())


async def salvar_contato(
    db: AsyncSession, usuario_codigo: int, usuario_nome: str, whatsapp_numero: str,
) -> UsuarioContato:
    result = await db.execute(select(UsuarioContato).where(UsuarioContato.usuario_codigo == usuario_codigo))
    contato = result.scalar_one_or_none()

    numero_limpo = "".join(c for c in whatsapp_numero if c.isdigit())

    if contato is None:
        contato = UsuarioContato(
            usuario_codigo=usuario_codigo, usuario_nome_snapshot=usuario_nome,
            whatsapp_numero=numero_limpo, ativo=True,
        )
        db.add(contato)
    else:
        contato.whatsapp_numero = numero_limpo
        contato.usuario_nome_snapshot = usuario_nome
        contato.ativo = True

    await db.commit()
    return contato