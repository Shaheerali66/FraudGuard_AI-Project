import time
import secrets
import joblib
import pandas as pd
import os
import uuid
import io
import random
from datetime import datetime
from typing import List
from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from schemas import (
    TransactionInput, PredictionResponse, TransactionRecord,
    DashboardStats, BatchTransactionResult, BatchPredictionResponse,
    MerchantRegisterRequest, MerchantRegisterResponse, ExplanationFactor
)
from config import settings
from logger import logger
from utils import get_risk_tier_and_verdict
from database import get_db, Transaction, Merchant, seed_demo_merchant
from auth import get_current_merchant

# ─── App definition ───────────────────────────────────────────────────────────

app = FastAPI(
    title="FraudGuard Enterprise API",
    version="2.0.0",
    description=(
        "Real-time Credit Card Fraud Detection API for e-commerce and payment integrations. "
        "Register a merchant account to obtain an API key, then call "
        "POST /api/v1/transactions with your checkout data to receive an instant fraud verdict."
    ),
    contact={"name": "FraudGuard Support", "email": "support@fraudguard.io"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global exception handler ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error. Please check the logs."},
    )

# ─── Request logging middleware ───────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    elapsed = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} "
        f"status={response.status_code} time={elapsed:.4f}s"
    )
    return response

# ─── Model loading ────────────────────────────────────────────────────────────

pipeline = None
shap_explainer = None
feature_names = None

@app.on_event("startup")
def startup():
    global pipeline, shap_explainer, feature_names
    # Load the ML model
    model_path = os.path.join(os.path.dirname(__file__), "fraud_model_pipeline.pkl")
    try:
        if os.path.exists(model_path):
            pipeline = joblib.load(model_path)
            logger.info("Model pipeline loaded successfully.")
        else:
            logger.warning(f"Model pipeline not found at {model_path}.")
    except Exception as e:
        logger.error(f"Error loading model pipeline: {e}")

    # Load SHAP explainer
    explainer_path = os.path.join(os.path.dirname(__file__), "shap_explainer.pkl")
    try:
        if os.path.exists(explainer_path):
            shap_explainer = joblib.load(explainer_path)
            logger.info("SHAP explainer loaded successfully.")
        else:
            logger.warning(f"SHAP explainer not found at {explainer_path}.")
    except Exception as e:
        logger.error(f"Error loading SHAP explainer: {e}")

    # Load feature names
    names_path = os.path.join(os.path.dirname(__file__), "feature_names.pkl")
    try:
        if os.path.exists(names_path):
            feature_names = joblib.load(names_path)
            logger.info("Feature names loaded successfully.")
        else:
            logger.warning(f"Feature names not found at {names_path}.")
    except Exception as e:
        logger.error(f"Error loading feature names: {e}")

    # Seed the demo merchant so the frontend works out of the box
    seed_demo_merchant()
    logger.info("Demo merchant seed check complete.")

# ─── Shared prediction helper ─────────────────────────────────────────────────

