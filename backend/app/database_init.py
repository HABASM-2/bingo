# app/database_init.py
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
from app.database import DATABASE_URL  # your SQLAlchemy URL

def ensure_database():
    if not database_exists(DATABASE_URL):
        create_database(DATABASE_URL)
        print(f"✅ Database created: {DATABASE_URL}")
    else:
        print(f"ℹ️ Database already exists: {DATABASE_URL}")
