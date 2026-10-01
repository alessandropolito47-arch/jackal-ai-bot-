"""
NEWS CRIPTOVALUTA.IT - Rassegna quotidiana su Telegram (The Jackal AI Bot)
============================================================================
Ogni mattina legge il feed RSS pubblico di criptovaluta.it, prende gli
articoli delle ultime 24 ore e invia su Telegram una rassegna ordinata:
  - prima le notizie di RISCHIO (hack, crolli, Fed/tassi, regolamentazione)
  - poi quelle che riguardano i nostri mercati: crypto, oro, forex/macro
In fondo aggiunge un COMMENTO automatico di Claude (API Anthropic) su cosa
significano le notizie per i bot Jackal AI. Il commento compare solo se nei
Secrets del repository c'e' ANTHROPIC_API_KEY; senza chiave arrivano solo
titoli e link. Il commento e' informativo: i bot non cambiano regole.
"""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from telegram_notify import send_telegram_message

FEED_URL = "https://www.criptovaluta.it/feed/"
ORE = 24
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODELLO = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

CONTESTO_BOT = """Sei l'analista dei bot di trading Jackal AI (conto DEMO Pepperstone). Regole dei bot:
- BOT CRYPTO (giornaliero, 21 crypto): segue il trend, quasi sempre in ACQUISTO; stop 2 ATR sul server,
  parziale a +1R, poi pareggio e trailing 2 ATR, target 5 ATR; segnali manuali contro-trend solo informativi.
- BOT ORO (XAUUSD, 4 ore): solo ACQUISTI sulla rottura del massimo di 20 candele, stop sul minimo di 10.
- BOT FOREX (giornaliero, carry + trend): opera solo nella direzione con swap positivo e a favore del trend
  (oggi: BUY USDJPY e AUDJPY, SELL EURUSD; CADJPY fermo); filtro notizie ad alto impatto.
I bot NON cambiano regole in base alle notizie."""

ISTRUZIONI = """Scrivi in italiano, tono professionale e sobrio, massimo 900 caratteri, senza markdown.
Struttura: 1) il quadro del giorno in due frasi; 2) per CRYPTO, ORO e FOREX una riga ciascuno su cosa
le notizie potrebbero significare rispetto alle regole dei bot (rischi o conferme); 3) 'Da tenere d'occhio:'
con al massimo due punti. Non fare previsioni di prezzo, non dare consigli di acquisto o vendita, non
suggerire di intervenire sui bot. Se le notizie non sono rilevanti per i bot, dillo chiaramente."""

CATEGORIE = [
    ("⚠️ RISCHIO", r"hack|attacc|crollo|crolla|crash|liquidaz|panico|fallim|bancarott|sec\b|divieto|"
                  r"sanzion|guerra|fed\b|federal reserve|tassi|treasury|rendimenti|inflazione"),
    ("🥇 ORO / METALLI", r"\boro\b|gold|argento|xau|metalli"),
    ("💱 FOREX / MACRO", r"dollaro|yen|euro\b|bce|boj|banca centrale|valute|petrolio|pil\b|occupazione"),
    ("₿ CRYPTO PRINCIPALI", r"bitcoin|btc|ethereum|\beth\b|solana|\bsol\b|ripple|xrp|chainlink|litecoin|"
                           r"dogecoin|cardano|avalanche|polkadot|etf"),
]


def leggi_feed():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "Mozilla/5.0 (JackalAIBot news)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    articoli = []
    for item in root.iter("item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        data = item.findtext("pubDate")
        try:
            quando = parsedate_to_datetime(data).astimezone(timezone.utc)
        except Exception:
            continue
        articoli.append((quando, titolo, link))
    return articoli


def classifica(titolo):
    t = titolo.lower()
    for nome, pattern in CATEGORIE:
        if re.search(pattern, t):
            return nome
    return None


def commento_claude(titoli):
    """Chiede a Claude un breve commento sulle notizie (solo i titoli)."""
    if not ANTHROPIC_API_KEY or not titoli:
        return None
    import requests
    corpo = {
        "model": MODELLO,
        "max_tokens": 600,
        "system": CONTESTO_BOT + "\n\n" + ISTRUZIONI,
        "messages": [{"role": "user", "content": "Titoli delle ultime 24 ore da criptovaluta.it:\n" +
                      "\n".join(f"- {t}" for t in titoli)}],
    }
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                          headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          data=json.dumps(corpo))
        r.raise_for_status()
        testo = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()
        return testo or None
    except Exception as e:
        return f"(commento non disponibile: {e})"


def main():
    limite = datetime.now(timezone.utc) - timedelta(hours=ORE)
    try:
        articoli = [a for a in leggi_feed() if a[0] >= limite]
    except Exception as e:
        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                              f"📰 Rassegna criptovaluta.it: feed non raggiungibile ({e}).")
        return
    gruppi = {nome: [] for nome, _ in CATEGORIE}
    altri = 0
    for quando, titolo, link in sorted(articoli, reverse=True):
        cat = classifica(titolo)
        if cat:
            gruppi[cat].append(f"• {quando.strftime('%d/%m %H:%M')} UTC - {titolo}\n  {link}")
        else:
            altri += 1
    righe = [f"📰 RASSEGNA CRIPTOVALUTA.IT - ultime {ORE} ore ({len(articoli)} articoli)", ""]
    for nome, _ in CATEGORIE:
        if gruppi[nome]:
            righe.append(nome)
            righe.extend(gruppi[nome])
            righe.append("")
    if altri:
        righe.append(f"(+{altri} articoli su altri temi)")
    commento = commento_claude([t for _, t, _ in sorted(articoli, reverse=True)][:40])
    if commento:
        righe += ["", "🧠 COMMENTO DI CLAUDE", commento]
    righe += ["", "Nota: solo informativa. I bot non cambiano le regole in base alle notizie."]
    messaggio = "\n".join(righe)
    if len(messaggio) > 3900:
        messaggio = messaggio[:3850] + "\n... (rassegna troncata)"
    print(messaggio)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, messaggio)


if __name__ == "__main__":
    main()
