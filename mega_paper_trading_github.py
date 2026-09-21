"""
PAPER TRADING (MEGA) - Versione automatica per GitHub Actions
========================================================================
AGGIORNAMENTO: gestione del rischio con PRESA DI PROFITTO PARZIALE,
validata con backtest su 25 simboli/8 anni (1.815 trade attuale vs
1.816 trade con presa parziale, entrambi statisticamente significativi).

Meccanismo (sostituisce il trailing stop continuo precedente):
1. Stop fisso all'apertura (non si muove)
2. Se il prezzo raggiunge +1R: chiude META' posizione, sposta lo stop
   della meta' rimanente A PAREGGIO (fisso, non trailing)
3. La meta' rimanente prosegue verso il target originale o torna al
   pareggio (mai piu' in perdita da quel momento in poi)
"""

import csv
import json
import os
from datetime import datetime, timezone

import config
import strategy_core
from news_filter import check_important_news
from telegram_notify import send_telegram_message

STATE_FOLDER = "."
STATE_PATH = f"{STATE_FOLDER}/paper_state.json"
EQUITY_LOG_PATH = f"{STATE_FOLDER}/paper_equity_log.csv"
DECISION_LOG_PATH = f"{STATE_FOLDER}/paper_decision_log.csv"

NOTIONAL_CAPITAL_START = 1_000.0
PARTIAL_TP_R = 1.0

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"capital": NOTIONAL_CAPITAL_START, "positions": {}}
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def fetch_recent_candles(symbol, lookback=250):
    import yfinance as yf
    base_currency = symbol.split("/")[0]
    yf_symbol = f"{base_currency}-USD"
    df = yf.Ticker(yf_symbol).history(period="2y", interval="1d")

    candles = []
    for timestamp, row in df.iterrows():
        if row[["Open", "High", "Low", "Close"]].isnull().any():
            continue
        candles.append([
            int(timestamp.timestamp() * 1000),
            float(row["Open"]), float(row["High"]),
            float(row["Low"]), float(row["Close"]),
            float(row.get("Volume", 0) or 0),
        ])
    return candles[-lookback:]


def log_equity(state):
    file_exists = os.path.exists(EQUITY_LOG_PATH)
    with open(EQUITY_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp_utc", "capital", "open_positions"])
        open_count = sum(1 for v in state["positions"].values() if v is not None)
        writer.writerow([datetime.now(timezone.utc).isoformat(), f"{state['capital']:.2f}", open_count])


def log_decision(symbol, decision, executed, notes=""):
    file_exists = os.path.exists(DECISION_LOG_PATH)
    with open(DECISION_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp_utc", "symbol", "signal", "confirmations",
                              "price", "stop_price", "take_profit_price", "executed", "notes"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(), symbol, decision.signal,
            decision.confirmations, decision.price, decision.stop_price,
            decision.take_profit_price, executed, notes
        ])


def check_position(position, current_price):
    side = position["side"]
    entry = position["entry_price"]
    stop = position["stop_price"]
    target = position["take_profit_price"]
    initial_risk_distance = position["initial_risk_distance"]
    risk_amount = position["risk_amount"]

    hit_stop = (current_price <= stop) if side == "BUY" else (current_price >= stop)
    hit_target = (current_price >= target) if side == "BUY" else (current_price <= target)

    if not position.get("partial_taken", False):
        pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
        current_r = pnl_distance / initial_risk_distance if initial_risk_distance != 0 else 0

        if hit_stop:
            pnl = risk_amount * -1.0
            return {"action": "close", "pnl": pnl, "reason": "STOP-LOSS", "r_multiple": -1.0}

        if hit_target:
            reward_distance = abs(target - entry)
            r_multiple = reward_distance / initial_risk_distance if initial_risk_distance != 0 else 0
            pnl = risk_amount * r_multiple
            return {"action": "close", "pnl": pnl, "reason": "TAKE-PROFIT", "r_multiple": r_multiple}

        if current_r >= PARTIAL_TP_R:
            partial_pnl = risk_amount * PARTIAL_TP_R * 0.5
            return {"action": "partial", "pnl": partial_pnl, "new_stop": entry}

        return None

    else:
        hit_breakeven = (current_price <= stop) if side == "BUY" else (current_price >= stop)
        if hit_breakeven:
            pnl = 0.0
            total_r = position.get("partial_r_locked", 0.0)
            return {"action": "close", "pnl": pnl, "reason": "PAREGGIO (dopo presa parziale)", "r_multiple": total_r}

        if hit_target:
            reward_distance = abs(target - entry)
            remaining_r = (reward_distance / initial_risk_distance if initial_risk_distance != 0 else 0) * 0.5
            pnl = risk_amount * remaining_r
            total_r = position.get("partial_r_locked", 0.0) + remaining_r
            return {"action": "close", "pnl": pnl, "reason": "TAKE-PROFIT (meta' residua)", "r_multiple": total_r}

        return None


