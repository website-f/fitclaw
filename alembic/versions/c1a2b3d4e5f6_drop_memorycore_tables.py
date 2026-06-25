"""drop_memorycore_tables

Revision ID: c1a2b3d4e5f6
Revises: bb999d88703e
Create Date: 2026-06-25 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'bb999d88703e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_memory_usage_user_tool', table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_user_id'), table_name='memory_usage')
    op.drop_index('ix_memory_usage_user_created', table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_tool'), table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_session_id'), table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_project_key'), table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_model'), table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_id'), table_name='memory_usage')
    op.drop_index(op.f('ix_memory_usage_created_at'), table_name='memory_usage')
    op.drop_table('memory_usage')

    op.drop_index('ix_memory_design_user_name', table_name='memory_design')
    op.drop_index(op.f('ix_memory_design_user_id'), table_name='memory_design')
    op.drop_index(op.f('ix_memory_design_project_key'), table_name='memory_design')
    op.drop_index(op.f('ix_memory_design_name'), table_name='memory_design')
    op.drop_index(op.f('ix_memory_design_id'), table_name='memory_design')
    op.drop_table('memory_design')


def downgrade() -> None:
    op.create_table(
        'memory_design',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('image_paths', sa.JSON(), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('project_key', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memory_design_id'), 'memory_design', ['id'], unique=False)
    op.create_index(op.f('ix_memory_design_name'), 'memory_design', ['name'], unique=False)
    op.create_index(op.f('ix_memory_design_project_key'), 'memory_design', ['project_key'], unique=False)
    op.create_index(op.f('ix_memory_design_user_id'), 'memory_design', ['user_id'], unique=False)
    op.create_index('ix_memory_design_user_name', 'memory_design', ['user_id', 'name'], unique=True)

    op.create_table(
        'memory_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('tool', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=120), nullable=False),
        sa.Column('session_id', sa.String(length=120), nullable=True),
        sa.Column('project_key', sa.String(length=120), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memory_usage_created_at'), 'memory_usage', ['created_at'], unique=False)
    op.create_index(op.f('ix_memory_usage_id'), 'memory_usage', ['id'], unique=False)
    op.create_index(op.f('ix_memory_usage_model'), 'memory_usage', ['model'], unique=False)
    op.create_index(op.f('ix_memory_usage_project_key'), 'memory_usage', ['project_key'], unique=False)
    op.create_index(op.f('ix_memory_usage_session_id'), 'memory_usage', ['session_id'], unique=False)
    op.create_index(op.f('ix_memory_usage_tool'), 'memory_usage', ['tool'], unique=False)
    op.create_index('ix_memory_usage_user_created', 'memory_usage', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_memory_usage_user_id'), 'memory_usage', ['user_id'], unique=False)
    op.create_index('ix_memory_usage_user_tool', 'memory_usage', ['user_id', 'tool'], unique=False)
