"""adicionar status aguardando correios

Revision ID: 68b246244269
Revises: a8b5b4100e07
Create Date: 2026-09-02 13:26:47.667051

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '68b246244269'
down_revision = 'a8b5b4100e07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO status (id, nome, ordem, cor, finalizador, pausa_sla, ativo)
        VALUES (6, 'Aguardando Correios', 6, '#0ea5e9', false, true, true)
        ON CONFLICT (id) DO NOTHING
    """)
    # Mesma lição aprendida antes: sincronizar a sequência pra não colidir
    # quando o admin criar um status novo pelo painel no futuro.
    op.execute("SELECT setval('status_id_seq', COALESCE((SELECT MAX(id) FROM status), 1))")


def downgrade() -> None:
    op.execute("DELETE FROM status WHERE id = 6 AND NOT EXISTS (SELECT 1 FROM chamado WHERE status_id = 6)")