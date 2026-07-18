from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    APP_VERSION: str

    HOST: str
    PORT: int

    DEBUG: bool

    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    DATABASE_URL: str

    # SQLAlchemy pool sizing (per process). Safe defaults for multi-worker.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""
    # Keep enabled by default. Only set false for emergency local debugging.
    TELEGRAM_BOT_ENABLED: bool = True
    # Optional HTTP(S)/SOCKS proxy when api.telegram.org is blocked.
    # Example: socks5://127.0.0.1:1080
    TELEGRAM_PROXY_URL: str = ""

    TELEGRAM_WEBAPP_URL: str = ""

    REDIS_URL: str = "redis://localhost:6379"

    # Comma-separated Telegram usernames allowed to use privileged endpoints.
    # Authorization always uses the username stored on the JWT-authenticated user.
    ADMIN_TELEGRAM_USERNAMES: str = "has365"

    BINGO_DRAW_INTERVAL_MIN: float = 3.0
    BINGO_DRAW_INTERVAL_MAX: float = 5.0
    BINGO_MAX_CARDS: int = 2
    BINGO_DEFAULT_ENTRY_FEE: str = "0"

    # Ethiopian Bingo lobby / stake rules.
    BINGO_BOARD_PRICE: str = "10"          # ETB per board (fixed stake)
    BINGO_MAX_BOARDS: int = 2              # boards a player may pick per round
    BINGO_BOARD_POOL_MAX: int = 400        # selectable cartela ids: 1..400
    BINGO_LOBBY_SECONDS: int = 40          # shared lobby countdown
    BINGO_WINNER_OVERLAY_SECONDS: int = 7  # hold beat + winner splash before next lobby

    # Per-user abuse throttles (fixed window). Limits are generous enough for
    # fast legitimate tapping but cap runaway clients / scripted floods.
    BINGO_RATE_SELECT_MAX: int = 15        # select/deselect ops ...
    BINGO_RATE_SELECT_WINDOW_MS: int = 3000  # ... per this window
    BINGO_RATE_CLAIM_MAX: int = 6          # manual BINGO claims ...
    BINGO_RATE_CLAIM_WINDOW_MS: int = 5000   # ... per this window

    # Bingo house bot — backend-driven autofill for the public lobby.
    BINGO_BOT_ENABLED: bool = True
    BINGO_BOT_USERNAME: str = "bright_bingo_bot"
    BINGO_BOT_DISPLAY_NAME: str = "Bright Bot"
    # Reserved sentinel telegram_id (negative so it never collides with real TG ids).
    BINGO_BOT_TELEGRAM_ID: int = -777000001
    BINGO_BOT_MIN_BOARDS: int = 15
    BINGO_BOT_MAX_BOARDS: int = 30
    # Release when distinct real players with ≥1 board exceed this value
    # (i.e. real_selectors > threshold ⇒ ≥21 when threshold=20).
    BINGO_BOT_REAL_PLAYER_THRESHOLD: int = 20
    BINGO_BOT_CLAIM_WINDOW_START_SEC: float = 1.0
    BINGO_BOT_CLAIM_WINDOW_END_SEC: float = 35.0
    # Auto-credit house funds when bot wallet falls below this (ETB).
    BINGO_BOT_MIN_BALANCE: str = "5000"
    BINGO_BOT_TOPUP_AMOUNT: str = "20000"
    BINGO_BOT_INITIAL_BALANCE: str = "20000"
    # Only auto-fill this room id (shared public lobby).
    BINGO_BOT_ROOM_ID: str = "default"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()