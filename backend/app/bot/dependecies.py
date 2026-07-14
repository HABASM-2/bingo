from app.db.database import SessionLocal


def get_bot_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()