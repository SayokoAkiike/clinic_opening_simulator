"""add geography-cast spatial indexes for ST_DWithin performance

Revision ID: add_geog_idx
Revises: add_spatial_idx
Create Date: 2026-07-14

"""
from alembic import op

revision = "add_geog_idx"
down_revision = "add_spatial_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ST_DWithin(geom::geography, ...) はgeometry型のGiSTインデックスを使えないため、
    # geography型にキャストした式そのものに対するインデックスを別途作成する
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_population_mesh_geog "
        "ON population_mesh USING GIST ((geom::geography))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_medical_institutions_geog "
        "ON medical_institutions USING GIST ((geom::geography))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_population_mesh_geog")
    op.execute("DROP INDEX IF EXISTS idx_medical_institutions_geog")
