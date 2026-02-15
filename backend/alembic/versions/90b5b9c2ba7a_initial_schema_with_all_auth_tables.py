"""initial schema with all auth tables

Revision ID: 90b5b9c2ba7a
Revises:
Create Date: 2026-02-16 04:56:55.447968

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90b5b9c2ba7a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = set(inspect(conn).get_table_names())

    # --- Create tables if they don't exist (fresh DB) ---
    if 'users' not in existing_tables:
        op.create_table(
            'users',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('email', sa.String(255), unique=True, index=True, nullable=False),
            sa.Column('hashed_password', sa.String(255), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
            sa.Column('is_admin', sa.Boolean(), server_default=sa.text('0'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('last_active', sa.DateTime(), nullable=True),
        )
    else:
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(sa.Column('last_active', sa.DateTime(), nullable=True))

    if 'conversations' not in existing_tables:
        op.create_table(
            'conversations',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('title', sa.String(500), nullable=False),
            sa.Column('is_starred', sa.Boolean(), server_default=sa.text('0'), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
    else:
        with op.batch_alter_table('conversations') as batch_op:
            batch_op.add_column(sa.Column('is_starred', sa.Boolean(), server_default=sa.text('0'), nullable=False))

    if 'messages' not in existing_tables:
        op.create_table(
            'messages',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('chunks_json', sa.Text(), nullable=True),
            sa.Column('feedback', sa.Boolean(), nullable=True),
            sa.Column('feedback_comment', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
        )
    else:
        with op.batch_alter_table('messages') as batch_op:
            batch_op.add_column(sa.Column('feedback', sa.Boolean(), nullable=True))
            batch_op.add_column(sa.Column('feedback_comment', sa.Text(), nullable=True))

    # Drop the old standalone feedback table (feedback now lives on messages)
    if 'feedback' in existing_tables:
        op.drop_table('feedback')


def downgrade() -> None:
    with op.batch_alter_table('messages') as batch_op:
        batch_op.drop_column('feedback_comment')
        batch_op.drop_column('feedback')

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_column('is_starred')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('last_active')

    op.create_table('feedback',
        sa.Column('id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('user_id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('conversation_id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('message_id', sa.VARCHAR(length=36), nullable=False),
        sa.Column('rating', sa.VARCHAR(length=10), nullable=False),
        sa.Column('comment', sa.TEXT(), nullable=True),
        sa.Column('created_at', sa.DATETIME(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
