from fastapi import APIRouter
from app.api.routes import auth

from app.api.routes import sms

from app.bingo.router import router as bingo_router
from app.dama.router import router as dama_router
from app.aviator.router import router as aviator_router
from app.plinko.router import router as plinko_router
from app.lotto.router import router as lotto_router
from app.admin.router import router as admin_router

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

api_router.include_router(
    dama_router,
)

api_router.include_router(
    aviator_router,
)

api_router.include_router(
    plinko_router,
)

api_router.include_router(
    lotto_router,
)

api_router.include_router(
    admin_router,
)
