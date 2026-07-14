"""
End-to-end test for the batch CSV upload endpoint.
Run: python test_batch.py
"""
import urllib.request
import json

CSV_PATH = r"d:\Fraud_Detection_System\data\test_batch.csv"
API_URL  = "http://127.0.0.1:8000/api/v1/transactions/batch"

with open(CSV_PATH, "rb") as f:
    csv_data = f.read()

boundary = "----TestBoundary1234"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="test_batch.csv"\r\n'
    f"Content-Type: text/csv\r\n\r\n"
).encode() + csv_data + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request(
    API_URL,
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)

r = urllib.request.urlopen(req)
result = json.loads(r.read())

print("=== BATCH RESULT SUMMARY ===")
print(f"  total_rows : {result['total_rows']}")
print(f"  processed  : {result['processed']}")
print(f"  failed     : {result['failed']}")
print(f"  approved   : {result['approved']}")
print(f"  pending    : {result['pending']}")
print(f"  flagged    : {result['flagged']}")
print()
print("=== PER-ROW RESULTS ===")
for row in result["results"]:
    err = row.get("error") or "-"
    tx  = row.get("transaction_id") or "ERROR"
    merchant = str(row.get("merchant") or "?")[:12]
    score = row.get("fraud_probability")
    score_str = f"{score:.3f}" if score is not None else "N/A"
    status = row.get("status") or "ERR"
    print(f"  Row {row['row_number']:2d} | {tx:14s} | {merchant:<12s} | score={score_str} | status={status} | err={err}")
