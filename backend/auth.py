"""
auth.py — FastAPI dependency for merchant API-key authentication.

Every request to the protected /transactions endpoint must carry the header:
    X-API-Key: <your_key>

Rate limiting is enforced in-memory (no external dependencies):
    max 100 requests per 60-second sliding window, per API key.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Header, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, Merchant

# ─── In-memory rate-limit store ───────────────────────────────────────────────
# NOTE: this resets on server restart and is per-process only.
# For production, replace with Redis-backed counters.
_rl_store: dict[str, list[datetime]] = defaultdict(list)

RATE_LIMIT_MAX    = 100   # max requests …
RATE_LIMIT_WINDOW = 60    # … within this many seconds


def _enforce_rate_limit(api_key: str) -> None:
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=RATE_LIMIT_WINDOW)

    # Evict timestamps outside the sliding window
    _rl_store[api_key] = [ts for ts in _rl_store[api_key] if ts > cutoff]

    if len(_rl_store[api_key]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: maximum {RATE_LIMIT_MAX} requests "
                f"per {RATE_LIMIT_WINDOW} seconds allowed."
            ),
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
        )

    _rl_store[api_key].append(now)


# ─── Auth dependency ──────────────────────────────────────────────────────────

def get_current_merchant(
    x_api_key: str = Header(
        None,
        description="Merchant API key issued by FraudGuard. "
                    "Pass as HTTP header: X-API-Key: <your_key>",
    ),
    db: Session = Depends(get_db),
) -> Merchant:
    """
    Validate the X-API-Key header.
    - Returns the Merchant ORM object on success.
    - Raises HTTP 401 if the header is absent, key is unknown, or merchant is deactivated.
    - Raises HTTP 429 if the per-key rate limit is exceeded.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Add the header: X-API-Key: <your_key>. "
                   "Register at POST /api/v1/merchants/register.",
        )

    merchant = db.query(Merchant).filter(Merchant.api_key == x_api_key).first()

    if not merchant:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Register at POST /api/v1/merchants/register.",
        )
    if not merchant.is_active:
        raise HTTPException(
            status_code=401,
            detail="This API key has been deactivated. Contact FraudGuard support.",
        )

    _enforce_rate_limit(x_api_key)
    return merchant
