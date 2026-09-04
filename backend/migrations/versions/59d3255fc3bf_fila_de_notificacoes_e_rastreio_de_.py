"""fila de notificacoes e rastreio de cidades

Revision ID: 59d3255fc3bf
Revises: 68b246244269
Create Date: 2026-09-03 23:53:00.802675

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '59d3255fc3bf'
down_revision = '68b246244269'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notificacao_pendente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.String(length=50), nullable=False),
        sa.Column('mensagem', sa.Text(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('notificacao_pendente')
