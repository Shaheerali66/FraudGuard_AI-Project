def get_risk_tier_and_verdict(probability: float) -> tuple[str, str]:
    """
    Risk rules
    0–30% -> Approved (Low risk)
    30–75% -> Warning (Warning risk tier)
    75–100% -> Rejected (High risk tier)
    """
    if probability <= 0.30:
        return "Low", "APPROVED"
    elif probability <= 0.75:
        return "Warning", "VERIFICATION_REQUIRED"
    else:
        return "High", "REJECTED"
