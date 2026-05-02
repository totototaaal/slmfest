"""Initial Kaspi provider schema.

Revision ID: 0001_initial_kaspi_schema
Revises:
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_kaspi_schema"
down_revision = None
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "accounts" not in table_names:
        op.create_table(
            "accounts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("account", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("balance_due", sa.Numeric(12, 2), nullable=False),
            sa.Column("can_be_paid", sa.Boolean(), nullable=False),
            sa.Column("extra_fields", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_accounts_account", "accounts", ["account"], unique=True)
    elif "extra_fields" not in _columns("accounts"):
        op.add_column("accounts", sa.Column("extra_fields", sa.JSON(), nullable=True))

    if "payments" not in table_names:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("txn_id", sa.BigInteger(), nullable=False),
            sa.Column("prv_txn", sa.Integer(), nullable=True),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("command", sa.String(length=10), nullable=False),
            sa.Column("sum", sa.Numeric(12, 2), nullable=False),
            sa.Column("txn_date", sa.DateTime(timezone=False), nullable=False),
            sa.Column("txn_date_raw", sa.String(length=14), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("prv_txn"),
        )
        op.create_index("ix_payments_txn_id", "payments", ["txn_id"], unique=True)
    else:
        payment_columns = _columns("payments")
        if "txn_date" not in payment_columns:
            op.add_column("payments", sa.Column("txn_date", sa.DateTime(timezone=False), nullable=True))
        if "txn_date_raw" not in payment_columns:
            op.add_column("payments", sa.Column("txn_date_raw", sa.String(length=14), nullable=True))
        if bind.dialect.name != "sqlite":
            op.alter_column("payments", "txn_id", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False)
            op.alter_column("payments", "prv_txn", existing_type=sa.Integer(), nullable=True)

    if "request_logs" not in table_names:
        op.create_table(
            "request_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("txn_id", sa.BigInteger(), nullable=True),
            sa.Column("command", sa.String(length=10), nullable=True),
            sa.Column("account", sa.String(length=200), nullable=True),
            sa.Column("client_ip", sa.String(length=45), nullable=True),
            sa.Column("params", sa.JSON(), nullable=True),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("result", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    elif bind.dialect.name != "sqlite":
        op.alter_column("request_logs", "txn_id", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)


def downgrade() -> None:
    op.drop_table("request_logs")
    op.drop_index("ix_payments_txn_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_accounts_account", table_name="accounts")
    op.drop_table("accounts")
