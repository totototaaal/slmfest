"""Allow nullable payment provider transaction before flush.

Revision ID: 0003_fix_sqlite_payments_prv_txn_nullable
Revises: 0002_add_quick_payment_orders
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_fix_sqlite_payments_prv_txn_nullable"
down_revision = "0002_add_quick_payment_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "payments" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("payments")}
    if columns.get("prv_txn", {}).get("nullable") is True:
        return

    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("prv_txn", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("prv_txn", existing_type=sa.Integer(), nullable=False)
