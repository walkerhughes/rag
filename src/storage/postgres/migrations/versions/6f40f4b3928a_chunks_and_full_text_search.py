"""chunks and full text search

Revision ID: 6f40f4b3928a
Revises: 75de4db74d29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6f40f4b3928a"
down_revision: str | None = "75de4db74d29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("episode_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("first_position", sa.Integer(), nullable=False),
        sa.Column("last_position", sa.Integer(), nullable=False),
        sa.Column("speakers", postgresql.ARRAY(sa.String(length=200)), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start", sa.Interval(), nullable=True),
        sa.Column("chunker_version", sa.String(length=16), nullable=False),
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint("first_position <= last_position", name="chunk_positions_ordered"),
        sa.CheckConstraint("first_position >= 0", name="chunk_first_position_non_negative"),
        sa.ForeignKeyConstraint(["episode_id"], ["episode.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "ordinal", name="chunk_ordinal_unique"),
    )
    op.create_index(op.f("ix_chunk_episode_id"), "chunk", ["episode_id"], unique=False)
    op.create_index("ix_chunk_search", "chunk", ["search"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_chunk_speakers", "chunk", ["speakers"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_speakers", table_name="chunk", postgresql_using="gin")
    op.drop_index("ix_chunk_search", table_name="chunk", postgresql_using="gin")
    op.drop_index(op.f("ix_chunk_episode_id"), table_name="chunk")
    op.drop_table("chunk")
