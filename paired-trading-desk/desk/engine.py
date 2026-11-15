"""One paper cycle.

Vibe-Trading's job is the backtest gate. The AI Hedge Fund's job is the vote.
Hummingbot and pumpfun-bonkfun-bot own the fills for their venues. Orders are
decided on bar T and filled on bar T+1.
"""

from __future__ import annotations

from pathlib import Path

from desk.config import Config
from desk.models import Bar, Decision, Position, ResearchCard, Vote


def sma(values: list[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def _signal(fast: float | None, slow: float | None) -> int:
    if fast is None or slow is None or slow == 0:
        return 0
    if fast > slow * 1.0001:
        return 1
    if fast < slow * 0.9999:
        return -1
    return 0


def research_symbol(bars: list[Bar], cfg: Config, symbol: str, venue: str) -> ResearchCard:
    closes = [bar.close for bar in bars]
    fast = sma(closes, cfg.fast)
    slow = sma(closes, cfg.slow)
    signal = _signal(fast, slow)
    buy_hold = closes[-1] / closes[0] - 1
    curve = _strategy_equity(closes, cfg.fast, cfg.slow, cfg.fee_usd)
    total = curve[-1] - 1
    drawdown = max_drawdown(curve)
    passed = True
    reason = "lolos gerbang backtest"
    if len(closes) < cfg.slow + 2:
        passed, reason = False, "bar belum cukup"
    elif signal != 1:
        passed, reason = False, "sinyal tidak long"
    elif total < cfg.min_total_return:
        passed, reason = False, "imbal hasil di bawah batas"
    elif drawdown > cfg.max_drawdown:
        passed, reason = False, "drawdown melewati batas"
    return ResearchCard(
        symbol=symbol,
        venue=venue,
        bars=len(closes),
        total_return=total,
        buy_hold_return=buy_hold,
        excess_return=total - buy_hold,
        max_drawdown=drawdown,
        signal=signal,
        fast=fast,
        slow=slow,
        passed=passed,
        reason=reason,
    )


def _strategy_equity(closes: list[float], fast_n: int, slow_n: int, fee: float) -> list[float]:
    """Long/flat SMA book. Decision at close T, fill at close T+1, start at 1.0 cash."""
    cash = 1.0
    shares = 0.0
    pending: int | None = None
    curve: list[float] = []
    for index, price in enumerate(closes):
        if pending is not None:
            equity_now = cash + shares * price
            want_long = pending == 1
            held = shares * price > 1e-12
            if want_long and not held and equity_now > 0:
                notional = equity_now
                fee_paid = notional * fee
                spend = min(notional, cash / (1 + fee) if fee else cash)
                fee_paid = spend * fee
                shares += spend / price
                cash -= spend + fee_paid
            elif not want_long and held:
                proceeds = shares * price
                fee_paid = proceeds * fee
                cash += proceeds - fee_paid
                shares = 0.0
            pending = None
        curve.append(cash + shares * price)
        fast = sma(closes[: index + 1], fast_n)
        slow = sma(closes[: index + 1], slow_n)
        if index + 1 < len(closes):
            pending = 1 if _signal(fast, slow) == 1 else 0
    return curve


def committee(card: ResearchCard, closes: list[float], cfg: Config) -> Decision:
    fast = card.fast or 0.0
    slow = card.slow or 0.0
    price = closes[-1]
    votes = [
        _trend_vote(card.signal),
        _momentum_vote(closes, cfg.fast),
        _stretch_vote(price, slow),
        _drawdown_vote(closes),
    ]
    score = sum(vote.value for vote in votes) / len(votes)
    if score >= cfg.min_vote:
        action = "buy"
        weight = min(cfg.max_weight, score * cfg.max_weight)
        reason = "suara komite cukup untuk menambah"
    elif score <= -cfg.min_vote:
        action = "sell"
        weight = 0.0
        reason = "suara komite cukup untuk melepas"
    else:
        action = "hold"
        weight = 0.0
        reason = "suara di dalam pita netral"
    return Decision(card.symbol, card.venue, action, score, weight, reason, votes)


def _trend_vote(signal: int) -> Vote:
    return Vote("trend", float(signal), "arah rata-rata cepat terhadap lambat")


def _momentum_vote(closes: list[float], window: int) -> Vote:
    if len(closes) <= window or closes[-window - 1] == 0:
        return Vote("momentum", 0.0, "jendela belum penuh")
    change = closes[-1] / closes[-window - 1] - 1
    value = max(-1.0, min(1.0, change / 0.04))
    return Vote("momentum", value, f"perubahan {window} bar {change:.2%}")


def _stretch_vote(price: float, slow: float) -> Vote:
    if slow <= 0:
        return Vote("stretch", 0.0, "rata-rata lambat kosong")
    stretch = price / slow - 1
    if stretch > 0.05:
        value = -max(0.0, min(1.0, (stretch - 0.05) / 0.10))
    elif stretch < -0.05:
        value = max(0.0, min(1.0, (-0.05 - stretch) / 0.10))
    else:
        value = 0.0
    return Vote("stretch", value, f"jarak harga ke rata-rata lambat {stretch:.2%}")


def _drawdown_vote(closes: list[float]) -> Vote:
    peak = max(closes)
    drawdown = (peak - closes[-1]) / peak if peak else 0.0
    if drawdown >= 0.25:
        value = -1.0
    elif drawdown <= 0.02:
        value = 0.25
    else:
        value = 0.25 + (drawdown - 0.02) * ((-1.0 - 0.25) / (0.25 - 0.02))
    return Vote("drawdown", value, f"turun {drawdown:.2%} dari puncak jendela")


class Book:
    def __init__(self, cash_usd: float, cash_sol: float) -> None:
        self.cash_usd = cash_usd
        self.cash_sol = cash_sol
        self.positions: dict[str, Position] = {}
        self.peak_equity = cash_usd

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash_usd
        for position in self.positions.values():
            if position.quote == "USD":
                total += position.qty * prices.get(position.symbol, position.avg_price)
        return total

    def gross_usd(self, prices: dict[str, float]) -> float:
        total = 0.0
        for position in self.positions.values():
            if position.quote == "USD":
                total += abs(position.qty * prices.get(position.symbol, position.avg_price))
        return total


def _kill_reason(state_dir: Path) -> str | None:
    path = state_dir / "KILL"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or "halt"


def launch_return(relative: float, fee: float) -> float:
    """SOL return after the entry fee and the exit fee, versus the SOL spent."""
    return relative * (1 - fee) ** 2 - 1


def plan_launch_exit(path: list[float], fee: float, take_profit: float, stop_loss: float, max_hold: int) -> tuple[str, float, int]:
    last_relative = path[-1] if path else 1.0
    for step, relative in enumerate(path):
        if step == 0:
            continue
        change = launch_return(relative, fee)
        if change >= take_profit:
            return "take_profit", relative, step
        if change <= -stop_loss:
            return "stop_loss", relative, step
        if step >= max_hold:
            return "time", relative, step
    return "mark", last_relative, max(0, len(path) - 1)


def run_cycle(
    cfg: Config,
    series: dict[str, list[Bar]],
    launches: list[dict],
    state_dir: Path,
) -> dict:
    book = Book(cfg.capital_usd, cfg.capital_sol)
    killed = _kill_reason(state_dir)
    fills: list[dict] = []
    curve: list[dict] = []
    last_cards: dict[str, dict] = {}
    last_decisions: dict[str, dict] = {}
    scores: dict[str, float] = {item.symbol: 0.0 for item in cfg.universe}
    pending: list[dict] = []
    halted_by_drawdown = False
    length = max(len(bars) for bars in series.values())
    symbols = [item.symbol for item in cfg.universe if item.symbol in series]

    for index in range(length):
        prices = {
            symbol: series[symbol][index].close
            for symbol in symbols
            if index < len(series[symbol])
        }
        if killed or halted_by_drawdown:
            pending = []
        else:
            still: list[dict] = []
            for order in pending:
                if order["fill_index"] != index:
                    still.append(order)
                    continue
                fill = _fill_order(book, order, prices, cfg)
                if fill:
                    fills.append(fill)
            pending = still
        equity = book.equity(prices)
        book.peak_equity = max(book.peak_equity, equity)
        if book.peak_equity > 0:
            portfolio_dd = (book.peak_equity - equity) / book.peak_equity
            if portfolio_dd >= cfg.portfolio_drawdown_halt:
                halted_by_drawdown = True
                pending = []
        curve.append({"t": index, "date": _date_at(series, symbols, index), "equity": round(equity, 4)})

        for symbol in symbols:
            bars = series[symbol]
            if index >= len(bars):
                continue
            instrument = cfg.instrument(symbol)
            card = research_symbol(bars[: index + 1], cfg, symbol, instrument.venue)
            last_cards[symbol] = _card_dict(card)
            if not card.passed or killed or halted_by_drawdown:
                scores[symbol] = 0.0
                continue
            decision = committee(card, [bar.close for bar in bars[: index + 1]], cfg)
            scores[symbol] = decision.score
            last_decisions[symbol] = _decision_dict(decision)
            if decision.action == "hold" or index + 1 >= len(bars):
                continue
            pending.append(
                {
                    "symbol": symbol,
                    "venue": instrument.venue,
                    "target_weight": decision.target_weight,
                    "fill_index": index + 1,
                    "score": decision.score,
                    "action": decision.action,
                }
            )

    launch_rows = _run_launches(cfg, book, launches, scores, killed, halted_by_drawdown)
    report = {
        "mode": "paper",
        "killed": killed,
        "drawdown_halt": halted_by_drawdown,
        "cash_usd": round(book.cash_usd, 4),
        "cash_sol": round(book.cash_sol, 8),
        "equity_usd": curve[-1]["equity"] if curve else cfg.capital_usd,
        "peak_equity_usd": round(book.peak_equity, 4),
        "positions": [_position_dict(item, _last_price(series, item.symbol)) for item in book.positions.values()],
        "research": last_cards,
        "decisions": last_decisions,
        "fills": fills,
        "launches": launch_rows,
        "curve": curve,
        "scores": {key: round(value, 4) for key, value in scores.items()},
    }
    return report


def _fill_order(book: Book, order: dict, prices: dict[str, float], cfg: Config) -> dict | None:
    price = prices.get(order["symbol"])
    if price is None or price <= 0:
        return None
    equity = book.equity(prices)
    current = book.positions.get(order["symbol"])
    current_notional = current.qty * price if current and current.quote == "USD" else 0.0
    target = order["target_weight"] * equity
    delta = target - current_notional
    if abs(delta) < cfg.rebalance_band_usd:
        return None
    delta = max(-cfg.max_order_usd, min(cfg.max_order_usd, delta))
    gross_without = book.gross_usd(prices) - abs(current_notional)
    room = cfg.max_gross_usd - gross_without
    if room <= 0:
        return None
    if abs(current_notional + delta) > room and abs(delta) > 0:
        # Keep the position inside the gross cap.
        allowed = max(0.0, room)
        desired = current_notional + delta
        desired = max(-allowed, min(allowed, desired))
        delta = desired - current_notional
    if delta > 0:
        spend = delta
        if spend * (1 + cfg.fee_usd) > book.cash_usd:
            spend = book.cash_usd / (1 + cfg.fee_usd)
        if spend <= 1e-8:
            return None
        fee = spend * cfg.fee_usd
        qty = spend / price
        _add_long(book, order["symbol"], order["venue"], qty, price)
        book.cash_usd -= spend + fee
        return _fill_dict(order, "buy", qty, price, spend, fee)
    sell_notional = min(abs(delta), current_notional)
    if sell_notional <= 1e-8 or current is None:
        return None
    qty = sell_notional / price
    fee = sell_notional * cfg.fee_usd
    current.qty -= qty
    if current.qty <= 1e-10:
        book.positions.pop(order["symbol"], None)
    book.cash_usd += sell_notional - fee
    return _fill_dict(order, "sell", qty, price, sell_notional, fee)


def _add_long(book: Book, symbol: str, venue: str, qty: float, price: float) -> None:
    held = book.positions.get(symbol)
    if held is None:
        book.positions[symbol] = Position(symbol, venue, qty, price, "USD")
        return
    total = held.qty + qty
    held.avg_price = (held.avg_price * held.qty + price * qty) / total
    held.qty = total


def _run_launches(
    cfg: Config,
    book: Book,
    launches: list[dict],
    scores: dict[str, float],
    killed: str | None,
    halted: bool,
) -> list[dict]:
    rows: list[dict] = []
    risk_on = scores.get(cfg.risk_on_symbol, 0.0) >= cfg.min_vote
    open_count = 0
    for launch in launches:
        row = {
            "mint": launch["mint"],
            "symbol": launch["symbol"],
            "platform": launch["platform"],
            "venue": "pumpfun",
            "status": "skipped",
            "reason": "",
            "pnl_sol": 0.0,
        }
        if not cfg.launch_enabled:
            row["reason"] = "jalur launch dimatikan"
        elif killed:
            row["reason"] = "kill switch"
        elif halted:
            row["reason"] = "drawdown portofolio"
        elif not risk_on:
            row["reason"] = "komite kripto tidak risk-on"
        elif launch["platform"] not in cfg.launch_platforms:
            row["reason"] = "platform di luar daftar"
        elif float(launch["age_seconds"]) > cfg.launch_max_age:
            row["reason"] = "umur token melewati batas"
        elif open_count >= cfg.max_open_launches:
            row["reason"] = "slot posisi penuh"
        elif book.cash_sol < cfg.launch_buy_sol:
            row["reason"] = "SOL paper tidak cukup"
        else:
            reason, relative, step = plan_launch_exit(
                list(launch["path"]),
                cfg.fee_sol,
                cfg.launch_take_profit,
                cfg.launch_stop_loss,
                cfg.launch_max_hold,
            )
            budget = cfg.launch_buy_sol
            price = float(launch["price_sol"])
            tokens = budget * (1 - cfg.fee_sol) / price
            exit_price = price * relative
            proceeds = tokens * exit_price * (1 - cfg.fee_sol)
            pnl = proceeds - budget
            book.cash_sol += pnl
            open_count += 1
            row.update(
                {
                    "status": "closed",
                    "reason": reason,
                    "steps": step,
                    "entry_sol": price,
                    "exit_sol": exit_price,
                    "pnl_sol": round(pnl, 8),
                }
            )
        rows.append(row)
    return rows


def _fill_dict(order: dict, side: str, qty: float, price: float, notional: float, fee: float) -> dict:
    return {
        "venue": order["venue"],
        "symbol": order["symbol"],
        "side": side,
        "qty": round(qty, 8),
        "price": round(price, 8),
        "notional": round(notional, 4),
        "fee": round(fee, 4),
        "action": order["action"],
        "score": round(order["score"], 4),
    }


def _card_dict(card: ResearchCard) -> dict:
    return {
        "symbol": card.symbol,
        "venue": card.venue,
        "bars": card.bars,
        "total_return": round(card.total_return, 4),
        "buy_hold_return": round(card.buy_hold_return, 4),
        "excess_return": round(card.excess_return, 4),
        "max_drawdown": round(card.max_drawdown, 4),
        "signal": card.signal,
        "passed": card.passed,
        "reason": card.reason,
    }


def _decision_dict(decision: Decision) -> dict:
    return {
        "symbol": decision.symbol,
        "venue": decision.venue,
        "action": decision.action,
        "score": round(decision.score, 4),
        "target_weight": round(decision.target_weight, 4),
        "reason": decision.reason,
        "votes": [
            {"agent": vote.agent, "value": round(vote.value, 4), "note": vote.note}
            for vote in decision.votes
        ],
    }


def _position_dict(position: Position, price: float) -> dict:
    return {
        "symbol": position.symbol,
        "venue": position.venue,
        "qty": round(position.qty, 8),
        "avg_price": round(position.avg_price, 6),
        "last": round(price, 6),
        "quote": position.quote,
        "market_value": round(position.qty * price, 4),
    }


def _last_price(series: dict[str, list[Bar]], symbol: str) -> float:
    bars = series.get(symbol)
    if not bars:
        return 0.0
    return bars[-1].close


def _date_at(series: dict[str, list[Bar]], symbols: list[str], index: int) -> str:
    for symbol in symbols:
        bars = series[symbol]
        if index < len(bars):
            return bars[index].date
    return str(index)
