import hashlib
import hmac
from urllib.parse import parse_qsl

BOT_TOKEN = "8045248665:AAFPsHgXWQAmqx-NskW4rULWUQu1qRVq_SQ"

def verify_telegram(init_data: str):
    # Convert query string to dict
    data_dict = dict(parse_qsl(init_data, strict_parsing=True))

    # Telegram sends a hash to verify integrity
    hash_from_telegram = data_dict.pop("hash")

    # Sort keys and build data check string
    data_check_string = "\n".join(
        [f"{k}={v}" for k, v in sorted(data_dict.items())]
    )

    # Create secret key from bot token
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()

    # Generate HMAC SHA256 hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare hashes safely
    is_valid = hmac.compare_digest(calculated_hash, hash_from_telegram)

    return is_valid, data_dict
