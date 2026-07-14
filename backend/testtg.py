from app.core.telegram import TelegramAuth


data = {
    "auth_date": "1710000000",
    "query_id": "ABC",
    "hash": "ignored",
    "user": '{"id":123}'
}


result = TelegramAuth.build_data_check_string(data)

print(result)