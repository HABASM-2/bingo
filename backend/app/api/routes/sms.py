from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.sms_transaction import SMSTransaction
from app.services.sms_parser import SMSParser


router = APIRouter(
    prefix="/sms",
    tags=["SMS"]
)



class SMSPayload(BaseModel):

    from_: str

    text: str

    sentStamp: int

    receivedStamp: int

    sim: str



@router.post("/webhook")
async def receive_sms(
    sms: SMSPayload,
    db: Session = Depends(get_db),
):


    # Parse any supported bank

    data = SMSParser.parse(
        sms.text
    )


    transaction_id = data["transaction_id"]



    if not transaction_id:

        raise HTTPException(
            status_code=400,
            detail="Transaction ID missing"
        )



    # Check duplicate transaction

    existing = (
        db.query(SMSTransaction)
        .filter(
            SMSTransaction.transaction_id ==
            transaction_id
        )
        .first()
    )



    if existing:

        return {

            "status": "duplicate",

            "transaction_id": transaction_id,

        }



    transaction = SMSTransaction(

        transaction_id=transaction_id,

        amount=data["amount"],

        source=data["source"],

        transaction_type="UNKNOWN",

        sender=sms.from_,

    )



    db.add(transaction)

    db.commit()

    db.refresh(transaction)



    return {

        "status": "saved",

        "transaction_id": transaction_id,

        "source": data["source"],

        "amount": str(data["amount"]),

        "type": "UNKNOWN",

    }