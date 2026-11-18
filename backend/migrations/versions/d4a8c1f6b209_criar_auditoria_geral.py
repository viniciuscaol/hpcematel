"""criar trilha central de auditoria

Revision ID: d4a8c1f6b209
Revises: a7c4e8f2190b
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a8c1f6b209"
down_revision = "a7c4e8f2190b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auditoria_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_codigo", sa.Integer(), nullable=True),
        sa.Column("usuario_login", sa.String(length=100), nullable=True),
        sa.Column("usuario_nome", sa.String(length=255), nullable=True),
        sa.Column("tipo_evento", sa.String(length=20), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("acao", sa.String(length=120), nullable=False),
        sa.Column("resultado", sa.String(length=20), nullable=False),
        sa.Column("metodo_http", sa.String(length=10), nullable=True),
        sa.Column("caminho", sa.String(length=500), nullable=True),
        sa.Column("entidade", sa.String(length=80), nullable=True),
        sa.Column("entidade_id", sa.String(length=80), nullable=True),
        sa.Column("status_http", sa.Integer(), nullable=True),
        sa.Column("ip_origem", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("detalhes", sa.Text(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_auditoria_log_usuario_codigo", "auditoria_log", ["usuario_codigo"])
    op.create_index("ix_auditoria_log_usuario_login", "auditoria_log", ["usuario_login"])
    op.create_index("ix_auditoria_log_criado_em", "auditoria_log", ["criado_em"])
    op.create_index(
        "ix_auditoria_log_categoria_criado_em",
        "auditoria_log",
        ["categoria", "criado_em"],
    )
    op.create_index(
        "ix_auditoria_log_tipo_criado_em",
        "auditoria_log",
        ["tipo_evento", "criado_em"],
    )
    op.create_index(
        "ix_auditoria_log_resultado_criado_em",
        "auditoria_log",
        ["resultado", "criado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_log_resultado_criado_em", table_name="auditoria_log")
    op.drop_index("ix_auditoria_log_tipo_criado_em", table_name="auditoria_log")
    op.drop_index("ix_auditoria_log_categoria_criado_em", table_name="auditoria_log")
    op.drop_index("ix_auditoria_log_criado_em", table_name="auditoria_log")
    op.drop_index("ix_auditoria_log_usuario_login", table_name="auditoria_log")
    op.drop_index("ix_auditoria_log_usuario_codigo", table_name="auditoria_log")
    op.drop_table("auditoria_log")
