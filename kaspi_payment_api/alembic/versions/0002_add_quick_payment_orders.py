"""Add quick payment orders.

Revision ID: 0002_add_quick_payment_orders
Revises: 0001_initial_kaspi_schema
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_quick_payment_orders"
down_revision = "0001_initial_kaspi_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "orders" in table_names:
        return

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tran_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("redirect_url", sa.Text(), nullable=True),
        sa.Column("qr_code_image", sa.Text(), nullable=True),
        sa.Column("return_url", sa.Text(), nullable=True),
        sa.Column("referer_host", sa.String(length=1024), nullable=True),
        sa.Column("kaspi_code", sa.Integer(), nullable=True),
        sa.Column("kaspi_message", sa.Text(), nullable=True),
        sa.Column("kaspi_response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_order_id", "orders", ["order_id"], unique=True)
    op.create_index("ix_orders_tran_id", "orders", ["tran_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_orders_tran_id", table_name="orders")
    op.drop_index("ix_orders_order_id", table_name="orders")
    op.drop_table("orders")
