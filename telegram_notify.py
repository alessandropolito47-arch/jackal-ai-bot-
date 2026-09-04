"""
TELEGRAM NOTIFY - Invia messaggi su Telegram
================================================
Usa l'API gratuita di Telegram Bot per inviare messaggi di testo
al tuo telefono. Nessuna libreria speciale necessaria oltre
'requests' (che abbiamo gia').

Per usarlo ti servono due cose (spiegate nella guida):
1. Un TOKEN del bot (ottenuto da @BotFather su Telegram)
2. Il tuo CHAT_ID personale (il numero che identifica la tua chat)
"""

import requests


def send_telegram_message(token, chat_id, text):
    """
    Invia un messaggio di testo alla chat Telegram indicata.
    Non solleva mai errori che blocchino il bot: se l'invio fallisce,
    stampa solo un avviso e continua.
    """
    if not token or not chat_id:
        print("  [telegram] Token o chat_id mancanti: notifica non inviata.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Telegram limita i messaggi a 4096 caratteri
    text = text[:4000]
    payload = {"chat_id": chat_id, "text": text}

    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        print("  [telegram] Notifica inviata con successo.")
        return True
    except Exception as e:
        print(f"  [telegram] Errore nell'invio della notifica: {e}")
        return False
