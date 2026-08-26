"""corrigir finalizador de resolvido e cancelado

Revision ID: 1b1204712876
Revises: ff5f1f7a4142
Create Date: 2026-08-26 03:40:15.105571

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b1204712876'
down_revision = 'ff5f1f7a4142'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Marca Resolvido (4) e Cancelado (5) como status finalizadores —
    # esse ajuste tinha sido feito só via comando manual antes da migração
    # para o cluster, e se perdeu quando o banco foi recriado do zero.
    op.execute("UPDATE status SET finalizador = true WHERE id IN (4, 5)")

    # Confere também os valores de SLA por prioridade, pelo mesmo motivo
    # (também era um ajuste manual, agora vira parte da migração).
    op.execute("""
        UPDATE prioridade SET sla_horas = CASE id
            WHEN 1 THEN 48
            WHEN 2 THEN 24
            WHEN 3 THEN 8
            WHEN 4 THEN 4
            ELSE sla_horas
        END
    """)


def downgrade() -> None:
    op.execute("UPDATE status SET finalizador = false WHERE id IN (4, 5)")
