"""adicionar numero chamado e sla

Revision ID: db9ebf70ea70
Revises: 9c1e8e30d8a7
Create Date: 2026-08-12 14:05:33.185693

"""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db9ebf70ea70'
down_revision = '9c1e8e30d8a7'
branch_labels = None
depends_on = None


FUSO_BAHIA = timezone(timedelta(hours=-3))


def _calcular_prazo(criado_em_utc: datetime) -> datetime:
    inicio_local = criado_em_utc.astimezone(FUSO_BAHIA)
    prazo_local = inicio_local + timedelta(hours=24)
    while prazo_local.weekday() in (5, 6):
        prazo_local += timedelta(days=1)
    return prazo_local.astimezone(timezone.utc)


def upgrade() -> None:
    # 1. Tabela de contador diário (garante numeração sequencial sem colisão)
    op.create_table(
        "chamado_contador_diario",
        sa.Column("data", sa.Date, primary_key=True),
        sa.Column("contador", sa.Integer, nullable=False, server_default="0"),
    )

    # 2. Novas colunas no chamado (nullable por enquanto, para poder popular os existentes)
    op.add_column("chamado", sa.Column("numero_chamado", sa.String(10), nullable=True))
    op.add_column("chamado", sa.Column("prazo_sla", sa.DateTime(timezone=True), nullable=True))

    conn = op.get_bind()

    # 3. Backfill: numera os chamados já existentes, agrupando por dia local (Bahia)
    conn.execute(sa.text("""
        WITH ordenados AS (
            SELECT id,
                   (criado_em AT TIME ZONE 'America/Bahia')::date AS dia_local,
                   ROW_NUMBER() OVER (
                       PARTITION BY (criado_em AT TIME ZONE 'America/Bahia')::date
                       ORDER BY criado_em
                   ) AS seq
            FROM chamado
        )
        UPDATE chamado c
        SET numero_chamado = to_char(o.dia_local, 'DDMMYY') || lpad(o.seq::text, 4, '0')
        FROM ordenados o
        WHERE c.id = o.id
    """))

    # 4. Inicializa o contador diário com base no que já foi numerado
    conn.execute(sa.text("""
        INSERT INTO chamado_contador_diario (data, contador)
        SELECT (criado_em AT TIME ZONE 'America/Bahia')::date, COUNT(*)
        FROM chamado
        GROUP BY 1
    """))

    # 5. Backfill do prazo de SLA para os chamados existentes
    resultado = conn.execute(sa.text("SELECT id, criado_em FROM chamado"))
    for linha in resultado:
        prazo = _calcular_prazo(linha.criado_em.replace(tzinfo=timezone.utc))
        conn.execute(
            sa.text("UPDATE chamado SET prazo_sla = :prazo WHERE id = :id"),
            {"prazo": prazo, "id": linha.id},
        )

    # 6. Agora que tudo está preenchido, torna as colunas obrigatórias e únicas
    op.alter_column("chamado", "numero_chamado", nullable=False)
    op.alter_column("chamado", "prazo_sla", nullable=False)
    op.create_unique_constraint("uq_chamado_numero_chamado", "chamado", ["numero_chamado"])


def downgrade() -> None:
    op.drop_constraint("uq_chamado_numero_chamado", "chamado", type_="unique")
    op.drop_column("chamado", "prazo_sla")
    op.drop_column("chamado", "numero_chamado")
    op.drop_table("chamado_contador_diario")