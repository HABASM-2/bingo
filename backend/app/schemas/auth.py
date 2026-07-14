from pydantic import BaseModel


class TelegramLoginRequest(BaseModel):
    init_data: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    user: dict