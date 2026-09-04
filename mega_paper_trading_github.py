"""
PAPER TRADING (MEGA) - Versione automatica per GitHub Actions
========================================================================
Identica alla versione Colab nella logica, ma pensata per girare da
sola, una volta al giorno, senza intervento umano:

- Lo stato (capitale, posizioni) viene salvato in file nel repository
  stesso, e GitHub Actions li salva automaticamente (commit) dopo
  ogni esecuzione - cosi' il giorno dopo si riparte da dove si era
  arrivati.
- Il risultato del controllo viene mandato come messaggio Telegram,
  cosi' lo vedi sul telefono senza dover aprire nulla.

Le chiavi (token Telegram, chat id) vengono lette da variabili
d'ambiente, impostate come "secrets" su GitHub - non sono mai scritte
nel codice.
"""

import csv
import json
import os
from datetime import datetime, timezone

import config
import strategy_core
from news_filter import print_news_warning
from telegram_notify import send_telegram_message

STATE_FOLDER = "."
STATE_PATH = f"{STATE_FOLDER}/paper_state.json"
EQUITY_LOG_PATH = f"{STATE_FOLDER}/paper_equity_log.csv"
DECISION_LOG_PATH = f"{STATE_FOLDER}/paper_decision_log.csv"

NOTIONAL_CAPITAL_START = 10_000.0

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


def run_daily_check():
    state = load_state()
    capital = state["capital"]
    positions = state["positions"]

    today = datetime.now(timezone.utc).date()
    summary_lines = []
    summary_lines.append(f"THE JACKAL AI BOT - MEGA")
    summary_lines.append(f"Data: {today}")
    summary_lines.append(f"Capitale iniziale oggi: {capital:,.2f}")
    summary_lines.append("")

    print("=" * 70)
    print("THE JACKAL AI BOT - PAPER TRADING (VERSIONE MEGA, automatico)")
    print(f"Data controllo: {today}")
    print(f"Capitale simulato attuale: {capital:,.2f}")
    print("=" * 70 + "\n")

    for symbol in config.SYMBOLS:
        try:
            candles = fetch_recent_candles(symbol)
        except Exception as e:
            line = f"[{symbol}] Errore nel recupero dati: {e}"
            print(line)
            continue

        if not candles:
            continue

        current_price = candles[-1][4]
        position = positions.get(symbol)

        if position is not None:
            side = position["side"]
            entry = position["entry_price"]
            stop = position["stop_price"]
            target = position["take_profit_price"]

            hit_stop = (current_price <= stop) if side == "BUY" else (current_price >= stop)
            hit_target = (current_price >= target) if side == "BUY" else (current_price <= target)

            if hit_stop or hit_target:
                risk_amount = position["risk_amount"]
                risk_distance = abs(entry - stop)
                pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
                r_multiple = pnl_distance / risk_distance if risk_distance != 0 else 0
                pnl = risk_amount * r_multiple
                capital += pnl
                reason = "stop-loss" if hit_stop else "take-profit"
                line = (f"[{symbol}] CHIUSA ({reason}) @ {current_price:.4f} | "
                        f"P&L: {pnl:+.2f} | Capitale: {capital:,.2f}")
                print(line)
                summary_lines.append(line)
                positions[symbol] = None
            else:
                pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
                risk_distance = abs(entry - stop)
                r_multiple = pnl_distance / risk_distance if risk_distance != 0 else 0
                line = (f"[{symbol}] {side} ancora aperta @ {current_price:.4f} "
                        f"(entrata: {entry:.4f} | {r_multiple:+.2f}R)")
                print(line)
                summary_lines.append(line)
            continue

        decision = strategy_core.evaluate(candles)
        executed = False

        if decision.signal in ("BUY", "SELL"):
            open_count = sum(1 for v in positions.values() if v is not None)
            if open_count < config.MAX_CONCURRENT_POSITIONS:
                risk_amount = capital * (config.RISK_PER_TRADE_PCT / 100) * decision.volatility_scale
                currency_code = symbol.split("/")[0]
                print_news_warning(symbol, currency_code)
                positions[symbol] = {
                    "side": decision.signal,
                    "entry_price": decision.price,
                    "stop_price": decision.stop_price,
                    "take_profit_price": decision.take_profit_price,
                    "risk_amount": risk_amount,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                }
                executed = True
                line = (f"[{symbol}] NUOVA {decision.signal} @ {decision.price:.4f} | "
                        f"conferme: {decision.confirmations}/11 | rischio: {risk_amount:.2f}")
                print(line)
                summary_lines.append(line)

        log_decision(symbol, decision, executed)

    state["capital"] = capital
    state["positions"] = positions
    save_state(state)
    log_equity(state)

    summary_lines.append("")
    summary_lines.append(f"Capitale finale: {capital:,.2f}")
    summary_lines.append(f"Rendimento dal via: {(capital / NOTIONAL_CAPITAL_START - 1) * 100:+.2f}%")
    open_count = sum(1 for v in positions.values() if v is not None)
    summary_lines.append(f"Posizioni aperte: {open_count}")

    if len(summary_lines) <= 5:
        summary_lines.append("Nessun movimento oggi (nessuna apertura/chiusura).")

    message = "\n".join(summary_lines)
    print("\n" + "=" * 70)
    print(message)
    print("=" * 70)

    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    run_daily_check()
