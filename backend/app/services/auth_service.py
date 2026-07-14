from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
import secrets
import string

from app.models.sms_transaction import ReferralReward


class AuthService:

    def __init__(self, db: Session):
        self.db = db

    def generate_referral_code(
        self,
        length: int = 8,
    ):

        while True:

            code = "".join(
                secrets.choice(
                    string.ascii_uppercase + string.digits
                )
                for _ in range(length)
            )

            exists = (
                self.db.query(User)
                .filter(
                    User.referral_code == code
                )
                .first()
            )

            if not exists:
                return code


    def login_with_telegram(self, telegram_data: dict):

        telegram_user = json.loads(
            telegram_data["user"]
        )

        telegram_id = telegram_user["id"]

        user = (
            self.db.query(User)
            .filter(
                User.telegram_id == telegram_id
            )
            .first()
        )

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=telegram_user.get("username"),
                first_name=telegram_user.get("first_name", ""),
                last_name=telegram_user.get("last_name"),
                language_code=telegram_user.get("language_code"),
                photo_url=telegram_user.get("photo_url"),
                is_premium=telegram_user.get("is_premium", False),
            )

            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

        return user

    from datetime import datetime, timezone

    def register_telegram_user(
        self,
        telegram_user,
        referral_code=None,
    ) -> tuple[User, bool, list[str], User | None]:

        user = self.get_by_telegram_id(
            telegram_user.id
        )

        inviter = None

        if referral_code:

            inviter = (
                self.db.query(User)
                .filter(
                    User.referral_code == referral_code
                )
                .first()
            )

        if not user:

            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_premium=telegram_user.is_premium or False,

                # new user's own code
                referral_code=self.generate_referral_code(),

                # who invited this user
                referred_by_id=(
                    inviter.id
                    if inviter
                    else None
                ),
            )

            self.db.add(user)

            self.db.flush()


            # welcome bonus
            before = user.balance

            user.balance += Decimal("10.00")


            self.db.add(
                WalletTransaction(
                    user_id=user.id,
                    transaction_type="BONUS",
                    amount=Decimal("10.00"),
                    balance_before=before,
                    balance_after=user.balance,
                    reference_type="REGISTRATION",
                    reference_id=user.id,
                    description="Welcome bonus",
                )
            )



            # referral bonus

            if inviter and inviter.id != user.id:

                before = inviter.balance

                inviter.balance += Decimal("10.00")


                self.db.add(
                    WalletTransaction(
                        user_id=inviter.id,
                        transaction_type="REFERRAL",
                        amount=Decimal("10.00"),
                        balance_before=before,
                        balance_after=inviter.balance,
                        reference_type="REFERRAL",
                        reference_id=user.id,
                        description="Referral bonus",
                    )
                )


                self.db.add(
                    ReferralReward(
                        inviter_id=inviter.id,
                        invited_user_id=user.id,
                        amount=Decimal("10.00"),
                        status="COMPLETED",
                    )
                )


            self.db.commit()

            self.db.refresh(user)

            return user, True, [], inviter

        updated_fields = []

        if user.username != telegram_user.username:
            user.username = telegram_user.username
            updated_fields.append("Username")

        if user.first_name != telegram_user.first_name:
            user.first_name = telegram_user.first_name
            updated_fields.append("First Name")

        if user.last_name != telegram_user.last_name:
            user.last_name = telegram_user.last_name
            updated_fields.append("Last Name")

        if user.language_code != telegram_user.language_code:
            user.language_code = telegram_user.language_code
            updated_fields.append("Language")

        if user.is_premium != (telegram_user.is_premium or False):
            user.is_premium = telegram_user.is_premium or False
            updated_fields.append("Telegram Premium")

        user.last_seen_at = datetime.now(timezone.utc)

        if updated_fields:
            self.db.commit()
            self.db.refresh(user)

        return user, False, updated_fields, None

        # return user, True

        # return {
        #     "id": str(user.id),
        #     "first_name": user.first_name,
        #     "username": user.username,
        # }

    def get_by_telegram_id(
        self,
        telegram_id: int,
    ):
        return (
            self.db.query(User)
            .filter(
                User.telegram_id == telegram_id
            )
            .first()
        )