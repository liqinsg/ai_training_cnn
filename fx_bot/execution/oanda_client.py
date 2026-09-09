"""
# fx_bot/execution/oanda_client.py
OANDA 客户端 —— 新架构独立模块
仅从 fx_bot 内部导入，不引用任何上级目录老代码

适配自：config_oanda.py + fx_trade_bot_utils.py + setup_fx_bot.sh
配置来源：全部改为 Settings() 注入
"""
import logging
import time
from typing import Optional, Dict, Any

import pandas as pd
import oandapyV20
from oandapyV20.endpoints.accounts import AccountDetails, AccountSummary
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.endpoints.trades import OpenTrades, TradesList, TradeCRCDO, TradeClientExtensions

from core.config.settings import Settings

logger = logging.getLogger(__name__)


class OandaClient:
    """OANDA V20 API 客户端 —— 封装常用交易操作，配置通过 Settings 注入。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api = oandapyV20.API(
            access_token=settings.OANDA_API_KEY,
            environment=settings.OANDA_ENV,
        )
        self.account_id = settings.OANDA_ACCOUNT_ID

    # ── 账户信息 ──────────────────────────────────────────────────────────

    def get_account_equity(self) -> float:
        try:
            resp = self.api.request(AccountDetails(accountID=self.account_id))
            return float(resp["account"]["balance"])
        except Exception as e:
            logger.warning(f"Could not fetch equity: {e}, using fallback 10000.0")
            return 10000.0

    def get_account_summary(self) -> Dict[str, Any]:
        try:
            resp = self.api.request(AccountSummary(account_id=self.account_id))
            return resp.get("account", {})
        except Exception as e:
            logger.warning(f"Account summary failed: {e}")
            return {}

    # ── K 线数据 ─────────────────────────────────────────────────────────

    def fetch_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = 100,
    ) -> pd.DataFrame:
        """Fetch historical OHLC candles — returns clean DataFrame."""
        resp = self.api.request(
            InstrumentsCandles(
                instrument=instrument,
                params={"granularity": granularity, "count": count, "price": "M"},
            )
        )
        df = pd.DataFrame(
            [
                {
                    "Time": c["time"],
                    "Open": float(c["mid"]["o"]),
                    "High": float(c["mid"]["h"]),
                    "Low": float(c["mid"]["l"]),
                    "Close": float(c["mid"]["c"]),
                }
                for c in resp["candles"]
            ]
        ).set_index("Time")
        logger.debug(f"Fetched {instrument} {granularity} bars={len(df)}")
        return df

    # ── 持仓查询 ─────────────────────────────────────────────────────────

    def get_open_position(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Get current open position for an instrument.
        Returns None if no position exists, else dict: {"units": int, "side": "long"/"short"}
        """
        try:
            resp = self.api.request(
                PositionDetails(accountID=self.account_id, instrument=instrument)
            )
            pos = resp.get("position", {})
            long_units = pos.get("long", {}).get("units", "0")
            short_units = pos.get("short", {}).get("units", "0")

            if long_units != "0":
                return {"units": int(long_units), "side": "long"}
            if short_units != "0":
                return {"units": -int(short_units), "side": "short"}
            return None
        except Exception as e:
            if "NO_SUCH_POSITION" in str(e) or "404" in str(e):
                return None
            logger.warning(f"Position check failed for {instrument}: {e}")
            return None

    def get_my_position(
        self,
        instrument: str,
        tag_prefix: str = "FXBOT-AUTO",
        no_tag_fallback: bool = False,
    ):
        """
        🔒 SAFE by default: TAG match ONLY → returns None if no match.
        Turn on no_tag_fallback=True to return the FIRST open trade as fallback.

        ⚠️ clientExtensions 挂在 TRADE 上，不在 Position 对象上。
        因此必须查 GET /v3/accounts/{accountID}/trades?state=OPEN&instrument=...
        (旧实现读 position.trades —— 该字段不存在，永远返回 None)

        Returns: {units, side, trade_id, tag, entry_price} / None
        """
        try:
            resp = self.api.request(
                TradesList(
                    self.account_id,
                    params={"state": "OPEN", "instrument": instrument},
                )
            )
            trade_list = resp.get("trades", [])
        except Exception as e:
            logger.warning(f"⚠️ 持仓详情查询失败: {e}")
            return None

        if not trade_list:
            return None

        def _norm(t):
            units = float(t.get("currentUnits", 0))
            return {
                "units": abs(units),
                "side": "BUY" if units > 0 else "SELL",
                "trade_id": t.get("id"),
                "tag": t.get("clientExtensions", {}).get("tag", "") or "(none)",
                "entry_price": float(t.get("price", 0)),
            }

        # ── 1. TAG MATCH (always try first) ──────────────────────────────
        for t in trade_list:
            tag = t.get("clientExtensions", {}).get("tag", "")
            if tag.startswith(tag_prefix):
                logger.info(f"🎯 Found by TAG: TradeID={t.get('id')} TAG={tag}")
                return _norm(t)

        # ── 2. NO TAG MATCH — decide based on flag ───────────────────────
        if not no_tag_fallback:
            logger.info("⚠️ No TAG match — SAFE STOP, no action")
            return None

        # ── 3. FALLBACK: first open trade for this instrument ───────────
        first = trade_list[0]
        logger.info(
            f"⚠️ No TAG match — FALLBACK to FIRST trade: TradeID={first.get('id')}"
        )
        return _norm(first)

    def get_position(self) -> list:
        """Return list of all open trades."""
        try:
            resp = self.api.request(OpenTrades(self.account_id))
            return resp.get("trades", [])
        except Exception as e:
            logger.warning(f"Open trades fetch failed: {e}")
            return []

    # ── 下单 / 平仓 ───────────────────────────────────────────────────────

    def open_order(self, instrument, direction, units, sl, tp, tag="FXBOT-AUTO", dry_run=False):
        """开仓 — 附带自定义Tag用于归属识别

        ⚠️ OANDA 不会把 order.clientExtensions 自动传播到 trade。
        成交后必须用 TradeClientExtensions 在 trade 上写 tag，
        否则 get_my_position() 的 TAG 归属逻辑永远匹配不到。

        ⚠️ 拒单不抛异常：响应是 orderCancelTransaction / orderRejectTransaction。
        必须显式检查并返回 ok=False，否则会把失败误报成成功。
        """
        sl_str = self.format_price(sl, instrument)
        tp_str = self.format_price(tp, instrument)
        client_id = f"fxbot-{int(time.time() * 1000)}"
        client_ext = {"id": client_id, "tag": tag, "comment": "FXBOT auto trade"}

        payload = {
            "order": {
                "units": str(units if direction == "BUY" else -units),
                "instrument": instrument,
                "timeInForce": "FOK",
                "type": "MARKET",
                "stopLossOnFill": {"price": sl_str, "timeInForce": "GTC"},
                "takeProfitOnFill": {"price": tp_str, "timeInForce": "GTC"},
                # ✅ 专属标签：用于识别自己开的单
                "clientExtensions": client_ext,
            }
        }

        if dry_run:
            print(f"[DRY-RUN] Would {direction} {instrument} units={units} SL={sl_str} TP={tp_str} TAG={tag}")
            return {"ok": True, "trade_id": "SIMULATED", "tag": tag}

        try:
            resp = self.api.request(
                oandapyV20.endpoints.orders.OrderCreate(self.account_id, payload)
            )

            # ── 1. 拒绝检测：OANDA 拒单不抛异常 ────────────────────────────
            cancel = resp.get("orderCancelTransaction") or resp.get("orderRejectTransaction")
            if cancel:
                reason = cancel.get("reason", "UNKNOWN")
                logger.error(f"❌ Open order REJECTED by OANDA: {reason}")
                return {"ok": False, "error": f"ORDER_CANCELLED: {reason}"}

            # ── 2. 提取 trade_id：在 tradeOpened.tradeID，不在顶层 ─────────
            tx = resp.get("orderFillTransaction", {})
            trade_id = tx.get("tradeOpened", {}).get("tradeID", "") or tx.get("tradeID", "")
            if not trade_id:
                logger.error(f"❌ Open order filled but no tradeID: {list(resp.keys())}")
                return {"ok": False, "error": "NO_TRADE_ID_IN_FILL_TRANSACTION"}

            entry_price = float(tx.get("price", 0))

            # ── 3. 把 tag 写入 trade —— 关键！order tag 不会自动传播 ─────────
            try:
                self.api.request(
                    TradeClientExtensions(
                        self.account_id,
                        trade_id,
                        data={"clientExtensions": client_ext},
                    )
                )
                logger.info(f"🏷️  Trade tagged: TradeID={trade_id} TAG={tag}")
            except Exception as e:
                logger.warning(f"⚠️  TradeClientExtensions FAILED trade={trade_id}: {e}")

            logger.info(f"✅ Open order filled: TradeID={trade_id} TAG={tag}")
            return {
                "ok": True,
                "trade_id": trade_id,
                "tag": tag,
                "entry_price": entry_price,
                "response": resp,
            }
        except Exception as e:
            logger.error(f"❌ Open order failed: {e}")
            return {"ok": False, "error": str(e)}

    def close_position(self, instrument: str, dry_run: bool = False) -> bool:
        """Close existing position for instrument. Returns True on success."""
        if dry_run:
            logger.info(f"DRY-RUN — would CLOSE: {instrument}")
            return True
        try:
            pos = self.api.request(
                PositionDetails(accountID=self.account_id, instrument=instrument)
            ).get("position", {})
            if pos.get("long", {}).get("units", "0") != "0":
                units = -int(pos["long"]["units"])
            elif pos.get("short", {}).get("units", "0") != "0":
                units = abs(int(pos["short"]["units"]))
            else:
                logger.info(f"No position to close: {instrument}")
                return False

            self.api.request(
                OrderCreate(
                    accountID=self.account_id,
                    data={
                        "order": {
                            "type": "MARKET",
                            "instrument": instrument,
                            "units": str(units),
                            "positionFill": "REDUCE_ONLY",
                        }
                    },
                )
            )
            logger.info(f"Closed {instrument}")
            return True
        except Exception as e:
            logger.error(f"Close failed for {instrument}: {e}")
            return False

    # ========== Close OUR Position — TAG matched ONLY (SAFE by default) ==========
    def close_my_position(
        self,
        instrument: str,
        tag_prefix: str = "FXBOT-AUTO",
        no_tag_fallback: bool = False,
    ):
        """Close OUR open Position — TAG matched by default (SAFE).
        • no_tag_fallback=False (DEFAULT): TAG match ONLY → SAFE STOP if no match.
        • no_tag_fallback=True: TAG match → else FIRST trade as fallback.

        Returns: (ok, trade_id_closed or None)
        """
        my_pos = self.get_my_position(instrument, tag_prefix, no_tag_fallback)
        if not my_pos:
            logger.info(f"⚠️ No closeable position for {instrument} — nothing to close")
            return False, None

        trade_id = my_pos["trade_id"]
        side = my_pos["side"]
        units = my_pos["units"]
        logger.info(
            f"🎯 Closing: TradeID={trade_id} {side} {units} units TAG={my_pos['tag']}"
        )

        close_units = -units if side == "BUY" else units

        try:
            self.api.request(
                OrderCreate(
                    accountID=self.account_id,
                    data={
                        "order": {
                            "type": "MARKET",
                            "instrument": instrument,
                            "units": str(close_units),
                            "positionFill": "REDUCE_ONLY",
                        }
                    },
                )
            )
            logger.info(f"✅ CLOSED: {instrument} TradeID={trade_id}")
            return True, trade_id
        except Exception as e:
            logger.error(f"❌ close_my_position failed: {e}")
            return False, None

    # ========== Close ALL — ANY position regardless of TAG ==========
    def close_all_positions(self, instrument: str) -> bool:
        """Close EVERY position for this instrument — ANY TAG, ANYONE'S.
        ⚠️ DANGEROUS — closes ALL positions! Use only when you mean it!
        """
        pos = self.get_open_position(instrument)
        if not pos:
            logger.info(f"No position to close: {instrument}")
            return False

        close_units = -pos["units"] if pos["side"] == "long" else pos["units"]

        try:
            self.api.request(
                OrderCreate(
                    accountID=self.account_id,
                    data={
                        "order": {
                            "type": "MARKET",
                            "instrument": instrument,
                            "units": str(close_units),
                            "positionFill": "REDUCE_ONLY",
                        }
                    },
                )
            )
            logger.warning(f"⚠️  CLOSED ALL POSITIONS for {instrument} — not filtered by TAG!")
            return True
        except Exception as e:
            logger.error(f"❌ close_all_positions failed: {e}")
            return False

    # ========== Update Position — ONLY by trade_id (single specific) ==========
    def update_position(
        self,
        trade_id: str,
        instrument: str,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
    ) -> bool:
        """Update SL/TP — ONLY the ONE Position with this trade_id.
        ⚠️ Must specify trade_id — will NEVER update multiple positions!
        """
        data = {}
        if sl_price is not None:
            data["stopLoss"] = {
                "price": self.format_price(sl_price, instrument),
                "timeInForce": "GTC",
            }
        if tp_price is not None:
            data["takeProfit"] = {
                "price": self.format_price(tp_price, instrument),
                "timeInForce": "GTC",
            }
        if not data:
            logger.warning("Nothing to update: SL/TP both empty")
            return False

        try:
            self.api.request(TradeCRCDO(self.account_id, trade_id, data=data))
            logger.info(f"✅ UPDATED TradeID={trade_id} → SL={sl_price} TP={tp_price}")
            return True
        except Exception as e:
            logger.error(f"❌ update_position failed: {e}")
            return False

    # ── 静态工具 ─────────────────────────────────────────────────────────

    @staticmethod
    def _price_decimals(pair: str) -> int:
        """Return correct decimal places for OANDA pricing."""
        return 3 if "JPY" in pair.upper() else 5

    @staticmethod
    def pip_size(pair: str) -> float:
        """Return 1 pip value for pair."""
        return 0.01 if "JPY" in pair.upper() else 0.0001

    @staticmethod
    def format_price(price, instrument: str) -> str:
        """Format price string per instrument decimal (3 for JPY, 5 for others)."""
        try:
            n = float(price)
            return f"{n:.3f}" if "JPY" in instrument.upper() else f"{n:.5f}"
        except (TypeError, ValueError):
            return str(price)

    def __repr__(self):
        return f"OandaClient(env={self.settings.OANDA_ENV}, account={self.account_id})"