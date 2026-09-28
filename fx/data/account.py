import logging

logger = logging.getLogger(__name__)

def get_account_equity(api, oanda_account_id: str) -> float:
    try:
        from oandapyV20.endpoints.accounts import AccountDetails

        resp = api.request(AccountDetails(accountID=oanda_account_id))
        return float(resp["account"]["balance"])
    except Exception as e:
        logger.warning(f"Could not fetch equity: {e}, using fallback 10000")
        return 10000.0

def should_close_by_strength(
    pair: str, side: str, strength_scores: dict, threshold: float = 1.0
) -> tuple:
    clean = pair.replace("=X", "").replace("_", "")
    if len(clean) == 6:
        base, quote = clean[:3], clean[3:]
    else:
        parts = pair.replace("=X", "").split("_")
        if len(parts) == 2:
            base, quote = parts[0], parts[1]
        else:
            return False, ""

    base_score = strength_scores.get(base, 0)
    quote_score = strength_scores.get(quote, 0)
    gap = base_score - quote_score

    if side == "long" and -gap > threshold:
        return (
            True,
            f"Strength flip: {quote} (+{quote_score:.2f}) stronger than {base} ({base_score:.2f}), gap={-gap:.2f}",
        )
    if side == "short" and gap > threshold:
        return (
            True,
            f"Strength flip: {base} (+{base_score:.2f}) stronger than {quote} ({quote_score:.2f}), gap={gap:.2f}",
        )
    return False, ""
