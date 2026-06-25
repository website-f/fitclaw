"""add_governance_tables

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-25 01:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('department', sa.String(length=60), nullable=True),
        sa.Column('allowed_departments', sa.JSON(), nullable=False),
        sa.Column('can_resolve_handoffs', sa.Integer(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index(op.f('ix_user_roles_id'), 'user_roles', ['id'], unique=False)
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_roles_department'), 'user_roles', ['department'], unique=False)

    op.create_table(
        'handoff_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('handoff_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('session_id', sa.String(length=120), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=40), nullable=False),
        sa.Column('department', sa.String(length=60), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('context_excerpt', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assignee', sa.String(length=120), nullable=True),
        sa.Column('reply', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('handoff_id'),
    )
    op.create_index(op.f('ix_handoff_requests_id'), 'handoff_requests', ['id'], unique=False)
    op.create_index(op.f('ix_handoff_requests_handoff_id'), 'handoff_requests', ['handoff_id'], unique=False)
    op.create_index(op.f('ix_handoff_requests_user_id'), 'handoff_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_handoff_requests_session_id'), 'handoff_requests', ['session_id'], unique=False)
    op.create_index(op.f('ix_handoff_requests_message_id'), 'handoff_requests', ['message_id'], unique=False)
    op.create_index(op.f('ix_handoff_requests_department'), 'handoff_requests', ['department'], unique=False)
    op.create_index(op.f('ix_handoff_requests_status'), 'handoff_requests', ['status'], unique=False)
    op.create_index(op.f('ix_handoff_requests_assignee'), 'handoff_requests', ['assignee'], unique=False)
    op.create_index('ix_handoff_requests_user_status', 'handoff_requests', ['user_id', 'status'], unique=False)
    op.create_index('ix_handoff_requests_status_created', 'handoff_requests', ['status', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_handoff_requests_status_created', table_name='handoff_requests')
    op.drop_index('ix_handoff_requests_user_status', table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_assignee'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_status'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_department'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_message_id'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_session_id'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_user_id'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_handoff_id'), table_name='handoff_requests')
    op.drop_index(op.f('ix_handoff_requests_id'), table_name='handoff_requests')
    op.drop_table('handoff_requests')

    op.drop_index(op.f('ix_user_roles_department'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_user_id'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_id'), table_name='user_roles')
    op.drop_table('user_roles')
