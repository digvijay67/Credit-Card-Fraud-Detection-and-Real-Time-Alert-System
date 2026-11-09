from datetime import timedelta

from sqlalchemy import func

from app import db
from app.models import Transaction


def transaction_features(user_id, amount, occurred_at, distance):
    recent_transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.occurred_at >= occurred_at - timedelta(days=1),
        Transaction.occurred_at < occurred_at,
    )
    average_amount = db.session.query(func.avg(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.occurred_at >= occurred_at - timedelta(days=30),
        Transaction.occurred_at < occurred_at,
    ).scalar()
    return {
        "amount": amount,
        "transaction_hour": occurred_at.hour,
        "transactions_last_24h": recent_transactions.count(),
        "avg_amount_30d": float(average_amount or 0),
        "distance_from_last_km": distance,
    }
