# ml/integration_hook.py — STAGE B INTEGRATION HOOK
# Enforces Phase 3.1 / A.2 contract §4.1.1 isolation while the frozen legacy
# production path (C-2) keeps running unchanged.
#
# Scope of this module (additive, NOT-YET-WIRED seam):
#   * It is a NEW PredictionResult consumer and is therefore bound by
#     §4.1.1(5): a non-READY result must never count as an ML vote or reach
#     Entry Authorization. While CD is unverified every live result is
#     UNINTERPRETABLE, so the guard blocks everything today.
#   * The legacy production path (C-2: strategy_decision.py / `model_p_up`) is a
#     registered Known Exception (§4.1.1.6). It is NOT re-executed here; the
#     caller passes its already-produced signal through unchanged.
#   * Nothing here changes Step 7 scoring, votes, weights, or trading behaviour.

import logging

from ml.live_prediction_engine import PredictionStatus

logger = logging.getLogger(__name__)


def evaluate_prediction_guard(prediction_result) -> bool:
    """§4.1.1 isolation guard.

    Returns True only when a PredictionResult is legally permitted to
    participate in downstream execution (ML vote / Entry Authorization).

    Today CD is NOT VERIFIED, so every live result is UNINTERPRETABLE and this
    returns False. The READY branch is deliberately kept so the seam unlocks
    naturally once CD verification lands (§1.3.2) without changing the guard.
    """
    # Rule 1: UNINTERPRETABLE is strictly blocked — inference succeeded but CD
    # is unverified, so no direction may be interpreted (§1.3.2).
    if prediction_result.status == PredictionStatus.UNINTERPRETABLE:
        logger.warning(
            "[GUARD-BLOCK] Pair=%s | Status=UNINTERPRETABLE (%s). "
            "Blocked from Entry Authorization.",
            prediction_result.pair,
            prediction_result.reason,
        )
        return False

    # Rule 2: only READY may pass; every other status (UNAVAILABLE, NOT_RUN,
    # INVALID, ERROR, ABSTAIN, ...) is blocked (§1.5, §4.2).
    if prediction_result.status != PredictionStatus.READY:
        logger.info(
            "[GUARD-BLOCK] Pair=%s | Status=%s (%s). Blocked.",
            prediction_result.pair,
            prediction_result.status,
            prediction_result.reason,
        )
        return False

    return True


def guarded_live_polling_hook(
    pair: str,
    timeframe: str,
    raw_candles,
    live_engine,
    legacy_signal=None,
):
    """Guarded sidecar audit hook.

    The caller's frozen legacy path (C-2) has already produced `legacy_signal`.
    This hook runs ONLY the new engine under §4.1.1 isolation, audits the
    result, and returns `legacy_signal` unchanged. It never re-runs the frozen
    path and never touches orders, so it has zero effect on live behaviour.
    """
    try:
        prediction_result = live_engine.predict_live(pair, timeframe, raw_candles)

        if evaluate_prediction_guard(prediction_result):
            # Unreachable while CD is unverified. Reserved for the post-CD
            # activation gate; even then this hook performs no execution.
            logger.info("[AUTHORIZED] New ML engine authorized action for %s.", pair)
        else:
            # Safely audit the intercepted prediction without touching orders.
            logger.debug(
                "[AUDIT-LOG] Pair=%s | Status=%s | RawProb=%s | LegacySignal=%s",
                pair,
                prediction_result.status,
                prediction_result.raw_probability,
                legacy_signal,
            )
    except Exception:
        # Isolation: a prediction/audit failure must never break the live loop.
        logger.exception("[INTEGRATION-ERROR] Guarded prediction failed for %s", pair)

    return legacy_signal
