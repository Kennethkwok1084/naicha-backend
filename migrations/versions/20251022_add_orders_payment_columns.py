"""add orders payment columns

Revision ID: 20251022_add_orders_payment_columns
Revises: 
Create Date: 2025-10-22 16:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251022_0002'
down_revision = '20241008_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('payment_channel', sa.String(length=50), nullable=True))
    op.add_column('orders', sa.Column('payment_status', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('orders', 'payment_status')
    op.drop_column('orders', 'payment_channel')
