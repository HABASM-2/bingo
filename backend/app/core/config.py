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

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""

    TELEGRAM_WEBAPP_URL: str = ""

    REDIS_URL: str = "redis://localhost:6379"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()