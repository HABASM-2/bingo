from app.database import SessionLocal
from app.models.user import User
from app.core.security import create_access_token

def register_or_get_telegram_user(data: dict):
    telegram_id = int(data["id"])
    username = data.get("username")
    first_name = data.get("first_name")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(
                telegram_id=telegram_id,
                telegram_username=username,
                telegram_first_name=first_name,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token({"sub": str(user.id)})
        return user, token
    finally:
        db.close()
