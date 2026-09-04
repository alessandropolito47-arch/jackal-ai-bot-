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
from news_filter import check_important_news
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
    capital_at_start = capital

    new_lines = []
    closed_lines = []
    open_lines = []
    news_lines = []

    print("=" * 70)
    print("THE JACKAL AI BOT - PAPER TRADING (VERSIONE MEGA, automatico)")
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
            side = position["side"]
            entry = position["entry_price"]
            stop = position["stop_price"]
            target = position["take_profit_price"]

            # TRAILING STOP: lo stop segue il prezzo migliore raggiunto da
            # quando la posizione e' aperta, mantenendo la stessa distanza
            # di rischio iniziale - ma si sposta SOLO a favore, mai indietro.
            initial_risk_distance = position.get("initial_risk_distance", abs(entry - stop))
            trailing_moved = False

            if side == "BUY":
                position["extreme_price"] = max(position.get("extreme_price", entry), current_price)
                trailing_stop = position["extreme_price"] - initial_risk_distance
                if trailing_stop > stop:
                    stop = trailing_stop
                    position["stop_price"] = stop
                    trailing_moved = True
            else:
                position["extreme_price"] = min(position.get("extreme_price", entry), current_price)
                trailing_stop = position["extreme_price"] + initial_risk_distance
                if trailing_stop < stop:
                    stop = trailing_stop
                    position["stop_price"] = stop
                    trailing_moved = True

            hit_stop = (current_price <= stop) if side == "BUY" else (current_price >= stop)
            hit_target = (current_price >= target) if side == "BUY" else (current_price <= target)

            if hit_stop or hit_target:
                risk_amount = position["risk_amount"]
                risk_distance = abs(entry - stop)
                pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
                r_multiple = pnl_distance / risk_distance if risk_distance != 0 else 0
                pnl = risk_amount * r_multiple
                pct_change = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100
                capital += pnl
                reason = "STOP-LOSS" if hit_stop else "TAKE-PROFIT"
                emoji = "🔴" if hit_stop else "🟢"
                line = (f"{emoji} [{symbol}] {reason}\n"
                        f"   Entrata: {entry:.4f} -> Uscita: {current_price:.4f} ({pct_change:+.2f}%)\n"
                        f"   P&L: {pnl:+.2f} ({r_multiple:+.2f}R) | Nuovo capitale: {capital:,.2f}")
                print(line)
                closed_lines.append(line)
                positions[symbol] = None
            else:
                pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
                risk_distance_now = abs(entry - stop)
                r_multiple = pnl_distance / risk_distance_now if risk_distance_now != 0 else 0
                pct_change = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100
                trailing_note = " 🔄 stop aggiornato" if trailing_moved else ""
                line = (f"[{symbol}] {side} | prezzo: {current_price:.4f} ({pct_change:+.2f}%)\n"
                        f"   entrata: {entry:.4f} | stop: {stop:.4f} | target: {target:.4f} | {r_multiple:+.2f}R{trailing_note}")
                print(line)
                open_lines.append(line)
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
                    "extreme_price": decision.price,
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

    if not new_lines and not closed_lines and not open_lines:
        message_parts.append("Nessuna posizione aperta e nessun movimento oggi.")

    message = "\n".join(message_parts)
    print("\n" + "=" * 70)
    print(message)
    print("=" * 70)

    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    run_daily_check()
