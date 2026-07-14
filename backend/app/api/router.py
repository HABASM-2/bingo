from fastapi import APIRouter
from app.api.routes import auth

from app.api.routes import sms

from app.bingo.router import router as bingo_router

api_router = APIRouter(prefix="/api")

api_router.include_router(
    auth.router,
    tags=["auth"],    
)

api_router.include_router(
    sms.router,
    tags=["sms"],    
)

api_router.include_router(
    bingo_router,
)