def run_daily_check():
    state = load_state()
    capital = state["capital"]
    positions = state["positions"]

    today = datetime.now(timezone.utc).date()
    capital_at_start = capital

    new_lines = []
    closed_lines = []
    partial_lines = []
    open_lines = []
    news_lines = []

    print("=" * 70)
    print("THE JACKAL AI BOT - PAPER TRADING (MEGA, con presa parziale)")
    print(f"Data controllo: {today}")
    print(f"Capitale simulato attuale: {capital:,.2f}")
    print("=" * 70 + "\n")

    for symbol in config.SYMBOLS:
        try:
            candles = fetch_recent_candles(symbol)
        except Exception as e:
            print(f"[{symbol}] Errore nel recupero dati: {e}")
            continue

        if not candles:
            continue

        current_price = candles[-1][4]
        position = positions.get(symbol)

        if position is not None:
            result = check_position(position, current_price)

            if result is None:
                pnl_distance = (current_price - position["entry_price"]) if position["side"] == "BUY" else (position["entry_price"] - current_price)
                current_r = pnl_distance / position["initial_risk_distance"] if position["initial_risk_distance"] != 0 else 0
                status = "post-parziale" if position.get("partial_taken") else "in corso"
                line = (f"[{symbol}] {position['side']} ({status}) | prezzo: {current_price:.4f} | "
                        f"entrata: {position['entry_price']:.4f} | stop: {position['stop_price']:.4f} | "
                        f"target: {position['take_profit_price']:.4f} | {current_r:+.2f}R")
                print(line)
                open_lines.append(line)

            elif result["action"] == "partial":
                capital += result["pnl"]
                position["partial_taken"] = True
                position["partial_r_locked"] = PARTIAL_TP_R * 0.5
                position["stop_price"] = result["new_stop"]
                line = (f"🟡 [{symbol}] PRESA PARZIALE (+{PARTIAL_TP_R}R)\n"
                        f"   Meta' posizione chiusa: +{result['pnl']:.2f} | Nuovo capitale: {capital:,.2f}\n"
                        f"   Stop meta' rimanente spostato a pareggio: {result['new_stop']:.4f}")
                print(line)
                partial_lines.append(line)

            elif result["action"] == "close":
                capital += result["pnl"]
                emoji = "🟢" if result["pnl"] >= 0 else "🔴"
                line = (f"{emoji} [{symbol}] {result['reason']}\n"
                        f"   P&L: {result['pnl']:+.2f} ({result['r_multiple']:+.2f}R totale) | Nuovo capitale: {capital:,.2f}")
                print(line)
                closed_lines.append(line)
                positions[symbol] = None
            continue

        decision = strategy_core.evaluate(candles)
        executed = False

        if decision.signal in ("BUY", "SELL"):
            open_count = sum(1 for v in positions.values() if v is not None)
            if open_count < config.MAX_CONCURRENT_POSITIONS:
                risk_amount = capital * (config.RISK_PER_TRADE_PCT / 100) * decision.volatility_scale
                currency_code = symbol.split("/")[0]

                news = check_important_news(currency_code)
                if news:
                    news_text = f"⚠️ [{symbol}] {len(news)} notizia/e rilevante/i:\n" + "\n".join(
                        f"   - {item['title']}" for item in news)
                    print(news_text)
                    news_lines.append(news_text)

                positions[symbol] = {
                    "side": decision.signal,
                    "entry_price": decision.price,
                    "stop_price": decision.stop_price,
                    "take_profit_price": decision.take_profit_price,
                    "risk_amount": risk_amount,
                    "initial_risk_distance": abs(decision.price - decision.stop_price),
                    "partial_taken": False,
                    "partial_r_locked": 0.0,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                }
                executed = True
                emoji = "🟢" if decision.signal == "BUY" else "🔴"
                line = (f"{emoji} [{symbol}] NUOVA {decision.signal} @ {decision.price:.4f}\n"
                        f"   stop: {decision.stop_price:.4f} | target: {decision.take_profit_price:.4f} | "
                        f"conferme: {decision.confirmations}/11 | rischio: {risk_amount:.2f}")
                print(line)
                new_lines.append(line)

        log_decision(symbol, decision, executed)

    state["capital"] = capital
    state["positions"] = positions
    save_state(state)
    log_equity(state)

    open_count = sum(1 for v in positions.values() if v is not None)

    message_parts = [
        "THE JACKAL AI BOT - MEGA",
        f"Data: {today}",
        f"Capitale: {capital_at_start:,.2f} -> {capital:,.2f} ({(capital / NOTIONAL_CAPITAL_START - 1) * 100:+.2f}% dal via)",
        "",
    ]

    if new_lines:
        message_parts.append("=== NUOVE POSIZIONI ===")
        message_parts.extend(new_lines)
        message_parts.append("")

    if partial_lines:
        message_parts.append("=== PRESE DI PROFITTO PARZIALI ===")
        message_parts.extend(partial_lines)
        message_parts.append("")

    if closed_lines:
        message_parts.append("=== POSIZIONI CHIUSE ===")
        message_parts.extend(closed_lines)
        message_parts.append("")

    if news_lines:
        message_parts.append("=== NOTIZIE RILEVANTI ===")
        message_parts.extend(news_lines)
        message_parts.append("")

    if open_lines:
        message_parts.append(f"=== POSIZIONI ANCORA APERTE ({open_count}) ===")
        message_parts.extend(open_lines)
        message_parts.append("")

    if not new_lines and not closed_lines and not open_lines and not partial_lines:
        message_parts.append("Nessuna posizione aperta e nessun movimento oggi.")

    message = "\n".join(message_parts)
    print("\n" + "=" * 70)
    print(message)
    print("=" * 70)

    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    run_daily_check()
