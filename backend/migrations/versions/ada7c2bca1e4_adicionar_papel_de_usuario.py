"""adicionar papel de usuario

Revision ID: ada7c2bca1e4
Revises: b0e87eb4148e
Create Date: 2026-08-20 11:31:50.422215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ada7c2bca1e4'
down_revision = 'b0e87eb4148e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usuario_contato', sa.Column('papel', sa.String(length=20), nullable=False, server_default='CAC'))


def downgrade() -> None:
    op.drop_column('usuario_contato', 'papel')