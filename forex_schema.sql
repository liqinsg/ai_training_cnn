-- Forex bot schema for Oracle Autonomous AI Database (Transaction Processing)
-- Conventions: UTC timestamps, NUMBER for money/prices (never FLOAT),
-- env ('DEMO'/'LIVE') on every table that records bot activity.
-- Run as a dedicated schema user (e.g. FXBOT), NOT as ADMIN.

---------------------------------------------------------------- 1. REFERENCE
CREATE TABLE fx_instrument (
  instrument   VARCHAR2(10) PRIMARY KEY,           -- 'USD_JPY'
  pip_size     NUMBER(8,5)  NOT NULL,              -- 0.01 JPY pairs, 0.0001 others
  quote_ccy    VARCHAR2(3)  NOT NULL,
  is_active    NUMBER(1) DEFAULT 1 NOT NULL
);

CREATE TABLE strategy_profile (
  profile_id   VARCHAR2(10) PRIMARY KEY,           -- 'P1','P3','P4'
  description  VARCHAR2(200),
  is_live      NUMBER(1) DEFAULT 0 NOT NULL,       -- P3 = 1; safe default is 0
  config_json  JSON,
  created_at   TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

---------------------------------------------------------------- 2. MARKET DATA
CREATE TABLE fx_candle (
  instrument   VARCHAR2(10) NOT NULL REFERENCES fx_instrument,
  granularity  VARCHAR2(4)  NOT NULL,              -- M15, M30, H1, H4
  ts           TIMESTAMP WITH TIME ZONE NOT NULL,
  o NUMBER(12,5) NOT NULL, h NUMBER(12,5) NOT NULL,
  l NUMBER(12,5) NOT NULL, c NUMBER(12,5) NOT NULL,
  volume       NUMBER(12),
  complete     NUMBER(1) DEFAULT 1 NOT NULL,
  CONSTRAINT pk_fx_candle PRIMARY KEY (instrument, granularity, ts)
) ORGANIZATION INDEX;                              -- candles are read by range

CREATE TABLE news_event (
  news_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_ts     TIMESTAMP WITH TIME ZONE NOT NULL,
  currency     VARCHAR2(3),
  impact       VARCHAR2(10),                       -- LOW/MED/HIGH
  headline     VARCHAR2(500),
  source       VARCHAR2(50),                       -- 'gemini_grounded'
  fetched_at   TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

CREATE TABLE api_usage (                            -- Gemini quota tracking
  usage_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  provider     VARCHAR2(20), model VARCHAR2(50),
  cache_hit    NUMBER(1), tokens_in NUMBER, tokens_out NUMBER,
  status       VARCHAR2(20)                        -- OK / QUOTA / ERROR
);

---------------------------------------------------------------- 3. DECISIONS
-- Decision and execution are separate: a decision may never become an order.
CREATE TABLE decision_run (
  run_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  env          VARCHAR2(4) NOT NULL CHECK (env IN ('DEMO','LIVE')),
  profile_id   VARCHAR2(10) NOT NULL REFERENCES strategy_profile,
  run_ts       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  git_sha      VARCHAR2(40),
  flags_json   JSON,                               -- snapshot of ENABLE_* switches
  config_hash  VARCHAR2(64),
  status       VARCHAR2(20)
);

CREATE TABLE strength_snapshot (                    -- 8 G10 currency ranking per run
  run_id       NUMBER NOT NULL REFERENCES decision_run,
  currency     VARCHAR2(3) NOT NULL,
  score        NUMBER(12,6), rank_pos NUMBER(2),
  score_v2     NUMBER(12,6),                       -- shadow ATR-normalized score
  CONSTRAINT pk_strength PRIMARY KEY (run_id, currency)
);

CREATE TABLE decision (
  decision_id  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id       NUMBER NOT NULL REFERENCES decision_run,
  instrument   VARCHAR2(10) NOT NULL REFERENCES fx_instrument,
  direction    VARCHAR2(5) CHECK (direction IN ('LONG','SHORT','FLAT')),
  final_score  NUMBER(10,4),
  action       VARCHAR2(20) NOT NULL,              -- TRADE / SKIP / BLOCKED_NEWS ...
  reason       VARCHAR2(400),
  record_json  JSON                                -- full JSONL-style decision record
);

CREATE TABLE decision_factor (                      -- attribution (Trend/Location/XGB/MC)
  decision_id  NUMBER NOT NULL REFERENCES decision,
  factor       VARCHAR2(20) NOT NULL,
  raw_score    NUMBER(10,4), weight NUMBER(6,4), contribution NUMBER(10,4),
  score_without NUMBER(10,4),                      -- counterfactual: factor removed
  flipped_action NUMBER(1),                        -- 1 if removal changes the action
  CONSTRAINT pk_dec_factor PRIMARY KEY (decision_id, factor)
);

---------------------------------------------------------------- 4. EXECUTION
CREATE TABLE trade_order (
  order_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  env               VARCHAR2(4) NOT NULL CHECK (env IN ('DEMO','LIVE')),
  decision_id       NUMBER REFERENCES decision,
  client_request_id VARCHAR2(64) NOT NULL UNIQUE,  -- idempotency: no double-submit
  oanda_order_id    VARCHAR2(30),
  oanda_trade_id    VARCHAR2(30),
  instrument        VARCHAR2(10) NOT NULL REFERENCES fx_instrument,
  side              VARCHAR2(4) NOT NULL CHECK (side IN ('BUY','SELL')),
  units_requested   NUMBER(12) NOT NULL,
  units_filled      NUMBER(12),                    -- requested vs filled reconciliation
  price_requested   NUMBER(12,5), price_filled NUMBER(12,5),
  sl_price          NUMBER(12,5), tp_price NUMBER(12,5),
  status            VARCHAR2(20) NOT NULL,         -- SUBMITTED/FILLED/PARTIAL/REJECTED
  error_text        VARCHAR2(400),
  submitted_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  filled_at         TIMESTAMP WITH TIME ZONE
);
CREATE INDEX ix_order_trade ON trade_order (oanda_trade_id);

---------------------------------------------------------------- 5. RISK / POSITIONS
CREATE TABLE position_cluster (
  cluster_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  env            VARCHAR2(4) NOT NULL CHECK (env IN ('DEMO','LIVE')),
  profile_id     VARCHAR2(10) NOT NULL REFERENCES strategy_profile,
  instrument     VARCHAR2(10) NOT NULL REFERENCES fx_instrument,
  side           VARCHAR2(4) NOT NULL,
  state          VARCHAR2(20) NOT NULL CHECK (state IN
                   ('INIT','BREAK_EVEN','TRAILING_CHANDELIER',
                    'TIME_DECAY_REDUCE','TIME_DECAY_EXIT','CLOSED')),
  entry_price_0  NUMBER(12,5) NOT NULL,            -- FROZEN: R basis
  r_unit_0       NUMBER(12,5) NOT NULL,            -- FROZEN: initial ATR-based risk
  initial_sl_0   NUMBER(12,5) NOT NULL,            -- FROZEN
  current_sl     NUMBER(12,5),
  opened_at      TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  closed_at      TIMESTAMP WITH TIME ZONE
);

-- Enforce "R is frozen" at the DB level
CREATE OR REPLACE TRIGGER trg_cluster_frozen_r
BEFORE UPDATE OF entry_price_0, r_unit_0, initial_sl_0 ON position_cluster
FOR EACH ROW
BEGIN
  RAISE_APPLICATION_ERROR(-20001, 'entry_price_0 / r_unit_0 / initial_sl_0 are immutable');
END;
/

CREATE TABLE cluster_unit (                         -- pyramid legs
  unit_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_id   NUMBER NOT NULL REFERENCES position_cluster,
  order_id     NUMBER REFERENCES trade_order,
  unit_seq     NUMBER(3) NOT NULL,                 -- 0 = base unit
  units_open   NUMBER(12) NOT NULL,
  entry_price  NUMBER(12,5) NOT NULL,
  CONSTRAINT uq_unit UNIQUE (cluster_id, unit_seq)
);

CREATE TABLE risk_event (                           -- state machine audit trail
  event_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_id   NUMBER NOT NULL REFERENCES position_cluster,
  ts           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  event_type   VARCHAR2(30) NOT NULL,              -- SL_MOVE, PARTIAL_CLOSE, PYRAMID_ADD...
  from_state   VARCHAR2(20), to_state VARCHAR2(20),
  sl_old NUMBER(12,5), sl_new NUMBER(12,5),
  r_multiple   NUMBER(8,3),
  details_json JSON
);

CREATE TABLE trade_close (
  close_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cluster_id   NUMBER NOT NULL REFERENCES position_cluster,
  order_id     NUMBER REFERENCES trade_order,
  units_closed NUMBER(12) NOT NULL,
  price        NUMBER(12,5) NOT NULL,
  realized_pl  NUMBER(18,5), fees NUMBER(18,5),
  reason       VARCHAR2(30),                       -- SL/TP/TIME_DECAY/MANUAL
  closed_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP
);

---------------------------------------------------------------- 6. OPS
CREATE TABLE reconciliation_log (                   -- bot state vs OANDA state
  recon_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  env          VARCHAR2(4) NOT NULL,
  ts           TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP,
  cluster_id   NUMBER REFERENCES position_cluster,
  check_type   VARCHAR2(30) NOT NULL,              -- SL_DRIFT, SIZE_MISMATCH, ORPHAN_TRADE
  expected_val VARCHAR2(60), actual_val VARCHAR2(60),
  resolved     NUMBER(1) DEFAULT 0 NOT NULL
);

CREATE TABLE equity_snapshot (
  env          VARCHAR2(4) NOT NULL CHECK (env IN ('DEMO','LIVE')),
  ts           TIMESTAMP WITH TIME ZONE NOT NULL,
  balance      NUMBER(18,2), nav NUMBER(18,2),
  unrealized_pl NUMBER(18,2), margin_used NUMBER(18,2),
  CONSTRAINT pk_equity PRIMARY KEY (env, ts)
);

---------------------------------------------------------------- 7. REPORTING
CREATE OR REPLACE VIEW v_profile_performance AS
SELECT c.env, c.profile_id, c.instrument,
       COUNT(DISTINCT c.cluster_id)            AS clusters,
       SUM(t.realized_pl - NVL(t.fees,0))      AS net_pl,
       SUM(CASE WHEN t.realized_pl > 0 THEN 1 ELSE 0 END) AS winning_closes,
       COUNT(t.close_id)                       AS closes
FROM position_cluster c
LEFT JOIN trade_close t ON t.cluster_id = c.cluster_id
GROUP BY c.env, c.profile_id, c.instrument;

-- Seed
INSERT INTO fx_instrument VALUES ('USD_JPY', 0.01, 'JPY', 1);
INSERT INTO fx_instrument VALUES ('EUR_JPY', 0.01, 'JPY', 1);
INSERT INTO fx_instrument VALUES ('GBP_JPY', 0.01, 'JPY', 1);
INSERT INTO fx_instrument VALUES ('AUD_JPY', 0.01, 'JPY', 1);
COMMIT;