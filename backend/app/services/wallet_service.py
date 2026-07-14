from decimal import Decimal

from app.models.wallet_transaction import WalletTransaction


def credit_wallet(
    db,
    user,
    amount: Decimal,
    transaction_type: str,
    description: str,
    reference_type=None,
    reference_id=None,
):

    before = user.balance

    user.balance += amount

    after = user.balance

    transaction = WalletTransaction(
        user_id=user.id,
        transaction_type=transaction_type,
        amount=amount,
        balance_before=before,
        balance_after=after,
        status="COMPLETED",
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )

    db.add(transaction)

    return transaction