"""
Database models using SQLModel (SQLAlchemy + Pydantic).
"""
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, JSON, Column
import sqlalchemy as sa


class PRReview(SQLModel, table=True):
    """Record of a completed PR review."""
    __tablename__ = "pr_reviews"

    id:         Optional[int] = Field(default=None, primary_key=True)
    owner:      str
    repo:       str
    pr_number:  int
    risk_level: str           # LOW / MEDIUM / HIGH
    risk_score: int
    comment_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Store raw agent results as JSON for debugging
    agent_results: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON)
    )


class PRFinding(SQLModel, table=True):
    """Individual finding from an agent."""
    __tablename__ = "pr_findings"

    id:          Optional[int] = Field(default=None, primary_key=True)
    review_id:   int           = Field(foreign_key="pr_reviews.id")
    agent:       str
    file:        str
    line:        int
    issue_type:  str
    severity:    str
    message:     str
    suggestion:  Optional[str] = None
    created_at:  datetime = Field(default_factory=datetime.utcnow)
