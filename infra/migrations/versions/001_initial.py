"""Initial projects and document records."""
from alembic import op
import sqlalchemy as sa
revision = '001'
down_revision = None

def upgrade():
    op.create_table('projects', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(120), nullable=False), sa.Column('demo', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('records', sa.Column('id', sa.String(36), primary_key=True), sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False), sa.Column('kind', sa.String(32), nullable=False), sa.Column('data', sa.JSON(), nullable=False))
    op.create_index('ix_records_project_id', 'records', ['project_id'])
    op.create_index('ix_records_kind', 'records', ['kind'])

def downgrade():
    op.drop_table('records')
    op.drop_table('projects')
