"""Initial schema — pr_reviews and pr_findings tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pr_reviews",
        sa.Column("id",           sa.Integer(),     nullable=False, autoincrement=True),
        sa.Column("owner",        sa.String(),      nullable=False),
        sa.Column("repo",         sa.String(),      nullable=False),
        sa.Column("pr_number",    sa.Integer(),     nullable=False),
        sa.Column("risk_level",   sa.String(),      nullable=False),
        sa.Column("risk_score",   sa.Integer(),     nullable=False),
        sa.Column("comment_url",  sa.String(),      nullable=True),
        sa.Column("agent_results", sa.JSON(),       nullable=True),
        sa.Column("created_at",   sa.DateTime(),    nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pr_reviews_repo_pr", "pr_reviews", ["owner", "repo", "pr_number"])

    op.create_table(
        "pr_findings",
        sa.Column("id",          sa.Integer(),  nullable=False, autoincrement=True),
        sa.Column("review_id",   sa.Integer(),  nullable=False),
        sa.Column("agent",       sa.String(),   nullable=False),
        sa.Column("file",        sa.String(),   nullable=False),
        sa.Column("line",        sa.Integer(),  nullable=False),
        sa.Column("issue_type",  sa.String(),   nullable=False),
        sa.Column("severity",    sa.String(),   nullable=False),
        sa.Column("message",     sa.String(),   nullable=False),
        sa.Column("suggestion",  sa.String(),   nullable=True),
        sa.Column("created_at",  sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["pr_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pr_findings_review", "pr_findings", ["review_id"])
    op.create_index("ix_pr_findings_severity", "pr_findings", ["severity"])


def downgrade() -> None:
    op.drop_table("pr_findings")
    op.drop_table("pr_reviews")
