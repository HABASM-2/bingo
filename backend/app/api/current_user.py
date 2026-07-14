from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import (
    security_scheme,
    decode_access_token,
)
from app.models.user import User


def get_current_user(
    credentials=Depends(security_scheme),
    db: Session = Depends(get_db),
):

    payload = decode_access_token(
        credentials.credentials
    )

    user_id = UUID(payload["sub"])

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        raise Exception("User not found")

    return user