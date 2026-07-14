import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8000/api/v1"

SAMPLE_TX = {
    "merchant": "Amazon Store",
    "merchant_category": "shopping_net",
    "amt": 999.99, # High amount to trigger risk signals
    "gender": "M",
    "city": "New York",
    "state": "NY",
    "city_pop": 500000,
    "distance_from_home": 150.5, # Very far to trigger distance risk
    "is_night_transaction": 1,
    "transaction_hour": 3,
    "weekend_transaction": 1,
}

def post(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload else None
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

print("=" * 60)
print("Testing Fraud Detection with SHAP Explainability Factors")
print("=" * 60)

status, body = post(
    f"{BASE}/transactions",
    SAMPLE_TX,
    {"X-API-Key": "fg-demo-key-a1b2c3d4e5f6"}
)

print(f"Response Status: {status}")
print(f"Response Body Keys: {list(body.keys())}")
print(f"Transaction ID: {body.get('transaction_id')}")
print(f"Fraud Probability: {body.get('fraud_probability'):.4f}")
print(f"Verdict: {body.get('verdict')}")
print(f"Risk Tier: {body.get('risk_tier')}")
print(f"Status: {body.get('status')}")

print("\nExplanation Factors (top_factors):")
factors = body.get("top_factors", [])
for f in factors:
    print(f"  - Feature: {f['feature']:<30} | Impact: {f['impact']:.6f} | Direction: {f['direction']}")
    
assert len(factors) > 0, "No explainability factors were returned!"
print("\n[PASS] EXPLAINABILITY VERIFICATION PASSED SUCCESSFULLY!")
print("=" * 60)
