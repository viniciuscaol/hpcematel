"""adicionar histórico e auditoria do monitoramento

Revision ID: c8d9e1a2b3f4
Revises: 1b1204712876
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d9e1a2b3f4"
down_revision = "1b1204712876"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitoramento_amostra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coletado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cpu_percentual", sa.Float(), nullable=False),
        sa.Column("memoria_percentual", sa.Float(), nullable=False),
        sa.Column("detalhes_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_monitoramento_amostra_coletado_em", "monitoramento_amostra", ["coletado_em"])
    op.create_table(
        "monitoramento_acao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_codigo", sa.Integer(), nullable=False),
        sa.Column("usuario_login", sa.String(100), nullable=False),
        sa.Column("usuario_nome", sa.String(255), nullable=False),
        sa.Column("acionado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resultado", sa.String(30), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=True),
    )
    op.create_index("ix_monitoramento_acao_usuario_codigo", "monitoramento_acao", ["usuario_codigo"])
    op.create_index("ix_monitoramento_acao_acionado_em", "monitoramento_acao", ["acionado_em"])


def downgrade() -> None:
    op.drop_table("monitoramento_acao")
    op.drop_table("monitoramento_amostra")
