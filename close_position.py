"""
CHIUSURA MANUALE - Chiude una posizione specifica al prezzo di mercato attuale
==================================================================================
Permette di chiudere una posizione aperta in qualsiasi momento, indipendentemente
da stop-loss o take-profit, al prezzo di mercato corrente.

USO (da riga di comando, o tramite GitHub Actions con input):
    python close_position.py SOL/USDT
"""

import sys
import json
import os
from datetime import datetime, timezone

from telegram_notify import send_telegram_message

STATE_PATH = "paper_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def load_state():
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


def close_manually(symbol):
    state = load_state()
    positions = state["positions"]
    capital = state["capital"]

    if symbol not in positions or positions[symbol] is None:
        message = f"⚠️ CHIUSURA MANUALE FALLITA\n[{symbol}] non risulta come posizione aperta."
        print(message)
        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
        return

    position = positions[symbol]
    current_price = fetch_current_price(symbol)

    if current_price is None:
        message = f"⚠️ CHIUSURA MANUALE FALLITA\n[{symbol}] impossibile recuperare il prezzo attuale."
        print(message)
        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
        return

    side = position["side"]
    entry = position["entry_price"]
    risk_amount = position["risk_amount"]
    initial_risk_distance = position.get("initial_risk_distance", abs(entry - position["stop_price"]))

    pnl_distance = (current_price - entry) if side == "BUY" else (entry - current_price)
    r_multiple = pnl_distance / initial_risk_distance if initial_risk_distance != 0 else 0
    pnl = risk_amount * r_multiple
    pct_change = (current_price - entry) / entry * 100 if side == "BUY" else (entry - current_price) / entry * 100

    capital += pnl
    positions[symbol] = None

    state["capital"] = capital
    state["positions"] = positions
    save_state(state)

    esito = "PROFITTO" if pnl >= 0 else "PERDITA"
    emoji = "🟢" if pnl >= 0 else "🔴"

    message = (
        f"{emoji} CHIUSURA MANUALE [{symbol}] - {esito}\n"
        f"   Entrata: {entry:.4f} -> Uscita: {current_price:.4f} ({pct_change:+.2f}%)\n"
        f"   P&L: {pnl:+.2f} ({r_multiple:+.2f}R) | Nuovo capitale: {capital:,.2f}\n"
        f"   Chiuso manualmente il {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
    )
    print(message)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python close_position.py SIMBOLO (es. SOL/USDT)")
        sys.exit(1)

    symbol_to_close = sys.argv[1]
    close_manually(symbol_to_close)
