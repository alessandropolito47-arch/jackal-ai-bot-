"""
INTRADAY MONITOR - Sorveglianza delle posizioni gia' aperte (ogni 30 minuti)
================================================================================
AGGIORNAMENTO 27/09/2026 - stesse regole di uscita dell'EA MT5 v3.16, tramite
position_manager.py: parziale a +1R con pareggio, poi trailing a 2 ATR dal
massimo raggiunto, target finale a 5 ATR. Mantiene il controllo notizie
(una sola volta per titolo, tramite notified_news.json).
"""

import json
import os
from datetime import datetime, timezone, timedelta

import config
import position_manager as pm
from news_filter import check_important_news
from telegram_notify import send_telegram_message

STATE_PATH = "paper_state.json"
NOTIFIED_NEWS_PATH = "notified_news.json"
NEWS_RETENTION_DAYS = 14
PARTIAL_TP_R = pm.PARTIAL_TP_R

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


def load_notified_news():
    if not os.path.exists(NOTIFIED_NEWS_PATH):
        return []
    with open(NOTIFIED_NEWS_PATH, "r") as f:
        return json.load(f)


def save_notified_news(notified_list):
    with open(NOTIFIED_NEWS_PATH, "w") as f:
        json.dump(notified_list, f, indent=2)


def prune_old_notified_news(notified_list):
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_RETENTION_DAYS)
    pruned = []
    for item in notified_list:
        try:
            seen_at = datetime.fromisoformat(item["notified_at"])
            if seen_at >= cutoff:
                pruned.append(item)
        except (KeyError, ValueError):
            continue
    return pruned


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

    notified_news = prune_old_notified_news(load_notified_news())
    already_notified_titles = {item["title"] for item in notified_news}

    open_symbols = [s for s, p in positions.items() if p is not None]
    if not open_symbols:
        print("Nessuna posizione aperta da sorvegliare.")
        save_notified_news(notified_news)
        return

    print(f"Sorveglianza intraday: {len(open_symbols)} posizioni aperte, ore {datetime.now(timezone.utc).isoformat()}")

    closed_lines = []
    partial_lines = []
    news_alerts = []
    new_notifications = []

    for symbol in open_symbols:
        position = positions[symbol]

        currency_code = symbol.split("/")[0]
        try:
            news = check_important_news(currency_code)
            nuove = [n for n in news if n["title"] not in already_notified_titles]
            if nuove:
                news_text = (f"⚠️ [{symbol}] {len(nuove)} notizia/e NUOVA/E:\n" +
                             "\n".join(f"   - {item['title']}" for item in nuove))
                print(news_text)
                news_alerts.append(news_text)
                for item in nuove:
                    already_notified_titles.add(item["title"])
                    new_notifications.append({
                        "title": item["title"], "symbol": symbol,
                        "notified_at": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            print(f"[{symbol}] Errore nel controllo notizie: {e}")

        try:
            current_price = fetch_current_price(symbol)
        except Exception as e:
            print(f"[{symbol}] Errore nel recupero prezzo: {e}")
            continue

        if current_price is None:
            continue

        pm.allinea_target(position)
        pm.aggiorna_trailing(position)
        result = pm.check_position(position, current_price)
        if result is None or result["action"] == "partial":
            pm.aggiorna_estremo(position, current_price)

        if result is None:
            continue

        elif result["action"] == "partial":
            capital += result["pnl"]
            position["partial_taken"] = True
            position["partial_r_locked"] = PARTIAL_TP_R * 0.5
            position["stop_price"] = result["new_stop"]
            line = (f"🟡 PRESA PARZIALE INTRADAY [{symbol}] (+{PARTIAL_TP_R}R)\n"
                    f"   Meta' posizione chiusa: +{result['pnl']:.2f} | Nuovo capitale: {capital:,.2f}\n"
                    f"   Stop meta' rimanente spostato a pareggio: {result['new_stop']:.4f}")
            print(line)
            partial_lines.append(line)

        elif result["action"] == "close":
            capital += result["pnl"]
            emoji = "🟢" if result["pnl"] >= 0 else "🔴"
            line = (f"{emoji} CHIUSURA INTRADAY [{symbol}] {result['reason']}\n"
                    f"   P&L: {result['pnl']:+.2f} ({result['r_multiple']:+.2f}R totale) | Nuovo capitale: {capital:,.2f}")
            print(line)
            closed_lines.append(line)
            positions[symbol] = None

    state["capital"] = capital
    state["positions"] = positions
    save_state(state)

    notified_news.extend(new_notifications)
    save_notified_news(notified_news)

    message_parts = []
    if partial_lines:
        message_parts.append("🧪 SIMULAZIONE GITHUB - sorveglianza intraday (NON e' il conto Pepperstone)\n")
        message_parts.extend(partial_lines)
    if closed_lines:
        if message_parts:
            message_parts.append("")
        else:
            message_parts.append("🧪 SIMULAZIONE GITHUB - sorveglianza intraday (NON e' il conto Pepperstone)\n")
        message_parts.extend(closed_lines)

    if news_alerts:
        if message_parts:
            message_parts.append("")
        message_parts.append("📰 NOTIZIE NUOVE SU POSIZIONI APERTE\n")
        message_parts.extend(news_alerts)

    if message_parts:
        message = "\n\n".join(message_parts)
        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
    else:
        print("Nessuna posizione ha toccato stop, target o soglia parziale; nessuna notizia nuova.")


if __name__ == "__main__":
    main()
