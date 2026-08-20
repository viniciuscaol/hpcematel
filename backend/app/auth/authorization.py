"""
Controle de acesso por papel (CAC, TECNICO, ADMIN).

get_current_user_com_papel: usada em telas, para saber o papel do
usuário e decidir o que mostrar (ex: esconder botão de excluir).

exigir_papel(...): dependência que barra a requisição com 403 se o
usuário não tiver um dos papéis permitidos — é essa a barreira real,
aplicada no backend, independente do que a tela mostra ou esconde.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database.helpdesk_db import get_helpdesk_db
from app.services.contato_service import buscar_papel_usuario


async def get_current_user_com_papel(
    usuario: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_helpdesk_db),
) -> dict:
    papel = await buscar_papel_usuario(db, usuario["codigo"])
    return {**usuario, "papel": papel}


def exigir_papel(*papeis_permitidos: str):
    async def checker(usuario: dict = Depends(get_current_user_com_papel)) -> dict:
        if usuario["papel"] not in papeis_permitidos:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Você não tem permissão para realizar esta ação.",
            )
        return usuario
    return checker