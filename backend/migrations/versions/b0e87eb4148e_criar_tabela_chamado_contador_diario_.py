"""criar tabela chamado_contador_diario que faltava

Revision ID: b0e87eb4148e
Revises: d280b941f6a9
Create Date: 2026-08-19 20:16:58.895204

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0e87eb4148e'
down_revision = 'd280b941f6a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chamado_contador_diario',
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('contador', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('data'),
    )


def downgrade() -> None:
    op.drop_table('chamado_contador_diario')
