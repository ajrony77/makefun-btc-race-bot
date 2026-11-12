"""cbBTC 1-minute paper-trading bot for make.fun bounty btc-race-24h-20261112-1439.

Strategy (long only, at most one main position):
  1. A tiny "ticket" round-trip in the first few minutes so the race guardrail
     of at least one fill is met even if no later setup appears.
  2. After the first RANGE_BARS minutes, take a single opening-range breakout:
     buy when the close breaks the range high. This is a standard session-open
     rule; the window start is the session.
  3. Risk: trail the close by TRAIL_BPS, tighten to RATCHET_TRAIL_BPS once
     unrealized profit has reached RATCHET_ARM_BPS (the tighter trail latches),
     and sell if the close falls back through the range low. A hard equity
     drawdown stop ends trading if equity drops STOP_DD_BPS from its peak.
  4. No re-entry after the main trade exits. Fees, slippage and impact are
     about 26 bps on a full-size round trip, so the bot avoids churn.

Python 3.13 standard library only. Deterministic: same bars, same orders.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
BPS = makefun_bars.BPS

# Opening range: first 30 present 1-minute bars of the window.
RANGE_BARS = 30
# Initial trailing stop, wide enough to live through a typical intra-trend dip.
TRAIL_BPS = 80
# Once the trade is up this far, latch a tighter trail so we keep more of a run.
RATCHET_ARM_BPS = 100
RATCHET_TRAIL_BPS = 50
# Fraction of cash to spend on the main buy (leaves a little room under the cap).
SIZE_BPS = 9200
MAX_SLIPPAGE_BPS = 100
# Flatten and stand aside if equity falls this far from its peak (well under 25%).
STOP_DD_BPS = 1000
# Tiny early fill so a window with no breakout still has at least one trade.
TICKET_NOTIONAL = 25_000_000  # 25 USDC
TICKET_BUY_SEQ = 2
TICKET_SELL_SEQ = 6
MIN_HOLD_BARS = 5


class Bot:
    def __init__(self):
        self.range_high = None
        self.range_low = None
        self.present = 0
        self.peak_close = 0
        self.peak_equity = None
        self.halted = False
        self.entry_seq = None
        self.ticket_open = False
        self.ticket_done = False
        self.ever_main = False
        self.ratcheted = False
        self._range_highs = []
        self._range_lows = []

    def on_hello(self, state):
        self.peak_equity = state.equity

    def on_batch(self, state, batch):
        if self.peak_equity is None or state.equity > self.peak_equity:
            self.peak_equity = state.equity
        if self.peak_equity > 0 and (self.peak_equity - state.equity) * BPS // self.peak_equity >= STOP_DD_BPS:
            self.halted = True

        bar = None
        for b in batch["bars"]:
            if b["symbol"] == SYMBOL:
                bar = b
                self.present += 1
                break

        held = state.positions.get(SYMBOL)
        qty = held.qty if held else 0

        if state.warming_up:
            return []

        # Ticket: close first, so it is always done before the range can break.
        if self.ticket_open and qty > 0 and state.seq >= TICKET_SELL_SEQ:
            self.ticket_open = False
            self.ticket_done = True
            return [self._sell(qty)]

        if self.halted:
            return [self._sell(qty)] if qty > 0 else []

        if (
            not self.ticket_done
            and not self.ticket_open
            and qty == 0
            and bar is not None
            and state.seq == TICKET_BUY_SEQ
            and not self.ever_main
        ):
            notional = min(TICKET_NOTIONAL, state.cash)
            if notional >= int(state.hello["fees"]["min_notional_quote_units"]):
                self.ticket_open = True
                return [self._buy(notional)]
            return []

        if bar is None:
            return []

        close = int(bar["c"])
        high = int(bar["h"])
        low = int(bar["l"])

        if self.range_high is None:
            self._range_highs.append(high)
            self._range_lows.append(low)
            if len(self._range_highs) < RANGE_BARS:
                return []
            self.range_high = max(self._range_highs[:RANGE_BARS])
            self.range_low = min(self._range_lows[:RANGE_BARS])
            # The bar that completes the range is not a breakout bar.
            return []

        if qty > 0 and not self.ticket_open:
            if close > self.peak_close:
                self.peak_close = close
            held_long_enough = self.entry_seq is not None and (state.seq - self.entry_seq) >= MIN_HOLD_BARS
            if held is not None and not self.ratcheted and held.cost > 0:
                value = state.value(SYMBOL, held.qty, close)
                if value * BPS >= held.cost * (BPS + RATCHET_ARM_BPS):
                    self.ratcheted = True
            trail = RATCHET_TRAIL_BPS if self.ratcheted else TRAIL_BPS
            trail_hit = self.peak_close > 0 and close * BPS <= self.peak_close * (BPS - trail)
            range_hit = self.range_low is not None and close <= self.range_low
            if held_long_enough and (trail_hit or range_hit):
                self.entry_seq = None
                self.ratcheted = False
                return [self._sell(qty)]
            return []

        if qty > 0 or self.ticket_open or self.ever_main:
            return []
        if close < self.range_high:
            return []

        notional = state.cash * SIZE_BPS // BPS
        room = state.weight_room(SYMBOL)
        if room < notional:
            notional = room
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if notional < min_notional:
            return []
        self.peak_close = close
        self.entry_seq = state.seq
        self.ever_main = True
        self.ratcheted = False
        return [self._buy(notional)]

    def _buy(self, notional):
        return {
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }

    def _sell(self, qty):
        return {
            "side": "sell",
            "symbol": SYMBOL,
            "qty": qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }


BOT = Bot()
makefun_bars.run(BOT.on_batch, on_hello=BOT.on_hello)