def predict_single(transaction: TransactionInput, db: Session, compute_explainability: bool = False) -> PredictionResponse:
    """
    Core ML prediction logic shared by both the single-transaction and
    batch endpoints. Runs the model, determines risk tier, persists to DB,
    and returns a PredictionResponse.
    """
    input_data = pd.DataFrame([transaction.model_dump()])

    # Patch any columns the pipeline expects but TransactionInput doesn't carry
    patch_cols = {
        "category":                  transaction.merchant_category,
        "Merchant_Category":         transaction.merchant_category,
        "Transaction_Type":          "Online",
        "Transaction_Time":          "12:00",
        "Payment_Method":            "Credit Card",
        "merch_zipcode":             10000,
        "Customer_Satisfaction_Score": 5,
        "Customer_Age":              30,
        "Loyalty_Points_Earned":     100,
    }
    for col, val in patch_cols.items():
        if col not in input_data.columns:
            input_data[col] = val

    prob_array = pipeline.predict_proba(input_data)
    fraud_probability = float(prob_array[0][1])

    if fraud_probability < 0.30:
        risk_tier, verdict, status = "Low",     "APPROVED",               "Approved"
    elif fraud_probability < 0.75:
        risk_tier, verdict, status = "Warning", "VERIFICATION_REQUIRED",  "Pending Review"
    else:
        risk_tier, verdict, status = "High",    "REJECTED",               "Flagged"

    tx_id = f"TRX-{uuid.uuid4().hex[:8].upper()}"

    # SHAP Explainability
    top_factors = []
    top_factor_1 = None
    top_factor_2 = None

    if compute_explainability and shap_explainer is not None and feature_names is not None:
        try:
            preprocessor = pipeline.named_steps['preprocessor']
            row_transformed = preprocessor.transform(input_data)
            if hasattr(row_transformed, "toarray"):
                row_transformed = row_transformed.toarray()
            
            raw_shap = shap_explainer.shap_values(row_transformed)
            if isinstance(raw_shap, list):
                raw_shap = raw_shap[1]
            if len(raw_shap.shape) > 1:
                raw_shap = raw_shap[0]
            
            factors_list = []
            for name, val in zip(feature_names, raw_shap):
                factors_list.append((name, float(val)))
            
            # Sort by absolute SHAP value descending
            factors_list.sort(key=lambda x: abs(x[1]), reverse=True)
            
            # Take top 5
            for name, val in factors_list[:5]:
                direction = "increases_risk" if val > 0 else "decreases_risk"
                top_factors.append(ExplanationFactor(feature=name, impact=abs(val), direction=direction))
            
            if len(top_factors) > 0:
                top_factor_1 = top_factors[0].feature
            if len(top_factors) > 1:
                top_factor_2 = top_factors[1].feature
        except Exception as e:
            logger.error(f"Error computing SHAP explainability: {e}", exc_info=True)

    db_tx = Transaction(
        transaction_id=tx_id,
        merchant_category=transaction.merchant_category,
        amount=transaction.amt,
        gender=transaction.gender,
        city_population=transaction.city_pop,
        distance_from_home=transaction.distance_from_home,
        is_night_transaction=transaction.is_night_transaction,
        fraud_probability=fraud_probability,
        risk_tier=risk_tier,
        status=status,
        top_factor_1=top_factor_1,
        top_factor_2=top_factor_2
    )
    db.add(db_tx)
    db.commit()
    db.refresh(db_tx)

    return PredictionResponse(
        transaction_id=tx_id,
        fraud_probability=fraud_probability,
        verdict=verdict,
        risk_tier=risk_tier,
        status=status,
        top_factors=top_factors
    )

# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    """Quick liveness/readiness probe."""
    return {"status": "healthy", "model_loaded": pipeline is not None}

# ─── Merchant registration (public) ──────────────────────────────────────────

@app.post(
    f"{settings.API_VERSION}/merchants/register",
    response_model=MerchantRegisterResponse,
    summary="Register a new merchant and receive an API key",
    description=(
        "Self-service merchant registration. Supply a company name and contact email; "
        "the API returns a unique `api_key` you must store securely — it is shown only once. "
        "Use this key as the `X-API-Key` header when calling the fraud-check endpoint."
    ),
    tags=["Merchant"],
)
def register_merchant(body: MerchantRegisterRequest, db: Session = Depends(get_db)):
    # Check for duplicate email (simple uniqueness guard)
    existing = db.query(Merchant).filter(Merchant.contact_email == body.contact_email).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A merchant with this email is already registered.",
        )

    new_key = f"fg-{secrets.token_hex(16)}"
    merchant = Merchant(
        merchant_name=body.merchant_name,
        api_key=new_key,
        contact_email=body.contact_email,
        is_active=True,
    )
    db.add(merchant)
    db.commit()
    db.refresh(merchant)

    logger.info(
        f"MERCHANT_REGISTER | id={merchant.id} "
        f"name='{merchant.merchant_name}' email='{merchant.contact_email}'"
    )

    return MerchantRegisterResponse(
        merchant_id=merchant.id,
        merchant_name=merchant.merchant_name,
        api_key=new_key,
        contact_email=merchant.contact_email,
        message=(
            "Registration successful. Store your API key securely — "
            "it will not be shown again."
        ),
    )

# ─── Single transaction (merchant-authenticated) ──────────────────────────────

