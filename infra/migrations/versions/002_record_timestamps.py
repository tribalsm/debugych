"""Deterministic ordering for job and patch histories."""
from alembic import op
import sqlalchemy as sa
revision = '002'
down_revision = '001'

def upgrade():
    # Batch recreation also supports existing SQLite databases.
    with op.batch_alter_table('records') as batch:
        batch.add_column(sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))

def downgrade():
    with op.batch_alter_table('records') as batch:
        batch.drop_column('created_at')
