import hashlib
import hmac

from urllib.parse import parse_qsl

from app.core.config import settings


class TelegramAuth:

    @staticmethod
    def parse(init_data: str) -> dict[str, str]:
        return dict(parse_qsl(init_data, keep_blank_values=True))


    @staticmethod
    def build_data_check_string(data: dict[str, str]) -> str:
        items = []

        for key, value in sorted(data.items()):
            if key != "hash":
                items.append(f"{key}={value}")

        return "\n".join(items)


    @staticmethod
    def secret_key() -> bytes:
        return hmac.new(
            key=b"WebAppData",
            msg=settings.TELEGRAM_BOT_TOKEN.encode(),
            digestmod=hashlib.sha256,
        ).digest()


    @staticmethod
    def calculate_hash(data_check_string: str) -> str:
        return hmac.new(
            key=TelegramAuth.secret_key(),
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify(init_data: str) -> dict[str, str]:

        data = TelegramAuth.parse(init_data)

        if "hash" not in data:
            raise ValueError("Missing hash")

        check_string = TelegramAuth.build_data_check_string(data)

        calculated_hash = TelegramAuth.calculate_hash(check_string)

        if not hmac.compare_digest(
            calculated_hash,
            data["hash"],
        ):
            raise ValueError("Invalid Telegram data")

        return data