"""Add crawl_states table for tracking monitoring progress.

Revision ID: a2f7c3d81e9b
Revises: 1b3848e38506
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a2f7c3d81e9b"
down_revision = "1b3848e38506"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False, unique=True),
        sa.Column("last_external_id", sa.String(255), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("crawl_states")
