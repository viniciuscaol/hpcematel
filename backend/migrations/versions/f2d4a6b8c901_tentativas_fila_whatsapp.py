"""tentativas e agendamento da fila de WhatsApp

Revision ID: f2d4a6b8c901
Revises: 59d3255fc3bf
"""
from alembic import op
import sqlalchemy as sa

revision = "f2d4a6b8c901"
down_revision = "59d3255fc3bf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notificacao_pendente", sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False))
    op.add_column("notificacao_pendente", sa.Column("ultima_tentativa_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notificacao_pendente", sa.Column("proxima_tentativa_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("notificacao_pendente", sa.Column("ultimo_erro", sa.String(120), nullable=True))
    op.create_index("ix_notificacao_pendente_proxima_tentativa_em", "notificacao_pendente", ["proxima_tentativa_em"])


def downgrade() -> None:
    op.drop_index("ix_notificacao_pendente_proxima_tentativa_em", table_name="notificacao_pendente")
    for coluna in ("ultimo_erro", "proxima_tentativa_em", "ultima_tentativa_em", "tentativas"):
        op.drop_column("notificacao_pendente", coluna)
