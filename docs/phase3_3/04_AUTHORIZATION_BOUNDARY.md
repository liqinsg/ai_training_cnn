# Phase 3.3 — Authorization Boundary

**Document ID:** `PHASE3_3_AUTHORIZATION_BOUNDARY`
**Date:** 2026-11-16
**Purpose:** State precisely what Phase 3.3 may and may not do. Phase 3.3 is a **research** phase for predictive value; it is **not** an implementation authorization.

---

## 1. Phase 3.3 MAY do (research only)

| Allowed | Constraint |
|---|---|
| Evaluate the predictive value of the 33 eligible candidates | per `02_FEATURE_VALUE_EVALUATION_PROTOCOL.md`, subject to its own execution authorization |
| Select or reject candidates **for predictive reasons** | must not alter any technical definition |
| Preregister evaluation protocols, hypotheses, splits, trial budgets | before inspecting results |
| Produce analysis reports and proposals | no production effect |
| Read the existing legacy bundle (read-only) | no writes/overwrites; negative validation recorded in `05_…` |

## 2. Phase 3.3 MAY NOT do

| Forbidden | Reason |
|---|---|
| Train any model | needs new authorization |
| Write / overwrite / publish model artifacts | needs new authorization |
| Change a frozen parameter or a feature definition | returns to the Phase 3.2 owner process |
| Re-issue / alter the Feature Contract Identity | Phase 3.2 decision |
| Freeze the `PredictionResult` / prediction schema | not approved |
| Set `USE_FEATURE_CONTRACT_V2` default ON | not allowed |
| Wire live prediction (READY / `live_hook`) | not allowed |
| Deploy | not allowed |
| Change trading behavior | not allowed |
| Treat research "success" as implementation approval | research ≠ authorization |

## 3. Operations requiring separate, specific owner approval

Each of the following needs its **own explicit** authorization naming the scope, data, compute and acceptance — a blanket "approve Phase 3.3" is insufficient:

1. Model training (any scope).
2. Artifact write / overwrite / publish.
3. Production deployment.
4. READY activation / live-prediction wiring.
5. Trading-behavior change.
6. Any change to a Contract, a frozen parameter, or an identity.
7. Execution of the value-evaluation protocol (`02_…`).

## 4. Conditions to unlock a gate

Before any gate in §3 is opened, **all** must hold:

1. the corresponding verification stage has complete acceptance evidence;
2. every open item for that gate is explicitly dispositioned (not silently skipped);
3. the relevant Contract and artifact identities are fixed;
4. change scope, impact path and rollback are stated;
5. the **owner** approves that specific action.

## 5. Standing clause (proposed)

> Phase 3.3 predictive-value research does not constitute a re-freeze of the Phase 3.2 Feature Contract, and does not automatically grant production-implementation, model-training, or runtime-wiring rights.

## 6. Inherited red lines (still in force)

- Do not train, do not write/overwrite artifacts, do not deploy, do not activate READY, do not change trading behavior.
- Fail closed on any unapproved/unevidenced calendar, session, gap, or invalid candle — no silent fallback.
- All runtime-path changes stay behind the default-`False` `USE_FEATURE_CONTRACT_V2` switch.
- Append-only records; do not rewrite approved wording.
- Do not relax tolerances after seeing results.
- Do not mark P3–P5 as pass / waived / `NOT REQUIRED`.
