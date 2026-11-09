from decimal import Decimal

from app import db
from app.models import utcnow


class MGMCustomer(db.Model):
    __tablename__ = "mgm_bank_customers"

    id = db.Column(db.Integer, primary_key=True)
    bank_id = db.Column(db.Integer, db.ForeignKey("mgm_banks.id"), nullable=False)
    app_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True
    )
    customer_id = db.Column(db.String(40), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    mobile = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    account = db.relationship("MGMAccount", back_populates="customer", uselist=False)
    bank_record = db.relationship("MGMBank")
    app_user = db.relationship("User")


class MGMAccount(db.Model):
    __tablename__ = "mgm_bank_accounts"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("mgm_bank_customers.id"), nullable=False, unique=True
    )
    account_number = db.Column(db.String(32), nullable=False, unique=True, index=True)
    credit_limit = db.Column(db.Numeric(12, 2), nullable=False)
    used_limit = db.Column(
        db.Numeric(12, 2), nullable=False, default=lambda: Decimal("0.00")
    )
    status = db.Column(db.String(16), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    customer = db.relationship("MGMCustomer", back_populates="account")


class MGMBank(db.Model):
    __tablename__ = "mgm_banks"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    environment = db.Column(db.String(24), nullable=False, default="simulation")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class MGMBankTransaction(db.Model):
    __tablename__ = "mgm_bank_transactions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(
        db.Integer, db.ForeignKey("mgm_bank_accounts.id"), nullable=False, index=True
    )
    fraud_transaction_id = db.Column(
        db.Integer, db.ForeignKey("transaction.id"), nullable=False, unique=True
    )
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(24), nullable=False, index=True)
    balance_before = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    account = db.relationship("MGMAccount")
    fraud_transaction = db.relationship("Transaction")


class MGMLedgerEntry(db.Model):
    __tablename__ = "mgm_bank_ledger"

    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("mgm_bank_transactions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    entry_type = db.Column(db.String(24), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    used_limit_before = db.Column(db.Numeric(12, 2), nullable=False)
    used_limit_after = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    bank_transaction = db.relationship("MGMBankTransaction")


class MGMNotificationPreview(db.Model):
    __tablename__ = "mgm_bank_notification_previews"

    id = db.Column(db.Integer, primary_key=True)
    bank_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey("mgm_bank_transactions.id"),
        nullable=False,
        index=True,
    )
    channel = db.Column(db.String(16), nullable=False)
    recipient = db.Column(db.String(254), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="preview_only")
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    bank_transaction = db.relationship("MGMBankTransaction")
