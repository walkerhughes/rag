"""canonical corpus

Revision ID: 75de4db74d29
Revises: 23ca86075a4f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "75de4db74d29"
down_revision: str | None = "23ca86075a4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('running', 'succeeded', 'failed')", name="ingestion_run_status_valid"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "episode",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_table(
        "speaker",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "episode_speaker",
        sa.Column("episode_id", sa.UUID(), nullable=False),
        sa.Column("speaker_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episode.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id", "speaker_id"),
    )
    op.create_table(
        "transcript_segment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("episode_id", sa.UUID(), nullable=False),
        sa.Column("speaker_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start", sa.Interval(), nullable=True),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("position >= 0", name="transcript_segment_position_non_negative"),
        sa.ForeignKeyConstraint(["episode_id"], ["episode.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_run.id"],
        ),
        sa.ForeignKeyConstraint(
            ["speaker_id"],
            ["speaker.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "position", name="transcript_segment_position_unique"),
    )
    op.create_index(
        op.f("ix_transcript_segment_episode_id"), "transcript_segment", ["episode_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transcript_segment_episode_id"), table_name="transcript_segment")
    op.drop_table("transcript_segment")
    op.drop_table("episode_speaker")
    op.drop_table("speaker")
    op.drop_table("episode")
    op.drop_table("ingestion_run")
