from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
from asyncio import sleep, create_task
import random
from decimal import Decimal

from app.game_manager import game_manager
from app.database import SessionLocal
from app.models.user import User
from app.models.transaction import Transaction
from app.core.security import decode_access_token

router = APIRouter(prefix="/bingo", tags=["Bingo"])

STAKE_AMOUNT = Decimal("10.00")

# --- Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

def check_bingo_win(playboard, marked_numbers):
    marked = set(marked_numbers)
    marked.add(0)  # FREE cell

    grid = [playboard[i:i+5] for i in range(0, 25, 5)]
    winning_cells = []

    for r in range(5):
        if all(grid[r][c] in marked for c in range(5)):
            winning_cells.extend([(r, c) for c in range(5)])

    for c in range(5):
        if all(grid[r][c] in marked for r in range(5)):
            winning_cells.extend([(r, c) for r in range(5)])

    if all(grid[i][i] in marked for i in range(5)):
        winning_cells.extend([(i, i) for i in range(5)])

    if all(grid[i][4 - i] in marked for i in range(5)):
        winning_cells.extend([(i, 4 - i) for i in range(5)])

    return list(set(winning_cells))

# --- Game state ---
game_state = {
    "reservation_active": True,
    "called_numbers": [],
    "users": {},  # ws_id -> user state
}

GAME_RESERVATION_TIME = 60
CALL_INTERVAL = 4
game_started = False

# --- Game loop ---
async def start_game():
    global game_state
    
    db = SessionLocal()
    
    while True:
        await manager.broadcast({"type": "new_round"})
        game_manager.next_game()

        game_state["reservation_active"] = True
        game_state["called_numbers"] = []
        game_state["users"] = {}

        for t in range(GAME_RESERVATION_TIME, 0, -1):
            await manager.broadcast({
                "type": "reservation",
                "reservation_active": True,
                "seconds_left": t,
                "reserved_numbers": [u["selected_number"] for u in game_state["users"].values()],
                "game_no": game_manager.get_game_number(),
                "players": len(game_state["users"]),
                "derash": float(len(game_state["users"]) * STAKE_AMOUNT),
            })
            await sleep(1)

        game_state["reservation_active"] = False
        await manager.broadcast({
            "type": "reservation_end",
            "game_no": game_manager.get_game_number(),
        })

        if not game_state["users"]:
            await manager.broadcast({
                "type": "no_players",
                "game_no": game_manager.get_game_number(),
            })
            await sleep(3)
            continue

        remaining_numbers = list(range(1, 76))
        random.shuffle(remaining_numbers)

        for number in remaining_numbers:
            game_state["called_numbers"].append(number)

            await manager.broadcast({
                "type": "number_called",
                "number": number,
                "called_numbers": game_state["called_numbers"],
                "game_no": game_manager.get_game_number(),
            })

            # ---------------- CHECK WINNERS ----------------
            winners = []
            for ws_id, user in game_state["users"].items():
                
                if not user.get("eligible", True):
                    continue

                if not user.get("connected", True):
                    continue
                
                if user.get("winner"):
                    continue

                winning_cells = check_bingo_win(
                    user["playboard"], user["marked_numbers"]
                )

                if winning_cells:
                    user["winner"] = True
                    user["winning_cells"] = winning_cells
                    winners.append(ws_id)

            if winners:
                winner_id = winners[0]
                winner_user = game_state["users"][winner_id]

                # ---------------- PAYOUT LOGIC ----------------
                total_stake = Decimal("0.00")
                for u_ws_id, u in game_state["users"].items():
                    if u.get("staked"):
                        total_stake += STAKE_AMOUNT
                        if u_ws_id != winner_id:
                            # NO balance deduction here, already deducted on selection
                            db.add(Transaction(
                                user_id=u["user_id"],
                                type="withdraw",
                                amount=STAKE_AMOUNT,
                                reason="Bingo lost stake",
                            ))

                # Deposit total to winner
                db_winner = db.query(User).filter(User.id == winner_user["user_id"]).first()
                db_winner.balance += total_stake
                db.add(Transaction(
                    user_id=db_winner.id,
                    type="deposit",
                    amount=total_stake,
                    reason=f"Bingo win (collected {len(game_state['users'])} stakes)",
                ))
                db.commit()

                # Broadcast winner info
                await manager.broadcast({
                    "type": "winner",
                    "winner_id": winner_id,
                    "winning_number": winner_user["selected_number"],
                    "winning_cells": winner_user["winning_cells"],
                    "game_no": game_manager.get_game_number(),
                })
                break

            await sleep(CALL_INTERVAL)

        await sleep(5)

