"""add_knowledge_tables

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-06-25 00:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=500), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('department', sa.String(length=60), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('chunk_count', sa.Integer(), nullable=False),
        sa.Column('char_count', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('doc_id'),
    )
    op.create_index(op.f('ix_knowledge_documents_id'), 'knowledge_documents', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_doc_id'), 'knowledge_documents', ['doc_id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_user_id'), 'knowledge_documents', ['user_id'], unique=False)
    op.create_index(op.f('ix_knowledge_documents_department'), 'knowledge_documents', ['department'], unique=False)
    op.create_index('ix_knowledge_documents_user_uploaded', 'knowledge_documents', ['user_id', 'uploaded_at'], unique=False)

    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.String(length=120), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('token_estimate', sa.Integer(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['doc_id'], ['knowledge_documents.doc_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_chunks_id'), 'knowledge_chunks', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_doc_id'), 'knowledge_chunks', ['doc_id'], unique=False)
    op.create_index(op.f('ix_knowledge_chunks_user_id'), 'knowledge_chunks', ['user_id'], unique=False)
    op.create_index('ix_knowledge_chunks_doc_index', 'knowledge_chunks', ['doc_id', 'chunk_index'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_knowledge_chunks_doc_index', table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_user_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_doc_id'), table_name='knowledge_chunks')
    op.drop_index(op.f('ix_knowledge_chunks_id'), table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')

    op.drop_index('ix_knowledge_documents_user_uploaded', table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_department'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_user_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_doc_id'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_id'), table_name='knowledge_documents')
    op.drop_table('knowledge_documents')
