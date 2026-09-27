"""
CONFIG (MEGA) - Configurazione allineata all'EA MT5 v3.16 (27/09/2026)
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

RISK_PER_TRADE_PCT = 0.75
MAX_CONCURRENT_POSITIONS = 10   # allineato all'EA MT5 (MaxPosizioniAperte)

ATR_STOP_MULTIPLIER = 2.0
TAKE_PROFIT_ATR_MULTIPLIER = 5.0   # target finale (5 ATR = 2,5R)

# Gestione dell'uscita (allineata all'EA MT5 v3.16)
PARTIAL_TP_R = 1.0     # presa parziale di meta' posizione a +1R
TRAILING_ATR = 2.0     # dopo la parziale lo stop segue il prezzo a 2 ATR dal massimo

VOLATILITY_SCALE_ENABLED = False   # disattivato: l'EA MT5 e i test usano rischio fisso per trade
VOLATILITY_LOOKBACK = 50
VOLATILITY_MIN_SCALE = 0.3

DRAWDOWN_CIRCUIT_BREAKER_PCT = 5.0

MIN_INDICATORS_CONFIRMING = 7
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

TREND_FILTER_PERIOD = 100

ADX_MIN_STRENGTH = 20

# Filtri di entrata v3.10 (letti da strategy_core.py)
USE_MFI = True
USE_SUPERTREND = True
USE_ICHIMOKU = True
ANTI_CHASE_ATR = 3.0

BACKTEST_STARTING_CAPITAL = 1_000.0
HISTORY_YEARS = 8

STATE_FILE = "positions_state_mega.json"
DECISION_LOG_FILE = "decision_log_mega.csv"
BACKTEST_REPORT_FILE = "mega_backtest_report.csv"
