import logging

logger = logging.getLogger(__name__)

def get_account_margin_context(api, oanda_account_id: str) -> dict:
    try:
        from oandapyV20.endpoints.accounts import AccountDetails

        resp = api.request(AccountDetails(accountID=oanda_account_id))
        acc = resp.get("account", {})
        return {
            "currency": acc.get("currency", "USD"),
            "margin_available": float(acc.get("marginAvailable", 0)),
            "balance": float(acc.get("balance", 0)),
            "margin_rate": float(acc.get("marginRate", 0.05)),
            "leverage": 1.0 / float(acc.get("marginRate", 0.05)) if acc.get("marginRate") else 20.0,
        }
    except Exception as e:
        logger.warning(f"Margin context fetch failed: {e}")
        return {}

def _fetch_cross_rate(api, from_ccy: str, to_ccy: str) -> float:
    if from_ccy == to_ccy:
        return 1.0
    try:
        from oandapyV20.endpoints.instruments import InstrumentsCandles

        def _ask(pair):
            r = InstrumentsCandles(
                instrument=pair,
                params={"count": 1, "granularity": "M1", "price": "A"},
            )
            return float(api.request(r)["candles"][0]["ask"]["c"])

        for pair in (f"{from_ccy}_{to_ccy}", f"{to_ccy}_{from_ccy}"):
            try:
                rate = _ask(pair)
                return rate if pair.startswith(from_ccy) else (1.0 / rate)
            except Exception:
                continue

        try:
            r1 = _ask(f"{from_ccy}_USD") if from_ccy != "USD" else 1.0
            r2 = _ask(f"{to_ccy}_USD") if to_ccy != "USD" else 1.0
            if r1 and r2:
                return r2 / r1
        except Exception:
            pass

        return 1.0
    except Exception:
        return 1.0

def check_margin_available(
    api,
    oanda_account_id: str,
    instrument: str,
    units: int,
    current_price: float,
    account_ctx: dict | None = None,
    safety_buffer: float = 1.2,
) -> tuple[bool, str]:
    try:
        ctx = account_ctx or get_account_margin_context(api, oanda_account_id)
        if not ctx:
            return (True, "Margin check skipped (no account context)")

        margin_available = ctx["margin_available"]
        margin_rate = ctx["margin_rate"]
        acc_currency = ctx.get("currency", "USD")

        instrument_clean = instrument.replace("_", "")
        if len(instrument_clean) >= 6:
            quote_ccy = instrument_clean[3:6]
        else:
            quote_ccy = acc_currency

        notional = abs(units) * current_price

        quote_to_acc = 1.0
        if quote_ccy != acc_currency:
            quote_to_acc = _fetch_cross_rate(api, quote_ccy, acc_currency)

        notional_acc_ccy = notional * quote_to_acc
        required = notional_acc_ccy * margin_rate * safety_buffer

        if margin_available < required:
            return (
                False,
                f"INSUFFICIENT MARGIN — avail={margin_available:.2f} {acc_currency}, "
                f"need={required:.2f} {acc_currency} "
                f"(notional={notional:.0f} {quote_ccy} → {notional_acc_ccy:.0f} {acc_currency}, "
                f"units={units}, px={current_price:.5f}, rate={margin_rate}, "
                f"quote2acc={quote_to_acc:.4f})",
            )
        return (
            True,
            f"Margin OK — avail={margin_available:.2f} {acc_currency}, "
            f"need={required:.2f} {acc_currency} (notional={notional_acc_ccy:.0f} {acc_currency})",
        )
    except Exception as e:
        return (True, f"Margin check skipped (API err: {e})")

def compute_max_safe_units(
    api,
    oanda_account_id: str,
    instrument: str,
    current_price: float,
    account_ctx: dict | None = None,
    safety_buffer: float = 1.2,
) -> int:
    try:
        ctx = account_ctx or get_account_margin_context(api, oanda_account_id)
        if not ctx or current_price <= 0:
            return 0
        margin_available = ctx["margin_available"]
        margin_rate = ctx["margin_rate"]
        acc_currency = ctx.get("currency", "USD")

        instrument_clean = instrument.replace("_", "")
        quote_ccy = instrument_clean[3:6] if len(instrument_clean) >= 6 else acc_currency
        quote_to_acc = 1.0
        if quote_ccy != acc_currency:
            quote_to_acc = _fetch_cross_rate(api, quote_ccy, acc_currency)

        max_notional_acc = margin_available / (margin_rate * safety_buffer)
        max_units = int(max_notional_acc / (current_price * quote_to_acc))
        return max(0, max_units)
    except Exception:
        return 0
