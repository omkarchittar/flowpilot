"""Persist revision-bound advisory review briefs and their redacted input context."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_review_brief"
down_revision = "a58da83f8591"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflows", sa.Column("review_brief", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("workflows", "review_brief")
