"""adicionar rastreio de correios

Revision ID: a8b5b4100e07
Revises: a6f274bcb6e7
Create Date: 2026-08-31 13:34:11.069596

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8b5b4100e07'
down_revision = 'a6f274bcb6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chamado_rastreio',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chamado_id', sa.Integer(), sa.ForeignKey('chamado.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tipo', sa.String(length=10), nullable=False),  # "envio" ou "reverso"
        sa.Column('codigo_rastreio', sa.String(length=20), nullable=False),
        sa.Column('status_atual', sa.Text(), nullable=True),
        sa.Column('entregue', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ultima_verificacao_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chamado_rastreio_chamado_id', 'chamado_rastreio', ['chamado_id'])


def downgrade() -> None:
    op.drop_index('ix_chamado_rastreio_chamado_id', table_name='chamado_rastreio')
    op.drop_table('chamado_rastreio')