# --- WebSocket endpoint ---
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global game_started

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close()
        return

    payload = decode_access_token(token)
    user_id = payload.get("sub")

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close()
        return

    await manager.connect(websocket)
    ws_id = str(user.id) 
    # ws_id = str(id(websocket))

    try:
        user_state = game_state["users"].get(ws_id, {})
        await websocket.send_json({
            "type": "init",
            "reservation_active": game_state["reservation_active"],
            "seconds_left": GAME_RESERVATION_TIME if game_state["reservation_active"] else 0,
            "called_numbers": game_state["called_numbers"],
            "reserved_numbers": [u["selected_number"] for u in game_state["users"].values()],
            "user_id": ws_id,
            "selected_number": user_state.get("selected_number"),
            "playboard": user_state.get("playboard"),"players": len(game_state["users"]),
            "derash": float(len(game_state["users"]) * STAKE_AMOUNT),
        })

        if not game_started:
            game_started = True
            create_task(start_game())

        while True:
            data = await websocket.receive_json()

            if data["type"] == "select_number":
                if not game_state["reservation_active"]:
                    continue

                number = data["number"]
                user_state = game_state["users"].get(ws_id)

                # ---------------- DESELECT (same number) ----------------
                if user_state and user_state.get("selected_number") == number:
                    if user_state.get("staked"):
                        user.balance += STAKE_AMOUNT
                        db.add(Transaction(
                            user_id=user.id,
                            type="deposit",
                            amount=STAKE_AMOUNT,
                            reason="Bingo stake refund",
                        ))
                        db.commit()

                    del game_state["users"][ws_id]

                else:
                    reserved = [u["selected_number"] for u in game_state["users"].values()]
                    if number in reserved:
                        continue

                    # 🔹 CASE 1: User already selected another number → JUST CHANGE NUMBER
                    if user_state and user_state.get("staked"):
                        # regenerate playboard ONLY, no balance change
                        pass

                    # 🔹 CASE 2: First-time selection → CHARGE STAKE
                    else:
                        db.refresh(user)
                        if user.balance < STAKE_AMOUNT:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Insufficient balance",
                            })
                            continue

                        user.balance -= STAKE_AMOUNT
                        db.add(Transaction(
                            user_id=user.id,
                            type="withdraw",
                            amount=STAKE_AMOUNT,
                            reason="Bingo stake",
                        ))
                        db.commit()

                    # -------- Generate new playboard --------
                    def generate_bingo_playboard(selected_number: int):
                        columns = {
                            "B": list(range(1, 16)),
                            "I": list(range(16, 31)),
                            "N": list(range(31, 46)),
                            "G": list(range(46, 61)),
                            "O": list(range(61, 76)),
                        }

                        selected_col = None
                        for col, nums in columns.items():
                            if selected_number in nums:
                                selected_col = col
                                nums.remove(selected_number)
                                break

                        board_cols = {}
                        for col, nums in columns.items():
                            if col == selected_col:
                                board_cols[col] = [selected_number] + random.sample(nums, 4)
                            elif col == "N":
                                board_cols[col] = random.sample(nums, 4)
                            else:
                                board_cols[col] = random.sample(nums, 5)

                        board = []
                        for row in range(5):
                            for col in ["B", "I", "N", "G", "O"]:
                                if col == "N" and row == 2:
                                    board.append(0)
                                else:
                                    idx = row if not (col == "N" and row > 2) else row - 1
                                    board.append(board_cols[col][idx])
                        return board

                    playboard = generate_bingo_playboard(number)

                    game_state["users"][ws_id] = {
                        "user_id": user.id,
                        "selected_number": number,
                        "playboard": playboard,
                        "winner": False,
                        "staked": True,
                        "connected": True,
                        "eligible": True,
                        "marked_numbers": [],
                    }

                for ws in manager.active_connections:
                    uid = ws_id
                    us = game_state["users"].get(uid)
                    await ws.send_json({
                        "type": "number_reserved",
                        "reserved_numbers": [u["selected_number"] for u in game_state["users"].values()],
                        "user_id": uid,
                        "selected_number": us.get("selected_number") if us else None,
                        "playboard": us.get("playboard") if us else None,
                        "marked_numbers": us.get("marked_numbers") if us else [],
                        "players": len(game_state["users"]),
                        "derash": float(len(game_state["users"]) * STAKE_AMOUNT),
                    })

            elif data["type"] == "mark_number":
                if game_state["reservation_active"]:
                    continue

                num = data.get("number")
                user_state = game_state["users"].get(ws_id)

                if not user_state or not user_state.get("eligible", True):
                    continue

                last_called = game_state["called_numbers"][-1] if game_state["called_numbers"] else None

                # ❌ Clicking wrong number → DISQUALIFY
                if (
                    num != last_called
                    or num not in user_state["playboard"]
                    or num in user_state["marked_numbers"]
                ):
                    user_state["eligible"] = False
                    await websocket.send_json({
                        "type": "error",
                        "message": "❌ Wrong number! You are out of the game.",
                    })
                    continue

                # ✅ Valid mark
                user_state["marked_numbers"].append(num)

                await websocket.send_json({
                    "type": "marked_numbers",
                    "marked_numbers": user_state["marked_numbers"],
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        user_state = game_state["users"].get(ws_id)

        # BEFORE GAME START → REFUND + REMOVE
        if (
            user_state
            and game_state["reservation_active"]
            and user_state.get("staked")
        ):
            user.balance += STAKE_AMOUNT
            db.add(Transaction(
                user_id=user.id,
                type="deposit",
                amount=STAKE_AMOUNT,
                reason="Bingo stake refund (disconnect)",
            ))
            db.commit()

            del game_state["users"][ws_id]

        # AFTER GAME START → DISQUALIFY (NO REFUND)
        elif user_state:
            user_state["connected"] = True
            user_state["eligible"] = True   # 👈 CRITICAL LINE

        # Notify remaining players
        for ws in manager.active_connections:
            await ws.send_json({
                "type": "user_disconnected",
                "players": len(game_state["users"]),
                "derash": float(len(game_state["users"]) * STAKE_AMOUNT),
            })