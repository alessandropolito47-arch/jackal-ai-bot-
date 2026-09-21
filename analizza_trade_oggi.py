"""
ANALISI TRADE REALI - Ha mai toccato +1R prima di chiudersi?
================================================================
"""

import os
import yfinance as yf
from telegram_notify import send_telegram_message

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TRADES = [
    {"symbol": "ADA", "entry": 0.2190, "stop_originale": 0.1944, "exit": 0.2121, "esito": "perdita (manuale)"},
    {"symbol": "BNB", "entry": 744.28, "stop_originale": 701.2070, "exit": 712.35, "esito": "stop-loss"},
    {"symbol": "AVAX", "entry": 7.8620, "stop_originale": 7.2662, "exit": 7.5510, "esito": "stop-loss"},
    {"symbol": "ATOM", "entry": 1.8434, "stop_originale": None, "exit": 1.6953, "esito": "stop-loss"},
    {"symbol": "NEAR", "entry": 2.5300, "stop_originale": None, "exit": 2.3553, "esito": "stop-loss"},
    {"symbol": "DOT", "entry": 1.1055, "stop_originale": None, "exit": 1.0158, "esito": "stop-loss"},
    {"symbol": "ICP", "entry": 2.4677, "stop_originale": 2.2122, "exit": 2.8896, "esito": "take-profit"},
]


def main():
    lines = ["ANALISI STORICO TRADE - Hanno toccato +1R prima di chiudersi?\n"]
    lines.append(f"({len(TRADES)} trade analizzati, quelli con dati completi disponibili)\n")

    trade_1r_confermati = 0
    trade_analizzabili = 0

    for t in TRADES:
        symbol = t["symbol"]
        entry = t["entry"]
        exit_price = t["exit"]

        if t["stop_originale"] is not None:
            initial_risk_distance = entry - t["stop_originale"]
        else:
            initial_risk_distance = None

        block = [f"\n[{symbol}] entrata {entry}, uscita {exit_price} ({t['esito']})"]

        if initial_risk_distance is None:
            block.append("  Stop originale non disponibile - impossibile calcolare la soglia +1R esatta.")
            for line in block:
                print(line)
            lines.extend(block)
            continue

        one_r_target = entry + initial_risk_distance
        trade_analizzabili += 1

        yf_symbol = f"{symbol}-USD"
        try:
            df = yf.Ticker(yf_symbol).history(period="30d", interval="1h")
            if df.empty:
                block.append("  Nessun dato disponibile.")
            else:
                max_high = df["High"].max()
                r_raggiunto = (max_high - entry) / initial_risk_distance if initial_risk_distance != 0 else 0

                if max_high >= one_r_target:
                    block.append(f"  Massimo raggiunto: {max_high:.4f} ({r_raggiunto:+.2f}R)")
                    block.append(f"  SI': ha toccato +1R. La presa parziale avrebbe fatto la differenza.")
                    trade_1r_confermati += 1
                else:
                    block.append(f"  Massimo raggiunto: {max_high:.4f} ({r_raggiunto:+.2f}R)")
                    block.append(f"  NO: mai arrivato a +1R.")
        except Exception as e:
            block.append(f"  Errore nel recupero dati: {e}")

        for line in block:
            print(line)
        lines.extend(block)

    summary = (f"\n\nRIEPILOGO: su {trade_analizzabili} trade analizzabili, "
               f"{trade_1r_confermati} hanno toccato +1R prima di chiudersi.")
    print(summary)
    lines.append(summary)

    message = "\n".join(lines)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)


if __name__ == "__main__":
    main()
