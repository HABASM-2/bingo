from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from fastapi import Depends

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "connected",
    }