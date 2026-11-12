# cbBTC 24h race bot

A long-only 1-minute paper-trading bot for the make.fun bounty
[Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261112-1439)
(`btc-race-24h-20261112-1439`). It starts with $1,000 of paper USDC and trades
Coinbase Wrapped BTC (cbBTC) against the official bars-replay market model
(4 bps fee, 2 bps slippage, plus pool impact).

## Strategy

After a very small early ticket trade (so the run always has at least one
fill), the bot waits for a 30-minute opening range, then buys once if the
close breaks that range high. It trails the close by 80 bps, tightens to a
latched 50 bps trail once the trade is 100 bps in profit, and also exits if
price falls back through the range low. It does not re-enter. A 10% equity
drawdown stop ends trading, well inside the race's 25% cap.

The idea is to take one confirmed session move, pay the round-trip cost only
once, and sit in cash when there is no breakout — rather than churn 1-minute
signals against a 26 bps all-in cost.

## Run

The official entrypoint is `main.py` (Python 3.13, standard library only, plus
the vendored kit shim in `vendor/makefun_bars.py`). The grader runs:

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

It reads one JSON line per minute on stdin (`hello`, then `batch`, then `done`)
and writes one reply per batch on stdout, per `agent-fun/bars-replay/v1`.

Grade it locally from the unpacked kit (Docker is required for a Python bot on
the official `grade-local` command; `--driver process` runs Node bots only):

```sh
node cli/makefun.mjs grade-local --kit . --bot /path/to/this/repo --driver docker
```

## License

MIT License. Copyright (c) 2026 ajrony.
