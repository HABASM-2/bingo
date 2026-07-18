from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.current_user import get_current_user
from app.models.user import User

from app.api.dependencies import get_db
from app.schemas.auth import TelegramLoginRequest, TokenResponse
from app.core.telegram import TelegramAuth
from app.core.security import create_access_token
from app.services.auth_service import AuthService
from app.bot.links import build_invite_link


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


def _user_payload(user: User) -> dict:
    referral_code = user.referral_code or ""
    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "photo_url": user.photo_url,
        # Real Postgres balance for this user — the frontend uses this to
        # seed the wallet display immediately after login instead of
        # waiting on a second round-trip (and must never fall back to a
        # shared/hardcoded number in its place).
        "balance": str(user.balance),
        "referral_code": referral_code,
        "invite_link": build_invite_link(referral_code),
    }


@router.get("/me")
def me(
    user: User = Depends(get_current_user),
):
    return _user_payload(user)

@router.post("/telegram", response_model=TokenResponse)
def telegram_login(
    request: TelegramLoginRequest,
    db: Session = Depends(get_db),
):

    try:
        telegram_data = TelegramAuth.verify(
            request.init_data
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )


    user = AuthService(db).login_with_telegram(
        telegram_data
    )


    token = create_access_token(
        str(user.id)
    )


    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(user),
    }