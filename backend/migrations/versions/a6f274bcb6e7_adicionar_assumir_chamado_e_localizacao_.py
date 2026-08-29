"""adicionar assumir chamado e localizacao de fechamento

Revision ID: a6f274bcb6e7
Revises: 1b1204712876
Create Date: 2026-08-29 02:51:36.226999

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6f274bcb6e7'
down_revision = '1b1204712876'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chamado', sa.Column('fechado_latitude', sa.Float(), nullable=True))
    op.add_column('chamado', sa.Column('fechado_longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('chamado', 'fechado_longitude')
    op.drop_column('chamado', 'fechado_latitude')
