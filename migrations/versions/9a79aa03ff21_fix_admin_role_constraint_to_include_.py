"""fix admin role constraint to include manager

Revision ID: 9a79aa03ff21
Revises: 05bff91a2f29
Create Date: 2025-10-26 01:47:33.449266
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '9a79aa03ff21'
down_revision = '05bff91a2f29'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_admins_role", "admins", type_="check")
    op.create_check_constraint(
        "ck_admins_role",
        "admins",
        "role IN ('admin','manager','clerk')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_admins_role", "admins", type_="check")
    op.create_check_constraint(
        "ck_admins_role",
        "admins",
        "role IN ('admin','clerk')",
    )
