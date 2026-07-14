"""
Full verification suite for the merchant API auth system.
Tests all 4 required scenarios:
  1. No API key → 401
  2. Valid demo key → fraud verdict
  3. /merchants/register → new key → use it successfully
  4. Invalid key → 401
"""
import urllib.request
import urllib.error
import json
import time

BASE = "http://127.0.0.1:8000/api/v1"

SAMPLE_TX = {
    "merchant": "Test Store",
    "merchant_category": "shopping_net",
    "amt": 49.99,
    "gender": "M",
    "city": "New York",
    "state": "NY",
    "city_pop": 500000,
    "distance_from_home": 5.2,
    "is_night_transaction": 0,
    "transaction_hour": 14,
    "weekend_transaction": 0,
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
print("FraudGuard Merchant Auth Verification Suite")
print("=" * 60)

# ── Test 1: No API key → 401
print("\n[1] POST /transactions with NO X-API-Key header...")
status, body = post(f"{BASE}/transactions", SAMPLE_TX)
assert status == 401, f"Expected 401, got {status}: {body}"
print(f"    [PASS] — HTTP {status}: {body.get('detail','')[:60]}")

# ── Test 2: Valid demo key → success
print("\n[2] POST /transactions with DEMO key...")
status, body = post(
    f"{BASE}/transactions",
    SAMPLE_TX,
    {"X-API-Key": "fg-demo-key-a1b2c3d4e5f6"},
)
assert status == 200, f"Expected 200, got {status}: {body}"
assert "verdict" in body and "fraud_probability" in body
print(f"    [PASS] — HTTP {status} | verdict={body['verdict']} "
      f"score={body['fraud_probability']:.3f} tx={body['transaction_id']}")

# ── Test 3: Register new merchant → get key → use it
print("\n[3] POST /merchants/register -> new key -> call /transactions with it...")
status, reg = post(
    f"{BASE}/merchants/register",
    {"merchant_name": "Verify Shop", "contact_email": "verify@testshop.io"},
)
assert status == 200, f"Registration failed ({status}): {reg}"
new_key = reg["api_key"]
print(f"    Registered: id={reg['merchant_id']} key={new_key}")

status, body = post(
    f"{BASE}/transactions",
    SAMPLE_TX,
    {"X-API-Key": new_key},
)
assert status == 200, f"Expected 200 with new key, got {status}: {body}"
print(f"    [PASS] — New key works: verdict={body['verdict']} tx={body['transaction_id']}")

# ── Test 4: Invalid key → 401
print("\n[4] POST /transactions with INVALID key...")
status, body = post(
    f"{BASE}/transactions",
    SAMPLE_TX,
    {"X-API-Key": "fg-totally-fake-key-0000"},
)
assert status == 401, f"Expected 401, got {status}: {body}"
print(f"    [PASS] — HTTP {status}: {body.get('detail','')[:60]}")

print("\n" + "=" * 60)
print("ALL 4 TESTS PASSED")
print("=" * 60)
