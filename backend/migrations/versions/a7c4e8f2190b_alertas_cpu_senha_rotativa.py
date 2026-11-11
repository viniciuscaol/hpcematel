"""estado de alertas CPU, senha rotativa e notificações 24h

Revision ID: a7c4e8f2190b
Revises: e9f3c2a7b611
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c4e8f2190b"
down_revision = "e9f3c2a7b611"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notificacao_pendente",
        sa.Column("fora_horario", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "monitoramento_estado",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("senha_atual_cifrada", sa.Text(), nullable=False),
        sa.Column("faixa_cpu", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("monitoramento_estado")
    op.drop_column("notificacao_pendente", "fora_horario")
