"""Project-scoped local retrieval, with real pgvector on PostgreSQL."""
from alembic import op
import sqlalchemy as sa
from apps.api.db import VectorType
revision='004'
down_revision='003'

def upgrade():
    pg=op.get_bind().dialect.name=='postgresql'
    if pg:op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('context_chunks',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False),
        sa.Column('version',sa.String(64),nullable=False),sa.Column('encoder',sa.String(80),nullable=False),
        sa.Column('path',sa.String(200),nullable=False),sa.Column('start_line',sa.Integer(),nullable=False),
        sa.Column('end_line',sa.Integer(),nullable=False),sa.Column('content',sa.Text(),nullable=False),
        sa.Column('embedding',VectorType() if pg else sa.Text(),nullable=False))
    op.create_index('ix_context_chunks_project_id','context_chunks',['project_id'])
    op.create_index('ix_context_chunks_version','context_chunks',['version'])

def downgrade():
    op.drop_table('context_chunks')
    # The extension may be used by other tables. Never remove it on downgrade.
