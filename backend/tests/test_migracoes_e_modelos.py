"""
Confirma que as migrações do Alembic criam exatamente o que os models
Python esperam. Este teste teria pego, por exemplo, uma tabela ou
coluna que existe no código mas nunca foi aplicada via migração.
"""
import pytest
from sqlalchemy import select

from app.database.helpdesk_db import HelpdeskSessionLocal
from app.models.chamado import Categoria, Prioridade, Status


async def test_tabelas_basicas_existem_e_estao_populadas():
    async with HelpdeskSessionLocal() as db:
        categorias = (await db.execute(select(Categoria))).scalars().all()
        prioridades = (await db.execute(select(Prioridade))).scalars().all()
        status_list = (await db.execute(select(Status))).scalars().all()

    assert len(categorias) > 0, "Seed de categorias não foi aplicado"
    assert len(prioridades) > 0, "Seed de prioridades não foi aplicado"
    assert len(status_list) > 0, "Seed de status não foi aplicado"


async def test_prioridade_tem_sla_horas_configurado():
    async with HelpdeskSessionLocal() as db:
        prioridades = (await db.execute(select(Prioridade))).scalars().all()

    for p in prioridades:
        assert p.sla_horas > 0, f"Prioridade '{p.nome}' está com sla_horas inválido"


async def test_existe_pelo_menos_um_status_finalizador():
    async with HelpdeskSessionLocal() as db:
        status_list = (await db.execute(select(Status))).scalars().all()

    assert any(s.finalizador for s in status_list), "Nenhum status está marcado como finalizador"