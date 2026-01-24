from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
from asyncio import sleep, create_task
import random
from decimal import Decimal

from app.game_manager import game_manager
from app.database import SessionLocal
from app.models.user import User
from app.models.transaction import Transaction
from app.core.security import decode_access_token

router = APIRouter(prefix="/bingo", tags=["Bingo"])

# =========================================================
# STAKE ROOMS
# =========================================================
STAKE_ROOMS: Dict[int, Decimal] = {
    10: Decimal("10.00"),
    20: Decimal("20.00"),
    50: Decimal("50.00"),
}

GAME_RESERVATION_TIME = 60
CALL_INTERVAL = 4

# =========================================================
# PER-STAKE GAME COUNTERS
# =========================================================
game_counters: Dict[int, int] = {stake: 1 for stake in STAKE_ROOMS}

# =========================================================
# GENERATE 75 FIXED PLAYBOARDS (ONCE AT SERVER START)
# =========================================================
def generate_fixed_board(seed: int):
    random.seed(seed)  # deterministic per number

    columns = {
        "B": random.sample(range(1, 16), 5),
        "I": random.sample(range(16, 31), 5),
        "N": random.sample(range(31, 46), 5),
        "G": random.sample(range(46, 61), 5),
        "O": random.sample(range(61, 76), 5),
    }

    board = []
    for r in range(5):
        for c, key in enumerate(["B", "I", "N", "G", "O"]):
            if r == 2 and c == 2:
                board.append(0)  # FREE center
            else:
                board.append(columns[key][r])
    return board


# 🔒 75 immutable playboards
PLAYBOARDS: Dict[int, list[int]] = {
    n: generate_fixed_board(n) for n in range(1, 76)
}

# =========================================================
# CONNECTION MANAGER
# =========================================================
class ConnectionManager:
    def __init__(self):
        self.connections: Dict[WebSocket, int] = {}  # ws -> stake

    async def connect(self, websocket: WebSocket, stake: int):
        await websocket.accept()
        self.connections[websocket] = stake

    def disconnect(self, websocket: WebSocket):
        self.connections.pop(websocket, None)

    async def broadcast(self, message: dict, stake: int):
        for ws, ws_stake in list(self.connections.items()):
            if ws_stake == stake:
                try:
                    await ws.send_json(message)
                except:
                    pass


manager = ConnectionManager()

# =========================================================
# GAME STATE
# =========================================================
def create_game_state():
    return {
        "reservation_active": True,
        "called_numbers": [],
        "users": {},  # ws_id -> user_state
        "started": False,
    }


games = {stake: create_game_state() for stake in STAKE_ROOMS}

# =========================================================
# BINGO WIN CHECK
# =========================================================
def check_bingo_win(playboard, marked_numbers):
    marked = set(marked_numbers)
    marked.add(0)  # FREE

    grid = [playboard[i:i + 5] for i in range(0, 25, 5)]
    wins = []

    for r in range(5):
        if all(grid[r][c] in marked for c in range(5)):
            wins.extend([(r, c) for c in range(5)])

    for c in range(5):
        if all(grid[r][c] in marked for r in range(5)):
            wins.extend([(r, c) for r in range(5)])

    if all(grid[i][i] in marked for i in range(5)):
        wins.extend([(i, i) for i in range(5)])

    if all(grid[i][4 - i] in marked for i in range(5)):
        wins.extend([(i, 4 - i) for i in range(5)])

    return list(set(wins))

# =========================================================
# GAME LOOP
# =========================================================
async def start_game(stake: int):
    game = games[stake]
    STAKE_AMOUNT = STAKE_ROOMS[stake]

    while True:
        # Increment per-stake game number
        current_game_no = game_counters[stake]
        game_counters[stake] += 1

        game["reservation_active"] = True
        game["called_numbers"] = []
        game["users"] = {}

        await manager.broadcast({
            "type": "new_round",
            "game_no": f"{current_game_no:06}",
        }, stake)

        # ---------- RESERVATION ----------
        for t in range(GAME_RESERVATION_TIME, 0, -1):
            await manager.broadcast({
                "type": "reservation",
                "reservation_active": True,
                "seconds_left": t,
                "reserved_numbers": [u["selected_number"] for u in game["users"].values()],
                "players": len(game["users"]),
                "derash": float(len(game["users"]) * STAKE_AMOUNT),
                "game_no": f"{current_game_no:06}",
            }, stake)
            await sleep(1)

        game["reservation_active"] = False
        await manager.broadcast({"type": "reservation_end"}, stake)

        if not game["users"]:
            await manager.broadcast({"type": "no_players"}, stake)
            await sleep(3)
            continue

        # ---------- NUMBER CALLING ----------
        numbers = list(range(1, 76))
        random.shuffle(numbers)

        for num in numbers:
            game["called_numbers"].append(num)

            await manager.broadcast({
                "type": "number_called",
                "number": num,
                "called_numbers": game["called_numbers"],
                "game_no": f"{current_game_no:06}",
            }, stake)

            winners = []
            for ws_id, user in game["users"].items():
                if not user["eligible"] or user["winner"]:
                    continue
                cells = check_bingo_win(user["playboard"], user["marked_numbers"])
                if cells:
                    user["winner"] = True
                    user["winning_cells"] = cells
                    winners.append(ws_id)

            if winners:
                db = SessionLocal()
                try: 
                    winner_id = winners[0]
                    winner = game["users"][winner_id]
                    total = STAKE_AMOUNT * len(game["users"])
                    db_user = db.query(User).filter(User.id == winner["user_id"]).first()
                    db_user.balance += total

                    db.add(Transaction(
                        user_id=db_user.id,
                        type="deposit",
                        amount=total,
                        stake_amount=STAKE_AMOUNT,
                        game_no=game_manager.get_game_number(),
                        reason="Bingo win",
                    ))
                    db.commit()
                finally:
                    db.close()

                await manager.broadcast({
                    "type": "winner",
                    "winner_id": winner_id,
                    "winning_number": winner["selected_number"],
                    "winning_cells": winner["winning_cells"],
                    "game_no": f"{current_game_no:06}",
                }, stake)
                break

            await sleep(CALL_INTERVAL)

        await sleep(5)

