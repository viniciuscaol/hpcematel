"""unir histórico de monitoramento e fila de notificações

Revision ID: e9f3c2a7b611
Revises: f2d4a6b8c901, c8d9e1a2b3f4
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e9f3c2a7b611"
down_revision: Union[str, Sequence[str], None] = ("f2d4a6b8c901", "c8d9e1a2b3f4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Migração de junção: as alterações já foram aplicadas nas revisões ancestrais.
    pass


def downgrade() -> None:
    # Não desfaz as revisões ancestrais; apenas separa novamente o grafo.
    pass
