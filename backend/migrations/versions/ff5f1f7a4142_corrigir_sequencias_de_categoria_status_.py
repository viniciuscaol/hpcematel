"""corrigir sequencias de categoria status prioridade

Revision ID: ff5f1f7a4142
Revises: edfc3c516614
Create Date: 2026-08-24 12:30:07.713102

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ff5f1f7a4142'
down_revision = 'edfc3c516614'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT setval('categoria_id_seq', COALESCE((SELECT MAX(id) FROM categoria), 1))")
    op.execute("SELECT setval('status_id_seq', COALESCE((SELECT MAX(id) FROM status), 1))")
    op.execute("SELECT setval('prioridade_id_seq', COALESCE((SELECT MAX(id) FROM prioridade), 1))")


def downgrade() -> None:
    pass  # ajuste de sequência não precisa de reversão