@app.post(
    f"{settings.API_VERSION}/transactions",
    response_model=PredictionResponse,
    summary="Real-time fraud check for a single transaction",
    description=(
        "**Primary endpoint for merchant / e-commerce integrations.**\n\n"
        "Submit one transaction during checkout and receive an instant fraud verdict.\n\n"
        "**Authentication:** Pass your API key as the `X-API-Key` HTTP header.\n\n"
        "**Rate limit:** 100 requests per 60-second window per API key.\n\n"
        "**How to act on the response:**\n"
        "- `verdict = APPROVED` → allow the payment immediately.\n"
        "- `verdict = VERIFICATION_REQUIRED` → hold the payment and ask the customer "
        "  to complete an additional authentication step (OTP, 3DS, etc.).\n"
        "- `verdict = REJECTED` → block the payment and notify the customer.\n\n"
        "The `fraud_probability` (0–1) and `risk_tier` (Low / Warning / High) give "
        "you the raw score for your own business-rule logic."
    ),
    tags=["Fraud Detection"],
)
def process_transaction(
    transaction: TransactionInput,
    db: Session = Depends(get_db),
    merchant: Merchant = Depends(get_current_merchant),
):
    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail="Fraud model is not loaded. Contact support.",
        )
    try:
        result = predict_single(transaction, db, compute_explainability=True)
        logger.info(
            f"FRAUD_CHECK | merchant_id={merchant.id} merchant='{merchant.merchant_name}' "
            f"tx={result.transaction_id} score={result.fraud_probability:.4f} "
            f"verdict={result.verdict}"
        )
        return result
    except Exception as e:
        logger.error(f"Error during prediction: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Prediction error: {str(e)}")

# ─── CSV Template download (bank-staff / internal) ────────────────────────────

@app.get(
    f"{settings.API_VERSION}/transactions/batch/template",
    tags=["Batch (Internal)"],
    summary="Download the CSV template for batch uploads",
)
def download_template():
    """Return a downloadable sample CSV showing the expected column format."""
    sample_csv = (
        "merchant,merchant_category,amt,gender,city,state,"
        "city_pop,distance_from_home,is_night_transaction,transaction_hour,weekend_transaction\n"
        "Amazon,shopping_net,49.99,M,New York,NY,500000,5.2,0,14,0\n"
        "Walmart,grocery_pos,120.50,F,Los Angeles,CA,800000,1.8,0,10,1\n"
        "Shell,gas_transport,65.00,M,Chicago,IL,200000,12.5,1,23,0\n"
        "Netflix,entertainment,15.99,F,Houston,TX,350000,0.5,0,19,0\n"
        "eBay,misc_net,299.00,M,Phoenix,AZ,150000,8.3,0,16,1\n"
    )
    return StreamingResponse(
        io.BytesIO(sample_csv.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraud_detection_template.csv"},
    )

# ─── Batch upload (bank-staff / internal, no merchant auth) ──────────────────

REQUIRED_CSV_COLUMNS = {"merchant", "merchant_category", "amt", "gender", "city", "state"}
MAX_BATCH_ROWS = 5_000

@app.post(
    f"{settings.API_VERSION}/transactions/batch",
    response_model=BatchPredictionResponse,
    tags=["Batch (Internal)"],
    summary="Batch fraud check via CSV upload (bank staff only)",
    description=(
        "Internal tool for bank officers to analyse large transaction sets in one upload. "
        "Not intended for external merchant integration. "
        "No API key required — access is controlled at the network/session layer."
    ),
)
async def process_batch(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")

    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="CSV file contains no data rows.")

    if len(df) > MAX_BATCH_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File has {len(df)} rows, exceeding the limit of {MAX_BATCH_ROWS}."
            ),
        )

    df.columns = df.columns.str.strip()
    missing_cols = REQUIRED_CSV_COLUMNS - {c.lower() for c in df.columns}
    if missing_cols:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV is missing required column(s): {', '.join(sorted(missing_cols))}. "
                f"Required: {', '.join(sorted(REQUIRED_CSV_COLUMNS))}."
            ),
        )

    now = datetime.now()
    current_hour = now.hour
    is_night_default  = 1 if (current_hour >= 22 or current_hour < 5) else 0
    is_weekend_default = 1 if now.weekday() in [5, 6] else 0

    results: List[BatchTransactionResult] = []
    processed = failed = approved_count = pending_count = flagged_count = 0

    for idx, row in df.iterrows():
        row_num       = int(idx) + 1
        merchant_name = str(row.get("merchant", "N/A"))
        row_amt       = None

        try:
            row_amt = float(row["amt"])

            def _int_col(col, default):
                return int(row[col]) if col in df.columns and pd.notna(row.get(col)) else default

            def _float_col(col, default):
                return float(row[col]) if col in df.columns and pd.notna(row.get(col)) else default

            city_pop   = _int_col("city_pop",            random.randint(50_000, 1_000_000))
            distance   = _float_col("distance_from_home", round(random.uniform(1.0, 20.0), 2))
            is_night   = _int_col("is_night_transaction", is_night_default)
            tx_hour    = _int_col("transaction_hour",     current_hour)
            is_weekend = _int_col("weekend_transaction",  is_weekend_default)

            txn = TransactionInput(
                merchant=merchant_name,
                merchant_category=str(row["merchant_category"]),
                amt=row_amt,
                gender=str(row["gender"]),
                city=str(row["city"]),
                state=str(row["state"]),
                city_pop=city_pop,
                distance_from_home=distance,
                is_night_transaction=is_night,
                transaction_hour=tx_hour,
                weekend_transaction=is_weekend,
            )
            pred = predict_single(txn, db)
            processed += 1

            if pred.status == "Approved":        approved_count += 1
            elif pred.status == "Pending Review": pending_count  += 1
            elif pred.status == "Flagged":        flagged_count  += 1

            results.append(BatchTransactionResult(
                row_number=row_num,
                transaction_id=pred.transaction_id,
                merchant=merchant_name,
                amt=row_amt,
                fraud_probability=pred.fraud_probability,
                risk_tier=pred.risk_tier,
                status=pred.status,
            ))

        except Exception as e:
            failed += 1
            results.append(BatchTransactionResult(
                row_number=row_num,
                merchant=merchant_name,
                amt=row_amt,
                error=str(e),
            ))

    logger.info(
        f"BATCH | file='{file.filename}' total={len(df)} "
        f"processed={processed} failed={failed} "
        f"approved={approved_count} pending={pending_count} flagged={flagged_count}"
    )

    return BatchPredictionResponse(
        total_rows=len(df),
        processed=processed,
        failed=failed,
        approved=approved_count,
        pending=pending_count,
        flagged=flagged_count,
        results=results,
    )

