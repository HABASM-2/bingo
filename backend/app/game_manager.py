class GameManager:
    def __init__(self):
        self.game_number = 1
        self.players = set()        # ws_ids
        self.derash = set()         # selected numbers

    # ---- Game Number ----
    def next_game(self):
        self.game_number += 1
        self.players.clear()
        self.derash.clear()

    def get_game_number(self) -> str:
        return str(self.game_number).zfill(6)

    # ---- Players ----
    def add_player(self, ws_id: str):
        self.players.add(ws_id)

    def remove_player(self, ws_id: str):
        self.players.discard(ws_id)

    def player_count(self) -> int:
        return len(self.players)

    # ---- Derash (reserved numbers) ----
    def reserve_number(self, number: int):
        self.derash.add(number)

    def unreserve_number(self, number: int):
        self.derash.discard(number)

    def derash_count(self) -> int:
        return len(self.derash)


# ✅ SINGLETON (shared across app)
game_manager = GameManager()
