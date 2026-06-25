"""add_audit_tables

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-25 01:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('actor', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('action', sa.String(length=80), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('related_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id'),
    )
    op.create_index(op.f('ix_audit_events_id'), 'audit_events', ['id'], unique=False)
    op.create_index(op.f('ix_audit_events_event_id'), 'audit_events', ['event_id'], unique=False)
    op.create_index(op.f('ix_audit_events_user_id'), 'audit_events', ['user_id'], unique=False)
    op.create_index('ix_audit_events_user_created', 'audit_events', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_audit_events_action', 'audit_events', ['action'], unique=False)

    op.create_table(
        'llm_usage_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usage_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('session_id', sa.String(length=120), nullable=True),
        sa.Column('tool', sa.String(length=40), nullable=False),
        sa.Column('provider', sa.String(length=60), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_cents', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usage_id'),
    )
    op.create_index(op.f('ix_llm_usage_events_id'), 'llm_usage_events', ['id'], unique=False)
    op.create_index(op.f('ix_llm_usage_events_usage_id'), 'llm_usage_events', ['usage_id'], unique=False)
    op.create_index(op.f('ix_llm_usage_events_user_id'), 'llm_usage_events', ['user_id'], unique=False)
    op.create_index(op.f('ix_llm_usage_events_session_id'), 'llm_usage_events', ['session_id'], unique=False)
    op.create_index('ix_llm_usage_user_created', 'llm_usage_events', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_llm_usage_user_model', 'llm_usage_events', ['user_id', 'model'], unique=False)

    op.create_table(
        'chat_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('session_id', sa.String(length=120), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.String(length=8), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('correction', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feedback_id'),
    )
    op.create_index(op.f('ix_chat_feedback_id'), 'chat_feedback', ['id'], unique=False)
    op.create_index(op.f('ix_chat_feedback_feedback_id'), 'chat_feedback', ['feedback_id'], unique=False)
    op.create_index(op.f('ix_chat_feedback_user_id'), 'chat_feedback', ['user_id'], unique=False)
    op.create_index(op.f('ix_chat_feedback_session_id'), 'chat_feedback', ['session_id'], unique=False)
    op.create_index(op.f('ix_chat_feedback_message_id'), 'chat_feedback', ['message_id'], unique=False)
    op.create_index('ix_chat_feedback_user_created', 'chat_feedback', ['user_id', 'created_at'], unique=False)

    op.create_table(
        'budget_caps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('scope_value', sa.String(length=120), nullable=True),
        sa.Column('period', sa.String(length=20), nullable=False),
        sa.Column('limit_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('threshold_pct', sa.Float(), nullable=False),
        sa.Column('last_alert_pct', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('budget_id'),
    )
    op.create_index(op.f('ix_budget_caps_id'), 'budget_caps', ['id'], unique=False)
    op.create_index(op.f('ix_budget_caps_budget_id'), 'budget_caps', ['budget_id'], unique=False)
    op.create_index(op.f('ix_budget_caps_user_id'), 'budget_caps', ['user_id'], unique=False)
    op.create_index('ix_budget_caps_user_active', 'budget_caps', ['user_id', 'active'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_budget_caps_user_active', table_name='budget_caps')
    op.drop_index(op.f('ix_budget_caps_user_id'), table_name='budget_caps')
    op.drop_index(op.f('ix_budget_caps_budget_id'), table_name='budget_caps')
    op.drop_index(op.f('ix_budget_caps_id'), table_name='budget_caps')
    op.drop_table('budget_caps')

    op.drop_index('ix_chat_feedback_user_created', table_name='chat_feedback')
    op.drop_index(op.f('ix_chat_feedback_message_id'), table_name='chat_feedback')
    op.drop_index(op.f('ix_chat_feedback_session_id'), table_name='chat_feedback')
    op.drop_index(op.f('ix_chat_feedback_user_id'), table_name='chat_feedback')
    op.drop_index(op.f('ix_chat_feedback_feedback_id'), table_name='chat_feedback')
    op.drop_index(op.f('ix_chat_feedback_id'), table_name='chat_feedback')
    op.drop_table('chat_feedback')

    op.drop_index('ix_llm_usage_user_model', table_name='llm_usage_events')
    op.drop_index('ix_llm_usage_user_created', table_name='llm_usage_events')
    op.drop_index(op.f('ix_llm_usage_events_session_id'), table_name='llm_usage_events')
    op.drop_index(op.f('ix_llm_usage_events_user_id'), table_name='llm_usage_events')
    op.drop_index(op.f('ix_llm_usage_events_usage_id'), table_name='llm_usage_events')
    op.drop_index(op.f('ix_llm_usage_events_id'), table_name='llm_usage_events')
    op.drop_table('llm_usage_events')

    op.drop_index('ix_audit_events_action', table_name='audit_events')
    op.drop_index('ix_audit_events_user_created', table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_user_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_event_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_id'), table_name='audit_events')
    op.drop_table('audit_events')
