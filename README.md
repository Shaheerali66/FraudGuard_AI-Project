# Credit Card Fraud Detection Web Application

A complete, production-quality Credit Card Fraud Detection system featuring a Machine Learning model trained on Kaggle data, a FastAPI backend, and a premium Streamlit frontend dashboard.

## Architecture

The project is divided into three modules, each designed to run in its own virtual environment to avoid dependency conflicts:
1.  **Model**: Data preprocessing, feature engineering, and Random Forest model training.
2.  **Backend**: A RESTful API built with FastAPI serving the trained model.
3.  **Frontend**: A responsive, banking-style Streamlit dashboard.

## Folder Structure

```text
CreditCardFraudDetection/
├── data/                        # Place your Kaggle CSV here
├── backend/                     # FastAPI application
├── frontend/                    # Streamlit dashboard
├── logs/                        # Automatically generated rotation logs
├── model/                       # ML training scripts
├── .gitignore
├── LICENSE
└── README.md
```

## Setup Instructions

### 1. Model Training
1. Download the Credit Card Fraud Detection dataset from Kaggle and place it at `data/credit_card_transactions.csv`.
2. Open a terminal and navigate to the `model/` directory.
3. Create a virtual environment and install dependencies:
   ```bash
   cd model
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   # source venv/bin/activate
   
   pip install -r requirements.txt
   ```
4. Run the training script:
   ```bash
   python train_model.py
   ```
   This will engineer features, train a Balanced Random Forest, print evaluation metrics, and save `fraud_model_pipeline.pkl` into the `backend/` directory.

### 2. Backend (FastAPI)
1. Navigate to the `backend/` directory.
2. Create its virtual environment:
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
3. Start the API server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
4. Test the API by visiting `http://127.0.0.1:8000/docs`.

### 3. Frontend (Streamlit)
1. Navigate to the `frontend/` directory.
2. Create its virtual environment:
   ```bash
   cd frontend
   python -m venv venv
   venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```
3. Start the dashboard:
   ```bash
   streamlit run app.py
   ```
4. Access the dashboard at `http://localhost:8501`.

## Features
- **Real-Time Emulator**: Send synthetic transactions and view the model's risk verdict (Approved, Warning, Blocked) in real-time.
- **Risk Command Center**: Global KPI metrics and historical transaction analytics with interactive charts.
- **CSV Batch Upload**: Upload up to 5,000 transactions at once for bulk fraud analysis.
- **Merchant API**: Secure, key-authenticated REST endpoint for external e-commerce/payment integration.

---

## Merchant / API Integration

External e-commerce and payment systems can call the Fraud Check API directly during checkout.

### 1. Register a merchant

```bash
curl -X POST http://127.0.0.1:8000/api/v1/merchants/register \
  -H 'Content-Type: application/json' \
  -d '{"merchant_name": "My Store", "contact_email": "dev@mystore.com"}'
```

Response:
```json
{
  "merchant_id": 2,
  "merchant_name": "My Store",
  "api_key": "fg-a1b2c3d4e5f6...",
  "contact_email": "dev@mystore.com",
  "message": "Registration successful. Store your API key securely — it will not be shown again."
}
```

> ⚠️ Save the `api_key` immediately — it is shown only once.

You can also register directly from the **🔌 API Integration** page in the Streamlit dashboard.

### 2. Call the Fraud Check endpoint

**Endpoint:** `POST http://127.0.0.1:8000/api/v1/transactions`

**Required header:** `X-API-Key: <your_key>`

**Rate limit:** 100 requests per 60-second window per API key (returns HTTP 429 if exceeded).

#### Request schema

| Field | Type | Required | Description |
|---|---|---|---|
| `merchant` | string | ✅ | Merchant name |
| `merchant_category` | string | ✅ | e.g. `shopping_net`, `grocery_pos`, `gas_transport` |
| `amt` | float | ✅ | Transaction amount |
| `gender` | string | ✅ | Cardholder gender (`M` or `F`) |
| `city` | string | ✅ | City of transaction |
| `state` | string | ✅ | 2-letter state code |
| `city_pop` | int | ✅ | City population |
| `distance_from_home` | float | ✅ | Distance from home to merchant (km) |
| `is_night_transaction` | int (0/1) | ✅ | 1 if between 10 PM–5 AM |
| `transaction_hour` | int (0–23) | ✅ | Hour of transaction |
| `weekend_transaction` | int (0/1) | ✅ | 1 if Saturday or Sunday |

#### Example curl call

```bash
curl -X POST http://127.0.0.1:8000/api/v1/transactions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -d '{
    "merchant": "My Store",
    "merchant_category": "shopping_net",
    "amt": 149.99,
    "gender": "M",
    "city": "New York",
    "state": "NY",
    "city_pop": 500000,
    "distance_from_home": 5.2,
    "is_night_transaction": 0,
    "transaction_hour": 14,
    "weekend_transaction": 0
  }'
```

#### Response

```json
{
  "transaction_id": "TRX-3A7F91BC",
  "fraud_probability": 0.042,
  "verdict": "APPROVED",
  "risk_tier": "Low",
  "status": "Approved",
  "top_factors": [
    {
      "feature": "Distance from Home",
      "impact": 0.12,
      "direction": "decreases_risk"
    },
    {
      "feature": "Transaction Amount",
      "impact": 0.05,
      "direction": "increases_risk"
    }
  ]
}
```

#### How to act on the verdict

| `verdict` | Meaning | Recommended action |
|---|---|---|
| `APPROVED` | Low fraud risk | Allow the payment immediately |
| `VERIFICATION_REQUIRED` | Moderate risk | Hold payment, trigger OTP / 3-D Secure |
| `REJECTED` | High fraud risk | Block the payment, notify the customer |

### 3. Demo / internal key

A demo merchant (`FraudGuard Demo`) with API key `fg-demo-key-a1b2c3d4e5f6` is seeded automatically on first startup. The Streamlit frontend uses this key for all internal calls. Do not use this key in production.

### 4. Interactive API docs

Visit `http://127.0.0.1:8000/docs` for the full OpenAPI/Swagger UI with live request testing.

---

## Model Training & Explainability

We train the fraud detection pipeline using an advanced automated search and explainability workflow:

1. **Feature Engineering**: Implements geographical distance calculation (Haversine) and time-based feature extraction.
2. **Model Selection**: Upgrades the model search using `RandomizedSearchCV` with 5-fold stratified cross-validation. We optimize and evaluate multiple candidates (`RandomForestClassifier` vs `XGBClassifier`) for **ROC-AUC** and **F1-score**.
3. **Training Report**: A detailed report comparing candidate models is automatically saved to `model/training_report.txt` after training.
4. **Explainability**: Calculates SHAP values using a fitted `TreeExplainer` on the best model, outputting the top 3-5 factors that either increase or decrease risk for real-time inference.

