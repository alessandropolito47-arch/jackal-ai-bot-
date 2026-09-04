"""
NEWS FILTER - Notizie crypto importanti (informativo, non blocca il bot)
============================================================================
Legge il feed RSS pubblico e gratuito di CoinTelegraph (una testata
giornalistica specializzata in crypto, senza bisogno di registrazione
ne' chiave API) e segnala i titoli recenti che menzionano la moneta
in questione E contengono parole chiave associate a eventi rilevanti
(hack, causa legale, normativa, crollo, ecc.).

Questo modulo NON blocca automaticamente le operazioni del bot: si
limita a segnalare notizie potenzialmente rilevanti, lasciando a te
la valutazione finale - questo filtro non e' mai stato validato
statisticamente come il resto della strategia.

USO:
    from news_filter import print_news_warning
    print_news_warning("BTC/USDT", "BTC")
"""

import feedparser

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
]

# Parole chiave (in inglese, lingua delle fonti) che spesso accompagnano
# notizie ad alto impatto sul prezzo.
HIGH_IMPACT_KEYWORDS = [
    "hack", "exploit", "breach", "stolen", "lawsuit", "sec ", "sues",
    "ban", "banned", "regulation", "regulatory", "crash", "plunge",
    "delist", "outage", "halt", "investigation", "fraud", "collapse",
    "liquidation", "etf approval", "etf rejected",
]

# Nomi completi per riconoscere meglio le monete nei titoli (oltre al ticker)
CURR
