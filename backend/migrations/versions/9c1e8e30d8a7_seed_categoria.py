"""seed categoria

Revision ID: 9c1e8e30d8a7
Revises: d33f43f83a67
Create Date: 2026-08-11 19:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9c1e8e30d8a7'
down_revision = 'd33f43f83a67'
branch_labels = None
depends_on = None


categoria_table = sa.table(
    "categoria",
    sa.column("id", sa.Integer),
    sa.column("nome", sa.String),
    sa.column("ativo", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        categoria_table,
        [
            {"id": 1, "nome": "Suporte Técnico", "ativo": True},
            {"id": 2, "nome": "Equipamento", "ativo": True},
            {"id": 3, "nome": "Sistema / Acesso", "ativo": True},
            {"id": 4, "nome": "Outros", "ativo": True},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM categoria")
