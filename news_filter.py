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

RSS_FEEDS = ["https://cointelegraph.com/rss"]

HIGH_IMPACT_KEYWORDS = [
    "hack", "exploit", "breach", "stolen", "lawsuit", "sec ", "sues",
    "ban", "banned", "regulation", "regulatory", "crash", "plunge",
    "delist", "outage", "halt", "investigation", "fraud", "collapse",
    "liquidation", "etf approval", "etf rejected",
]

CURRENCY_NAMES = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "bnb",
    "XRP": "xrp",
    "ADA": "cardano",
    "AVAX": "avalanche",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "TRX": "tron",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "MATIC": "polygon",
    "NEAR": "near",
    "FIL": "filecoin",
    "ICP": "internet computer",
    "ETC": "ethereum classic",
    "XLM": "stellar",
    "ALGO": "algorand",
    "VET": "vechain",
    "SAND": "sandbox",
    "MANA": "decentraland",
    "AAVE": "aave",
}


def fetch_recent_headlines(max_items=60):
    headlines = []
    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:max_items]:
                headlines.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"  [news_filter] Impossibile leggere il feed {feed_url}: {e}")
    return headlines


def check_important_news(currency_code, max_results=3):
    currency_name = CURRENCY_NAMES.get(currency_code, "").lower()
    code_lower = currency_code.lower()

    headlines = fetch_recent_headlines()
    matches = []

    for item in headlines:
        title_lower = item["title"].lower()
        mentions_currency = (code_lower in title_lower) or (currency_name and currency_name in title_lower)
        if not mentions_currency:
            continue

        has_keyword = any(keyword in title_lower for keyword in HIGH_IMPACT_KEYWORDS)
        if has_keyword:
            matches.append(item)
            if len(matches) >= max_results:
                break

    return matches


def print_news_warning(symbol, currency_code):
    news = check_important_news(currency_code)
    if news:
        print(f"  ATTENZIONE [{symbol}]: {len(news)} notizia/e potenzialmente rilevante/i (CoinTelegraph):")
        for item in news:
            print(f"    - {item['title']}")
            if item["link"]:
                print(f"      {item['link']}")
        print(f"  Valuta tu se procedere con l'apertura, il bot continua comunque in automatico.")
