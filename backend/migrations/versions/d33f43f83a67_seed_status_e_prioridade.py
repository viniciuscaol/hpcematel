"""seed status e prioridade

Revision ID: d33f43f83a67
Revises: de4b99d93b54
Create Date: 2026-08-11 19:01:48.240319

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd33f43f83a67'
down_revision = 'de4b99d93b54'
branch_labels = None
depends_on = None


status_table = sa.table(
    "status",
    sa.column("id", sa.Integer),
    sa.column("nome", sa.String),
    sa.column("ordem", sa.Integer),
    sa.column("cor", sa.String),
    sa.column("ativo", sa.Boolean),
)

prioridade_table = sa.table(
    "prioridade",
    sa.column("id", sa.Integer),
    sa.column("nome", sa.String),
    sa.column("ordem", sa.Integer),
    sa.column("cor", sa.String),
    sa.column("ativo", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        status_table,
        [
            {"id": 1, "nome": "Aberto", "ordem": 1, "cor": "#2563eb", "ativo": True},
            {"id": 2, "nome": "Em andamento", "ordem": 2, "cor": "#d97706", "ativo": True},
            {"id": 3, "nome": "Aguardando cliente", "ordem": 3, "cor": "#7c3aed", "ativo": True},
            {"id": 4, "nome": "Resolvido", "ordem": 4, "cor": "#16a34a", "ativo": True},
            {"id": 5, "nome": "Encerrado", "ordem": 5, "cor": "#6b7280", "ativo": True},
        ],
    )
    op.bulk_insert(
        prioridade_table,
        [
            {"id": 1, "nome": "Baixa", "ordem": 1, "cor": "#16a34a", "ativo": True},
            {"id": 2, "nome": "Média", "ordem": 2, "cor": "#d97706", "ativo": True},
            {"id": 3, "nome": "Alta", "ordem": 3, "cor": "#ea580c", "ativo": True},
            {"id": 4, "nome": "Urgente", "ordem": 4, "cor": "#dc2626", "ativo": True},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM status")
    op.execute("DELETE FROM prioridade")