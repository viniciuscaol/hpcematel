"""adicionar exclusao logica do chamado

Revision ID: 2a76f2a9348e
Revises: db9ebf70ea70
Create Date: 2026-08-12 22:20:00.458847

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a76f2a9348e'
down_revision = 'db9ebf70ea70'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chamado", sa.Column("excluido", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("chamado", sa.Column("excluido_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chamado", sa.Column("excluido_por_codigo", sa.Integer, nullable=True))
    op.add_column("chamado", sa.Column("excluido_por_nome_snapshot", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("chamado", "excluido_por_nome_snapshot")
    op.drop_column("chamado", "excluido_por_codigo")
    op.drop_column("chamado", "excluido_em")
    op.drop_column("chamado", "excluido")
