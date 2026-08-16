"""adicionar controle de notificacao sla

Revision ID: abde8296327f
Revises: c5a7a42601aa
Create Date: 2026-08-15 14:26:50.626152

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abde8296327f'
down_revision = 'c5a7a42601aa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chamado', sa.Column('sla_notificado_status', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('chamado', 'sla_notificado_status')
