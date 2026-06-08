"""Add quick payment form order log.

Revision ID: 0004_add_quick_payment_form_orders
Revises: 0003_fix_sqlite_payments_prv_txn_nullable
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_quick_payment_form_orders"
down_revision = "0003_fix_sqlite_payments_prv_txn_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "quick_payment_orders" in inspector.get_table_names():
        return

    op.create_table(
        "quick_payment_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tran_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=16), nullable=False),
        sa.Column("amount_tenge", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_tiyin", sa.BigInteger(), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("return_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quick_payment_orders_order_id", "quick_payment_orders", ["order_id"], unique=False)
    op.create_index("ix_quick_payment_orders_tran_id", "quick_payment_orders", ["tran_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quick_payment_orders_tran_id", table_name="quick_payment_orders")
    op.drop_index("ix_quick_payment_orders_order_id", table_name="quick_payment_orders")
    op.drop_table("quick_payment_orders")
