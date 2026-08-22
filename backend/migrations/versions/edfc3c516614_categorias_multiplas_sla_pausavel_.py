"""categorias multiplas, sla pausavel, descricao opcional

Revision ID: edfc3c516614
Revises: ada7c2bca1e4
Create Date: 2026-08-22 11:22:39.602633

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'edfc3c516614'
down_revision = 'ada7c2bca1e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Categorias múltiplas ---
    op.create_table(
        'chamado_categoria',
        sa.Column('chamado_id', sa.Integer(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['chamado_id'], ['chamado.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['categoria_id'], ['categoria.id']),
        sa.PrimaryKeyConstraint('chamado_id', 'categoria_id'),
    )
    op.execute("""
        INSERT INTO chamado_categoria (chamado_id, categoria_id)
        SELECT id, categoria_id FROM chamado WHERE categoria_id IS NOT NULL
    """)
    op.drop_column('chamado', 'categoria_id')

    # --- Descrição não obrigatória ---
    op.alter_column('chamado', 'descricao', existing_type=sa.Text(), nullable=True)

    # --- SLA pausável (status "Aguardando cliente") ---
    op.add_column('status', sa.Column('pausa_sla', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('chamado', sa.Column('sla_pausado_em', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE status SET pausa_sla = true WHERE id = 3")  # Aguardando cliente

    # --- Renomear Encerrado -> Cancelado (evita 2 status parecendo "concluído") ---
    op.execute("UPDATE status SET nome = 'Cancelado' WHERE id = 5")


def downgrade() -> None:
    op.execute("UPDATE status SET nome = 'Encerrado' WHERE id = 5")
    op.drop_column('chamado', 'sla_pausado_em')
    op.drop_column('status', 'pausa_sla')
    op.alter_column('chamado', 'descricao', existing_type=sa.Text(), nullable=False)
    op.add_column('chamado', sa.Column('categoria_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE chamado c SET categoria_id = (
            SELECT categoria_id FROM chamado_categoria cc WHERE cc.chamado_id = c.id LIMIT 1
        )
    """)
    op.drop_table('chamado_categoria')
