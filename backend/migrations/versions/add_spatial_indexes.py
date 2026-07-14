"""add spatial indexes on geom columns

Revision ID: add_spatial_idx
Revises: 7c7327e5805f
Create Date: 2026-07-14

"""
from alembic import op

revision = "add_spatial_idx"
down_revision = "7c7327e5805f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_population_mesh_geom ON population_mesh USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_medical_institutions_geom ON medical_institutions USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_diagnosis_logs_geom ON diagnosis_logs USING GIST (geom)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_population_mesh_geom")
    op.execute("DROP INDEX IF EXISTS idx_medical_institutions_geom")
    op.execute("DROP INDEX IF EXISTS idx_diagnosis_logs_geom")
