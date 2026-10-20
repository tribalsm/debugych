"""Atomic persistent daily AI reservations shared by worker processes."""
from alembic import op
import sqlalchemy as sa
revision='003'
down_revision='002'

def upgrade():
    op.create_table('ai_budgets',sa.Column('id',sa.String(40),primary_key=True),
                    sa.Column('calls',sa.BigInteger(),nullable=False),sa.Column('tokens',sa.BigInteger(),nullable=False),sa.Column('cost_micro',sa.BigInteger(),nullable=False))

def downgrade():op.drop_table('ai_budgets')
