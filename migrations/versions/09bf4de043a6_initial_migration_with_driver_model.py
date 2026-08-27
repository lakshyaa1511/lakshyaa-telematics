"""Initial migration with driver model

Revision ID: 09bf4de043a6
Revises: 
Create Date: 2026-08-03 18:02:47.881440

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '09bf4de043a6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("device", schema=None) as batch_op:
        batch_op.add_column(sa.Column("driver_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_device_driver","driver",["driver_id"],["id"])
    # ### end Alembic commands ###

def downgrade():
    with op.batch_alter_table("device", schema=None) as batch_op:
        batch_op.drop_constraint("fk_device_driver",type_="foreignkey")
        batch_op.drop_column("driver_id")
    # ### end Alembic commands ###
