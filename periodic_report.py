"""
PERIODIC REPORT - Riepilogo settimanale/mensile su Telegram
================================================================
Legge la cronologia del capitale (paper_equity_log.csv, aggiornata
automaticamente ogni giorno dal controllo giornaliero) e calcola la
variazione sugli ultimi 7 giorni (settimanale) o 30 giorni (mensile),
poi manda un riepilogo su Telegram.

USO:
    python periodic_report.py weekly
    python periodic_report.py monthly
"""

import csv
import os
import sys
from datetime import datetime, timezone, timedelta

from telegram_notify import send_telegram_message

EQUITY_LOG_PATH = "paper_equity_log.csv"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

NOTIONAL_CAPITAL_START = 10_000.0


def load_equity_history():
    if not os.path.exists(EQUITY_LOG_PATH):
        return []
    rows = []
    with open(EQUITY_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp_utc"])
                capital = float(row["capital"])
                rows.append((ts, capital))
            except (KeyError, ValueError):
                continue
    return sorted(rows, key=lambda r: r[0])


def build_report(period_label, days_back):
    history = load_equity_history()
    if not history:
        return f"THE JACKAL AI BOT - Riepilogo {period_label}\n\nNessun dato ancora disponibile."

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)

    start_capital = history[0][1]
    for ts, capital in history:
        if ts <= cutoff:
            start_capital = capital
        else:
            break

    end_capital = history[-1][1]
    change_pct = (end_capital / start_capital - 1) * 100 if start_capital else 0
    change_abs = end_capital - start_capital

    overall_change_pct = (end_capital / NOTIONAL_CAPITAL_START - 1) * 100

    trend_emoji = "📈" if change_abs >= 0 else "📉"

    lines = [
        f"{trend_emoji} THE JACKAL AI BOT - Riepilogo {period_label}",
        f"Periodo: ultimi {days_back} giorni",
        "",
        f"Capitale inizio periodo: {start_capital:,.2f}",
        f"Capitale fine periodo:   {end_capital:,.2f}",
        f"Variazione nel periodo:  {change_abs:+,.2f} ({change_pct:+.2f}%)",
        "",
        f"Variazione totale dal via: {overall_change_pct:+.2f}%",
    ]
    return "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    if mode == "monthly":
        message = build_report("MENSILE", 30)
    else:
        message = build_report("SETTIMANALE", 7)

    print(message)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    main()
