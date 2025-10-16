from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///./crm.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass  # ✅ THIS MUST BE INDENTED

# Dependency for FastAPI routes
def get_db():  # ✅ Function header (no indent here)
    db = SessionLocal()  # ✅ Indented block
    try:
        yield db
    finally:
        db.close()
