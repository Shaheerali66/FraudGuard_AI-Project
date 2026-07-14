from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transactions.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ─── Deterministic demo key ───────────────────────────────────────────────────
# Used by the frontend and seeded into the DB on first run so internal calls
# work without any manual configuration.
DEMO_API_KEY = "fg-demo-key-a1b2c3d4e5f6"


# ─── ORM models ───────────────────────────────────────────────────────────────

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    merchant_category = Column(String)
    amount = Column(Float)
    gender = Column(String)
    city_population = Column(Integer)
    distance_from_home = Column(Float)
    is_night_transaction = Column(Integer)

    fraud_probability = Column(Float)
    risk_tier = Column(String)
    status = Column(String)           # Approved | Pending Review | Flagged | Blocked

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    top_factor_1 = Column(String, nullable=True)
    top_factor_2 = Column(String, nullable=True)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, index=True)
    banker_id = Column(Integer, nullable=True)
    decision = Column(String)         # APPROVED | BLOCKED | VERIFICATION_REQUIRED
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String)
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    type = Column(String)
    message = Column(String)
    status = Column(String, default="unread")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    merchant_name = Column(String, nullable=False)
    api_key = Column(String, unique=True, index=True, nullable=False)
    contact_email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ─── Create tables ────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)


# ─── Seeding ──────────────────────────────────────────────────────────────────

def seed_demo_merchant() -> None:
    """
    Create a deterministic demo merchant on first run if no merchant rows exist.
    This ensures the Streamlit frontend (which uses DEMO_API_KEY) works out of
    the box without manual registration.
    """
    db = SessionLocal()
    try:
        if db.query(Merchant).count() == 0:
            demo = Merchant(
                merchant_name="FraudGuard Demo",
                api_key=DEMO_API_KEY,
                contact_email="demo@fraudguard.io",
                is_active=True,
            )
            db.add(demo)
            db.commit()
    finally:
        db.close()


# ─── DB session dependency ────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
