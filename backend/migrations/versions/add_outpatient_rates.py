"""add outpatient_rates table

Revision ID: add_outpatient_rates
Revises: add_geog_idx
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa

revision = "add_outpatient_rates"
down_revision = "add_geog_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outpatient_rates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("department", sa.String, nullable=False, index=True),
        sa.Column("age_bracket", sa.String, nullable=False),
        sa.Column("gender", sa.String, nullable=False),
        sa.Column("rate_per_100k", sa.Numeric, nullable=False),
        sa.Column("source_year", sa.Integer, nullable=False),
    )
    op.create_index(
        "idx_outpatient_rates_dept_age_gender",
        "outpatient_rates",
        ["department", "age_bracket", "gender"],
    )


def downgrade() -> None:
    op.drop_index("idx_outpatient_rates_dept_age_gender", table_name="outpatient_rates")
    op.drop_table("outpatient_rates")
