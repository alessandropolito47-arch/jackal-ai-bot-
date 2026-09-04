"""
INTRADAY MONITOR - Sorveglianza delle posizioni gia' aperte
================================================================
Diverso dal controllo giornaliero: questo script NON valuta nuovi
segnali di ingresso (avrebbe poco senso, dato che la strategia si
basa su candele giornaliere che non cambiano nell'arco della
giornata). Si limita a controllare se il prezzo ATTUALE delle
posizioni gia' aperte ha toccato lo stop-loss o il take-profit,
per chiuderle tempestivamente anche durante movimenti bruschi
infragiornalieri, invece di aspettare il controllo notturno.

Include anche l'aggiornamento del trailing stop, per coerenza con
il controllo giornaliero.

USO:
    python intraday_monitor.py
"""

import json
import os
from datetime import datetime, timezone

import config
from telegram_notify import send_telegram_message

STATE_PATH = "paper_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"capital": 10_000.0, "positions": {}}
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def fetch_current_price(symbol):
    import yfinance as yf
    base_currency = symbol.split("/")[0]
    yf_symbol = f"{base_currency}-USD"
    df = yf.Ticker(yf_symbol).history(period="1d", interval="5m")
    if df.empty:
        df = yf.Ticker(yf_symbol).history(period="5d", interval="1d")
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


def main():
    state = load_state()
    capital = state["capital"]
    positions = state["positions"]

    open_symbols = [s for s, p in positions.items() if p is not None]
    if not open_symbols:
        print("Nessuna posizione aperta da sorvegliare.")
        return

    print(f"Sorveglianza intraday: {len(open_symbols)} posizioni aperte, ore {datetime.now(timezone.utc).isoformat()}")

    alerts = []

    for symbol in open_symbols:
        position = positions[symbol]
        try:
            current_price = fetch_current_price(symbol)
        except Exception as e:
            print(f"[{symbol}] Errore nel recupero prezzo: {e}")
            continue

        if current_price is None:
            continue

        side = position["side"]
        entry = position["entry_price"]
        stop = position["stop_price"]
        target = position["take_profit_price"]
        initial_risk_distance = position.get("initial_risk_distance", abs(entry - stop))

        if side == "BUY":
            position["extreme_price"] = max(position.get("extreme_price", entry), current_price)
            trailing_stop = position["extreme_price"] - initial_risk_distance
            if trailing_stop > stop:
                stop = trailing_stop
                position["stop_price"] = stop
        else:
            position["extreme_price"] = min(position.get("extreme_price", entry), current_price)
            trailing_stop = position["extreme_price"] + initial_risk_distance
            if trailing_stop < stop:
                stop = trailing_stop
                position["stop_price"] = stop

        hit_stop = (current_price <= stop) if side == "BUY" else (current_price >= stop)
        hit_target = (current_price >= target) if side == "BUY" else (current_price <= target)

        if hit_stop or hit_target:
            risk_amount = position["risk_amount"]
            risk_distance = abs(entry - stop)
            pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
            r_multiple = pnl_distance / risk_distance if risk_distance != 0 else 0
            pnl = risk_amount * r_multiple
            capital += pnl
            reason = "STOP-LOSS" if hit_stop else "TAKE-PROFIT"
            emoji = "🔴" if hit_stop else "🟢"
            pct_change = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100

            alert = (f"{emoji} CHIUSURA INTRADAY [{symbol}] {reason}\n"
                     f"   Entrata: {entry:.4f} -> Uscita: {current_price:.4f} ({pct_change:+.2f}%)\n"
                     f"   P&L: {pnl:+.2f} ({r_multiple:+.2f}R) | Nuovo capitale: {capital:,.2f}")
            print(alert)
            alerts.append(alert)
            positions[symbol] = None

    state["capital"] = capital
    state["positions"] = positions
    save_state(state)

    if alerts:
        message = "⚡ SORVEGLIANZA INTRADAY - The Jackal AI Bot\n\n" + "\n\n".join(alerts)
        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
    else:
        print("Nessuna posizione ha toccato stop o target in questo controllo.")


if __name__ == "__main__":
    main()
