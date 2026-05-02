from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account = Column(String(200), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active")
    balance_due = Column(Numeric(12, 2), nullable=False, default=0.00)
    can_be_paid = Column(Boolean, default=True, nullable=False)
    extra_fields = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    txn_id = Column(BigInteger, unique=True, nullable=False, index=True)
    prv_txn = Column(Integer, unique=True, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    command = Column(String(10), nullable=False)
    sum = Column(Numeric(12, 2), nullable=False)
    txn_date = Column(DateTime(timezone=False), nullable=False)
    txn_date_raw = Column(String(14), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    txn_id = Column(BigInteger, nullable=True)
    command = Column(String(10), nullable=True)
    account = Column(String(200), nullable=True)
    client_ip = Column(String(45), nullable=True)
    params = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    result = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
