"""
INTRADAY MONITOR - Sorveglianza delle posizioni gia' aperte
================================================================
Diverso dal controllo giornaliero: questo script NON valuta nuovi
segnali di ingresso. Si limita a controllare se il prezzo ATTUALE
delle posizioni gia' aperte ha toccato lo stop-loss o il take-profit,
e aggiorna il trailing stop.

Controlla anche le notizie rilevanti (CoinTelegraph) su OGNI posizione
ancora aperta - ma segnala ogni notizia SOLO UNA VOLTA (tiene traccia
di quelle gia' notificate in notified_news.json), evitando di
rimandare lo stesso titolo ad ogni ciclo di 30 minuti.

USO:
    python intraday_monitor.py
"""

import json
import os
from datetime import datetime, timezone, timedelta

import config
from news_filter import check_important_news
from telegram_notify import send_telegram_message

STATE_PATH = "paper_state.json"
NOTIFIED_NEWS_PATH = "notified_news.json"
NEWS_RETENTION_DAYS = 14  # dopo quanti giorni una notizia "vecchia" viene dimenticata

TELEGRAM_