# =========================================================
# WEBSOCKET ENDPOINT
# =========================================================
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    stake = websocket.query_params.get("stake")

    if not token or not stake:
        await websocket.close()
        return

    stake = int(stake)
    if stake not in STAKE_ROOMS:
        await websocket.close()
        return

    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=1008)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=1008)
        return
    print("WS TOKEN:", token)
    print("WS PAYLOAD:", payload)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            await websocket.close()
            return
    finally:
        db.close()

    ws_id = str(user.id)
    game = games[stake]

    await manager.connect(websocket, stake)

    if not game.get("task"):
        game["task"] = create_task(start_game(stake))

    try:
        user_state = game["users"].get(ws_id)

        await websocket.send_json({
            "type": "init",
            "reservation_active": game["reservation_active"],
            "seconds_left": GAME_RESERVATION_TIME if game["reservation_active"] else 0,
            "called_numbers": game["called_numbers"],
            "reserved_numbers": [u["selected_number"] for u in game["users"].values()],
            "user_id": ws_id,
            "players": len(game["users"]),
            "derash": float(len(game["users"]) * STAKE_ROOMS[stake]),
            "selected_number": user_state["selected_number"] if user_state else None,
            "playboard": user_state["playboard"] if user_state else [],
            "marked_numbers": user_state["marked_numbers"] if user_state else [],
        })

        while True:
            data = await websocket.receive_json()

            # ---------- SELECT NUMBER ----------
            if data["type"] == "select_number":
                if not game["reservation_active"]:
                    continue

                number = data["number"]
                user_state = game["users"].get(ws_id)

                db = SessionLocal()
                try:
                    db_user = db.query(User).filter(User.id == user_id).with_for_update().first()
                    if not db_user:
                        continue

                    # ==========================================
                    # DESELECT (REFUND)
                    # ==========================================
                    if user_state and user_state["selected_number"] == number:
                        db_user.balance += STAKE_ROOMS[stake]

                        db.add(Transaction(
                            user_id=db_user.id,
                            type="deposit",
                            amount=STAKE_ROOMS[stake],
                            stake_amount=STAKE_ROOMS[stake],
                            reason="Bingo stake refund",
                        ))

                        del game["users"][ws_id]
                        db.commit()

                        await manager.broadcast({
                            "type": "number_reserved",
                            "reserved_numbers": [u["selected_number"] for u in game["users"].values()],
                            "players": len(game["users"]),
                            "derash": float(len(game["users"]) * STAKE_ROOMS[stake]),
                            "user_id": ws_id,
                            "selected_number": None,
                            "playboard": [],
                            "marked_numbers": [],
                        }, stake)
                        continue

                    # ==========================================
                    # ALREADY RESERVED BY OTHERS
                    # ==========================================
                    if number in [u["selected_number"] for u in game["users"].values()]:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Number already reserved",
                        })
                        continue

                    # ==========================================
                    # ALREADY STAKED (CHANGE NUMBER BLOCK)
                    # ==========================================
                    if user_state:
                        await websocket.send_json({
                            "type": "error",
                            "message": "You already reserved a number",
                        })
                        continue

                    # ==========================================
                    # CHECK BALANCE
                    # ==========================================
                    if db_user.balance < STAKE_ROOMS[stake]:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Insufficient balance",
                        })
                        continue

                    # ==========================================
                    # FIRST RESERVATION (WITHDRAW)
                    # ==========================================
                    db_user.balance -= STAKE_ROOMS[stake]

                    db.add(Transaction(
                        user_id=db_user.id,
                        type="withdraw",
                        amount=STAKE_ROOMS[stake],
                        stake_amount=STAKE_ROOMS[stake],
                        reason="Bingo stake",
                        withdraw_status="completed"
                    ))

                    game["users"][ws_id] = {
                        "user_id": db_user.id,
                        "selected_number": number,
                        "playboard": PLAYBOARDS[number],
                        "marked_numbers": [],
                        "eligible": True,
                        "winner": False,
                    }

                    db.commit()

                    await manager.broadcast({
                        "type": "number_reserved",
                        "reserved_numbers": [u["selected_number"] for u in game["users"].values()],
                        "players": len(game["users"]),
                        "derash": float(len(game["users"]) * STAKE_ROOMS[stake]),
                        "user_id": ws_id,
                        "selected_number": number,
                        "playboard": PLAYBOARDS[number],
                        "marked_numbers": [],
                    }, stake)

                finally:
                    db.close()

            # ---------- MARK NUMBER ----------
            elif data["type"] == "mark_number":
                if game["reservation_active"]:
                    continue

                state = game["users"].get(ws_id)
                if not state or not state["eligible"]:
                    continue

                num = data["number"]
                last = game["called_numbers"][-1]

                if num != last or num in state["marked_numbers"]:
                    state["eligible"] = False
                    await websocket.send_json({
                        "type": "error",
                        "message": "❌ Wrong number! You are out.",
                    })
                    continue

                state["marked_numbers"].append(num)
                await websocket.send_json({
                    "type": "marked_numbers",
                    "marked_numbers": state["marked_numbers"],
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
