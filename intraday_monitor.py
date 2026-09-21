"""
INTRADAY MONITOR - Sorveglianza delle posizioni gia' aperte
================================================================
AGGIORNAMENTO: stessa logica di presa di profitto parziale del
controllo giornaliero. Mantiene anche il controllo notizie (una sola
volta per titolo, tramite notified_news.json).
"""

import json
import os
from datetime import datetime, timezone, timedelta

import config
from news_filter import check_important_news
from telegram_notify import send_telegram_message

STATE_PATH = "paper_state.json"
NOTIFIED_NEWS_PATH = "notified_news.json"
NEWS_RETENTION_DAYS = 14
PARTIAL_TP_R = 1.0

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

        result = check_position(position, current_price)

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
        message_parts.append("⚡ SORVEGLIANZA INTRADAY - The Jackal AI Bot\n")
        message_parts.extend(partial_lines)
    if closed_lines:
        if message_parts:
            message_parts.append("")
        else:
            message_parts.append("⚡ SORVEGLIANZA INTRADAY - The Jackal AI Bot\n")
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
