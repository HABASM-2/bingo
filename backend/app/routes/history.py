from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.transaction import Transaction
from app.models.user import User
from app.core.security import decode_access_token
from fastapi import Request

router = APIRouter(prefix="/bingo", tags=["Bingo"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/history")
async def bingo_history(request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("Authorization")
    if not token:
        return {"error": "Missing token"}

    token = token.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        return {"error": "Invalid token"}

    user_id = payload.get("sub")
    if not user_id:
        return {"error": "Invalid user"}

    # --- Leaderboard: last 5 winners ---
    leaderboard = (
        db.query(Transaction)
        .filter(Transaction.type == "deposit", Transaction.reason.ilike("%Bingo win%"))
        .order_by(Transaction.created_at.desc())
        .limit(5)
        .all()
    )

    leaderboard_data = []
    for t in leaderboard:
        user = db.query(User).filter(User.id == t.user_id).first()
        leaderboard_data.append({
            "game_no": t.game_no,
            "winner": user.display_name if user else "Unknown",
            "amount": float(t.amount),         # amount won
            "stake_amount": float(t.stake_amount)  # new: stake used
        })

    # --- User bet history ---
    bets = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id, Transaction.reason == "Bingo stake")
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )
    bets_data = []
    for stake_tx in bets:
        win_tx = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                Transaction.game_no == stake_tx.game_no,
                Transaction.reason.ilike("%Bingo win%")
            )
            .first()
        )

        if win_tx:
            status = "won"
            result_amount = float(win_tx.amount)
        else:
            status = "lost"
            result_amount = 0

        bets_data.append({
            "game_no": stake_tx.game_no,
            "selected_number": None,
            "stake_amount": float(stake_tx.stake_amount),
            "result_amount": result_amount,
            "status": status,
            "created_at": stake_tx.created_at,
        })

    return {
        "leaderboard": leaderboard_data,
        "bets": bets_data
    }