from fastapi import APIRouter, Request
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.deposit import IncomingDeposit
from decimal import Decimal
import json
import re

router = APIRouter(prefix="/sms", tags=["SMS"])


# =========================
# SAFE JSON PARSER
# =========================
def safe_json_load(body: bytes):
    """
    Handles cases where forwarder sends extra characters.
    Extracts first valid JSON object only.
    """
    text = body.decode("utf-8", errors="ignore").strip()

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == -1:
        return None

    try:
        return json.loads(text[start:end])
    except Exception:
        return None


# =========================
# SMS PARSER
# =========================
def parse_sms(text: str):
    text_lower = text.lower()

    # TELEBIRR
    if "telebirr" in text_lower:
        amount = re.search(r"ETB\s?([\d,]+\.\d{2})", text)
        txid = re.search(r"transaction number is (\w+)", text, re.I)
        if amount and txid:
            return {
                "provider": "telebirr",
                "amount": Decimal(amount.group(1).replace(",", "")),
                "txid": txid.group(1)
            }

    # CBE
    if "cbe" in text_lower or "banking with cbe" in text_lower:
        amount = re.search(r"ETB\s?([\d,]+\.\d{2})", text)
        txid = re.search(r"FT\w+", text)
        if amount and txid:
            return {
                "provider": "cbe",
                "amount": Decimal(amount.group(1).replace(",", "")),
                "txid": txid.group(0)
            }

    # ABYSSINIA
    if "abyssinia" in text_lower:
        amount = re.search(r"ETB\s?([\d,]+\.\d{2})", text)
        txid = re.search(r"trx=(\w+)", text)
        if amount and txid:
            return {
                "provider": "abyssinia",
                "amount": Decimal(amount.group(1).replace(",", "")),
                "txid": txid.group(1)
            }

    return None


# =========================
# WEBHOOK
# =========================
@router.post("/webhook")
async def sms_webhook(req: Request):
    body = await req.body()

    data = safe_json_load(body)
    if not data:
        return {"status": "invalid_json"}

    sms_text = data.get("text", "")
    if not sms_text:
        return {"status": "no_text"}

    parsed = parse_sms(sms_text)
    if not parsed:
        return {"status": "not_payment_sms"}

    db: Session = SessionLocal()
    try:
        # Avoid duplicate deposits
        exists = db.query(IncomingDeposit).filter_by(
            transaction_id=parsed["txid"]
        ).first()

        if exists:
            return {"status": "duplicate"}

        dep = IncomingDeposit(
            provider=parsed["provider"],
            amount=parsed["amount"],
            transaction_id=parsed["txid"],
            raw_text=sms_text
        )

        db.add(dep)
        db.commit()

        return {
            "status": "stored",
            "provider": parsed["provider"],
            "amount": float(parsed["amount"]),
            "txid": parsed["txid"]
        }

    finally:
        db.close()
