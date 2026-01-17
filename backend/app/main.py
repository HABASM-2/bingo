from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routes import auth, bingo
from app.models import user
from app.database_init import ensure_database
from app.routes import admin



# --- ensure database exists ---
ensure_database()

app = FastAPI(title="Bingo API")

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Create tables ---
Base.metadata.create_all(bind=engine)

# --- Include routes ---
app.include_router(bingo.router)
app.include_router(auth.router)
app.include_router(admin.router)

@app.get("/")
def root():
    return {"message": "Bingo API is running 🚀"}
