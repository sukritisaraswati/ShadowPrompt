"""hosted pages

Revision ID: 75540c02cbbd
Revises: 5a1f0c2d7e91
Create Date: 2026-10-02 20:32:15.889650
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "75540c02cbbd"
down_revision: str | None = "5a1f0c2d7e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hosted_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("link_key", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("payload_id", sa.String(length=128), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetch_count", sa.Integer(), nullable=False),
        sa.Column("first_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_user_agent", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_hosted_pages_campaign_id_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hosted_pages")),
        sa.UniqueConstraint("link_key", name=op.f("uq_hosted_pages_link_key")),
    )


def downgrade() -> None:
    op.drop_table("hosted_pages")