# ─── Bank-officer review endpoints ───────────────────────────────────────────

@app.get(
    f"{settings.API_VERSION}/transactions/pending",
    response_model=List[TransactionRecord],
    tags=["Review"],
)
def get_pending_transactions(db: Session = Depends(get_db)):
    return (
        db.query(Transaction)
        .filter(Transaction.status.in_(["Pending Review", "Flagged"]))
        .order_by(Transaction.status == "Flagged")
        .all()
    )

@app.get(
    f"{settings.API_VERSION}/transactions/history",
    response_model=List[TransactionRecord],
    tags=["Review"],
)
def get_transaction_history(db: Session = Depends(get_db)):
    return (
        db.query(Transaction)
        .filter(Transaction.status.in_(["Approved", "Blocked"]))
        .order_by(Transaction.created_at.desc())
        .all()
    )

@app.put(f"{settings.API_VERSION}/transactions/{{tx_id}}/approve", tags=["Review"])
def approve_transaction(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.transaction_id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx.status = "Approved"
    tx.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Transaction approved successfully"}

@app.put(f"{settings.API_VERSION}/transactions/{{tx_id}}/block", tags=["Review"])
def block_transaction(tx_id: str, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.transaction_id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx.status = "Blocked"
    tx.reviewed_at = datetime.utcnow()
    db.commit()
    return {"message": "Transaction blocked successfully"}

@app.get(
    f"{settings.API_VERSION}/dashboard/stats",
    response_model=DashboardStats,
    tags=["Review"],
)
def get_dashboard_stats(db: Session = Depends(get_db)):
    total     = db.query(Transaction).count()
    approved  = db.query(Transaction).filter(Transaction.status == "Approved").count()
    pending   = db.query(Transaction).filter(Transaction.status == "Pending Review").count()
    flagged   = db.query(Transaction).filter(Transaction.status == "Flagged").count()
    blocked   = db.query(Transaction).filter(Transaction.status == "Blocked").count()
    avg_score = db.query(func.avg(Transaction.fraud_probability)).scalar() or 0.0

    return DashboardStats(
        total_transactions=total,
        approved=approved,
        pending=pending,
        flagged=flagged,
        blocked=blocked,
        avg_fraud_score=avg_score,
    )
