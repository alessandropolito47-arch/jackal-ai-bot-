"""
CONFIG (MEGA) - Configurazione per la versione con tutti gli indicatori
============================================================================
"""

PAPER_TRADING = True

SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "DOGE/USDT",
    "DOT/USDT",
    "LINK/USDT",
    "LTC/USDT",
    "TRX/USDT",
    "ATOM/USDT",
    "UNI/USDT",
    "MATIC/USDT",
    "NEAR/USDT",
    "FIL/USDT",
    "ICP/USDT",
    "ETC/USDT",
    "XLM/USDT",
    "ALGO/USDT",
    "VET/USDT",
    "SAND/USDT",
    "MANA/USDT",
    "AAVE/USDT",
]

TIMEFRAMES = ["1d"]
DEFAULT_TIMEFRAME = "1d"

# ============================================================
# GESTIONE DEL RISCHIO
# ============================================================

RISK_PER_TRADE_PCT = 0.05
MAX_CONCURRENT_POSITIONS = 3

ATR_STOP_MULTIPLIER = 2.0
TAKE_PROFIT_ATR_MULTIPLIER = 3.0

# ============================================
