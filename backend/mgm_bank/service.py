from decimal import Decimal
from uuid import uuid4

from app import db
from app.models import User

from .models import MGMAccount, MGMBank, MGMCustomer

DEMO_BANK_CODE = "MGM-DEMO"
DEFAULT_CREDIT_LIMIT = Decimal("5000.00")


def ensure_demo_bank():
    bank = MGMBank.query.filter_by(code=DEMO_BANK_CODE).first()
    if bank is None:
        bank = MGMBank(
            code=DEMO_BANK_CODE,
            name="MGM Bank",
            environment="simulation",
        )
        db.session.add(bank)
        db.session.flush()
    return bank


def ensure_customer_account(
    user: User, *, customer_name: str | None = None, mobile: str | None = None
):
    customer = MGMCustomer.query.filter_by(app_user_id=user.id).first()
    if customer is not None:
        return customer

    bank = ensure_demo_bank()
    customer_key = uuid4().hex[:12].upper()
    customer = MGMCustomer(
        bank_id=bank.id,
        app_user_id=user.id,
        customer_id=f"MGM-C-{customer_key}",
        name=customer_name or f"Demo Customer {user.id}",
        email=user.email,
        mobile=mobile or "+91-90000-00000",
    )
    db.session.add(customer)
    db.session.flush()
    db.session.add(
        MGMAccount(
            customer_id=customer.id,
            account_number=f"MGM-{uuid4().hex[:12].upper()}",
            credit_limit=DEFAULT_CREDIT_LIMIT,
            used_limit=Decimal("0.00"),
        )
    )
    return customer


def ensure_accounts_for_existing_users():
    ensure_demo_bank()
    for user in User.query.order_by(User.id).all():
        ensure_customer_account(user)
    db.session.commit()
