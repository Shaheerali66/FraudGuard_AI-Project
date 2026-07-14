from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ─── Single-transaction I/O ───────────────────────────────────────────────────

class TransactionInput(BaseModel):
    merchant: str = Field(..., description="Name of the merchant")
    merchant_category: str = Field(..., description="Category of the merchant")
    amt: float = Field(..., description="Transaction amount")
    gender: str = Field(..., description="Gender of the cardholder (M or F)")
    city: str = Field(..., description="City of the transaction")
    state: str = Field(..., description="State of the transaction (2-letter code)")
    city_pop: int = Field(..., description="Population of the city")
    distance_from_home: float = Field(..., description="Distance between home and merchant (km)")
    is_night_transaction: int = Field(..., description="1 if transaction is between 10 PM and 5 AM, else 0")
    transaction_hour: int = Field(..., description="Hour of the transaction (0–23)")
    weekend_transaction: int = Field(..., description="1 if weekend, else 0")


class ExplanationFactor(BaseModel):
    feature: str
    impact: float
    direction: str  # increases_risk | decreases_risk

class PredictionResponse(BaseModel):
    transaction_id: str
    fraud_probability: float
    verdict: str
    risk_tier: str
    status: str
    top_factors: List[ExplanationFactor] = []


class TransactionRecord(BaseModel):
    id: int
    transaction_id: str
    merchant_category: str
    amount: float
    fraud_probability: float
    risk_tier: str
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    top_factor_1: Optional[str] = None
    top_factor_2: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_transactions: int
    approved: int
    pending: int
    flagged: int
    blocked: int
    avg_fraud_score: float


# ─── Batch I/O ────────────────────────────────────────────────────────────────

class BatchTransactionResult(BaseModel):
    row_number: int
    transaction_id: Optional[str] = None
    merchant: Optional[str] = None
    amt: Optional[float] = None
    fraud_probability: Optional[float] = None
    risk_tier: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class BatchPredictionResponse(BaseModel):
    total_rows: int
    processed: int
    failed: int
    approved: int
    pending: int
    flagged: int
    results: List[BatchTransactionResult]


# ─── Merchant registration ─────────────────────────────────────────────────────

class MerchantRegisterRequest(BaseModel):
    merchant_name: str = Field(..., description="Your company or store name")
    contact_email: str = Field(..., description="Contact email address")


class MerchantRegisterResponse(BaseModel):
    merchant_id: int
    merchant_name: str
    api_key: str
    contact_email: str
    message: str
