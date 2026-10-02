"""
NEWS FOREX - Rassegna quotidiana su Telegram per il bot forex (The Jackal AI Bot)
==================================================================================
Ogni mattina (lunedi'-venerdi') invia su Telegram:
  1) CALENDARIO: gli eventi economici ad ALTO impatto delle prossime 24 ore
     sulle valute dei nostri cambi (USD, JPY, EUR, AUD, CAD), con orario
     italiano, previsione e dato precedente (calendario pubblico ForexFactory)
  2) NOTIZIE: i titoli forex delle ultime 24 ore che riguardano quelle valute,
     banche centrali, tassi e interventi (feed RSS pubblici)
  3) COMMENTO di Claude (facoltativo): solo se nei Secrets c'e' ANTHROPIC_API_KEY
Solo informativa: il bot forex ha gia' il suo filtro notizie e non cambia regole.
"""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from telegram_notify import send_telegram_message

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODELLO = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

ROMA = ZoneInfo("Europe/Rome")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
GIORNI_LUNGHI = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
VALUTE = ["USD", "JPY", "EUR", "AUD", "CAD"]
CALENDARIO_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEED = [
    ("Investing.com IT", "https://it.investing.com/rss/news_1.rss"),
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
]
PAROLE = (r"dollar|usd|yen|jpy|euro|eur\b|aud|australian|cad|canadian|loonie|fed\b|fomc|powell|boj|bank of japan|"
          r"ueda|bce|ecb|lagarde|rba|boc|bank of canada|tassi|rate|inflazion|inflation|cpi|pce|occupazion|"
          r"payroll|nfp|jobs|intervent|intervention|treasury|rendiment|yield|carry|swap")
PAROLE_IT_EN = re.compile(PAROLE, re.IGNORECASE)

CONTESTO = """Sei l'analista del bot forex Jackal AI (conto DEMO). Regole: carry + trend sul giornaliero, opera solo
nella direzione con swap positivo e a favore del trend (oggi BUY USDJPY e AUDJPY, SELL EURUSD; CADJPY fermo),
stop 3 ATR sul server, parziale a +1R, uscita all'incrocio delle medie 20/50, filtro sugli eventi ad alto impatto.
Il bot NON cambia regole in base alle notizie."""
ISTRUZIONI = """Italiano, tono professionale, massimo 800 caratteri, senza markdown. 1) quadro in due frasi;
2) una riga per USDJPY/AUDJPY e una per EURUSD su rischi o conferme rispetto alle regole del bot (es. rischio di
intervento sullo yen, sorprese sui tassi); 3) 'Da tenere d'occhio:' max due punti. Nessuna previsione di prezzo,
nessun consiglio operativo, nessun invito a intervenire sul bot."""


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JackalAIBot news)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def calendario():
    """Eventi ad alto impatto nelle prossime 24 ore sulle nostre valute."""
    eventi = json.loads(scarica(CALENDARIO_URL))
    ora = datetime.now(timezone.utc)
    fine = ora + timedelta(hours=24)
    righe = []
    for e in eventi:
        if e.get("impact") != "High" or e.get("country") not in VALUTE:
            continue
        try:
            quando = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        if ora - timedelta(hours=1) <= quando <= fine:
            dettagli = []
            if e.get("forecast"):
                dettagli.append(f"previsto {e['forecast']}")
            if e.get("previous"):
                dettagli.append(f"prec. {e['previous']}")
            righe.append((quando, f"• {GIORNI[quando.astimezone(ROMA).weekday()]} {quando.astimezone(ROMA).strftime('%H:%M')} {e['country']} - {e.get('title','')}"
                                  + (f" ({', '.join(dettagli)})" if dettagli else "")))
    return [r for _, r in sorted(righe)]


def notizie():
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    trovate, viste, errori = [], set(), []
    for nome, url in FEED:
        try:
            root = ET.fromstring(scarica(url))
        except Exception as e:
            errori.append(f"{nome} non raggiungibile")
            continue
        for item in root.iter("item"):
            titolo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            try:
                quando = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc)
            except Exception:
                continue
            if quando < limite or titolo.lower() in viste or not PAROLE_IT_EN.search(titolo):
                continue
            viste.add(titolo.lower())
            trovate.append((quando, f"• {quando.astimezone(ROMA).strftime('%d/%m %H:%M')} [{nome}] {titolo}\n  {link}", titolo))
    trovate.sort(reverse=True)
    return trovate[:15], errori


def commento(eventi, titoli):
    if not ANTHROPIC_API_KEY:
        return None
    import requests
    testo = "Eventi alto impatto prossime 24h:\n" + ("\n".join(eventi) or "nessuno") + \
            "\n\nTitoli forex ultime 24h:\n" + ("\n".join(f"- {t}" for t in titoli) or "nessuno")
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                          headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          data=json.dumps({"model": MODELLO, "max_tokens": 600,
                                           "system": CONTESTO + "\n\n" + ISTRUZIONI,
                                           "messages": [{"role": "user", "content": testo}]}))
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip() or None
    except Exception as e:
        return f"(commento non disponibile: {e})"


def main():
    oggi = datetime.now(ROMA)
    righe = [f"💱 RASSEGNA FOREX - {GIORNI_LUNGHI[oggi.weekday()]} {oggi.strftime('%d/%m/%Y')}", ""]
    try:
        eventi = calendario()
        righe.append("📅 EVENTI AD ALTO IMPATTO (prossime 24 ore, ora italiana)")
        righe.extend(eventi or ["• nessun evento ad alto impatto su USD, JPY, EUR, AUD, CAD"])
    except Exception as e:
        eventi = []
        righe.append(f"📅 Calendario non disponibile ({e})")
    righe.append("")
    lista, errori = notizie()
    righe.append("📰 NOTIZIE SULLE NOSTRE VALUTE (ultime 24 ore)")
    righe.extend([r for _, r, _ in lista] or ["• nessuna notizia rilevante"])
    if errori:
        righe.append("(" + "; ".join(errori) + ")")
    c = commento(eventi, [t for _, _, t in lista])
    if c:
        righe += ["", "🧠 COMMENTO DI CLAUDE", c]
    righe += ["", "Nota: solo informativa. Il bot forex ha il suo filtro notizie e non cambia regole."]
    messaggio = "\n".join(righe)
    if len(messaggio) > 3900:
        messaggio = messaggio[:3850] + "\n... (rassegna troncata)"
    print(messaggio)
    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, messaggio)


if __name__ == "__main__":
    main()
