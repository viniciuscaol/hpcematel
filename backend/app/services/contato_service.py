"""
Gerencia contato de WhatsApp e papel (permissão) de cada usuário do Help Desk.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chamado import UsuarioContato

PAPEL_ADMIN = "ADMIN"
PAPEL_TECNICO = "TECNICO"
PAPEL_CAC = "CAC"
PAPEIS_VALIDOS = {PAPEL_ADMIN, PAPEL_TECNICO, PAPEL_CAC}


async def buscar_numero_whatsapp(db: AsyncSession, usuario_codigo: int) -> str | None:
    result = await db.execute(
        select(UsuarioContato).where(
            UsuarioContato.usuario_codigo == usuario_codigo, UsuarioContato.ativo.is_(True)
        )
    )
    contato = result.scalar_one_or_none()
    return contato.whatsapp_numero if contato else None


async def buscar_papel_usuario(db: AsyncSession, usuario_codigo: int) -> str:
    result = await db.execute(
        select(UsuarioContato.papel).where(
            UsuarioContato.usuario_codigo == usuario_codigo, UsuarioContato.ativo.is_(True)
        )
    )
    papel = result.scalar_one_or_none()
    return papel or PAPEL_CAC  # sem registro = perfil mais restrito, por segurança


async def listar_contatos(db: AsyncSession) -> list[UsuarioContato]:
    result = await db.execute(select(UsuarioContato).order_by(UsuarioContato.usuario_nome_snapshot))
    return list(result.scalars().all())


async def salvar_contato(
    db: AsyncSession,
    usuario_codigo: int,
    usuario_nome: str,
    whatsapp_numero: str | None = None,
    papel: str | None = None,
) -> UsuarioContato:
    result = await db.execute(select(UsuarioContato).where(UsuarioContato.usuario_codigo == usuario_codigo))
    contato = result.scalar_one_or_none()

    numero_limpo = "".join(c for c in whatsapp_numero if c.isdigit()) if whatsapp_numero else None
    papel_valido = papel if papel in PAPEIS_VALIDOS else PAPEL_CAC

    if contato is None:
        contato = UsuarioContato(
            usuario_codigo=usuario_codigo,
            usuario_nome_snapshot=usuario_nome,
            whatsapp_numero=numero_limpo,
            papel=papel_valido,
            ativo=True,
        )
        db.add(contato)
    else:
        if whatsapp_numero is not None:
            contato.whatsapp_numero = numero_limpo
        if papel is not None:
            contato.papel = papel_valido
        contato.usuario_nome_snapshot = usuario_nome
        contato.ativo = True

    await db.commit()
    return contato